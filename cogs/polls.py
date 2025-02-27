import discord
from discord.ext import commands
import asyncio
import datetime
import re
from typing import Optional, List, Dict, Union

class Polls(commands.Cog):
    """Create and manage polls in your server"""
    
    def __init__(self, bot):
        self.bot = bot
        self.active_polls = {}  # Store active polls in memory
        self.emoji_letters = ['🇦', '🇧', '🇨', '🇩', '🇪', '🇫', '🇬', '🇭', '🇮', '🇯', '🇰', '🇱', '🇲', '🇳', '🇴', '🇵', '🇶', '🇷', '🇸', '🇹']
        self.yes_no_emojis = ['👍', '👎']
    
    @commands.group(invoke_without_command=True)
    async def poll(self, ctx, *, question: str = None):
        """Create a simple yes/no poll
        
        Example:
        - ;poll Should we have pizza for dinner?
        """
        if question is None:
            return await ctx.send("Please provide a question for the poll.")
        
        # Create a yes/no poll
        embed = discord.Embed(
            title="📊 Poll",
            description=question,
            color=0x3498db,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Created by {ctx.author.display_name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        
        message = await ctx.send(embed=embed)
        
        # Add reactions
        for emoji in self.yes_no_emojis:
            await message.add_reaction(emoji)
        
        # Store the poll in memory
        self.active_polls[message.id] = {
            "type": "yes_no",
            "question": question,
            "options": ["Yes", "No"],
            "emojis": self.yes_no_emojis,
            "author_id": ctx.author.id,
            "channel_id": ctx.channel.id,
            "message_id": message.id,
            "created_at": datetime.datetime.utcnow()
        }
    
    @poll.command(name="options", aliases=["multiple", "multi"])
    async def poll_options(self, ctx, question: str, *options):
        """Create a poll with multiple options
        
        Example:
        - ;poll options "What's your favorite color?" Red Blue Green Yellow
        - ;poll multi "Best programming language?" Python JavaScript Java C# Go
        
        You can provide up to 20 options.
        """
        if not options:
            return await ctx.send("Please provide at least 2 options for the poll.")
        
        if len(options) > 20:
            return await ctx.send("You can only have up to 20 options in a poll.")
        
        if len(options) < 2:
            return await ctx.send("You need at least 2 options for a poll.")
        
        # Create the poll embed
        embed = discord.Embed(
            title="📊 Poll",
            description=question,
            color=0x3498db,
            timestamp=datetime.datetime.utcnow()
        )
        
        # Add options to the embed
        option_text = ""
        for i, option in enumerate(options):
            option_text += f"{self.emoji_letters[i]} {option}\n"
        
        embed.add_field(name="Options", value=option_text, inline=False)
        embed.set_footer(text=f"Created by {ctx.author.display_name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        
        message = await ctx.send(embed=embed)
        
        # Add reactions for each option
        for i in range(len(options)):
            await message.add_reaction(self.emoji_letters[i])
        
        # Store the poll in memory
        self.active_polls[message.id] = {
            "type": "options",
            "question": question,
            "options": options,
            "emojis": self.emoji_letters[:len(options)],
            "author_id": ctx.author.id,
            "channel_id": ctx.channel.id,
            "message_id": message.id,
            "created_at": datetime.datetime.utcnow()
        }
    
    @poll.command(name="timed", aliases=["timer"])
    async def poll_timed(self, ctx, duration: str, question: str, *options):
        """Create a timed poll that will show results after the specified duration
        
        Duration format: 
        - 1m = 1 minute
        - 1h = 1 hour
        - 1d = 1 day
        
        Example:
        - ;poll timed 1h "Movie night tonight?" Yes No Maybe
        - ;poll timer 30m "Lunch options?" Pizza Burgers Salad Sushi
        
        You can provide up to 20 options. If no options are provided, it will be a yes/no poll.
        """
        # Parse the duration
        duration_seconds = 0
        time_regex = re.compile(r"(\d+)([smhd])")
        matches = time_regex.findall(duration.lower())
        
        for value, unit in matches:
            try:
                if unit == "s":
                    duration_seconds += int(value)
                elif unit == "m":
                    duration_seconds += int(value) * 60
                elif unit == "h":
                    duration_seconds += int(value) * 3600
                elif unit == "d":
                    duration_seconds += int(value) * 86400
            except ValueError:
                return await ctx.send("Invalid duration format. Use s, m, h, or d (e.g., 30m, 1h, 2h30m).")
        
        if duration_seconds <= 0:
            return await ctx.send("Please specify a valid duration greater than 0 seconds.")
        
        if duration_seconds > 7 * 86400:  # 7 days
            return await ctx.send("Polls can only last up to 7 days.")
        
        # Create the poll
        if not options:
            # Yes/No poll
            embed = discord.Embed(
                title="⏱️ Timed Poll",
                description=question,
                color=0x3498db,
                timestamp=datetime.datetime.utcnow()
            )
            
            end_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=duration_seconds)
            embed.add_field(name="Duration", value=f"Poll ends <t:{int(end_time.timestamp())}:R>", inline=False)
            embed.set_footer(text=f"Created by {ctx.author.display_name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
            
            message = await ctx.send(embed=embed)
            
            # Add reactions
            for emoji in self.yes_no_emojis:
                await message.add_reaction(emoji)
            
            # Store the poll in memory
            self.active_polls[message.id] = {
                "type": "timed_yes_no",
                "question": question,
                "options": ["Yes", "No"],
                "emojis": self.yes_no_emojis,
                "author_id": ctx.author.id,
                "channel_id": ctx.channel.id,
                "message_id": message.id,
                "created_at": datetime.datetime.utcnow(),
                "end_time": end_time
            }
            
            # Schedule the poll to end
            self.bot.loop.create_task(self.end_poll_after_duration(message.id, duration_seconds))
        else:
            # Multiple options poll
            if len(options) > 20:
                return await ctx.send("You can only have up to 20 options in a poll.")
            
            if len(options) < 2:
                return await ctx.send("You need at least 2 options for a poll.")
            
            # Create the poll embed
            embed = discord.Embed(
                title="⏱️ Timed Poll",
                description=question,
                color=0x3498db,
                timestamp=datetime.datetime.utcnow()
            )
            
            # Add options to the embed
            option_text = ""
            for i, option in enumerate(options):
                option_text += f"{self.emoji_letters[i]} {option}\n"
            
            embed.add_field(name="Options", value=option_text, inline=False)
            
            end_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=duration_seconds)
            embed.add_field(name="Duration", value=f"Poll ends <t:{int(end_time.timestamp())}:R>", inline=False)
            embed.set_footer(text=f"Created by {ctx.author.display_name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
            
            message = await ctx.send(embed=embed)
            
            # Add reactions for each option
            for i in range(len(options)):
                await message.add_reaction(self.emoji_letters[i])
            
            # Store the poll in memory
            self.active_polls[message.id] = {
                "type": "timed_options",
                "question": question,
                "options": options,
                "emojis": self.emoji_letters[:len(options)],
                "author_id": ctx.author.id,
                "channel_id": ctx.channel.id,
                "message_id": message.id,
                "created_at": datetime.datetime.utcnow(),
                "end_time": end_time
            }
            
            # Schedule the poll to end
            self.bot.loop.create_task(self.end_poll_after_duration(message.id, duration_seconds))
    
    @poll.command(name="end", aliases=["stop", "finish"])
    async def poll_end(self, ctx, message_id: int):
        """End a poll early and display the results
        
        Example:
        - ;poll end 123456789012345678
        
        You can get the message ID by right-clicking on the poll message and selecting "Copy ID".
        You must be the creator of the poll to end it.
        """
        # Check if the poll exists
        if message_id not in self.active_polls:
            return await ctx.send("Could not find a poll with that ID.")
        
        # Check if the user is the creator of the poll
        if ctx.author.id != self.active_polls[message_id]["author_id"] and not ctx.author.guild_permissions.administrator:
            return await ctx.send("You can only end polls that you created or if you're an administrator.")
        
        # End the poll
        await self.end_poll(message_id)
        await ctx.send("Poll ended successfully.")
    
    async def end_poll_after_duration(self, message_id: int, duration: int):
        """End a poll after the specified duration"""
        await asyncio.sleep(duration)
        await self.end_poll(message_id)
    
    async def end_poll(self, message_id: int):
        """End a poll and display the results"""
        if message_id not in self.active_polls:
            return
        
        poll_data = self.active_polls[message_id]
        
        try:
            # Get the channel and message
            channel = self.bot.get_channel(poll_data["channel_id"])
            if not channel:
                del self.active_polls[message_id]
                return
            
            message = await channel.fetch_message(message_id)
            if not message:
                del self.active_polls[message_id]
                return
            
            # Count the votes
            votes = {}
            total_votes = 0
            
            for reaction in message.reactions:
                if str(reaction.emoji) in poll_data["emojis"]:
                    index = poll_data["emojis"].index(str(reaction.emoji))
                    option = poll_data["options"][index]
                    # Subtract 1 to account for the bot's reaction
                    count = reaction.count - 1
                    votes[option] = count
                    total_votes += count
            
            # Create the results embed
            embed = discord.Embed(
                title="📊 Poll Results",
                description=poll_data["question"],
                color=0x3498db,
                timestamp=datetime.datetime.utcnow()
            )
            
            # Sort options by vote count (descending)
            sorted_options = sorted(votes.items(), key=lambda x: x[1], reverse=True)
            
            # Add results to the embed
            results_text = ""
            for option, count in sorted_options:
                percentage = (count / total_votes) * 100 if total_votes > 0 else 0
                bar_length = 20
                filled_length = int(bar_length * percentage / 100)
                bar = "█" * filled_length + "░" * (bar_length - filled_length)
                
                results_text += f"{option}: {count} votes ({percentage:.1f}%)\n"
                results_text += f"{bar}\n\n"
            
            if not results_text:
                results_text = "No votes were cast."
            
            embed.add_field(name=f"Results (Total: {total_votes} votes)", value=results_text, inline=False)
            embed.set_footer(text=f"Poll ended", icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None)
            
            # Send the results
            await channel.send(embed=embed)
            
            # Update the original message to show it's ended
            original_embed = message.embeds[0]
            if original_embed.title:
                original_embed.title = f"{original_embed.title} [ENDED]"
            
            await message.edit(embed=original_embed)
            
            # Remove the poll from memory
            del self.active_polls[message_id]
            
        except Exception as e:
            print(f"Error ending poll: {e}")
            # Clean up in case of error
            if message_id in self.active_polls:
                del self.active_polls[message_id]

async def setup(bot):
    await bot.add_cog(Polls(bot))