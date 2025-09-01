"""
bot/services/auth_service.py
Fixed CAS Authentication Service - handles duplicate users and state management
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Set

import aiohttp
import discord
import asyncpg

from bot.database.models.user import User
from bot.database.queries.user_queries import UserQueries
from bot.database.models.discord_profile import DiscordProfile
from bot.database.queries.discord_profile_queries import DiscordProfileQueries
from bot.database.queries.discord_stats_queries import DiscordStatsQueries
from bot.database.queries.verification_audit_queries import VerificationAuditQueries
from bot.database.queries.cas_attributes_history_queries import CASAttributesHistoryQueries
from bot.utils.config import Config
from bot.services.logging_service import EmbedLogger, LogLevel

logger = logging.getLogger(__name__)


def _safe_str(val: Optional[str]) -> str:
    return val if isinstance(val, str) else ""


def _account_age_days(dt: Optional[datetime]) -> Optional[float]:
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return round((datetime.now(timezone.utc) - dt).total_seconds() / 86400.0, 2)


def _derive_country_code(cas_attrs: Dict[str, Any], discord_locale: Optional[str]) -> Optional[str]:
    for key in ("c", "country", "schacCountryOfCitizenship", "schacHomeOrganizationCountry"):
        v = cas_attrs.get(key)
        if isinstance(v, str) and len(v) in (2, 3):
            return v.upper()
    if discord_locale and "-" in discord_locale:
        return discord_locale.split("-")[-1].upper()
    return None


def _first_ip_from_headers(headers: Optional[dict]) -> Optional[str]:
    if not headers:
        return None
    for key in ("X-Forwarded-For", "x-forwarded-for"):
        raw = headers.get(key)
        if raw:
            ip = raw.split(",")[0].strip()
            return ip
    for key in ("X-Real-IP", "x-real-ip"):
        raw = headers.get(key)
        if raw:
            return raw.strip()
    return None


class AuthService:
    def __init__(self, bot: discord.Client, db_pool, embed_logger: EmbedLogger):
        self.bot = bot
        self.db_pool = db_pool
        self.config = Config()
        self.user_queries = UserQueries(db_pool)
        self.embed_logger = embed_logger

        self.cas_server_url = "https://www.sso.vsb.cz"
        self.cas_login_url = f"{self.cas_server_url}/login"
        self.cas_validate_url = f"{self.cas_server_url}/p3/serviceValidate"
        self.cas_logout_url = f"{self.cas_server_url}/logout"
        self.service_url = "https://sso.vsb-discord.cz/callback"
        
        # State storage - don't pop until successful
        self.pending_auths: Dict[str, Dict[str, Any]] = {}
        
        self.used_tickets: Set[str] = set()

    async def setup(self):
        """Initialize service and register commands"""
        await self.register_button_handlers()

        if self.embed_logger:
            await self.embed_logger.log_system_event(
                title="Auth Service Started",
                description="CAS authentication service initialized successfully",
                level=LogLevel.SUCCESS,
                fields=[
                    ("CAS Server", self.cas_server_url, True),
                    ("Service URL", self.service_url, True),
                    ("Validation URL", self.cas_validate_url, True),
                    ("Status", "🟢 Ready", True),
                ],
            )

    async def register_button_handlers(self):
        """Register button interaction handlers"""
        @self.bot.event
        async def on_interaction(interaction: discord.Interaction):
            if interaction.type != discord.InteractionType.component:
                return
            if interaction.data.get("custom_id") == "auth_sso":
                await self.handle_auth_button(interaction)

    async def handle_auth_button(self, interaction: discord.Interaction):
        """Handle SSO authentication button click."""
        user_id = str(interaction.user.id)
        username = interaction.user.name

        # Check if already verified
        try:
            existing_user = await self.user_queries.get_user_by_id(user_id)
            if existing_user and existing_user.activity == 1:
                await interaction.response.send_message(
                    "Již jsi ověřený! / You are already verified!", ephemeral=True
                )
                if self.embed_logger:
                    await self.embed_logger.log_custom(
                        service="Authentication",
                        title="Repeated Verification Attempt",
                        description=f"User <@{user_id}> attempted verification but is already verified",
                        level=LogLevel.WARNING,
                        fields={
                            "User": f"<@{user_id}>",
                            "Username": username,
                            "Verified": "Yes",
                        },
                    )
                return
        except Exception as e:
            logger.warning(f"Error checking existing user: {e}")

        if self.embed_logger:
            await self.embed_logger.log_auth_start(user_id, username)

        # Collect Discord metadata
        acct_created = getattr(interaction.user, "created_at", None)
        discord_meta = {
            "id": user_id,
            "username": username,
            "global_name": getattr(interaction.user, "global_name", None),
            "discriminator": getattr(interaction.user, "discriminator", None),
            "account_created_at": acct_created.isoformat() if isinstance(acct_created, datetime) else None,
            "account_age_days_at_auth": _account_age_days(acct_created),
            "interaction_locale": getattr(interaction, "locale", None),
            "guild_locale": getattr(interaction, "guild_locale", None),
        }

        cas_login_url = self.generate_cas_login_url(user_id, extra_meta=discord_meta)

        view = discord.ui.View()
        link_button = discord.ui.Button(
            label="Otevřít VSB SSO / Open VSB SSO",
            style=discord.ButtonStyle.link,
            url=cas_login_url,
            emoji="🔐",
        )
        view.add_item(link_button)

        await interaction.response.send_message(
            "Klikni na tlačítko pro otevření VSB SSO přihlášení:\n"
            "Click the button to open VSB SSO login:",
            view=view,
            ephemeral=True,
        )

    def generate_cas_login_url(self, discord_user_id: str, extra_meta: Optional[Dict[str, Any]] = None) -> str:
        """Generate CAS login URL with service parameter & persist pending state."""
        state = secrets.token_urlsafe(32)

        self.pending_auths[state] = {
            "discord_user_id": discord_user_id,
            "timestamp": datetime.utcnow(),
            "ip_address": None,
            "discord_meta": extra_meta or {},
        }

        if self.embed_logger:
            asyncio.create_task(
                self.embed_logger.log_custom(
                    service="Authentication",
                    title="Auth URL Generated",
                    description="CAS login URL generated for user",
                    level=LogLevel.INFO,
                    fields={
                        "User": f"<@{discord_user_id}>",
                        "State Token": state[:8] + "…",
                        "CAS Server": self.cas_server_url,
                        "Service URL": self.service_url,
                        "Pending Auths": str(len(self.pending_auths)),
                    },
                )
            )

        service_url_with_state = f"{self.service_url}?state={state}"
        params = {"service": service_url_with_state}
        return f"{self.cas_login_url}?{urllib.parse.urlencode(params)}"

    async def process_cas_callback(
        self,
        ticket: str,
        state: str,
        client_ip: Optional[str] = None,
        request_headers: Optional[dict] = None,
    ) -> dict:
        """Process CAS callback - fixed to handle duplicates and preserve state"""
        
        # Check if ticket was already used
        if ticket in self.used_tickets:
            logger.warning(f"Ticket {ticket[:8]}... already used, rejecting")
            raise ValueError("Ticket already processed")
        
        # Mark ticket as used immediately
        self.used_tickets.add(ticket)
        
        # Clean up old tickets (keep only last 1000)
        if len(self.used_tickets) > 1000:
            self.used_tickets = set(list(self.used_tickets)[-500:])
        
        # Check state exists (don't pop yet!)
        if state not in self.pending_auths:
            if self.embed_logger:
                await self.embed_logger.log_auth_failure(
                    user_id="Unknown",
                    reason="Invalid state parameter",
                    error_details=f"State '{state[:8]}…' not found in pending authentications",
                )
            raise ValueError("Invalid state parameter")

        # Get auth info WITHOUT removing it
        auth_info = self.pending_auths.get(state)
        if not auth_info:
            raise ValueError("Invalid state parameter")
            
        discord_user_id = auth_info["discord_user_id"]
        pending_started = auth_info.get("timestamp")

        ip_from_headers = _first_ip_from_headers(request_headers)
        login_ip = ip_from_headers or client_ip

        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Authentication",
                title="CAS Callback Received",
                description="Processing CAS callback for user",
                level=LogLevel.INFO,
                fields={
                    "User": f"<@{discord_user_id}>",
                    "Ticket": ticket[:8] + "…",
                    "State": state[:8] + "…",
                    "Auth Age (s)": str((datetime.utcnow() - pending_started).total_seconds())
                    if pending_started else "unknown",
                    "Client IP": login_ip or "unknown",
                },
            )

        try:
            # Validate CAS ticket
            user_info = await self.validate_cas_ticket(ticket, state)
            
            # Save user with proper duplicate handling
            await self.verify_user(discord_user_id, user_info, auth_info.get("discord_meta") or {}, login_ip=login_ip)
            
            # Only remove state after successful processing
            self.pending_auths.pop(state, None)
            
            # Audit trail
            try:
                v_audit = VerificationAuditQueries(self.db_pool)
                await v_audit.insert(
                    discord_id=discord_user_id,
                    login=user_info["uid"],
                    cas_username=user_info["uid"],
                    state_plaintext=state,
                    ticket_plaintext=ticket,
                    result="success",
                    error_message=None,
                )
            except Exception as e:
                logger.warning(f"Failed to insert verification_audit: {e}")

            try:
                cas_hist = CASAttributesHistoryQueries(self.db_pool)
                await cas_hist.insert_snapshot(
                    discord_id=discord_user_id,
                    login=user_info["uid"],
                    attributes=user_info.get("attributes", {}),
                )
            except Exception as e:
                logger.warning(f"Failed to insert cas_attributes_history: {e}")

            try:
                stats_q = DiscordStatsQueries(self.db_pool)
                await stats_q.touch_seen(discord_user_id, last_login_ip=login_ip, increment_login=True)
            except Exception as e:
                logger.warning(f"Failed to update discord_user_stats: {e}")

            if self.embed_logger:
                await self.embed_logger.log_auth_success(discord_user_id, user_info)

            return {"discord_user_id": discord_user_id, "user_info": user_info}
            
        except Exception as e:
            # Log failure but keep state for retry
            logger.error(f"Auth processing failed: {e}")
            
            # Audit failure
            try:
                v_audit = VerificationAuditQueries(self.db_pool)
                await v_audit.insert(
                    discord_id=discord_user_id,
                    login="unknown",
                    cas_username="unknown",
                    state_plaintext=state,
                    ticket_plaintext=ticket,
                    result="failure",
                    error_message=str(e),
                )
            except:
                pass
                
            raise

    async def validate_cas_ticket(self, ticket: str, state: str) -> dict:
        """Validate CAS ticket and parse user info."""
        service_url_with_state = f"{self.service_url}?state={state}"
        params = {"ticket": ticket, "service": service_url_with_state}
        validate_url = f"{self.cas_validate_url}?{urllib.parse.urlencode(params)}"

        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Authentication",
                title="CAS Ticket Validation",
                description="Validating CAS ticket with CAS server",
                level=LogLevel.INFO,
                fields={
                    "Validate URL": self.cas_validate_url,
                    "Service (w/ state)": service_url_with_state,
                },
            )

        async with aiohttp.ClientSession() as session:
            async with session.get(validate_url, timeout=15) as resp:
                xml_response = await resp.text()

        try:
            root = ET.fromstring(xml_response)
            ns = {"cas": "http://www.yale.edu/tp/cas"}
            success = root.find("cas:authenticationSuccess", ns)
            if success is None:
                failure = root.find("cas:authenticationFailure", ns)
                code = failure.attrib.get("code") if failure is not None else "UNKNOWN"
                msg = (failure.text or "").strip() if failure is not None else "CAS authentication failed"
                raise Exception(f"{code}: {msg}")

            username = success.findtext("cas:user", default="", namespaces=ns)
            attributes = {}
            cas_attrs = success.find("cas:attributes", ns)
            if cas_attrs is not None:
                for child in cas_attrs:
                    tag = child.tag.split("}", 1)[-1]
                    attributes[tag] = (child.text or "").strip()

            if self.embed_logger:
                asyncio.create_task(
                    self.embed_logger.log_custom(
                        service="Authentication",
                        title="CAS Response Parsed",
                        description="CAS v3 attributes parsed",
                        level=LogLevel.SUCCESS,
                        fields={
                            "Username": username,
                            "Attributes Found": str(len(attributes)),
                            "Email": attributes.get("mail", "not provided")[:80],
                            "Affiliations": attributes.get("eduPersonAffiliation", "n/a")[:120],
                        },
                    )
                )

            return {
                "uid": username,
                "login": username,
                "attributes": attributes,
                "mail": attributes.get("mail", ""),
                "givenName": attributes.get("givenName", ""),
                "sn": attributes.get("sn", ""),
                "cn": attributes.get("cn", ""),
                "groups": attributes.get("groups", "").split(",") if attributes.get("groups") else [],
                "eduPersonAffiliation": (
                    attributes.get("eduPersonAffiliation", "").split(",")
                    if attributes.get("eduPersonAffiliation") else []
                ),
            }

        except ET.ParseError as e:
            logger.error(f"Failed to parse CAS XML response: {e}")
            raise

    async def verify_user(
        self,
        discord_user_id: str,
        user_info: dict,
        discord_meta_from_auth: Dict[str, Any],
        login_ip: Optional[str] = None,
    ):
        """Save user with proper duplicate handling and type conversion."""
        login = user_info.get("uid", "").lower()
        email = user_info.get("mail", "")
        first_name = user_info.get("givenName", "")
        last_name = user_info.get("sn", "")
        groups = user_info.get("groups", [])
        affiliations = user_info.get("eduPersonAffiliation", [])
        cas_attrs = user_info.get("attributes", {})
        user_type = self.determine_user_type(groups, affiliations)
        
        # Get member info
        member = None
        try:
            gid = int(self.config.guild_id)
            guild = self.bot.get_guild(gid)
            if guild:
                member = guild.get_member(int(discord_user_id))
        except Exception as e:
            logger.warning(f"Failed to get member {discord_user_id}: {e}")

        # Build Discord metadata
        discord_meta = dict(discord_meta_from_auth or {})
        if member:
            if not discord_meta.get("username"):
                discord_meta["username"] = member.name
            discord_meta.setdefault("global_name", getattr(member, "global_name", None))
            discord_meta.setdefault("discriminator", getattr(member, "discriminator", None))
            if "account_created_at" not in discord_meta and getattr(member, "created_at", None):
                discord_meta["account_created_at"] = member.created_at.isoformat()
                discord_meta["account_age_days_at_auth"] = _account_age_days(member.created_at)

        country_code = _derive_country_code(cas_attrs, discord_meta.get("interaction_locale"))
        if country_code:
            discord_meta["country_code"] = country_code

        merged_attrs = dict(cas_attrs)
        merged_attrs["discord_meta"] = discord_meta

        # Save to users table (uses VARCHAR for discord_id)
        async with self.db_pool.acquire() as conn:
            try:
                # For yearly re-verification: always update existing user by login
                await conn.execute("""
                    INSERT INTO users (id, login, activity, type, verification, real_name, attributes, verified_at)
                    VALUES ($1, $2, 1, $3, $4, $5, $6::jsonb, $7)
                    ON CONFLICT (login) DO UPDATE SET
                        id = EXCLUDED.id,
                        activity = 1,
                        type = EXCLUDED.type,
                        real_name = EXCLUDED.real_name,
                        attributes = EXCLUDED.attributes,
                        verified_at = EXCLUDED.verified_at
                """, 
                    discord_user_id,  # Keep as string for users table
                    login, 
                    user_type,
                    self.generate_verification_code(),
                    f"{first_name} {last_name} ({email})".strip(),
                    json.dumps(merged_attrs),
                    datetime.utcnow()
                )
                logger.info(f"User {discord_user_id} with login {login} saved/updated successfully")
                
            except asyncpg.UniqueViolationError as e:
                # Handle same Discord user with different VSB login
                if "users_pkey" in str(e):
                    await conn.execute("""
                        UPDATE users 
                        SET login = $1, activity = 1, type = $2,
                            real_name = $3, attributes = $4::jsonb, verified_at = $5
                        WHERE id = $6
                    """, 
                        login, 
                        user_type,
                        f"{first_name} {last_name} ({email})".strip(),
                        json.dumps(merged_attrs),
                        datetime.utcnow(), 
                        discord_user_id  # Keep as string
                    )
                    logger.info(f"Updated existing Discord user {discord_user_id} with new login {login}")
                else:
                    logger.error(f"Unexpected constraint violation: {e}")
                    raise

        # Assign Discord role (expects string)
        await self.assign_discord_role(discord_user_id, user_type)
        
        # Try to restore previous roles if re-verifying
        try:
            from bot.cogs.auth_management_cog import AuthManagementCog
            
            guild = self.bot.get_guild(int(self.config.guild_id))
            if guild:
                member = guild.get_member(int(discord_user_id))
                if member:
                    for cog in self.bot.cogs.values():
                        if isinstance(cog, AuthManagementCog):
                            if str(discord_user_id) in cog.role_backups:
                                await cog.restore_user_roles(member)
                                logger.info(f"Restored roles for {discord_user_id} after re-verification")
                                
                                if self.embed_logger:
                                    await self.embed_logger.log_custom(
                                        service="Authentication",
                                        title="Roles Restored",
                                        description="User's previous roles restored after re-verification",
                                        level=LogLevel.SUCCESS,
                                        fields={
                                            "User": f"<@{discord_user_id}>",
                                            "Login": user_info.get("uid", "unknown"),
                                            "Status": "✅ Roles restored",
                                        }
                                    )
                            break
        except Exception as e:
            logger.warning(f"Failed to check/restore roles for {discord_user_id}: {e}")
        
        # Update discord_profiles table (uses VARCHAR for discord_id)
        try:
            prof_q = DiscordProfileQueries(self.db_pool)
            profile = DiscordProfile(
                discord_id=discord_user_id,  # Keep as string
                username=discord_meta.get("username") or (member.name if member else "unknown"),
                global_name=discord_meta.get("global_name"),
                discriminator=discord_meta.get("discriminator"),
                locale=discord_meta.get("interaction_locale") or discord_meta.get("guild_locale"),
                country_code=discord_meta.get("country_code"),
                account_created_at=getattr(member, "created_at", None) if member else None,
                account_age_days=discord_meta.get("account_age_days_at_auth"),
                is_bot=bool(getattr(member, "bot", False)) if member else bool(discord_meta.get("is_bot", False)),
                avatar_hash=(getattr(getattr(member, "avatar", None), "key", None) if member else discord_meta.get("avatar_hash")),
            )
            await prof_q.upsert(profile)
        except Exception as e:
            logger.warning(f"Failed to upsert discord_profiles: {e}")
        
        # Update CAS attributes history
        try:
            cas_q = CASAttributesHistoryQueries(self.db_pool)
            cas_history = CASAttributesHistory(
                id=None,
                discord_id=discord_user_id,  # Keep as string
                login=login,
                cas_username=user_info.get("uid", "unknown"),
                cas_attributes=cas_attrs,
                auth_time=datetime.utcnow(),
                client_ip=login_ip,
            )
            await cas_q.insert(cas_history)
        except Exception as e:
            logger.warning(f"Failed to insert cas_attributes_history: {e}")
        
        # Update discord_user_stats (uses VARCHAR for discord_id)
        try:
            stats_q = DiscordStatsQueries(self.db_pool)
            await stats_q.touch_seen(
                discord_user_id,  # Keep as string
                last_login_ip=login_ip, 
                increment_login=True
            )
        except Exception as e:
            logger.warning(f"Failed to update discord_user_stats: {e}")
        
        # Initialize economy stats if needed (uses BIGINT - need conversion!)
        try:
            from bot.database.queries.economy_queries import EconomyQueries
            user_id_int = int(discord_user_id)  # Convert to int for economy tables
            
            # Ensure user has economy stats row
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO xp_stats(user_id, daily_xp, daily_xp_date) 
                    VALUES($1, 0, CURRENT_DATE)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    user_id_int  # Use int for economy tables
                )
                logger.debug(f"Ensured economy stats for user {user_id_int}")
        except ValueError:
            logger.error(f"Invalid discord_user_id for economy conversion: {discord_user_id}")
        except Exception as e:
            logger.warning(f"Failed to initialize economy stats: {e}")
        
        # Log successful authentication
        if self.embed_logger:
            await self.embed_logger.log_auth_success(discord_user_id, user_info)
        
        return {
            "discord_user_id": discord_user_id,
            "user_info": user_info
        }

    def determine_user_type(self, groups: list, affiliations: list) -> int:
        """Determine if user is student (0) or teacher (2)."""
        teacher_affiliations = ["employee", "faculty", "staff", "teacher"]
        for affiliation in affiliations:
            if any(ta in affiliation.lower() for ta in teacher_affiliations):
                if self.embed_logger:
                    asyncio.create_task(
                        self.embed_logger.log_custom(
                            service="Authentication",
                            title="User Type Determined",
                            description="User classified as teacher based on affiliations",
                            level=LogLevel.INFO,
                            fields={"Type": "Teacher", "Reason": f"Affiliation: {affiliation}"},
                        )
                    )
                return 2

        teacher_groups = ["employees", "staff", "faculty", "teachers"]
        for group in groups:
            if any(tg in group.lower() for tg in teacher_groups):
                if self.embed_logger:
                    asyncio.create_task(
                        self.embed_logger.log_custom(
                            service="Authentication",
                            title="User Type Determined",
                            description="User classified as teacher based on groups",
                            level=LogLevel.INFO,
                            fields={"Type": "Teacher", "Reason": f"Group: {group}"},
                        )
                    )
                return 2

        if self.embed_logger:
            asyncio.create_task(
                self.embed_logger.log_custom(
                    service="Authentication",
                    title="User Type Determined",
                    description="User classified as student (default)",
                    level=LogLevel.INFO,
                    fields={"Type": "Student", "Reason": "No teacher indicators found"},
                )
            )
        return 0

    async def assign_discord_role(self, discord_user_id: str, user_type: int):
        """Assign appropriate Discord role to user."""
        try:
            gid = int(self.config.guild_id)
        except:
            gid = self.config.guild_id

        guild = self.bot.get_guild(gid)
        if not guild:
            logger.error(f"Guild {self.config.guild_id} not found")
            return

        member = guild.get_member(int(discord_user_id))
        if not member:
            logger.error(f"Member {discord_user_id} not found in guild")
            return

        role_id = self.config.teacher_role_id if user_type == 2 else self.config.student_role_id
        role_name = "Teacher" if user_type == 2 else "Student"

        role = guild.get_role(role_id)
        if not role:
            logger.error(f"Role {role_id} not found")
            return

        try:
            await member.add_roles(role)
            logger.info(f"Added role {role.name} to user {discord_user_id}")
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Role Management",
                    title="Role Assigned",
                    description="Successfully assigned role to verified user",
                    level=LogLevel.SUCCESS,
                    fields={
                        "User": f"<@{discord_user_id}>",
                        "Role": role.name,
                        "Type": role_name,
                        "Role ID": str(role_id),
                        "Guild": guild.name,
                    },
                )
        except discord.Forbidden:
            logger.error(f"Missing permission to assign role")
        except Exception as e:
            logger.error(f"Failed to assign role: {e}")

    def generate_verification_code(self) -> str:
        """Generate random verification code."""
        return secrets.token_urlsafe(8)[:8]

    async def cleanup_expired_auths(self):
        """Clean up expired authentication attempts (older than 1 hour)."""
        cutoff_time = datetime.utcnow() - timedelta(hours=1)
        expired_states = [s for s, info in self.pending_auths.items() if info["timestamp"] < cutoff_time]
        for s in expired_states:
            del self.pending_auths[s]

        if expired_states and self.embed_logger:
            await self.embed_logger.log_custom(
                service="Authentication",
                title="Expired Auth Cleanup",
                description="Cleaned up expired authentication attempts",
                level=LogLevel.INFO,
                fields={
                    "Expired Sessions": str(len(expired_states)),
                    "Active Sessions": str(len(self.pending_auths)),
                    "Cutoff Age": "1 hour",
                },
            )