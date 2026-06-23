from __future__ import annotations

import hashlib
import io
import logging
import re
from dataclasses import dataclass

from pypdf import PdfReader

LOGGER = logging.getLogger(__name__)

PRINTED_BY_PATTERN = re.compile(
    r"^Printed by .+ on .+ Copyright .+ National Comprehensive Cancer Network",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PdfFingerprint:
    byte_sha256: str
    content_sha256: str
    page_count: int | None
    version: str | None
    method: str


def _byte_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _normalize_line(line: str) -> str:
    return " ".join(line.split())


def _find_version(line: str) -> str | None:
    match = re.search(r"\bVersion[:\s]+(\d+\.\d{4})\b", line, flags=re.IGNORECASE)
    if not match:
        return None
    return f"Version {match.group(1)}"


def pdf_fingerprint(content: bytes) -> PdfFingerprint:
    byte_digest = _byte_sha256(content)
    try:
        reader = PdfReader(io.BytesIO(content))
        lines = [f"pages:{len(reader.pages)}"]
        version = None
        for page in reader.pages:
            for raw_line in (page.extract_text() or "").splitlines():
                line = _normalize_line(raw_line)
                if not line:
                    continue
                if not version:
                    version = _find_version(line)
                if PRINTED_BY_PATTERN.match(line):
                    continue
                lines.append(line)
        content_digest = hashlib.sha256("\n".join(lines).encode("utf-8", "replace")).hexdigest()
        return PdfFingerprint(
            byte_sha256=byte_digest,
            content_sha256=content_digest,
            page_count=len(reader.pages),
            version=version,
            method="pypdf-text-with-nccn-footer-filter",
        )
    except Exception as exc:
        LOGGER.warning("PDF content fingerprint failed; falling back to byte hash: %s", exc)
        return PdfFingerprint(
            byte_sha256=byte_digest,
            content_sha256=byte_digest,
            page_count=None,
            version=None,
            method="byte-sha256-fallback",
        )
