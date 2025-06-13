import discord

from .startup import client
from .startup import services

# ----------------------------------------------------------------------
# MESSAGE EVENTS
# ----------------------------------------------------------------------


@client.event
async def on_message(message: discord.Message):
    """
    Triggered when a message is sent in a channel.
    Handles commands, moderation, and other message-based services.
    """
    for service in services:
        await service.on_message(message)


@client.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    """
    Triggered when a message is edited.
    Useful for moderation, logging, or tracking edits.
    """
    for service in services:
        await service.on_message_edit(before, after)


@client.event
async def on_message_delete(message: discord.Message):
    """
    Triggered when a message is deleted.
    Useful for moderation or message logging.
    """
    for service in services:
        await service.on_message_delete(message)


# ----------------------------------------------------------------------
# MEMBER EVENTS
# ----------------------------------------------------------------------


@client.event
async def on_member_join(member: discord.Member):
    """
    Triggered when a new member joins the server.
    Handles welcome messages, auto-roles, or tracking new users.
    """
    for service in services:
        await service.on_member_join(member)


@client.event
async def on_member_remove(member: discord.Member):
    """
    Triggered when a member leaves or is kicked from the server.
    Useful for farewell messages or tracking member removals.
    """
    for service in services:
        await service.on_member_remove(member)


@client.event
async def on_member_update(before: discord.Member, after: discord.Member):
    """
    Triggered when a member's profile is updated (e.g., nickname, roles).
    Useful for role tracking or monitoring profile changes.
    """
    for service in services:
        await service.on_member_update(before, after)


# ----------------------------------------------------------------------
# REACTION EVENTS
# ----------------------------------------------------------------------


@client.event
async def on_reaction_add(reaction: discord.Reaction, user: discord.User):
    """
    Triggered when a reaction is added to a message.
    Useful for reaction roles or tracking user reactions.
    """
    for service in services:
        await service.on_reaction_add(reaction, user)


@client.event
async def on_reaction_remove(reaction: discord.Reaction, user: discord.User):
    """
    Triggered when a reaction is removed from a message.
    Useful for reaction roles or tracking reaction removal.
    """
    for service in services:
        await service.on_reaction_remove(reaction, user)


# ----------------------------------------------------------------------
# VOICE EVENTS
# ----------------------------------------------------------------------


@client.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """
    Triggered when a user's voice state changes (e.g., joins/leaves a voice channel, mutes/unmutes).
    Useful for tracking voice channel activity or managing voice-related events.
    """
    for service in services:
        await service.on_voice_state_update(member, before, after)


# ----------------------------------------------------------------------
# CHANNEL EVENTS
# ----------------------------------------------------------------------


@client.event
async def on_guild_channel_create(channel: discord.abc.GuildChannel):
    """
    Triggered when a new channel is created.
    Useful for logging or automated channel setup.
    """
    for service in services:
        await service.on_guild_channel_create(channel)


@client.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    """
    Triggered when a channel is deleted.
    Useful for logging channel deletions or cleanup tasks.
    """
    for service in services:
        await service.on_guild_channel_delete(channel)


@client.event
async def on_guild_channel_update(before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
    """
    Triggered when a channel's settings are updated.
    Useful for tracking changes to channel settings.
    """
    for service in services:
        await service.on_guild_channel_update(before, after)


# ----------------------------------------------------------------------
# GUILD (SERVER) EVENTS
# ----------------------------------------------------------------------


@client.event
async def on_guild_join(guild: discord.Guild):
    """
    Triggered when the bot joins a new guild (server).
    Useful for initialization or welcome messages for guild admins.
    """
    for service in services:
        await service.on_guild_join(guild)


@client.event
async def on_guild_remove(guild: discord.Guild):
    """
    Triggered when the bot is removed from a guild.
    Useful for cleanup tasks or logging.
    """
    for service in services:
        await service.on_guild_remove(guild)


@client.event
async def on_guild_update(before: discord.Guild, after: discord.Guild):
    """
    Triggered when a guild's settings are updated.
    Useful for tracking server-level changes.
    """
    for service in services:
        await service.on_guild_update(before, after)


# ----------------------------------------------------------------------
# ROLE EVENTS
# ----------------------------------------------------------------------


@client.event
async def on_guild_role_create(role: discord.Role):
    """
    Triggered when a new role is created.
    Useful for logging role creation or automated role setup.
    """
    for service in services:
        await service.on_guild_role_create(role)


@client.event
async def on_guild_role_delete(role: discord.Role):
    """
    Triggered when a role is deleted.
    Useful for logging or role cleanup tasks.
    """
    for service in services:
        await service.on_guild_role_delete(role)


@client.event
async def on_guild_role_update(before: discord.Role, after: discord.Role):
    """
    Triggered when a role's settings are updated.
    Useful for tracking role changes or managing permissions.
    """
    for service in services:
        await service.on_guild_role_update(before, after)


# ----------------------------------------------------------------------
# MODERATION EVENTS
# ----------------------------------------------------------------------


@client.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    """
    Triggered when a user is banned from the guild.
    Useful for logging bans or notifying staff members.
    """
    for service in services:
        await service.on_member_ban(guild, user)


@client.event
async def on_member_unban(guild: discord.Guild, user: discord.User):
    """
    Triggered when a user is unbanned from the guild.
    Useful for logging unbans or notifying staff members.
    """
    for service in services:
        await service.on_member_unban(guild, user)
