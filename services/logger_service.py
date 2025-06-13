import discord
from service import Service
from utils.logger import get_logger

# Initialize logger for this service
logger = get_logger("logger_service")


def __service__():
    return LoggerService()


class LoggerService(Service):
    async def on_ready(self):
        logger.info("HelloService is ready!")

    async def on_message(self, message: discord.Message):
        logger.info(f"ID: {message.id}, Author: {message.author.display_name}, Content: {message.content}")
