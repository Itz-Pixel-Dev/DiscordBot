import discord
from discord.ext import commands, tasks
import asyncio
import datetime
import re
import pytz
from bson.objectid import ObjectId

time_regex = re.compile(r"(\d+)([smhd])")
time_dict = {"s": 1, "m": 60, "h": 3600, "d": 86400}

class TimeConverter(commands.Converter):
    async def convert(self, ctx, argument):
        matches = time_regex.findall(argument.lower())
        time = 0
        for value, unit in matches:
            try:
                time += int(value) * time_dict[unit]
            except (KeyError, ValueError):
                raise commands.BadArgument(f"{value}{unit} is an invalid time format! Use s, m, h, or d.")
        if time == 0:
            raise commands.BadArgument("Please specify a valid time!")
        return time

class Reminders(commands.Cog):
    """Set reminders for yourself or for a channel"""
    
    def __init__(self, bot):
        self.bot = bot
        self.reminder_task.start()
        self.db = self.bot.db["reminders"]
    
    def cog_unload(self):
        self.reminder_task.cancel()
    
    @tasks.loop(seconds=30)
    async def reminder_task(self):
        """Check for reminders that need to be sent"""
        current_time = datetime.datetime.utcnow()
        
        # Find all reminders that are due
        async for reminder in self.db.find({"remind_time": {"$lte": current_time}}):
            # Get the channel
            channel = self.bot.get_channel(reminder["channel_id"])
            if not channel:
                # Try to fetch the channel if it's not in cache
                try:
                    channel = await self.bot.fetch_channel(reminder["channel_id"])
                except discord.NotFound:
                    # If channel doesn't exist anymore, delete the reminder
                    await self.db.delete_one({"_id": reminder["_id"]})
                    continue
            
            # Get the user
            try:
                user = await self.bot.fetch_user(reminder["user_id"])
            except discord.NotFound:
                # If user doesn't exist anymore, delete the reminder
                await self.db.delete_one({"_id": reminder["_id"]})
                continue
            
            # Create the embed
            embed = discord.Embed(
                title="⏰ Reminder",
                description=reminder["content"],
                color=0x3498db,
                timestamp=current_time
            )
            embed.set_footer(text=f"Reminder set on {reminder['created_at'].strftime('%Y-%m-%d %H:%M:%S UTC')}")
            
            # Send the reminder
            try:
                if reminder["dm"]:
                    # Send DM to the user
                    try:
                        await user.send(f"⏰ **Reminder!**", embed=embed)
                    except discord.Forbidden:
                        # If user has DMs disabled, send to the channel
                        await channel.send(f"{user.mention} ⏰ **Reminder!** (Could not send DM)", embed=embed)
                else:
                    # Send to the channel
                    await channel.send(f"{user.mention} ⏰ **Reminder!**", embed=embed)
            except Exception as e:
                print(f"Error sending reminder: {e}")
            
            # Delete the reminder
            await self.db.delete_one({"_id": reminder["_id"]})
    
    @reminder_task.before_loop
    async def before_reminder_task(self):
        await self.bot.wait_until_ready()
    
    @commands.group(aliases=["remind", "reminder"], invoke_without_command=True)
    async def remindme(self, ctx, time: TimeConverter, *, content: str):
        """Set a reminder
        
        Examples:
        - ;remindme 1h30m Take the pizza out of the oven
        - ;remindme 2d Check on the project status
        - ;remind 10m Call mom
        
        Time format: 
        - s: seconds
        - m: minutes
        - h: hours
        - d: days
        """
        await self.create_reminder(ctx, time, content, True)
    
    @remindme.command(name="here")
    async def remindme_here(self, ctx, time: TimeConverter, *, content: str):
        """Set a reminder that will be sent in the current channel
        
        Examples:
        - ;remindme here 1h30m Meeting starts
        - ;remind here 10m Break time
        """
        await self.create_reminder(ctx, time, content, False)
    
    async def create_reminder(self, ctx, time, content, dm=True):
        """Create a reminder in the database"""
        created_at = datetime.datetime.utcnow()
        remind_time = created_at + datetime.timedelta(seconds=time)
        
        reminder = {
            "user_id": ctx.author.id,
            "channel_id": ctx.channel.id,
            "guild_id": ctx.guild.id if ctx.guild else None,
            "content": content,
            "created_at": created_at,
            "remind_time": remind_time,
            "dm": dm
        }
        
        result = await self.db.insert_one(reminder)
        
        # Format time until reminder
        time_str = self.format_time_difference(time)
        
        embed = discord.Embed(
            title="⏰ Reminder Set",
            description=f"I'll remind you in **{time_str}**.",
            color=0x3498db,
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="Content", value=content, inline=False)
        embed.add_field(name="Reminder ID", value=str(result.inserted_id), inline=False)
        embed.add_field(name="Will remind at", value=f"{remind_time.strftime('%Y-%m-%d %H:%M:%S')} UTC", inline=False)
        embed.add_field(name="Destination", value="DM" if dm else "This channel", inline=False)
        
        await ctx.send(embed=embed)
    
    @remindme.command(name="list")
    async def remindme_list(self, ctx):
        """List all your active reminders"""
        reminders = await self.db.find({"user_id": ctx.author.id}).sort("remind_time", 1).to_list(length=None)
        
        if not reminders:
            return await ctx.send("You don't have any active reminders.")
        
        embed = discord.Embed(
            title="Your Reminders",
            description=f"You have {len(reminders)} active reminder(s).",
            color=0x3498db,
            timestamp=datetime.datetime.utcnow()
        )
        
        for i, reminder in enumerate(reminders, 1):
            time_left = reminder["remind_time"] - datetime.datetime.utcnow()
            time_str = self.format_timedelta(time_left)
            
            content = reminder["content"]
            if len(content) > 100:
                content = content[:97] + "..."
            
            embed.add_field(
                name=f"{i}. In {time_str}",
                value=f"**ID:** {reminder['_id']}\n**Content:** {content}\n**Destination:** {'DM' if reminder['dm'] else 'Channel'}",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @remindme.command(name="delete", aliases=["remove", "cancel"])
    async def remindme_delete(self, ctx, reminder_id: str):
        """Delete a reminder by its ID
        
        Example:
        - ;remindme delete 5f3e3e3e3e3e3e3e3e3e3e3e
        """
        try:
            object_id = ObjectId(reminder_id)
        except:
            return await ctx.send("Invalid reminder ID. Use the `remindme list` command to see your reminders and their IDs.")
        
        result = await self.db.delete_one({"_id": object_id, "user_id": ctx.author.id})
        
        if result.deleted_count == 0:
            return await ctx.send("Could not find a reminder with that ID. Make sure you own the reminder.")
        
        await ctx.send("✅ Reminder deleted successfully.")
    
    @remindme.command(name="clear")
    async def remindme_clear(self, ctx):
        """Delete all your reminders"""
        result = await self.db.delete_many({"user_id": ctx.author.id})
        
        if result.deleted_count == 0:
            return await ctx.send("You don't have any reminders to clear.")
        
        await ctx.send(f"✅ Cleared {result.deleted_count} reminder(s).")
    
    def format_time_difference(self, seconds):
        """Format a time difference in seconds to a human-readable string"""
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        parts = []
        if days > 0:
            parts.append(f"{int(days)} day{'s' if days != 1 else ''}")
        if hours > 0:
            parts.append(f"{int(hours)} hour{'s' if hours != 1 else ''}")
        if minutes > 0:
            parts.append(f"{int(minutes)} minute{'s' if minutes != 1 else ''}")
        if seconds > 0 and len(parts) < 2:
            parts.append(f"{int(seconds)} second{'s' if seconds != 1 else ''}")
        
        if not parts:
            return "less than a second"
        
        if len(parts) == 1:
            return parts[0]
        
        return ", ".join(parts[:-1]) + f" and {parts[-1]}"
    
    def format_timedelta(self, delta):
        """Format a timedelta to a human-readable string"""
        total_seconds = delta.total_seconds()
        if total_seconds < 0:
            return "now"
        return self.format_time_difference(total_seconds)

async def setup(bot):
    await bot.add_cog(Reminders(bot))