import discord
from discord.ext import commands
import aiohttp
import os
from datetime import datetime
import asyncio

class Weather(commands.Cog):
    """Weather commands for checking weather conditions in different locations"""
    
    def __init__(self, bot):
        self.bot = bot
        self.api_key = os.environ.get("OPENWEATHER_API_KEY", "")  # Will need to be added to .env
        self.base_url = "http://api.openweathermap.org/data/2.5/"
        self.icon_url = "http://openweathermap.org/img/wn/{}@2x.png"
        
    @commands.group(invoke_without_command=True)
    async def weather(self, ctx, *, location: str = None):
        """Get the current weather for a location"""
        if location is None:
            return await ctx.send("Please provide a location to check the weather for.")
        
        async with ctx.typing():
            weather_data = await self.get_current_weather(location)
            
            if not weather_data:
                return await ctx.send(f"Could not find weather data for **{location}**.")
            
            embed = self.format_current_weather(weather_data, location)
            await ctx.send(embed=embed)
    
    @weather.command(name="forecast")
    async def weather_forecast(self, ctx, *, location: str = None):
        """Get a 5-day weather forecast for a location"""
        if location is None:
            return await ctx.send("Please provide a location to check the forecast for.")
        
        async with ctx.typing():
            forecast_data = await self.get_forecast(location)
            
            if not forecast_data:
                return await ctx.send(f"Could not find forecast data for **{location}**.")
            
            embeds = self.format_forecast(forecast_data, location)
            
            if len(embeds) == 1:
                await ctx.send(embed=embeds[0])
            else:
                # Simple pagination
                current_page = 0
                message = await ctx.send(embed=embeds[current_page])
                
                # Add reactions for pagination
                await message.add_reaction("◀️")
                await message.add_reaction("▶️")
                
                def check(reaction, user):
                    return user == ctx.author and str(reaction.emoji) in ["◀️", "▶️"] and reaction.message.id == message.id
                
                while True:
                    try:
                        reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
                        
                        if str(reaction.emoji) == "▶️" and current_page < len(embeds) - 1:
                            current_page += 1
                            await message.edit(embed=embeds[current_page])
                            await message.remove_reaction(reaction, user)
                        
                        elif str(reaction.emoji) == "◀️" and current_page > 0:
                            current_page -= 1
                            await message.edit(embed=embeds[current_page])
                            await message.remove_reaction(reaction, user)
                        
                        else:
                            await message.remove_reaction(reaction, user)
                            
                    except asyncio.TimeoutError:
                        await message.clear_reactions()
                        break
    
    async def get_current_weather(self, location):
        """Fetch current weather data from OpenWeatherMap API"""
        if not self.api_key:
            return None
            
        params = {
            "q": location,
            "appid": self.api_key,
            "units": "metric"  # Use metric units by default
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.base_url}weather", params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    return None
            except Exception as e:
                print(f"Error fetching weather data: {e}")
                return None
    
    async def get_forecast(self, location):
        """Fetch 5-day forecast data from OpenWeatherMap API"""
        if not self.api_key:
            return None
            
        params = {
            "q": location,
            "appid": self.api_key,
            "units": "metric"  # Use metric units by default
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.base_url}forecast", params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    return None
            except Exception as e:
                print(f"Error fetching forecast data: {e}")
                return None
    
    def format_current_weather(self, data, location):
        """Format current weather data into an embed"""
        weather = data["weather"][0]
        main = data["main"]
        wind = data["wind"]
        sys = data["sys"]
        
        # Convert timestamp to readable time
        sunrise = datetime.fromtimestamp(sys["sunrise"]).strftime("%H:%M")
        sunset = datetime.fromtimestamp(sys["sunset"]).strftime("%H:%M")
        
        embed = discord.Embed(
            title=f"Weather in {data['name']}, {sys['country']}",
            description=f"**{weather['description'].capitalize()}**",
            color=0x3498db,
            timestamp=datetime.utcnow()
        )
        
        embed.set_thumbnail(url=self.icon_url.format(weather["icon"]))
        
        embed.add_field(name="Temperature", value=f"{main['temp']}°C", inline=True)
        embed.add_field(name="Feels Like", value=f"{main['feels_like']}°C", inline=True)
        embed.add_field(name="Humidity", value=f"{main['humidity']}%", inline=True)
        
        embed.add_field(name="Wind Speed", value=f"{wind['speed']} m/s", inline=True)
        embed.add_field(name="Pressure", value=f"{main['pressure']} hPa", inline=True)
        embed.add_field(name="Visibility", value=f"{data.get('visibility', 0) / 1000} km", inline=True)
        
        embed.add_field(name="Sunrise", value=sunrise, inline=True)
        embed.add_field(name="Sunset", value=sunset, inline=True)
        
        embed.set_footer(text=f"Requested by {location}")
        
        return embed
    
    def format_forecast(self, data, location):
        """Format forecast data into multiple embeds (one per day)"""
        embeds = []
        forecast_list = data["list"]
        city = data["city"]
        
        # Group forecasts by day
        days = {}
        for forecast in forecast_list:
            date = datetime.fromtimestamp(forecast["dt"]).strftime("%Y-%m-%d")
            if date not in days:
                days[date] = []
            days[date].append(forecast)
        
        # Create an embed for each day
        for date, forecasts in days.items():
            day_name = datetime.strptime(date, "%Y-%m-%d").strftime("%A")
            
            embed = discord.Embed(
                title=f"Forecast for {city['name']}, {city['country']}",
                description=f"**{day_name}, {date}**",
                color=0x3498db,
                timestamp=datetime.utcnow()
            )
            
            # Add each time period to the embed
            for forecast in forecasts:
                time = datetime.fromtimestamp(forecast["dt"]).strftime("%H:%M")
                weather = forecast["weather"][0]
                main = forecast["main"]
                
                embed.add_field(
                    name=f"{time} - {weather['description'].capitalize()}",
                    value=f"🌡️ **Temp:** {main['temp']}°C\n"
                          f"💧 **Humidity:** {main['humidity']}%\n"
                          f"💨 **Wind:** {forecast['wind']['speed']} m/s",
                    inline=True
                )
            
            embed.set_footer(text=f"Requested by {location}")
            embeds.append(embed)
        
        return embeds

async def setup(bot):
    await bot.add_cog(Weather(bot))