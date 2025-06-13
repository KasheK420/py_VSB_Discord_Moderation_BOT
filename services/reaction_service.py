import discord
from discord import app_commands
from configuration import Configuration
from service import Service
from utils.logger import get_logger

# Initialize logger for this service
logger = get_logger("reaction_service")


def __service__():
    return ReactionService()


class ReactionService(Service):
    def __init__(self):
        super().__init__()
        self.text_responses = Configuration.get("services.reaction_service_text", {})
        self.gif_responses = Configuration.get("services.reaction_service_gif", {})
        self.tenor_api_key = Configuration.get("api_keys.tenor", None)

        if not self.tenor_api_key:
            logger.error("Tenor API key is missing in configuration.json")

    def __start__(self):
        logger.info("ReactionService is starting!")

    async def on_ready(self):
        logger.info("ReactionService is ready!")

    def __register_commands__(self):
        """
        Register slash commands for the ReactionService.
        """

        @self.commands.command(
            name="react_text",
            description="Get a text reaction for a specific word."
        )
        @app_commands.describe(
            word="The word to trigger a text response."
        )
        async def react_text(interaction: discord.Interaction, word: str):
            """
            Fetch a text response for the given word from the configured dictionary.
            """
            response = self.text_responses.get(word.lower())
            if response:
                await interaction.response.send_message(content=f"Response for '{word}': {response}")
                logger.info(f"Text reaction provided for '{word}': {response}")
            else:
                await interaction.response.send_message(content=f"No text response found for '{word}'.", ephemeral=True)
                logger.warning(f"No text response configured for '{word}'.")

        @self.commands.command(
            name="react_gif",
            description="Get a GIF reaction for a specific word."
        )
        @app_commands.describe(
            word="The word to trigger a GIF response."
        )
        async def react_gif(interaction: discord.Interaction, word: str):
            """
            Fetch a GIF response for the given word using the Tenor API.
            """
            from utils.tenor_api_gif import get_tenor_gif
            try:
                gif_url = get_tenor_gif(word, self.tenor_api_key)
                if gif_url:
                    await interaction.response.send_message(content=gif_url)
                    logger.info(f"GIF reaction provided for '{word}': {gif_url}")
                else:
                    await interaction.response.send_message(content=f"No GIF found for '{word}'.", ephemeral=True)
                    logger.warning(f"No GIF response found for '{word}'.")
            except Exception as e:
                logger.error(f"Error fetching GIF for '{word}': {e}")
                await interaction.response.send_message(content="An error occurred while fetching the GIF.", ephemeral=True)

    async def on_message(self, message: discord.Message):
        """
        Handle incoming messages and respond based on text or GIF triggers.
        """
        if message.author == self.client.user:
            return

        for word, response in self.text_responses.items():
            if word in message.content.lower():
                await self.respond_with_text(message, response)
                return

        for word in self.gif_responses.keys():
            if word in message.content.lower():
                await self.respond_with_gif(message, word)
                return

    async def respond_with_text(self, message: discord.Message, text_response: str):
        try:
            await message.channel.send(text_response)
            logger.info(f"Responded with text: {text_response}")
        except Exception as e:
            logger.error(f"Error responding with text: {e}")

    async def respond_with_gif(self, message: discord.Message, search_term: str):
        try:
            from utils.tenor_api_gif import get_tenor_gif
            gif_url = get_tenor_gif(search_term, self.tenor_api_key)
            if gif_url:
                await message.channel.send(gif_url)
                logger.info(f"Responded with GIF: {gif_url}")
            else:
                logger.error("Failed to fetch GIF from Tenor API")
        except Exception as e:
            logger.error(f"Error responding with GIF: {e}")
