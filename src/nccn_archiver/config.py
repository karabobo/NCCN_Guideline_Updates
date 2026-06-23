from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _csv_env(name: str) -> set[str]:
    value = os.getenv(name, "")
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def _csv_list_env(name: str) -> tuple[str, ...]:
    value = os.getenv(name, "")
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _int_csv_env(name: str, default: tuple[int, ...]) -> tuple[int, ...]:
    value = os.getenv(name, "")
    if not value.strip():
        return default
    numbers: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if item:
            numbers.append(int(item))
    return tuple(numbers)


def _optional_int_env(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    parsed = int(value)
    return parsed if parsed > 0 else None


@dataclass(frozen=True)
class Settings:
    archive_dir: Path
    state_file: Path
    index_file: Path
    run_interval_hours: int
    username: str
    password: str
    cookie_header: str
    include_slugs: set[str]
    exclude_slugs: set[str]
    pdf_variants: set[str]
    categories: tuple[int, ...]
    detail_urls: tuple[str, ...]
    limit: int | None
    detail_limit: int | None
    request_delay_seconds: float
    max_concurrency: int
    min_pdf_bytes: int

    @classmethod
    def from_env(cls) -> "Settings":
        archive_dir = Path(os.getenv("NCCN_ARCHIVE_DIR", "/archive")).expanduser()
        return cls(
            archive_dir=archive_dir,
            state_file=Path(os.getenv("NCCN_STATE_FILE", archive_dir / "manifest.json")).expanduser(),
            index_file=Path(os.getenv("NCCN_INDEX_FILE", archive_dir / "index.yaml")).expanduser(),
            run_interval_hours=int(os.getenv("NCCN_RUN_INTERVAL_HOURS", "24")),
            username=os.getenv("NCCN_USERNAME", ""),
            password=os.getenv("NCCN_PASSWORD", ""),
            cookie_header=os.getenv("NCCN_COOKIE", ""),
            include_slugs=_csv_env("NCCN_INCLUDE_SLUGS"),
            exclude_slugs=_csv_env("NCCN_EXCLUDE_SLUGS"),
            pdf_variants=_csv_env("NCCN_PDF_VARIANTS") or {"primary"},
            categories=_int_csv_env("NCCN_CATEGORIES", (1, 2, 3, 4)),
            detail_urls=_csv_list_env("NCCN_DETAIL_URLS"),
            limit=_optional_int_env("NCCN_LIMIT"),
            detail_limit=_optional_int_env("NCCN_DETAIL_LIMIT"),
            request_delay_seconds=float(os.getenv("NCCN_REQUEST_DELAY_SECONDS", "2")),
            max_concurrency=max(1, int(os.getenv("NCCN_MAX_CONCURRENCY", "2"))),
            min_pdf_bytes=max(1, int(os.getenv("NCCN_MIN_PDF_BYTES", "1024"))),
        )

    @property
    def has_login_config(self) -> bool:
        return bool(self.username and self.password)
