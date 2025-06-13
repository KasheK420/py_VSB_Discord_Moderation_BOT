import asyncio

import discord

from ..configuration import Configuration
from ..service import Service
from ..utils.logger import get_logger

# Initialize logger for this service
logger = get_logger("meme_antitext_service")


def __service__():
    return MemeAntiTextService()


class MemeAntiTextService(Service):
    async def on_ready(self):
        logger.info("MemeAntiTextService is ready!")

    async def on_message(self, message: discord.Message):
        await MemeAntiTextService.check_for_validity(message)

    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        await MemeAntiTextService.check_for_validity(after)

    @staticmethod
    async def check_for_validity(message: discord.Message):
        if message.channel.id != Configuration.get("channels.meme"):
            return

        await asyncio.sleep(1)  # Introduces a delay to ensure the message is fetched
        await message.fetch()
        if (
            len(message.attachments) > 0
            and (
                message.attachments[0].content_type.startswith("image/")
                or message.attachments[0].content_type.startswith("video/")
            )
        ) or (len(message.embeds) > 0 and message.embeds[0].type in ["video", "image", "gifv"]):
            return

        await message.delete()
        logger.info(f"Deleted message in meme channel from {message.author.display_name}: {message.content}")
        # TODO: Hall of Shame message
        # TODO: Custom-made slow-mode
