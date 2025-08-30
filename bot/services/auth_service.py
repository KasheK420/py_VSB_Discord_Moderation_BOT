"""
bot/services/auth_service.py
CAS Authentication Service for VSB SSO with comprehensive logging
"""

import asyncio
import logging
import secrets
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import aiohttp
import discord

from ..database.models.user import User
from ..database.queries.user_queries import UserQueries
from ..utils.config import Config
from .logging_service import EmbedLogger, LogLevel

logger = logging.getLogger(__name__)


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
        self.service_url = "https://sso.vsb-discord.cz/callback"

        # Temporary state storage for tracking authentication attempts
        self.pending_auths = {}

    async def setup(self):
        """Initialize service and register commands"""
        await self.register_button_handlers()

        # Log service startup
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

            if interaction.data["custom_id"] == "auth_sso":
                await self.handle_auth_button(interaction)

    async def handle_auth_button(self, interaction: discord.Interaction):
        """Handle SSO authentication button click"""
        user_id = str(interaction.user.id)
        username = interaction.user.name

        # Check if user is already verified
        try:
            existing_user = await self.user_queries.get_user_by_id(user_id)
            if existing_user and existing_user.activity == 1:
                await interaction.response.send_message(
                    "Již jsi ověřený! / You are already verified!", ephemeral=True
                )

                # Log repeated verification attempt
                if self.embed_logger:
                    await self.embed_logger.log_custom(
                        service="Authentication",
                        title="Repeated Verification Attempt",
                        description=f"User <@{user_id}> attempted verification but is already verified",
                        level=LogLevel.WARNING,
                        fields={
                            "User": f"<@{user_id}>",
                            "Username": username,
                            "Current Login": existing_user.login,
                            "Verified Since": (
                                existing_user.verified_at.strftime("%Y-%m-%d %H:%M")
                                if existing_user.verified_at
                                else "Unknown"
                            ),
                            "User Type": "Teacher" if existing_user.type == 2 else "Student",
                            "Action": "Button click blocked",
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
            # Continue with authentication if database check fails

        # Log authentication start
        if self.embed_logger:
            await self.embed_logger.log_auth_start(user_id, username)

        # Generate CAS login URL
        cas_login_url = self.generate_cas_login_url(user_id)

        # Create view with link button that opens the CAS login URL
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

    def generate_cas_login_url(self, discord_user_id: str) -> str:
        """Generate CAS login URL with service parameter"""
        # Generate state to track this authentication attempt
        state = secrets.token_urlsafe(32)
        self.pending_auths[state] = {
            "discord_user_id": discord_user_id,
            "timestamp": datetime.utcnow(),
            "ip_address": None,  # Could be enhanced to track IP
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
                        "State Token": state[:8] + "...",
                        "CAS Server": self.cas_server_url,
                        "Service URL": self.service_url,
                        "Pending Auths": str(len(self.pending_auths)),
                    },
                )
            )

        # Create service URL with state parameter
        service_url_with_state = f"{self.service_url}?state={state}"

        # Generate CAS login URL
        params = {"service": service_url_with_state}

        return f"{self.cas_login_url}?{urllib.parse.urlencode(params)}"

    async def process_cas_callback(self, ticket: str, state: str) -> dict:
        """Process CAS callback and validate ticket"""
        if state not in self.pending_auths:
            # Log invalid state
            if self.embed_logger:
                await self.embed_logger.log_auth_failure(
                    user_id="Unknown",
                    reason="Invalid state parameter",
                    error_details=f"State '{state[:8]}...' not found in pending authentications",
                )
            raise ValueError("Invalid state parameter")

        auth_info = self.pending_auths.pop(state)
        discord_user_id = auth_info["discord_user_id"]

        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Authentication",
                title="CAS Callback Received",
                description="Processing CAS callback for user",
                level=LogLevel.INFO,
                fields={
                    "User": f"<@{discord_user_id}>",
                    "Ticket": ticket[:8] + "...",
                    "State": state[:8] + "...",
                    "Auth Age": str((datetime.utcnow() - auth_info["timestamp"]).total_seconds())
                    + "s",
                },
            )

        try:
            # Validate ticket with CAS server
            user_info = await self.validate_cas_ticket(ticket, state)

            # Process user verification
            await self.verify_user(discord_user_id, user_info)

            # Log successful authentication
            if self.embed_logger:
                await self.embed_logger.log_auth_success(discord_user_id, user_info)

            return {"discord_user_id": discord_user_id, "user_info": user_info}

        except Exception as e:
            # Log authentication failure
            if self.embed_logger:
                await self.embed_logger.log_auth_failure(
                    user_id=discord_user_id, reason=str(type(e).__name__), error_details=str(e)
                )

                # Also log as error for debugging
                await self.embed_logger.log_error(
                    service="Authentication",
                    error=e,
                    context=f"CAS callback processing failed - User: {discord_user_id}, Ticket: {ticket[:8]}..., State: {state[:8]}...",
                )

            raise

    async def validate_cas_ticket(self, ticket: str, state: str) -> dict:
        """Validate CAS ticket and get user information"""
        service_url_with_state = f"{self.service_url}?state={state}"

        params = {"ticket": ticket, "service": service_url_with_state}

        validate_url = f"{self.cas_validate_url}?{urllib.parse.urlencode(params)}"

        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Authentication",
                title="CAS Ticket Validation",
                description="Validating ticket with CAS server",
                level=LogLevel.INFO,
                fields={
                    "Validation URL": self.cas_validate_url,
                    "Ticket": ticket[:8] + "...",
                    "Service": service_url_with_state,
                },
            )

        async with aiohttp.ClientSession() as session:
            async with session.get(validate_url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    error = Exception(
                        f"CAS validation failed (HTTP {response.status}): {error_text}"
                    )

                    if self.embed_logger:
                        await self.embed_logger.log_error(
                            service="Authentication",
                            error=error,
                            context=f"CAS server returned HTTP {response.status}",
                        )
                    raise error

                xml_response = await response.text()

                if self.embed_logger:
                    await self.embed_logger.log_custom(
                        service="Authentication",
                        title="CAS Response Received",
                        description="Successfully received response from CAS server",
                        level=LogLevel.SUCCESS,
                        fields={
                            "Response Length": f"{len(xml_response)} chars",
                            "Status": "✅ HTTP 200",
                        },
                    )

                return self.parse_cas_response(xml_response)

    def parse_cas_response(self, xml_response: str) -> dict:
        """Parse CAS XML response to extract user information"""
        try:
            root = ET.fromstring(xml_response)

            # Define namespace
            namespace = {"cas": "http://www.yale.edu/tp/cas"}

            # Check if authentication was successful
            success = root.find(".//cas:authenticationSuccess", namespace)
            if success is None:
                failure = root.find(".//cas:authenticationFailure", namespace)
                if failure is not None:
                    error_msg = failure.text or "Unknown authentication failure"
                    error = Exception(f"CAS authentication failed: {error_msg}")

                    if self.embed_logger:
                        asyncio.create_task(
                            self.embed_logger.log_error(
                                service="Authentication",
                                error=error,
                                context=f"CAS server rejected authentication: {error_msg}",
                            )
                        )
                    raise error
                else:
                    error = Exception("Invalid CAS response format")
                    if self.embed_logger:
                        asyncio.create_task(
                            self.embed_logger.log_error(
                                service="Authentication",
                                error=error,
                                context="CAS response missing success/failure elements",
                            )
                        )
                    raise error

            # Extract user information
            user = success.find("cas:user", namespace)
            if user is None:
                error = Exception("User not found in CAS response")
                if self.embed_logger:
                    asyncio.create_task(
                        self.embed_logger.log_error(
                            service="Authentication",
                            error=error,
                            context="CAS success response missing user element",
                        )
                    )
                raise error

            username = user.text

            # Extract attributes
            attributes = {}
            attrs_element = success.find("cas:attributes", namespace)
            if attrs_element is not None:
                for child in attrs_element:
                    # Remove namespace prefix from tag name
                    tag_name = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    attributes[tag_name] = child.text

            if self.embed_logger:
                asyncio.create_task(
                    self.embed_logger.log_custom(
                        service="Authentication",
                        title="CAS Response Parsed",
                        description="Successfully parsed user data from CAS",
                        level=LogLevel.SUCCESS,
                        fields={
                            "Username": username,
                            "Attributes Found": str(len(attributes)),
                            "Email": attributes.get("mail", "not provided")[:50],
                            "Groups": str(
                                len(
                                    attributes.get("groups", "").split(",")
                                    if attributes.get("groups")
                                    else []
                                )
                            )
                            + " groups",
                        },
                    )
                )

            return {
                "uid": username,
                "login": username,
                "attributes": attributes,
                # Map common attributes
                "mail": attributes.get("mail", ""),
                "givenName": attributes.get("givenName", ""),
                "sn": attributes.get("sn", ""),
                "cn": attributes.get("cn", ""),
                "groups": (
                    attributes.get("groups", "").split(",") if attributes.get("groups") else []
                ),
                "eduPersonAffiliation": (
                    attributes.get("eduPersonAffiliation", "").split(",")
                    if attributes.get("eduPersonAffiliation")
                    else []
                ),
            }

        except ET.ParseError as e:
            logger.error(f"Failed to parse CAS XML response: {e}")
            logger.error(f"XML content: {xml_response}")
            error = Exception(f"Invalid XML response from CAS server: {e}")

            if self.embed_logger:
                asyncio.create_task(
                    self.embed_logger.log_error(
                        service="Authentication",
                        error=error,
                        context=f"XML parsing failed - Content length: {len(xml_response)}",
                    )
                )
            raise error

    async def verify_user(self, discord_user_id: str, user_info: dict):
        """Verify user and assign appropriate roles"""
        # Extract user data
        login = user_info.get("uid", "").lower()
        email = user_info.get("mail", "")
        first_name = user_info.get("givenName", "")
        last_name = user_info.get("sn", "")
        groups = user_info.get("groups", [])
        affiliations = user_info.get("eduPersonAffiliation", [])

        # Determine user type (0=student, 2=teacher)
        user_type = self.determine_user_type(groups, affiliations)

        # Save or update user in database
        await self.save_user(
            discord_user_id, login, email, first_name, last_name, user_type, user_info["attributes"]
        )

        # Log database operation
        if self.embed_logger:
            await self.embed_logger.log_database_operation(
                operation="UPSERT",
                table="users",
                affected_rows=1,
                details=f"User {login} ({discord_user_id}) - Type: {'Teacher' if user_type == 2 else 'Student'}",
            )

        # Assign Discord role
        await self.assign_discord_role(discord_user_id, user_type)

        logger.info(f"User {discord_user_id} verified as {login} (type: {user_type})")

    def determine_user_type(self, groups: list, affiliations: list) -> int:
        """Determine if user is student (0) or teacher (2)"""
        # Check affiliations for teacher/employee indicators
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
                            fields={
                                "Type": "Teacher",
                                "Reason": f"Affiliation: {affiliation}",
                                "All Affiliations": ", ".join(affiliations),
                            },
                        )
                    )
                return 2

        # Check groups for teacher indicators
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
                            fields={
                                "Type": "Teacher",
                                "Reason": f"Group: {group}",
                                "All Groups": ", ".join(groups[:5])
                                + ("..." if len(groups) > 5 else ""),
                            },
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
                    fields={
                        "Type": "Student",
                        "Reason": "No teacher indicators found",
                        "Groups Checked": str(len(groups)),
                        "Affiliations Checked": str(len(affiliations)),
                    },
                )
            )

        return 0  # Default to student

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
        """Save or update user in database"""
        user = User(
            id=discord_id,
            login=login,
            activity=1,
            type=user_type,
            verification=self.generate_verification_code(),
            real_name=f"{first_name} {last_name} ({email})",
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
                        "Email": email,
                        "Full Name": f"{first_name} {last_name}",
                        "Attributes": f"{len(attributes)} items stored",
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
        """Assign appropriate Discord role to user"""
        guild = self.bot.get_guild(self.config.guild_id)
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

        # Get role based on user type
        if user_type == 2:
            role_id = self.config.teacher_role_id
            role_name = "Teacher"
        else:
            role_id = self.config.student_role_id
            role_name = "Student"

        role = guild.get_role(role_id)
        if role:
            try:
                await member.add_roles(role)
                logger.info(f"Added role {role.name} to user {discord_user_id}")

                # Log role assignment
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
                error = Exception(f"No permission to assign role {role.name}")
                if self.embed_logger:
                    await self.embed_logger.log_error(
                        service="Authentication",
                        error=error,
                        context=f"Role assignment failed - no permission to assign {role.name} to {discord_user_id}",
                    )
            except Exception as e:
                if self.embed_logger:
                    await self.embed_logger.log_error(
                        service="Authentication",
                        error=e,
                        context=f"Role assignment failed - {discord_user_id} -> {role.name}",
                    )
        else:
            error = Exception(f"Role {role_id} not found in guild")
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Authentication",
                    error=error,
                    context=f"Role assignment failed - role {role_id} ({role_name}) not found",
                )

    def generate_verification_code(self) -> str:
        """Generate random verification code"""
        return secrets.token_urlsafe(8)[:8]

    async def cleanup_expired_auths(self):
        """Clean up expired authentication attempts (older than 1 hour)"""
        cutoff_time = datetime.utcnow() - timedelta(hours=1)
        expired_states = []

        for state, auth_info in self.pending_auths.items():
            if auth_info["timestamp"] < cutoff_time:
                expired_states.append(state)

        for state in expired_states:
            del self.pending_auths[state]

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
