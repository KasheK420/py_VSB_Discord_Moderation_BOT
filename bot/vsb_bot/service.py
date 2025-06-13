import discord

from abc import abstractmethod, ABC
from discord import app_commands


class Service(ABC):
    client: discord.Client = None
    server: discord.Guild = None
    commands: app_commands.CommandTree = None

    def __init__(self):
        pass

    def __start__(self):
        self.server = self.client.guilds[0]

    def __register_commands__(self):
        pass

    # EVENTS
    async def on_ready(self):
        pass

    # MESSAGE EVENTS
    async def on_message(self, message: discord.Message):
        pass

    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        pass

    async def on_message_delete(self, message: discord.Message):
        pass

    # MEMBER EVENTS
    async def on_member_join(self, member: discord.Member):
        pass

    async def on_member_remove(self, member: discord.Member):
        pass

    async def on_member_update(self, before: discord.Member, after: discord.Member):
        pass

    # REACTION EVENTS
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        pass

    async def on_reaction_remove(self, reaction: discord.Reaction, user: discord.User):
        pass

    # VOICE EVENTS
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        pass

    # CHANNEL EVENTS
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        pass

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        pass

    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        pass

    # GUILD (SERVER) EVENTS
    async def on_guild_join(self, guild: discord.Guild):
        pass

    async def on_guild_remove(self, guild: discord.Guild):
        pass

    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        pass

    # ROLE EVENTS
    async def on_guild_role_create(self, role: discord.Role):
        pass

    async def on_guild_role_delete(self, role: discord.Role):
        pass

    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        pass

    # MODERATION EVENTS
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        pass

    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        pass
