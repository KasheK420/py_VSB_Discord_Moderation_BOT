# bot/cogs/hall_of_shame_cog.py
from __future__ import annotations
import logging
import discord
from discord.ext import commands
from discord import app_commands, Interaction
from bot.database.database_service import database_service
from bot.database.queries.shame_queries import ShameQueries
from bot.services.logging_service import LogLevel

logger = logging.getLogger(__name__)

class HallOfShameCog(commands.Cog):
    """Tracks moderation events and shows leaderboards."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.embed_logger = getattr(bot, "embed_logger", None)
        self.shame_channel_id = getattr(bot.config, "hall_of_shame_channel_id", 0)

    async def cog_load(self):
        await ShameQueries.ensure_schema(database_service.pool)
        try:
            guild_obj = discord.Object(id=self.bot.config.guild_id)
            self.bot.tree.add_command(self.group, guild=guild_obj)
            await self.bot.tree.sync(guild=guild_obj)
        except Exception as e:
            logger.warning(f"Shame group sync: {e}")

    # Helper for moderation services to call:
    async def record_warning(self, user_id:int, moderator_id:int|None, reason:str|None):
        await ShameQueries.add_event(database_service.pool, user_id=user_id, kind="warn", reason=reason, moderator_id=moderator_id)

    # --- Event hooks we can infer without changing your mod service much ---

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        await ShameQueries.add_event(database_service.pool, user_id=user.id, kind="ban", reason=None, moderator_id=None)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # timeout detection (discord timed out)
        if before.timed_out_until != after.timed_out_until and after.timed_out_until is not None:
            await ShameQueries.add_event(database_service.pool, user_id=after.id, kind="timeout", reason="Timed out", moderator_id=None)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # try detect kick via audit log
        try:
            entry = await member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick).flatten()
            if entry and entry[0].target.id == member.id:
                await ShameQueries.add_event(database_service.pool, user_id=member.id, kind="kick", reason=entry[0].reason, moderator_id=entry[0].user.id if entry[0].user else None)
        except Exception:
            pass

    # --- Slash commands ---

    group = app_commands.Group(name="shame", description="Hall of Shame")

    @group.command(name="top", description="Zobrazí žebříček přestupků")
    @app_commands.describe(metric="warnings|kicks|bans|timeouts", limit="počet výsledků (max 20)")
    async def shame_top(self, itx: Interaction, metric: str = "warnings", limit: int = 10):
        await itx.response.defer(ephemeral=True)
        limit = max(1, min(limit, 20))
        rows = await ShameQueries.leaderboard(database_service.pool, by=metric, limit=limit)
        if not rows:
            return await itx.followup.send("Žádná data zatím nejsou.", ephemeral=True)
        lines = []
        for i, r in enumerate(rows, 1):
            uid = r["user_id"]
            lines.append(f"**{i}.** <@{uid}> — W:{r['warnings']} K:{r['kicks']} B:{r['bans']} T:{r['timeouts']}")
        await itx.followup.send("\n".join(lines), ephemeral=True)

    @group.command(name="user", description="Statistiky přestupků uživatele")
    async def shame_user(self, itx: Interaction, user: discord.User):
        await itx.response.defer(ephemeral=True)
        st = await ShameQueries.stats(database_service.pool, user.id)
        if not st:
            return await itx.followup.send("Uživatel nemá zaznamenané přestupky.", ephemeral=True)
        msg = (f"**{user}**\n"
               f"Varování: **{st['warnings']}**\n"
               f"Kicky: **{st['kicks']}**\n"
               f"Ban(y): **{st['bans']}**\n"
               f"Timeouty: **{st['timeouts']}**\n")
        await itx.followup.send(msg, ephemeral=True)
