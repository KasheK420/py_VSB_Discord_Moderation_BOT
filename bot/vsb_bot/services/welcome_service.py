import random
import discord

from ..configuration import Configuration
from ..service import Service
from ..utils.logger import get_logger

# Initialize logger for this service
logger = get_logger("welcome_service")


def __service__():
    return WelcomeService()


class WelcomeService(Service):
    def __init__(self):
        super().__init__()
        # Load configuration for the welcome service
        self.channel_id = Configuration.get("services.welcome_service.channel", None)
        self.text_templates = Configuration.get("services.welcome_service.text_templates", [])
        self.gif_keywords = Configuration.get("services.welcome_service.gif_keywords", [])
        self.tenor_api_key = Configuration.get("api_keys.tenor", None)

        if not self.tenor_api_key:
            logger.error("Tenor API key is missing in configuration.json")

    def __start__(self):
        # Log that the service is starting
        if not self.channel_id:
            logger.error("Welcome channel ID is not configured in configuration.json")
        logger.info("WelcomeService is starting!")

    async def on_ready(self):
        # Log that the service is ready
        logger.info("WelcomeService is ready!")

    async def on_member_join(self, member: discord.Member):
        """
        Handle a new member joining the server by sending a welcome message.
        """
        if not self.channel_id:
            logger.error("Welcome channel ID is not configured in configuration.json")
            return

        try:
            channel = self.server.get_channel(self.channel_id)
            if not channel:
                logger.error(f"Welcome channel with ID {self.channel_id} not found")
                return

            # Create a dynamic welcome message
            welcome_text = self.generate_welcome_text(member)
            gif_url = self.fetch_welcome_gif()

            # Send the welcome message as an embed
            embed = discord.Embed(
                title="Welcome to the Server! 🎉",
                description=welcome_text,
                color=discord.Color.blue()
            )
            if gif_url:
                embed.set_image(url=gif_url)

            await channel.send(embed=embed)
            logger.info(f"Sent welcome message for {member.display_name}")
        except Exception as e:
            logger.error(f"Error sending welcome message: {e}")

    def generate_welcome_text(self, member: discord.Member):
        """
        Generate a dynamic welcome message for the new member.
        """
        import random
        if not self.text_templates:
            return f"Welcome, {member.mention}!"
        return random.choice(self.text_templates).format(user=member.mention)

    def fetch_welcome_gif(self):
        """
        Fetch a random welcome GIF using the Tenor API.
        """
        try:
            # Import get_tenor_gif lazily to avoid circular imports
            from ..utils.tenor_api_gif import get_tenor_gif

            if not self.gif_keywords:
                return None

            keyword = random.choice(self.gif_keywords)
            return get_tenor_gif(keyword, self.tenor_api_key)
        except Exception as e:
            logger.error(f"Error fetching welcome GIF: {e}")
            return None
