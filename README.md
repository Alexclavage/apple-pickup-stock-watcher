# Apple Stock Watcher

**Unofficial self-hosted Apple Store pickup availability watcher.** Choose supported products, nearby Apple Retail Stores, view a model-grouped dashboard, and optionally get Discord stock-change notifications. It **does not buy or reserve products** and is not affiliated with Apple.

> **V1.0.0:** a user-validated US/Canada scan observed 3 variants across 17 returned stores with zero coverage issues in that scan. This is not validation of all SKUs or stores. Catalog parsing and France/UK adapters remain experimental. Apple endpoints are undocumented. See [V1 notes](docs/RELEASE_NOTES_V1.md) and [release checklist](docs/RELEASE_CHECKLIST.md).

## Quick start (Windows CMD)

Requires **Python 3.10+**, Git (if cloning), and Internet for live availability.

```bat
git clone https://github.com/Alexclavage/apple-pickup-stock-watcher.git
cd apple-pickup-stock-watcher
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
copy config.example.json config.json
.venv\Scripts\python.exe setup_wizard.py
```

Open **http://127.0.0.1:8091**. The wizard works on your computer only. Configure products and matching monitoring areas, then click **Save private configuration**. The included sample SKUs, prices, stores and locations are **illustrative, not independently verified**.

Stop the wizard with Ctrl+C. Test your config **offline**:

```bat
.venv\Scripts\python.exe preflight.py
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

If the preflight says **READY**, start real monitoring:

```bat
.venv\Scripts\python.exe app.py
```

Open **http://127.0.0.1:8080**. This starts real Apple requests and continues polling until Ctrl+C. The dashboard is **unauthenticated and localhost-only by default**: do not open it to the Internet without access controls.

**macOS/Linux:** use `python3 -m venv .venv`, `.venv/bin/python -m pip install -r requirements.txt`, `cp` instead of `copy` and `.venv/bin/python` for subsequent commands.

### How the wizard works

1. **Find variants** — optional, on-demand preview of SKU variants from official Apple buy pages, not yet added.
2. **Add selected variants to watchlist** — optional filters for color, storage and a **verified** carrier attribute where Apple actually supplies one.
3. **Save private configuration** — writes `config.json`; does not start monitoring. The watchlist summary and Save banner distinguish preview, unsaved and saved states.
4. **Restart `app.py`** — running monitoring reads the latest saved settings.

The wizard creates readable product IDs such as `iphone_18_pro_max_512gb_silver_ca`. **Area IDs identify locations, not devices** (`us_19702`, `ca_m5b2h1`), since one location can monitor multiple models. The optional green toast confirms draft edits; you must still Save and restart.

**Carrier caveat:** activation choices at checkout might not have distinct stock SKUs. Missing carrier metadata means **unknown**, not “unlocked.” If catalog discovery fails, add an independently verified SKU under **Advanced: individual SKUs**. Product prices may be unknown and must never be guessed from unrelated variants.

## Countries and polling limits

| Market | Availability support | Location input |
| --- | --- | --- |
| United States (`US`) | Live-tested for selected SKU/store pairs | Five-digit ZIP |
| Canada (`CA`) | Live-tested for selected SKU/store pairs | Postal code or city |
| France (`FR`) | Experimental, explicit opt-in; not live-validated | Five-digit postal code or city |
| United Kingdom (`GB`) | Experimental, explicit opt-in; not live-validated | UK postcode or city |

Every configured product country needs **at least one monitoring area in the same country**. A location searches nearby stores returned by Apple, **not every Apple Store in that city or country**. Set optional Apple Store IDs to limit to selected shops; an empty list includes all stores returned by the query. Other countries are unsupported.

Conservative limits: **8 monitoring areas**, **96 configured product IDs**, **48 SKUs/model**, **12 product IDs per Apple request**, **24 pickup requests per scan**. More areas and products increase intervals; HTTP 429/541 triggers longer cooldowns. Avoid aggressive polling.

`preflight.py` checks coverage, number of products/areas, estimated request cost and whether alerts are enabled. It performs **no Apple, FX or Discord calls**, writes no files, and does not verify whether SKUs or prices are real. `python preflight.py --json` returns sanitized counts rather than SKUs, postal codes or secrets.

### Safe real test without Discord alerts

In a separate Windows CMD, after preflight:

```bat
set WATCHER_DISABLE_DISCORD=1
set STATE_FILE=%TEMP%\apple-stock-watcher-test-state.json
set HISTORY_FILE=%TEMP%\apple-stock-watcher-test-history.json
.venv\Scripts\python.exe app.py
```

Inspect `http://127.0.0.1:8080/api/status`; stop the watcher with Ctrl+C after the first check. **This contacts Apple** (and potentially an FX service) but does **not** send Discord messages or write your normal state/history. Close that CMD session after testing. Avoid running a second poller alongside production on the same stores.

### Explicit one-shot live integration checks (V1 validation only)

These commands **never launch the polling worker** and never change `STATE_FILE`, `HISTORY_FILE` or `config.json`. They make **no network requests unless an explicit confirmation flag is provided**. Both commands are separate from the optional ongoing monitor.

**1. Apple multi-variant pickup test.** Use the setup wizard to add **at least two distinct Apple SKU references in the same country**, based on real product data, and save the private config. The example config contains only one SKU per country and will be intentionally refused by this test. Close the wizard and ensure no other local watcher is polling simultaneously. Check `preflight.py` first, then:

```bat
set WATCHER_DISABLE_DISCORD=1
.venv\Scripts\python.exe integration_smoke.py apple --confirm-live
```

This performs **one actual Apple scan** over your configured areas (potentially several individual Apple requests) and may use the FX provider for price estimates. It reports sanitized **country counts, observed distinct variants, number of stores, availability categories and coverage errors**. It does **not** send any Discord messages, write state/history, reveal SKUs/postal codes or assert that an unverified product is sold out. `PASS` means at least two distinct same-market variants were observed, with no known partial results or coverage issues in that checked scan; it is not proof of nationwide stock accuracy.

**2. Single Discord delivery test.** Create a **dedicated private test channel** in your own Discord server and a webhook for that channel. Paste the webhook URL into your **local** `.env` only as `DISCORD_WEBHOOK=...`; never paste the URL into chat, screenshots, GitHub, or terminal output. In the test CMD:

```bat
set WATCHER_DISABLE_DISCORD=
.venv\Scripts\python.exe integration_smoke.py discord --confirm-send
```

This sends **exactly one clearly labeled test message**, with mentions disabled, to that private webhook. It does not query Apple, start monitoring or write any state. A reported HTTP **200/204** means Discord accepted the request: check that the message actually appears in your test channel. HTTP 429 means rate limited; do not retry immediately. Do not use your production alert webhook for this test. You may remove the test webhook from `.env` after confirming delivery.

**3. Local dashboard security:** with `app.py` running in a disposable test session, `netstat -ano -p TCP | findstr ":8080"` should show only **127.0.0.1:8080** (and possibly local established connections), never a `0.0.0.0:8080` listening socket. The setup wizard should similarly listen only at **127.0.0.1:8091**. This local binding test does **not** validate hosted firewall, authentication or public Railway access.

## Dashboard, stock status and Discord

The dashboard groups SKUs by **model, market and returned Apple Store**, with expandable variant details. Manually configured products appear separately. Search, availability filters, recent stock changes and last-check times are shown.

- **AVAILABLE:** an Apple response confirms a selected variant available in a checked store.
- **UNAVAILABLE:** a selected variant was confirmed unavailable during a **fully verified** cycle; it says nothing about other stores.
- **PARTIAL / UNKNOWN:** unconfigured region, failed batch/store request, missing SKU, inconsistent returned store sets or other missing verification. **Never equivalent to sold out.**

During a partial cycle, genuine newly available responses can be reported, but **stock-out alerts and history transitions are deferred** until a fully verified cycle. Following a prior outage, “monitoring restored” is only sent on a complete check.

Discord is optional. Put `DISCORD_WEBHOOK` only in private `.env` or hosted secrets — never in Git. The wizard supports alert filters `alert_store_ids` and `alert_product_ids`: missing filters mean “all,” while explicit empty lists disable that alert dimension. `WATCHER_DISABLE_DISCORD=1` disables outbound Discord delivery, even with a webhook configured.

Prices and conversions are **estimates**. Canadian tax is a user-configurable estimate (sample 13%, **not** a national rate). US tax estimates cover implemented jurisdictions only. FR/GB inputs are assumed VAT-inclusive. Verify stock, final price and taxes with Apple before traveling.

## Security, state and compatibility

- `config.json`, `.env`, history/state files and backup files are ignored by Git and Docker. Never share these files unredacted.
- The setup wizard listens only on **127.0.0.1:8091** with localhost/origin/request-token checks; it backs up `config.json` on Save and preserves unknown legacy keys **server-side** without exposing them in the browser.
- The dashboard defaults to **127.0.0.1:8080**. `WATCHER_HOST=0.0.0.0` is an explicit opt-in for Docker or a protected reverse proxy; **this does not add login authentication**.
- Only **one polling worker** should own state/history files. Use a persistent volume for hosted storage. State and Discord delivery are best effort, not a transactional message queue.
- Without `config.json`, legacy built-in sample defaults can load. The preflight warns rather than treating sample settings as a verified real setup.
- The Apple catalog is refreshed **only when you search it**; variant lists are saved at selection time, not auto-updated in the background. Some Mac/Watch custom orders may not support pickup.

### HTTP endpoints

| Path | Purpose |
| --- | --- |
| `/` | Dashboard |
| `/api/status` | Last scan details (may expose store/product preferences) |
| `/api/history` | Stock-change history |
| `/health` | Process liveness **only**; not proof of Apple connectivity |
| `127.0.0.1:8091` | Separate setup wizard process |

### Docker Compose (localhost only)

```sh
cp .env.example .env
cp config.example.json config.json
docker compose up -d --build
```

Docker Compose binds the published dashboard to **127.0.0.1:8080** and stores state/history in a named volume. Stop with `docker compose down`, **without** `-v` unless you intend to delete saved data. Docker Compose does not run or expose the wizard. Windows CMD uses `copy` instead of `cp`.

## Contributing and release readiness

Run `python -m unittest discover -s tests -v`. Tests use **mocked** responses and make no live Apple/Discord calls; passing CI is not proof of complete real-world compatibility.

- [Architecture](docs/ARCHITECTURE.md) — data flows and module responsibilities
- [V1 release notes](docs/RELEASE_NOTES_V1.md) — features, validation, upgrade and known limits
- [Publication review](docs/PUBLICATION_REVIEW.md) — findings and review scope
- [Release checklist](docs/RELEASE_CHECKLIST.md) — requirements for a safe V1
- [Roadmap](ROADMAP.md) — planned functionality and experimental gaps
- [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [MIT License](LICENSE)

This is an independent community project. Apple, Apple Store and iPhone are trademarks of Apple Inc.
