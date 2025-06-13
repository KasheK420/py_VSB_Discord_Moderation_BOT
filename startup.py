import importlib
import os
import discord
from discord import app_commands
from configuration import Configuration
from utils.logger import get_logger

# Initialize logger
logger = get_logger("vsb")

# Check for the bot token
if os.environ.get("DISCORD_TOKEN") is None:
    logger.error("DISCORD_TOKEN environment variable not set.")
    exit(1)

# Discord client setup
intents = discord.Intents.all()
client = discord.Client(intents=intents)
commands = app_commands.CommandTree(client)

# Load configuration
Configuration.get_instance()

# Service loading
services = []
service_whitelist = os.environ.get("SERVICE_WHITELIST")
if service_whitelist is not None:
    service_whitelist = list(map(str.strip, service_whitelist.split(",")))

for file in os.listdir("services"):
    if not file.endswith(".py") or file.startswith("_"):
        continue

    service_name = file[:-3]
    if service_whitelist and service_name not in service_whitelist:
        continue

    logger.info(f"Loading service {service_name}...")
    try:
        lib = importlib.import_module(f".{service_name}", "services")
        service_class = lib.__service__()
        service_class.client = client
        service_class.commands = commands
        services.append(service_class)
        service_class.__register_commands__()
    except Exception as e:
        logger.error(f"Failed to load service {service_name}: {e}")

# Client events
@client.event
async def on_ready():
    logger.info("Syncing slash commands with Discord...")
    try:
        await commands.sync()
        logger.info("Slash commands synced successfully.")
    except Exception as e:
        logger.error(f"Error syncing slash commands: {e}")

    logger.info("Syncing servers...")
    client.fetch_guilds(limit=1)

    logger.info("Syncing channels...")
    await client.guilds[0].fetch_channels()

    logger.info("Starting services...")
    for service in services:
        try:
            service.__start__()
            await service.on_ready()
        except Exception as e:
            logger.error(f"Failed to initialize service {service.__class__.__name__}: {e}")

    # Set bot presence
    activity = discord.Game(name="Monitoring the server 🚀")
    await client.change_presence(status=discord.Status.online, activity=activity)

    logger.info(f"Bot ready. Services loaded: {len(services)}")

# Import events
importlib.import_module("events")

# Run the bot
client.run(os.environ.get("DISCORD_TOKEN"))
