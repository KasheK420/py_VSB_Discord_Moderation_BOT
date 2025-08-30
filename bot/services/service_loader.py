# bot/services/service_loader.py
import logging
from datetime import datetime

import discord

from bot.database.database_service import database_service
from bot.services.auth_service import AuthService
from bot.services.logging_service import EmbedLogger, LogLevel
from bot.services.onboarding_service import OnboardingService
from bot.services.smart_moderation_service import SmartModerationService
from bot.utils.ai_helper import init_ai_service
from bot.utils.webserver import OAuthWebServer

logger = logging.getLogger(__name__)

_onboarding = None
_moderation = None
_initialization_start = None


async def init_core_services(bot: discord.Client, config):
    """Initialize core services with comprehensive logging"""
    global _initialization_start
    _initialization_start = datetime.utcnow()

    logger.info("Starting core services initialization...")

    # Initialize database first
    try:
        logger.info("Initializing database service...")
        start_time = datetime.utcnow()
        await database_service.initialize()
        db_init_time = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Database service initialized in {db_init_time:.2f}s")
    except Exception as e:
        logger.error(f"Failed to initialize database service: {e}")
        raise

    # Create logger object but DO NOT require cache here.
    embed_logger = None
    if config.admin_log_channel_id and int(config.admin_log_channel_id) != 0:
        try:
            logger.info(f"Creating embed logger for channel {config.admin_log_channel_id}...")
            embed_logger = EmbedLogger(bot, int(config.admin_log_channel_id))
            # defer embed_logger.setup() to post-login stage where fetch_channel will succeed
            logger.info("Embed logger created (setup deferred to post-login)")
        except Exception as e:
            logger.warning(f"Failed to create embed logger: {e}")
    else:
        logger.info("Admin log channel not configured - running without embed logging")

    # Initialize authentication service
    try:
        logger.info("Initializing authentication service...")
        start_time = datetime.utcnow()
        auth = AuthService(bot, database_service.pool, embed_logger)
        await auth.setup()
        auth_init_time = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Authentication service initialized in {auth_init_time:.2f}s")
    except Exception as e:
        logger.error(f"Failed to initialize authentication service: {e}")
        if embed_logger:
            try:
                await embed_logger.log_error(
                    service="Service Loader",
                    error=e,
                    context="Authentication service initialization failed",
                )
            except:
                pass
        raise

    # Initialize web server
    try:
        logger.info("Initializing OAuth web server...")
        start_time = datetime.utcnow()
        web = OAuthWebServer(auth)
        await web.start()
        web_init_time = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"OAuth web server started in {web_init_time:.2f}s")
    except Exception as e:
        logger.error(f"Failed to start OAuth web server: {e}")
        if embed_logger:
            try:
                await embed_logger.log_error(
                    service="Service Loader",
                    error=e,
                    context="OAuth web server initialization failed",
                )
            except:
                pass
        raise

    # Initialize onboarding service
    try:
        logger.info("Initializing onboarding service...")
        global _onboarding
        _onboarding = OnboardingService(config)
        if embed_logger:
            _onboarding.set_logger(embed_logger)
        logger.info("Onboarding service initialized")
    except Exception as e:
        logger.error(f"Failed to initialize onboarding service: {e}")
        if embed_logger:
            try:
                await embed_logger.log_error(
                    service="Service Loader",
                    error=e,
                    context="Onboarding service initialization failed",
                )
            except:
                pass
        # Don't raise - onboarding is not critical

    # Ensure KB schema (extensions, tables, indexes) so Help-Center is ready
    # kb_schema_time = 0.0
    # try:
    #    from bot.database.queries.kb_queries import KBQueries

    #    logger.info("Ensuring KB schema (extensions, tables, indexes)...")
    #    t0 = datetime.utcnow()
    #    await KBQueries.ensure_schema(database_service.pool)
    #    kb_schema_time = (datetime.utcnow() - t0).total_seconds()
    #    logger.info(f"KB schema ready in {kb_schema_time:.2f}s")
    # except Exception as e:
    #    logger.error(f"Failed to ensure KB schema: {e}")
    #    if embed_logger:
    #        try:
    #            await embed_logger.log_error(
    #                service="Service Loader", error=e, context="KB schema bootstrap failed"
    #            )
    #        except:
    #            pass
    #    # not fatal

    # Log successful core services initialization
    total_init_time = (datetime.utcnow() - _initialization_start).total_seconds()
    logger.info(f"Core services initialization completed in {total_init_time:.2f}s")

    if embed_logger:
        try:
            await embed_logger.log_custom(
                service="Service Loader",
                title="Core Services Initialized",
                description="All core services started successfully",
                level=LogLevel.SUCCESS,
                fields={
                    "Database": f"✅ Ready ({db_init_time:.2f}s)",
                    "Authentication": f"✅ Ready ({auth_init_time:.2f}s)",
                    "Web Server": f"✅ Running ({web_init_time:.2f}s)",
                    "Onboarding": "✅ Ready",
                    # "KB Schema": f"{'✅ Ready' if kb_schema_time>0 else '⚠️ Skipped'}"
                    # + (f" ({kb_schema_time:.2f}s)" if kb_schema_time > 0 else ""),
                    "Embed Logger": "✅ Active",
                    "Total Init Time": f"{total_init_time:.2f}s",
                    "Status": "🟢 All systems operational",
                },
            )
        except Exception as e:
            logger.warning(f"Failed to log core services initialization: {e}")

    return embed_logger, auth, web


async def init_community_cogs(bot: discord.Client, embed_logger: EmbedLogger | None) -> float:
    """
    Adds community cogs:
      - WelcomeCog
      - HelpCenterCog
      - HallOfFameCog
      - HallOfShameCog
      - EconomyCog
      - GamblingCog
      - ShopCog
    """
    from datetime import datetime

    t0 = datetime.utcnow()
    try:
        # Ensure DB schemas
        from bot.database.queries.economy_queries import EconomyQueries
        from bot.database.queries.hof_queries import HOFQueries
        from bot.database.queries.kb_queries import KBQueries
        from bot.database.queries.shame_queries import ShameQueries
        from bot.database.queries.shop_queries import ShopQueries

        await KBQueries.ensure_schema(database_service.pool)
        await HOFQueries.ensure_schema(database_service.pool)
        await ShameQueries.ensure_schema(database_service.pool)
        await EconomyQueries.ensure_schema(database_service.pool)
        await ShopQueries.ensure_schema(database_service.pool)

        # Import and add cogs
        from bot.cogs.casino_cog import CasinoCog
        from bot.cogs.economy_cog import EconomyCog
        from bot.cogs.gambling_cog import GamblingCog
        from bot.cogs.hall_of_fame_cog import HallOfFameCog
        from bot.cogs.hall_of_shame_cog import HallOfShameCog

        # from bot.cogs.help_center_cog import HelpCenterCog
        from bot.cogs.shop_cog import ShopCog
        from bot.cogs.welcome_cog import WelcomeCog

        await bot.add_cog(WelcomeCog(bot))
        # await bot.add_cog(HelpCenterCog(bot))
        await bot.add_cog(HallOfFameCog(bot))
        await bot.add_cog(HallOfShameCog(bot))
        await bot.add_cog(EconomyCog(bot))
        await bot.add_cog(GamblingCog(bot))
        await bot.add_cog(ShopCog(bot))
        await bot.add_cog(CasinoCog(bot))

        dt = (datetime.utcnow() - t0).total_seconds()
        logger.info(f"Community cogs loaded in {dt:.2f}s")

        if embed_logger:
            gen_id = getattr(bot.config, "general_channel_id", 0) or getattr(
                bot.config, "welcome_channel_id", 0
            )
            forum_id = getattr(bot.config, "help_center_forum_channel_id", 0)
            fame_id = getattr(bot.config, "hall_of_fame_channel_id", 0)
            shame_id = getattr(bot.config, "hall_of_shame_channel_id", 0)
            gamble_id = getattr(bot.config, "gambling_channel_id", 0)
            shop_announce = getattr(bot.config, "shop_announce_channel_id", 0)
            await embed_logger.log_custom(
                service="Service Loader",
                title="Community Cogs Loaded",
                description="All community features are active",
                level=LogLevel.SUCCESS,
                fields={
                    "Welcome/Goodbye": f"<#{gen_id}>" if gen_id else "n/a",
                    "Help-Center Forum": f"<#{forum_id}>" if forum_id else "n/a",
                    "Hall of Fame": f"<#{fame_id}>" if fame_id else "n/a",
                    "Hall of Shame": f"<#{shame_id}>" if shame_id else "n/a",
                    "Gambling": f"<#{gamble_id}>" if gamble_id else "n/a",
                    "Shop announce": f"<#{shop_announce}>" if shop_announce else "n/a",
                    "XP/Economy": (
                        "enabled" if getattr(bot.config, "xp_enabled", True) else "disabled"
                    ),
                },
            )
        return dt
    except Exception as e:
        logger.error(f"Failed to load community cogs: {e}")
        if embed_logger:
            await embed_logger.log_error(
                service="Service Loader", error=e, context="Failed to load community cogs"
            )
        return 0.0


async def init_ai_and_moderation(bot: discord.Client, embed_logger: EmbedLogger | None):
    """Initialize AI and moderation services with logging, then community cogs"""
    logger.info("Starting AI and moderation services initialization...")
    start_time = datetime.utcnow()

    ai_init_time = 0.0
    mod_init_time = 0.0
    community_time = 0.0

    # Initialize AI service
    try:
        logger.info("Initializing AI service...")
        ai_start = datetime.utcnow()
        await init_ai_service(embed_logger)
        ai_init_time = (datetime.utcnow() - ai_start).total_seconds()
        logger.info(f"AI service initialized in {ai_init_time:.2f}s")
    except Exception as e:
        logger.error(f"Failed to initialize AI service: {e}")
        if embed_logger:
            try:
                await embed_logger.log_error(
                    service="Service Loader", error=e, context="AI service initialization failed"
                )
            except:
                pass
        # Don't raise - AI is not critical for basic bot operation

    # Initialize moderation service
    try:
        logger.info("Initializing smart moderation service...")
        mod_start = datetime.utcnow()
        global _moderation
        _moderation = SmartModerationService()
        await _moderation.setup(bot, embed_logger)
        mod_init_time = (datetime.utcnow() - mod_start).total_seconds()
        logger.info(f"Smart moderation service initialized in {mod_init_time:.2f}s")
    except Exception as e:
        logger.error(f"Failed to initialize moderation service: {e}")
        if embed_logger:
            try:
                await embed_logger.log_error(
                    service="Service Loader",
                    error=e,
                    context="Moderation service initialization failed",
                )
            except:
                pass
        # Don't raise - moderation is not critical for basic bot operation

    # Load community cogs (Welcome + Help-Center)
    try:
        community_time = await init_community_cogs(bot, embed_logger)
    except Exception as e:
        logger.warning(f"Community cogs load raised: {e}")
        community_time = 0.0

    # Log AI and moderation initialization
    total_ai_mod_time = (datetime.utcnow() - start_time).total_seconds()
    logger.info(f"AI and moderation services initialization completed in {total_ai_mod_time:.2f}s")

    if embed_logger:
        try:
            from bot.utils.ai_helper import get_ai_service

            ai_service = get_ai_service()
            ai_status = "✅ Ready" if ai_service and ai_service.groq_api_key else "⚠️ No API key"
            mod_status = (
                "✅ Ready" if _moderation and _moderation.config.get("enabled") else "⚠️ Disabled"
            )
            community_status = "✅ Loaded" if community_time > 0 else "⚠️ Not loaded"

            await embed_logger.log_custom(
                service="Service Loader",
                title="AI & Moderation Services Initialized",
                description="AI and moderation services startup completed",
                level=LogLevel.SUCCESS,
                fields={
                    "AI Service": f"{ai_status} ({ai_init_time:.2f}s)",
                    "Moderation Service": f"{mod_status} ({mod_init_time:.2f}s)",
                    "Community Cogs": f"{community_status} ({community_time:.2f}s)",
                    "AI Provider": "Groq API",
                    "Moderation Version": (
                        _moderation.config.get("version", "unknown") if _moderation else "N/A"
                    ),
                    "Total Init Time": f"{total_ai_mod_time:.2f}s",
                    "Status": "🟢 Enhanced services active",
                },
            )
        except Exception as e:
            logger.warning(f"Failed to log AI/moderation initialization: {e}")


def get_onboarding():
    """Get the onboarding service instance"""
    return _onboarding


def get_moderation():
    """Get the moderation service instance"""
    return _moderation


async def get_service_status() -> dict:
    """Get status of all services"""
    global _initialization_start

    status = {
        "initialization_time": None,
        "database": {"status": "unknown"},
        "authentication": {"status": "unknown"},
        "web_server": {"status": "unknown"},
        "onboarding": {"status": "unknown"},
        "ai_service": {"status": "unknown"},
        "moderation": {"status": "unknown"},
    }

    if _initialization_start:
        uptime = (datetime.utcnow() - _initialization_start).total_seconds()
        status["initialization_time"] = f"{uptime:.2f}s ago"
        status["uptime_seconds"] = uptime

    # Check database service
    try:
        if database_service.pool:
            health = await database_service.health_check()
            status["database"] = {
                "status": "healthy" if health else "unhealthy",
                "pool_size": (
                    database_service.pool._size
                    if hasattr(database_service.pool, "_size")
                    else "unknown"
                ),
            }
    except Exception as e:
        status["database"] = {"status": "error", "error": str(e)}

    # Check onboarding service
    if _onboarding:
        status["onboarding"] = {"status": "ready"}

    # Check AI service
    try:
        from bot.utils.ai_helper import get_ai_service

        ai_service = get_ai_service()
        if ai_service:
            usage_stats = await ai_service.get_usage_stats()
            status["ai_service"] = {
                "status": usage_stats.get("service_status", "unknown"),
                "requests_last_hour": usage_stats.get("requests_last_hour", 0),
                "available_models": usage_stats.get("available_models", 0),
            }
    except Exception as e:
        status["ai_service"] = {"status": "error", "error": str(e)}

    # Check moderation service
    if _moderation:
        try:
            mod_stats = _moderation.get_moderation_stats()
            status["moderation"] = {
                "status": "enabled" if mod_stats.get("enabled") else "disabled",
                "version": mod_stats.get("version", "unknown"),
                "ai_calls_today": mod_stats.get("ai_calls_today", 0),
                "users_warned": mod_stats.get("total_users_warned", 0),
            }
        except Exception as e:
            status["moderation"] = {"status": "error", "error": str(e)}

    return status


async def log_service_status(embed_logger: EmbedLogger):
    """Log current service status"""
    if not embed_logger:
        return

    try:
        status = await get_service_status()

        fields = {}
        for service_name, service_info in status.items():
            if service_name in ["initialization_time", "uptime_seconds"]:
                continue

            service_status = service_info.get("status", "unknown")
            if (
                service_status == "healthy"
                or service_status == "ready"
                or service_status == "enabled"
            ):
                status_emoji = "✅"
            elif service_status == "disabled":
                status_emoji = "⚠️"
            elif service_status == "error" or service_status == "unhealthy":
                status_emoji = "❌"
            else:
                status_emoji = "❓"

            fields[service_name.replace("_", " ").title()] = f"{status_emoji} {service_status}"

        if status.get("uptime_seconds"):
            uptime = status["uptime_seconds"]
            fields["Uptime"] = f"{uptime//3600:.0f}h {(uptime%3600)//60:.0f}m {uptime%60:.0f}s"

        await embed_logger.log_custom(
            service="Service Loader",
            title="Service Status Check",
            description="Current status of all bot services",
            level=LogLevel.INFO,
            fields=fields,
        )

    except Exception as e:
        logger.error(f"Failed to log service status: {e}")
        await embed_logger.log_error(
            service="Service Loader", error=e, context="Failed to generate service status report"
        )


async def shutdown_services(embed_logger: EmbedLogger | None = None):
    """Gracefully shutdown all services"""
    logger.info("Starting graceful service shutdown...")

    if embed_logger:
        await embed_logger.log_custom(
            service="Service Loader",
            title="Service Shutdown Initiated",
            description="Gracefully shutting down all bot services",
            level=LogLevel.WARNING,
            fields={"Status": "🔴 Shutting down..."},
        )

    shutdown_errors = []

    # Shutdown moderation service
    if _moderation:
        try:
            logger.info("Shutting down moderation service...")
            # Moderation service doesn't have explicit shutdown, just log
            logger.info("Moderation service stopped")
        except Exception as e:
            shutdown_errors.append(f"Moderation: {e}")
            logger.error(f"Error shutting down moderation service: {e}")

    # Shutdown database service
    try:
        logger.info("Shutting down database service...")
        await database_service.close()
        logger.info("Database service shutdown complete")
    except Exception as e:
        shutdown_errors.append(f"Database: {e}")
        logger.error(f"Error shutting down database service: {e}")

    if embed_logger and not shutdown_errors:
        await embed_logger.log_custom(
            service="Service Loader",
            title="Service Shutdown Complete",
            description="All services shutdown gracefully",
            level=LogLevel.SUCCESS,
            fields={"Status": "🔴 All services stopped"},
        )
    elif embed_logger and shutdown_errors:
        await embed_logger.log_custom(
            service="Service Loader",
            title="Service Shutdown with Errors",
            description="Some services encountered errors during shutdown",
            level=LogLevel.ERROR,
            fields={"Errors": "\n".join(shutdown_errors), "Status": "🔴 Shutdown with issues"},
        )

    logger.info(f"Service shutdown complete. Errors: {len(shutdown_errors)}")
    return len(shutdown_errors) == 0
