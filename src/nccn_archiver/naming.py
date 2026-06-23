from __future__ import annotations

import re
from urllib.parse import urlparse


def slugify(value: str, fallback: str = "guideline") -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or fallback


def filename_from_url(url: str, fallback_slug: str) -> str:
    name = urlparse(url).path.rsplit("/", 1)[-1]
    if name.lower().endswith(".pdf"):
        return slugify(name[:-4], fallback_slug) + ".pdf"
    return slugify(fallback_slug) + ".pdf"


def safe_filename_part(value: str, fallback: str) -> str:
    value = value.strip()
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", value)
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"_+", "_", value).strip("._ ")
    return value or fallback


def version_token(version: str | None, fallback_hash: str) -> str:
    if version:
        return safe_filename_part(version.replace(":", ""), fallback_hash[:12])
    return f"Version_unknown_{fallback_hash[:12]}"


def guideline_pdf_filename(title: str, version: str | None, content_hash: str, variant: str = "primary") -> str:
    title_part = safe_filename_part(title, "Guideline")
    version_part = version_token(version, content_hash)
    if variant and variant != "primary":
        variant_part = safe_filename_part(variant, "variant")
        return f"NCCN_{title_part}_{variant_part}_{version_part}.pdf"
    return f"NCCN_{title_part}_{version_part}.pdf"
