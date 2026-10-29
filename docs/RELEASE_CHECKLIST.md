# V1 Release Candidate Checklist

The V1 release should be based on **one reviewed consolidated PR against `main`**, not an unreviewed sequence of independent production deployments. This checklist is the release gate, not a declaration that everything below is complete.

## 1. Source and change management

- [x] Base the consolidated candidate on the tip of draft PR #14, which already contains the cumulative work of PRs #1–#14.
- [x] Keep the existing fourteen PRs and the deployed private Railway watcher unchanged during review.
- [ ] Inspect the consolidated diff against `main` for secrets, generated files, third-party code/license restrictions and accidental production-specific settings.
- [ ] Review the full PR and obtain maintainer approval before merge. **Do not merge or tag V1 automatically.**
- [ ] After merge, decide whether to close now-redundant draft PRs with links to the consolidated PR. Keep their historical discussion accessible.

## 2. Clean installation

- [x] Provide a short, current Windows CMD / macOS / Linux quick start.
- [x] Provide a local offline preflight that reports market/area coverage and request budget without secrets or live requests.
- [x] Add a CI test for importing the app and running preflight against a fresh copy of `config.example.json` in an isolated temporary directory.
- [ ] Independently clone into a **new directory** on a clean Windows machine and follow the README step by step.
- [ ] Try a clean macOS/Linux install and Docker Compose start/stop cycle with a fresh volume, verifying port 8080 is **not publicly exposed**.
- [ ] Verify the wizard can add/remove/save model variants, generate backups and correctly handle an invalid existing config.

## 3. Real pickup and alerts

- [x] **US:** manually observed a real product/store response (Delaware R102, one SKU) during October 2026 testing.
- [x] **Canada:** manually observed a real product/store response (Toronto R121, one SKU) during October 2026 testing.
- [ ] Verify **several SKU variants** and **more than one store** per area; one successful pair is not exhaustive endpoint validation.
- [ ] Verify behavior when Apple returns missing products, stores, invalid schema, 429 and 541 without increasing request frequency.
- [ ] Test Discord delivery in a **dedicated private test webhook** with permission; offline unit tests only simulate posting.
- [ ] Confirm the first-run alert behavior, state persistence across restart, deferred negative transitions and retry behavior.
- [ ] **FR/GB:** retain experimental label until actual live responses and store coverage are independently verified.
- [ ] Verify official Apple buy-page catalog extraction against current live HTML, including color/storage and carrier ambiguity; failures must be explicit.

## 4. Security, data and deployment

- [x] Avoid committing `.env`, `config.json`, state/history and their backups.
- [x] Bind both local servers to loopback by default. `WATCHER_HOST` is explicit for hosted dashboard use.
- [x] Do not return unknown private config fields through the wizard configuration API.
- [x] Avoid printing Discord exception text that may contain the webhook URL.
- [ ] Review all logs and API payloads for personal locations, product selections and secrets.
- [ ] Plan hosted authentication or firewall/routing restrictions before making the dashboard public.
- [ ] Before changing Railway, review persistent volumes, host binding, single-worker behavior and deployment rollback procedure.
- [ ] Confirm the watcher can be stopped and rolled back without corrupting state/history or deleting user configuration.

## 5. Code and documentation quality

- [x] Keep the CI matrix at Python 3.12/3.14 × Windows/Ubuntu and ensure strict JavaScript syntax validation on current Node.
- [x] Align documentation with current model preview → add → save → restart workflow, unknown pricing, and conservative stock semantics.
- [ ] Run the full CI matrix on the **final consolidated commit**; confirm every job green before requesting review.
- [ ] Exercise an isolated, mocked scenario for multi-country, multi-batch partial coverage (plus dashboard/API rendering).
- [ ] Review dependency versions, upstream endpoints, rate limits and cross-platform compatibility.
- [ ] Consider a future outbox/idempotency design for Discord retries; current delivery is best effort.
- [ ] Confirm meaningful versioning/release notes and publish a tag/release **only after merge and approval**.

## Suggested pre-release commands

**Windows CMD** (inside the clone):

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe preflight.py
```

**Safe live validation only when authorized to call Apple:**

```bat
set WATCHER_DISABLE_DISCORD=1
set STATE_FILE=%TEMP%\apple-watcher-rc-test-state.json
set HISTORY_FILE=%TEMP%\apple-watcher-rc-test-history.json
.venv\Scripts\python.exe app.py
```

Check `/api/status` once, record which markets and stores actually returned, stop with Ctrl+C. Do not conflate offline test success with confirmation of all real Apple inventory, tax or price data.

## Decision

The consolidated PR is **reviewable**, but the release remains a **candidate** until the unchecked manual and security gates have been addressed. The existing private production watcher must remain unchanged unless the owner explicitly chooses a migration.
