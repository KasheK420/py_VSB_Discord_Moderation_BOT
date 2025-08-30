# bot/cogs/welcome_cog.py
from __future__ import annotations

import logging
import os
import random
from typing import Optional, List

import discord
from discord.ext import commands

from bot.services.logging_service import LogLevel
from bot.services.tenor_service import TenorClient
from bot.utils.ai_helper import get_ai_service  # uses your shared AIService accessor

logger = logging.getLogger(__name__)


# -------- Fallback Czech templates (used only if AI call fails) --------

def _poem_welcome_fallback(name: str) -> str:
    name = (name or "příteli").strip()
    choices = [
        [
            f"{name}, vítej u nás, v tomhle chatu,",
            "ptej se klidně — bez zbytečného patu.",
            "Když zabloudíš, mrkni na připnuté zprávy,",
            "od toho jsme tu — pomůžem ti hravě."
        ],
        [
            f"Ahoj {name}! Přisel jsi v pravý čas,",
            "kanály čekají, pojď mezi nás.",
            "Když něco nejde, napiš pár vět,",
            "společně najdeme správný směr i svět."
        ],
    ]
    return "\n".join(random.choice(choices))


def _poem_farewell_fallback(name: str, reason_label: str) -> str:
    name = (name or "cestovateli").strip()
    tail = "měj se krásně a ať se daří dál." if reason_label != "zabanován" else "snad příště lépe — tak zas někdy dál."
    choices = [
        [
            f"{name} dnes {reason_label} náš digitální sál,",
            "vzpomínky zůstanou, chat nezmizel v dál.",
            "Ať pingy ti přejí, ať net drží dál,",
            tail
        ],
        [
            f"Tak ahoj {name}, co {reason_label} bez váhání,",
            "naše vlákna šumí, běží povídání.",
            "Kdyby ses vrátil, budem rádi zas,",
            tail
        ],
    ]
    return "\n".join(random.choice(choices))


# --------------------------- Cog ---------------------------

class WelcomeCog(commands.Cog):
    """
    CZ welcome/goodbye:
    - On join: public poem in general channel (AI, gpt-oss-120b) + optional Tenor GIF + Czech DM instructions.
    - On leave/kick/ban: public farewell poem (AI) in general channel.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.embed_logger = getattr(bot, "embed_logger", None)

        # Public channel to post poems (fallback to welcome channel if general is not set)
        self.general_channel_id: Optional[int] = getattr(bot.config, "general_channel_id", None) \
            or getattr(bot.config, "welcome_channel_id", None)

        # Verification channel (for DM instructions)
        self.verification_channel_id: Optional[int] = getattr(bot.config, "welcome_channel_id", None)

        # Tenor settings (optional). Default locale -> cs_CZ so retrieved GIFs match language where possible.
        api_key = getattr(bot.config, "tenor_api_key", "") or ""
        locale = getattr(bot.config, "tenor_locale", None) or "cs_CZ"
        content_filter = getattr(bot.config, "tenor_content_filter", "medium")
        self.tenor = TenorClient(api_key, locale=locale, content_filter=content_filter)

        # Model for occasional AI generation in this cog
        self.poem_model = "gpt-oss-120b"

    # ---------- helpers ----------

    def _get_general(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        if not self.general_channel_id:
            return None
        ch = guild.get_channel(int(self.general_channel_id))
        return ch if isinstance(ch, discord.TextChannel) else None

    async def _fetch_tenor_gif(self, query: str) -> Optional[str]:
        if not self.tenor.is_enabled:
            return None
        try:
            return await self.tenor.best_gif(query)
        except Exception as e:
            logger.debug(f"Tenor GIF fetch failed: {e}")
            return None

    async def _generate_cz_poem(self, member_name: str, kind: str) -> str:
        """
        Return a short Czech poem for welcome/farewell. Never returns empty string.
        kind: 'welcome' | 'farewell:odešel' | 'farewell:kick' | 'farewell:ban'
        """
        from bot.utils.ai_helper import get_ai_service
        ai = get_ai_service()

        # Prefer a model that your Groq account actually has.
        # You can override via env WELCOME_POEM_MODEL if you want to experiment.
        model = os.getenv("WELCOME_POEM_MODEL", "llama4-scout")

        tone = {
            "welcome": "vřelé uvítání a přátelská, studentská atmosféra",
            "farewell:odešel": "milé rozloučení a přání hodně štěstí",
            "farewell:kick": "krátká, lehce škádlivá rozlučka bez urážek",
            "farewell:ban": "formální rozloučení bez negativity, žádné urážky",
        }.get(kind, "vřelá, přátelská atmosféra")

        system_prompt = (
            "Jsi přátelský básník českého Discord serveru VŠB. "
            "Vždy odpovídej česky, bez uvozovek a bez formátovacích značek. "
            "Piš 3–6 krátkých řádků, hravých a srozumitelných. "
            "Nepoužívej markdownové bloky ani kódové fence."
        )

        user_prompt = (
            f"Napiš krátkou, hravou básničku pro uživatele jménem **{member_name}**. "
            f"Téma: {tone}. "
            "Básnička má být laskavá, stručná a školní, žádné vulgarity."
        )

        text = ""
        try:
            if ai:
                # We force Czech, so we don't need the language-preservation helper.
                text = await ai.quick_prompt(
                    prompt=user_prompt,
                    system_prompt=system_prompt,
                    max_tokens=220,
                    temperature=0.85,
                    respect_input_language=False,
                    model=model,
                )
                text = (text or "").strip()
                # Remove possible code fences or stray backticks
                if text.startswith("```"):
                    text = text.strip("` \n")
                # Normalize too-long output
                lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                if len(lines) > 6:
                    lines = lines[:6]
                text = "\n".join(lines)
        except Exception as e:
            # Log the underlying AI error, but don't break the user flow
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Welcome",
                    error=e,
                    context=f"AI poem generation exception (kind={kind})"
                )
            text = ""

        if not text:
            # Solid Czech fallback to avoid raising 'Empty AI poem'
            emotis = ["🎓", "✨", "💚", "🧭", "📚", "🟢"]
            emoji = random.choice(emotis)
            if kind.startswith("farewell"):
                text = (
                    f"{member_name}, ať cesta dál je fajn,\n"
                    "u nás máš dveře vždycky dokořán.\n"
                    "Když budeš chtít, tak zase napiš nám,\n"
                    f"Discord tě vítá — ať se daří! {emoji}"
                )
            else:
                text = (
                    f"Vítej k nám, {member_name}, mezi nás,\n"
                    "ať každý den má dobrý čas.\n"
                    "Studuj, bav se, ptej se klidně dál,\n"
                    f"spolu to dáme — vítej! {emoji}"
                )

        # Optional: log success for observability
        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Welcome",
                title="Poem Generated",
                description="CZ poem prepared for user event",
                level=LogLevel.SUCCESS,
                fields={
                    "Kind": kind,
                    "Model": model,
                    "Length": f"{len(text)} chars",
                }
            )

        return text


    async def _send_welcome_embed(self, member: discord.Member) -> None:
        channel = self._get_general(member.guild)
        if not channel:
            return

        poem = await self._generate_cz_poem(member.display_name, kind="welcome")

        # Try name-based GIF, fallback to generic Czech terms
        gif_url = await (self._fetch_tenor_gif(f"{member.display_name} vítání") or self._fetch_tenor_gif("uvítání"))

        embed = discord.Embed(
            title=f"Vítej, {member.display_name}! 🎉",
            description=poem,
            color=discord.Color.green(),
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        if gif_url:
            embed.set_image(url=gif_url)
        embed.add_field(name="Začni klidně pozdravem 👋", value=f"Vítej na **{member.guild.name}**!", inline=False)
        embed.add_field(name="Tipy pro nováčky", value="Mrkni na připnuté zprávy a FAQ kanály.", inline=False)
        embed.set_footer(text=f"Uživatel ID: {member.id}")

        try:
            await channel.send(content=f"Ahoj <@{member.id}>!", embed=embed,
                               allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Welcome",
                    title="Uvítání zveřejněno",
                    description=f"Vítej embed pro <@{member.id}> v {channel.mention}",
                    level=LogLevel.SUCCESS,
                    fields={"GIF": gif_url or "žádný", "Model": self.poem_model}
                )
        except discord.Forbidden as e:
            if self.embed_logger:
                await self.embed_logger.log_error("Welcome", e, context=f"Chybí oprávnění v #{getattr(channel, 'id', '?')}")
        except Exception as e:
            if self.embed_logger:
                await self.embed_logger.log_error("Welcome", e, context=f"Nezdařilo se poslat uvítání pro {member.id}")

    async def _dm_new_member(self, member: discord.Member) -> None:
        # CZ onboarding DM
        vr_ch = member.guild.get_channel(int(self.verification_channel_id)) if self.verification_channel_id else None
        verify_hint = f"• Ověření: přejdi do {vr_ch.mention} a postupuj podle instrukcí." if vr_ch else "• Ověření: mrkni do uvítacího kanálu a postupuj podle instrukcí."

        text = (
            f"Ahoj {member.display_name}! 👋\n\n"
            f"Vítej na **{member.guild.name}**.\n\n"
            f"**Jak začít:**\n"
            f"{verify_hint}\n"
            f"• Projdi si připnuté zprávy v důležitých kanálech.\n"
            f"• Kdykoli se zeptej — komunita ti ráda poradí.\n\n"
            f"Hodně štěstí a ať se ti tu líbí! 🍀"
        )

        try:
            await member.send(text)
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Welcome",
                    title="UVÍTACÍ DM odeslána",
                    description=f"Soukromá zpráva poslána uživateli <@{member.id}>",
                    level=LogLevel.INFO
                )
        except discord.Forbidden:
            if self.embed_logger:
                await self.embed_logger.log_warning(
                    title="DM nelze doručit",
                    description=f"Uživatel <@{member.id}> má uzavřené zprávy."
                )
        except Exception as e:
            if self.embed_logger:
                await self.embed_logger.log_error("Welcome", e, context=f"DM selhala pro {member.id}")

    async def _send_farewell_embed(self, guild: discord.Guild, user: discord.abc.User, reason_label: str) -> None:
        channel = self._get_general(guild)
        if not channel:
            return

        poem = await self._generate_cz_poem(getattr(user, "display_name", user.name), kind=f"farewell:{reason_label}")
        gif_url = await (self._fetch_tenor_gif(f"{user.name} rozloučení") or self._fetch_tenor_gif("rozloučení"))

        embed = discord.Embed(
            title=f"Na rozloučenou, {user.name} 👋",
            description=poem,
            color=discord.Color.orange() if reason_label != "zabanován" else discord.Color.dark_red(),
        )
        if isinstance(user, (discord.Member, discord.User)):
            embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        if gif_url:
            embed.set_image(url=gif_url)
        embed.set_footer(text=f"Uživatel ID: {user.id}")

        try:
            await channel.send(embed=embed)
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Welcome",
                    title="Rozloučení zveřejněno",
                    description=f"Zpráva při odchodu ({reason_label}) pro {user} v {channel.mention}",
                    level=LogLevel.INFO,
                    fields={"GIF": gif_url or "žádný", "Model": self.poem_model}
                )
        except Exception as e:
            if self.embed_logger:
                await self.embed_logger.log_error("Welcome", e, context=f"Nezdařilo se poslat rozloučení pro {user.id}")

    # ---------- events ----------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        await self._send_welcome_embed(member)
        await self._dm_new_member(member)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot:
            return
        await self._send_farewell_embed(member.guild, member, reason_label="odešel")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        if user.bot:
            return
        await self._send_farewell_embed(guild, user, reason_label="zabanován")
