# bot/cogs/gambling_cog.py
from __future__ import annotations
import secrets
import random
import logging
from typing import List, Tuple

import discord
from discord.ext import commands
from discord import app_commands, Interaction

from bot.database.database_service import database_service
from bot.database.queries.economy_queries import EconomyQueries
from bot.services.logging_service import LogLevel

logger = logging.getLogger(__name__)

# --------- Slots configuration ---------
SYMBOLS = [
    {"emoji": "🍒", "weight": 28, "pay": {3: 5,  4: 10, 5: 25}},
    {"emoji": "🍋", "weight": 26, "pay": {3: 5,  4: 10, 5: 20}},
    {"emoji": "🍇", "weight": 22, "pay": {3: 8,  4: 15, 5: 30}},
    {"emoji": "🔔", "weight": 14, "pay": {3: 10, 4: 25, 5: 50}},
    {"emoji": "⭐",  "weight": 7,  "pay": {3: 15, 4: 40, 5: 80}},
    {"emoji": "7️⃣", "weight": 2,  "pay": {3: 25, 4: 100,5: 250}},
    {"emoji": "💎", "weight": 1,  "pay": {3: 50, 4: 200,5: 500}},
]
# 10 typických výplatních linií přes 5 válců a 4 řádky (0..3)
PAYLINES = [
    [(0,0),(1,0),(2,0),(3,0),(4,0)],
    [(0,1),(1,1),(2,1),(3,1),(4,1)],
    [(0,2),(1,2),(2,2),(3,2),(4,2)],
    [(0,3),(1,3),(2,3),(3,3),(4,3)],
    [(0,0),(1,1),(2,2),(3,1),(4,0)],
    [(0,3),(1,2),(2,1),(3,2),(4,3)],
    [(0,1),(1,0),(2,1),(3,2),(4,3)],
    [(0,2),(1,3),(2,2),(3,1),(4,0)],
    [(0,1),(1,2),(2,3),(3,2),(4,1)],
    [(0,2),(1,1),(2,0),(3,1),(4,2)],
]
NUM_REELS = 5
NUM_ROWS = 4
NUM_LINES = len(PAYLINES)

def _weighted_symbol() -> str:
    population = [s["emoji"] for s in SYMBOLS]
    weights = [s["weight"] for s in SYMBOLS]
    return random.choices(population, weights=weights, k=1)[0]

def spin_slots() -> List[List[str]]:
    """4 řádky × 5 sloupců grid."""
    return [[_weighted_symbol() for _ in range(NUM_REELS)] for __ in range(NUM_ROWS)]

def evaluate_grid(grid: List[List[str]], bet_per_line: int) -> Tuple[int, List[str]]:
    """Vrací (celková výhra v bodech, list popisů výher na jednotlivých liniích)."""
    def symbol_pay(emoji: str, n: int) -> int:
        for s in SYMBOLS:
            if s["emoji"] == emoji:
                return s["pay"].get(n, 0)
        return 0

    total_win = 0
    descs: List[str] = []

    for idx, line in enumerate(PAYLINES, 1):
        first = grid[line[0][1]][line[0][0]]
        run = 1
        for (x,y) in line[1:]:
            if grid[y][x] == first:
                run += 1
            else:
                break
        if run >= 3:
            base = symbol_pay(first, run)
            payout = base * bet_per_line
            total_win += payout
            descs.append(f"L{idx}: {first} ×{run} → +{payout}")
    return total_win, descs

def grid_to_art(grid: List[List[str]]) -> str:
    # jednoduché monospaced vykreslení 4x5 s rámečky
    col = NUM_REELS
    row = NUM_ROWS
    top = "┌" + "───────┬"*(col-1) + "───────┐"
    mid = "├" + "───────┼"*(col-1) + "───────┤"
    bot = "└" + "───────┴"*(col-1) + "───────┘"
    lines = [top]
    for r in range(row):
        cells = "│ " + " │ ".join(grid[r][c] for c in range(col)) + " │"
        lines.append(cells)
        if r < row-1:
            lines.append(mid)
    lines.append(bot)
    return "```\n" + "\n".join(lines) + "\n```"

# ---------- Balance helpers ----------
async def get_points(user_id: int) -> int:
    st = await EconomyQueries.get_stats(database_service.pool, user_id)
    return int(st["points"]) if st and "points" in st else 0

def fmt_delta(v: int) -> str:
    return f"{v:+d}"

# ---------- Gambling Cog ----------
class GamblingCog(commands.Cog):
    """Gambling: balance, dice panel, slots panel. Výsledky a sázky přes body z Economy."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.embed_logger = getattr(bot, "embed_logger", None)
        self.channel_id = getattr(bot.config, "gambling_channel_id", 0)
        # reuse slots min/max for dice too
        self.min_bpl = getattr(bot.config, "slots_min_bet_per_line", 1)
        self.max_bpl = getattr(bot.config, "slots_max_bet_per_line", 50)

    async def cog_load(self):
        pass

    def _check_channel(self, itx: Interaction) -> bool:
        return self.channel_id == 0 or itx.channel_id == self.channel_id

    # Group
    group = app_commands.Group(name="gamble", description="Hry o body")

    # -------- Balance ----------
    @group.command(name="balance", description="Zobrazí tvůj zůstatek bodů")
    async def gamble_balance(self, itx: Interaction):
        if not self._check_channel(itx):
            return await itx.response.send_message("Použij prosím vyhrazený gambling kanál.", ephemeral=True)
        await itx.response.defer(ephemeral=True)
        pts = await get_points(itx.user.id)
        await itx.followup.send(f"💰 **Zůstatek:** {pts} bodů", ephemeral=True)

    # Alias
    @group.command(name="wallet", description="Alias pro balance — zůstatek bodů")
    async def gamble_wallet(self, itx: Interaction):
        await self.gamble_balance(itx)

    # -------- Dice (panel) ----------
    @group.command(name="dice", description="Otevře panel pro kostku: nastav sázku a vyber číslo (1–6).")
    async def gamble_dice(self, itx: Interaction):
        if not self._check_channel(itx):
            return await itx.response.send_message("Použij prosím vyhrazený gambling kanál.", ephemeral=True)

        pts = await get_points(itx.user.id)
        view = DiceView(self, itx.user.id, self.min_bpl, self.max_bpl, initial_balance=pts)
        await itx.response.send_message(
            view.status_text(),
            view=view,
            ephemeral=True
        )

    # -------- Slots (panel) ----------
    @group.command(name="slots", description="Slot machine 4×5 (10 linií). Otevře ovládací panel.")
    async def gamble_slots(self, itx: Interaction):
        if not self._check_channel(itx):
            return await itx.response.send_message("Použij prosím vyhrazený gambling kanál.", ephemeral=True)

        pts = await get_points(itx.user.id)
        view = SlotsView(self, itx.user.id, self.min_bpl, self.max_bpl, initial_balance=pts)
        await itx.response.send_message(
            view.status_text(),
            view=view,
            ephemeral=True
        )

# ---------- Safe interaction mixin ----------
class _SafeView(discord.ui.View):
    async def _safe_edit(self, interaction: Interaction, *, content: str, view: discord.ui.View | None = None):
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(content=content, view=view)
            else:
                await interaction.response.edit_message(content=content, view=view)
        except discord.HTTPException:
            await self._safe_send(interaction, content, ephemeral=True)

    async def _safe_send(self, interaction: Interaction, content: str, *, ephemeral: bool = False):
        try:
            if interaction.response.is_done():
                await interaction.followup.send(content, ephemeral=ephemeral)
            else:
                await interaction.response.send_message(content, ephemeral=ephemeral)
        except discord.HTTPException:
            pass

# ---------- Dice View ----------
class DiceView(_SafeView):
    def __init__(self, cog: GamblingCog, user_id: int, min_bet: int, max_bet: int, initial_balance: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.bet = max(min_bet, min(5, max_bet))  # default
        self.min_bet = min_bet
        self.max_bet = max_bet
        self.guess = 3
        self.balance = initial_balance

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await self._safe_send(interaction, "Tohle není tvoje session.", ephemeral=True)
            return False
        return True

    def status_text(self) -> str:
        return (
            f"🎲 **Kostka** — vyber číslo a vsaď.\n"
            f"Číslo: **{self.guess}**  •  Sázka: **{self.bet}**\n"
            f"💰 Zůstatek: **{self.balance}** bodů\n"
            f"Výhra při zásahu: **{self.bet * 6}** (6× vklad)"
        )

    # --- Buttons ---

    @discord.ui.button(label="-", style=discord.ButtonStyle.secondary)
    async def minus(self, interaction: Interaction, button: discord.ui.Button):
        self.bet = max(self.min_bet, self.bet - 1)
        await self._safe_edit(interaction, content=self.status_text(), view=self)

    @discord.ui.button(label="+", style=discord.ButtonStyle.secondary)
    async def plus(self, interaction: Interaction, button: discord.ui.Button):
        self.bet = min(self.max_bet, self.bet + 1)
        await self._safe_edit(interaction, content=self.status_text(), view=self)

    # quick number buttons
    @discord.ui.button(label="1", style=discord.ButtonStyle.primary)
    async def g1(self, interaction: Interaction, button: discord.ui.Button):
        self.guess = 1
        await self._safe_edit(interaction, content=self.status_text(), view=self)

    @discord.ui.button(label="2", style=discord.ButtonStyle.primary)
    async def g2(self, interaction: Interaction, button: discord.ui.Button):
        self.guess = 2
        await self._safe_edit(interaction, content=self.status_text(), view=self)

    @discord.ui.button(label="3", style=discord.ButtonStyle.primary)
    async def g3(self, interaction: Interaction, button: discord.ui.Button):
        self.guess = 3
        await self._safe_edit(interaction, content=self.status_text(), view=self)

    @discord.ui.button(label="4", style=discord.ButtonStyle.primary)
    async def g4(self, interaction: Interaction, button: discord.ui.Button):
        self.guess = 4
        await self._safe_edit(interaction, content=self.status_text(), view=self)

    @discord.ui.button(label="5", style=discord.ButtonStyle.primary)
    async def g5(self, interaction: Interaction, button: discord.ui.Button):
        self.guess = 5
        await self._safe_edit(interaction, content=self.status_text(), view=self)

    @discord.ui.button(label="6", style=discord.ButtonStyle.primary)
    async def g6(self, interaction: Interaction, button: discord.ui.Button):
        self.guess = 6
        await self._safe_edit(interaction, content=self.status_text(), view=self)

    @discord.ui.button(label="ROLL", style=discord.ButtonStyle.success)
    async def roll(self, interaction: Interaction, button: discord.ui.Button):
        # Refresh balance
        self.balance = await get_points(interaction.user.id)
        if self.bet > self.balance:
            return await self._safe_send(interaction, f"Nedostatek bodů. Zůstatek: {self.balance}, potřeba: {self.bet}.", ephemeral=True)

        # Deduct bet
        try:
            await EconomyQueries.spend_points(database_service.pool, interaction.user.id, self.bet, meta=f"gamble:dice:bet:{self.guess}")
        except Exception:
            self.balance = await get_points(interaction.user.id)
            return await self._safe_send(interaction, f"Nedostatek bodů. Zůstatek: {self.balance}.", ephemeral=True)

        # Roll
        roll = secrets.choice([1,2,3,4,5,6])
        win = self.bet * 6 if roll == self.guess else 0
        if win > 0:
            await EconomyQueries.award_points(database_service.pool, interaction.user.id, win, meta="gamble:dice:win")

        # New balance
        self.balance = await get_points(interaction.user.id)
        delta = win - self.bet
        msg = (
            f"🎲 Kostka: **{roll}**  |  Tip: **{self.guess}**\n"
            f"Vklad: **{self.bet}**  •  Výhra: **{win}**  •  Bilance: **{fmt_delta(delta)}**\n"
            f"💰 Nový zůstatek: **{self.balance}** bodů\n\n"
            f"(Můžeš hrát dál – uprav sázku/číslo a znovu **ROLL**.)"
        )
        await self._safe_edit(interaction, content=msg + "\n\n" + self.status_text(), view=self)

        if self.cog.embed_logger:
            await self.cog.embed_logger.log_custom(
                service="Gambling",
                title="Dice roll",
                description=f"user={interaction.user} guess={self.guess} bet={self.bet} roll={roll} win={win}",
                level=LogLevel.INFO,
            )

    @discord.ui.button(label="Zavřít", style=discord.ButtonStyle.danger)
    async def close(self, interaction: Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await self._safe_edit(interaction, content="🎲 Uzavřeno.", view=self)

# ---------- Slots View ----------
class SlotsView(_SafeView):
    def __init__(self, cog: GamblingCog, user_id: int, min_bpl: int, max_bpl: int, initial_balance: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.bet_per_line = min_bpl
        self.min_bpl = min_bpl
        self.max_bpl = max_bpl
        self.balance = initial_balance

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await self._safe_send(interaction, "Tohle není tvoje session.", ephemeral=True)
            return False
        return True

    def status_text(self) -> str:
        total = self.bet_per_line * NUM_LINES
        return (
            f"🎰 **Slots** — {NUM_LINES} linií\n"
            f"Sázka na linii: **{self.bet_per_line}**  •  Celkový vklad: **{total}**\n"
            f"💰 Zůstatek: **{self.balance}** bodů"
        )

    @discord.ui.button(label="-", style=discord.ButtonStyle.secondary)
    async def minus(self, interaction: Interaction, button: discord.ui.Button):
        self.bet_per_line = max(self.min_bpl, self.bet_per_line - 1)
        await self._safe_edit(interaction, content=self.status_text(), view=self)

    @discord.ui.button(label="+", style=discord.ButtonStyle.secondary)
    async def plus(self, interaction: Interaction, button: discord.ui.Button):
        self.bet_per_line = min(self.max_bpl, self.bet_per_line + 1)
        await self._safe_edit(interaction, content=self.status_text(), view=self)

    @discord.ui.button(label="SPIN", style=discord.ButtonStyle.success)
    async def spin(self, interaction: Interaction, button: discord.ui.Button):
        total_bet = self.bet_per_line * NUM_LINES

        # Refresh balance & check
        self.balance = await get_points(interaction.user.id)
        if total_bet > self.balance:
            return await self._safe_send(interaction, f"Nedostatek bodů. Zůstatek: {self.balance}, potřeba: {total_bet}.", ephemeral=True)

        # Deduct bet
        try:
            await EconomyQueries.spend_points(
                database_service.pool,
                interaction.user.id,
                total_bet,
                meta=f"gamble:slots:bet:{self.bet_per_line}x{NUM_LINES}",
            )
        except Exception:
            self.balance = await get_points(interaction.user.id)
            return await self._safe_send(interaction, f"Nedostatek bodů. Zůstatek: {self.balance}.", ephemeral=True)

        # Spin
        grid = spin_slots()
        win, line_descs = evaluate_grid(grid, self.bet_per_line)
        if win > 0:
            await EconomyQueries.award_points(database_service.pool, interaction.user.id, win, meta="gamble:slots:win")

        # New balance
        self.balance = await get_points(interaction.user.id)
        delta = win - total_bet

        art = grid_to_art(grid)
        lines_text = "\n".join(line_descs) if line_descs else "Žádná výherní linie tentokrát."
        summary = (
            f"Vklad: **{total_bet}**  •  Výhra: **{win}**  •  Bilance: **{fmt_delta(delta)}**\n"
            f"💰 Nový zůstatek: **{self.balance}** bodů"
        )

        await self._safe_edit(
            interaction,
            content=f"🎰 **SPIN** — sázka na linii **{self.bet_per_line}** (celkem {NUM_LINES} linií)\n{art}\n{lines_text}\n\n{summary}\n\n{self.status_text()}",
            view=self,
        )

        if self.cog.embed_logger:
            await self.cog.embed_logger.log_custom(
                service="Gambling",
                title="Slots spin",
                description=f"user={interaction.user} bpl={self.bet_per_line} total={total_bet} win={win}",
                level=LogLevel.INFO,
            )

    @discord.ui.button(label="Zavřít", style=discord.ButtonStyle.danger)
    async def close(self, interaction: Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await self._safe_edit(interaction, content="🎰 Uzavřeno.", view=self)
