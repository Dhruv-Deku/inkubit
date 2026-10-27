"""Image helpers: normalise uploads, data URLs, numbered-box annotation."""

from __future__ import annotations

import base64
import hashlib
import io

from PIL import Image, ImageDraw, ImageFont, ImageOps

MAX_SIDE = 1600  # longest side sent to models; keeps payloads small and coordinates stable


def sha256(data: bytes) -> str:
    """Hex SHA-256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def normalise_upload(data: bytes) -> tuple[bytes, str, int, int]:
    """Decode any common image, apply EXIF rotation, cap the size, re-encode.

    PNG inputs that are already small and upright are returned unchanged, so
    bundled samples keep their hash. Returns (bytes, mime, width, height).
    """
    img = Image.open(io.BytesIO(data))
    fmt = (img.format or "").upper()
    upright = ImageOps.exif_transpose(img)
    if fmt == "PNG" and max(img.size) <= MAX_SIDE and upright.size == img.size:
        return data, "image/png", img.width, img.height
    img = upright.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue(), "image/jpeg", img.width, img.height


def data_url(data: bytes, mime: str) -> str:
    """``data:<mime>;base64,...`` as accepted by Meta Model API image inputs."""
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def annotate(data: bytes, boxes: list[tuple[str, tuple[float, float, float, float]]]) -> bytes:
    """Draw numbered boxes (set-of-marks) so a vision model can cite segment ids."""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    for label, (x1, y1, x2, y2) in boxes:
        draw.rectangle((x1, y1, x2, y2), outline=(220, 40, 40), width=3)
        tx, ty = x1, max(0, y1 - 26)
        tb = draw.textbbox((tx, ty), label, font=font)
        draw.rectangle(tb, fill=(220, 40, 40))
        draw.text((tx, ty), label, fill=(255, 255, 255), font=font)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()
