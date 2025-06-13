import discord
from discord import app_commands

from ..service import Service
from ..utils.logger import get_logger

# Initialize logger
logger = get_logger("user_management_self")


def __service__():
    return UserManagementSelfService()


class UserManagementSelfService(Service):
    def __register_commands__(self):
        """
        Register all user-level slash commands.
        """

        # --- Text Manipulation Commands ---
        @self.commands.command(name="reverse", description="Reverse text.")
        @app_commands.describe(text="The text to reverse.")
        async def reverse(interaction: discord.Interaction, text: str):
            reversed_text = text[::-1]
            await interaction.response.send_message(f"Reversed text: `{reversed_text}`")
            logger.info(f"Reversed text for {interaction.user}: {text} -> {reversed_text}")

        @self.commands.command(name="bold", description="Make text bold.")
        @app_commands.describe(text="The text to bold.")
        async def bold(interaction: discord.Interaction, text: str):
            bolded_text = f"**{text}**"
            await interaction.response.send_message(bolded_text)
            logger.info(f"Bolded text for {interaction.user}: {text}")

        @self.commands.command(name="italicize", description="Italicize text.")
        @app_commands.describe(text="The text to italicize.")
        async def italicize(interaction: discord.Interaction, text: str):
            italicized_text = f"*{text}*"
            await interaction.response.send_message(italicized_text)
            logger.info(f"Italicized text for {interaction.user}: {text}")

        @self.commands.command(name="censor", description="Censor text.")
        @app_commands.describe(text="The text to censor.")
        async def censor(interaction: discord.Interaction, text: str):
            censored_text = "".join(["*" if c.isalnum() else c for c in text])
            await interaction.response.send_message(f"Censored text: `{censored_text}`")
            logger.info(f"Censored text for {interaction.user}: {text} -> {censored_text}")

        @self.commands.command(name="strike", description="Strike through text.")
        @app_commands.describe(text="The text to strike through.")
        async def strike(interaction: discord.Interaction, text: str):
            striked_text = f"~~{text}~~"
            await interaction.response.send_message(striked_text)
            logger.info(f"Striked text for {interaction.user}: {text}")

        @self.commands.command(name="underline", description="Underline text.")
        @app_commands.describe(text="The text to underline.")
        async def underline(interaction: discord.Interaction, text: str):
            underlined_text = f"__{text}__"
            await interaction.response.send_message(underlined_text)
            logger.info(f"Underlined text for {interaction.user}: {text}")

        # --- Fun Commands ---
        @self.commands.command(name="kiss", description="Kiss a user.")
        @app_commands.describe(user="The user to kiss.")
        async def kiss(interaction: discord.Interaction, user: discord.Member):
            await interaction.response.send_message(f"{interaction.user.mention} kissed {user.mention}! 💋")
            logger.info(f"{interaction.user} kissed {user}.")

        @self.commands.command(name="hug", description="Hug a user.")
        @app_commands.describe(user="The user to hug.")
        async def hug(interaction: discord.Interaction, user: discord.Member):
            await interaction.response.send_message(f"{interaction.user.mention} gave {user.mention} a big hug! 🤗")
            logger.info(f"{interaction.user} hugged {user}.")

        @self.commands.command(name="slap", description="Slap a user.")
        @app_commands.describe(user="The user to slap.")
        async def slap(interaction: discord.Interaction, user: discord.Member):
            await interaction.response.send_message(f"{interaction.user.mention} slapped {user.mention}! 👋")
            logger.info(f"{interaction.user} slapped {user}.")

        @self.commands.command(name="wave", description="Wave at a user.")
        @app_commands.describe(user="The user to wave at.")
        async def wave(interaction: discord.Interaction, user: discord.Member):
            await interaction.response.send_message(f"{interaction.user.mention} waved at {user.mention}! 👋")
            logger.info(f"{interaction.user} waved at {user}.")

        @self.commands.command(name="smile", description="Smile.")
        async def smile(interaction: discord.Interaction):
            await interaction.response.send_message(f"{interaction.user.mention} is smiling. 😊")
            logger.info(f"{interaction.user} smiled.")

        @self.commands.command(name="cry", description="Cry.")
        async def cry(interaction: discord.Interaction):
            await interaction.response.send_message(f"{interaction.user.mention} is crying. 😢")
            logger.info(f"{interaction.user} cried.")

        @self.commands.command(name="laugh", description="Laugh at a user.")
        @app_commands.describe(user="The user to laugh at.")
        async def laugh(interaction: discord.Interaction, user: discord.Member):
            await interaction.response.send_message(f"{interaction.user.mention} laughed at {user.mention}! 😂")
            logger.info(f"{interaction.user} laughed at {user}.")

    async def on_ready(self):
        logger.info("UserManagementSelfService is ready!")
