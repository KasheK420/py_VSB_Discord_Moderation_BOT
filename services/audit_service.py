from utils.logger import get_logger
from service import Service
import discord
import datetime
from configuration import Configuration

# Set up logging
logger = get_logger("audit_service")


def __service__():
    """Returns an instance of the AuditService."""
    return AuditService()


class AuditService(Service):
    """
    Service to log and audit message edits and deletions.
    """

    async def on_ready(self):
        """
        Called when the bot is ready.
        """
        logger.info("AuditService is ready!")

    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """
        Called when a message is edited.
        Logs the edit to the audit channel.
        """
        if after.author.bot:
            # Ignore bot messages
            return

        try:
            embed = discord.Embed(
                title="Message Edited",
                description=f"[Jump to Message]({after.jump_url})",
                timestamp=datetime.datetime.now(),
                color=discord.Colour.from_rgb(255, 255, 0)
            )
            embed.set_footer(text=f"Edited by: {after.author.name}#{after.author.discriminator}")
            embed.add_field(name="Channel", value=after.channel.mention, inline=True)
            embed.add_field(name="Before", value=before.content or "*Empty*", inline=False)
            embed.add_field(name="After", value=after.content or "*Empty*", inline=False)

            audit_channel = await self.get_audit_channel()
            await audit_channel.send(embed=embed)
            logger.info(f"Logged message edit by {after.author.name} in {after.channel.name}")
        except Exception as e:
            logger.error(f"Error logging message edit: {e}")

    async def on_message_delete(self, message: discord.Message):
        """
        Called when a message is deleted.
        Logs the deletion to the audit channel.
        """
        if message.author.bot:
            # Ignore bot messages
            return

        try:
            embed = discord.Embed(
                title="Message Deleted",
                description=f"Channel: {message.channel.mention}",
                timestamp=datetime.datetime.now(),
                color=discord.Colour.from_rgb(255, 0, 0)
            )
            embed.set_footer(text=f"Deleted by: {message.author.name}#{message.author.discriminator}")
            embed.add_field(name="Content", value=message.content or "*Empty*", inline=False)

            audit_channel = await self.get_audit_channel()
            await audit_channel.send(embed=embed)
            logger.info(f"Logged message deletion by {message.author.name} in {message.channel.name}")
        except Exception as e:
            logger.error(f"Error logging message deletion: {e}")

    async def get_audit_channel(self):
        """
        Fetches the audit log channel from the configuration.
        """
        try:
            audit_channel_id = Configuration.get("channels.audit-log")
            if not audit_channel_id:
                raise ValueError("Audit log channel ID is not set in configuration.")
            channel = await self.server.fetch_channel(audit_channel_id)
            return channel
        except Exception as e:
            logger.error(f"Error fetching audit log channel: {e}")
            raise
