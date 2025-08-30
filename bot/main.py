"""
bot/main.py
Slim bootstrap: init services, load cogs, sync slash commands (guild-first)
Enhanced with comprehensive logging
"""
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from bot.utils.logging_config import setup_logging
from bot.utils.config import Config
from bot.database.database_service import database_service
from bot.services.logging_service import EmbedLogger, LogLevel
from bot.services.auth_service import AuthService
from bot.utils.webserver import OAuthWebServer
from bot.cogs.ai import AICog

from bot.services.service_loader import (
    init_core_services,
    init_ai_and_moderation,
    get_onboarding,
)

# Cog imports kept at bottom to avoid circular imports
setup_logging()
logger = logging.getLogger(__name__)


class VSBBot(commands.Bot):
    def __init__(self, config: Config):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.message_content = True  # moderation needs this
        super().__init__(command_prefix=config.command_prefix, intents=intents)
        self.config = config
        self.db_service = database_service
        self.embed_logger: EmbedLogger | None = None
        self.auth_service: AuthService | None = None
        self.web_server: OAuthWebServer | None = None
        self.startup_time = None

    async def setup_hook(self):
        """Called when the bot is starting up"""
        logger.info("Bot setup hook called - initializing services...")
        
        # Record startup time
        from datetime import datetime
        self.startup_time = datetime.utcnow()
        
        # Init core infra (DB, auth, web). Do NOT touch guild/channel here.
        try:
            from bot.services.service_loader import init_core_services, init_ai_and_moderation, get_onboarding
            self.embed_logger, self.auth_service, self.web_server = await init_core_services(self, self.config)
            await init_ai_and_moderation(self, self.embed_logger)
            
            logger.info("Core services initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize core services: {e}")
            raise

        # Schedule post-login init that runs AFTER we're actually connected
        asyncio.create_task(self._post_login_init())

    async def _post_login_init(self):
        """Post-login initialization after bot is connected"""
        await self.wait_until_ready()

        # --- Ensure the embed logger is actually set up (idempotent) ---
        if self.embed_logger:
            try:
                # setup() safely retries fetch_channel and marks _setup_done
                await self.embed_logger.setup()
            except Exception as e:
                logging.getLogger(__name__).warning(f"Embed logger setup failed: {e}")

        # Log that we're starting post-login tasks
        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Bot Startup",
                title="Post-Login Initialization",
                description="Bot is ready, starting post-login setup",
                level=LogLevel.INFO,
                fields={
                    "Bot User": f"{self.user.name}#{self.user.discriminator}",
                    "Bot ID": str(self.user.id),
                    "Guild Count": str(len(self.guilds)),
                    "Cached Users": str(len(self.users))
                }
            )

        # --- Validate configured entities (channels, roles, users) ---
        try:
            await self._validate_config_entities()
        except Exception as e:
            logging.getLogger(__name__).warning(f"Config entity validation failed: {e}")
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Bot Startup",
                    error=e,
                    context="Config entity validation failed"
                )

        # Load cogs (slash-only) here to avoid cache issues
        try:
            from bot.cogs.admin import AdminCog
            from bot.cogs.verification import VerificationCog
            from bot.services.service_loader import get_onboarding

            # If logger was not created earlier, try once more here
            if self.embed_logger is None and self.config.admin_log_channel_id and int(self.config.admin_log_channel_id) != 0:
                try:
                    from bot.services.logging_service import EmbedLogger
                    self.embed_logger = EmbedLogger(self, int(self.config.admin_log_channel_id))
                    await self.embed_logger.setup()
                    await self.embed_logger.log_custom(
                        service="Bot Startup",
                        title="Logger Initialized (Retry)",
                        description="Admin logger initialized after bot ready",
                        level=LogLevel.SUCCESS,
                        fields={
                            "Channel ID": str(self.config.admin_log_channel_id),
                            "Setup Method": "Post-ready initialization"
                        }
                    )
                except Exception as e:
                    logging.getLogger(__name__).warning(
                        f"Admin log channel {self.config.admin_log_channel_id} not available: {e}"
                    )

            await self.add_cog(AdminCog(self))
            await self.add_cog(VerificationCog(self, get_onboarding()))
            await self.add_cog(AICog(self))

            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Bot Startup",
                    title="Cogs Loaded",
                    description="All bot cogs loaded successfully",
                    level=LogLevel.SUCCESS,
                    fields={
                        "Cogs Loaded": "AdminCog, VerificationCog, AICog",
                        "Total Cogs": str(len(self.cogs)),
                        "Status": "All loaded"
                    }
                )

            logger.info(f"Loaded {len(self.cogs)} cogs successfully")

        except Exception as e:
            logger.error(f"Failed to load cogs: {e}")
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Bot Startup",
                    error=e,
                    context="Failed to load bot cogs during post-login initialization"
                )

        # Guild-first slash sync (cache-independent)
        await self._sync_app_commands()

        # Ensure welcome message now that we're connected
        try:
            onboarding = get_onboarding()
            if onboarding:
                await onboarding.ensure_verification_message(self)
                if self.embed_logger:
                    await self.embed_logger.log_custom(
                        service="Bot Startup",
                        title="Welcome Message Ensured",
                        description="Verification message posted in welcome channel",
                        level=LogLevel.SUCCESS,
                        fields={
                            "Channel": f"<#{self.config.welcome_channel_id}>",
                            "Status": "Ready for verification"
                        }
                    )
        except Exception as e:
            logger.error(f"Failed to ensure welcome message: {e}")
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Bot Startup",
                    error=e,
                    context="Failed to ensure welcome message in post-login initialization"
                )

    async def _validate_config_entities(self):
        """
        Validate all configured IDs (channels, roles, users) exist and are accessible.
        Posts a summary embed to the admin log channel if available.
        """
        results = {
            "channels_ok": [],
            "channels_fail": [],
            "roles_ok": [],
            "roles_fail": [],
            "users_ok": [],
            "users_fail": [],
            "guild_ok": None,
            "guild_fail": None,
        }

        # Resolve guild
        guild = self.get_guild(int(self.config.guild_id)) if self.config.guild_id else None
        if guild:
            results["guild_ok"] = f"{guild.name} ({guild.id})"
        else:
            results["guild_fail"] = str(self.config.guild_id)

        # Helper: safely fetch a channel
        async def _get_channel(cid: int):
            try:
                ch = await self.fetch_channel(cid)
            except Exception:
                ch = self.get_channel(cid)
            return ch if isinstance(ch, (discord.TextChannel, discord.Thread, discord.VoiceChannel, discord.CategoryChannel)) else None

        # Collect candidate fields from Config by suffix
        cfg = self.config
        id_fields = []
        for name, value in vars(cfg).items():
            if not value:
                continue
            if not isinstance(value, (int, str)):
                continue
            try:
                ivalue = int(value)
            except Exception:
                continue

            lname = name.lower()
            if lname.endswith(("_channel_id", "_role_id", "_user_id")):
                id_fields.append((lname, ivalue))

        # Validate channels
        for name, cid in [f for f in id_fields if f[0].endswith("_channel_id")]:
            ch = await _get_channel(cid)
            if ch:
                results["channels_ok"].append(f"{name} <#{cid}>")
            else:
                results["channels_fail"].append(f"{name} {cid}")

        # Validate roles (need guild)
        for name, rid in [f for f in id_fields if f[0].endswith("_role_id")]:
            if guild:
                role = guild.get_role(rid)
                if role:
                    results["roles_ok"].append(f"{name} @{role.name} ({rid})")
                else:
                    results["roles_fail"].append(f"{name} {rid}")
            else:
                results["roles_fail"].append(f"{name} {rid} (no guild)")

        # Validate users
        for name, uid in [f for f in id_fields if f[0].endswith("_user_id")]:
            user = self.get_user(uid)
            if not user:
                try:
                    user = await self.fetch_user(uid)
                except Exception:
                    user = None
            if user:
                results["users_ok"].append(f"{name} {user} ({uid})")
            else:
                results["users_fail"].append(f"{name} {uid}")

        # Log results
        if self.embed_logger:
            fields = {}

            if results["guild_ok"] or results["guild_fail"]:
                fields["Guild"] = results["guild_ok"] or f"Missing {results['guild_fail']}"

            if results["channels_ok"]:
                fields["Channels OK"] = "\n".join(results["channels_ok"][:10]) + \
                    (" ..." if len(results["channels_ok"]) > 10 else "")
            if results["channels_fail"]:
                fields["Channels Missing"] = "\n".join(results["channels_fail"])

            if results["roles_ok"]:
                fields["Roles OK"] = "\n".join(results["roles_ok"][:10]) + \
                    (" ..." if len(results["roles_ok"]) > 10 else "")
            if results["roles_fail"]:
                fields["Roles Missing"] = "\n".join(results["roles_fail"])

            if results["users_ok"]:
                fields["Users OK"] = "\n".join(results["users_ok"][:10]) + \
                    (" ..." if len(results["users_ok"]) > 10 else "")
            if results["users_fail"]:
                fields["Users Missing"] = "\n".join(results["users_fail"])

            await self.embed_logger.log_custom(
                service="Config Validator",
                title="Configuration Entities Verified",
                description="Checked channels, roles, users configured in environment",
                level=LogLevel.SUCCESS if not (results["channels_fail"] or results["roles_fail"] or results["users_fail"] or results["guild_fail"]) else LogLevel.WARNING,
                fields=fields
            )

        # Also print to console for visibility
        logger.info(f"Config validation: {results}")

    async def _sync_app_commands(self):
        """Sync application commands"""
        try:
            # Guild sync first (fast)
            gobj = discord.Object(id=self.config.guild_id)
            synced_guild = await self.tree.sync(guild=gobj)
            logger.info(f"Synced {len(synced_guild)} guild slash command(s) to {self.config.guild_id}")
            
            # Global sync (slower, up to 1 hour propagation)
            synced_global = await self.tree.sync()
            logger.info(f"Synced {len(synced_global)} global slash command(s)")
            
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Bot Startup",
                    title="Commands Synced",
                    description="Guild and global slash commands registered",
                    level=LogLevel.SUCCESS,
                    fields={
                        "Guild ID": str(self.config.guild_id),
                        "Guild Commands": str(len(synced_guild)),
                        "Global Commands": str(len(synced_global)),
                        "Guild Sync": "✅ Immediate",
                        "Global Sync": "⏳ Up to 1 hour propagation"
                    }
                )
        except Exception as e:
            logger.exception("Slash command sync failed")
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Bot Startup", 
                    error=e, 
                    context="Slash command sync failed during startup"
                )

    async def on_ready(self):
        """Called when bot is ready"""
        startup_duration = None
        if self.startup_time:
            from datetime import datetime
            startup_duration = (datetime.utcnow() - self.startup_time).total_seconds()
        
        logger.info(f"Logged in as {self.user} ({self.user.id})")
        
        # Set bot presence
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="for verification requests")
        )
        
        if self.embed_logger:
            guild_info = []
            for guild in self.guilds:
                member_count = guild.member_count or len([m for m in guild.members if not m.bot])
                guild_info.append(f"{guild.name} ({member_count} members)")
            
            await self.embed_logger.log_custom(
                service="Bot Status",
                title="🚀 Bot Ready",
                description=f"VSB Discord Bot is now online and ready to serve!",
                level=LogLevel.SUCCESS,
                fields={
                    "Bot": f"{self.user.name}#{self.user.discriminator}",
                    "Bot ID": str(self.user.id),
                    "Startup Time": f"{startup_duration:.2f}s" if startup_duration else "Unknown",
                    "Guilds": str(len(self.guilds)),
                    "Guild Details": "\n".join(guild_info[:3]) + ("..." if len(guild_info) > 3 else ""),
                    "Cached Users": str(len(self.users)),
                    "Cogs Loaded": str(len(self.cogs)),
                    "Activity": "Watching for verification requests",
                    "Status": "🟢 Online and Ready"
                }
            )

    async def on_guild_join(self, guild: discord.Guild):
        """Called when bot joins a new guild"""
        logger.info(f"Joined guild: {guild.name} ({guild.id}) with {guild.member_count} members")
        
        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Bot Status",
                title="Guild Joined",
                description=f"Bot joined a new Discord server",
                level=LogLevel.INFO,
                fields={
                    "Guild": guild.name,
                    "Guild ID": str(guild.id),
                    "Members": str(guild.member_count or len(guild.members)),
                    "Owner": f"{guild.owner.name}#{guild.owner.discriminator}" if guild.owner else "Unknown",
                    "Created": guild.created_at.strftime("%Y-%m-%d"),
                    "Features": ", ".join(guild.features[:5]) if guild.features else "None"
                }
            )

    async def on_guild_remove(self, guild: discord.Guild):
        """Called when bot is removed from a guild"""
        logger.info(f"Left guild: {guild.name} ({guild.id})")
        
        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Bot Status",
                title="Guild Left",
                description=f"Bot was removed from a Discord server",
                level=LogLevel.WARNING,
                fields={
                    "Guild": guild.name,
                    "Guild ID": str(guild.id),
                    "Members": str(guild.member_count or len(guild.members)),
                    "Reason": "Removed/banned from server"
                }
            )

    async def on_error(self, event: str, *args, **kwargs):
        """Global error handler"""
        logger.exception(f"Error in event {event}")
        
        if self.embed_logger:
            import traceback
            error_info = traceback.format_exc()
            await self.embed_logger.log_error(
                service="Bot Core",
                error=Exception(f"Event error: {event}"),
                context=f"Global error in event {event} - Args: {len(args)}, Kwargs: {len(kwargs)}"
            )

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Handle command errors"""
        logger.error(f"Command error in {ctx.command}: {error}")
        
        if self.embed_logger:
            await self.embed_logger.log_error(
                service="Bot Commands",
                error=error,
                context=f"Command error - Command: {ctx.command}, User: {ctx.author.id}, Guild: {ctx.guild.id if ctx.guild else 'DM'}"
            )

    async def close(self):
        """Clean shutdown"""
        logger.info("Bot shutting down...")
        
        if self.embed_logger:
            uptime = None
            if self.startup_time:
                from datetime import datetime
                uptime = (datetime.utcnow() - self.startup_time).total_seconds()
            
            await self.embed_logger.log_custom(
                service="Bot Status",
                title="🔴 Bot Shutting Down",
                description="VSB Discord Bot is shutting down",
                level=LogLevel.WARNING,
                fields={
                    "Bot": f"{self.user.name}#{self.user.discriminator}" if self.user else "Unknown",
                    "Uptime": f"{uptime:.2f}s ({uptime//3600:.0f}h {(uptime%3600)//60:.0f}m)" if uptime else "Unknown",
                    "Guilds Served": str(len(self.guilds)),
                    "Reason": "Graceful shutdown",
                    "Status": "🔴 Offline"
                }
            )
        
        # Close services
        if self.web_server:
            try:
                await self.web_server.stop()
            except Exception as e:
                logger.error(f"Error stopping web server: {e}")
        
        try:
            await self.db_service.close()
        except Exception as e:
            logger.error(f"Error closing database: {e}")
        
        await super().close()


async def main():
    """Main entry point"""
    config = Config()
    
    # Validate critical configuration
    missing_config = []
    if not config.bot_token:
        missing_config.append("DISCORD_BOT_TOKEN")
    if not config.db_password:
        missing_config.append("DB_PASSWORD")
    
    if missing_config:
        logger.error(f"Missing critical configuration: {', '.join(missing_config)}")
        return

    logger.info("=" * 60)
    logger.info("Starting VSB Discord Bot...")
    logger.info(f"Database: {config.db_host}:{config.db_port}/{config.db_name}")
    logger.info(f"Guild ID: {config.guild_id}")
    logger.info(f"Admin Log Channel: {config.admin_log_channel_id}")
    logger.info(f"Welcome Channel: {config.welcome_channel_id}")
    logger.info("=" * 60)

    bot = VSBBot(config)
    
    try:
        await bot.start(config.bot_token)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt - shutting down gracefully...")
    except Exception as e:
        logger.error(f"Bot crashed with error: {e}")
        logger.exception("Bot crash traceback:")
    finally:
        if not bot.is_closed():
            await bot.close()
        logger.info("Bot shutdown complete")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested via keyboard interrupt")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        logger.exception("Fatal error traceback:")
    finally:
        logger.info("Application terminated")