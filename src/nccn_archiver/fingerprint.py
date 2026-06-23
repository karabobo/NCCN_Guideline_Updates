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
    method: str


def _byte_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _normalize_line(line: str) -> str:
    return " ".join(line.split())


def pdf_fingerprint(content: bytes) -> PdfFingerprint:
    byte_digest = _byte_sha256(content)
    try:
        reader = PdfReader(io.BytesIO(content))
        lines = [f"pages:{len(reader.pages)}"]
        for page in reader.pages:
            for raw_line in (page.extract_text() or "").splitlines():
                line = _normalize_line(raw_line)
                if not line:
                    continue
                if PRINTED_BY_PATTERN.match(line):
                    continue
                lines.append(line)
        content_digest = hashlib.sha256("\n".join(lines).encode("utf-8", "replace")).hexdigest()
        return PdfFingerprint(
            byte_sha256=byte_digest,
            content_sha256=content_digest,
            page_count=len(reader.pages),
            method="pypdf-text-with-nccn-footer-filter",
        )
    except Exception as exc:
        LOGGER.warning("PDF content fingerprint failed; falling back to byte hash: %s", exc)
        return PdfFingerprint(
            byte_sha256=byte_digest,
            content_sha256=byte_digest,
            page_count=None,
            method="byte-sha256-fallback",
        )
