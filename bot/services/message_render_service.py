# bot/services/message_render_service.py
from __future__ import annotations

import io
import logging
import textwrap

import aiohttp
import discord
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

_DEFAULT_FONT = ImageFont.load_default()


async def _fetch_bytes(url: str) -> bytes | None:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=8) as r:
                if r.status == 200:
                    return await r.read()
    except Exception as e:
        logger.debug(f"fetch image failed: {e}")
    return None


def _wrap_text(txt: str, width: int) -> list[str]:
    lines = []
    for para in (txt or "").splitlines():
        if not para.strip():
            lines.append("")
            continue
        lines.extend(textwrap.wrap(para, width=60))
    return lines


async def render_message_card(message: discord.Message) -> bytes:
    """
    Render a simple Discord-like message card with avatar, name, content and reaction bar (textual).
    Returns PNG bytes.
    """
    author = message.author
    content = message.content or ""
    lines = _wrap_text(content, 60)[:12]  # cap
    reactions_text = (
        "  ".join([f"{r.emoji!s} {r.count}" for r in message.reactions])
        if message.reactions
        else ""
    )

    # Base sizes
    width = 900
    top = 20
    left = 20
    avatar_size = 64
    line_height = 20
    content_height = max(60, line_height * (len(lines) + 1))
    reaction_bar_h = 28 if reactions_text else 0
    total_height = top + avatar_size + 16 + content_height + reaction_bar_h + 40

    img = Image.new("RGB", (width, total_height), (54, 57, 63))  # Discord dark
    draw = ImageDraw.Draw(img)

    # Avatar
    avatar_url = author.display_avatar.url
    avatar_bytes = await _fetch_bytes(str(avatar_url))
    if avatar_bytes:
        av = Image.open(io.BytesIO(avatar_bytes)).convert("RGB").resize((avatar_size, avatar_size))
        img.paste(av, (left, top))
    else:
        draw.ellipse((left, top, left + avatar_size, top + avatar_size), fill=(100, 100, 100))

    # Name + timestamp
    name_x = left + avatar_size + 15
    draw.text((name_x, top), author.display_name, font=_DEFAULT_FONT, fill=(255, 255, 255))
    ts = message.created_at.strftime("%Y-%m-%d %H:%M")
    draw.text((name_x + 200, top), ts, font=_DEFAULT_FONT, fill=(185, 187, 190))

    # Content
    cy = top + 28
    for ln in lines:
        draw.text((name_x, cy), ln, font=_DEFAULT_FONT, fill=(220, 221, 222))
        cy += line_height

    # Attach first image thumbnail if present
    attach_y = cy + 8
    for att in message.attachments or []:
        if att.content_type and att.content_type.startswith("image/"):
            img_bytes = await _fetch_bytes(att.url)
            if img_bytes:
                try:
                    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                    # fit width 520
                    maxw = 520
                    ratio = min(1.0, maxw / im.width)
                    im = im.resize((int(im.width * ratio), int(im.height * ratio)))
                    img.paste(im, (name_x, attach_y))
                    attach_y += im.height + 6
                    break
                except Exception:
                    pass

    # Reaction bar
    if reactions_text:
        ry = total_height - 40
        draw.rounded_rectangle((name_x, ry, name_x + 600, ry + 24), radius=8, fill=(47, 49, 54))
        draw.text((name_x + 10, ry + 5), reactions_text, font=_DEFAULT_FONT, fill=(220, 221, 222))

    # Export
    out = io.BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    return out.read()
