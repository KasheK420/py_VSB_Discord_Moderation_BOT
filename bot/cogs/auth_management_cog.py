"""
bot/cogs/auth_management_cog.py
Comprehensive authentication management system with yearly re-verification
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

import discord
from discord import app_commands
from discord.ext import commands, tasks

logger = logging.getLogger(__name__)


class AuthManagementCog(commands.Cog):
    """Manages yearly re-verification and authentication enforcement"""
    
    def __init__(self, bot, db_pool, config, embed_logger):
        self.bot = bot
        self.db_pool = db_pool
        self.config = config
        self.embed_logger = embed_logger
        
        # Paths for persistent storage
        self.role_backup_file = Path("data/role_backups.json")
        self.purge_state_file = Path("data/purge_state.json")
        
        # Create data directory
        self.role_backup_file.parent.mkdir(exist_ok=True)
        
        # In-memory caches
        self.role_backups: Dict[str, List[int]] = {}  # user_id -> [role_ids]
        self.purge_in_progress = False
        self.purge_queue: List[str] = []
        self.protected_roles: Set[int] = set()  # Roles that prevent de-verification
        
        # Load state
        self.load_state()
        
        # Start background tasks
        self.daily_check.start()
        self.purge_processor.start()
        
    def cog_unload(self):
        """Clean up when cog unloads"""
        self.daily_check.cancel()
        self.purge_processor.cancel()
        self.save_state()
        
    def load_state(self):
        """Load persistent state from files"""
        # Load role backups
        if self.role_backup_file.exists():
            with open(self.role_backup_file, 'r') as f:
                self.role_backups = json.load(f)
                
        # Load purge state
        if self.purge_state_file.exists():
            with open(self.purge_state_file, 'r') as f:
                state = json.load(f)
                self.purge_in_progress = state.get("in_progress", False)
                self.purge_queue = state.get("queue", [])
                
        # Set protected roles from config
        self.protected_roles = {
            self.config.admin_role_id,
            self.config.moderator_role_id,
            getattr(self.config, 'host_role_id', None),
            getattr(self.config, 'absolvent_role_id', None),
            getattr(self.config, 'vip_role_id', None),
        }
        self.protected_roles.discard(None)
        
    def save_state(self):
        """Save persistent state to files"""
        # Save role backups
        with open(self.role_backup_file, 'w') as f:
            json.dump(self.role_backups, f)
            
        # Save purge state
        with open(self.purge_state_file, 'w') as f:
            json.dump({
                "in_progress": self.purge_in_progress,
                "queue": self.purge_queue
            }, f)
            
    def backup_user_roles(self, member: discord.Member):
        """Backup user's current roles before removal"""
        role_ids = [r.id for r in member.roles if r.id != member.guild.default_role.id]
        self.role_backups[str(member.id)] = role_ids
        self.save_state()
        
    async def restore_user_roles(self, member: discord.Member):
        """Restore user's backed up roles after re-verification"""
        user_id = str(member.id)
        if user_id not in self.role_backups:
            return
            
        guild = member.guild
        restored = []
        
        for role_id in self.role_backups[user_id]:
            role = guild.get_role(role_id)
            if role and role not in member.roles:
                try:
                    await member.add_roles(role)
                    restored.append(role.name)
                except:
                    pass
                    
        if restored:
            logger.info(f"Restored roles for {member.id}: {', '.join(restored)}")
            
        # Clean up backup
        del self.role_backups[user_id]
        self.save_state()
        
    async def notify_user(self, user_id: str, message: str, embed: Optional[discord.Embed] = None):
        """Notify user via DM, fallback to channel ping"""
        try:
            user = await self.bot.fetch_user(int(user_id))
            await user.send(message, embed=embed)
            logger.info(f"Sent DM to user {user_id}")
            return True
        except:
            # DM failed, try channel ping
            try:
                guild = self.bot.get_guild(int(self.config.guild_id))
                channel = guild.get_channel(int(self.config.verification_channel_id))
                
                if channel:
                    msg = await channel.send(f"<@{user_id}> {message}", embed=embed)
                    # Delete after 5 seconds (they see ping but message disappears)
                    await asyncio.sleep(5)
                    await msg.delete()
                    logger.info(f"Pinged user {user_id} in channel")
                    return True
            except:
                pass
                
        logger.warning(f"Failed to notify user {user_id}")
        return False
        
    def is_protected(self, member: discord.Member) -> bool:
        """Check if member has protected roles"""
        return any(role.id in self.protected_roles for role in member.roles)
        
    async def remove_verification(self, member: discord.Member, backup_roles: bool = True):
        """Remove verification from a member"""
        if backup_roles:
            self.backup_user_roles(member)
            
        # Remove student/teacher roles
        roles_to_remove = []
        if hasattr(self.config, 'student_role_id'):
            role = member.guild.get_role(self.config.student_role_id)
            if role in member.roles:
                roles_to_remove.append(role)
                
        if hasattr(self.config, 'teacher_role_id'):
            role = member.guild.get_role(self.config.teacher_role_id)
            if role in member.roles:
                roles_to_remove.append(role)
                
        # Remove all other roles except @everyone and protected
        for role in member.roles:
            if role != member.guild.default_role and role.id not in self.protected_roles:
                roles_to_remove.append(role)
                
        if roles_to_remove:
            await member.remove_roles(*roles_to_remove, reason="Yearly re-verification required")
            
        # Update database
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET activity = 0 WHERE id = $1",
                str(member.id)
            )
            
    @tasks.loop(hours=24)
    async def daily_check(self):
        """Daily check for August purge and pre-purge notifications"""
        now = datetime.now(timezone.utc)
        
        # Check if it's August 1st - start yearly purge
        if now.month == 8 and now.day == 1 and not self.purge_in_progress:
            await self.start_yearly_purge()
            
        # Check if it's July 1st - start 30-day warning
        if now.month == 7 and now.day == 1:
            await self.send_reverification_warnings()
            
    @tasks.loop(minutes=5)
    async def purge_processor(self):
        """Process purge queue gradually (100 users per 5 minutes)"""
        if not self.purge_in_progress or not self.purge_queue:
            return
            
        guild = self.bot.get_guild(int(self.config.guild_id))
        if not guild:
            return
            
        batch_size = 100
        batch = self.purge_queue[:batch_size]
        self.purge_queue = self.purge_queue[batch_size:]
        
        for user_id in batch:
            try:
                member = guild.get_member(int(user_id))
                if member and not self.is_protected(member):
                    await self.remove_verification(member)
                    await self.notify_user(
                        user_id,
                        "**Yearly Re-verification Required**\n\n"
                        "Your verification has expired. Please re-verify your VSB account to regain access.\n"
                        "Use the verification channel to authenticate again."
                    )
                    await asyncio.sleep(0.5)  # Rate limit
            except Exception as e:
                logger.error(f"Error processing purge for {user_id}: {e}")
                
        # Save progress
        self.save_state()
        
        # Check if done
        if not self.purge_queue:
            self.purge_in_progress = False
            self.save_state()
            logger.info("Yearly purge completed")
            
            if self.embed_logger:
                await self.embed_logger.log_system_event(
                    title="Yearly Purge Completed",
                    description="All non-protected users have been de-verified",
                    level="SUCCESS"
                )
                
    async def start_yearly_purge(self):
        """Start the yearly verification purge"""
        logger.info("Starting yearly verification purge")
        
        guild = self.bot.get_guild(int(self.config.guild_id))
        if not guild:
            return
            
        # Get all verified users from database
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM users WHERE activity = 1"
            )
            
        # Build purge queue
        self.purge_queue = []
        for row in rows:
            user_id = row['id']
            member = guild.get_member(int(user_id))
            if member and not self.is_protected(member):
                self.purge_queue.append(user_id)
                
        self.purge_in_progress = True
        self.save_state()
        
        logger.info(f"Purge queue built with {len(self.purge_queue)} users")
        
        if self.embed_logger:
            await self.embed_logger.log_system_event(
                title="Yearly Purge Started",
                description=f"Beginning de-verification of {len(self.purge_queue)} users",
                level="WARNING",
                fields=[
                    ("Total Users", str(len(self.purge_queue)), True),
                    ("Batch Size", "100 per 5 minutes", True),
                    ("Estimated Time", f"{len(self.purge_queue) / 100 * 5:.1f} minutes", True)
                ]
            )
            
    async def send_reverification_warnings(self):
        """Send 30-day warning before purge"""
        guild = self.bot.get_guild(int(self.config.guild_id))
        if not guild:
            return
            
        # Get users who haven't verified recently
        cutoff = datetime.now(timezone.utc) - timedelta(days=335)  # ~11 months
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM users WHERE activity = 1 AND (verified_at IS NULL OR verified_at < $1)",
                cutoff
            )
            
        notified = 0
        for row in rows:
            user_id = row['id']
            member = guild.get_member(int(user_id))
            
            if member and not self.is_protected(member):
                embed = discord.Embed(
                    title="⚠️ Verification Expiring Soon",
                    description=(
                        "Your VSB verification will expire in **30 days**.\n\n"
                        "Please re-verify before August 1st to maintain your access and roles.\n"
                        "You can verify now using the verification channel."
                    ),
                    color=discord.Color.yellow(),
                    timestamp=datetime.now(timezone.utc)
                )
                
                if await self.notify_user(user_id, "", embed=embed):
                    notified += 1
                    
                await asyncio.sleep(1)  # Rate limit
                
        logger.info(f"Sent {notified} re-verification warnings")
        
    # === SLASH COMMANDS ===
    
    @app_commands.command(name="force_reverify", description="Force user(s) to re-verify")
    @app_commands.describe(
        user="Specific user to force re-verify",
        all_users="Force ALL users to re-verify (dangerous!)"
    )
    async def force_reverify(self, interaction: discord.Interaction, 
                           user: Optional[discord.Member] = None,
                           all_users: bool = False):
        """Force re-verification for user(s)"""
        # Admin only
        if not any(role.id in {self.config.admin_role_id, self.config.moderator_role_id} 
                  for role in interaction.user.roles):
            await interaction.response.send_message("Insufficient permissions", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        
        if all_users:
            # Confirm dangerous action
            await interaction.followup.send(
                "⚠️ This will force ALL users to re-verify. Starting purge...",
                ephemeral=True
            )
            await self.start_yearly_purge()
            
        elif user:
            await self.remove_verification(user)
            await self.notify_user(
                str(user.id),
                "**Re-verification Required**\n\n"
                "An administrator has requested you to re-verify your VSB account.\n"
                "Please use the verification channel to authenticate."
            )
            await interaction.followup.send(f"Forced re-verification for {user.mention}", ephemeral=True)
            
        else:
            await interaction.followup.send("Please specify a user or use all_users=True", ephemeral=True)
            
    @app_commands.command(name="user_cas_info", description="View user's CAS attributes")
    @app_commands.describe(user="User to check")
    async def user_cas_info(self, interaction: discord.Interaction, user: discord.Member):
        """View user's CAS authentication data"""
        # Admin/Mod only
        if not any(role.id in {self.config.admin_role_id, self.config.moderator_role_id} 
                  for role in interaction.user.roles):
            await interaction.response.send_message("Insufficient permissions", ephemeral=True)
            return
            
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE id = $1",
                str(user.id)
            )
            
        if not row:
            await interaction.response.send_message("User not found in database", ephemeral=True)
            return
            
        # Build info embed
        embed = discord.Embed(
            title=f"CAS Info: {user.name}",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(name="Discord ID", value=row['id'], inline=True)
        embed.add_field(name="VSB Login", value=row['login'] or "N/A", inline=True)
        embed.add_field(name="Activity", value="✅ Active" if row['activity'] == 1 else "❌ Inactive", inline=True)
        embed.add_field(name="Type", value="Teacher" if row['type'] == 2 else "Student", inline=True)
        embed.add_field(name="Real Name", value=row['real_name'] or "N/A", inline=False)
        
        if row['verified_at']:
            embed.add_field(name="Verified At", value=row['verified_at'].strftime("%Y-%m-%d %H:%M UTC"), inline=True)
            
        # Parse attributes
        if row['attributes']:
            attrs = row['attributes']
            if isinstance(attrs, dict):
                # Show key CAS attributes
                cas_fields = ['mail', 'eduPersonAffiliation', 'groups', 'cn']
                for field in cas_fields:
                    if field in attrs:
                        value = attrs[field]
                        if isinstance(value, list):
                            value = ', '.join(value)
                        if value:
                            embed.add_field(name=field, value=str(value)[:1024], inline=False)
                            
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    @app_commands.command(name="restore_roles", description="Restore backed up roles for a user")
    @app_commands.describe(user="User to restore roles for")
    async def restore_roles(self, interaction: discord.Interaction, user: discord.Member):
        """Manually restore backed up roles"""
        # Admin only
        if self.config.admin_role_id not in [r.id for r in interaction.user.roles]:
            await interaction.response.send_message("Admin only command", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        
        if str(user.id) not in self.role_backups:
            await interaction.followup.send(f"No role backup found for {user.mention}", ephemeral=True)
            return
            
        await self.restore_user_roles(user)
        await interaction.followup.send(f"Restored roles for {user.mention}", ephemeral=True)
        
    @app_commands.command(name="purge_status", description="Check yearly purge status")
    async def purge_status(self, interaction: discord.Interaction):
        """Check status of yearly purge"""
        embed = discord.Embed(
            title="Yearly Purge Status",
            color=discord.Color.orange() if self.purge_in_progress else discord.Color.green()
        )
        
        embed.add_field(name="Status", value="🔄 In Progress" if self.purge_in_progress else "✅ Idle", inline=True)
        embed.add_field(name="Queue Size", value=str(len(self.purge_queue)), inline=True)
        embed.add_field(name="Role Backups", value=str(len(self.role_backups)), inline=True)
        
        if self.purge_in_progress and self.purge_queue:
            eta = len(self.purge_queue) / 100 * 5  # 100 per 5 minutes
            embed.add_field(name="Estimated Time", value=f"{eta:.1f} minutes", inline=True)
            
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    @app_commands.command(name="claim_role", description="Claim Host or Absolvent role")
    @app_commands.describe(role_type="Role to claim")
    @app_commands.choices(role_type=[
        app_commands.Choice(name="Host", value="host"),
        app_commands.Choice(name="Absolvent", value="absolvent")
    ])
    async def claim_role(self, interaction: discord.Interaction, role_type: str):
        """Allow users to claim Host or Absolvent roles"""
        user_id = str(interaction.user.id)
        
        # Check if user is verified
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT activity FROM users WHERE id = $1",
                user_id
            )
            
        if not row or row['activity'] != 1:
            await interaction.response.send_message(
                "You must be verified first before claiming special roles",
                ephemeral=True
            )
            return
            
        # Assign role
        if role_type == "host":
            role_id = getattr(self.config, 'host_role_id', None)
            role_name = "Host"
        else:
            role_id = getattr(self.config, 'absolvent_role_id', None)
            role_name = "Absolvent"
            
        if not role_id:
            await interaction.response.send_message(f"{role_name} role not configured", ephemeral=True)
            return
            
        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.response.send_message(f"{role_name} role not found", ephemeral=True)
            return
            
        if role in interaction.user.roles:
            await interaction.response.send_message(f"You already have the {role_name} role", ephemeral=True)
            return
            
        await interaction.user.add_roles(role)
        
        # Restore other roles if user had them backed up
        if user_id in self.role_backups:
            await self.restore_user_roles(interaction.user)
            
        await interaction.response.send_message(
            f"✅ You have been assigned the {role_name} role and your other roles have been restored",
            ephemeral=True
        )
        
        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Role Management",
                title=f"{role_name} Role Claimed",
                description=f"User claimed {role_name} role",
                level="INFO",
                fields={
                    "User": f"<@{user_id}>",
                    "Role": role_name,
                    "Roles Restored": "Yes" if user_id in self.role_backups else "No"
                }
            )


async def setup(bot):
    """Setup function for loading the cog"""