# bot/cogs/casino_cog.py
from __future__ import annotations

import asyncio
import hashlib
import random
import secrets

import discord
from discord import Interaction, app_commands
from discord.ext import commands, tasks

from bot.database.database_service import database_service
from bot.database.queries.economy_queries import EconomyQueries
from bot.services.logging_service import LogLevel


# ----------------- Helpers: economy -----------------
async def _get_points(user_id: int) -> int:
    st = await EconomyQueries.get_stats(database_service.pool, user_id)
    return int(st["points"]) if st and "points" in st else 0


# ----------------- Safe interaction View mixin -----------------
class _SafeView(discord.ui.View):
    async def _safe_edit(
        self,
        itx: Interaction,
        *,
        content: str | None = None,
        embed: discord.Embed | None = None,
        view: discord.ui.View | None = None,
    ):
        try:
            if itx.response.is_done():
                await itx.edit_original_response(content=content, embed=embed, view=view)
            else:
                await itx.response.edit_message(content=content, embed=embed, view=view)
        except discord.HTTPException:
            await self._safe_send(itx, content or "", embed=embed, ephemeral=True)

    async def _safe_send(
        self,
        itx: Interaction,
        content: str,
        *,
        embed: discord.Embed | None = None,
        ephemeral: bool = False,
    ):
        try:
            if itx.response.is_done():
                await itx.followup.send(content, embed=embed, ephemeral=ephemeral)
            else:
                await itx.response.send_message(content, embed=embed, ephemeral=ephemeral)
        except discord.HTTPException:
            pass


# ----------------- Cards/Blackjack -----------------
SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]


def _card_value(rank: str) -> list[int]:
    if rank == "A":
        return [1, 11]
    if rank in ("J", "Q", "K"):
        return [10]
    return [int(rank)]


def _hand_total(cards: list[str]) -> tuple[int, bool]:
    """
    Returns (best_total, is_blackjack)
    cards like "A♠", "10♦"
    """
    totals = [0]
    for c in cards:
        r = c[:-1] if c[:-1] != "" else c[0]
        vals = _card_value(r)
        new_totals = []
        for t in totals:
            for v in vals:
                new_totals.append(t + v)
        totals = new_totals
    # choose best <=21 if possible else smallest
    best = max([t for t in totals if t <= 21], default=min(totals))
    is_bj = (len(cards) == 2) and (best == 21)
    return best, is_bj


def _draw_deck(num_decks: int = 4) -> list[str]:
    deck = []
    for _ in range(num_decks):
        for s in SUITS:
            for r in RANKS:
                deck.append(f"{r}{s}")
    secrets.SystemRandom().shuffle(deck)
    return deck


def _cards_str(cards: list[str]) -> str:
    # fallback emoji style
    return " ".join(cards)


# ----------------- Casino Cog -----------------
class CasinoCog(commands.Cog):
    """Další casino hry (Blackjack, RPS, Coinflip, Mines) řízené přes embed & tlačítka (ephemeral)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.embed_logger = getattr(bot, "embed_logger", None)
        cfg = getattr(bot, "config", None)
        # limity – volitelné v configu, jinak default
        self.min_bet = getattr(cfg, "casino_min_bet", 1) if cfg else 1
        self.max_bet = getattr(cfg, "casino_max_bet", 1000) if cfg else 1000
        self.channel_id = getattr(cfg, "gambling_channel_id", 0) if cfg else 0
        # Lottery runtime (in-memory)
        self.lottery_ticket_price = getattr(cfg, "lottery_ticket_price", 10) if cfg else 10
        self.lottery_interval_minutes = getattr(cfg, "lottery_interval_minutes", 60) if cfg else 60
        self.lottery_announce_channel_id = (
            getattr(cfg, "lottery_announce_channel_id", 0) if cfg else 0
        )
        self.lottery_pool: int = 0
        self.lottery_tickets: dict[int, int] = {}

    # -------------- utility --------------
    def _check_channel(self, itx: Interaction) -> bool:
        return self.channel_id == 0 or itx.channel_id == self.channel_id

    def _lottery_build_status_embed(self, note: str = "") -> discord.Embed:
        total_tickets = sum(self.lottery_tickets.values())
        emb = discord.Embed(title="🎟️ Lottery / Jackpot", color=discord.Color.purple())
        emb.add_field(name="Cena losu", value=str(self.lottery_ticket_price))
        emb.add_field(name="V banku", value=str(self.lottery_pool))
        emb.add_field(name="Počet losů (celkem)", value=str(total_tickets))
        if note:
            emb.add_field(name="Info", value=note, inline=False)
        emb.set_footer(text=f"Losování každých {self.lottery_interval_minutes} min (in-memory).")
        return emb

    @tasks.loop(minutes=1)
    async def draw_lottery(self):
        # run only when interval elapsed
        # simplistic “tick” counter using task.current_loop
        try:
            if self.draw_lottery.current_loop % max(1, self.lottery_interval_minutes) != 0:
                return
        except Exception:
            return

        if not self.lottery_tickets:
            return  # nothing to draw

        # weighted pick
        tickets: list[tuple[int, int]] = list(self.lottery_tickets.items())  # (user_id, count)
        population = [uid for (uid, cnt) in tickets for _ in range(cnt)]
        winner = secrets.choice(population)
        prize = int(self.lottery_pool * 0.9)  # 90% to winner
        carry = self.lottery_pool - prize

        # pay
        if prize > 0:
            await EconomyQueries.award_points(
                database_service.pool, winner, prize, meta="lottery:win"
            )

        # announce
        chan_id = self.lottery_announce_channel_id or self.channel_id
        if chan_id:
            ch = self.bot.get_channel(chan_id)
            if isinstance(ch, discord.TextChannel):
                try:
                    u = self.bot.get_user(winner) or await self.bot.fetch_user(winner)
                    emb = discord.Embed(
                        title="🎉 Lottery — Výsledek losování",
                        description=f"Výherce: {u.mention if u else winner}\nVýhra: **{prize}** bodů\nZůstatek banku převeden: {carry} bodů",
                        color=discord.Color.purple(),
                    )
                    await ch.send(embed=emb)
                except Exception:
                    pass

        # reset round (carryover)
        self.lottery_pool = carry
        self.lottery_tickets.clear()

    # -------------- BLACKJACK --------------
    @app_commands.command(name="blackjack", description="Zahraj si blackjack (21).")
    @app_commands.describe(bet="Sázka v bodech")
    async def blackjack(self, itx: Interaction, bet: int):
        if not self._check_channel(itx):
            return await itx.response.send_message(
                "Použij prosím vyhrazený gambling kanál.", ephemeral=True
            )
        if bet < self.min_bet or bet > self.max_bet:
            return await itx.response.send_message(
                f"Sázka musí být mezi {self.min_bet} a {self.max_bet}.", ephemeral=True
            )

        # Balance check
        bal = await _get_points(itx.user.id)
        if bal < bet:
            return await itx.response.send_message(
                f"Nedostatek bodů. Zůstatek: {bal}.", ephemeral=True
            )

        # Spend initial bet
        try:
            await EconomyQueries.spend_points(
                database_service.pool, itx.user.id, bet, meta="blackjack:bet"
            )
        except Exception:
            bal = await _get_points(itx.user.id)
            return await itx.response.send_message(
                f"Nedostatek bodů. Zůstatek: {bal}.", ephemeral=True
            )

        # Create game view
        view = BlackjackView(self, itx.user.id, initial_bet=bet)
        await view.start_game()

        await itx.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

        if self.embed_logger:
            await self.embed_logger.log_custom(
                service="Casino",
                title="Blackjack started",
                description=f"user={itx.user} bet={bet}",
                level=LogLevel.INFO,
            )

    # -------------- RPS (rock-paper-scissors) --------------
    @app_commands.command(name="rps", description="Kámen–Nůžky–Papír o body.")
    @app_commands.describe(bet="Sázka v bodech")
    async def rps(self, itx: Interaction, bet: int):
        if not self._check_channel(itx):
            return await itx.response.send_message(
                "Použij prosím vyhrazený gambling kanál.", ephemeral=True
            )
        if bet < self.min_bet or bet > self.max_bet:
            return await itx.response.send_message(
                f"Sázka musí být mezi {self.min_bet} a {self.max_bet}.", ephemeral=True
            )

        bal = await _get_points(itx.user.id)
        if bal < bet:
            return await itx.response.send_message(
                f"Nedostatek bodů. Zůstatek: {bal}.", ephemeral=True
            )

        try:
            await EconomyQueries.spend_points(
                database_service.pool, itx.user.id, bet, meta="rps:bet"
            )
        except Exception:
            bal = await _get_points(itx.user.id)
            return await itx.response.send_message(
                f"Nedostatek bodů. Zůstatek: {bal}.", ephemeral=True
            )

        view = RPSView(self, itx.user.id, bet)
        emb = view.build_embed(state="Vyber si: ✊/✋/✌️")
        await itx.response.send_message(embed=emb, view=view, ephemeral=True)

    # -------------- Coinflip --------------
    @app_commands.command(name="coinflip", description="Panna nebo orel (1:1).")
    @app_commands.describe(bet="Sázka v bodech")
    async def coinflip(self, itx: Interaction, bet: int):
        if not self._check_channel(itx):
            return await itx.response.send_message(
                "Použij prosím vyhrazený gambling kanál.", ephemeral=True
            )
        if bet < self.min_bet or bet > self.max_bet:
            return await itx.response.send_message(
                f"Sázka musí být mezi {self.min_bet} a {self.max_bet}.", ephemeral=True
            )

        bal = await _get_points(itx.user.id)
        if bal < bet:
            return await itx.response.send_message(
                f"Nedostatek bodů. Zůstatek: {bal}.", ephemeral=True
            )

        try:
            await EconomyQueries.spend_points(
                database_service.pool, itx.user.id, bet, meta="coinflip:bet"
            )
        except Exception:
            bal = await _get_points(itx.user.id)
            return await itx.response.send_message(
                f"Nedostatek bodů. Zůstatek: {bal}.", ephemeral=True
            )

        view = CoinflipView(self, itx.user.id, bet)
        await itx.response.send_message(
            embed=view.build_embed("Vyber stranu"), view=view, ephemeral=True
        )

    # -------------- Mines 5x5 --------------
    @app_commands.command(name="mines", description="Mines 5×5 – vyhýbej se minám, cashout včas.")
    @app_commands.describe(mines="Počet min (1–8)", bet="Sázka v bodech")
    async def mines(self, itx: Interaction, mines: int, bet: int):
        if not self._check_channel(itx):
            return await itx.response.send_message(
                "Použij prosím vyhrazený gambling kanál.", ephemeral=True
            )
        if not (1 <= mines <= 8):
            return await itx.response.send_message("Počet min musí být 1–8.", ephemeral=True)
        if bet < self.min_bet or bet > self.max_bet:
            return await itx.response.send_message(
                f"Sázka musí být mezi {self.min_bet} a {self.max_bet}.", ephemeral=True
            )

        bal = await _get_points(itx.user.id)
        if bal < bet:
            return await itx.response.send_message(
                f"Nedostatek bodů. Zůstatek: {bal}.", ephemeral=True
            )

        try:
            await EconomyQueries.spend_points(
                database_service.pool, itx.user.id, bet, meta=f"mines:bet:{mines}"
            )
        except Exception:
            bal = await _get_points(itx.user.id)
            return await itx.response.send_message(
                f"Nedostatek bodů. Zůstatek: {bal}.", ephemeral=True
            )

        view = MinesView(self, itx.user.id, bet, mines)
        await itx.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

    # -------------- Roulette --------------
    @app_commands.command(
        name="roulette", description="Roulette (evropská, 0–36) s tlačítkovým sázením."
    )
    async def roulette(self, itx: Interaction):
        if not self._check_channel(itx):
            return await itx.response.send_message(
                "Použij prosím vyhrazený gambling kanál.", ephemeral=True
            )
        bal = await _get_points(itx.user.id)
        view = RouletteView(self, itx.user.id, bal, unit_bet=max(10, self.min_bet))
        await itx.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

    # -------------- Baccarat --------------
    @app_commands.command(name="baccarat", description="Baccarat — vsadíš na Player/Banker/Tie.")
    @app_commands.describe(bet="Sázka v bodech", side="Strana")
    @app_commands.choices(
        side=[
            app_commands.Choice(name="Player", value="player"),
            app_commands.Choice(name="Banker", value="banker"),
            app_commands.Choice(name="Tie", value="tie"),
        ]
    )
    async def baccarat(self, itx: Interaction, bet: int, side: app_commands.Choice[str]):
        if not self._check_channel(itx):
            return await itx.response.send_message(
                "Použij prosím vyhrazený gambling kanál.", ephemeral=True
            )
        if bet < self.min_bet or bet > self.max_bet:
            return await itx.response.send_message(
                f"Sázka musí být mezi {self.min_bet} a {self.max_bet}.", ephemeral=True
            )
        bal = await _get_points(itx.user.id)
        if bal < bet:
            return await itx.response.send_message(
                f"Nedostatek bodů. Zůstatek: {bal}.", ephemeral=True
            )

        try:
            await EconomyQueries.spend_points(
                database_service.pool, itx.user.id, bet, meta=f"baccarat:bet:{side.value}"
            )
        except Exception:
            bal = await _get_points(itx.user.id)
            return await itx.response.send_message(
                f"Nedostatek bodů. Zůstatek: {bal}.", ephemeral=True
            )

        view = BaccaratView(self, itx.user.id, bet, side.value)
        await itx.response.send_message(
            embed=view.build_embed("Připraveno — stiskni **Deal**."), view=view, ephemeral=True
        )

    # -------------- Crash --------------
    @app_commands.command(name="crash", description="Crash — cashout dřív, než graf spadne!")
    @app_commands.describe(bet="Sázka v bodech")
    async def crash(self, itx: Interaction, bet: int):
        if not self._check_channel(itx):
            return await itx.response.send_message(
                "Použij prosím vyhrazený gambling kanál.", ephemeral=True
            )
        if bet < self.min_bet or bet > self.max_bet:
            return await itx.response.send_message(
                f"Sázka musí být mezi {self.min_bet} a {self.max_bet}.", ephemeral=True
            )
        bal = await _get_points(itx.user.id)
        if bal < bet:
            return await itx.response.send_message(
                f"Nedostatek bodů. Zůstatek: {bal}.", ephemeral=True
            )

        try:
            await EconomyQueries.spend_points(
                database_service.pool, itx.user.id, bet, meta="crash:bet"
            )
        except Exception:
            bal = await _get_points(itx.user.id)
            return await itx.response.send_message(
                f"Nedostatek bodů. Zůstatek: {bal}.", ephemeral=True
            )

        view = CrashView(self, itx.user.id, bet)
        await itx.response.send_message(embed=view.build_embed(1.00), view=view, ephemeral=True)
        view.start(itx)

    # -------------- Higher / Lower --------------
    @app_commands.command(
        name="hol", description="Higher or Lower — odhadni další kartu, cashout včas."
    )
    @app_commands.describe(bet="Sázka v bodech")
    async def hol(self, itx: Interaction, bet: int):
        if not self._check_channel(itx):
            return await itx.response.send_message(
                "Použij prosím vyhrazený gambling kanál.", ephemeral=True
            )
        if bet < self.min_bet or bet > self.max_bet:
            return await itx.response.send_message(
                f"Sázka musí být mezi {self.min_bet} a {self.max_bet}.", ephemeral=True
            )
        bal = await _get_points(itx.user.id)
        if bal < bet:
            return await itx.response.send_message(
                f"Nedostatek bodů. Zůstatek: {bal}.", ephemeral=True
            )

        try:
            await EconomyQueries.spend_points(
                database_service.pool, itx.user.id, bet, meta="hol:bet"
            )
        except Exception:
            bal = await _get_points(itx.user.id)
            return await itx.response.send_message(
                f"Nedostatek bodů. Zůstatek: {bal}.", ephemeral=True
            )

        view = HigherLowerView(self, itx.user.id, bet)
        view.new_round()
        await itx.response.send_message(
            embed=view.build_embed("Vyber **Higher** nebo **Lower**."), view=view, ephemeral=True
        )

    # -------------- Lottery / Jackpot --------------
    @app_commands.command(
        name="lottery", description="Lottery/Jackpot — koupit losy nebo zobrazit pool."
    )
    @app_commands.describe(buy="Počet losů k nákupu (nech prázdné pro zobrazení stavu)")
    async def lottery(self, itx: Interaction, buy: int | None = None):
        if not self._check_channel(itx):
            return await itx.response.send_message(
                "Použij prosím vyhrazený gambling kanál.", ephemeral=True
            )

        if buy is None:
            emb = self._lottery_build_status_embed()
            return await itx.response.send_message(embed=emb, ephemeral=True)

        # purchase
        if buy <= 0:
            return await itx.response.send_message("Počet losů musí být kladný.", ephemeral=True)

        cost = buy * self.lottery_ticket_price
        bal = await _get_points(itx.user.id)
        if bal < cost:
            return await itx.response.send_message(
                f"Nedostatek bodů. Cena: {cost}, zůstatek: {bal}.", ephemeral=True
            )
        try:
            await EconomyQueries.spend_points(
                database_service.pool, itx.user.id, cost, meta=f"lottery:buy:{buy}"
            )
        except Exception:
            bal = await _get_points(itx.user.id)
            return await itx.response.send_message(
                f"Nedostatek bodů. Zůstatek: {bal}.", ephemeral=True
            )

        # record tickets
        self.lottery_pool += cost
        self.lottery_tickets[itx.user.id] = self.lottery_tickets.get(itx.user.id, 0) + buy
        emb = self._lottery_build_status_embed(
            note=f"Zakoupeno **{buy}** losů (cena {cost}). Děkujeme!"
        )
        await itx.response.send_message(embed=emb, ephemeral=True)


def _coming(name: str) -> discord.Embed:
    return discord.Embed(
        title=f"{name}",
        description="🎯 Připravujeme plnou verzi s tlačítkovým ovládáním a animacemi.",
        color=discord.Color.blurple(),
    )


# ================= BLACKJACK VIEW =================
class BlackjackView(_SafeView):
    def __init__(self, cog: CasinoCog, user_id: int, initial_bet: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.bet = initial_bet
        self.double_used = False
        self.closed = False

        # fairness
        self.server_seed = secrets.token_hex(16)
        self.deck = _draw_deck(4)
        self.deck_hash = hashlib.sha256(
            (self.server_seed + ":" + ",".join(self.deck)).encode()
        ).hexdigest()

        # hands
        self.player: list[str] = []
        self.dealer: list[str] = []
        self.revealed = False

    async def interaction_check(self, itx: Interaction) -> bool:
        if itx.user.id != self.user_id:
            await self._safe_send(itx, "Tohle není tvoje session.", ephemeral=True)
            return False
        return True

    async def start_game(self):
        # deal 2/2
        self.player.append(self.deck.pop())
        self.dealer.append(self.deck.pop())
        self.player.append(self.deck.pop())
        self.dealer.append(self.deck.pop())

        p_total, p_bj = _hand_total(self.player)
        d_total, d_bj = _hand_total(self.dealer)

        if p_bj or d_bj:
            await asyncio.sleep(0.5)
            await self._finish(final=True)

    def build_embed(self) -> discord.Embed:
        p_total, p_bj = _hand_total(self.player)
        if self.revealed:
            d_total, d_bj = _hand_total(self.dealer)
            dealer_line = (
                f"{_cards_str(self.dealer)}  (**{d_total}**{' blackjack' if d_bj else ''})"
            )
        else:
            dealer_line = f"{self.dealer[0]}  [🂠 skrytá]"

        emb = discord.Embed(
            title="🃏 Blackjack",
            color=discord.Color.green() if not self.revealed else discord.Color.gold(),
        )
        emb.add_field(
            name="Tvoje ruka",
            value=f"{_cards_str(self.player)}  (**{p_total}**{' blackjack' if p_bj else ''})",
            inline=False,
        )
        emb.add_field(name="Dealer", value=dealer_line, inline=False)

        bal_hint = f"💰 Sázka: **{self.bet}**  •  Zůstatek: **{self._balance_hint()}**"
        emb.add_field(name="Stav", value=bal_hint, inline=False)

        emb.set_footer(
            text=f"Fairness: SHA256 = {self.deck_hash}"
            + (" • odhalen seed níže" if self.revealed else "")
        )

        # buttons state
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = False

        # disable ineligible buttons
        if self.revealed or self.closed:
            self._disable_all()
        else:
            if self.double_used or len(self.player) != 2:
                self._button("double").disabled = True

        return emb

    def _button(self, key: str) -> discord.ui.Button:
        for b in self.children:
            if isinstance(b, discord.ui.Button) and b.custom_id == key:
                return b  # type: ignore
        raise KeyError(key)

    def _disable_all(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    def _balance_hint(self) -> str:
        # we don’t fetch every time (just hint); accurate deltas posíláme v resultu
        return "viz výsledek"

    async def _finish(self, final: bool = False, itx: Interaction | None = None):
        """Reveal dealer and settle if final."""
        self.revealed = True

        # Dealer draws if not final immediate BJ
        p_total, p_bj = _hand_total(self.player)
        d_total, d_bj = _hand_total(self.dealer)

        if not (p_bj or d_bj):
            # dealer stands on soft 17+
            while True:
                d_total, _ = _hand_total(self.dealer)
                # treat soft: if any ace counted as 11 and total==17, we stand (S17)
                if d_total >= 17:
                    break
                self.dealer.append(self.deck.pop())

        # Compute result
        p_total, p_bj = _hand_total(self.player)
        d_total, d_bj = _hand_total(self.dealer)
        bet_total = self.bet + (self.bet if self.double_used else 0)

        result = ""
        payout = 0

        def _lose():
            return "❌ Prohra – sázka propadá."

        def _push():
            return "➖ Push – vrácení sázky."

        def _win(mult: float = 1.0):
            return f"✅ Výhra ×{mult:.2f}"

        if p_bj and d_bj:
            # push
            payout = bet_total
            result = _push()
        elif p_bj:
            payout = int(bet_total + bet_total * 1.5)
            result = _win(1.5)
        elif d_bj:
            payout = 0
            result = _lose()
        else:
            if p_total > 21:
                payout = 0
                result = _lose()
            elif d_total > 21 or p_total > d_total:
                payout = bet_total * 2
                result = _win(1.00)
            elif p_total == d_total:
                payout = bet_total
                result = _push()
            else:
                payout = 0
                result = _lose()

        # Award payout (already spent bet upfront)
        delta = payout - bet_total
        if payout > 0:
            await EconomyQueries.award_points(
                database_service.pool, self.user_id, payout, meta="blackjack:payout"
            )

        bal = await _get_points(self.user_id)

        # Final embed
        final_emb = self.build_embed()
        final_emb.add_field(
            name="Výsledek",
            value=f"{result}\nBilance: **{delta:+d}**  •  Nový zůstatek: **{bal}**",
            inline=False,
        )
        final_emb.set_footer(text=f"Fairness: SHA256={self.deck_hash} • seed={self.server_seed}")

        self._disable_all()
        if itx:
            await self._safe_edit(itx, embed=final_emb, view=self)
        # If called from timeout or start_game immediate BJ, will be re-rendered by caller.

    # Buttons
    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary, custom_id="hit")
    async def hit(self, itx: Interaction, _: discord.ui.Button):
        self.player.append(self.deck.pop())
        p_total, _ = _hand_total(self.player)
        if p_total > 21:
            # bust → finish
            await self._finish(final=True, itx=itx)
            return
        await self._safe_edit(itx, embed=self.build_embed(), view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.success, custom_id="stand")
    async def stand(self, itx: Interaction, _: discord.ui.Button):
        await self._finish(final=True, itx=itx)

    @discord.ui.button(label="Double", style=discord.ButtonStyle.danger, custom_id="double")
    async def double(self, itx: Interaction, btn: discord.ui.Button):
        # Only first action
        if self.double_used or len(self.player) != 2:
            return await self._safe_send(itx, "Double nyní nelze.", ephemeral=True)

        # Charge extra bet
        try:
            await EconomyQueries.spend_points(
                database_service.pool, self.user_id, self.bet, meta="blackjack:double"
            )
        except Exception:
            bal = await _get_points(self.user_id)
            return await self._safe_send(
                itx, f"Nedostatek bodů pro double. Zůstatek: {bal}.", ephemeral=True
            )

        self.double_used = True
        # draw one and stand
        self.player.append(self.deck.pop())
        await self._finish(final=True, itx=itx)

    async def on_timeout(self) -> None:
        if self.closed or self.revealed:
            return
        self.closed = True
        # auto-stand
        try:
            await self._finish(final=True)
        except Exception:
            pass


# ================= RPS VIEW =================
class RPSView(_SafeView):
    CHOICES = [("✊", "rock"), ("✋", "paper"), ("✌️", "scissors")]

    def __init__(self, cog: CasinoCog, user_id: int, bet: int):
        super().__init__(timeout=90)
        self.cog = cog
        self.user_id = user_id
        self.bet = bet

    def build_embed(self, state: str) -> discord.Embed:
        emb = discord.Embed(
            title="✊✋✌️ Kámen–Nůžky–Papír", description=state, color=discord.Color.blurple()
        )
        emb.add_field(name="Sázka", value=str(self.bet))
        return emb

    async def _resolve(self, itx: Interaction, player: str):
        # animate
        await self._safe_edit(
            itx, embed=self.build_embed(f"Zvoleno: {player}. Bot přemýšlí…"), view=self
        )
        await asyncio.sleep(1.0)

        bot = random.choice([c for _, c in self.CHOICES])
        res = {
            ("rock", "scissors"): 1,
            ("paper", "rock"): 1,
            ("scissors", "paper"): 1,
            ("scissors", "rock"): -1,
            ("rock", "paper"): -1,
            ("paper", "scissors"): -1,
        }.get((player, bot), 0)

        delta = 0
        if res > 0:
            delta = self.bet  # net
            await EconomyQueries.award_points(
                database_service.pool, self.user_id, self.bet * 2, meta="rps:win"
            )
        elif res == 0:
            delta = 0
            await EconomyQueries.award_points(
                database_service.pool, self.user_id, self.bet, meta="rps:tie"
            )
        else:
            delta = -self.bet  # already paid

        bal = await _get_points(self.user_id)
        text = f"Ty: **{player}**  •  Bot: **{bot}**\nBilance: **{delta:+d}**  •  Nový zůstatek: **{bal}**"
        emb = self.build_embed(text)
        for ch in self.children:
            if isinstance(ch, discord.ui.Button):
                ch.disabled = True
        await self._safe_edit(itx, embed=emb, view=self)

    @discord.ui.button(label="✊", style=discord.ButtonStyle.secondary)
    async def rock(self, itx: Interaction, _: discord.ui.Button):
        await self._resolve(itx, "rock")

    @discord.ui.button(label="✋", style=discord.ButtonStyle.secondary)
    async def paper(self, itx: Interaction, _: discord.ui.Button):
        await self._resolve(itx, "paper")

    @discord.ui.button(label="✌️", style=discord.ButtonStyle.secondary)
    async def scissors(self, itx: Interaction, _: discord.ui.Button):
        await self._resolve(itx, "scissors")


# ================= COINFLIP VIEW =================
class CoinflipView(_SafeView):
    def __init__(self, cog: CasinoCog, user_id: int, bet: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id
        self.bet = bet

    def build_embed(self, state: str) -> discord.Embed:
        emb = discord.Embed(title="🪙 Coinflip", description=state, color=discord.Color.gold())
        emb.add_field(name="Sázka", value=str(self.bet))
        return emb

    async def _flip(self, itx: Interaction, pick: str):
        # simple animation
        await self._safe_edit(
            itx, embed=self.build_embed(f"Zvoleno: **{pick}**\nTočím mincí…"), view=self
        )
        for _ in range(3):
            await asyncio.sleep(0.4)
            await self._safe_edit(itx, embed=self.build_embed("…"), view=self)

        outcome = random.choice(["Heads", "Tails"])
        win = outcome == pick

        delta = 0
        if win:
            delta = self.bet
            await EconomyQueries.award_points(
                database_service.pool, self.user_id, self.bet * 2, meta="coinflip:win"
            )
        else:
            delta = -self.bet

        bal = await _get_points(self.user_id)
        txt = f"Výsledek: **{outcome}**\nBilance: **{delta:+d}**  •  Nový zůstatek: **{bal}**"
        emb = self.build_embed(txt)
        for ch in self.children:
            if isinstance(ch, discord.ui.Button):
                ch.disabled = True
        await self._safe_edit(itx, embed=emb, view=self)

    @discord.ui.button(label="Heads", style=discord.ButtonStyle.primary)
    async def heads(self, itx: Interaction, _: discord.ui.Button):
        await self._flip(itx, "Heads")

    @discord.ui.button(label="Tails", style=discord.ButtonStyle.primary)
    async def tails(self, itx: Interaction, _: discord.ui.Button):
        await self._flip(itx, "Tails")


# ================= MINES VIEW =================
class MinesView(_SafeView):
    SIZE = 5

    def __init__(self, cog: CasinoCog, user_id: int, bet: int, mines: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.bet = bet
        self.mines = mines
        self.grid: list[list[str]] = [
            [" "] * self.SIZE for _ in range(self.SIZE)
        ]  # " " hidden, "💣" mine, "💎" safe
        self.revealed = [[False] * self.SIZE for _ in range(self.SIZE)]
        self.placed = False
        self.safe_count = 0
        self.dead = False

        # Precompute random order for placement fairness
        self._seed = secrets.token_hex(8)
        self._rng = secrets.SystemRandom()

        # Cashout button
        self.cash_btn = discord.ui.Button(label="Cash Out", style=discord.ButtonStyle.success)
        self.cash_btn.callback = self.cashout  # type: ignore
        self.add_item(self.cash_btn)

        # Add 25 field buttons
        for r in range(self.SIZE):
            for c in range(self.SIZE):
                btn = discord.ui.Button(
                    label=f"{chr(65+r)}{c+1}",
                    style=discord.ButtonStyle.secondary,
                    row=r,
                    custom_id=f"m{r}_{c}",
                )

                async def handler(itx: Interaction, rr=r, cc=c, _btn=btn):
                    await self.pick(itx, rr, cc, _btn)

                btn.callback = handler  # type: ignore
                self.add_item(btn)

    def build_embed(self, note: str = "") -> discord.Embed:
        emb = discord.Embed(
            title="💣 Mines (5×5)",
            color=discord.Color.red() if self.dead else discord.Color.green(),
        )
        emb.add_field(name="Sázka", value=str(self.bet))
        emb.add_field(name="Miny", value=str(self.mines))
        emb.add_field(name="Bezpečné odhaleno", value=str(self.safe_count))
        if note:
            emb.add_field(name="Info", value=note, inline=False)
        emb.set_footer(text=f"Seed: {self._seed}")
        return emb

    def _payout(self) -> int:
        # Jednoduchá křivka multiplikátoru podle počtu bezpečných odhalení a počtu min.
        # Není to kasino-matematika, ale je čitelná a roste s rizikem.
        base = 1.0
        step = max(0.10, self.mines * 0.08)  # víc min → rychlejší růst
        mult = base + self.safe_count * step
        return int(self.bet * mult)

    async def pick(self, itx: Interaction, r: int, c: int, btn: discord.ui.Button):
        if self.dead:
            return await self._safe_send(itx, "Hra skončila.", ephemeral=True)
        if self.revealed[r][c]:
            return await self._safe_send(itx, "Už odhaleno.", ephemeral=True)

        # Place mines after first safe click
        if not self.placed:
            cells = [
                (rr, cc)
                for rr in range(self.SIZE)
                for cc in range(self.SIZE)
                if not (rr == r and cc == c)
            ]
            self._rng.shuffle(cells)
            for mr, mc in cells[: self.mines]:
                self.grid[mr][mc] = "💣"
            self.placed = True

        # Reveal
        self.revealed[r][c] = True
        if self.grid[r][c] == "💣":
            # Boom
            self.dead = True
            # disable all field buttons
            for item in self.children:
                if (
                    isinstance(item, discord.ui.Button)
                    and item.custom_id
                    and item.custom_id.startswith("m")
                ):
                    item.disabled = True
            self.cash_btn.disabled = True

            delta = -self.bet  # already spent
            bal = await _get_points(self.user_id)
            emb = self.build_embed(
                note=f"💥 Narazil jsi na minu! Bilance: **{delta:+d}** • Zůstatek: **{bal}**"
            )
            return await self._safe_edit(itx, embed=emb, view=self)

        # Safe
        self.grid[r][c] = "💎"
        self.safe_count += 1
        btn.style = discord.ButtonStyle.success
        btn.label = "💎"
        await self._safe_edit(
            itx, embed=self.build_embed(note="Bezpečné! Můžeš pokračovat nebo Cash Out."), view=self
        )

    async def cashout(self, itx: Interaction):
        if self.dead:
            return
        payout = self._payout()
        delta = payout - self.bet
        if payout > 0:
            await EconomyQueries.award_points(
                database_service.pool, self.user_id, payout, meta=f"mines:cashout:{self.mines}"
            )
        bal = await _get_points(self.user_id)

        # lock board
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        emb = self.build_embed(
            note=f"💰 Cash Out: výplata **{payout}** • Bilance: **{delta:+d}** • Nový zůstatek: **{bal}**"
        )
        await self._safe_edit(itx, embed=emb, view=self)


# ================= ROULETTE VIEW =================
class RouletteView(_SafeView):
    REDS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
    BLACKS = set(range(1, 37)) - REDS
    GREEN = {0}

    def __init__(self, cog: CasinoCog, user_id: int, balance: int, unit_bet: int = 10):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.unit = unit_bet
        self.balance_hint = balance
        # bets: list of dicts {"type":..., "value":..., "amt":...}
        self.bets: list[dict] = []

        # Controls
        self.add_item(
            discord.ui.Button(label="-10", style=discord.ButtonStyle.secondary, custom_id="ru_dec")
        )
        self.add_item(
            discord.ui.Button(label="+10", style=discord.ButtonStyle.secondary, custom_id="ru_inc")
        )
        self.add_item(
            discord.ui.Button(label="Red", style=discord.ButtonStyle.danger, custom_id="ru_red")
        )
        self.add_item(
            discord.ui.Button(
                label="Black", style=discord.ButtonStyle.primary, custom_id="ru_black"
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Clear", style=discord.ButtonStyle.secondary, custom_id="ru_clear"
            )
        )

        self.add_item(
            discord.ui.Button(label="Odd", style=discord.ButtonStyle.secondary, custom_id="ru_odd")
        )
        self.add_item(
            discord.ui.Button(
                label="Even", style=discord.ButtonStyle.secondary, custom_id="ru_even"
            )
        )
        self.add_item(
            discord.ui.Button(label="1–18", style=discord.ButtonStyle.secondary, custom_id="ru_low")
        )
        self.add_item(
            discord.ui.Button(
                label="19–36", style=discord.ButtonStyle.secondary, custom_id="ru_high"
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Confirm & Spin", style=discord.ButtonStyle.success, custom_id="ru_spin"
            )
        )

        self.add_item(
            discord.ui.Button(
                label="Dozen 1", style=discord.ButtonStyle.secondary, custom_id="ru_dz1"
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Dozen 2", style=discord.ButtonStyle.secondary, custom_id="ru_dz2"
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Dozen 3", style=discord.ButtonStyle.secondary, custom_id="ru_dz3"
            )
        )
        self.add_item(
            discord.ui.Button(label="Col 1", style=discord.ButtonStyle.secondary, custom_id="ru_c1")
        )
        self.add_item(
            discord.ui.Button(label="Col 2", style=discord.ButtonStyle.secondary, custom_id="ru_c2")
        )

        self.add_item(
            discord.ui.Button(label="Col 3", style=discord.ButtonStyle.secondary, custom_id="ru_c3")
        )

        sel = discord.ui.Select(
            placeholder="Přidat Straight (číslo 0–36)",
            options=[discord.SelectOption(label=str(n), value=str(n)) for n in range(37)],
            min_values=1,
            max_values=1,
            custom_id="ru_num",
        )

        async def on_select(itx: Interaction):
            if not await self._guard(itx):
                return
            n = int(sel.values[0])
            self.bets.append({"type": "STRAIGHT", "value": n, "amt": self.unit})
            await self._safe_edit(itx, embed=self.build_embed(), view=self)

        sel.callback = on_select  # type: ignore
        self.add_item(sel)

    async def interaction_check(self, itx: Interaction) -> bool:
        return itx.user.id == self.user_id

    async def _guard(self, itx: Interaction) -> bool:
        if itx.user.id != self.user_id:
            await self._safe_send(itx, "Tohle není tvoje session.", ephemeral=True)
            return False
        return True

    def _bets_summary(self) -> tuple[str, int]:
        if not self.bets:
            return "Zatím žádné sázky.", 0
        lines = []
        total = 0
        for b in self.bets:
            kind = b["type"]
            val = b["value"]
            amt = b["amt"]
            total += amt
            label = kind if kind != "STRAIGHT" else f"Straight {val}"
            lines.append(f"• {label}: {amt}")
        return "\n".join(lines), total

    def build_embed(self, result_text: str = "") -> discord.Embed:
        bets_text, total = self._bets_summary()
        emb = discord.Embed(title="🎡 Roulette (evropská)", color=discord.Color.dark_teal())
        emb.add_field(name="Jednotka sázky", value=str(self.unit))
        emb.add_field(name="Zůstatek (orientační)", value=str(self.balance_hint))
        emb.add_field(name=f"Sázky (celkem {total})", value=bets_text, inline=False)
        if result_text:
            emb.add_field(name="Výsledek", value=result_text, inline=False)
        emb.set_footer(text="Typy: Red/Black/Odd/Even/Low/High • Dozens/Columns • Straight (0–36)")
        return emb

    # --- Button routing ---
    async def interaction_check_and_route(self, itx: Interaction, cid: str):
        if not await self._guard(itx):
            return
        if cid == "ru_dec":
            self.unit = max(1, self.unit - 10)
        elif cid == "ru_inc":
            self.unit = min(self.cog.max_bet, self.unit + 10)
        elif cid == "ru_red":
            self.bets.append({"type": "RED", "value": None, "amt": self.unit})
        elif cid == "ru_black":
            self.bets.append({"type": "BLACK", "value": None, "amt": self.unit})
        elif cid == "ru_odd":
            self.bets.append({"type": "ODD", "value": None, "amt": self.unit})
        elif cid == "ru_even":
            self.bets.append({"type": "EVEN", "value": None, "amt": self.unit})
        elif cid == "ru_low":
            self.bets.append({"type": "LOW", "value": None, "amt": self.unit})
        elif cid == "ru_high":
            self.bets.append({"type": "HIGH", "value": None, "amt": self.unit})
        elif cid == "ru_dz1":
            self.bets.append({"type": "DOZEN", "value": 1, "amt": self.unit})
        elif cid == "ru_dz2":
            self.bets.append({"type": "DOZEN", "value": 2, "amt": self.unit})
        elif cid == "ru_dz3":
            self.bets.append({"type": "DOZEN", "value": 3, "amt": self.unit})
        elif cid == "ru_c1":
            self.bets.append({"type": "COL", "value": 1, "amt": self.unit})
        elif cid == "ru_c2":
            self.bets.append({"type": "COL", "value": 2, "amt": self.unit})
        elif cid == "ru_c3":
            self.bets.append({"type": "COL", "value": 3, "amt": self.unit})
        elif cid == "ru_clear":
            self.bets.clear()
        elif cid == "ru_spin":
            await self._spin(itx)
            return
        await self._safe_edit(itx, embed=self.build_embed(), view=self)

    async def _spin(self, itx: Interaction):
        # charge total
        _, total = self._bets_summary()
        if total <= 0:
            return await self._safe_send(itx, "Žádné sázky.", ephemeral=True)

        # check balance fresh
        bal = await _get_points(itx.user.id)
        if bal < total:
            return await self._safe_send(
                itx, f"Nedostatek bodů. Potřeba: {total}, zůstatek: {bal}.", ephemeral=True
            )
        try:
            await EconomyQueries.spend_points(
                database_service.pool, itx.user.id, total, meta="roulette:bet"
            )
        except Exception:
            bal = await _get_points(itx.user.id)
            return await self._safe_send(itx, f"Nedostatek bodů. Zůstatek: {bal}.", ephemeral=True)

        # spin anim
        await self._safe_edit(itx, embed=self.build_embed("Točím… 🎲"), view=self)
        await asyncio.sleep(1.2)

        n = random.randint(0, 36)
        color = "🟢" if n == 0 else ("🔴" if n in self.REDS else "⚫")
        outcome = f"{color} **{n}**"
        win_total = 0

        for b in self.bets:
            amt = b["amt"]
            kind = b["type"]
            val = b["value"]
            if kind == "STRAIGHT":
                if n == val:
                    win_total += amt * 36
            elif kind in ("RED", "BLACK"):
                ok = (n in self.REDS) if kind == "RED" else (n in self.BLACKS)
                if n != 0 and ok:
                    win_total += amt * 2
            elif kind in ("ODD", "EVEN"):
                if n != 0:
                    ok = (n % 2 == 1) if kind == "ODD" else (n % 2 == 0)
                    if ok:
                        win_total += amt * 2
            elif kind in ("LOW", "HIGH"):
                if kind == "LOW" and (1 <= n <= 18):
                    win_total += amt * 2
                if kind == "HIGH" and (19 <= n <= 36):
                    win_total += amt * 2
            elif kind == "DOZEN":
                if val == 1 and (1 <= n <= 12):
                    win_total += amt * 3
                if val == 2 and (13 <= n <= 24):
                    win_total += amt * 3
                if val == 3 and (25 <= n <= 36):
                    win_total += amt * 3
            elif kind == "COL":
                mod = n % 3
                if n != 0:
                    if val == 1 and mod == 1:
                        win_total += amt * 3
                    if val == 2 and mod == 2:
                        win_total += amt * 3
                    if val == 3 and mod == 0:
                        win_total += amt * 3

        if win_total > 0:
            await EconomyQueries.award_points(
                database_service.pool, itx.user.id, win_total, meta="roulette:win"
            )

        new_bal = await _get_points(itx.user.id)
        delta = win_total - total
        text = f"Výsledek: {outcome}\nBilance: **{delta:+d}** • Nový zůstatek: **{new_bal}**"
        # lock bets after round
        for c in self.children:
            if isinstance(c, discord.ui.Button) or isinstance(c, discord.ui.Select):
                c.disabled = True
        await self._safe_edit(itx, embed=self.build_embed(text), view=self)

    async def on_timeout(self) -> None:
        for c in self.children:
            if isinstance(c, discord.ui.Button) or isinstance(c, discord.ui.Select):
                c.disabled = True


# ================= BACCARAT VIEW =================
class BaccaratView(_SafeView):
    def __init__(self, cog: CasinoCog, user_id: int, bet: int, side: str):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.bet = bet
        self.side = side  # 'player' | 'banker' | 'tie'
        self.deck = _draw_deck(6)
        self.player: list[str] = []
        self.banker: list[str] = []
        self.ended = False

        self.deal_btn = discord.ui.Button(label="Deal", style=discord.ButtonStyle.success)
        self.deal_btn.callback = self.deal  # type: ignore
        self.add_item(self.deal_btn)

    def build_embed(self, note: str = "") -> discord.Embed:
        emb = discord.Embed(title="🎴 Baccarat", color=discord.Color.blue())
        emb.add_field(name="Sázka", value=str(self.bet))
        emb.add_field(name="Strana", value=self.side.capitalize())
        if self.player:
            p_total = sum(min(_card_value(c[:-1])[-1], 10) for c in self.player) % 10
            b_total = sum(min(_card_value(c[:-1])[-1], 10) for c in self.banker) % 10
            emb.add_field(
                name="Player", value=f"{_cards_str(self.player)}  (**{p_total}**)", inline=False
            )
            emb.add_field(
                name="Banker", value=f"{_cards_str(self.banker)}  (**{b_total}**)", inline=False
            )
        if note:
            emb.add_field(name="Info", value=note, inline=False)
        return emb

    async def deal(self, itx: Interaction):
        if self.ended:
            return
        # Initial two each
        self.player = [self.deck.pop(), self.deck.pop()]
        self.banker = [self.deck.pop(), self.deck.pop()]
        await self._safe_edit(itx, embed=self.build_embed("Rozdáno…"), view=self)
        await asyncio.sleep(1.0)

        def total9(cards: list[str]) -> int:
            t = 0
            for c in cards:
                r = c[:-1]
                v = 10 if r in ("10", "J", "Q", "K") else (1 if r == "A" else int(r))
                t += v
            return t % 10

        p = total9(self.player)
        b = total9(self.banker)

        # Naturals
        if p in (8, 9) or b in (8, 9):
            await self._finish(itx)
            return

        # Player draw rule
        third_player: str | None = None
        if p <= 5:
            third_player = self.deck.pop()
            self.player.append(third_player)
            await self._safe_edit(
                itx, embed=self.build_embed("Player bere třetí kartu…"), view=self
            )
            await asyncio.sleep(1.0)
            p = total9(self.player)

        # Banker draw rule (simplified correct rules)
        def banker_drawn(b_total: int, p_third: str | None) -> bool:
            if p_third is None:
                # if player stood: banker draws on <=5
                return b_total <= 5
            # map third card value 0-9
            r = p_third[:-1]
            v = 0
            if r in ("10", "J", "Q", "K"):
                v = 0
            elif r == "A":
                v = 1
            else:
                v = int(r)
            if b_total <= 2:
                return True
            if b_total == 3:
                return v != 8
            if b_total == 4:
                return 2 <= v <= 7
            if b_total == 5:
                return 4 <= v <= 7
            if b_total == 6:
                return v in (6, 7)
            return False

        if banker_drawn(b, third_player):
            self.banker.append(self.deck.pop())
            await self._safe_edit(
                itx, embed=self.build_embed("Banker bere třetí kartu…"), view=self
            )
            await asyncio.sleep(1.0)

        await self._finish(itx)

    async def _finish(self, itx: Interaction):
        self.ended = True
        # lock button
        for i in self.children:
            if isinstance(i, discord.ui.Button):
                i.disabled = True

        def total9(cards: list[str]) -> int:
            t = 0
            for c in cards:
                r = c[:-1]
                v = 10 if r in ("10", "J", "Q", "K") else (1 if r == "A" else int(r))
                t += v
            return t % 10

        p = total9(self.player)
        b = total9(self.banker)

        if p > b:
            winner = "player"
        elif b > p:
            winner = "banker"
        else:
            winner = "tie"

        payout = 0
        note = ""
        if winner == "tie":
            if self.side == "tie":
                payout = self.bet * 9  # 8:1 + return bet
                note = "✅ Tie 8:1"
            else:
                payout = self.bet  # push for P/B on tie
                note = "➖ Tie — push (vrácení sázky)."
        else:
            if self.side == winner:
                if winner == "banker":
                    payout = int(self.bet + self.bet * 0.95)  # 0.95:1 + return bet
                    note = "✅ Banker 0.95:1"
                else:
                    payout = self.bet * 2  # 1:1 + return bet
                    note = "✅ Player 1:1"
            else:
                payout = 0
                note = "❌ Prohra."

        if payout > 0:
            await EconomyQueries.award_points(
                database_service.pool, self.user_id, payout, meta="baccarat:payout"
            )

        bal = await _get_points(self.user_id)
        emb = self.build_embed(f"{note}\nNový zůstatek: **{bal}**")
        await self._safe_edit(itx, embed=emb, view=self)


# ================= CRASH VIEW =================
class CrashView(_SafeView):
    def __init__(self, cog: CasinoCog, user_id: int, bet: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.bet = bet
        # precompute crash point (heavy tail, capped)
        # 1.00 + Exp(λ=1.0), cap 25x
        self.crash_at = min(25.0, 1.0 + random.expovariate(1.0))
        self.running = False
        self.stopped = False
        self.current = 1.00

        self.cash_btn = discord.ui.Button(label="Cash Out", style=discord.ButtonStyle.success)
        self.cash_btn.callback = self.cashout  # type: ignore
        self.add_item(self.cash_btn)

    def build_embed(self, mult: float, crashed: bool = False, note: str = "") -> discord.Embed:
        txt = f"Multiplikátor: **{mult:.2f}×**"
        if crashed:
            txt += f"\n💥 Crash na **{self.crash_at:.2f}×**"
        if note:
            txt += f"\n{note}"
        emb = discord.Embed(title="📈 Crash", description=txt, color=discord.Color.orange())
        emb.add_field(name="Sázka", value=str(self.bet))
        return emb

    def start(self, itx: Interaction):
        self.running = True
        asyncio.create_task(self._run(itx))

    async def _run(self, itx: Interaction):
        # increment ~ every 0.6s
        while self.running and not self.stopped:
            await asyncio.sleep(0.6)
            self.current *= 1.07  # growth step
            if self.current >= self.crash_at:
                # crash
                self.stopped = True
                self.cash_btn.disabled = True
                await self._safe_edit(
                    itx,
                    embed=self.build_embed(self.crash_at, crashed=True, note="❌ Prohra."),
                    view=self,
                )
                return
            await self._safe_edit(itx, embed=self.build_embed(self.current), view=self)

    async def cashout(self, itx: Interaction):
        if self.stopped:
            return
        self.stopped = True
        self.cash_btn.disabled = True
        payout = int(self.bet * self.current)
        if payout > 0:
            await EconomyQueries.award_points(
                database_service.pool, self.user_id, payout, meta="crash:cashout"
            )
        bal = await _get_points(self.user_id)
        await self._safe_edit(
            itx,
            embed=self.build_embed(
                self.current, note=f"💰 Cashout: **{payout}** • Nový zůstatek: **{bal}**"
            ),
            view=self,
        )


# ================= HIGHER / LOWER VIEW =================
class HigherLowerView(_SafeView):
    def __init__(self, cog: CasinoCog, user_id: int, bet: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.bet = bet
        self.deck = _draw_deck(4)
        self.current: str | None = None
        self.mult = 1.0  # grows by 1.2× per correct guess

        self.btn_hi = discord.ui.Button(label="Higher", style=discord.ButtonStyle.primary)
        self.btn_lo = discord.ui.Button(label="Lower", style=discord.ButtonStyle.primary)
        self.btn_cash = discord.ui.Button(label="Cash Out", style=discord.ButtonStyle.success)

        self.btn_hi.callback = self.pick_higher  # type: ignore
        self.btn_lo.callback = self.pick_lower  # type: ignore
        self.btn_cash.callback = self.cashout  # type: ignore

        self.add_item(self.btn_hi)
        self.add_item(self.btn_lo)
        self.add_item(self.btn_cash)

    def _rank_val(self, card: str) -> int:
        r = card[:-1]
        order = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
        return order.index(r)

    def new_round(self):
        self.current = self.deck.pop()

    def build_embed(self, note: str = "") -> discord.Embed:
        cur = self.current or "?"
        emb = discord.Embed(title="⬆️⬇️ Higher / Lower", color=discord.Color.dark_gold())
        emb.add_field(name="Aktuální karta", value=cur)
        emb.add_field(name="Multiplikátor", value=f"{self.mult:.2f}×")
        emb.add_field(name="Sázka", value=str(self.bet))
        if note:
            emb.add_field(name="Info", value=note, inline=False)
        return emb

    async def pick_higher(self, itx: Interaction):
        await self._resolve(itx, higher=True)

    async def pick_lower(self, itx: Interaction):
        await self._resolve(itx, higher=False)

    async def _resolve(self, itx: Interaction, *, higher: bool):
        # draw next
        nxt = self.deck.pop()
        assert self.current is not None
        ok = (
            (self._rank_val(nxt) > self._rank_val(self.current))
            if higher
            else (self._rank_val(nxt) < self._rank_val(self.current))
        )

        if ok:
            self.mult *= 1.2
            self.current = nxt
            await self._safe_edit(
                itx, embed=self.build_embed(note=f"✅ Správně! Nová karta: **{nxt}**"), view=self
            )
        else:
            # lose
            for b in self.children:
                if isinstance(b, discord.ui.Button):
                    b.disabled = True
            await self._safe_edit(
                itx,
                embed=self.build_embed(note=f"❌ Špatně! Byla karta **{nxt}**. Prohra."),
                view=self,
            )

    async def cashout(self, itx: Interaction):
        for b in self.children:
            if isinstance(b, discord.ui.Button):
                b.disabled = True
        payout = int(self.bet * self.mult)
        if payout > 0:
            await EconomyQueries.award_points(
                database_service.pool, self.user_id, payout, meta="hol:cashout"
            )
        bal = await _get_points(self.user_id)
        await self._safe_edit(
            itx,
            embed=self.build_embed(note=f"💰 Cash Out: **{payout}** • Nový zůstatek: **{bal}**"),
            view=self,
        )
