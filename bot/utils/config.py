# bot/utils/config.py

import os
from dataclasses import dataclass, field
from typing import List


def _split_csv(name: str, default: str = "") -> List[str]:
    raw = os.getenv(name, default)
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    # Discord
    bot_token: str = os.getenv("DISCORD_BOT_TOKEN", "")
    guild_id: int = int(os.getenv("DISCORD_GUILD_ID", "631124326522945546"))
    command_prefix: str = os.getenv("COMMAND_PREFIX", "!")

    # OAuth2
    oauth_client_id: str = os.getenv("OAUTH_CLIENT_ID", "")
    oauth_client_secret: str = os.getenv("OAUTH_CLIENT_SECRET", "")
    # Optional custom endpoints (fallback to AuthService defaults if empty)
    oauth_base_url: str = os.getenv("OAUTH_BASE_URL", "")          # e.g., https://vsb-discord-bot.marekhanus.cz
    oauth_authorize_url: str = os.getenv("OAUTH_AUTHORIZE_URL", "")
    oauth_token_url: str = os.getenv("OAUTH_TOKEN_URL", "")
    oauth_userinfo_url: str = os.getenv("OAUTH_USERINFO_URL", "")

    # Database (Postgres)
    db_host: str = os.getenv("DB_HOST", "postgres")
    db_port: int = int(os.getenv("DB_PORT", "5432"))
    db_name: str = os.getenv("DB_NAME", "vsb_discord")
    db_user: str = os.getenv("DB_USER", "vsb_bot")
    db_password: str = os.getenv("DB_PASSWORD", "")

    # Roles
    student_role_id: int = int(os.getenv("STUDENT_ROLE_ID", "691417700949295114"))
    teacher_role_id: int = int(os.getenv("TEACHER_ROLE_ID", "689909803119935665"))
    admin_role_id: int = int(os.getenv("ADMIN_ROLE_ID", "689908370018402343"))
    erasmus_role_id: int = int(os.getenv("ERASMUS_ROLE_ID", "690947461992284211"))
    admin_help_role_id: int = int(os.getenv("ADMIN_HELP_ROLE_ID", "691501757943250966"))
    developer_role_id: int = int(os.getenv("DEVELOPER_ROLE_ID", "692150310231212092"))
    host_role_id: int = int(os.getenv("HOST_ROLE_ID", "690325052658548756"))
    absolvent_role_id: int = int(os.getenv("ABSOLVENT_ROLE_ID", "690325135542190091"))
    classes_role_ids: List[int] = field(default_factory=lambda: [int(x) for x in _split_csv("CLASSES_ROLE_IDS")])

    # Channels
    welcome_channel_id: int = int(os.getenv("WELCOME_CHANNEL_ID", "691407527253901312"))
    bot_channel_id: int = int(os.getenv("BOT_CHANNEL_ID", "691419856632938556"))
    admin_log_channel_id: int = int(os.getenv("ADMIN_LOG_CHANNEL_ID", "0"))
    teachers_accounts_channel_id: int = int(os.getenv("TEACHERS_ACCOUNTS_CHANNEL_ID", "0"))
    giveaway_channel_id: int = int(os.getenv("GIVEAWAY_CHANNEL_ID", "0"))
    vsb_news_channel_id: int = int(os.getenv("VSB_NEWS_CHANNEL_ID", "0"))

    # NEW: General channel for public welcomes/farewells (poems)
    general_channel_id: int = int(os.getenv("GENERAL_CHANNEL_ID", "0") or "0")

    # NEW: Help Center forum channel for the auto-answer cog
    help_center_forum_channel_id: int = int(os.getenv("HELP_CENTER_FORUM_CHANNEL_ID", "0") or "0")

    # Feature flags / toggles
    legacy_prefixes: List[str] = field(default_factory=lambda: _split_csv("LEGACY_PREFIXES"))
    tester_ids: List[int] = field(default_factory=lambda: [int(x) for x in _split_csv("TESTER_IDS")])
    messenger_delete_after: int = int(os.getenv("MESSENGER_DELETE_AFTER", "10"))
    channel_clean_delete_after: int = int(os.getenv("CHANNEL_CLEAN_DELETE_AFTER", "120"))
    verification_teacher_url_prefix: str = os.getenv("VERIFICATION_TEACHER_URL_PREFIX", "")

    # Apps / feature flags
    app_student_verification_enabled: bool = _env_bool("APP_STUDENT_VERIFICATION_ENABLED", False)
    app_student_scraper_enabled: bool = _env_bool("APP_STUDENT_SCRAPER_ENABLED", False)

    # AI Configuration (Groq API)
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    # Default language for user-facing bot messages (set to Czech as requested)
    default_language: str = os.getenv("DEFAULT_LANGUAGE", "cs")    # 'cs' | 'auto' | 'pl' | 'sk' | 'en'
    language_fallback: str = os.getenv("LANGUAGE_FALLBACK", "en")  # fallback if detection fails

    # NEW: AI mention reply + personas toggles
    ai_reply_on_mention: bool = _env_bool("AI_REPLY_ON_MENTION", True)
    ai_personas_enabled: bool = _env_bool("AI_PERSONAS_ENABLED", True)
    WELCOME_POEM_MODEL: str = os.getenv("WELCOME_POEM_MODEL", "llama4-scout")

    # NEW: Tenor GIF integration
    tenor_api_key: str = os.getenv("TENOR_API_KEY", "") or ""
    tenor_locale: str = os.getenv("TENOR_LOCALE", "cs_CZ")
    tenor_content_filter: str = os.getenv("TENOR_CONTENT_FILTER", "medium")

    # Optional SMTP (for future use)
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "465"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_pass: str = os.getenv("SMTP_PASS", "")

    # Hall of Fame / Shame
    hall_of_fame_channel_id: int = int(os.getenv("HALL_OF_FAME_CHANNEL_ID", "0") or "0")
    fame_reaction_threshold: int = int(os.getenv("FAME_REACTION_THRESHOLD", "5") or "5")
    hall_of_shame_channel_id: int = int(os.getenv("HALL_OF_SHAME_CHANNEL_ID", "0") or "0")

    # Economy / XP
    xp_enabled: bool = _env_bool("XP_ENABLED", True)
    xp_message_cooldown_sec: int = int(os.getenv("XP_MESSAGE_COOLDOWN_SEC", "15") or "15")
    xp_per_message: int = int(os.getenv("XP_PER_MESSAGE", "5") or "5")
    points_per_message: int = int(os.getenv("POINTS_PER_MESSAGE", "1") or "1")
    xp_per_reaction_received: int = int(os.getenv("XP_PER_REACTION_RECEIVED", "2") or "2")
    points_per_reaction_received: int = int(os.getenv("POINTS_PER_REACTION_RECEIVED", "1") or "1")
    xp_daily_cap: int = int(os.getenv("XP_DAILY_CAP", "500") or "500")
    
    # Gambling & Shop
    gambling_channel_id: int = int(os.getenv("GAMBLING_CHANNEL_ID", "0") or "0")
    slots_min_bet_per_line: int = int(os.getenv("SLOTS_MIN_BET_PER_LINE", "1") or "1")
    slots_max_bet_per_line: int = int(os.getenv("SLOTS_MAX_BET_PER_LINE", "50") or "50")
    shop_announce_channel_id: int = int(os.getenv("SHOP_ANNOUNCE_CHANNEL_ID", "0") or "0")
    casino_min_bet: int = int(os.getenv("CASINO_MIN_BET", "1") or "1")
    casino_max_bet: int = int(os.getenv("CASINO_MAX_BET", "1000") or "1000")
    lottery_ticket_price: int = int(os.getenv("LOTTERY_TICKET_PRICE", "10") or "10")
    lottery_interval_minutes: int = int(os.getenv("LOTTERY_INTERVAL_MINUTES", "60") or "60")
    lottery_announce_channel_id: int = int(os.getenv("LOTTERY_ANNOUNCE_CHANNEL_ID", "0") or "0")

