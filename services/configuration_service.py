import json

import discord
from discord import app_commands
from discord.app_commands.checks import has_permissions

from configuration import Configuration
from service import Service


def __service__():
    return ConfigurationService()


class ConfigurationService(Service):
    def __register_commands__(self):
        @self.commands.command(
            name="conf_get",
            description="Get a configuration value"
        )
        @app_commands.describe(
            path="Configuration path"
        )
        @has_permissions(administrator=True)
        async def conf_get(interaction: discord.Interaction, path: str):
            value = Configuration.get(path)
            await interaction.response.send_message(content=f"`{path}` = `{value}`", ephemeral=True)

        @self.commands.command(
            name="conf_all",
            description="Get all a configuration values"
        )
        @has_permissions(administrator=True)
        async def conf_all(interaction: discord.Interaction):
            values: dict = Configuration._singleton.conf
            await interaction.response.send_message(content=f"```{json.dumps(values, indent=2)}```", ephemeral=True)
