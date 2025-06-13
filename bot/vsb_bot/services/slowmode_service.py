import re
import discord

from ..service import Service
from ..utils.logger import get_logger

# Initialize logger for this service
logger = get_logger("slowmode_service")

def __service__():
    return SlowmodeService()


class SlowmodeService(Service):
    def __init__(self):
        super().__init__()
        # Load admin role IDs from configuration.json
        self.admin_roles = [
            631140434332221462,
            689908370018402343,
            689908435235766275
        ]

    def __start__(self):
        # Log that the service has started
        logger.info("SlowmodeService is starting!")

    async def on_ready(self):
        # Log that the service is ready
        logger.info("SlowmodeService is ready!")

    async def on_message(self, message: discord.Message):
        # Ignore bot's own messages
        if message.author == self.client.user:
            return

        # Check if the user has an admin role
        if not self.is_admin(message.author):
            return

        # Handle `!slowmode` command
        if message.content.startswith("!slowmode"):
            await self.handle_slowmode_command(message)
            return

        # Handle "ticho"/"TICHO" trigger
        if message.content.lower() in ["ticho", "ticcho"]:
            await self.set_slowmode(message.channel, 60)  # Default: 1 minute
            await message.channel.send("Slowmode enabled for 1 minute.")
            return

    async def handle_slowmode_command(self, message: discord.Message):
        """
        Handles the `!slowmode` command.
        Parses the time argument and sets slowmode for the current channel.
        """
        try:
            # Extract time from command (e.g., "!slowmode 1h", "!slowmode 30s")
            match = re.match(r"!slowmode\s*(\d+)?([hms]?)", message.content)
            if not match:
                await message.channel.send("Invalid command format. Use `!slowmode <time>` (e.g., `!slowmode 1h`).")
                return

            # Extract time and unit
            time_value = int(match.group(1)) if match.group(1) else 1  # Default to 1
            time_unit = match.group(2) or "m"  # Default to minutes if no unit

            # Convert time to seconds
            duration_in_seconds = self.convert_to_seconds(time_value, time_unit)
            if duration_in_seconds is None:
                await message.channel.send("Invalid time format. Use `h`, `m`, or `s`.")
                return

            # Set slowmode for the current channel
            await self.set_slowmode(message.channel, duration_in_seconds)
            await message.channel.send(f"Slowmode enabled for {time_value}{time_unit}.")
        except Exception as e:
            logger.error(f"Error handling slowmode command: {e}")
            await message.channel.send("An error occurred while setting slowmode.")

    async def set_slowmode(self, channel: discord.TextChannel, duration: int):
        """
        Sets the slowmode duration for the given channel.
        """
        try:
            await channel.edit(slowmode_delay=duration)
            logger.info(f"Set slowmode for {channel.name} to {duration} seconds.")
        except Exception as e:
            logger.error(f"Error setting slowmode: {e}")

    def is_admin(self, user: discord.Member) -> bool:
        """
        Checks if the user has an admin role.
        """
        return any(role.id in self.admin_roles for role in user.roles)

    @staticmethod
    def convert_to_seconds(value: int, unit: str) -> int:
        """
        Converts a time value and unit to seconds.
        """
        if unit == "h":
            return value * 3600
        elif unit == "m":
            return value * 60
        elif unit == "s":
            return value
        else:
            return None
