import datetime
import os
import random
import discord
import re
from configuration import Configuration
from service import Service
from utils.logger import get_logger
from utils.tenor_api_gif import get_tenor_gif

logger = get_logger("hall_of_shame_service")


def __service__():
    return HallOfShameService()


class HallOfShameService(Service):
    def __init__(self):
        super().__init__()
        self.hos_channel_id = Configuration.get("services.hall_of_shame.channel")
        self.admin_channel_id = Configuration.get("services.hall_of_shame.admin_channel")
        self.bad_words = Configuration.get("services.hall_of_shame.bad_words", [])
        self.tenor_api_key = os.environ.get("TENOR_API_KEY")
        # self.warnings = Configuration.get("warnings", {})
        self.warnings = {}

    def __start__(self):
        if not all([self.hos_channel_id, self.admin_channel_id]):
            raise RuntimeError("Hall of Shame channels not configured!")
        if self.tenor_api_key is None:
            raise RuntimeError("Tenor API key is missing!")
        logger.info("HallOfShameService started!")

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        found_words = self._detect_bad_words(message.content)
        if found_words:
            await self._process_infraction(message, found_words)

    def _detect_bad_words(self, content: str) -> list:
        content_lower = content.lower()
        return [word for word in self.bad_words if re.search(rf'\b{re.escape(word.lower())}\b', content_lower)]

    async def _process_infraction(self, message: discord.Message, bad_words: list):
        try:
            # Delete original message
            await message.delete()

            # Send private warning
            await self._send_user_warning(message.author, bad_words)

            # Update warnings
            user_id = str(message.author.id)
            self.warnings[user_id] = self.warnings.get(user_id, 0) + 1
            # TODO: Database entry for variables
            # Configuration.update("warnings", self.warnings)

            # Process punishment
            await self._apply_punishment(message.author)

            # Create Hall of Shame embed
            hos_channel = self.server.get_channel(self.hos_channel_id)
            embed = discord.Embed(
                title="🚨 Rule Violation Detected",
                color=discord.Color.red()
            )
            embed.add_field(
                name="Offending User",
                value=f"{message.author.mention} ({message.author.id})",
                inline=False
            )
            embed.add_field(
                name="Original Message",
                value=self._highlight_bad_words(message.content, bad_words),
                inline=False
            )
            embed.add_field(
                name="Detected Words",
                value=', '.join(bad_words),
                inline=False
            )

            # Add GIF
            gif_url = get_tenor_gif(random.choice(bad_words), self.tenor_api_key)
            if gif_url:
                embed.set_image(url=gif_url)

            await hos_channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Error processing infraction: {e}")

    def _highlight_bad_words(self, text: str, bad_words: list) -> str:
        for word in bad_words:
            text = re.sub(rf'\b({re.escape(word)})\b', r'**\1**', text, flags=re.IGNORECASE)
        return text

    async def _send_user_warning(self, user: discord.User, bad_words: list):
        try:
            embed = discord.Embed(
                title="⚠️ Content Warning",
                description=f"You used prohibited words: {', '.join(bad_words)}\n"
                            "Repeated violations will result in mutes/bans!",
                color=discord.Color.orange()
            )
            await user.send(embed=embed)
        except discord.Forbidden:
            logger.warning(f"Couldn't send DM to {user.id}")

    async def _apply_punishment(self, user: discord.Member):
        warnings = self.warnings.get(str(user.id), 0)

        if warnings >= 30:
            await user.ban(reason="Excessive warnings (30+)")
            await self._notify_admins(f"Banned {user.mention} for 30+ warnings")
        elif warnings >= 20:
            await user.kick(reason="Excessive warnings (20+)")
            await self._notify_admins(f"Kicked {user.mention} for 20+ warnings")
        elif warnings >= 15:
            await user.timeout(discord.utils.utcnow() + datetime.timedelta(days=7))
        elif warnings >= 10:
            await user.timeout(discord.utils.utcnow() + datetime.timedelta(days=1))
        elif warnings >= 5:
            await user.timeout(discord.utils.utcnow() + datetime.timedelta(minutes=15))
        elif warnings >= 3:
            await user.timeout(discord.utils.utcnow() + datetime.timedelta(minutes=5))

    async def _notify_admins(self, message: str):
        channel = self.server.get_channel(self.admin_channel_id)
        if channel:
            await channel.send(message)
