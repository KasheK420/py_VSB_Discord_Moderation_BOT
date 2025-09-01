# bot/services/health_service.py
import asyncio
import logging
import os
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple, List

import aiohttp
import discord

try:
    import psutil  # for CPU/RAM/disk/container uptime
except Exception:
    psutil = None  # optional; handled gracefully

from ..database.database_service import database_service

logger = logging.getLogger(__name__)

@dataclass
class ServiceStatus:
    name: str
    ok: bool
    details: str = ""
    latency_ms: Optional[float] = None
    last_update: Optional[datetime] = None


def _status_emoji(ok: Optional[bool]) -> str:
    if ok is True:
        return "🟢"
    if ok is False:
        return "🔴"
    return "🟡"


def _fmt_bool(ok: Optional[bool]) -> str:
    if ok is True:
        return "OK"
    if ok is False:
        return "FAIL"
    return "N/A"


class HealthMonitorService:
    """
    Periodically updates a single embed message in a configured channel
    with system + app health. Also provides a registry for custom services
    to push their status (optional).
    """

    def __init__(self, bot: discord.Client, config):
        self.bot = bot
        self.config = config
        self.channel_id: Optional[int] = int(getattr(config, "health_channel_id", "0") or 0)
        self.update_interval_s: int = int(getattr(config, "health_update_interval_s", "60") or 60)
        # If provided, we try to query Node Exporter (optional)
        self.node_exporter_url: Optional[str] = getattr(config, "node_exporter_url", None)
        # If set, we reuse the same message (edited, not spammy)
        self._message_id_store_path = os.environ.get("HEALTH_MSG_ID_FILE", "/app/health_msg_id.txt")

        self._message: Optional[discord.Message] = None
        self._task: Optional[asyncio.Task] = None
        self._session: Optional[aiohttp.ClientSession] = None

        # A lightweight in-memory registry for sub-services to publish their state
        self._service_registry: Dict[str, ServiceStatus] = {}

        # process start for uptime (fallback when psutil not present)
        self._process_start = time.time()

    # ---------- Public API ----------

    def register_service(self, name: str, ok: bool, details: str = "", latency_ms: Optional[float] = None):
        """Other services/cogs can call this to expose their health."""
        self._service_registry[name] = ServiceStatus(
            name=name,
            ok=ok,
            details=details[:200],
            latency_ms=latency_ms,
            last_update=datetime.now(timezone.utc),
        )

    async def start(self):
        if not self.channel_id:
            logger.warning("[Health] No health_channel_id configured; service disabled.")
            return
        if self._task:
            return
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5))
        self._task = asyncio.create_task(self._runner(), name="health-monitor-loop")

    async def stop(self):
        if self._task:
            self._task.cancel()
            self._task = None
        if self._session:
            await self._session.close()
            self._session = None

    async def force_refresh_now(self):
        await self._ensure_message()
        await self._update_message()

    # ---------- Core loop ----------

    async def _runner(self):
        await self._ensure_message()
        while True:
            try:
                await self._update_message()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception("[Health] update failed: %s", e)
            await asyncio.sleep(self.update_interval_s)

    # ---------- Message management ----------

    async def _ensure_message(self):
        chan = self.bot.get_channel(self.channel_id)
        if not chan:
            try:
                chan = await self.bot.fetch_channel(self.channel_id)
            except Exception:
                logger.error("[Health] Channel %s not found", self.channel_id)
                return

        # try to reuse stored message id (so we don’t post duplicates on restarts)
        msg_id = self._load_message_id()
        if msg_id:
            try:
                self._message = await chan.fetch_message(msg_id)
                return
            except Exception:
                # stale id -> drop
                self._message = None

        # find a previous bot message with our fingerprint in the last ~50 messages
        fingerprint = self._title()
        try:
            async for m in chan.history(limit=50):
                if m.author.id == self.bot.user.id and m.embeds:
                    if m.embeds[0].title == fingerprint:
                        self._message = m
                        self._store_message_id(m.id)
                        return
        except Exception:
            pass

        # create a new message
        embed = discord.Embed(title=self._title(), description="Inicializace…", color=discord.Color.blurple())
        try:
            self._message = await chan.send(embed=embed)
            self._store_message_id(self._message.id)
        except Exception as e:
            logger.error("[Health] Failed to post message: %s", e)
            self._message = None

    def _title(self) -> str:
        return "🩺 Stav systému (Health Monitor)"

    def _store_message_id(self, mid: int):
        try:
            with open(self._message_id_store_path, "w") as f:
                f.write(str(mid))
        except Exception:
            pass

    def _load_message_id(self) -> Optional[int]:
        try:
            if os.path.exists(self._message_id_store_path):
                with open(self._message_id_store_path, "r") as f:
                    return int(f.read().strip())
        except Exception:
            return None
        return None

    # ---------- Collectors ----------

    async def _check_internet(self) -> Tuple[Optional[bool], Optional[float], str]:
        """
        Try two endpoints: Cloudflare (1.1.1.1) and GitHub (as DNS + TLS).
        """
        if not self._session:
            return None, None, "no session"
        urls = ["https://1.1.1.1", "https://github.com"]
        last_err = ""
        start = time.perf_counter()
        for url in urls:
            try:
                async with self._session.get(url) as resp:
                    if resp.status < 500:
                        latency = (time.perf_counter() - start) * 1000
                        return True, latency, f"ok via {url}"
            except Exception as e:
                last_err = str(e)
        return False, None, last_err or "unreachable"

    async def _check_database(self) -> Tuple[Optional[bool], Optional[float], str]:
        try:
            if not database_service.pool:
                return False, None, "no pool"
            start = time.perf_counter()
            async with database_service.pool.acquire() as conn:
                await conn.execute("SELECT 1;")
            latency = (time.perf_counter() - start) * 1000
            return True, latency, "connected"
        except Exception as e:
            return False, None, str(e)[:200]

    def _collect_bot_info(self) -> Dict[str, str]:
        lat_ms = int(self.bot.latency * 1000) if getattr(self.bot, "latency", None) else None
        now = datetime.now(timezone.utc)

        # uptime
        if psutil:
            try:
                p = psutil.Process(os.getpid())
                start_ts = p.create_time()
            except Exception:
                start_ts = self._process_start
        else:
            start_ts = self._process_start
        uptime_s = int(time.time() - start_ts)

        return {
            "bot_user": f"{self.bot.user} ({self.bot.user.id})" if self.bot.user else "N/A",
            "latency": f"{lat_ms} ms" if lat_ms is not None else "N/A",
            "uptime": _format_duration(uptime_s),
            "time": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "hostname": socket.gethostname(),
            "guilds": str(len(self.bot.guilds)) if getattr(self.bot, "guilds", None) is not None else "N/A",
            "cogs": ", ".join(sorted(self.bot.cogs.keys()))[:1000] if hasattr(self.bot, "cogs") else "N/A",
        }

    def _collect_container_metrics(self) -> Dict[str, str]:
        if not psutil:
            return {"cpu": "N/A", "ram": "N/A", "disk": "N/A"}
        out = {}
        try:
            out["cpu"] = f"{psutil.cpu_percent(interval=None):.1f}%"
        except Exception:
            out["cpu"] = "N/A"
        try:
            vm = psutil.virtual_memory()
            out["ram"] = f"{vm.percent:.1f}% ({_bytes_h(vm.used)}/{_bytes_h(vm.total)})"
        except Exception:
            out["ram"] = "N/A"
        try:
            du = psutil.disk_usage("/")
            out["disk"] = f"{du.percent:.1f}% ({_bytes_h(du.used)}/{_bytes_h(du.total)})"
        except Exception:
            out["disk"] = "N/A"
        return out

    async def _collect_node_exporter(self) -> Dict[str, str]:
        """
        OPTIONAL: Basic scrape of a Prometheus Node Exporter (if URL configured),
        e.g. http://host.docker.internal:9100/metrics or http://<host ip>:9100/metrics
        We only parse a few lines to avoid heavy dependencies.
        """
        if not self.node_exporter_url or not self._session:
            return {}
        data = {}
        try:
            async with self._session.get(self.node_exporter_url) as resp:
                text = await resp.text()
        except Exception:
            return {}

        # Very small parser
        def _get_metric(name: str) -> Optional[float]:
            for line in text.splitlines():
                if line.startswith(name + " "):
                    try:
                        return float(line.split(" ", 1)[1].strip())
                    except Exception:
                        return None
            return None

        # Examples of simple metrics to present
        up = _get_metric("up")
        load1 = _get_metric("node_load1")
        mem_total = _get_metric("node_memory_MemTotal_bytes")
        mem_avail = _get_metric("node_memory_MemAvailable_bytes")
        if up is not None:
            data["host_up"] = "OK" if up >= 1 else "DOWN"
        if load1 is not None:
            data["host_load1"] = f"{load1:.2f}"
        if mem_total and mem_avail:
            used = mem_total - mem_avail
            data["host_mem"] = f"{(used / mem_total)*100:.1f}% ({_bytes_h(used)}/{_bytes_h(mem_total)})"
        return data

    # ---------- Embed crafting ----------

    async def _update_message(self):
        if not self._message:
            return

        # Internet
        internet_ok, internet_lat_ms, internet_msg = await self._check_internet()
        # DB
        db_ok, db_lat_ms, db_msg = await self._check_database()
        # Bot + container
        bot_info = self._collect_bot_info()
        container = self._collect_container_metrics()
        # Host (optional)
        host = await self._collect_node_exporter()

        # Services section (from registry + loaded cogs summary)
        services_lines = []
        # Registry first
        for name, st in sorted(self._service_registry.items(), key=lambda x: x[0].lower()):
            age = f" · {int((datetime.now(timezone.utc) - st.last_update).total_seconds())}s" if st.last_update else ""
            lat = f" · {int(st.latency_ms)}ms" if st.latency_ms is not None else ""
            services_lines.append(f"{_status_emoji(st.ok)} **{name}** {_fmt_bool(st.ok)}{lat}{age} — {st.details}".strip())
        # Add loaded cogs summary line (read-only)
        services_lines.append(f"📦 Nahrané cogs: {bot_info.get('cogs','N/A')}")

        embed = discord.Embed(
            title=self._title(),
            description="Automaticky se obnovuje. Pokud je něco červené, mrkněte do logu.",
            color=discord.Color.green() if (internet_ok and db_ok) else discord.Color.orange() if (internet_ok or db_ok) else discord.Color.red(),
            timestamp=datetime.now(timezone.utc),
        )

        # BOT
        embed.add_field(
            name="🤖 Bot",
            value=(
                f"Uptime: **{bot_info['uptime']}**\n"
                f"Latency: **{bot_info['latency']}**\n"
                f"Guilds: **{bot_info['guilds']}**\n"
                f"Host: `{bot_info['hostname']}`\n"
            ),
            inline=True,
        )

        # DATABASE
        embed.add_field(
            name="🗄️ Databáze",
            value=(
                f"{_status_emoji(db_ok)} {_fmt_bool(db_ok)}"
                + (f" · {int(db_lat_ms)} ms" if db_lat_ms is not None else "")
                + (f"\n{db_msg}" if db_msg and db_ok is False else "")
            ) or "N/A",
            inline=True,
        )

        # INTERNET
        embed.add_field(
            name="🌐 Internet",
            value=(
                f"{_status_emoji(internet_ok)} {_fmt_bool(internet_ok)}"
                + (f" · {int(internet_lat_ms)} ms" if internet_lat_ms is not None else "")
                + (f"\n{internet_msg}" if internet_msg and internet_ok is False else "")
            ) or "N/A",
            inline=True,
        )

        # CONTAINER
        embed.add_field(
            name="📦 Kontejner",
            value=f"CPU: **{container['cpu']}**\nRAM: **{container['ram']}**\nDisk: **{container['disk']}**",
            inline=True,
        )

        # HOST (optional Node Exporter)
        host_lines = []
        if host:
            if "host_up" in host:
                host_lines.append(f"Up: **{host['host_up']}**")
            if "host_load1" in host:
                host_lines.append(f"Load1: **{host['host_load1']}**")
            if "host_mem" in host:
                host_lines.append(f"RAM: **{host['host_mem']}**")
        else:
            host_lines.append("N/A (přidej `node_exporter_url` do configu)")
        embed.add_field(name="🖥️ Host", value="\n".join(host_lines), inline=True)

        # SERVICES
        embed.add_field(
            name="🧩 Služby",
            value="\n".join(services_lines)[:1024] if services_lines else "N/A",
            inline=False,
        )

        # Footer
        embed.set_footer(text="Health Monitor · auto-refresh")

        try:
            await self._message.edit(embed=embed)
        except Exception as e:
            logger.error("[Health] Failed to edit message: %s", e)

# ---------- helpers ----------

def _bytes_h(n: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def _format_duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    parts: List[str] = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s or not parts: parts.append(f"{s}s")
    return " ".join(parts)
