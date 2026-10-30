# Apple Stock Watcher v1.0.0

**V1.0.0 — October 30, 2026.** The maintainer authorized publication and
[PR #15](https://github.com/Alexclavage/apple-pickup-stock-watcher/pull/15) was merged.

## First open-source V1

An unofficial MIT-licensed, self-hosted Apple Store pickup availability watcher,
with a local setup wizard, model-grouped dashboard and optional Discord alerts.
It does not purchase or reserve products and is not affiliated with Apple.

### Included

- US/Canada monitoring across selected areas/stores, bounded SKU batches,
  conservative polling intervals and rate-limit cooldowns.
- Local wizard: discover regional variants from official Apple buy pages,
  filter available color/storage/carrier metadata, preview, add and save.
  Manual SKU entry remains available when discovery cannot confirm a variant.
- Dashboard grouped by model, market and returned store, expandable variant
  details, search, filters and bounded recent stock-change history.
- Conservative AVAILABLE / UNAVAILABLE / PARTIAL / UNKNOWN handling: incomplete
  coverage never establishes a confirmed stock-out. Confirmed positives may
  notify during partial scans; negative transitions wait for a complete scan.
- Optional Discord notifications with store/product filters. First-run confirmed
  availability can notify; delivery is best effort, not guaranteed replay.
- Offline preflight, explicit opt-in one-shot integration tools, loopback defaults,
  wizard token/origin checks, private config backup and secret-safe HTTP errors.
- Source installation guides, localhost Docker Compose recipe, architecture,
  contributor/security documentation and offline Windows/Linux CI.

### Validation recorded October 30, 2026

- User: fresh Windows clone/environment/dependencies, preflight and then-current
  116-test suite (three JavaScript checks skipped locally with old Node).
- Candidate CI at `2af0fa5`: **124/124 tests in each of four environments**,
  Python 3.12/3.14 on Windows/Ubuntu, including eight integration-tool tests.
- User's real Apple scan: three variants observed across US/CA, 17 distinct
  returned stores, zero coverage issues in that scan.
- User confirmed receipt of the private Discord test and wizard binding to
  `127.0.0.1:8091`.

These are bounded observations, not proof of all products, stores or failure modes.
Final-head CI and publication status belong to the PR and
[publication checklist](RELEASE_CHECKLIST.md).

### Installation and upgrade

Follow the [README](../README.md). Python 3.10+ required; CI exercises 3.12/3.14.
V1 is distributed as source, not a PyPI package, installer or signed binary.
Docker builds locally from source; this PR publishes no registry image.

For existing installations: stop the watcher; privately back up `.env`,
`config.json` and files configured by `STATE_FILE` / `HISTORY_FILE`; update source
and dependencies. Keep private files instead of overwriting them with examples.
Run offline preflight and restart a single worker. Wizard Save does not restart it.
Legacy US ZIP/Canadian settings remain supported. Without `.env`, the default
state filename remains `state_v43.json`; `.env.example` selects `state.json`.

To roll back: stop the watcher and restore previous source/environment and private
backups. No automated migration or Railway deployment is included.

### Known limits

- Apple endpoints are undocumented. Catalog discovery and FR/GB adapters are
  experimental; FR/GB lack independent live validation.
- Coverage is limited to returned stores for configured areas. Unknown carrier
  metadata never establishes an unlocked device. Prices, FX and taxes are estimates.
- Dashboard has no built-in authentication: keep it local or supply access controls
  before hosting. `/health` reports process liveness, not stock accuracy.
- macOS clean installation, Docker runtime and hosted security remain unvalidated.
- State/history and Discord are best effort. Only one worker may own the files;
  a failed delivery can lose a notification. No exactly-once delivery guarantee.

The fourteen earlier draft PRs remain available for historical discussion.
This preparation leaves the private Railway watcher unchanged.
