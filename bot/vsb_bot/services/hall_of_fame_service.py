import discord

from ..configuration import Configuration
from ..service import Service
from ..utils.logger import get_logger

logger = get_logger("hall_of_fame_service")

def __service__():
    return HallOfFameService()

class HallOfFameService(Service):
    def __init__(self):
        super().__init__()
        self.hof_channel_id = Configuration.get("services.hall_of_fame.channel")
        self.processed_messages = set()  # Track messages we've already handled

    def __start__(self):
        if not self.hof_channel_id:
            logger.error("Hall of Fame channel ID not configured!")
        logger.info("HallOfFameService started!")

    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        try:
            # Check if message has crossed the x reactions threshold
            if reaction.message.id in self.processed_messages:
                return

            total_reactions = sum(count.count for count in reaction.message.reactions)
            if total_reactions >= Configuration.get("services.hall_of_fame.threshold", 20):
                await self._process_hof_message(reaction.message)
                self.processed_messages.add(reaction.message.id)
        except Exception as e:
            logger.error(f"Error processing reaction: {e}")

    async def _process_hof_message(self, message: discord.Message):
        try:
            hof_channel = self.server.get_channel(self.hof_channel_id)
            if not hof_channel:
                logger.error(f"Hall of Fame channel {self.hof_channel_id} not found!")
                return

            embed = discord.Embed(
                title="🌟 Hall of Fame Entry",
                description=message.content,
                color=discord.Color.gold()
            )
            embed.set_author(
                name=message.author.display_name,
                icon_url=message.author.display_avatar.url
            )
            embed.add_field(
                name="Original Channel",
                value=message.channel.mention,
                inline=True
            )
            embed.add_field(
                name="Reactions",
                value=sum(r.count for r in message.reactions),
                inline=True
            )

            # Add attachments if present
            if message.attachments:
                embed.set_image(url=message.attachments[0].url)

            await hof_channel.send(embed=embed)
            logger.info(f"Added message {message.id} to Hall of Fame")
        except Exception as e:
            logger.error(f"Error processing Hall of Fame message: {e}")