# bot/services/onboarding_service.py
import logging
from typing import Optional, Dict, Any, Tuple

import discord

from ..services.logging_service import LogLevel

logger = logging.getLogger(__name__)


class OnboardingService:
    """
    Handles onboarding flows:
      - posts SSO verification message
      - posts alternative role selection (Host / Absolvent)
      - logs joins/leaves/kicks/bans
      - generates verification statistics
      - assigns roles from component interactions
    """

    def __init__(self, config):
        self.config = config
        self.embed_logger: Optional = None
        self._interaction_hooked: bool = False  # ensure we don't double-register

    def set_logger(self, embed_logger):
        """Attach the embed logger used for admin/channel logging."""
        self.embed_logger = embed_logger

    # ---------------------------
    # Public bootstrap / handlers
    # ---------------------------

    async def ensure_verification_message(self, bot: discord.Client):
        """
        Ensure the verification messages are posted in the verification channel.

        It posts TWO messages in order:
          1) SSO Verification embed with one button (custom_id="auth_sso")
          2) Alternative roles embed with two buttons (Host, Absolvent)

        Note: We keep custom_id pattern 'role_host_<id>' / 'role_absolvent_<id>' so
        previously posted messages continue to work. Our interaction handler
        supports BOTH these and plain 'role_host' / 'role_absolvent'.
        """
        guild_id = int(self.config.guild_id)
        verification_channel_id = int(self.config.verification_channel_id)

        # --- Fetch guild (fetch_* with cache fallback for reliability) ---
        try:
            guild = await bot.fetch_guild(guild_id)
        except Exception:
            guild = bot.get_guild(guild_id)

        if not guild:
            error = Exception(f"Guild {guild_id} not found")
            logger.error(str(error))
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Onboarding Service",
                    error=error,
                    context="ensure_verification_message - guild not found",
                )
            return

        # --- Fetch channel (TextChannel expected) ---
        try:
            channel = await bot.fetch_channel(verification_channel_id)
        except Exception:
            channel = bot.get_channel(verification_channel_id)

        if not isinstance(channel, discord.TextChannel):
            error = Exception(
                f"Verification channel {verification_channel_id} not found or invalid type"
            )
            logger.error(str(error))
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Onboarding Service",
                    error=error,
                    context=f"ensure_verification_message - channel {verification_channel_id} not found/invalid",
                )
            return

        # --- Clean old bot messages (best-effort) ---
        messages_deleted = 0
        try:
            async for msg in channel.history(limit=50):
                if msg.author == bot.user:
                    try:
                        await msg.delete()
                        messages_deleted += 1
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Failed to clean old messages: {e}")
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Onboarding Service",
                    title="Message Cleanup Warning",
                    description="Failed to clean some old verification messages",
                    level=LogLevel.WARNING,
                    fields={
                        "Channel": f"<#{verification_channel_id}>",
                        "Error": str(e),
                        "Action": "Continuing with new message post",
                    },
                )

        if self.embed_logger and messages_deleted > 0:
            await self.embed_logger.log_custom(
                service="Onboarding Service",
                title="Old Messages Cleaned",
                description="Removed old verification messages before posting new ones",
                level=LogLevel.INFO,
                fields={
                    "Channel": f"<#{verification_channel_id}>",
                    "Messages Deleted": str(messages_deleted),
                    "Status": "✅ Cleaned",
                },
            )

        pistachio = discord.Color.from_str("#8BC34A")

        # =========================
        # Embed 1: SSO Verification
        # =========================
        embed_verification = discord.Embed(
            title="🔒 Verifikace",
            description=(
                "**Vítejte na studentském komunitním Discordu VŠB - TUO.**\n\n"
                "**Jak se verifikovat?**\n"
                "Pro vstup na celý Discord je potřeba zmáčknout tlačítko pod touto zprávou, "
                "pomocí kterého se vygeneruje unikátní odkaz na **SSO verifikaci**.\n\n"
                "Tento odkaz tě následně přesměruje na **oficiální přihlášení od VŠB - TUO** "
                "(https://sso.vsb.cz).\n\n"
                "—\n"
                "**Welcome!** Click the button below to generate a unique **SSO verification** link. "
                "You will be redirected to the official **VŠB - TUO login** page (https://sso.vsb.cz)."
            ),
            color=pistachio,
        )
        embed_verification.set_footer(text="VSB Discord Server • Secure authentication via VSB SSO")

        view_verification = discord.ui.View(timeout=None)
        view_verification.add_item(
            discord.ui.Button(
                label="Ověřit se / Verify",
                style=discord.ButtonStyle.primary,
                custom_id="auth_sso",
                emoji="🔒",
            )
        )

        # ====================================
        # Embed 2: Alternative roles selection
        # ====================================
        embed_roles = discord.Embed(
            title="👥 Nejsi student VŠB-TUO?",
            description=(
                "Nestuduješ u nás, nebo jsi absolvent?\n\n"
                "Vyber si jednu z rolí níže pro **omezený přístup** na náš Discord."
            ),
            color=pistachio,
        )

        view_roles = discord.ui.View(timeout=None)
        view_roles.add_item(
            discord.ui.Button(
                label="Host",
                style=discord.ButtonStyle.secondary,
                # Keep suffixed pattern so old messages keep working
                custom_id=f"role_host_{self.config.host_role_id}",
                emoji="🙋",
            )
        )
        view_roles.add_item(
            discord.ui.Button(
                label="Absolvent",
                style=discord.ButtonStyle.secondary,
                custom_id=f"role_absolvent_{self.config.absolvent_role_id}",
                emoji="🎓",
            )
        )

        # --- Post both embeds ---
        try:
            msg1 = await channel.send(embed=embed_verification, view=view_verification)
            msg2 = await channel.send(embed=embed_roles, view=view_roles)

            logger.info(
                f"Verification and role messages posted in channel {verification_channel_id} "
                f"(msg IDs: {msg1.id}, {msg2.id})"
            )

            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Onboarding Service",
                    title="Verification Messages Posted",
                    description="Verification & role-selection messages successfully posted",
                    level=LogLevel.SUCCESS,
                    fields={
                        "Channel": f"<#{verification_channel_id}>",
                        "Verification Msg ID": str(msg1.id),
                        "Roles Msg ID": str(msg2.id),
                        "Guild": guild.name,
                        "Old Messages Deleted": str(messages_deleted),
                        "Embed1 Title": embed_verification.title,
                        "Embed2 Title": embed_roles.title,
                        "Button IDs": "auth_sso, role_host_*, role_absolvent_*",
                        "Status": "✅ Ready for users",
                    },
                )

        except discord.Forbidden:
            error = Exception(f"No permission to send messages in channel {verification_channel_id}")
            logger.error(str(error))
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Onboarding Service",
                    error=error,
                    context=f"ensure_verification_message - no permission in channel {verification_channel_id}",
                )
        except Exception as e:
            logger.error(f"Failed to post verification messages: {e}")
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Onboarding Service",
                    error=e,
                    context=f"ensure_verification_message - failed to post in channel {verification_channel_id}",
                )

        # Make sure interaction handler is registered once
        self.register_interaction_handler(bot)

    def register_interaction_handler(self, bot: discord.Client):
        if self._interaction_hooked:
            return

        async def _listener(interaction: discord.Interaction):
            try:
                if interaction.type != discord.InteractionType.component:
                    return
                custom_id = interaction.data.get("custom_id", "")
                if not custom_id:
                    return

                # ❌ REMOVE this whole branch:
                # if custom_id == "auth_sso":
                #     await self._respond_ephemeral(
                #         interaction,
                #         "🔒 Ověření: otevři odkaz, který ti bot poslal do DM. Pokud nic nepřišlo, "
                #         "zkontroluj soukromí zpráv nebo napiš moderátorům.",
                #         mention=False,
                #     )
                #     return

                # ✅ ponech jen obsluhu role_* tlačítek:
                role_info = self._parse_role_custom_id(custom_id)
                if role_info is None:
                    return
                role_type, role_id = role_info
                await self._handle_role_assignment_interaction(interaction, role_type, role_id)

            except Exception as e:
                logger.exception("Error in onboarding on_interaction: %s", e)
                if self.embed_logger:
                    await self.embed_logger.log_error(
                        service="Onboarding Service",
                        error=e,
                        context="on_interaction handler",
                    )

        bot.add_listener(_listener, "on_interaction")
        self._interaction_hooked = True
        logger.info("OnboardingService: on_interaction handler registered")

    # ---------------------------
    # Interaction / role helpers
    # ---------------------------

    def _parse_role_custom_id(self, custom_id: str) -> Optional[Tuple[str, int]]:
        """
        Accepts:
          - 'role_host_<id>' / 'role_absolvent_<id>'
          - 'role_host' / 'role_absolvent'  (falls back to config IDs)
        Returns tuple (role_type, role_id) or None if not ours.
        """
        if custom_id.startswith("role_host"):
            if custom_id.startswith("role_host_"):
                try:
                    rid = int(custom_id.split("role_host_")[1])
                except Exception:
                    rid = int(self.config.host_role_id)
            else:
                rid = int(self.config.host_role_id)
            return ("host", rid)

        if custom_id.startswith("role_absolvent"):
            if custom_id.startswith("role_absolvent_"):
                try:
                    rid = int(custom_id.split("role_absolvent_")[1])
                except Exception:
                    rid = int(self.config.absolvent_role_id)
            else:
                rid = int(self.config.absolvent_role_id)
            return ("absolvent", rid)

        return None

    async def _handle_role_assignment_interaction(
        self, interaction: discord.Interaction, role_type: str, role_id: int
    ):
        """Assign or toggle the role for the clicking member."""
        guild = interaction.guild
        member = interaction.user if isinstance(interaction.user, discord.Member) else None

        if guild is None or member is None:
            await self._respond_ephemeral(
                interaction, "⚠️ Nelze přiřadit roli mimo server.", mention=False
            )
            return

        role = guild.get_role(role_id)
        if role is None:
            await self._respond_ephemeral(
                interaction, "❌ Tato role už neexistuje. Kontaktuj moderátory.", mention=False
            )
            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Onboarding Service",
                    title="Role Assignment Failed",
                    description="Configured role was not found",
                    level=LogLevel.ERROR,
                    fields={
                        "User": f"{member} ({member.id})",
                        "Role Type": role_type,
                        "Role ID": str(role_id),
                        "Guild": guild.name,
                    },
                )
            return

        # Toggle behavior: add if missing, remove if already has
        try:
            if role in member.roles:
                await member.remove_roles(role, reason=f"Onboarding toggle: {role_type}")
                await self._respond_ephemeral(
                    interaction, f"➖ Odebrána role **{role.name}**.", mention=False
                )
                action = "removed"
            else:
                await member.add_roles(role, reason=f"Onboarding assign: {role_type}")
                await self._respond_ephemeral(
                    interaction, f"✅ Přiřazena role **{role.name}**.", mention=False
                )
                action = "assigned"

            logger.info("Onboarding %s role '%s' to %s", action, role.name, member)

            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Onboarding Service",
                    title="Role Updated",
                    description=f"Role {action}",
                    level=LogLevel.SUCCESS if action == "assigned" else LogLevel.INFO,
                    fields={
                        "User": f"{member.mention} ({member.id})",
                        "Role": f"{role.name} ({role.id})",
                        "Role Type": role_type,
                        "Guild": guild.name,
                        "Status": "OK",
                    },
                )

        except discord.Forbidden as e:
            await self._respond_ephemeral(
                interaction,
                "⛔ Nemám oprávnění upravovat tvoje role. Kontaktuj moderátory.",
                mention=False,
            )
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Onboarding Service",
                    error=e,
                    context=f"Assign role '{role.name}' forbidden",
                )
        except Exception as e:
            await self._respond_ephemeral(
                interaction, "❌ Něco se pokazilo při přiřazení role.", mention=False
            )
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Onboarding Service",
                    error=e,
                    context=f"Assign role '{role.name}' unexpected error",
                )

    async def _respond_ephemeral(
        self, interaction: discord.Interaction, message: str, mention: bool = False
    ):
        """Ephemeral helper (edit or respond)."""
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except Exception as e:
            logger.debug("Failed ephemeral response: %s", e)

    # ---------------------------
    # Member lifecycle logging
    # ---------------------------

    async def handle_user_join(self, member: discord.Member):
        """Handle new user joining the server with risk assessment and logging."""
        account_age_hours = (discord.utils.utcnow() - member.created_at).total_seconds() / 3600
        account_age_days = account_age_hours / 24

        if account_age_hours < 1:
            risk_level = "🔴 Very High"
        elif account_age_hours < 24:
            risk_level = "🟠 High"
        elif account_age_days < 7:
            risk_level = "🟡 Medium"
        else:
            risk_level = "🟢 Low"

        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Onboarding Service",
                title="New User Joined",
                description="New member joined the server",
                level=LogLevel.INFO,
                fields={
                    "User": f"{member.mention} ({member.name}#{member.discriminator})",
                    "User ID": str(member.id),
                    "Account Created": member.created_at.strftime("%Y-%m-%d %H:%M UTC"),
                    "Account Age": f"{account_age_days:.1f} days ({account_age_hours:.1f} hours)",
                    "Risk Level": risk_level,
                    "Avatar": "Yes" if member.avatar else "No (default)",
                    "Status": "⏳ Awaiting verification",
                },
            )

        logger.info(
            f"New member joined: {member.name}#{member.discriminator} ({member.id}) - "
            f"Account age: {account_age_days:.1f} days - Risk: {risk_level}"
        )

    async def handle_user_leave(self, member: discord.Member, was_verified: bool = None):
        """Handle user leaving the server with logging."""
        verification_status = (
            "✅ Verified"
            if was_verified
            else "❌ Unverified"
            if was_verified is False
            else "❓ Unknown"
        )

        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Onboarding Service",
                title="User Left Server",
                description="Member left the server",
                level=LogLevel.INFO,
                fields={
                    "User": f"{member.name}#{member.discriminator}",
                    "User ID": str(member.id),
                    "Joined At": (
                        member.joined_at.strftime("%Y-%m-%d %H:%M UTC")
                        if member.joined_at
                        else "Unknown"
                    ),
                    "Time in Server": (
                        str(discord.utils.utcnow() - member.joined_at).split(".")[0]
                        if member.joined_at
                        else "Unknown"
                    ),
                    "Verification Status": verification_status,
                    "Roles": (
                        ", ".join([role.name for role in member.roles[1:]])
                        if len(member.roles) > 1
                        else "None"
                    ),
                },
            )

        logger.info(
            f"Member left: {member.name}#{member.discriminator} ({member.id}) - Was verified: {was_verified}"
        )

    async def handle_user_kicked(self, member: discord.Member, reason: Optional[str] = None):
        """Separate log entry for kicked users."""
        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Onboarding Service",
                title="User Kicked",
                description="Member was kicked from the server",
                level=LogLevel.WARNING,
                fields={
                    "User": f"{member} ({member.id})",
                    "Reason": reason or "—",
                },
            )

    async def handle_user_banned(self, user: discord.User, reason: Optional[str] = None):
        """Separate log entry for banned users."""
        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Onboarding Service",
                title="User Banned",
                description="User was banned from the server",
                level=LogLevel.ERROR,
                fields={
                    "User": f"{user} ({user.id})",
                    "Reason": reason or "—",
                },
            )

    # ---------------------------
    # Stats
    # ---------------------------

    async def get_verification_stats(self, bot: discord.Client) -> Dict[str, Any]:
        """
        Generate onboarding / verification statistics from the guild.

        Returns dict with:
          - total_members, human_members, bot_members
          - verified_members, unverified_members
          - student_members, teacher_members
          - verification_rate (%)
        """
        guild_id = int(self.config.guild_id)
        guild = bot.get_guild(guild_id)

        if not guild:
            return {"error": "Guild not found"}

        total_members = guild.member_count or len(guild.members)
        bot_members = len([m for m in guild.members if m.bot])
        human_members = total_members - bot_members

        student_role = None
        teacher_role = None
        try:
            student_role = guild.get_role(int(self.config.student_role_id))
            teacher_role = guild.get_role(int(self.config.teacher_role_id))
        except (ValueError, AttributeError):
            pass

        student_count = len(student_role.members) if student_role else 0
        teacher_count = len(teacher_role.members) if teacher_role else 0
        verified_count = student_count + teacher_count
        unverified_count = max(0, human_members - verified_count)

        stats = {
            "total_members": total_members,
            "human_members": human_members,
            "bot_members": bot_members,
            "verified_members": verified_count,
            "unverified_members": unverified_count,
            "student_members": student_count,
            "teacher_members": teacher_count,
            "verification_rate": (
                round((verified_count / human_members * 100), 1) if human_members > 0 else 0
            ),
        }

        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Onboarding Service",
                title="Verification Stats Requested",
                description="Onboarding service statistics generated",
                level=LogLevel.INFO,
                fields={
                    "Total Members": str(total_members),
                    "Human Members": str(human_members),
                    "Verified Members": str(verified_count),
                    "Verification Rate": f"{stats['verification_rate']}%",
                    "Students": str(student_count),
                    "Teachers": str(teacher_count),
                    "Status": "✅ Stats generated",
                },
            )

        return stats
