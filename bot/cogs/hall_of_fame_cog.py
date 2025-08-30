# bot/cogs/hall_of_fame_cog.py
from __future__ import annotations
import logging, os
import discord
from discord.ext import commands
from bot.services.logging_service import LogLevel
from bot.database.database_service import database_service
from bot.database.queries.hof_queries import HOFQueries
from bot.services.message_render_service import render_message_card
from bot.utils.ai_helper import get_ai_service

logger = logging.getLogger(__name__)

class HallOfFameCog(commands.Cog):
    """Posts messages that reach reaction threshold into Hall of Fame channel with an AI quip (CZ)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.embed_logger = getattr(bot, "embed_logger", None)
        self.hof_channel_id = getattr(bot.config, "hall_of_fame_channel_id", 0)
        self.threshold = getattr(bot.config, "fame_reaction_threshold", 5)

    async def cog_load(self):
        await HOFQueries.ensure_schema(database_service.pool)

    def _sum_reactions(self, message: discord.Message) -> int:
        return sum(r.count for r in message.reactions)

    async def _post_to_hof(self, message: discord.Message, total: int):
        if not self.hof_channel_id:
            return
        if await HOFQueries.was_posted(database_service.pool, message.id):
            return

        # Render
        image_bytes = await render_message_card(message)
        file = discord.File(fp=image_bytes, filename="fame.png")

        # AI quip (CZ)
        ai = get_ai_service()
        quip = ""
        try:
            if ai:
                system = "Jsi vtipný a milý moderátor českého Discordu VŠB. Odpovídej jednou větou, česky."
                user = (
                    f"Napiš krátkou vtipnou poznámku (max 1 věta) k příspěvku, který získal {total} reakcí. "
                    f"Autor: {message.author.display_name}. Buď přátelský a nezesměšňuj nikoho."
                )
                r = await ai.generate_response(
                    messages=[{"role":"user","content":user}],
                    system_prompt=system,
                    max_tokens=60,
                    temperature=0.7,
                    model=None,  # default chat model
                )
                quip = (r["content"] or "").strip()
        except Exception as e:
            if self.embed_logger:
                await self.embed_logger.log_error("HallOfFame", e, context="AI quip failed")
            quip = ""

        ch = message.guild.get_channel(self.hof_channel_id)
        if not isinstance(ch, discord.TextChannel):
            return

        emb = discord.Embed(
            title="🏆 Hall of Fame",
            description=quip or f"{message.author.display_name} nasbíral/a **{total}** reakcí!",
            color=discord.Color.gold()
        )
        emb.add_field(name="Odkaz", value=f"[Přejít na zprávu]({message.jump_url})", inline=False)
        emb.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)

        sent = await ch.send(embed=emb, file=file)
        await HOFQueries.record_post(
            database_service.pool,
            message_id=message.id,
            channel_id=message.channel.id,
            author_id=message.author.id,
            posted_in=ch.id,
            fame_message_id=sent.id,
            reaction_total=total,
        )
        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="HallOfFame",
                title="Posted to HOF",
                description=f"Message {message.id} → {sent.jump_url}",
                level=LogLevel.SUCCESS,
                fields={"Total reactions": str(total)}
            )

    async def _check_message(self, message: discord.Message):
        if not message or not message.guild or message.author.bot:
            return
        if message.channel.id == self.hof_channel_id:
            return
        total = self._sum_reactions(message)
        if total >= self.threshold:
            await self._post_to_hof(message, total)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        if reaction.message.guild is None:
            return
        await self._check_message(reaction.message)

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction: discord.Reaction, user: discord.User):
        if reaction.message.guild is None:
            return
        await self._check_message(reaction.message)
