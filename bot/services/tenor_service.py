# bot/services/tenor_service.py
from __future__ import annotations

import aiohttp
import logging
import random
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


class TenorClient:
    """
    Minimal Tenor API v2 client for GIF search.
    Docs: https://tenor.com/gifapi/documentation
    """
    BASE_URL = "https://tenor.googleapis.com/v2"

    def __init__(
        self,
        api_key: str,
        *,
        locale: str = "en_US",
        content_filter: str = "medium",  # off|low|medium|high
        media_types: str = "gif,tinygif",
    ):
        self.api_key = api_key.strip()
        self.locale = locale
        self.content_filter = content_filter
        self.media_types = media_types

    @property
    def is_enabled(self) -> bool:
        return bool(self.api_key)

    async def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.BASE_URL}{path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=8) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def search_gifs(
        self,
        query: str,
        *,
        limit: int = 8,
        randomize: bool = True,
    ) -> List[str]:
        """
        Returns a list of GIF URLs (prefer full gif, fallback tinygif).
        """
        if not self.is_enabled:
            return []

        params = {
            "key": self.api_key,
            "q": query,
            "limit": limit,
            "random": "true" if randomize else "false",
            "locale": self.locale,
            "contentfilter": self.content_filter,
            "media_filter": self.media_types,  # comma-separated
        }

        try:
            data = await self._get("/search", params)
        except Exception as e:
            logger.warning(f"Tenor search failed for '{query}': {e}")
            return []

        out: List[str] = []
        for item in data.get("results", []):
            media = item.get("media_formats") or {}
            url = None
            if "gif" in media and media["gif"].get("url"):
                url = media["gif"]["url"]
            elif "tinygif" in media and media["tinygif"].get("url"):
                url = media["tinygif"]["url"]
            if url:
                out.append(url)

        if randomize and out:
            random.shuffle(out)
        return out

    async def best_gif(self, query: str) -> Optional[str]:
        hits = await self.search_gifs(query, limit=6, randomize=True)
        return hits[0] if hits else None
