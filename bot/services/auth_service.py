"""
bot/services/auth_service.py
CAS Authentication Service for VSB SSO with comprehensive logging

Key features:
- Unified state handling (state generated only here).
- CAS v3 ticket validation (/p3/serviceValidate).
- Saves user in `users` table (existing queries).
- Writes Discord metadata to `attributes.discord_meta`.
- Assigns Discord role based on inferred user type.
- NEW: Upserts discord_profiles, touches discord_user_stats (with IP),
       inserts verification_audit (sha256 state/ticket), snapshots cas_attributes_history.

Optional args in process_cas_callback() allow webserver to pass client_ip + headers.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import aiohttp
import discord

# Core models/queries you already have
from bot.database.models.user import User
from bot.database.queries.user_queries import UserQueries

# NEW models/queries for the extra tables
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
    # Prefer CAS attributes if available
    for key in ("c", "country", "schacCountryOfCitizenship", "schacHomeOrganizationCountry"):
        v = cas_attrs.get(key)
        if isinstance(v, str) and len(v) in (2, 3):
            return v.upper()
    # Fallback: from Discord locale (e.g., "cs-CZ" -> "CZ")
    if discord_locale and "-" in discord_locale:
        return discord_locale.split("-")[-1].upper()
    return None


def _first_ip_from_headers(headers: Optional[dict]) -> Optional[str]:
    if not headers:
        return None
    # Try standard reverse-proxy headers
    for key in ("X-Forwarded-For", "x-forwarded-for"):
        raw = headers.get(key)
        if raw:
            # X-Forwarded-For can be "client, proxy1, proxy2"
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

        # CAS configuration
        self.cas_server_url = "https://www.sso.vsb.cz"
        self.cas_login_url = f"{self.cas_server_url}/login"
        self.cas_validate_url = f"{self.cas_server_url}/p3/serviceValidate"
        self.cas_logout_url = f"{self.cas_server_url}/logout"

        # Service URL (where CAS redirects back)
        # IMPORTANT: must match the public HTTPS callback behind your reverse proxy
        self.service_url = "https://sso.vsb-discord.cz/callback"

        # Temporary state storage for tracking authentication attempts
        # state -> dict(discord_user_id, timestamp, ip_address, discord_meta)
        self.pending_auths: Dict[str, Dict[str, Any]] = {}

    # ---------------------------
    # Setup & interaction buttons
    # ---------------------------

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

        # Prevent reverify if already verified
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
                await self.embed_logger.log_error(
                    service="Authentication",
                    error=e,
                    context=f"Database check failed for user {user_id} during auth button click",
                )
            # continue even if the check fails

        # Log start
        if self.embed_logger:
            await self.embed_logger.log_auth_start(user_id, username)

        # Collect Discord meta
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

        # Generate CAS login URL (also stores pending_auths with discord_meta)
        cas_login_url = self.generate_cas_login_url(user_id, extra_meta=discord_meta)

        # Push link button to user
        view = discord.ui.View()
        link_button = discord.ui.Button(
            label="Otevřít VSB SSO / Open VSB SSO",
            style=discord.ButtonStyle.link,
            url=cas_login_url,
            emoji="🔒",
        )
        view.add_item(link_button)

        await interaction.response.send_message(
            "Klikni na tlačítko pro otevření VSB SSO přihlášení:\n"
            "Click the button to open VSB SSO login:",
            view=view,
            ephemeral=True,
        )

    # ---------------------------
    # URL generation & state
    # ---------------------------

    def generate_cas_login_url(self, discord_user_id: str, extra_meta: Optional[Dict[str, Any]] = None) -> str:
        """Generate CAS login URL with service parameter & persist pending state."""
        state = secrets.token_urlsafe(32)

        self.pending_auths[state] = {
            "discord_user_id": discord_user_id,
            "timestamp": datetime.utcnow(),
            "ip_address": None,  # optionally set in webserver if you want
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

        # Embed state into service URL (CAS will echo it back untouched)
        service_url_with_state = f"{self.service_url}?state={state}"
        params = {"service": service_url_with_state}
        return f"{self.cas_login_url}?{urllib.parse.urlencode(params)}"

    # ---------------------------
    # Callback path
    # ---------------------------

    async def process_cas_callback(
        self,
        ticket: str,
        state: str,
        client_ip: Optional[str] = None,
        request_headers: Optional[dict] = None,
    ) -> dict:
        """
        Process CAS callback and validate ticket.

        NOTE: client_ip/request_headers are optional. If your webserver passes them,
        we'll store best-effort IP into discord_user_stats.last_login_ip.
        """
        if state not in self.pending_auths:
            if self.embed_logger:
                await self.embed_logger.log_auth_failure(
                    user_id="Unknown",
                    reason="Invalid state parameter",
                    error_details=f"State '{state[:8]}…' not found in pending authentications",
                )
            raise ValueError("Invalid state parameter")

        auth_info = self.pending_auths.pop(state)
        discord_user_id = auth_info["discord_user_id"]
        pending_started = auth_info.get("timestamp")

        # Best-effort IP extraction
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

        # 1) Validate CAS ticket
        user_info = await self.validate_cas_ticket(ticket, state)

        # 2) Persist user, discord meta, and assign role
        await self.verify_user(discord_user_id, user_info, auth_info.get("discord_meta") or {}, login_ip=login_ip)

        # 3) NEW: Audit + attributes snapshot
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

        # 4) Stats touch_seen (login_count++, IP)
        try:
            stats_q = DiscordStatsQueries(self.db_pool)
            await stats_q.touch_seen(discord_user_id, last_login_ip=login_ip, increment_login=True)
        except Exception as e:
            logger.warning(f"Failed to update discord_user_stats: {e}")

        # 5) Log success
        if self.embed_logger:
            await self.embed_logger.log_auth_success(discord_user_id, user_info)

        return {"discord_user_id": discord_user_id, "user_info": user_info}

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
                # Try to extract failure message for logging
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
            logger.error(f"XML content (first 5k chars): {xml_response[:5000]}")
            if self.embed_logger:
                asyncio.create_task(
                    self.embed_logger.log_error(
                        service="Authentication",
                        error=Exception(f"Invalid XML response from CAS server: {e}"),
                        context=f"XML parsing failed - Content length: {len(xml_response)}",
                    )
                )
            raise

    # ---------------------------
    # User persistence & roles
    # ---------------------------

    async def verify_user(
        self,
        discord_user_id: str,
        user_info: dict,
        discord_meta_from_auth: Dict[str, Any],
        login_ip: Optional[str] = None,
    ):
        """Determine user type, save user (with Discord meta), assign role, and upsert new tables."""
        login = user_info.get("uid", "").lower()
        email = user_info.get("mail", "")
        first_name = user_info.get("givenName", "")
        last_name = user_info.get("sn", "")
        groups = user_info.get("groups", [])
        affiliations = user_info.get("eduPersonAffiliation", [])
        cas_attrs = user_info.get("attributes", {})

        # Determine user type (0=student, 2=teacher)
        user_type = self.determine_user_type(groups, affiliations)

        # Try to fetch member for richer Discord info
        member = None
        try:
            gid = int(self.config.guild_id)
            guild = self.bot.get_guild(gid)
            if guild:
                member = guild.get_member(int(discord_user_id))
        except Exception:
            member = None

        # Compose Discord metadata
        discord_meta = dict(discord_meta_from_auth or {})
        if member:
            if not discord_meta.get("username"):
                discord_meta["username"] = member.name
            discord_meta.setdefault("global_name", getattr(member, "global_name", None))
            discord_meta.setdefault("discriminator", getattr(member, "discriminator", None))
            if "account_created_at" not in discord_meta and getattr(member, "created_at", None):
                discord_meta["account_created_at"] = member.created_at.isoformat()
                discord_meta["account_age_days_at_auth"] = _account_age_days(member.created_at)

            # avatar hash if available
            try:
                avatar = getattr(member, "avatar", None)
                if avatar and getattr(avatar, "key", None):
                    discord_meta.setdefault("avatar_hash", avatar.key)
            except Exception:
                pass

            # is bot
            try:
                discord_meta["is_bot"] = bool(getattr(member, "bot", False))
            except Exception:
                pass

        # Derive country (CAS > locale)
        country_code = _derive_country_code(cas_attrs, discord_meta.get("interaction_locale"))
        if country_code:
            discord_meta["country_code"] = country_code

        # Merge into attributes JSON
        merged_attrs = dict(cas_attrs)
        merged_attrs["discord_meta"] = discord_meta

        # Save/update in `users`
        await self.save_user(
            discord_id=discord_user_id,
            login=login,
            email=email,
            first_name=first_name,
            last_name=last_name,
            user_type=user_type,
            attributes=merged_attrs,
        )

        # Assign Discord role
        await self.assign_discord_role(discord_user_id, user_type)

        # --- NEW TABLES PERSISTENCE (safe best-effort) ---
        try:
            # 1) discord_profiles upsert
            prof_q = DiscordProfileQueries(self.db_pool)
            profile = DiscordProfile(
                discord_id=discord_user_id,
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

        try:
            # 2) discord_user_stats touch_seen (login_count++, IP)
            stats_q = DiscordStatsQueries(self.db_pool)
            await stats_q.touch_seen(discord_user_id, last_login_ip=login_ip, increment_login=True)
        except Exception as e:
            logger.warning(f"Failed to update discord_user_stats: {e}")

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

    async def save_user(
        self,
        discord_id: str,
        login: str,
        email: str,
        first_name: str,
        last_name: str,
        user_type: int,
        attributes: dict,
    ):
        """Save or update user in database (users table)."""
        user = User(
            id=discord_id,
            login=login,
            activity=1,
            type=user_type,
            verification=self.generate_verification_code(),
            real_name=f"{first_name} {last_name} ({email})".strip(),
            attributes=attributes,
            verified_at=datetime.utcnow(),
        )

        try:
            await self.user_queries.upsert_user(user)
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Authentication",
                    title="User Data Saved",
                    description="User information stored in database",
                    level=LogLevel.SUCCESS,
                    fields={
                        "User": f"<@{discord_id}>",
                        "Login": login,
                        "Type": "Teacher" if user_type == 2 else "Student",
                        "Email": email[:80] or "n/a",
                        "Attributes": f"{len(attributes)} items (incl. discord_meta)",
                    },
                )
        except Exception as e:
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Authentication",
                    error=e,
                    context=f"Failed to save user data - Discord ID: {discord_id}, Login: {login}",
                )
            raise

    async def assign_discord_role(self, discord_user_id: str, user_type: int):
        """Assign appropriate Discord role to user."""
        try:
            gid = int(self.config.guild_id)
        except Exception:
            gid = self.config.guild_id

        guild = self.bot.get_guild(gid)
        if not guild:
            error = Exception(f"Guild {self.config.guild_id} not found")
            logger.error(str(error))
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Authentication",
                    error=error,
                    context="Role assignment failed - guild not found",
                )
            return

        member = guild.get_member(int(discord_user_id))
        if not member:
            error = Exception(f"Member {discord_user_id} not found in guild")
            logger.error(str(error))
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Authentication",
                    error=error,
                    context="Role assignment failed - member not found in guild",
                )
            return

        role_id = self.config.teacher_role_id if user_type == 2 else self.config.student_role_id
        role_name = "Teacher" if user_type == 2 else "Student"

        role = guild.get_role(role_id)
        if not role:
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Authentication",
                    error=Exception(f"Role {role_id} not found in guild"),
                    context=f"Role assignment failed - role {role_id} ({role_name}) not found",
                )
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
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Authentication",
                    error=Exception("Missing permission to assign role"),
                    context=f"Role assignment failed - {discord_user_id} -> {role.name}",
                )
        except Exception as e:
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Authentication",
                    error=e,
                    context=f"Role assignment failed - {discord_user_id} -> {role.name}",
                )

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
