import datetime

import discord
from discord import app_commands
from discord.app_commands.checks import has_permissions

from ..configuration import Configuration
from ..service import Service
from ..utils.logger import get_logger

# Initialize logger
logger = get_logger("user_management_admin")


def __service__():
    return UserManagementAdminService()


class UserManagementAdminService(Service):
    def __register_commands__(self):
        """
        Register all admin-only slash commands.
        """

        # --- User Moderation Commands --- #
        @self.commands.command(name="nick", description="Change a user's nickname.")
        @app_commands.describe(user="The user to change nickname for.", nickname="The new nickname.")
        @has_permissions(administrator=True)
        async def nick(interaction: discord.Interaction, user: discord.Member, nickname: str):
            try:
                await user.edit(nick=nickname)
                await interaction.response.send_message(f"Changed nickname for {user.mention} to `{nickname}`.")
                logger.info(f"Changed nickname for {user.name} to {nickname}")
            except Exception as e:
                logger.error(f"Failed to change nickname for {user.name}: {e}")
                await interaction.response.send_message(
                    "Failed to change the nickname. Check permissions.", ephemeral=True
                )

        @self.commands.command(name="kick", description="Kick a user from the server.")
        @app_commands.describe(user="The user to kick.", reason="The reason for kicking the user.")
        @has_permissions(administrator=True)
        async def kick(
            interaction: discord.Interaction,
            user: discord.Member,
            reason: str = "No reason provided.",
        ):
            try:
                await user.kick(reason=reason)
                await interaction.response.send_message(f"{user.mention} has been kicked. Reason: {reason}")
                logger.info(f"Kicked {user.name} for reason: {reason}")
            except Exception as e:
                logger.error(f"Failed to kick {user.name}: {e}")
                await interaction.response.send_message("Failed to kick the user. Check permissions.", ephemeral=True)

        @self.commands.command(name="ban", description="Ban a user from the server.")
        @app_commands.describe(user="The user to ban.", reason="The reason for banning the user.")
        @has_permissions(administrator=True)
        async def ban(
            interaction: discord.Interaction,
            user: discord.Member,
            reason: str = "No reason provided.",
        ):
            try:
                await user.ban(reason=reason)
                await interaction.response.send_message(f"{user.mention} has been banned. Reason: {reason}")
                logger.info(f"Banned {user.name} for reason: {reason}")
            except Exception as e:
                logger.error(f"Failed to ban {user.name}: {e}")
                await interaction.response.send_message("Failed to ban the user. Check permissions.", ephemeral=True)

        @self.commands.command(name="timeout", description="Timeout a user.")
        @app_commands.describe(
            user="The user to timeout.",
            duration="The duration of the timeout in seconds.",
        )
        @has_permissions(administrator=True)
        async def timeout(interaction: discord.Interaction, user: discord.Member, duration: int):
            try:
                await user.timeout(until=discord.utils.utcnow() + datetime.timedelta(seconds=duration))
                await interaction.response.send_message(f"{user.mention} has been timed out for {duration} seconds.")
                logger.info(f"Timed out {user.name} for {duration} seconds.")
            except Exception as e:
                logger.error(f"Failed to timeout {user.name}: {e}")
                await interaction.response.send_message(
                    "Failed to timeout the user. Check permissions.", ephemeral=True
                )

        @self.commands.command(name="purge", description="Delete multiple messages at once.")
        @app_commands.describe(amount="Number of messages to delete.")
        @has_permissions(administrator=True)
        async def purge(interaction: discord.Interaction, amount: int):
            try:
                deleted = await interaction.channel.purge(limit=amount)
                await interaction.response.send_message(f"Deleted {len(deleted)} messages.", ephemeral=True)
                logger.info(f"Purged {len(deleted)} messages in channel {interaction.channel.name}.")
            except Exception as e:
                logger.error(f"Failed to purge messages: {e}")
                await interaction.response.send_message("Failed to purge messages. Check permissions.", ephemeral=True)

        @self.commands.command(name="unban", description="Unban a user from the server.")
        @app_commands.describe(user="The username#discriminator of the user to unban.")
        @has_permissions(administrator=True)
        async def unban(interaction: discord.Interaction, user: str):
            """
            Unban a user from the server.
            """
            try:
                bans = await interaction.guild.bans()
                user_to_unban = next((entry.user for entry in bans if str(entry.user) == user), None)
                if user_to_unban:
                    await interaction.guild.unban(user_to_unban)
                    await interaction.response.send_message(f"{user_to_unban.mention} has been unbanned.")
                    logger.info(f"Unbanned {user_to_unban.name}")
                else:
                    await interaction.response.send_message("User not found in the ban list.", ephemeral=True)
            except Exception as e:
                logger.error(f"Failed to unban {user}: {e}")
                await interaction.response.send_message("Failed to unban the user. Check permissions.", ephemeral=True)

        @self.commands.command(name="untimeout", description="Remove a user's timeout.")
        @app_commands.describe(user="The user to remove timeout from.")
        @has_permissions(administrator=True)
        async def untimeout(interaction: discord.Interaction, user: discord.Member):
            """
            Remove a timeout from a user.
            """
            try:
                await user.timeout(None)
                await interaction.response.send_message(f"{user.mention}'s timeout has been removed.")
                logger.info(f"Removed timeout for {user.name}.")
            except Exception as e:
                logger.error(f"Failed to remove timeout for {user.name}: {e}")
                await interaction.response.send_message("Failed to remove timeout. Check permissions.", ephemeral=True)

        @self.commands.command(name="giverole", description="Give a role to a user.")
        @app_commands.describe(user="The user to give the role to.", role="The role to give.")
        @has_permissions(administrator=True)
        async def giverole(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
            """
            Assign a role to a user.
            """
            try:
                await user.add_roles(role)
                await interaction.response.send_message(f"Given role `{role.name}` to {user.mention}.")
                logger.info(f"Gave role {role.name} to {user.name}.")
            except Exception as e:
                logger.error(f"Failed to give role {role.name} to {user.name}: {e}")
                await interaction.response.send_message("Failed to give the role. Check permissions.", ephemeral=True)

        @self.commands.command(name="takerole", description="Remove a role from a user.")
        @app_commands.describe(user="The user to remove the role from.", role="The role to remove.")
        @has_permissions(administrator=True)
        async def takerole(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
            """
            Remove a role from a user.
            """
            try:
                await user.remove_roles(role)
                await interaction.response.send_message(f"Removed role `{role.name}` from {user.mention}.")
                logger.info(f"Removed role {role.name} from {user.name}.")
            except Exception as e:
                logger.error(f"Failed to remove role {role.name} from {user.name}: {e}")
                await interaction.response.send_message("Failed to remove the role. Check permissions.", ephemeral=True)

        @self.commands.command(name="warn", description="Warn a user.")
        @app_commands.describe(user="The user to warn.", reason="The reason for the warning.")
        @has_permissions(administrator=True)
        async def warn(interaction: discord.Interaction, user: discord.Member, reason: str):
            """
            Warn a user and log the warning in memory.
            """
            warnings = Configuration.get("warnings", {})
            warnings.setdefault(str(user.id), []).append(reason)
            Configuration._singleton.conf["warnings"] = warnings
            Configuration._singleton.refresh()

            await interaction.response.send_message(f"{user.mention} has been warned for: {reason}")
            logger.info(f"Warned {user.name}: {reason}")

        @self.commands.command(name="checkwarn", description="Check a user's warnings.")
        @app_commands.describe(user="The user to check warnings for.")
        @has_permissions(administrator=True)
        async def checkwarn(interaction: discord.Interaction, user: discord.Member):
            """
            Check warnings for a user.
            """
            warnings = Configuration.get("warnings", {}).get(str(user.id), [])
            if warnings:
                await interaction.response.send_message(
                    f"{user.mention} has the following warnings:\n" + "\n".join([f"- {w}" for w in warnings])
                )
            else:
                await interaction.response.send_message(f"{user.mention} has no warnings.")
            logger.info(f"Checked warnings for {user.name}.")

        @self.commands.command(name="clearwarn", description="Clear a user's warnings.")
        @app_commands.describe(user="The user to clear warnings for.")
        @has_permissions(administrator=True)
        async def clearwarn(interaction: discord.Interaction, user: discord.Member):
            """
            Clear all warnings for a user.
            """
            warnings = Configuration.get("warnings", {})
            if str(user.id) in warnings:
                del warnings[str(user.id)]
                Configuration.singleton.conf["warnings"] = warnings
                Configuration.singleton.refresh()
                await interaction.response.send_message(f"Cleared all warnings for {user.mention}.")
                logger.info(f"Cleared warnings for {user.name}.")
            else:
                await interaction.response.send_message(f"{user.mention} has no warnings to clear.")

        # --- Channel Management Commands --- #
        @self.commands.command(name="lock", description="Lock a channel.")
        @has_permissions(administrator=True)
        async def lock(interaction: discord.Interaction):
            """
            Lock the current channel by removing send message permissions for @everyone.
            """
            try:
                await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
                await interaction.response.send_message(f"{interaction.channel.mention} has been locked.")
                logger.info(f"Locked channel {interaction.channel.name}.")
            except Exception as e:
                logger.error(f"Failed to lock channel {interaction.channel.name}: {e}")
                await interaction.response.send_message(
                    "Failed to lock the channel. Check permissions.", ephemeral=True
                )

        @self.commands.command(name="unlock", description="Unlock a channel.")
        @has_permissions(administrator=True)
        async def unlock(interaction: discord.Interaction):
            """
            Unlock the current channel by restoring send message permissions for @everyone.
            """
            try:
                await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=True)
                await interaction.response.send_message(f"{interaction.channel.mention} has been unlocked.")
                logger.info(f"Unlocked channel {interaction.channel.name}.")
            except Exception as e:
                logger.error(f"Failed to unlock channel {interaction.channel.name}: {e}")
                await interaction.response.send_message(
                    "Failed to unlock the channel. Check permissions.", ephemeral=True
                )

    async def on_ready(self):
        logger.info("UserManagementAdminService is ready!")
