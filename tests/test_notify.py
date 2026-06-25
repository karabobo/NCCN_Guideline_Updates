from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from nccn_archiver.config import Settings
from nccn_archiver.models import ArchivedUpdate, FailedGuideline, RunSummary
from nccn_archiver.notify import build_feishu_payload, notify_run, should_notify


def make_settings(**overrides) -> Settings:
    values = {
        "archive_host_dir": Path("/volume1/Download/NCCN"),
        "archive_dir": Path("/archive"),
        "state_file": Path("/archive/manifest.json"),
        "index_file": Path("/archive/index.yaml"),
        "run_interval_hours": 24,
        "username": "",
        "password": "",
        "cookie_header": "",
        "include_slugs": set(),
        "exclude_slugs": set(),
        "pdf_variants": {"primary"},
        "categories": (1,),
        "detail_urls": (),
        "limit": None,
        "detail_limit": None,
        "request_delay_seconds": 2.0,
        "max_concurrency": 2,
        "min_pdf_bytes": 1024,
        "notify_provider": "feishu",
        "notify_on": "changes",
        "notify_title": "NCCN Guideline Updates",
        "notify_max_items": 20,
        "feishu_webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
        "feishu_secret": "",
    }
    values.update(overrides)
    return Settings(**values)


def make_update(**overrides) -> ArchivedUpdate:
    values = {
        "title": "Breast Cancer",
        "slug": "breast-cancer",
        "category": "1",
        "variant": "primary",
        "version": "Version 4.2026",
        "previous_version": "Version 3.2026",
        "source_url": "https://www.nccn.org/professionals/physician_gls/pdf/breast.pdf",
        "detail_url": "https://www.nccn.org/guidelines/",
        "historical_path": "/archive/guidelines/breast-cancer/Version_4.2026/file.pdf",
        "latest_path": "/archive/latest/NCCN_Breast_Cancer_Version_4.2026.pdf",
        "bytes": 123,
        "page_count": 42,
        "content_sha256": "abc123",
        "archived_at": "2026-06-26T00:00:00Z",
    }
    values.update(overrides)
    return ArchivedUpdate(**values)


class NotifyTests(unittest.TestCase):
    def test_build_feishu_payload_contains_stats_update_and_host_path(self) -> None:
        settings = make_settings(feishu_secret="secret")
        summary = RunSummary(
            checked=10,
            updated=1,
            skipped=8,
            failed=1,
            updates=(make_update(),),
            failures=(
                FailedGuideline(
                    title="Colon Cancer",
                    slug="colon-cancer",
                    category="1",
                    variant="primary",
                    detail_url="https://www.nccn.org/guidelines/",
                    error="download failed",
                ),
            ),
        )

        payload = build_feishu_payload(settings, summary, timestamp=1234567890)
        payload_text = str(payload)

        self.assertEqual(payload["msg_type"], "interactive")
        self.assertEqual(payload["timestamp"], "1234567890")
        self.assertIn("sign", payload)
        self.assertIn("Checked: **10**", payload_text)
        self.assertIn("Breast Cancer", payload_text)
        self.assertIn("Version 3.2026 -> Version 4.2026", payload_text)
        self.assertIn("/volume1/Download/NCCN/latest/NCCN_Breast_Cancer_Version_4.2026.pdf", payload_text)
        self.assertIn("Colon Cancer", payload_text)

    def test_changes_mode_skips_no_change_run(self) -> None:
        settings = make_settings()
        summary = RunSummary(checked=10, updated=0, skipped=10, failed=0)

        self.assertFalse(should_notify(settings, summary))

    def test_changes_mode_sends_failure_only_run(self) -> None:
        settings = make_settings()
        summary = RunSummary(checked=10, updated=0, skipped=9, failed=1)

        self.assertTrue(should_notify(settings, summary))

    def test_missing_webhook_does_not_raise(self) -> None:
        settings = make_settings(feishu_webhook_url="")
        summary = RunSummary(checked=1, updated=1, skipped=0, failed=0, updates=(make_update(),))

        asyncio.run(notify_run(settings, summary))


if __name__ == "__main__":
    unittest.main()
