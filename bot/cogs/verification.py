# bot/cogs/verification.py
from discord import Interaction, app_commands
from discord.ext import commands

from bot.services.onboarding_service import OnboardingService

from ..services.logging_service import LogLevel


class VerificationCog(commands.Cog):
    """Verification and onboarding commands (slash-only)"""

    def __init__(self, bot, onboarding: OnboardingService | None):
        self.bot = bot
        self.onboarding = onboarding

    @property
    def embed_logger(self):
        """Get embed logger from bot"""
        return getattr(self.bot, "embed_logger", None)

    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(
        name="setup_verification",
        description="Post the verification message with VSB SSO button in the configured welcome channel",
    )
    async def setup_verification(self, interaction: Interaction):
        if not self.onboarding:
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Verification Commands",
                    error=Exception("Onboarding service not available"),
                    context=f"setup_verification command by {interaction.user.id}",
                )
            return await interaction.response.send_message(
                "❌ Onboarding service not available.", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        try:
            await self.onboarding.ensure_verification_message(self.bot)

            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Verification Commands",
                    title="Verification Message Posted",
                    description=f"<@{interaction.user.id}> posted verification message in welcome channel",
                    level=LogLevel.SUCCESS,
                    fields={
                        "Command": "/setup_verification",
                        "Executed By": f"<@{interaction.user.id}>",
                        "Channel": f"<#{self.bot.config.verification_channel_id}>",
                        "Status": "✅ Posted successfully",
                    },
                )

            await interaction.followup.send("✅ Verification message posted", ephemeral=True)

        except Exception as e:
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Verification Commands",
                    error=e,
                    context=f"setup_verification command failed - executed by {interaction.user.id}",
                )
            await interaction.followup.send(
                f"❌ Failed to post verification message: {e}", ephemeral=True
            )

    @commands.Cog.listener()
    async def on_app_command_error(
        self, interaction: Interaction, error: app_commands.AppCommandError
    ):
        from discord.app_commands import errors

        if self.embed_logger:
            await self.embed_logger.log_error(
                service="Verification Commands",
                error=error,
                context=f"Verification command error - User: {interaction.user.id}, Command: {getattr(interaction.command, 'name', 'unknown')}",
            )

        if isinstance(error, errors.MissingPermissions):
            try:
                await interaction.response.send_message(
                    "❌ You don't have permission to use this command.", ephemeral=True
                )
            except Exception:
                try:
                    await interaction.followup.send(
                        "❌ You don't have permission to use this command.", ephemeral=True
                    )
                except Exception:
                    pass
        else:
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        "❌ Command failed unexpectedly.", ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        "❌ Command failed unexpectedly.", ephemeral=True
                    )
            except Exception:
                pass
