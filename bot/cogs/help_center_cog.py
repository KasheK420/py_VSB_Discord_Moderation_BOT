# bot/cogs/help_center_cog.py
import asyncio
import logging

import discord
from discord import Interaction, app_commands
from discord.ext import commands

from bot.database.database_service import get_database_service  # adjust if your path differs
from bot.services.kb_service import KBService
from bot.services.logging_service import LogLevel
from bot.utils.ai_helper import get_ai_service

logger = logging.getLogger(__name__)


def _ellipsis(s: str, n: int = 350) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


class HelpCenterCog(commands.Cog):
    """
    Auto-answers in a forum channel (help-center) by searching a local KB and asking AI to compose a reply.
    Admins can add/search KB via slash commands.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.forum_channel_id: int | None = getattr(
            self.bot.config, "help_center_forum_channel_id", None
        )
        self.embed_logger = getattr(self.bot, "embed_logger", None)

        # Services (lazy)
        self.kb: KBService | None = None

    async def _ensure_services(self):
        if self.kb is None:
            db = get_database_service()
            self.kb = KBService(db.pool)

    # ----- utilities -----

    def _is_help_center_forum(self, channel: discord.abc.GuildChannel) -> bool:
        return (
            isinstance(channel, discord.ForumChannel)
            and self.forum_channel_id
            and int(channel.id) == int(self.forum_channel_id)
        )

    async def _post_ai_reply(self, thread: discord.Thread, opener_message: discord.Message):
        """Search KB + compose public counselor reply and post it to the thread."""
        await self._ensure_services()
        ai = get_ai_service()
        if not ai or not self.kb:
            return

        # optional: prevent double replies on restarts
        if await self.kb.was_replied(thread.id):
            return

        query_text = opener_message.content or ""
        if not query_text.strip():
            return

        # Search KB
        results = await self.kb.search(query_text, limit=3)
        if not results:
            # nothing relevant found → skip quietly
            return

        # Build facts bloc for model
        bullet_lines = []
        kb_ids: list[int] = []
        for r in results:
            kb_ids.append(r["id"])
            line = f"- {r['title']}"
            if r.get("url"):
                line += f" → {r['url']}"
            if r.get("snippet"):
                line += f"\n  {_ellipsis(r['snippet'], 220)}"
            bullet_lines.append(line)

        facts = "\n".join(bullet_lines)

        # Compose counselor-style answer
        system_prompt = (
            "You are a friendly university help-desk assistant for students (VSB-TUO). "
            "Use the provided knowledge base facts to answer concisely in 4–8 sentences. "
            "If there are links, include them as markdown. Keep tone supportive and practical. "
            "If the KB may not fully answer the question, suggest next steps or a contact. "
            "Never invent links. If unsure, say what is known and propose how to get the rest."
        )

        user_prompt = (
            f"User question:\n```{_ellipsis(query_text, 1200)}```\n\n"
            f"Relevant KB facts:\n{facts}\n\n"
            "Write the best helpful reply for the student. Start directly with the answer."
        )

        try:
            reply = await ai.generate_response(
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=system_prompt,
                max_tokens=400,
                temperature=0.4,
                model=None,  # use default chat model (your llama4-scout)
            )
            text = reply["content"]
        except Exception as e:
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="HelpCenter",
                    error=e,
                    context=f"AI compose failed for thread {thread.id}",
                )
            return

        # Post publicly to thread + mark replied + feedback buttons
        view = discord.ui.View(timeout=1800)

        class HelpfulBtn(discord.ui.Button):
            def __init__(self, parent: "HelpCenterCog", helpful: bool):
                super().__init__(
                    style=discord.ButtonStyle.success if helpful else discord.ButtonStyle.secondary,
                    label="Helpful ✅" if helpful else "Not Helpful ❌",
                    row=0,
                )
                self.parent = parent
                self.helpful = helpful

            async def callback(self, interaction: discord.Interaction):
                await self.parent._ensure_services()
                if self.parent.kb:
                    await self.parent.kb.record_feedback(
                        thread.id, self.helpful, interaction.user.id
                    )
                await interaction.response.send_message(
                    (
                        "Thanks for the feedback!"
                        if self.helpful
                        else "Thanks — we will improve this."
                    ),
                    ephemeral=True,
                )

        view.add_item(HelpfulBtn(self, True))
        view.add_item(HelpfulBtn(self, False))

        try:
            msg = await thread.send(text[:1900], view=view)
            await self.kb.mark_replied(thread.id, msg.id, kb_ids)

            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="HelpCenter",
                    title="Auto Answer Posted",
                    description=f"Posted AI answer in {thread.mention}",
                    level=LogLevel.SUCCESS,
                    fields={
                        "Thread": thread.name,
                        "KB Matches": "\n".join([f"- {r['title']}" for r in results]),
                        "Message ID": str(msg.id),
                    },
                )
        except discord.Forbidden as e:
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="HelpCenter",
                    error=e,
                    context=f"No permission to post in thread {thread.id}",
                )
        except Exception as e:
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="HelpCenter",
                    error=e,
                    context=f"Failed to post in thread {thread.id}",
                )

    # ----- events -----

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        """When a new forum thread is created in help-center, read the opener and auto-answer."""
        try:
            if not self._is_help_center_forum(thread.parent):
                return
            # Wait until the thread's starter message is available
            await asyncio.sleep(0.7)
            starter = await thread.fetch_message(thread.id)
            if starter and starter.type == discord.MessageType.thread_starter_message:
                # The actual user message is the first message after the starter; fetch history
                async for m in thread.history(limit=1, oldest_first=True):
                    if m.author.bot:
                        continue
                    await self._post_ai_reply(thread, m)
                    break
            else:
                # Fallback: try first human message
                async for m in thread.history(limit=3, oldest_first=True):
                    if m.author.bot:
                        continue
                    await self._post_ai_reply(thread, m)
                    break
        except Exception as e:
            logger.exception("on_thread_create error: %s", e)
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="HelpCenter",
                    error=e,
                    context="on_thread_create pipeline failed",
                )

    # ----- slash commands (admin) -----

    group = app_commands.Group(name="kb", description="Knowledge base management")

    @group.command(name="add", description="Add or update a KB article")
    @app_commands.describe(
        title="Title of the article",
        url="Optional source URL",
        category="Optional category",
        tags="Optional comma-separated tags",
        body="Article body (plain text)",
        article_id="If set, updates existing article",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def kb_add(
        self,
        interaction: Interaction,
        title: str,
        body: str,
        url: str | None = None,
        category: str | None = None,
        tags: str | None = None,
        article_id: int | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        await self._ensure_services()
        tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
        art_id = await self.kb.upsert_article(
            title=title, body=body, url=url, category=category, tags=tag_list, article_id=article_id
        )
        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="HelpCenter",
                title="KB Article Upserted",
                description=f"By <@{interaction.user.id}>",
                level=LogLevel.SUCCESS,
                fields={
                    "ID": str(art_id),
                    "Title": title,
                    "Category": category or "n/a",
                    "Tags": ", ".join(tag_list) or "n/a",
                    "URL": url or "n/a",
                },
            )
        await interaction.followup.send(f"✅ KB saved (id `{art_id}`)", ephemeral=True)

    @group.command(name="search", description="Search KB manually (test what the bot would find)")
    @app_commands.describe(query="What to search for", limit="How many results")
    async def kb_search(self, interaction: Interaction, query: str, limit: int | None = 5):
        await interaction.response.defer(ephemeral=True)
        await self._ensure_services()
        hits = await self.kb.search(query, limit=limit or 5)
        if not hits:
            return await interaction.followup.send("No KB hits.", ephemeral=True)

        lines = []
        for h in hits:
            line = f"• **{h['title']}**"
            if h["url"]:
                line += f" → {h['url']}"
            line += f"\n  {_ellipsis(h['snippet'], 180)}"
            lines.append(line)
        await interaction.followup.send("\n".join(lines)[:1950], ephemeral=True)

    @group.command(name="status", description="Show Help Center config status")
    @app_commands.checks.has_permissions(administrator=True)
    async def kb_status(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        await self._ensure_services()
        ch = self.bot.get_channel(self.forum_channel_id) if self.forum_channel_id else None
        await interaction.followup.send(
            f"Forum: {ch.mention if ch else self.forum_channel_id}\n"
            f"KB ready: {'yes' if self.kb else 'no'}",
            ephemeral=True,
        )

    # ----- cog load -----

    async def cog_load(self):
        # Register slash group into your guild for instant availability (optional)
        try:
            guild_obj = discord.Object(id=self.bot.config.guild_id)
            self.bot.tree.add_command(self.group, guild=guild_obj)
            await self.bot.tree.sync(guild=guild_obj)
        except Exception as e:
            logger.warning(f"HelpCenterCog sync warning: {e}")
            try:
                self.bot.tree.add_command(self.group)
                await self.bot.tree.sync()
            except Exception as e2:
                logger.warning(f"HelpCenterCog global sync warning: {e2}")
