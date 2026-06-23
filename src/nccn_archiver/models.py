from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Guideline:
    title: str
    slug: str
    url: str
    category: str = ""
    variant: str = "primary"
    label: str = "NCCN Guidelines"
    detail_url: str = ""
    version: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class DownloadedFile:
    guideline: Guideline
    content: bytes
    content_type: str
    source_url: str


@dataclass(frozen=True)
class RunSummary:
    checked: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
