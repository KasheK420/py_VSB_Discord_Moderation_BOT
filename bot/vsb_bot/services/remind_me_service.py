import asyncio
from datetime import datetime
from datetime import timedelta

from discord import Interaction
from discord import app_commands

from ..service import Service
from ..utils.logger import get_logger

# Initialize logger
logger = get_logger("remindme_service")


def __service__():
    return RemindMeService()


class RemindMeService(Service):
    def __init__(self):
        super().__init__()
        self.reminders = []  # List to store reminders in memory
        self.loop_task = None

    def __start__(self):
        """
        Start the reminder checking loop.
        """
        if self.loop_task is None:
            self.loop_task = asyncio.create_task(self._reminder_loop())
            logger.info("Reminder loop started.")

    async def _reminder_loop(self):
        """
        Background loop to check reminders.
        """
        while True:
            now = datetime.now()
            for reminder in self.reminders[:]:
                if reminder["time"] <= now:
                    await reminder["user"].send(f"⏰ Reminder: {reminder['text']}")
                    self.reminders.remove(reminder)
                    logger.info(f"Sent reminder to {reminder['user'].name}: {reminder['text']}")
            await asyncio.sleep(30)  # Check reminders every 30 seconds

    def __register_commands__(self):
        """
        Register the slash commands for reminders.
        """

        @self.commands.command(name="remindme", description="Set a reminder.")
        @app_commands.describe(
            text="What should I remind you about?",
            time="When should I remind you? (e.g., 'tomorrow')",
        )
        async def remindme(interaction: Interaction, text: str, time: str):
            """
            Set a reminder with a text and time.
            """
            try:
                reminder_time = self.parse_time(time)
                self.reminders.append({"user": interaction.user, "text": text, "time": reminder_time})
                await interaction.response.send_message(f"⏰ Reminder set for {reminder_time}.", ephemeral=True)
                logger.info(f"Reminder set by {interaction.user.name}: {text} at {reminder_time}")
            except ValueError as e:
                await interaction.response.send_message(f"Error: {e}", ephemeral=True)
                logger.error(f"Failed to set reminder for {interaction.user.name}: {e}")

    async def on_ready(self):
        logger.info("RemindMeService is ready!")

    @staticmethod
    def parse_time(time_str: str) -> datetime:
        """
        Parse human-readable time into a datetime object.
        Supports "tomorrow", "next week", "next month", etc.
        """
        now = datetime.now()
        time_str = time_str.lower()

        if "tomorrow" in time_str:
            return now + timedelta(days=1)
        elif "next week" in time_str:
            return now + timedelta(weeks=1)
        elif "next month" in time_str:
            return now + timedelta(days=30)  # Approximation
        elif "next year" in time_str:
            return now + timedelta(days=365)
        else:
            raise ValueError("Unsupported time format. Try 'tomorrow', 'next week', etc.")
