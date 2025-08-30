# bot/cogs/shop_cog.py
from __future__ import annotations

import logging

import discord
from discord import Interaction, app_commands
from discord.ext import commands

from bot.database.database_service import database_service
from bot.database.queries.economy_queries import EconomyQueries
from bot.database.queries.shop_queries import ShopQueries
from bot.services.logging_service import LogLevel

logger = logging.getLogger(__name__)


class ShopCog(commands.Cog):
    """Jednoduchý shop: /shop list, /shop buy (odečte body), oznámí do kanálu s @ADMIN."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.embed_logger = getattr(bot, "embed_logger", None)
        self.announce_id = getattr(bot.config, "shop_announce_channel_id", 0)
        self.admin_role_id = getattr(bot.config, "admin_role_id", 0)

    async def cog_load(self):
        await ShopQueries.ensure_schema(database_service.pool)
        try:
            guild_obj = discord.Object(id=self.bot.config.guild_id)
            self.bot.tree.add_command(self.group, guild=guild_obj)
            await self.bot.tree.sync(guild=guild_obj)
        except Exception as e:
            logger.warning(f"Shop group sync: {e}")

    group = app_commands.Group(name="shop", description="Obchod s předměty")

    @group.command(name="list", description="Seznam položek v shopu")
    async def shop_list(self, itx: Interaction):
        await itx.response.defer(ephemeral=True)
        items = await ShopQueries.list_items(database_service.pool)
        if not items:
            return await itx.followup.send("Žádné položky zatím nejsou.", ephemeral=True)
        lines = []
        for it in items:
            lines.append(
                f"**#{it['id']}** — {it['name']} • **{it['price']} bodů** • skladem: {it['stock']}\n{(it['description'] or '')}"
            )
        await itx.followup.send("\n\n".join(lines)[:1950], ephemeral=True)

    @group.command(name="buy", description="Koupit položku")
    @app_commands.describe(item_id="ID položky", qty="Množství (default 1)")
    async def shop_buy(self, itx: Interaction, item_id: int, qty: int = 1):
        await itx.response.defer(ephemeral=True)
        # Validate item
        item = await ShopQueries.get_item(database_service.pool, item_id)
        if not item:
            return await itx.followup.send("Položka nenalezena.", ephemeral=True)
        if item["stock"] < qty:
            return await itx.followup.send("Nedostatečná zásoba.", ephemeral=True)

        total = int(item["price"]) * qty
        # Check and spend points
        try:
            await EconomyQueries.spend_points(
                database_service.pool, itx.user.id, total, meta=f"shop:buy:item#{item_id}x{qty}"
            )
        except Exception:
            return await itx.followup.send("Nedostatek bodů.", ephemeral=True)

        # Reserve/record purchase
        try:
            order = await ShopQueries.purchase(database_service.pool, itx.user.id, item_id, qty)
        except Exception as e:
            # refund in case of race error
            await EconomyQueries.award_points(
                database_service.pool, itx.user.id, total, meta="shop:refund"
            )
            return await itx.followup.send(f"Objednávka se nezdařila: {e}", ephemeral=True)

        await itx.followup.send(
            f"✅ Objednávka **#{order['order_id']}** — {item['name']} ×{qty} • zaplaceno **{total}** bodů.\n"
            f"Administrátoři budou informováni.",
            ephemeral=True,
        )

        # Announce to channel
        ch = itx.guild.get_channel(self.announce_id) if self.announce_id else None
        if isinstance(ch, discord.TextChannel):
            admin_ping = f"<@&{self.admin_role_id}>" if self.admin_role_id else "@admin"
            emb = discord.Embed(
                title="🛒 Nová objednávka",
                description=f"{itx.user.mention} objednal/a **{item['name']}** ×{qty}",
                color=discord.Color.blurple(),
            )
            emb.add_field(name="Cena", value=f"{total} bodů", inline=True)
            emb.add_field(name="Objednávka", value=f"#{order['order_id']}", inline=True)
            await ch.send(content=admin_ping, embed=emb)

        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Shop",
                title="Order placed",
                description=f"user={itx.user} item#{item_id} qty={qty} price={total}",
                level=LogLevel.SUCCESS,
            )

    # --- Admin helper to add items ---
    @group.command(name="add", description="(Admin) Přidat položku do shopu")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(name="Název", price="Cena v bodech", stock="Sklad", description="Popis")
    async def shop_add(
        self, itx: Interaction, name: str, price: int, stock: int, description: str = ""
    ):
        await itx.response.defer(ephemeral=True)
        if price < 0 or stock < 0:
            return await itx.followup.send("Cena/stock nemůže být záporný.", ephemeral=True)
        item_id = await ShopQueries.add_item(
            database_service.pool, name, price, stock, description or None
        )
        await itx.followup.send(
            f"✅ Přidáno **#{item_id}** — {name} • {price} bodů (skladem {stock})", ephemeral=True
        )
