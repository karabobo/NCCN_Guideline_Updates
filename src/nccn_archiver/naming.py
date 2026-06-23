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
