import discord

from discord import app_commands
from discord.app_commands.checks import has_permissions

from ..service import Service
from ..utils.logger import get_logger



# Initialize logger
logger = get_logger("text_formatter_service")


def __service__():
    return TextFormatterService()


class TextFormatterService(Service):
    def __register_commands__(self):
        """
        Register all slash commands for the Text Formatter Service.
        """

        # Admin command to create an embedded message with optional graphic
        @self.commands.command(name="create_embed", description="Create a custom embedded message (Admin only).")
        @app_commands.describe(
            title="The title of the embed.",
            description="The description of the embed.",
            image_url="Optional: URL of the image or graphic to include."
        )
        @has_permissions(administrator=True)
        async def create_embed(interaction: discord.Interaction, title: str, description: str, image_url: str = None):
            """
            Creates a rich embedded message with an optional image or graphic.
            Admin-only command.
            """
            try:
                embed = discord.Embed(title=title, description=description, color=discord.Color.blue())
                if image_url:
                    embed.set_image(url=image_url)
                embed.set_footer(text=f"Created by {interaction.user.display_name}")
                await interaction.channel.send(embed=embed)
                await interaction.response.send_message("Embedded message created successfully.", ephemeral=True)
                logger.info(f"Admin {interaction.user} created an embedded message.")
            except Exception as e:
                logger.error(f"Failed to create embed: {e}")
                await interaction.response.send_message("Failed to create the embed. Check the details and try again.",
                                                        ephemeral=True)

        # User command to create a code snippet embed
        @self.commands.command(name="code_snippet", description="Create a nicely formatted code snippet.")
        @app_commands.describe(
            language="The programming language for syntax highlighting.",
            code="The code snippet to include in the embed."
        )
        async def code_snippet(interaction: discord.Interaction, language: str, code: str):
            """
            Creates a formatted code snippet embed.
            Available for all users.
            """
            supported_languages = [
                "python", "javascript", "java", "c++", "c#", "ruby", "go", "typescript", "swift", "php"
            ]

            # Normalize the language input
            language = language.lower()

            if language not in supported_languages:
                await interaction.response.send_message(
                    f"Unsupported language. Supported languages are: {', '.join(supported_languages)}", ephemeral=True
                )
                return

            try:
                # Ensure the code is properly formatted with preserved whitespace
                formatted_code = code.strip()  # Remove leading/trailing whitespace
                formatted_code = formatted_code.replace('\t', '    ')  # Replace tabs with 4 spaces (optional)

                # Create the embed with the formatted code
                embed = discord.Embed(
                    title=f"Code Snippet ({language.capitalize()})",
                    description=f"```{language}\n{formatted_code}\n```",
                    color=discord.Color.green()
                )
                embed.set_footer(text=f"Snippet provided by {interaction.user.display_name}")

                # Send the embed to the channel
                await interaction.channel.send(embed=embed)
                await interaction.response.send_message("Code snippet created successfully.", ephemeral=True)
                logger.info(f"{interaction.user} created a code snippet in {language}.")
            except Exception as e:
                logger.error(f"Failed to create code snippet embed: {e}")
                await interaction.response.send_message("Failed to create the code snippet. Try again later.",
                                                        ephemeral=True)

    async def on_ready(self):
        logger.info("TextFormatterService is ready!")
