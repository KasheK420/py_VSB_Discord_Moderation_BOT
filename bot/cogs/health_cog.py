# bot/cogs/health_cog.py
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from ..services.health_service import HealthMonitorService
from ..services.logging_service import LogLevel

logger = logging.getLogger(__name__)

class HealthCog(commands.Cog):
    """Slash commands + startup for Health Monitor."""

    def __init__(self, bot: commands.Bot, config):
        self.bot = bot
        self.config = config
        self.health: Optional[HealthMonitorService] = None

    async def cog_load(self):
        # Start the monitor as the cog loads
        self.health = HealthMonitorService(self.bot, self.config)
        await self.health.start()
        logger.info("[Health] monitor started")

        # Optional: register your core services into registry so they show up
        # Example:
        # self.health.register_service("Moderation", ok=True, details="loaded")

    async def cog_unload(self):
        if self.health:
            await self.health.stop()
            logger.info("[Health] monitor stopped")

    @app_commands.command(name="health", description="Zobrazí/aktualizuje health embed.")
    @app_commands.describe(action="refresh/post")
    @app_commands.choices(action=[
        app_commands.Choice(name="refresh", value="refresh"),
        app_commands.Choice(name="post", value="post"),
    ])
    async def health_cmd(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        # Recommend limiting to admins/mods; simple check:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("⛔ Jen pro moderátory.", ephemeral=True)
            return

        if not self.health:
            await interaction.response.send_message("Health service není inicializován.", ephemeral=True)
            return

        if action.value == "refresh":
            await self.health.force_refresh_now()
            await interaction.response.send_message("✅ Health embed aktualizován.", ephemeral=True)
        elif action.value == "post":
            # Force re-post by clearing stored message id
            self.health._store_message_id(0)  # crude reset
            self.health._message = None
            await self.health.force_refresh_now()
            await interaction.response.send_message("✅ Health embed znovu publikován.", ephemeral=True)
        else:
            await interaction.response.send_message("Neznámá akce.", ephemeral=True)


async def setup(bot: commands.Bot):
    # Import your existing Config loader if needed; assume bot keeps `bot.config`
    config = getattr(bot, "config", None)
    await bot.add_cog(HealthCog(bot, config))
