# bot/cogs/admin.py
import json
import logging

import discord
from discord import Interaction, app_commands
from discord.ext import commands
from discord.ui import View, button

from bot.services.service_loader import get_moderation

from ..services.logging_service import LogLevel

logger = logging.getLogger(__name__)


class AdminCog(commands.Cog):
    """Admin / moderation utilities (slash-only)"""

    def __init__(self, bot):
        self.bot = bot

    @property
    def embed_logger(self):
        """Get embed logger from bot"""
        return getattr(self.bot, "embed_logger", None)

    mod = app_commands.Group(name="mod", description="Moderation controls (admin only)")

    @mod.command(name="reload", description="Reload moderation configuration")
    @app_commands.checks.has_permissions(administrator=True)
    async def mod_reload(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        mod = get_moderation()
        if not mod:
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Admin Commands",
                    error=Exception("Moderation service unavailable"),
                    context=f"mod reload command by {interaction.user.id}",
                )
            return await interaction.followup.send(
                "❌ Moderation service unavailable.", ephemeral=True
            )

        try:
            await mod.reload_configuration()
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Admin Commands",
                    title="Moderation Config Reloaded",
                    description=f"<@{interaction.user.id}> reloaded moderation configuration",
                    level=LogLevel.SUCCESS,
                    fields={
                        "Command": "/mod reload",
                        "Executed By": f"<@{interaction.user.id}>",
                        "Status": "✅ Success",
                    },
                )
            await interaction.followup.send("✅ Moderation configuration reloaded", ephemeral=True)
        except Exception as e:
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Admin Commands",
                    error=e,
                    context=f"mod reload command failed - executed by {interaction.user.id}",
                )
            await interaction.followup.send(f"❌ Reload failed: {e}", ephemeral=True)

    @mod.command(name="stats", description="Show moderation statistics")
    @app_commands.checks.has_permissions(administrator=True)
    async def mod_stats(self, interaction: Interaction):
        mod = get_moderation()
        stats = mod.get_moderation_stats() if mod else {}

        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Admin Commands",
                title="Moderation Stats Requested",
                description=f"<@{interaction.user.id}> requested moderation statistics",
                level=LogLevel.INFO,
                fields={
                    "Command": "/mod stats",
                    "Executed By": f"<@{interaction.user.id}>",
                    "Stats Retrieved": str(len(stats)) + " items" if stats else "unavailable",
                },
            )

        text = (
            "\n".join(f"**{k.replace('_',' ').title()}**: {v}" for k, v in stats.items())
            or "No stats available."
        )
        await interaction.response.send_message(text, ephemeral=True)

    @mod.command(name="reset_daily", description="Reset daily AI limits")
    @app_commands.checks.has_permissions(administrator=True)
    async def mod_reset_daily(self, interaction: Interaction):
        mod = get_moderation()
        if not mod:
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Admin Commands",
                    error=Exception("Moderation service unavailable"),
                    context=f"mod reset_daily command by {interaction.user.id}",
                )
            return await interaction.response.send_message(
                "❌ Moderation service unavailable.", ephemeral=True
            )

        old_count = mod.ai_calls_today if hasattr(mod, "ai_calls_today") else 0
        mod.reset_daily_limits()

        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Admin Commands",
                title="Daily AI Limits Reset",
                description=f"<@{interaction.user.id}> reset daily AI usage limits",
                level=LogLevel.SUCCESS,
                fields={
                    "Command": "/mod reset_daily",
                    "Executed By": f"<@{interaction.user.id}>",
                    "Previous Count": str(old_count),
                    "New Count": "0",
                    "Status": "✅ Reset",
                },
            )

        await interaction.response.send_message("✅ Daily AI limits reset", ephemeral=True)

    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="mod_check", description="Run moderation analyzer on sample text")
    async def mod_check(self, interaction: Interaction, text: str):
        await interaction.response.defer(ephemeral=True)
        mod = get_moderation()
        if not mod:
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Admin Commands",
                    error=Exception("Moderation service unavailable"),
                    context=f"mod_check command by {interaction.user.id}",
                )
            return await interaction.followup.send(
                "❌ Moderation service unavailable.", ephemeral=True
            )
        try:
            score, violations = mod.analyze_text(text)

            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Admin Commands",
                    title="Moderation Test Executed",
                    description=f"<@{interaction.user.id}> tested moderation analyzer",
                    level=LogLevel.INFO,
                    fields={
                        "Command": "/mod_check",
                        "Executed By": f"<@{interaction.user.id}>",
                        "Test Text Length": f"{len(text)} chars",
                        "Suspicion Score": str(score),
                        "Violations Found": str(len(violations)),
                        "Violations": ", ".join(violations) if violations else "none",
                    },
                )

            out = (
                f"**Input:** `{text}`\n"
                f"**Score:** {score}\n"
                f"**Violations:** {', '.join(violations) if violations else 'none'}"
            )
            await interaction.followup.send(out, ephemeral=True)
        except Exception as e:
            logger.exception("mod_check failed")
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Admin Commands",
                    error=e,
                    context=f"mod_check command failed - executed by {interaction.user.id}, text: {text[:50]}...",
                )
            await interaction.followup.send(f"❌ Command failed: {e}", ephemeral=True)

    @commands.Cog.listener()
    async def on_app_command_error(
        self, interaction: Interaction, error: app_commands.AppCommandError
    ):
        from discord.app_commands import errors

        if self.embed_logger:
            await self.embed_logger.log_error(
                service="Admin Commands",
                error=error,
                context=f"Slash command error - User: {interaction.user.id}, Command: {getattr(interaction.command, 'name', 'unknown')}",
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
            logger.exception("Slash command error")
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

    @app_commands.command(
        name="sync_commands", description="Force re-sync of all slash/context commands"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_commands(self, interaction: Interaction, scope: str = "guild"):
        """
        scope: 'guild' (fast sync in this server) or 'global' (takes up to 1h)
        """
        await interaction.response.defer(ephemeral=True)
        try:
            if scope.lower() == "guild":
                guild = discord.Object(id=self.bot.config.guild_id)
                synced = await self.bot.tree.sync(guild=guild)

                if self.embed_logger:
                    await self.embed_logger.log_custom(
                        service="Admin Commands",
                        title="Guild Commands Synced",
                        description=f"<@{interaction.user.id}> synced guild slash commands",
                        level=LogLevel.SUCCESS,
                        fields={
                            "Command": "/sync_commands",
                            "Executed By": f"<@{interaction.user.id}>",
                            "Scope": "Guild",
                            "Guild ID": str(self.bot.config.guild_id),
                            "Commands Synced": str(len(synced)),
                            "Status": "✅ Success",
                        },
                    )

                await interaction.followup.send(
                    f"✅ Synced {len(synced)} commands to this guild", ephemeral=True
                )
            else:
                synced = await self.bot.tree.sync()

                if self.embed_logger:
                    await self.embed_logger.log_custom(
                        service="Admin Commands",
                        title="Global Commands Synced",
                        description=f"<@{interaction.user.id}> synced global slash commands",
                        level=LogLevel.SUCCESS,
                        fields={
                            "Command": "/sync_commands",
                            "Executed By": f"<@{interaction.user.id}>",
                            "Scope": "Global",
                            "Commands Synced": str(len(synced)),
                            "Propagation Time": "~1 hour",
                            "Status": "✅ Success",
                        },
                    )

                await interaction.followup.send(
                    f"✅ Synced {len(synced)} global commands (propagation can take ~1h)",
                    ephemeral=True,
                )
        except Exception as e:
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Admin Commands",
                    error=e,
                    context=f"sync_commands failed - executed by {interaction.user.id}, scope: {scope}",
                )
            await interaction.followup.send(f"❌ Sync failed: {e}", ephemeral=True)

    @app_commands.command(
        name="mod_config", description="Show the current moderation.json (paginated)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def mod_config(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        mod = get_moderation()
        if not mod or not getattr(mod, "config", None):
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Admin Commands",
                    error=Exception("Moderation service not ready or config missing"),
                    context=f"mod_config command by {interaction.user.id}",
                )
            return await interaction.followup.send(
                "❌ Moderation service not ready or config missing.", ephemeral=True
            )

        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Admin Commands",
                title="Moderation Config Viewed",
                description=f"<@{interaction.user.id}> viewed moderation configuration",
                level=LogLevel.INFO,
                fields={
                    "Command": "/mod_config",
                    "Executed By": f"<@{interaction.user.id}>",
                    "Config Version": str(mod.config.get("version", "unknown")),
                    "Config Status": "Enabled" if mod.config.get("enabled") else "Disabled",
                },
            )

        cfg = mod.config  # this should be a dict
        pages: list[discord.Embed] = []

        # Helper to make a page
        def page(title: str, data: str) -> discord.Embed:
            e = discord.Embed(title=title, color=discord.Color.blurple())
            # Keep fields short to avoid 6000-char embed limit; chunk if needed
            chunk_size = 1000
            if len(data) <= chunk_size:
                e.description = f"```json\n{data}\n```"
            else:
                # Split into multiple fields if very long
                for i in range(0, len(data), chunk_size):
                    e.add_field(
                        name=f"Part {i//chunk_size + 1}",
                        value=f"```json\n{data[i:i+chunk_size]}\n```",
                        inline=False,
                    )
            return e

        # Break config into logical sections
        sections = [
            (
                "Overview",
                {
                    "version": cfg.get("version"),
                    "enabled": cfg.get("enabled"),
                    "server_type": cfg.get("server_type"),
                    "timezone": cfg.get("timezone"),
                    "warning_threshold": cfg.get("warning_threshold"),
                },
            ),
            ("Limits", cfg.get("limits")),
            ("Link Policy", cfg.get("link_policy")),
            ("Attachment Policy", cfg.get("attachment_policy")),
            ("Format Detectors", cfg.get("format_detectors")),
            ("Trusted User Criteria", cfg.get("trusted_user_criteria")),
            ("Anti-raid", cfg.get("anti_raid")),
            ("Weights", cfg.get("suspicion_weights")),
            ("Severity Mapping", cfg.get("severity_mapping")),
            ("Escalation Rules", cfg.get("escalation_rules")),
            ("Actions", cfg.get("actions")),
            ("Review Queues", cfg.get("review_queues")),
            ("Responses", cfg.get("responses")),
        ]

        # Create pages for sections
        for title, data in sections:
            if data is None:
                continue
            try:
                js = json.dumps(data, indent=2, ensure_ascii=False)
            except Exception:
                js = str(data)
            pages.append(page(f"Moderation • {title}", js))

        # Bad-word categories can be huge; show counts + samples per page
        bad = cfg.get("bad_words", {})
        if isinstance(bad, dict) and bad:
            counts = {
                k: (len(v) if isinstance(v, list) else (len(v) if v else 0)) for k, v in bad.items()
            }
            summary = "\n".join(f"- **{k}**: {counts[k]} patterns" for k in sorted(counts))
            pages.append(
                discord.Embed(
                    title="Moderation • Bad Words (summary)",
                    description=summary,
                    color=discord.Color.blurple(),
                )
            )

            # Add one page per category (first N samples)
            for k, v in bad.items():
                if not isinstance(v, list):
                    continue
                sample = v[:20]  # don't blow embed size
                js = json.dumps(sample, indent=2, ensure_ascii=False)
                pages.append(page(f"Bad Words • {k}", js))

        # Safety if no pages
        if not pages:
            pages = [
                discord.Embed(
                    title="Moderation Config", description="(empty)", color=discord.Color.blurple()
                )
            ]

        view = PagedEmbedView(pages, author_id=interaction.user.id, timeout=120)
        await interaction.followup.send(embed=pages[0], view=view, ephemeral=True)

    @app_commands.command(name="log_test", description="Post a test embed to the admin log channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def log_test(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        logger = getattr(self.bot, "embed_logger", None)
        if not logger:
            return await interaction.followup.send("No embed logger is attached.", ephemeral=True)
        try:
            await logger.log_custom(
                service="Admin",
                title="Log Test",
                description="If you see this, logging is working.",
                level=LogLevel.SUCCESS,
                fields={"Invoker": f"<@{interaction.user.id}>"},
            )
            await interaction.followup.send(
                "Sent a test embed to the admin log channel.", ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"Failed to send embed: {e}", ephemeral=True)


class PagedEmbedView(View):
    def __init__(self, pages: list[discord.Embed], author_id: int, timeout: int = 60):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.index = 0
        self.author_id = author_id
        # Initialize button states
        self._update_buttons()

    def _update_buttons(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "prev":
                    child.disabled = self.index <= 0
                if child.custom_id == "next":
                    child.disabled = self.index >= len(self.pages) - 1

    async def _edit(self, interaction: discord.Interaction):
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @button(label="◀ Prev", style=discord.ButtonStyle.secondary, custom_id="prev")
    async def prev(self, interaction: discord.Interaction, _):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message(
                "❌ Only the requester can control pagination.", ephemeral=True
            )
        if self.index > 0:
            self.index -= 1
        await self._edit(interaction)

    @button(label="Next ▶", style=discord.ButtonStyle.secondary, custom_id="next")
    async def next(self, interaction: discord.Interaction, _):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message(
                "❌ Only the requester can control pagination.", ephemeral=True
            )
        if self.index < len(self.pages) - 1:
            self.index += 1
        await self._edit(interaction)

    @button(label="Close", style=discord.ButtonStyle.danger, custom_id="close")
    async def close(self, interaction: discord.Interaction, _):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message(
                "❌ Only the requester can close this.", ephemeral=True
            )
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
