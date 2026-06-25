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
class ArchivedUpdate:
    title: str
    slug: str
    category: str
    variant: str
    version: str
    previous_version: str
    source_url: str
    detail_url: str
    historical_path: str
    latest_path: str
    bytes: int
    page_count: int | None
    content_sha256: str
    archived_at: str


@dataclass(frozen=True)
class FailedGuideline:
    title: str
    slug: str
    category: str
    variant: str
    detail_url: str
    error: str


@dataclass(frozen=True)
class RunSummary:
    checked: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    updates: tuple[ArchivedUpdate, ...] = ()
    failures: tuple[FailedGuideline, ...] = ()
