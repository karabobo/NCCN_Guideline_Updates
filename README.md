# NCCN Guidelines PDF Archiver

Dockerized archiver for downloading NCCN Guidelines PDFs with your own NCCN account and keeping a local version history.

This project does not use NCCN AccessKey or Developer API. It builds an index from public NCCN guideline pages, logs in only when PDF download requires it, and stores the PDFs in a local archive. Use it only for your authorized personal or internal use under NCCN terms. Do not redistribute the archived PDFs.

## What It Saves

- `archive/index.yaml`: current guideline index discovered from NCCN pages.
- `archive/manifest.json`: archive state, source URLs, checksums, sizes, and saved paths.
- `archive/latest/<slug>.pdf`: latest known PDF for each guideline.
- `archive/guidelines/<slug>/<version-or-checksum>/<file>.pdf`: historical copies when content changes.

## Quick Start

```bash
cp .env.example .env
```

Edit `.env`:

```env
NCCN_USERNAME=your-email@example.com
NCCN_PASSWORD=your-password
NCCN_LIMIT=1
NCCN_DETAIL_LIMIT=1
```

`NCCN_LIMIT=1` limits downloads. `NCCN_DETAIL_LIMIT=1` limits detail pages read per category while testing. Clear both after you confirm the archive works.

## Step 1: Build the Index Only

This does not download PDFs.

```bash
docker compose run --rm nccn-archiver --index-only
```

Check `archive/index.yaml` and pick a slug for a small test, for example:

```env
NCCN_INCLUDE_SLUGS=gastric-cancer
NCCN_LIMIT=
NCCN_DETAIL_LIMIT=
```

For the fastest single-guideline test, bypass category scanning:

```env
NCCN_DETAIL_URLS=https://www.nccn.org/guidelines/nccn-guidelines/guidelines-detail?category=1&id=1434
```

## Step 2: Test One Download

This logs in and downloads the selected PDF, but does not save it.

```bash
docker compose run --rm nccn-archiver --dry-run
```

Then save it for real:

```bash
docker compose run --rm nccn-archiver
```

## Step 3: Run on a Schedule

Clear test filters when you are ready:

```env
NCCN_INCLUDE_SLUGS=
NCCN_LIMIT=
```

Start the scheduled service:

```bash
docker compose up -d nccn-archiver-cron
```

Default interval:

```env
NCCN_RUN_INTERVAL_HOURS=24
```

## Filters

Archive only selected guidelines:

```env
NCCN_INCLUDE_SLUGS=breast-cancer,colon-cancer,gastric-cancer
```

Skip selected guidelines:

```env
NCCN_EXCLUDE_SLUGS=older-adult-oncology
```

Limit categories:

```env
NCCN_CATEGORIES=1,2,3,4
```

Or list exact guideline detail pages:

```env
NCCN_DETAIL_URLS=https://www.nccn.org/guidelines/nccn-guidelines/guidelines-detail?category=1&id=1434
```

## PDF Variants

By default, only the main professional guideline PDF is archived:

```env
NCCN_PDF_VARIANTS=primary
```

Optional values:

```env
NCCN_PDF_VARIANTS=primary,evidence_blocks
NCCN_PDF_VARIANTS=all
```

Other recognized variants are `basic_framework`, `core_framework`, `enhanced_framework`, `patient`, and `harmonized`.

## Login Fallback

If normal username/password login is blocked by MFA, SSO, or browser checks, you can paste your own active NCCN cookie string:

```env
NCCN_COOKIE=ASP.NET_SessionId=...; other_cookie=...
```

Treat this like a password. It expires and should not be committed.

## Operational Notes

- The script stores the raw PDF SHA-256, but update detection uses a normalized PDF content fingerprint so NCCN's per-download footer timestamp does not create duplicate versions.
- Credentials stay outside the image in `.env`.
- Default concurrency and delay are intentionally low.
- `--dry-run` still downloads PDFs to verify content and compute hashes, but it does not write them.
