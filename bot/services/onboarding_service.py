# bot/services/onboarding_service.py
import logging
from typing import Optional

import discord

from ..services.logging_service import LogLevel

logger = logging.getLogger(__name__)


class OnboardingService:
    def __init__(self, config):
        self.config = config
        self.embed_logger: Optional = None

    def set_logger(self, embed_logger):
        """Set the embed logger for this service"""
        self.embed_logger = embed_logger

    async def ensure_verification_message(self, bot: discord.Client):
        """Ensure verification message is posted in welcome channel"""
        guild_id = int(self.config.guild_id)
        welcome_channel_id = int(self.config.welcome_channel_id)

        # Use fetch_* for reliability, with cache fallback
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

        try:
            channel = await bot.fetch_channel(welcome_channel_id)
        except Exception:
            channel = bot.get_channel(welcome_channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            error = Exception(f"Welcome channel {welcome_channel_id} not found or invalid type")
            logger.error(str(error))
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Onboarding Service",
                    error=error,
                    context=f"ensure_verification_message - channel {welcome_channel_id} not found",
                )
            return

        # Clean old bot messages
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
                        "Channel": f"<#{welcome_channel_id}>",
                        "Error": str(e),
                        "Action": "Continuing with new message post",
                    },
                )

        if self.embed_logger and messages_deleted > 0:
            await self.embed_logger.log_custom(
                service="Onboarding Service",
                title="Old Messages Cleaned",
                description="Removed old verification messages before posting new one",
                level=LogLevel.INFO,
                fields={
                    "Channel": f"<#{welcome_channel_id}>",
                    "Messages Deleted": str(messages_deleted),
                    "Status": "✅ Cleaned",
                },
            )

        # Create verification embed
        embed = discord.Embed(
            title="Vítej / Welcome!",
            description=(
                "Pro získání přístupu k serveru se musíš ověřit pomocí VSB SSO.\n"
                "To gain access to the server, you need to verify using VSB SSO."
            ),
            color=discord.Color.blue(),
        )

        # Add helpful information
        embed.add_field(
            name="🔒 Ověření / Verification",
            value="Klikni na tlačítko níže pro ověření / Click the button below to verify",
            inline=False,
        )

        embed.add_field(
            name="📚 Po ověření / After verification",
            value=(
                "• Přístup ke všem kanálům / Access to all channels\n"
                "• Role podle typu účtu / Role based on account type\n"
                "• Účast v komunitě / Community participation"
            ),
            inline=False,
        )

        embed.set_footer(text="VSB Discord Server • Secure authentication via VSB SSO")

        # Create verification button
        view = discord.ui.View(timeout=None)
        view.add_item(
            discord.ui.Button(
                label="Ověřit se / Verify",
                style=discord.ButtonStyle.primary,
                custom_id="auth_sso",
                emoji="🔒",
            )
        )

        try:
            message = await channel.send(embed=embed, view=view)

            if self.embed_logger:
                await self.embed_logger.log_custom(
                    service="Onboarding Service",
                    title="Verification Message Posted",
                    description="New verification message successfully posted in welcome channel",
                    level=LogLevel.SUCCESS,
                    fields={
                        "Channel": f"<#{welcome_channel_id}>",
                        "Message ID": str(message.id),
                        "Guild": guild.name,
                        "Old Messages Deleted": str(messages_deleted),
                        "Embed Title": embed.title,
                        "Button Custom ID": "auth_sso",
                        "Status": "✅ Ready for users",
                    },
                )

            logger.info(
                f"Verification message posted in channel {welcome_channel_id} (message ID: {message.id})"
            )

        except discord.Forbidden:
            error = Exception(f"No permission to send messages in channel {welcome_channel_id}")
            logger.error(str(error))
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Onboarding Service",
                    error=error,
                    context=f"ensure_verification_message - no permission in channel {welcome_channel_id}",
                )
        except Exception as e:
            logger.error(f"Failed to post verification message: {e}")
            if self.embed_logger:
                await self.embed_logger.log_error(
                    service="Onboarding Service",
                    error=e,
                    context=f"ensure_verification_message - failed to post in channel {welcome_channel_id}",
                )

    async def handle_user_join(self, member: discord.Member):
        """Handle new user joining the server"""
        if self.embed_logger:
            # Check account age
            account_age_hours = (discord.utils.utcnow() - member.created_at).total_seconds() / 3600
            account_age_days = account_age_hours / 24

            # Determine risk level
            if account_age_hours < 1:
                risk_level = "🔴 Very High"
            elif account_age_hours < 24:
                risk_level = "🟠 High"
            elif account_age_days < 7:
                risk_level = "🟡 Medium"
            else:
                risk_level = "🟢 Low"

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
            f"New member joined: {member.name}#{member.discriminator} ({member.id}) - Account age: {account_age_days:.1f} days"
        )

    async def handle_user_leave(self, member: discord.Member, was_verified: bool = None):
        """Handle user leaving the server"""
        if self.embed_logger:
            # Try to determine if they were verified (would need database lookup)
            verification_status = (
                "✅ Verified"
                if was_verified
                else "❌ Unverified"
                if was_verified is False
                else "❓ Unknown"
            )

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

    async def get_verification_stats(self, bot: discord.Client) -> dict:
        """Get onboarding and verification statistics"""
        guild_id = int(self.config.guild_id)
        guild = bot.get_guild(guild_id)

        if not guild:
            return {"error": "Guild not found"}

        # Basic member statistics
        total_members = guild.member_count or len(guild.members)
        bot_members = len([m for m in guild.members if m.bot])
        human_members = total_members - bot_members

        # Get role statistics (assuming student/teacher roles exist)
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
        unverified_count = human_members - verified_count

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
