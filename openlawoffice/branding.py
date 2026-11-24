"""Secure validation, re-encoding, and storage of firm logos.

Client-provided filenames, extensions, and MIME types are never trusted. Every
upload is decoded by Pillow, bounded in size and pixel count, re-encoded into a
fresh image (which drops metadata and appended payloads), and written under a
random filename outside the static directory.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import secrets
import tempfile
import warnings
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {
    "PNG": ("png", "image/png"),
    "JPEG": ("jpg", "image/jpeg"),
    "WEBP": ("webp", "image/webp"),
}
STORED_NAME_RE = re.compile(r"^[a-f0-9]{32}\.(?:png|jpg|webp)$")


class LogoValidationError(ValueError):
    """A user-facing problem with an uploaded logo."""


@dataclass(frozen=True)
class StoredLogo:
    stored_name: str
    content_type: str
    size_bytes: int
    width: int
    height: int
    sha256: str
    path: Path


def _logo_directory(create: bool = False) -> Path:
    directory = Path(current_app.config["FIRM_LOGO_UPLOAD_DIR"]).expanduser()
    if create:
        directory.mkdir(parents=True, exist_ok=True)
        try:
            directory.chmod(0o700)
        except OSError:  # pragma: no cover - platform/filesystem dependent
            current_app.logger.warning(
                "Could not restrict permissions on %s", directory
            )
    return directory


def stored_logo_path(stored_name: str | None) -> Path | None:
    """Resolve a stored logo name without allowing path traversal."""
    if not stored_name or not STORED_NAME_RE.fullmatch(stored_name):
        return None
    directory = _logo_directory().resolve()
    path = (directory / stored_name).resolve()
    if path.parent != directory:
        return None
    return path


def remove_logo_file(stored_name: str | None) -> None:
    path = stored_logo_path(stored_name)
    if path is None or not path.is_file():
        return
    try:
        path.unlink()
    except OSError:  # pragma: no cover - platform/filesystem dependent
        current_app.logger.warning("Could not remove old logo file %s", path)


def _reencode(
    image: Image.Image, source_format: str, max_bytes: int
) -> tuple[bytes, int, int]:
    """Re-encode at progressively smaller sizes until the output fits."""
    max_dimension = current_app.config["FIRM_LOGO_MAX_DIMENSION"]
    limits = [max_dimension]
    limits.extend(size for size in (1200, 900, 640, 480) if size < max_dimension)

    for limit in limits:
        candidate = image.copy()
        candidate.thumbnail((limit, limit), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        if source_format == "JPEG":
            if candidate.mode != "RGB":
                candidate = candidate.convert("RGB")
            candidate.save(
                buffer,
                format="JPEG",
                quality=90,
                optimize=True,
                progressive=True,
            )
        elif source_format == "WEBP":
            candidate.save(buffer, format="WEBP", quality=90, method=6)
        else:
            candidate.save(buffer, format="PNG", optimize=True)

        payload = buffer.getvalue()
        if len(payload) <= max_bytes:
            return payload, candidate.width, candidate.height

    raise LogoValidationError(
        "The image is too large after processing. Try a simpler logo."
    )


def store_logo(file_storage) -> StoredLogo:
    """Validate and persist an uploaded logo, returning its metadata."""
    if file_storage is None or not getattr(file_storage, "filename", ""):
        raise LogoValidationError("Choose an image file to upload.")

    max_bytes = current_app.config["FIRM_LOGO_MAX_BYTES"]
    data = file_storage.read(max_bytes + 1)
    if not data:
        raise LogoValidationError("The uploaded file is empty.")
    if len(data) > max_bytes:
        raise LogoValidationError(
            f"Logo images must be {max_bytes // (1024 * 1024)} MB or smaller."
        )

    min_dimension = current_app.config["FIRM_LOGO_MIN_DIMENSION"]
    max_pixels = current_app.config["FIRM_LOGO_MAX_PIXELS"]

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                source_format = (source.format or "").upper()
                if source_format not in ALLOWED_FORMATS:
                    raise LogoValidationError("Upload a PNG, JPEG, or WebP image.")
                if getattr(source, "n_frames", 1) != 1:
                    raise LogoValidationError(
                        "Animated images are not supported. Upload a still image."
                    )

                width, height = source.size
                if width < min_dimension or height < min_dimension:
                    raise LogoValidationError(
                        f"Logo images must be at least {min_dimension} by "
                        f"{min_dimension} pixels."
                    )
                if width * height > max_pixels:
                    raise LogoValidationError(
                        "The image dimensions are too large. Upload a smaller image."
                    )

                source.load()
                oriented = ImageOps.exif_transpose(source)
                has_alpha = oriented.mode in {"RGBA", "LA"} or (
                    oriented.mode == "P" and "transparency" in oriented.info
                )
                working = oriented.convert("RGBA" if has_alpha else "RGB")
    except LogoValidationError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise LogoValidationError(
            "That file is not a valid PNG, JPEG, or WebP image."
        ) from exc

    payload, stored_width, stored_height = _reencode(working, source_format, max_bytes)
    digest = hashlib.sha256(payload).hexdigest()
    extension, content_type = ALLOWED_FORMATS[source_format]

    directory = _logo_directory(create=True)
    for _ in range(3):
        stored_name = f"{secrets.token_hex(16)}.{extension}"
        final_path = directory / stored_name
        if not final_path.exists():
            break
    else:  # pragma: no cover - astronomically unlikely
        raise LogoValidationError("Could not allocate a storage name for the logo.")

    descriptor = None
    temp_path = None
    try:
        descriptor, temp_path = tempfile.mkstemp(
            dir=directory, prefix=".logo-", suffix=".tmp"
        )
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(payload)
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, final_path)
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        if temp_path is not None:
            with contextlib.suppress(OSError):
                os.unlink(temp_path)
        current_app.logger.exception("Could not store the uploaded firm logo")
        raise LogoValidationError("The logo could not be saved. Try again.") from exc

    return StoredLogo(
        stored_name=stored_name,
        content_type=content_type,
        size_bytes=len(payload),
        width=stored_width,
        height=stored_height,
        sha256=digest,
        path=final_path,
    )
