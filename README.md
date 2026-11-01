# Apple Stock Watcher

**Unofficial self-hosted Apple Store pickup availability watcher.** Choose supported products, nearby Apple Retail Stores, view a model-grouped dashboard, and optionally get Discord stock-change notifications. It **does not buy or reserve products** and is not affiliated with Apple.

> **1.1 development branch:** worldwide store selection is being prepared separately from the published `v1.0.0`. US/Canada retain their completed V1 validation. Additional markets remain experimental, with [bounded live-check evidence](docs/REGIONAL_VALIDATION.md) recorded separately. Apple endpoints are undocumented; no claim of all-SKU/all-store coverage is made. See [V1 notes](docs/RELEASE_NOTES_V1.md).

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

1. **Choose a store** — search its country/city/name/ID, then click **Configure selected store**. The wizard shows the adapter's limits, selects that country's catalog/currency and prepares the store without adding an incomplete area.
2. **Choose regional products** — enter a complete local postal code, find a model's real variants, filter if desired, then **Add selected variants to watchlist**. US/Canada products cannot fill a French area. Discovery remains on demand and may fail; no guessed SKU is created.
3. **Add completed store selection** — available when regional products and a local search are entered. Stores using the same country/search can share an area. A notice explains when an existing all-returned-stores area will become a precise store filter.
4. **Save private configuration**, then **restart `app.py`**. Save writes `config.json`; it does not start monitoring. The watcher subsequently checks whether Apple actually returned the chosen stores and variants.

For existing areas, use **Choose products for this country** to repair a missing
association. Removing the last regional product immediately shows the affected
areas and a resolution action; removing an area leaves its products available to
edit/remove. All areas in a country share that country's product selection.
Manual products have visible Edit/Remove actions. Changing a product country
requires discovering/adding its regional replacement, so an old SKU or price is
never silently converted to a new market.

The wizard creates readable product IDs such as `iphone_18_pro_max_512gb_silver_ca`. **Area IDs identify locations, not devices** (`us_19702`, `ca_m5b2h1`), since one location can monitor multiple models. The optional green toast confirms draft edits; you must still Save and restart.

**Carrier caveat:** activation choices at checkout might not have distinct stock SKUs. Missing carrier metadata means **unknown**, not “unlocked.” If catalog discovery fails, add an independently verified SKU under **Advanced: individual SKUs**. Product prices may be unknown and must never be guessed from unrelated variants.

## Worldwide store selection (next-version branch)

The setup wizard contains an offline snapshot of **535 official stores in 27
countries/territories**, observed from [Apple's directory](https://www.apple.com/retail/storelist/)
on October 30, 2026. Search by country, city, name or store ID and add a store
to a guided store setup. Complete its local postal search and regional products,
then add the completed selection, Save and restart. Directory browsing and
configuration readiness make no Apple requests and do not confirm live coverage.

US/CA retain their recorded live evidence. The other 24 selectable markets are
**experimental regional adapters**, requiring explicit opt-in. The
[verification record](docs/REGIONAL_VALIDATION.md) distinguishes completed bounded
checks from unverified combinations; errors/missing responses remain unknown.
Macao is directory-only with no enabled pickup adapter.
The snapshot is not a live opening/closure feed or a guarantee of pickup eligibility.
There is no "scan all worldwide stores" mode; the 8-area/24-request budgets remain.
See [worldwide coverage](docs/WORLDWIDE_COVERAGE.md).

Use a **complete local postal code** when a city search returns no stores. In the
recorded checks, a full postcode returned stores in China and the Netherlands
where the earlier city/incomplete-postcode searches had returned none. An empty
response means unconfirmed coverage, not that every store is sold out.

## Countries and polling limits

| Market | Availability support | Location input |
| --- | --- | --- |
| United States (`US`) | Live-tested for selected SKU/store pairs | Five-digit ZIP |
| Canada (`CA`) | Live-tested for selected SKU/store pairs | Postal code or city |
| France (`FR`) | Experimental, explicit opt-in; bounded check recorded | Five-digit postal code or city |
| United Kingdom (`GB`) | Experimental, explicit opt-in; bounded check recorded | UK postcode or city |
| Other selectable markets | Experimental, explicit opt-in; see [per-market results](docs/REGIONAL_VALIDATION.md) | Full local postal code or city; results vary by market |

Every configured product country needs **at least one monitoring area in the same country**. A location searches nearby stores returned by Apple, **not every Apple Store in that city or country**. Set optional Apple Store IDs to limit to selected shops; an empty list includes all stores returned by the query. The next-version branch adds opt-in experimental candidates for additional directory markets; Macao remains directory-only.

Conservative limits: **8 monitoring areas**, **96 configured product IDs**, **48 SKUs/model**, **12 product IDs per Apple request**, **24 pickup requests per scan**. More areas and products increase intervals; HTTP 429/541 triggers longer cooldowns. Avoid aggressive polling.

Live integration uses undocumented Apple endpoints. Apple's
[Website Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html)
restrict automated access and monitoring; request limits and a successful response
do not establish permission. Check applicable authorization before live discovery
or polling. [Recorded verification and permission limits](docs/REGIONAL_VALIDATION.md)
are separate from current inventory and official support.

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

The complete wizard DOM regression needs Node 18+ and test-only dependencies:
`npm ci --prefix tests/ui --ignore-scripts --no-audit --no-fund`. CI installs these
and runs the interaction tests on Windows and Ubuntu. Node/jsdom are not required
to run the Python watcher. See [v1.1 candidate notes](docs/RELEASE_NOTES_V1_1.md).

- [Architecture](docs/ARCHITECTURE.md) — data flows and module responsibilities
- [V1 release notes](docs/RELEASE_NOTES_V1.md) — features, validation, upgrade and known limits
- [Publication review](docs/PUBLICATION_REVIEW.md) — findings and review scope
- [Release checklist](docs/RELEASE_CHECKLIST.md) — requirements for a safe V1
- [Roadmap](ROADMAP.md) — planned functionality and experimental gaps
- [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [MIT License](LICENSE)

This is an independent community project. Apple, Apple Store and iPhone are trademarks of Apple Inc.
