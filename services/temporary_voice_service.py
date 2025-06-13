import discord
import asyncio
import time
from datetime import datetime
from configuration import Configuration
from service import Service
from utils.logger import get_logger

logger = get_logger("temporary_voice_service")

def __service__():
    return TemporaryVoiceService()

class TemporaryVoiceService(Service):
    def __init__(self):
        super().__init__()
        config = Configuration.get("services.temporary_voice", {})
        self.creator_channel_id = config.get("creator_channel")
        self.log_channel_id = config.get("log_channel")
        self.category_id = config.get("category")
        self.cooldown = config.get("cooldown", 3600)
        self.default_slots = config.get("default_slots", 5)
        
        # Get role IDs from configuration
        self.host_role_id = Configuration.get("roles.host")
        self.student_role_id = Configuration.get("roles.student")
        
        self.temp_channels = {}
        self.user_cooldowns = {}

    def __start__(self):
        if not all([self.creator_channel_id, self.log_channel_id, self.category_id]):
            logger.error("Temporary Voice Service configuration incomplete!")
        logger.info("TemporaryVoiceService started!")

    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        try:
            # Handle channel creation
            if after.channel and after.channel.id == self.creator_channel_id:
                await self._create_temp_channel(member)

            # Handle channel cleanup
            if before.channel and before.channel.id in self.temp_channels.values():
                await self._cleanup_empty_channel(before.channel)

        except Exception as e:
            logger.error(f"Error handling voice state update: {e}")

    async def _create_temp_channel(self, member: discord.Member):
        if self._is_in_cooldown(member):
            await self._notify_cooldown(member)
            return

        try:
            guild = member.guild
            host_role = guild.get_role(self.host_role_id)
            student_role = guild.get_role(self.student_role_id)

            # Base permissions
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=False),
                host_role: discord.PermissionOverwrite(
                    connect=True,
                    manage_channels=True,
                    move_members=True
                ),
                student_role: discord.PermissionOverwrite(
                    connect=True,
                    speak=True
                ),
                member: discord.PermissionOverwrite(
                    manage_channels=True
                )
            }

            # Create category if not exists
            category = guild.get_channel(self.category_id)
            if not category:
                category = await guild.create_category("Temporary Channels")

            # Create voice channel
            new_channel = await category.create_voice_channel(
                name=f"{member.display_name}'s Room",
                overwrites=overwrites,
                user_limit=self.default_slots
            )

            await member.move_to(new_channel)
            self.temp_channels[member.id] = new_channel.id
            self.user_cooldowns[member.id] = time.time()
            
            await self._send_creation_log(member, new_channel)

        except Exception as e:
            logger.error(f"Error creating temp channel: {e}")
            await member.send("❌ Failed to create voice channel. Please contact staff.")

    def _is_in_cooldown(self, member: discord.Member) -> bool:
        last_created = self.user_cooldowns.get(member.id, 0)
        return (time.time() - last_created) < self.cooldown

    async def _notify_cooldown(self, member: discord.Member):
        try:
            remaining = self.cooldown - (time.time() - self.user_cooldowns[member.id])
            await member.send(
                f"You can create another voice channel in {int(remaining // 3600)} hours "
                f"and {int((remaining % 3600) // 60)} minutes."
            )
        except discord.Forbidden:
            logger.warning(f"Couldn't send cooldown DM to {member.id}")

    async def _cleanup_empty_channel(self, channel: discord.VoiceChannel):
        try:
            if len(channel.members) == 0:
                # Wait 60 seconds before deleting to prevent race conditions
                await asyncio.sleep(60)
                if len(channel.members) == 0:
                    await channel.delete()
                    # Remove from tracking
                    for uid, cid in list(self.temp_channels.items()):
                        if cid == channel.id:
                            del self.temp_channels[uid]
        except Exception as e:
            logger.error(f"Error cleaning up channel: {e}")

    async def _send_creation_log(self, member: discord.Member, channel: discord.VoiceChannel):
        log_channel = self.server.get_channel(self.log_channel_id)
        if log_channel:
            embed = discord.Embed(
                title="🎧 New Temporary Voice Channel Created",
                color=discord.Color.blurple(),
                timestamp=datetime.now()
            )
            embed.add_field(name="User", value=member.mention, inline=True)
            embed.add_field(name="Channel", value=channel.mention, inline=True)
            embed.add_field(
                name="Instructions", 
                value="• You have full control over this channel\n"
                      "• Default limit is 5 users\n"
                      "• Channel will auto-delete when empty\n"
                      "• You can create another channel in 1 hour",
                inline=False
            )
            await log_channel.send(embed=embed)