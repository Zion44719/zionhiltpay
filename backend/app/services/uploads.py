"""
Safe handling of uploaded images (profile photos, proof-of-address photos).

Nothing the client sends is trusted: size is capped while reading, the bytes must decode as a real
JPEG/PNG/WebP image, and the image is RE-ENCODED from its pixels, so metadata (GPS/EXIF) and anything
smuggled inside the file is discarded. Stored under a random name, outside any web-served folder, and only
ever served through authenticated endpoints. PDFs are deliberately not accepted for proof of address.
"""
import io
import os
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from app.core.config import settings

Image.MAX_IMAGE_PIXELS = 25_000_000          # refuse decompression bombs
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
KINDS = ("avatars", "documents", "logos")
NAME_RE = re.compile(r"^[0-9a-f]{32}\.(jpg|png)$")
BACKEND_DIR = Path(__file__).resolve().parents[2]


def upload_root() -> Path:
    root = Path(settings.UPLOAD_DIR)
    return root if root.is_absolute() else BACKEND_DIR / root


def _dir(kind: str) -> Path:
    if kind not in KINDS:
        raise ValueError("unknown upload kind")
    d = upload_root() / kind
    d.mkdir(parents=True, exist_ok=True)
    return d


def file_path(kind: str, name: str) -> Path:
    """Path for a stored file. The name comes from our own database, but is validated anyway."""
    if not name or not NAME_RE.fullmatch(name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return _dir(kind) / name


async def read_limited(file: UploadFile, max_bytes: int) -> bytes:
    data = bytearray()
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > max_bytes:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"That file is too large (max {max_bytes // 1_000_000} MB)")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file is empty")
    return bytes(data)


def _decode(data: bytes, keep_alpha: bool = False) -> Image.Image:
    try:
        im = Image.open(io.BytesIO(data))
        if im.format not in ALLOWED_FORMATS:
            raise ValueError("format")
        im.load()  # fully decode: catches truncated files and triggers the decompression-bomb guard
    except (UnidentifiedImageError, ValueError, OSError, Image.DecompressionBombError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That isn't a valid JPEG, PNG or WebP image")
    im = ImageOps.exif_transpose(im)
    if keep_alpha:
        return im.convert("RGBA")                 # logos keep their transparency
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        return bg
    return im.convert("RGB")


def _jpeg(im: Image.Image) -> bytes:
    out = io.BytesIO()
    im.save(out, format="JPEG", quality=85, optimize=True)   # fresh encode: no EXIF, no trailing data
    return out.getvalue()


def _avatar(data: bytes) -> bytes:
    im = _decode(data)
    return _jpeg(ImageOps.fit(im, (512, 512), method=Image.LANCZOS))   # centre-crop to a square


def _document(data: bytes) -> bytes:
    im = _decode(data)
    if min(im.size) < 300:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The photo is too small to read. Please take a clearer, closer picture.")
    im.thumbnail((1600, 1600), Image.LANCZOS)
    return _jpeg(im)


def _logo(data: bytes) -> bytes:
    """A partner logo: re-encoded from pixels as a transparent PNG, scaled to fit 480x240. SVG is refused on
    purpose (an SVG file can carry scripts), and so is anything that isn't a real raster image."""
    im = _decode(data, keep_alpha=True)
    if min(im.size) < 24:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That logo is too small. Please upload one at least 24 pixels tall.")
    im.thumbnail((480, 240), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, format="PNG", optimize=True)
    return out.getvalue()


async def make_logo(data: bytes) -> bytes:
    return await run_in_threadpool(_logo, data)


async def make_avatar(data: bytes) -> bytes:
    return await run_in_threadpool(_avatar, data)


async def make_document(data: bytes) -> bytes:
    return await run_in_threadpool(_document, data)


def save_file(kind: str, data: bytes, ext: str = "jpg") -> str:
    if ext not in ("jpg", "png"):
        raise ValueError("unsupported extension")
    name = uuid.uuid4().hex + "." + ext
    target = _dir(kind) / name
    tmp = target.with_suffix(".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, target)       # atomic: a half-written file is never visible
    return name


def delete_file(kind: str, name) -> None:
    if name and NAME_RE.fullmatch(name):
        try:
            (_dir(kind) / name).unlink(missing_ok=True)
        except OSError:
            pass
