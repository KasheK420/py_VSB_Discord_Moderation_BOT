# bot/utils/i18n.py
from __future__ import annotations
from typing import Optional

# Map Discord locales to ISO2 we’ll use for prompts
_LOCALE_MAP = {
    "cs": "cs", "cs-CZ": "cs",
    "pl": "pl", "pl-PL": "pl",
    "sk": "sk", "sk-SK": "sk",
    "en": "en", "en-US": "en", "en-GB": "en",
    # add more if you want
}

def _normalize(loc: Optional[str]) -> Optional[str]:
    if not loc:
        return None
    loc = loc.strip()
    return _LOCALE_MAP.get(loc, None) or _LOCALE_MAP.get(loc.split("-")[0], None)

def negotiate_language(*, interaction=None, guild=None, config=None) -> str:
    # 1) explicit slash param could be handled by caller (pass-through)
    # 2) interaction locale
    if interaction is not None:
        lang = _normalize(getattr(interaction, "locale", None))
        if lang: return lang
        lang = _normalize(getattr(interaction, "guild_locale", None))
        if lang: return lang
    # 3) guild’s preferred
    if guild is not None:
        lang = _normalize(getattr(guild, "preferred_locale", None))
        if lang: return lang
    # 4) config default (if not 'auto')
    if config is not None and getattr(config, "default_language", "auto") != "auto":
        lang = _normalize(config.default_language)
        if lang: return lang
    # 5) fallback
    fb = getattr(config, "language_fallback", "en") if config else "en"
    return _normalize(fb) or "en"

def language_directive(lang: str) -> str:
    # A firm-but-flexible instruction for the system prompt
    names = {"cs": "Czech", "pl": "Polish", "sk": "Slovak", "en": "English"}
    pretty = names.get(lang, lang)
    return (f"Always answer in {pretty} unless the user explicitly requests another language. "
            f"If the input is in multiple languages, reply in {pretty}.")
