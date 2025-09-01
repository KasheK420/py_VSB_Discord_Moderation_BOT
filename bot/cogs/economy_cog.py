# bot/cogs/economy_cog.py
from __future__ import annotations
import logging
import time
import discord
from discord import Interaction, app_commands
from discord.ext import commands
from bot.database.database_service import database_service
from bot.database.queries.economy_queries import EconomyQueries

logger = logging.getLogger(__name__)


class EconomyCog(commands.Cog):
    """XP/points system with proper type handling."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.embed_logger = getattr(bot, "embed_logger", None)
        self.enabled = getattr(bot.config, "xp_enabled", True)
        self.cooldown = getattr(bot.config, "xp_message_cooldown_sec", 15)
        self.xp_msg = getattr(bot.config, "xp_per_message", 5)
        self.pt_msg = getattr(bot.config, "points_per_message", 1)
        self.xp_rx = getattr(bot.config, "xp_per_reaction_received", 2)
        self.pt_rx = getattr(bot.config, "points_per_reaction_received", 1)
        self.daily_cap = getattr(bot.config, "xp_daily_cap", 500)
        self._last_msg_ts: dict[int, float] = {}

    async def cog_load(self):
        """Initialize schema and sync commands."""
        await EconomyQueries.ensure_schema(database_service.pool)
        try:
            guild_obj = discord.Object(id=self.bot.config.guild_id)
            self.bot.tree.add_command(self.group, guild=guild_obj)
            await self.bot.tree.sync(guild=guild_obj)
        except Exception as e:
            logger.warning(f"Economy group sync: {e}")

    def _can_award_message(self, user_id: int) -> bool:
        """Check cooldown for message XP."""
        now = time.time()
        last = self._last_msg_ts.get(user_id, 0.0)
        if now - last >= self.cooldown:
            self._last_msg_ts[user_id] = now
            return True
        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Award XP for messages."""
        if not self.enabled or message.guild is None or message.author.bot:
            return
        if not self._can_award_message(message.author.id):
            return
            
        try:
            # Get stats with proper int user_id
            st = await EconomyQueries.get_stats(database_service.pool, message.author.id)
            todays = st.get("daily_xp", 0) if st else 0
            
            if todays >= self.daily_cap:
                return
                
            xp = min(self.xp_msg, self.daily_cap - todays)
            await EconomyQueries.add_message_xp(
                database_service.pool, message.author.id, xp, self.pt_msg
            )
        except Exception as e:
            logger.error(f"Error awarding message XP: {e}")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        """Award XP for reactions received."""
        if not self.enabled or reaction.message.guild is None:
            return
        author = reaction.message.author
        if author.bot or user.id == author.id:
            return
            
        try:
            st = await EconomyQueries.get_stats(database_service.pool, author.id)
            todays = st.get("daily_xp", 0) if st else 0
            
            if todays >= self.daily_cap:
                return
                
            xp = min(self.xp_rx, self.daily_cap - todays)
            meta = f"emoji={reaction.emoji}, by={user.id}"
            await EconomyQueries.add_reaction_received(
                database_service.pool, author.id, xp, self.pt_rx, meta
            )
        except Exception as e:
            logger.error(f"Error awarding reaction XP: {e}")

    # --- Slash Commands ---
    group = app_commands.Group(name="xp", description="XP / body")

    @group.command(name="me", description="Zobrazí tvé XP a body")
    async def xp_me(self, itx: Interaction):
        """Show user's XP stats."""
        await itx.response.defer(ephemeral=True)
        try:
            st = await EconomyQueries.get_stats(database_service.pool, itx.user.id)
            if not st:
                return await itx.followup.send("Zatím nemáš žádná data.", ephemeral=True)
                
            msg = (
                f"**{itx.user}**\n"
                f"XP: **{st['xp']}**, Body: **{st['points']}**\n"
                f"Úroveň: **{st['level']}**\n"
                f"Zprávy: **{st['messages']}**, Reakce získané: **{st['reactions_received']}**\n"
                f"Dnešní XP: **{st.get('daily_xp', 0)}** / {self.daily_cap}"
            )
            await itx.followup.send(msg, ephemeral=True)
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            await itx.followup.send("Chyba při načítání dat.", ephemeral=True)

    @group.command(name="top", description="Žebříček podle XP/bodů")
    @app_commands.describe(by="xp|points|messages|reactions_received", limit="počet (max 20)")
    async def xp_top(self, itx: Interaction, by: str = "xp", limit: int = 10):
        """Show leaderboard."""
        await itx.response.defer(ephemeral=True)
        limit = max(1, min(limit, 20))
        
        try:
            rows = await EconomyQueries.leaderboard(database_service.pool, by=by, limit=limit)
            if not rows:
                return await itx.followup.send("Žádná data zatím nejsou.", ephemeral=True)
                
            lines = []
            for i, r in enumerate(rows, 1):
                lines.append(
                    f"**{i}.** <@{r['user_id']}> — XP:{r['xp']} Body:{r['points']} "
                    f"Msg:{r['messages']} Rx:{r['reactions_received']}"
                )
            await itx.followup.send("\n".join(lines), ephemeral=True)
        except Exception as e:
            logger.error(f"Error getting leaderboard: {e}")
            await itx.followup.send("Chyba při načítání žebříčku.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))