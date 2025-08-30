"""
bot/services/logging_service.py
Centralized logging service with Discord embeds for admin monitoring
Enhanced with comprehensive logging capabilities
"""

import discord
from discord import Embed, Color
from datetime import datetime
from typing import Optional, Dict, Any, List, Union
from enum import Enum
import asyncio
import logging
import traceback
import json

logger = logging.getLogger(__name__)

class LogLevel(Enum):
    """Log level colors and emojis"""
    INFO = (Color.blue(), "ℹ️")
    SUCCESS = (Color.green(), "✅")
    WARNING = (Color.orange(), "⚠️")
    ERROR = (Color.red(), "❌")
    CRITICAL = (Color.dark_red(), "🚨")
    AUTH = (Color.purple(), "🔒")
    SECURITY = (Color.dark_red(), "🛡️")
    PERFORMANCE = (Color.gold(), "⚡")
    DATABASE = (Color.teal(), "🗄️")
    SYSTEM = (Color.greyple(), "🔧")

class LogCategory(Enum):
    """Categories for different services"""
    AUTH = "Authentication"
    DATABASE = "Database"
    MODERATION = "Moderation"
    SYSTEM = "System"
    USER = "User Action"
    ERROR = "Error"
    AI = "AI Service"
    WEB = "Web Server"
    COMMAND = "Command"

class EmbedLogger:
    """Enhanced embed logger with comprehensive monitoring capabilities"""
    
    def __init__(self, bot: discord.Client, admin_channel_id: int):
        self.bot = bot
        self.admin_channel_id = int(admin_channel_id)
        self.admin_channel: Optional[discord.TextChannel | discord.Thread] = None
        self.pending_embeds: Dict[str, discord.Message] = {}
        self._setup_done: bool = False
        self._setup_attempted: bool = False
        self._retry_task: Optional[asyncio.Task] = None
        
        # Statistics tracking
        self.stats = {
            "logs_sent": 0,
            "logs_failed": 0,
            "logs_by_level": {level.name: 0 for level in LogLevel},
            "logs_by_service": {},
            "start_time": datetime.utcnow()
        }
        
        # Rate limiting to prevent spam
        self.rate_limit = {
            "messages": [],
            "max_per_minute": 30,
            "similar_message_cache": {}
        }

    async def _resolve_channel(self) -> Optional[discord.TextChannel | discord.Thread]:
        """Resolve the admin channel reliably via API with cache fallback."""
        try:
            chan = await self.bot.fetch_channel(self.admin_channel_id)
            if isinstance(chan, (discord.TextChannel, discord.Thread)):
                return chan
        except Exception:
            pass
        chan = self.bot.get_channel(self.admin_channel_id)
        if isinstance(chan, (discord.TextChannel, discord.Thread)):
            return chan
        return None

    async def setup(self) -> bool:
        """
        Initialize the logging channel.
        Safe to call multiple times; it will re-try if the channel is not yet resolvable.
        """
        self._setup_attempted = True
        self.admin_channel = await self._resolve_channel()

        if not self.admin_channel:
            logger.error(f"Admin log channel {self.admin_channel_id} not found (yet). Will retry once after ready.")
            if not self._retry_task:
                self._retry_task = asyncio.create_task(self._delayed_retry())
            return False

        self._setup_done = True
        await self.log_system_event(
            title="🚀 Enhanced Logging System Started",
            description="Comprehensive admin logging system initialized and ready",
            level=LogLevel.SUCCESS,
            fields=[
                ("Version", "3.0.0", True),
                ("Environment", "Production", True),
                ("Channel ID", str(self.admin_channel_id), True),
                ("Features", "Real-time monitoring, Error tracking, Performance metrics", False),
                ("Log Levels", f"{len(LogLevel)} levels available", True),
                ("Status", "🟢 Fully Operational", True),
            ],
        )
        return True

    async def _delayed_retry(self):
        """Retry channel resolution once after a short delay (post-ready)."""
        try:
            await self.bot.wait_until_ready()
            await asyncio.sleep(2)
            self.admin_channel = await self._resolve_channel()
            if self.admin_channel:
                self._setup_done = True
                logger.info(f"Admin log channel {self.admin_channel_id} resolved on retry.")
                await self.log_system_event(
                    title="🟢 Logger Reconnected",
                    description="Admin log channel resolved after retry",
                    level=LogLevel.SUCCESS,
                    fields=[
                        ("Channel", f"<#{self.admin_channel_id}>", True),
                        ("Retry Successful", "✅ Yes", True)
                    ]
                )
            else:
                logger.error(f"Admin log channel {self.admin_channel_id} still not found after retry.")
        except Exception as e:
            logger.exception(f"Logger delayed retry failed: {e}")

    def _should_rate_limit(self, content_hash: str) -> bool:
        """Check if message should be rate limited"""
        now = datetime.utcnow()
        
        # Clean old messages (older than 1 minute)
        self.rate_limit["messages"] = [
            msg_time for msg_time in self.rate_limit["messages"]
            if (now - msg_time).total_seconds() < 60
        ]
        
        # Check rate limit
        if len(self.rate_limit["messages"]) >= self.rate_limit["max_per_minute"]:
            return True
        
        # Check for similar messages (prevent spam)
        if content_hash in self.rate_limit["similar_message_cache"]:
            last_sent = self.rate_limit["similar_message_cache"][content_hash]
            if (now - last_sent).total_seconds() < 10:  # Same message within 10 seconds
                return True
        
        # Record this message
        self.rate_limit["messages"].append(now)
        self.rate_limit["similar_message_cache"][content_hash] = now
        
        return False

    async def _safe_send(self, embed: Embed, content_hash: str = None) -> Optional[discord.Message]:
        """
        Send embed if channel is ready and rate limiting allows.
        """
        if not self._setup_done:
            if self._setup_attempted and not self.admin_channel:
                self.admin_channel = await self._resolve_channel()
                if self.admin_channel:
                    self._setup_done = True

        if not self.admin_channel:
            return None
        
        # Rate limiting check
        if content_hash and self._should_rate_limit(content_hash):
            logger.debug("Rate limiting admin log message")
            return None
        
        try:
            message = await self.admin_channel.send(embed=embed)
            self.stats["logs_sent"] += 1
            return message
        except discord.HTTPException as e:
            if e.status == 429:  # Rate limited by Discord
                logger.warning("Discord rate limited admin logging")
            else:
                logger.debug(f"Failed to send admin embed: {e}")
            self.stats["logs_failed"] += 1
        except Exception as e:
            logger.debug(f"Failed to send admin embed: {e}")
            self.stats["logs_failed"] += 1
        
        return None

    def _create_base_embed(self, title: str, description: str, level: LogLevel) -> Embed:
        """Create base embed with consistent formatting"""
        color, emoji = level.value
        
        embed = Embed(
            title=f"{emoji} {title}",
            description=description[:2000] if description else None,  # Discord limit
            color=color,
            timestamp=datetime.utcnow(),
        )
        
        # Track statistics
        self.stats["logs_by_level"][level.name] += 1
        
        return embed

    def _add_fields_to_embed(self, embed: Embed, fields: Union[List[tuple], Dict[str, Any], None]):
        """Add fields to embed with proper formatting"""
        if not fields:
            return
        
        if isinstance(fields, dict):
            # Convert dict to list of tuples
            field_list = [(k, v, len(str(v)) < 50) for k, v in fields.items()]
        else:
            field_list = fields
        
        for field in field_list:
            if len(field) == 2:
                name, value = field
                inline = len(str(value)) < 50  # Auto-determine inline
            elif len(field) == 3:
                name, value, inline = field
            else:
                continue
            
            # Ensure field values are strings and within Discord limits
            name = str(name)[:256]
            value = str(value)[:1024] if value else "N/A"
            
            try:
                embed.add_field(name=name, value=value, inline=bool(inline))
                
                # Discord has a limit of 25 fields per embed
                if len(embed.fields) >= 25:
                    break
            except Exception as e:
                logger.debug(f"Failed to add field {name}: {e}")

    # --------------- Authentication Logging Methods ---------------

    async def log_auth_start(self, user_id: str, username: str) -> Optional[int]:
        """Log authentication start with pending status"""
        embed = self._create_base_embed(
            title="🔒 Authentication Started",
            description=f"User initiated VSB SSO authentication process",
            level=LogLevel.AUTH
        )
        
        self._add_fields_to_embed(embed, {
            "Discord User": f"<@{user_id}>",
            "Username": username,
            "User ID": f"`{user_id}`",
            "Status": "⏳ Processing...",
            "Provider": "VSB SSO",
            "Time": datetime.utcnow().strftime("%H:%M:%S UTC")
        })
        
        embed.set_footer(text="VSB SSO Authentication • Step 1/3")
        embed.set_thumbnail(url="https://cdn.discordapp.com/embed/avatars/0.png")

        message = await self._safe_send(embed, f"auth_start_{user_id}")
        if message:
            self.pending_embeds[user_id] = message
            return message.id
        return None

    async def log_auth_success(self, user_id: str, user_info: Dict[str, Any]):
        """Log successful authentication with user details"""
        message = self.pending_embeds.get(user_id)

        login = user_info.get("uid", "unknown")
        email = user_info.get("mail", "not provided")
        first_name = user_info.get("givenName", "")
        last_name = user_info.get("sn", "")
        groups = user_info.get("groups", [])
        affiliations = user_info.get("eduPersonAffiliation", [])

        is_teacher = any("employee" in str(g).lower() or "staff" in str(g).lower() or "faculty" in str(g).lower() 
                        for g in (groups + affiliations))
        role = "👨‍🏫 Teacher" if is_teacher else "🎓 Student"
        role_emoji = "👨‍🏫" if is_teacher else "🎓"

        embed = self._create_base_embed(
            title="✅ Authentication Successful",
            description=f"User successfully verified via VSB SSO and granted server access",
            level=LogLevel.SUCCESS
        )
        
        self._add_fields_to_embed(embed, {
            "Discord User": f"<@{user_id}>",
            "VSB Login": f"`{login}`",
            "Role Assigned": f"{role_emoji} {role.split(' ')[1]}",
            "Full Name": f"{first_name} {last_name}" if first_name and last_name else "Not provided",
            "Email": f"`{email}`" if email != "not provided" else "Not provided",
            "Status": "✅ Verified & Active"
        })

        if groups:
            groups_str = ", ".join(groups[:3])
            if len(groups) > 3:
                groups_str += f" (+{len(groups)-3} more)"
            embed.add_field(name="Groups", value=f"```{groups_str}```", inline=False)

        if affiliations:
            embed.add_field(name="Affiliations", value=", ".join(affiliations), inline=False)

        embed.set_footer(text=f"VSB SSO • Completed at {datetime.utcnow().strftime('%H:%M:%S UTC')}")
        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1/1/success.png")

        if message:
            try:
                await message.edit(embed=embed)
            except Exception:
                await self._safe_send(embed, f"auth_success_{user_id}")
            finally:
                self.pending_embeds.pop(user_id, None)
        else:
            await self._safe_send(embed, f"auth_success_{user_id}")

    async def log_auth_failure(self, user_id: str, reason: str, error_details: Optional[str] = None):
        """Log authentication failure with detailed error information"""
        message = self.pending_embeds.get(user_id)

        embed = self._create_base_embed(
            title="❌ Authentication Failed",
            description="VSB SSO authentication process failed",
            level=LogLevel.ERROR
        )
        
        self._add_fields_to_embed(embed, {
            "Discord User": f"<@{user_id}>",
            "User ID": f"`{user_id}`",
            "Status": "❌ Failed",
            "Failure Reason": f"```{reason}```",
            "Time": datetime.utcnow().strftime("%H:%M:%S UTC")
        })

        if error_details:
            # Truncate error details to prevent embed overflow
            truncated_details = error_details[:800] + "..." if len(error_details) > 800 else error_details
            embed.add_field(name="Technical Details", value=f"```{truncated_details}```", inline=False)

        embed.add_field(
            name="Suggested Actions",
            value="• User should try authentication again\n• Check VSB SSO service status\n• Verify network connectivity",
            inline=False,
        )
        
        embed.set_footer(text=f"VSB SSO • Failed at {datetime.utcnow().strftime('%H:%M:%S UTC')}")

        if message:
            try:
                await message.edit(embed=embed)
            except Exception:
                await self._safe_send(embed, f"auth_failure_{user_id}")
            finally:
                self.pending_embeds.pop(user_id, None)
        else:
            await self._safe_send(embed, f"auth_failure_{user_id}")

    # --------------- System & Service Logging Methods ---------------

    async def log_system_event(
        self,
        title: str,
        description: str,
        level: LogLevel = LogLevel.INFO,
        fields: Optional[Union[List[tuple], Dict[str, Any]]] = None,
    ):
        """Log system events with detailed information"""
        embed = self._create_base_embed(title, description, level)
        self._add_fields_to_embed(embed, fields)
        embed.set_footer(text="System Event Monitor")
        
        await self._safe_send(embed, f"system_{title.replace(' ', '_').lower()}")

    async def log_service_event(
        self,
        service_name: str,
        event_type: str,
        description: str,
        level: LogLevel = LogLevel.INFO,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log service-specific events"""
        embed = self._create_base_embed(
            title=f"[{service_name}] {event_type}",
            description=description,
            level=level
        )
        
        if details:
            self._add_fields_to_embed(embed, details)
        
        embed.set_footer(text=f"{service_name} Service Monitor")
        
        # Track service-specific statistics
        if service_name not in self.stats["logs_by_service"]:
            self.stats["logs_by_service"][service_name] = 0
        self.stats["logs_by_service"][service_name] += 1
        
        await self._safe_send(embed, f"service_{service_name}_{event_type}".lower().replace(' ', '_'))

    async def log_database_operation(self, operation: str, table: str, affected_rows: int = 0, details: Optional[str] = None):
        """Log database operations with performance metrics"""
        embed = self._create_base_embed(
            title="🗄️ Database Operation",
            description=f"Database operation executed: **{operation}**",
            level=LogLevel.DATABASE if hasattr(LogLevel, 'DATABASE') else LogLevel.INFO
        )
        
        self._add_fields_to_embed(embed, {
            "Operation": operation,
            "Table": f"`{table}`",
            "Affected Rows": str(affected_rows),
            "Timestamp": datetime.utcnow().strftime("%H:%M:%S UTC")
        })
        
        if details:
            # Safely truncate SQL details
            safe_details = details.replace(self.bot.config.db_password if hasattr(self.bot, 'config') else '', '[REDACTED]')
            truncated_details = safe_details[:500] + "..." if len(safe_details) > 500 else safe_details
            embed.add_field(name="Query Details", value=f"```sql\n{truncated_details}\n```", inline=False)
        
        embed.set_footer(text="Database Monitor")
        await self._safe_send(embed, f"db_{operation}_{table}".lower())

    async def log_error(self, service: str, error: Exception, context: Optional[str] = None):
        """Log errors with full context and debugging information"""
        embed = self._create_base_embed(
            title="🚨 Service Error",
            description=f"Error occurred in **{service}**",
            level=LogLevel.CRITICAL
        )
        
        error_type = type(error).__name__
        error_msg = str(error)[:1000]  # Limit error message length
        
        self._add_fields_to_embed(embed, {
            "Service": service,
            "Error Type": f"`{error_type}`",
            "Timestamp": datetime.utcnow().strftime("%H:%M:%S UTC"),
            "Error ID": f"`{hash(str(error)) % 10000:04d}`"  # Simple error ID for tracking
        })
        
        embed.add_field(name="Error Message", value=f"```python\n{error_msg}\n```", inline=False)
        
        if context:
            embed.add_field(name="Context", value=context[:500], inline=False)
        
        # Add traceback for debugging (truncated)
        tb = traceback.format_exc()
        if tb and tb != "NoneType: None\n":
            tb_short = tb[-800:]  # Last 800 chars of traceback
            embed.add_field(name="Traceback (tail)", value=f"```python\n{tb_short}\n```", inline=False)
        
        embed.add_field(
            name="Actions Taken",
            value="• Error logged for review\n• Service continues operation\n• Check logs for full details",
            inline=False
        )
        
        embed.set_footer(text="Error Monitor • Automatic incident tracking")
        await self._safe_send(embed, f"error_{service}_{error_type}".lower())

    # --------------- Moderation & Security Logging ---------------

    async def log_moderation_action(
        self, 
        moderator_id: str, 
        action: str, 
        target_id: str, 
        reason: Optional[str] = None,
        additional_info: Optional[Dict[str, Any]] = None
    ):
        """Log moderation actions with full audit trail"""
        embed = self._create_base_embed(
            title="⚖️ Moderation Action",
            description=f"Moderation action executed: **{action}**",
            level=LogLevel.WARNING
        )
        
        self._add_fields_to_embed(embed, {
            "Moderator": f"<@{moderator_id}>",
            "Target": f"<@{target_id}>",
            "Action": action,
            "Timestamp": datetime.utcnow().strftime("%H:%M:%S UTC")
        })
        
        if reason:
            embed.add_field(name="Reason", value=reason[:500], inline=False)
        
        if additional_info:
            self._add_fields_to_embed(embed, additional_info)
        
        embed.set_footer(text="Moderation Monitor • Audit Trail")
        await self._safe_send(embed, f"moderation_{action}_{target_id}".lower().replace(' ', '_'))

    async def log_security_event(
        self,
        event_type: str,
        description: str,
        severity: str = "medium",
        user_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log security-related events"""
        level_map = {
            "low": LogLevel.INFO,
            "medium": LogLevel.WARNING,
            "high": LogLevel.ERROR,
            "critical": LogLevel.CRITICAL
        }
        
        level = level_map.get(severity.lower(), LogLevel.WARNING)
        
        embed = self._create_base_embed(
            title=f"🛡️ Security Event - {event_type}",
            description=description,
            level=level
        )
        
        base_fields = {
            "Event Type": event_type,
            "Severity": severity.title(),
            "Timestamp": datetime.utcnow().strftime("%H:%M:%S UTC")
        }
        
        if user_id:
            base_fields["User Involved"] = f"<@{user_id}>"
        
        self._add_fields_to_embed(embed, base_fields)
        
        if details:
            self._add_fields_to_embed(embed, details)
        
        embed.set_footer(text="Security Monitor • Real-time threat detection")
        await self._safe_send(embed, f"security_{event_type}_{severity}".lower().replace(' ', '_'))

    # --------------- Performance & Monitoring ---------------

    async def log_performance_metric(
        self,
        operation: str,
        duration: float,
        success: bool = True,
        additional_metrics: Optional[Dict[str, Any]] = None
    ):
        """Log performance metrics for monitoring"""
        level = LogLevel.SUCCESS if success else LogLevel.WARNING
        
        embed = self._create_base_embed(
            title="⚡ Performance Metric",
            description=f"Operation performance recorded: **{operation}**",
            level=level
        )
        
        status = "✅ Success" if success else "⚠️ Issues detected"
        
        self._add_fields_to_embed(embed, {
            "Operation": operation,
            "Duration": f"{duration:.3f}s",
            "Status": status,
            "Timestamp": datetime.utcnow().strftime("%H:%M:%S UTC")
        })
        
        if additional_metrics:
            self._add_fields_to_embed(embed, additional_metrics)
        
        embed.set_footer(text="Performance Monitor • Real-time metrics")
        await self._safe_send(embed, f"perf_{operation}".lower().replace(' ', '_'))

    # --------------- Custom & Generic Logging ---------------

    async def log_custom(
        self,
        service: str,
        title: str,
        description: str,
        level: LogLevel = LogLevel.INFO,
        fields: Optional[Union[List[tuple], Dict[str, Any]]] = None,
        footer: Optional[str] = None,
    ):
        """Log custom events with flexible formatting"""
        embed = self._create_base_embed(
            title=f"[{service}] {title}",
            description=description,
            level=level
        )
        
        self._add_fields_to_embed(embed, fields)
        embed.set_footer(text=footer or f"{service} Service Monitor")
        
        # Track service statistics
        if service not in self.stats["logs_by_service"]:
            self.stats["logs_by_service"][service] = 0
        self.stats["logs_by_service"][service] += 1
        
        content_hash = f"custom_{service}_{title}".lower().replace(' ', '_')
        await self._safe_send(embed, content_hash)

    # --------------- Convenience Methods ---------------

    async def log_command(
        self,
        actor_id: int,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        succeeded: bool = True,
        error: Optional[Exception] = None,
        scope: Optional[str] = None,
        execution_time: Optional[float] = None
    ):
        """Log command execution with results and performance"""
        level = LogLevel.SUCCESS if succeeded else LogLevel.ERROR
        title = "Command Executed" if succeeded else "Command Failed"
        
        embed = self._create_base_embed(
            title=f"💻 {title}",
            description=f"<@{actor_id}> executed command **/{command}**",
            level=level
        )
        
        fields = {
            "Command": f"/{command}",
            "User": f"<@{actor_id}>",
            "Result": "✅ Success" if succeeded else "❌ Failed",
            "Timestamp": datetime.utcnow().strftime("%H:%M:%S UTC")
        }
        
        if scope:
            fields["Scope"] = scope
        
        if execution_time:
            fields["Execution Time"] = f"{execution_time:.3f}s"
        
        if params:
            param_str = ", ".join([f"{k}={v}" for k, v in params.items()])
            fields["Parameters"] = param_str[:500] + "..." if len(param_str) > 500 else param_str
        
        if error:
            fields["Error"] = str(error)[:300]
        
        self._add_fields_to_embed(embed, fields)
        embed.set_footer(text="Command Monitor • User action tracking")
        
        await self._safe_send(embed, f"command_{command}_{actor_id}")

    async def log_warning(self, title: str, description: str, fields: Optional[Union[List[tuple], Dict[str, Any]]] = None):
        """Log warning events"""
        await self.log_custom(
            service="System",
            title=title,
            description=description,
            level=LogLevel.WARNING,
            fields=fields
        )

    async def log_info(self, title: str, description: str, fields: Optional[Union[List[tuple], Dict[str, Any]]] = None):
        """Log informational events"""
        await self.log_custom(
            service="System",
            title=title,
            description=description,
            level=LogLevel.INFO,
            fields=fields
        )

    # --------------- Statistics & Health ---------------

    async def get_logging_stats(self) -> Dict[str, Any]:
        """Get comprehensive logging statistics"""
        uptime = (datetime.utcnow() - self.stats["start_time"]).total_seconds()
        
        return {
            "uptime_seconds": uptime,
            "uptime_formatted": f"{uptime//3600:.0f}h {(uptime%3600)//60:.0f}m {uptime%60:.0f}s",
            "total_logs_sent": self.stats["logs_sent"],
            "total_logs_failed": self.stats["logs_failed"],
            "success_rate": round((self.stats["logs_sent"] / max(1, self.stats["logs_sent"] + self.stats["logs_failed"])) * 100, 2),
            "logs_by_level": dict(self.stats["logs_by_level"]),
            "logs_by_service": dict(self.stats["logs_by_service"]),
            "rate_limit_status": {
                "recent_messages": len(self.rate_limit["messages"]),
                "max_per_minute": self.rate_limit["max_per_minute"],
                "cached_messages": len(self.rate_limit["similar_message_cache"])
            },
            "channel_status": {
                "channel_id": self.admin_channel_id,
                "setup_done": self._setup_done,
                "setup_attempted": self._setup_attempted,
                "channel_resolved": self.admin_channel is not None
            }
        }

    async def log_stats_summary(self):
        """Log current logging system statistics"""
        stats = await self.get_logging_stats()
        
        await self.log_custom(
            service="Logging System",
            title="Statistics Summary",
            description="Current logging system performance and usage statistics",
            level=LogLevel.INFO,
            fields={
                "Uptime": stats["uptime_formatted"],
                "Logs Sent": f"{stats['total_logs_sent']} (Success: {stats['success_rate']}%)",
                "Failed Logs": str(stats["total_logs_failed"]),
                "Most Active Level": max(stats["logs_by_level"], key=stats["logs_by_level"].get),
                "Services Tracked": str(len(stats["logs_by_service"])),
                "Channel Status": "✅ Connected" if stats["channel_status"]["channel_resolved"] else "❌ Disconnected"
            }
        )

    async def health_check(self) -> bool:
        """Check logging system health"""
        try:
            if not self.admin_channel:
                return False
            
            # Try to send a test message (deleted immediately)
            test_embed = Embed(
                title="Health Check",
                description="Logging system health verification",
                color=Color.green()
            )
            
            try:
                message = await self.admin_channel.send(embed=test_embed)
                await message.delete()
                return True
            except Exception:
                return False
                
        except Exception as e:
            logger.error(f"Logging health check failed: {e}")
            return False