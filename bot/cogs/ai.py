# bot/cogs/ai.py
import logging
import discord
from discord.ext import commands
from discord import app_commands, Interaction
from typing import Optional, List

from bot.utils.ai_helper import (
    ask_ai,
    translate_message,
    explain_concept,
    improve_text,
    smart_reply,
)
from bot.utils.ai_helper import get_ai_service, get_ai_config, set_ai_default_model, get_ai_model_registry
from ..services.logging_service import LogLevel

logger = logging.getLogger(__name__)

class AICog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # just define them here; don't add to tree yet
        self.ctx_reply = app_commands.ContextMenu(name="AI: Reply", callback=self._ctx_ai_reply)
        self.ctx_reply_post = app_commands.ContextMenu(name="AI: Reply (post)", callback=self._ctx_ai_reply_post)
        self.ctx_summarize = app_commands.ContextMenu(name="AI: Summarize", callback=self._ctx_ai_summarize)

    @property
    def embed_logger(self):
        """Get embed logger from bot"""
        return getattr(self.bot, 'embed_logger', None)

    async def cog_load(self):
        """Called by discord.py when the cog is fully loaded."""
        # Register to your guild for instant availability
        try:
            gobj = discord.Object(id=self.bot.config.guild_id)
            self.bot.tree.add_command(self.ctx_reply, guild=gobj)
            self.bot.tree.add_command(self.ctx_reply_post, guild=gobj)
            self.bot.tree.add_command(self.ctx_summarize, guild=gobj)
        except Exception:
            # If guild not ready, still add global
            self.bot.tree.add_command(self.ctx_reply)
            self.bot.tree.add_command(self.ctx_reply_post)
            self.bot.tree.add_command(self.ctx_summarize)

        # Try to sync the guild so context menus appear immediately
        try:
            await self.bot.tree.sync(guild=discord.Object(id=self.bot.config.guild_id))
        except Exception as e:
            # not fatal; they'll appear after the next global sync
            logging.getLogger(__name__).warning(f"AI Cog: guild sync failed: {e}")

    # Context menu command handlers
    async def _ctx_ai_reply_post(self, interaction: Interaction, message: discord.Message):
        """
        Generate a contextual AI reply and POST it publicly as a reply to the selected message.
        Requires 'Manage Messages' by default (see default_permissions above).
        """
        # Permission guard (extra safety in case default_permissions is bypassed)
        perms = interaction.user.guild_permissions if interaction.guild else None
        if not (perms and (perms.manage_messages or perms.administrator)):
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="AI Commands",
                    title="Unauthorized AI Reply Attempt",
                    description=f"<@{interaction.user.id}> tried to use AI reply post without permissions",
                    level=LogLevel.WARNING,
                    fields={
                        "Command": "AI: Reply (post)",
                        "User": f"<@{interaction.user.id}>",
                        "Target Message": f"{message.id}",
                        "Reason": "Missing Manage Messages permission"
                    }
                )
            return await interaction.response.send_message(
                "❌ You need **Manage Messages** to use this.", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)  # acknowledge quickly

        # --- USAGE LIMIT GUARD ---
        ai_service = get_ai_service()
        allowed, counters = ai_service.check_and_count_user(str(interaction.user.id))
        if not allowed:
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="AI Service",
                    title="User Limit Reached",
                    description=f"<@{interaction.user.id}> hit AI usage cap",
                    level=LogLevel.WARNING,
                    fields={
                        "Hour": f"{counters['hour']}/{ai_service.user_limits['per_hour']}",
                        "Day": f"{counters['day']}/{ai_service.user_limits['per_day']}",
                        "Week": f"{counters['week']}/{ai_service.user_limits['per_week']}",
                        "Command": "AI: Reply (post)"
                    }
                )
            return await interaction.followup.send(
                "⏳ You’ve reached your AI usage limit. Please try again later.",
                ephemeral=True
            )

        # Build minimal conversation context (last few human messages before the target)
        history: List[str] = []
        try:
            async for m in message.channel.history(limit=5, before=message, oldest_first=False):
                if m.author.bot:
                    continue
                history.append(f"{m.author.display_name}: {m.content}")
        except Exception:
            pass
        convo = list(reversed(history))

        # Generate the reply text
        try:
            reply_text = await smart_reply(
                user_message=message.content,
                conversation_context=convo,
                bot_personality="helpful moderator bot"
            )
            
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="AI Commands",
                    title="AI Public Reply Generated",
                    description=f"<@{interaction.user.id}> generated public AI reply",
                    level=LogLevel.SUCCESS,
                    fields={
                        "Command": "AI: Reply (post)",
                        "Executed By": f"<@{interaction.user.id}>",
                        "Target Message": f"By {message.author.mention} in {message.channel.mention}",
                        "Reply Length": f"{len(reply_text)} chars",
                        "Status": "✅ Posted publicly"
                    }
                )
                
        except Exception as e:
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="AI Commands",
                    error=e,
                    context=f"AI public reply failed - user: {interaction.user.id}, target: {message.id}"
                )
            return await interaction.followup.send(f"❌ AI failed: {e}", ephemeral=True)

        # Post the reply publicly, as a threaded reply to the original message
        try:
            await message.reply(
                content=reply_text[:1900],
                mention_author=False,  # avoid pinging the author automatically
                allowed_mentions=discord.AllowedMentions(
                    users=True, roles=False, everyone=False, replied_user=False
                ),
            )
            await interaction.followup.send("✅ Posted AI reply", ephemeral=True)
        except discord.Forbidden:
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="AI Commands",
                    error=Exception("Permission denied - cannot send messages"),
                    context=f"AI reply post failed - user: {interaction.user.id}, channel: {message.channel.id}"
                )
            await interaction.followup.send("❌ I lack permission to send messages here.", ephemeral=True)
        except Exception as e:
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="AI Commands",
                    error=e,
                    context=f"AI reply post failed - user: {interaction.user.id}, channel: {message.channel.id}"
                )
            await interaction.followup.send(f"❌ Failed to post: {e}", ephemeral=True)
            
    @app_commands.command(name="ai_ask", description="Ask the AI anything (short helpful answer).")
    @app_commands.describe(
        prompt="What do you want to ask?",
        public="Post the answer publicly in the channel (default: off/ephemeral)."
    )
    async def ai_ask(self, interaction: Interaction, prompt: str, public: Optional[bool] = False):
        await interaction.response.defer(ephemeral=not public)

        # --- USAGE LIMIT GUARD ---
        ai_service = get_ai_service()
        allowed, counters = ai_service.check_and_count_user(str(interaction.user.id))
        if not allowed:
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="AI Service",
                    title="User Limit Reached",
                    description=f"<@{interaction.user.id}> hit AI usage cap",
                    level=LogLevel.WARNING,
                    fields={
                        "Hour": f"{counters['hour']}/{ai_service.user_limits['per_hour']}",
                        "Day": f"{counters['day']}/{ai_service.user_limits['per_day']}",
                        "Week": f"{counters['week']}/{ai_service.user_limits['per_week']}",
                        "Command": "/ai_ask"
                    }
                )
            return await interaction.followup.send(
                "⏳ You’ve reached your AI usage limit. Please try again later.",
                ephemeral=not public
            )
        
        try:
            answer = await ask_ai(prompt=prompt, system_context="You are a helpful Discord assistant.", max_length=350)
            
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="AI Commands",
                    title="AI Question Answered",
                    description=f"<@{interaction.user.id}> asked AI a question",
                    level=LogLevel.SUCCESS,
                    fields={
                        "Command": "/ai_ask",
                        "User": f"<@{interaction.user.id}>",
                        "Question Length": f"{len(prompt)} chars",
                        "Answer Length": f"{len(answer)} chars",
                        "Visibility": "Public" if public else "Private",
                        "Status": "✅ Success"
                    }
                )
                
            await interaction.followup.send(answer[:1900], ephemeral=not public)
        except Exception as e:
            logger.exception("ai_ask failed")
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="AI Commands",
                    error=e,
                    context=f"ai_ask failed - user: {interaction.user.id}, prompt: {prompt[:100]}..."
                )
            await interaction.followup.send(f"❌ AI failed: {e}", ephemeral=True)

    @app_commands.command(name="ai_translate", description="Translate text to a given language.")
    @app_commands.describe(
        text="Text to translate",
        to_language="Target language (e.g. 'english', 'czech', 'polish')",
        public="Post the translation publicly (default: off/ephemeral)."
    )
    async def ai_translate(self, interaction: Interaction, text: str, to_language: str, public: Optional[bool] = False):
        await interaction.response.defer(ephemeral=not public)

        # --- USAGE LIMIT GUARD ---
        ai_service = get_ai_service()
        allowed, counters = ai_service.check_and_count_user(str(interaction.user.id))
        if not allowed:
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="AI Service",
                    title="User Limit Reached",
                    description=f"<@{interaction.user.id}> hit AI usage cap",
                    level=LogLevel.WARNING,
                    fields={
                        "Hour": f"{counters['hour']}/{ai_service.user_limits['per_hour']}",
                        "Day": f"{counters['day']}/{ai_service.user_limits['per_day']}",
                        "Week": f"{counters['week']}/{ai_service.user_limits['per_week']}",
                        "Command": "/ai_translate"
                    }
                )
            return await interaction.followup.send(
                "⏳ You’ve reached your AI usage limit. Please try again later.",
                ephemeral=not public
            )

        try:
            result = await translate_message(text, to_language)
            
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="AI Commands",
                    title="AI Translation Completed",
                    description=f"<@{interaction.user.id}> translated text",
                    level=LogLevel.SUCCESS,
                    fields={
                        "Command": "/ai_translate",
                        "User": f"<@{interaction.user.id}>",
                        "Target Language": to_language,
                        "Original Length": f"{len(text)} chars",
                        "Translated Length": f"{len(result)} chars",
                        "Visibility": "Public" if public else "Private",
                        "Status": "✅ Success"
                    }
                )
                
            await interaction.followup.send(result[:1900], ephemeral=not public)
        except Exception as e:
            logger.exception("ai_translate failed")
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="AI Commands",
                    error=e,
                    context=f"ai_translate failed - user: {interaction.user.id}, language: {to_language}"
                )
            await interaction.followup.send(f"❌ Translation failed: {e}", ephemeral=True)

    @app_commands.command(name="ai_explain", description="Explain a concept briefly and clearly.")
    @app_commands.describe(
        concept="What should be explained?",
        context="Optional extra context (e.g. 'for first-year CS student')",
        public="Post publicly (default: off/ephemeral)."
    )
    async def ai_explain(self, interaction: Interaction, concept: str, context: Optional[str] = "Discord server", public: Optional[bool] = False):
        await interaction.response.defer(ephemeral=not public)

        # --- USAGE LIMIT GUARD ---
        ai_service = get_ai_service()
        allowed, counters = ai_service.check_and_count_user(str(interaction.user.id))
        if not allowed:
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="AI Service",
                    title="User Limit Reached",
                    description=f"<@{interaction.user.id}> hit AI usage cap",
                    level=LogLevel.WARNING,
                    fields={
                        "Hour": f"{counters['hour']}/{ai_service.user_limits['per_hour']}",
                        "Day": f"{counters['day']}/{ai_service.user_limits['per_day']}",
                        "Week": f"{counters['week']}/{ai_service.user_limits['per_week']}",
                        "Command": "/ai_explain"
                    }
                )
            return await interaction.followup.send(
                "⏳ You’ve reached your AI usage limit. Please try again later.",
                ephemeral=not public
            )

        try:
            result = await explain_concept(concept, context=context or "Discord server")
            
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="AI Commands",
                    title="AI Explanation Generated",
                    description=f"<@{interaction.user.id}> requested an AI explanation",
                    level=LogLevel.SUCCESS,
                    fields={
                        "Command": "/ai_explain",
                        "User": f"<@{interaction.user.id}>",
                        "Concept": concept[:100] + ("..." if len(concept) > 100 else ""),
                        "Context": context or "Discord server",
                        "Explanation Length": f"{len(result)} chars",
                        "Visibility": "Public" if public else "Private",
                        "Status": "✅ Success"
                    }
                )
                
            await interaction.followup.send(result[:1900], ephemeral=not public)
        except Exception as e:
            logger.exception("ai_explain failed")
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="AI Commands",
                    error=e,
                    context=f"ai_explain failed - user: {interaction.user.id}, concept: {concept[:50]}..."
                )
            await interaction.followup.send(f"❌ Explain failed: {e}", ephemeral=True)

    @app_commands.command(name="ai_improve", description="Improve or rewrite text.")
    @app_commands.describe(
        text="Original text to improve",
        instruction="e.g. 'make it clearer and more professional'",
        public="Post publicly (default: off/ephemeral)."
    )
    async def ai_improve(self, interaction: Interaction, text: str, instruction: Optional[str] = "make it clearer and more professional", public: Optional[bool] = False):
        await interaction.response.defer(ephemeral=not public)

        # --- USAGE LIMIT GUARD ---
        ai_service = get_ai_service()
        allowed, counters = ai_service.check_and_count_user(str(interaction.user.id))
        if not allowed:
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="AI Service",
                    title="User Limit Reached",
                    description=f"<@{interaction.user.id}> hit AI usage cap",
                    level=LogLevel.WARNING,
                    fields={
                        "Hour": f"{counters['hour']}/{ai_service.user_limits['per_hour']}",
                        "Day": f"{counters['day']}/{ai_service.user_limits['per_day']}",
                        "Week": f"{counters['week']}/{ai_service.user_limits['per_week']}",
                        "Command": "/ai_improve"
                    }
                )
            return await interaction.followup.send(
                "⏳ You’ve reached your AI usage limit. Please try again later.",
                ephemeral=not public
            )

        try:
            result = await improve_text(text, instruction=instruction or "make it clearer and more professional")
            
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="AI Commands",
                    title="AI Text Improvement",
                    description=f"<@{interaction.user.id}> improved text with AI",
                    level=LogLevel.SUCCESS,
                    fields={
                        "Command": "/ai_improve",
                        "User": f"<@{interaction.user.id}>",
                        "Original Length": f"{len(text)} chars",
                        "Improved Length": f"{len(result)} chars",
                        "Instruction": instruction or "make it clearer and more professional",
                        "Visibility": "Public" if public else "Private",
                        "Status": "✅ Success"
                    }
                )
                
            await interaction.followup.send(result[:1900], ephemeral=not public)
        except Exception as e:
            logger.exception("ai_improve failed")
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="AI Commands",
                    error=e,
                    context=f"ai_improve failed - user: {interaction.user.id}, text length: {len(text)}"
                )
            await interaction.followup.send(f"❌ Improve failed: {e}", ephemeral=True)

    # Context Menu (Right-click) Commands on a Message
    async def _ctx_ai_reply(self, interaction: Interaction, message: discord.Message):
        """Generate a short reply to the selected message."""
        await interaction.response.defer(ephemeral=True)

        # --- USAGE LIMIT GUARD ---
        ai_service = get_ai_service()
        allowed, counters = ai_service.check_and_count_user(str(interaction.user.id))
        if not allowed:
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="AI Service",
                    title="User Limit Reached",
                    description=f"<@{interaction.user.id}> hit AI usage cap",
                    level=LogLevel.WARNING,
                    fields={
                        "Hour": f"{counters['hour']}/{ai_service.user_limits['per_hour']}",
                        "Day": f"{counters['day']}/{ai_service.user_limits['per_day']}",
                        "Week": f"{counters['week']}/{ai_service.user_limits['per_week']}",
                        "Command": "AI: Reply"
                    }
                )
            return await interaction.followup.send(
                "⏳ You’ve reached your AI usage limit. Please try again later.",
                ephemeral=True
            )

        try:
            # Pull a bit of context (last 4 messages before the target)
            history: List[str] = []
            try:
                async for m in message.channel.history(limit=5, before=message, oldest_first=False):
                    if m.author.bot:
                        continue
                    history.append(f"{m.author.display_name}: {m.content}")
            except Exception:
                pass

            convo = list(reversed(history))  # earlier → later
            reply = await smart_reply(
                user_message=message.content,
                conversation_context=convo,
                bot_personality="helpful moderator bot"
            )
            
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="AI Commands",
                    title="AI Reply Draft Generated",
                    description=f"<@{interaction.user.id}> generated AI reply draft",
                    level=LogLevel.SUCCESS,
                    fields={
                        "Command": "AI: Reply",
                        "User": f"<@{interaction.user.id}>",
                        "Target Message": f"By {message.author.mention} in {message.channel.mention}",
                        "Reply Length": f"{len(reply)} chars",
                        "Status": "✅ Draft generated"
                    }
                )
            
            # Show and also offer to post it
            btn = discord.ui.Button(label="Post to channel", style=discord.ButtonStyle.primary)
            view = discord.ui.View(timeout=30)
            view.add_item(btn)

            async def _post_callback(i: Interaction):
                if i.user.id != interaction.user.id:
                    return await i.response.send_message("❌ Only the requester can post this.", ephemeral=True)
                
                if self.embed_logger:
                    await self.embed_logger.log_custom(
                        service="AI Commands",
                        title="AI Reply Posted",
                        description=f"<@{interaction.user.id}> posted AI reply via button",
                        level=LogLevel.SUCCESS,
                        fields={
                            "Original Command": "AI: Reply",
                            "User": f"<@{interaction.user.id}>",
                            "Action": "Posted via button",
                            "Reply Length": f"{len(reply)} chars"
                        }
                    )
                    
                await i.response.send_message(f"↪️ Replying to {message.author.mention}:\n{reply}", ephemeral=False)

            btn.callback = _post_callback  # type: ignore
            await interaction.followup.send(f"**AI reply draft (ephemeral):**\n{reply}", view=view, ephemeral=True)
        except Exception as e:
            logger.exception("ctx_ai_reply failed")
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="AI Commands",
                    error=e,
                    context=f"ctx_ai_reply failed - user: {interaction.user.id}, message: {message.id}"
                )
            await interaction.followup.send(f"❌ AI reply failed: {e}", ephemeral=True)

    async def _ctx_ai_summarize(self, interaction: Interaction, message: discord.Message):
        """Summarize the selected message briefly."""
        await interaction.response.defer(ephemeral=True)

        # --- USAGE LIMIT GUARD ---
        ai_service = get_ai_service()
        allowed, counters = ai_service.check_and_count_user(str(interaction.user.id))
        if not allowed:
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="AI Service",
                    title="User Limit Reached",
                    description=f"<@{interaction.user.id}> hit AI usage cap",
                    level=LogLevel.Warning if hasattr(LogLevel, "Warning") else LogLevel.WARNING,
                    fields={
                        "Hour": f"{counters['hour']}/{ai_service.user_limits['per_hour']}",
                        "Day": f"{counters['day']}/{ai_service.user_limits['per_day']}",
                        "Week": f"{counters['week']}/{ai_service.user_limits['per_week']}",
                        "Command": "AI: Summarize"
                    }
                )
            return await interaction.followup.send(
                "⏳ You’ve reached your AI usage limit. Please try again later.",
                ephemeral=True
            )

        try:
            prompt = (
                "Summarize the following message for a Discord chat in 1–2 sentences. "
                "Be neutral, factual, and concise.\n\n"
                f"Message by {message.author.display_name}:\n```{message.content[:1800]}```"
            )
            summary = await ask_ai(prompt=prompt, system_context="You are a concise summarizer.", max_length=160, creativity=0.2)
            
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="AI Commands",
                    title="AI Summary Generated",
                    description=f"<@{interaction.user.id}> generated AI summary",
                    level=LogLevel.SUCCESS,
                    fields={
                        "Command": "AI: Summarize",
                        "User": f"<@{interaction.user.id}>",
                        "Target Message": f"By {message.author.mention} in {message.channel.mention}",
                        "Original Length": f"{len(message.content)} chars",
                        "Summary Length": f"{len(summary)} chars",
                        "Status": "✅ Success"
                    }
                )
                
            await interaction.followup.send(f"**Summary:** {summary}", ephemeral=True)
        except Exception as e:
            logger.exception("ctx_ai_summarize failed")
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="AI Commands",
                    error=e,
                    context=f"ctx_ai_summarize failed - user: {interaction.user.id}, message: {message.id}"
                )
            await interaction.followup.send(f"❌ AI summarize failed: {e}", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Publicly reply when the bot is mentioned in a message.
        Uses funny personas by default, falls back to serious style if the message
        looks technical (code blocks, stack traces).
        """
        try:
            # Ignore DMs and bot messages
            if message.author.bot or message.guild is None:
                return

            if not self.bot.user:
                return

            # Feature toggles from config (safe defaults)
            if hasattr(self.bot, "config"):
                if getattr(self.bot.config, "ai_reply_on_mention", True) is False:
                    return
                personas_enabled = getattr(self.bot.config, "ai_personas_enabled", True)
            else:
                personas_enabled = True

            # Is the bot mentioned?
            bot_id = self.bot.user.id
            mentioned = False
            if message.mentions and any(u.id == bot_id for u in message.mentions):
                mentioned = True
            else:
                raw = message.content or ""
                if f"<@{bot_id}>" in raw or f"<@!{bot_id}>" in raw:
                    mentioned = True
            if not mentioned:
                return

            # Optional: give moderation a breath (uncomment if needed)
            # await asyncio.sleep(0.15)

            # --- USAGE LIMIT GUARD ---
            ai_service = get_ai_service()
            if not ai_service:
                return

            allowed, counters = ai_service.check_and_count_user(str(message.author.id))
            if not allowed:
                if self.embed_logger:
                    await self.embed_logger.log_custom(
                        service="AI Service",
                        title="User Limit Reached",
                        description=f"<@{message.author.id}> hit AI usage cap (mention reply)",
                        level=LogLevel.WARNING,
                        fields={
                            "Hour": f"{counters['hour']}/{ai_service.user_limits['per_hour']}",
                            "Day": f"{counters['day']}/{ai_service.user_limits['per_day']}",
                            "Week": f"{counters['week']}/{ai_service.user_limits['per_week']}",
                            "Channel": f"{message.channel.mention}",
                        }
                    )
                return

            # Detect "serious" messages (avoid goofy persona when it looks technical)
            raw = message.content or ""
            is_serious = (
                "```" in raw
                or "traceback" in raw.lower()
                or "exception" in raw.lower()
                or "error" in raw.lower()
                or "docker" in raw.lower()
                or "sql" in raw.lower()
                or "python" in raw.lower()
                or "stack" in raw.lower()
                or len(raw) > 600
            )

            # Build small recent human-only context
            history_lines: list[str] = []
            try:
                async for m in message.channel.history(limit=6, before=message, oldest_first=False):
                    if m.author.bot:
                        continue
                    if not m.content:
                        continue
                    history_lines.append(f"{m.author.display_name}: {m.content[:400]}")
            except Exception:
                pass
            history_lines = list(reversed(history_lines))

            # Strip the bot mention from the text
            clean_text = raw.replace(self.bot.user.mention, "").strip()

            # Generate reply (funny personas by default, but off for serious)
            persona_used = None
            try:
                reply_text = await ai_service.generate_chat_reply(
                    user_message=clean_text if clean_text else raw,
                    conversation_context=history_lines,
                    temperature=0.65 if (personas_enabled and not is_serious) else 0.5,
                    max_tokens=360,
                    model=None,  # use current default chat model
                    funny=personas_enabled and not is_serious,
                    persona=None,  # let AI service pick randomly
                )
            except Exception as e:
                if self.embed_logger:
                    await self.embed_logger.log_error(
                        service="AI Commands",
                        error=e,
                        context=f"Mention reply generation failed in #{message.channel.id}"
                    )
                return

            # Post publicly as a reply
            try:
                await message.reply(
                    content=reply_text[:1900],
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions(
                        users=True, roles=False, everyone=False, replied_user=False
                    ),
                )

                if self.embed_logger:
                    persona_label = "fun" if (personas_enabled and not is_serious) else "serious"
                    await self.embed_logger.log_custom(
                        service="AI Commands",
                        title="Mention Reply Posted",
                        description=f"Bot replied publicly to a mention by <@{message.author.id}>",
                        level=LogLevel.SUCCESS,
                        fields={
                            "Channel": message.channel.mention,
                            "Mode": persona_label,
                            "Reply Length": f"{len(reply_text)}",
                            "User": f"<@{message.author.id}>",
                        }
                    )
            except discord.Forbidden as e:
                if self.embed_logger:
                    await self.embed_logger.log_error(
                        service="AI Commands",
                        error=e,
                        context=f"Permission error sending mention reply in #{message.channel.id}"
                    )
            except Exception as e:
                if self.embed_logger:
                    await self.embed_logger.log_error(
                        service="AI Commands",
                        error=e,
                        context=f"Failed to send mention reply in #{message.channel.id}"
                    )
        except Exception as e:
            logger.exception("Unhandled error in on_message mention handler: %s", e)



    # Nice error handling
    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: Interaction, error: app_commands.AppCommandError):
        from discord.app_commands import errors
        
        if self.embed_logger:
            await self.embed_logger.log_error(
                service="AI Commands",
                error=error,
                context=f"AI command error - User: {interaction.user.id}, Command: {getattr(interaction.command, 'name', 'unknown')}"
            )
        
        try:
            if isinstance(error, errors.CommandOnCooldown):
                await interaction.response.send_message("⏳ Hold up, that command is on cooldown.", ephemeral=True)
            elif isinstance(error, errors.MissingPermissions):
                await interaction.response.send_message("❌ You don't have permission to use this.", ephemeral=True)
            else:
                logger.exception("AI Cog command error")
                if interaction.response.is_done():
                    await interaction.followup.send("❌ Command failed unexpectedly.", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ Command failed unexpectedly.", ephemeral=True)
        except Exception:
            pass

    # Admin: config viewer
    @app_commands.command(name="ai_config", description="Show AI service configuration and models")
    @app_commands.checks.has_permissions(administrator=True)
    async def ai_config(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = get_ai_config()
        if cfg.get("service_status") != "active":
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="AI Commands",
                    error=Exception("AI service not initialized"),
                    context=f"ai_config command by {interaction.user.id}"
                )
            return await interaction.followup.send("❌ AI service is not initialized.", ephemeral=True)

        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="AI Commands",
                title="AI Config Viewed",
                description=f"<@{interaction.user.id}> viewed AI configuration",
                level=LogLevel.INFO,
                fields={
                    "Command": "/ai_config",
                    "Executed By": f"<@{interaction.user.id}>",
                    "Models Available": str(len(cfg.get("available_models", []))),
                    "Current Model": cfg.get("default_model_display", "unknown")
                }
            )

        # Header embed (no huge fields)
        header = discord.Embed(title="🤖 AI Service Configuration", color=discord.Color.blue())
        header.add_field(name="Provider", value=cfg["provider"], inline=True)
        header.add_field(name="Status", value=cfg["service_status"], inline=True)
        header.add_field(
            name="Default Model",
            value=f"{cfg['default_model_display']}\n`{cfg['default_model_api']}`",
            inline=False
        )
        header.add_field(
            name="Moderation Model",
            value="llama-3-1-8b-128k (forced)",
            inline=False
        )
        header.add_field(name="Rate Limit", value=f"{cfg['rate_limit_rpm']} req/min", inline=True)
        header.add_field(name="Base URL", value=f"`{cfg['base_url']}`", inline=False)

        # Build the models list as plain lines first
        lines = []
        for m in sorted(cfg["available_models"], key=lambda x: x["display"].lower()):
            star = "⭐" if m["key"] == cfg["default_model_key"] else "•"
            price_in = f"${m['in_price']:.2f}" if m["in_price"] is not None else "n/a"
            price_out = f"${m['out_price']:.2f}" if m["out_price"] is not None else "n/a"
            lines.append(
                f"{star} **{m['display']}**\n"
                f"   key: `{m['key']}` → api: `{m['api_name']}`\n"
                f"   ctx: {m['ctx']:,}  |  speed: {m['tps']}/s  |  in: {price_in}/MTok  |  out: {price_out}/MTok"
            )

        # Chunk lines into embed descriptions ≤ 1900 chars
        def chunk_lines_to_strings(items, limit=1900):
            chunks, cur = [], ""
            for ln in items:
                # +1 for newline between lines
                if len(cur) + len(ln) + 1 > limit:
                    if cur:
                        chunks.append(cur)
                    cur = ln
                else:
                    cur = (cur + "\n" + ln) if cur else ln
            if cur:
                chunks.append(cur)
            return chunks

        model_chunks = chunk_lines_to_strings(lines, limit=1900)

        # Build embeds: first is header, then 1..N "Models" embeds
        embeds: list[discord.Embed] = [header]
        for i, chunk in enumerate(model_chunks, 1):
            em = discord.Embed(
                title=f"Models ({i}/{len(model_chunks)})",
                description=chunk,
                color=discord.Color.blurple()
            )
            embeds.append(em)

        # Discord allows up to 10 embeds per message; send in batches if needed
        MAX_EMBEDS_PER_MESSAGE = 10
        sent_first = False
        for i in range(0, len(embeds), MAX_EMBEDS_PER_MESSAGE):
            batch = embeds[i:i + MAX_EMBEDS_PER_MESSAGE]
            if not sent_first:
                await interaction.followup.send(embeds=batch, ephemeral=True)
                sent_first = True
            else:
                await interaction.followup.send(embeds=batch, ephemeral=True)

    # Admin: set model with autocomplete
    async def _model_autocomplete(self, interaction: Interaction, current: str):
        reg = get_ai_model_registry()
        choices = []
        needle = (current or "").lower()
        for k, v in reg.items():
            label = f"{v['display']} ({k})"
            if not needle or needle in k.lower() or needle in v["display"].lower():
                choices.append(app_commands.Choice(name=label[:100], value=k[:100]))
            if len(choices) >= 20:
                break
        return choices

    @app_commands.command(name="ai_set_model", description="Set the AI default model")
    @app_commands.describe(model_key="Model key (use autocomplete or /ai_config)")
    @app_commands.autocomplete(model_key=_model_autocomplete)
    @app_commands.checks.has_permissions(administrator=True)
    async def ai_set_model(self, interaction: Interaction, model_key: str):
        await interaction.response.defer(ephemeral=True)
        reg = get_ai_model_registry()
        
        # Get AI service for logging
        ai_service = get_ai_service()
        
        if model_key not in reg:
            # allow raw API name as advanced escape hatch
            if ai_service:
                await ai_service.set_default_model(model_key, str(interaction.user.id))
            else:
                set_ai_default_model(model_key)
                
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="AI Configuration",
                    title="AI Model Set (Raw API Name)",
                    description=f"<@{interaction.user.id}> set AI model to raw API name",
                    level=LogLevel.WARNING,
                    fields={
                        "Command": "/ai_set_model",
                        "Executed By": f"<@{interaction.user.id}>",
                        "Model Key": f"`{model_key}`",
                        "Type": "Raw API Name (not in registry)",
                        "Warning": "Provider may reject if invalid",
                        "Status": "⚠️ Set with warning"
                    }
                )
                
            return await interaction.followup.send(
                f"⚠️ `{model_key}` is not in registry; set as raw API name. "
                f"If provider rejects it, switch to a known key from `/ai_config`.",
                ephemeral=True
            )
            
        # Set registered model
        if ai_service:
            await ai_service.set_default_model(model_key, str(interaction.user.id))
        else:
            set_ai_default_model(model_key)
            
        info = reg[model_key]
        
        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="AI Configuration",
                title="AI Default Model Changed",
                description=f"<@{interaction.user.id}> changed the default AI model",
                level=LogLevel.SUCCESS,
                fields={
                    "Command": "/ai_set_model",
                    "Executed By": f"<@{interaction.user.id}>",
                    "New Model": info['display'],
                    "Model Key": f"`{model_key}`",
                    "API Name": f"`{info['api_name']}`",
                    "Context Length": f"{info['ctx']:,}",
                    "Speed": f"~{info['tps']}/s",
                    "Status": "✅ Successfully changed"
                }
            )
        
        await interaction.followup.send(
            f"✅ Default model set to **{info['display']}**\n`{info['api_name']}` (ctx {info['ctx']:,}, ~{info['tps']}/s).",
            ephemeral=True
        )
