# Apple Stock Watcher

An independent, unofficial, self-hosted Apple Store pickup availability checker. Includes a Flask dashboard, Discord alerts on stock changes, selectable product SKUs, optional EUR conversions, and tax estimates. **It does not purchase or reserve products.** Not affiliated with Apple.

## Long-term vision: worldwide monitoring by postal code or city

The long-term goal is to let anyone check pickup availability for selected Apple products in **supported countries worldwide**, by entering a **country plus a postal code or city**. Users will be able to add multiple areas and, for each area, monitor all returned official Apple Retail Stores or select individual stores.

Multiple monitoring areas mean more regional requests. The setup wizard will warn that this can increase refresh delays, trigger Apple rate limits, or temporarily interrupt monitoring. The scheduler will deduplicate overlapping stores, bound request volume, and report the last successful check. An unverified or stale result must **never** be shown as a confirmed out-of-stock result.

**Current status:** the US/Canadian monitor supports multiple selected areas. France and the UK now have **opt-in experimental adapters**, but their live responses have not been independently validated by this project. Other countries, automatic SKU discovery and worldwide coverage remain future work. A search area may return nearby stores, not every Apple Store in a country; broader coverage requires additional areas.

See [ROADMAP.md](ROADMAP.md) for the implementation plan and validation criteria.

## Requirements

Python 3.10+ and network access for live availability checks. The watcher reads an Apple retail pickup endpoint that can change or impose rate limits. Respect Apple's terms and do not increase request frequency excessively.

## Quick start (Windows CMD)

```bat
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
copy config.example.json config.json
.venv\Scripts\python.exe app.py
```

Open http://localhost:8080. On macOS/Linux use `python3 -m venv .venv`, `source .venv/bin/activate`, `pip install -r requirements.txt`, `cp .env.example .env`, `cp config.example.json config.json`, `python app.py`.

Set `DISCORD_WEBHOOK` only in your private `.env` file (or deployment environment), **never in `.env.example`**. Keep `config.json` private to avoid accidentally sharing location preferences. The included `.gitignore` and `.dockerignore` exclude these files.

## Visual setup wizard (local computer only)

The watcher includes a **separate browser-based setup wizard**, so you can manage products, Apple SKUs, selected monitoring areas, estimated tax and Discord alert filters without manually editing JSON.

On Windows CMD, after installing dependencies with the Quick start commands:

```bat
.venv\Scripts\python.exe setup_wizard.py
```

On macOS/Linux run `python setup_wizard.py` inside the activated environment. Open **http://127.0.0.1:8091**, edit the fields and click **Save private configuration**. The wizard reads `config.json` or starts with `config.example.json`. If it overwrites an existing config, it keeps one private backup in `config.json.bak`; both are excluded from Git and Docker. Restart the watcher after saving.

**Security:** the wizard is not part of the public dashboard. It binds to `127.0.0.1` only, checks origin and request tokens for saves, and never displays or saves your Discord webhook. Do not forward this port to the public Internet. The wizard can look up variant SKUs on official Apple buy pages when you request it, but that discovery is experimental and does not prove pickup availability. Verify product details before relying on the stock results.

## Optional variant filters: colour, storage and carrier

After choosing a model name and country in the local setup wizard, click **Monitor this model — choose options**. The watcher obtains all currently discoverable regional SKU variants and displays **Colour**, **Storage**, and **Carrier connection** filters before saving. By default, all discovered variants are selected; narrow to one colour, capacity or carrier where verifiable.

The UI shows how many actual SKUs match each combination and enforces the existing maximum of 48 SKUs per selected model. Choosing a variant does not trigger live monitoring until the private config is saved and the watcher restarts. Individual SKU editing remains in Advanced.

**Important caveat about carrier selection:** A carrier plan/eSIM activation choice at Apple's checkout is not necessarily a unique product part number. The app **never interprets a missing carrier field as 'unlocked'**. Options such as *Without a carrier*, *With a carrier*, or a specific carrier are offered only when Apple's **explicit product-variant metadata** identifies that choice. If Apple lists the same SKU with contradictory carrier annotations, the carrier is marked **unknown**, and users are told that a carrier-specific stock distinction cannot be verified.

If colour/storage/carrier data is missing or the selected combination yields no verifiable SKU, the wizard reports this instead of guessing. Selection is currently one value per attribute (or **All**) and may be repeated to change an existing model subscription. Carrier selection cannot guarantee a prepaid eSIM or a specific activation plan at pickup.

## Model-first monitoring dashboard

The read-only monitoring dashboard (`/`, generally port 8080) now displays **one section per monitored Apple model and country**, not one section per SKU. Each model section summarizes its selected colors/capacities, verified store results and the number of locations with an available variant. A store card opens a variant-by-variant breakdown (availability, Apple SKU, price if supplied). Manually configured products without a model subscription appear as individual sections.

**Status accuracy:** a missing SKU response or missing store remains **UNKNOWN**; it is never counted as confirmed out of stock. Partially completed checks are labelled **partial** even if some store stock is confirmed. After a full watcher error, previously cached rows are not displayed as current verified stock. "Unavailable" only describes **checked Apple Stores**, never every retailer or every store worldwide. Filters and store search still operate on the grouped cards.

The dashboard does **not** automatically start the monitoring worker when visited. Running `setup_wizard.py` separately only edits `config.json`; launch or restart `app.py` to use it. Existing `/api/status` and `/api/history` JSON responses remain unchanged for integrations.

## Setup status: found, selected, saved, and active

The visual wizard distinguishes four stages so it is always clear what happens after clicking:

1. **Find variants** fetches Apple catalog data and displays options only. Variants found are **not** yet part of the watchlist.
2. **Add selected variants to watchlist** adds exact SKUs to a persistent summary with model, colour, capacity and selected areas.
3. **Save private configuration** writes the watchlist to `config.json`. A sticky Save button appears when there are unsaved changes. Saving while an uncommitted catalog preview is open is blocked until the preview is either added or discarded.
4. **Restart the watcher** to apply the new configuration. The wizard never claims that monitoring is running; saved-on-disk is not the same as active surveillance.

The watchlist includes **manual SKUs** as well as model-group subscriptions and displays the selected monitoring regions. A clear banner distinguishes **only previewed**, **unsaved edits**, **locally saved** and **example not saved** states. These are configuration statuses, not live Apple pickup availability.

## Clear product IDs, monitoring area names and local confirmation toasts

The wizard creates descriptive **product IDs** when a model variant is selected, using **model → storage → color → optional verified carrier → country**. Example: `iphone_18_pro_max_512gb_silver_ca`. If two Apple SKUs map to the same descriptive name, a short numeric suffix keeps the 40-character ID unique. Existing product IDs are preserved unless you manually edit them.

**Area IDs identify the geographic search**, not the product. One location may monitor many selected models simultaneously; therefore new areas receive IDs such as `us_19702` or `ca_m5b2h1`, rather than a device-specific identifier. A button **Rename area IDs from locations** updates old `us_1`/`ca_1` entries in the editor on request; names already saved in private `config.json` remain unchanged until you explicitly save. Changing a generated area location updates its draft ID automatically; manually edited IDs remain manual.

A small **green toast at the bottom right** confirms adding/removing selected variants, deleting a watched model, changing areas, and saving. Product/area changes are only **draft edits** until you press Save private configuration; restart the running watcher afterward to apply them. The confirmation always explains that distinction.

## One-click monitoring by Apple model

**Default experience:** in the local setup wizard, first choose your monitoring country/location, then select a model name such as **iPhone 18 Pro** or **iPhone 18 Pro Max** and click **Monitor this model**. The app requests the official regional Apple buy-page catalog, matches the requested model, and adds **every discovered color/storage SKU variant** automatically. It does not ask for a part number or an individual price. The selected model appears as one removable group in the wizard; raw SKUs remain accessible under Advanced.

- The model selection is **region-specific**. If you monitor several countries, add the model once for each desired country because part numbers and currencies may differ.
- **Unknown price is allowed**. When Apple's page does not provide a verifiable numeric price for a particular SKU, the watcher still tracks stock but displays **price not confirmed** instead of inventing a total or tax.
- Monitoring uses SKU batches of at most **12**, to avoid silent result truncation in the regional pickup API. Requests are spread out, with a hard configuration budget of **24 pickup requests per scan**, up to **96 total SKU variants**, a maximum of **48 variants per model** and the existing **eight-area limit**. The wizard shows the approximate per-scan request cost. Reduce models/areas if a budget limit is exceeded.
- **The resolved SKU list is saved at selection time**, not continuously refreshed with new model releases. Re-select a model to refresh its variants (subject to the catalog cache and cooldown). It is not an always-updated product database yet.
- Availability for configured-to-order Mac variants and certain Apple Watch configurations may require additional item components. The software cannot guarantee that all discovered SKUs will be eligible for in-store pickup.
- As before, Apple buy-page parsing is undocumented and must be validated with real responses. If the website changes, the app reports an error instead of making up SKUs.

## Discover Apple SKUs from the official Apple Store

The **local setup wizard** includes a **Find Apple SKUs** feature. Select a country and supported product family, then press the button to read an official Apple purchase page **once on demand**. Browse the extracted model, storage, color and SKU combinations, filter the results, and click **Add** to include a variant in your private configuration.

The initial allowlist covers selected iPhone, iPad, Mac and Apple Watch families for US/Canada; France/UK require the existing explicit experimental-region opt-in. Not every product Apple sells is indexed yet (AirPods, accessories, build-to-order Macs and certain Watch pairings need additional work).

**No invented data:** only SKU identifiers explicitly present in Apple's current buy-page data are offered. A product price is prefilled only if that exact item has a clear numeric price; otherwise the price field remains **blank** and must be filled before saving. Imported products are not automatically verified as eligible for store pickup. Always confirm the product and final price on Apple's site.

**Polite fetch policy:** discovery uses an Apple-domain-only URL allowlist, no user-supplied fetch URLs, a seven-megabyte page cap, a six-hour in-memory cache, and a global minimum two-minute delay between uncached catalog requests. Apple HTTP 429/541 responses trigger a 15-minute catalog request cooldown. This is **not a background scraper**; searching stock remains separate.

The Apple catalog page structure is undocumented. If no recognizable live selection data is present, the wizard reports an error rather than returning a potentially stale third-party catalog. No external app credentials are necessary.

## Customize products and stores

Edit `config.json`. Each item in `products` requires `market` (`US`, `CA`, or explicitly enabled experimental `FR` / `GB`), `name`, Apple's region-specific `part` / SKU, `price` (number), and `currency`. Set `search_zips` for US searches, with `allowed_states` as a whitelist of results. For Canada, set `ca_location` to a postal code. Set `ca_target_store` to an Apple Store ID, or `""` to include all returned Canadian stores. `us_priority_store` highlights a US store and sends individual notifications.

The supplied example contains illustrative SKU / price configuration from October 2026; prices, product availability, SKU identifiers, exchange rates and local tax estimates need independent verification. Only US jurisdictions implemented in `us_tax_rate` return tax estimates; unknown US jurisdictions show unknown totals. **Canadian tax is a manually configurable estimate (`ca_tax_rate`, default 0.13), not a nationwide tax rate.**

Without `config.json`, defaults from the original V4.5 are used. Minimum check interval is 120 seconds, but slower monitoring is recommended.

## Multiple monitoring areas (US and Canada)

Use the **local setup wizard** to add up to **8** monitored regions, each with its own country and location. For US locations, enter a five-digit ZIP; for Canadian locations, use a postal code (recommended) or city. US and Canada are the established markets. France and the UK are available as **experimental previews only** with explicit opt-in; other markets are rejected.

You can optionally enter specific Apple Retail Store IDs for each area. Leaving the area store filter blank monitors **all stores returned by Apple's nearby-pickup response**, not every Apple Store in the city or country. Overlapping regions are deduplicated by product and Apple Store ID.

The new `monitoring_areas` field in `config.json` looks like:

```json
{
  "monitoring_areas": [
    {"id": "new_york", "market": "US", "location": "10001", "store_ids": []},
    {"id": "toronto", "market": "CA", "location": "M5B 2H1", "store_ids": ["R121"]}
  ]
}
```

The watcher still accepts **legacy** `search_zips`, `ca_location`, and `ca_target_store` settings whenever `monitoring_areas` is absent. As soon as `monitoring_areas` is present, its area list takes precedence. The wizard retains legacy fields in private configurations for rollback purposes, but old and new fields need not describe the same selected locations. Keep a backup before switching back to an older watcher version.

**Multiple-area warning:** each configured area generally means one additional regional Apple pickup request per scan, and adding locations can lead to slower updates, missed checks and temporary Apple HTTP 429/541 rate limits. The watcher limits the number of areas to 8, staggers requests, slows the polling interval with 2+ areas, and stops the remaining requests in a cycle if Apple throttles the service. It does **not** guarantee continuous per-store monitoring or complete city coverage. If some areas fail, the overall status is `partial`, even when another store appears available. **Partial/unknown is not out of stock.**

## Experimental France and UK support (not yet live-validated)

The regional routing groundwork is available for the following markets:

| Market | Region | Endpoint | Currency | Location |
| --- | --- | --- | --- | --- |
| `FR` | France | `/fr/shop/retail/pickup-message` | EUR | French five-digit postal code or city |
| `GB` | United Kingdom | `/uk/shop/retail/pickup-message` | GBP | UK postcode or city |

To activate these markets, check **Enable France/UK preview (experimental)** in the local setup wizard. Add a product with a **real, region-specific Apple SKU**, then create at least one monitoring area in that country. The wizard saves `enable_experimental_regions: true` into `config.json`. The actual regional endpoint response, product compatibility and precise store coverage have **not** been confirmed by our own live tests.

**Pricing:** entered EUR and GBP product prices are treated as **user-supplied VAT-inclusive retail estimates**. The app does not calculate an itemized French or British VAT amount or promise a verified checkout total. GBP may be converted into EUR using the existing public FX provider. Never treat a failed or missing response as confirmed stock-out.

The beta flag has no effect unless the user selects FR/GB products and areas. It does not change existing US/Canada setups. This is experimental read-only pickup monitoring, not a purchasing or reservation tool.

## Targeted notifications

In `config.json`, optional fields `alert_store_ids` and `alert_product_ids` control which confirmed stock transitions generate **Discord** notifications. For example:

```json
{
  "alert_store_ids": ["R102", "R121"],
  "alert_product_ids": ["us_pro_512", "ca_pro_512"]
}
```

An omitted field means **all** stores or products; an empty array disables notifications for that dimension. These filters do not hide stores from the dashboard or its stock history. Product IDs must match keys inside `products`; store IDs are returned by Apple. The configured `us_priority_store` has a more prominent notification style.

## Stock history

Confirmed availability changes are retained locally in `history.json`, and recent events appear on the dashboard. The read-only endpoint `/api/history` returns the latest 100 events. Initial availability is treated as an event when the watcher has no prior state. Unknown or missing Apple responses do not create stock-out events.

Set `HISTORY_FILE` in `.env` to change the path and `HISTORY_MAX_EVENTS` to adjust the maximum number of retained entries (default 500; `0` disables history). `history.json` is excluded from Git and Docker builds. It contains product/store names and observation timestamps, so protect it alongside other monitoring data. The file is written on a best-effort basis; a history I/O failure does not interrupt polling.

For Railway or Docker deployments, use a persistent volume for **both** state and history if you want them to survive instance restarts or redeploys. This implementation is intended for a **single polling worker**, not multiple web workers sharing the same state files.

## Coverage correctness and dashboard network safety

**No geographic coverage is inferred:** configuring an Apple SKU for Canada does **not** mean Canada is monitored. You must also add a Canadian monitoring area; the same holds for any supported country. The local setup wizard now warns if a configured product market lacks a region. The dashboard labels that model **unknown (no monitoring area)** rather than **sold out**, and an otherwise successful US scan is marked **partial** when Canadian products were skipped. An empty regional Apple Store response is also treated as a coverage gap rather than confirmed sold-out. These warnings do not automatically add or change your private locations.

**Dashboard binds to localhost by default.** Running `python app.py` exposes the unauthenticated status dashboard only at `http://127.0.0.1:8080` on that computer. To serve it from Docker, a reverse proxy, or a hosted environment such as Railway, explicitly set `WATCHER_HOST=0.0.0.0` **and protect the endpoint with appropriate network access controls**. The included Docker Compose configuration enables binding inside the container but keeps the published port restricted to the host's localhost. Changing host binding does not add user authentication. Do not open a public dashboard containing your monitoring selections without access controls.

The dashboard renders its most recent UTC timestamp in the viewer's local browser timezone when JavaScript is available; the original canonical timestamp remains attached for reference.

## Safe stock transitions and Discord log privacy

When any part of a polling cycle is incomplete (an Apple store batch failed, a country was not checked, or an observed variant has unknown status), the watcher can still report **confirmed newly available stock**, but it will **not send an unavailable transition** or remove a previously available key until a subsequent **fully verified cycle**. This avoids false negative notifications while preserving the ability to detect genuine stock-outs on the next complete scan. The overall dashboard status remains partial during such cycles, and the historical event log does not claim a stock-out until it has been confirmed. Likewise, the model dashboard displays **negative responses from partial cycles as unknown/pending recheck**, while retaining confirmed positive observations; a negative is shown as unavailable only following a complete cycle. Multi-batch requests without a fixed Apple Store filter also compare the returned store sets; if the sets differ across batches, coverage is marked partial instead of assuming every SKU was checked at each store.

Webhook delivery errors are logged by **exception type or HTTP status only**. Full exception messages, which may contain a sensitive Discord webhook URL and secret token, are deliberately not printed. Discord credentials must remain in the private environment and are never needed by the visual setup wizard.

## Additional regression hardening: multi-batch coverage and config privacy

A selection may contain more than one 12-product batch. The watcher now validates **Apple Store coverage for every batch**, not just the combined results for the search area. If a subsequent batch returns no matching store, the overall status is **partial**, and those unverified variants must never be treated as sold out. After an outage, a Discord **recovered** notice is sent only when a later scan has no remaining partial errors or unknown variants; partial progress is not falsely reported as a full recovery. The request budget counts the real number of **configured product IDs sent to Apple**, including repeated SKUs under different IDs, rather than understating the requests by deduplicating part numbers. The setup wizard uses the same estimate.

The local wizard now returns only **validated, known configuration fields** from `/api/config`. Unknown legacy/private fields already present in `config.json` are retained **server-side** when you Save, without being exposed in the browser's configuration response. An existing malformed `config.json` is never silently overwritten by a new save; fix its JSON manually or restore the backup first. As always, credentials belong in private environment variables rather than in `config.json`.

## Local tests: offline preflight and safe live run

Before launching a real monitoring session, use the **read-only offline preflight**. It imports the same runtime configuration as the watcher but starts **no background worker**, does **not contact Apple or Discord**, and **does not write any files**.

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe preflight.py
```

A passing preflight shows the number of configured SKU variants and monitoring areas for each market, the estimated Apple requests per complete scan, any missing country/area combinations, and whether Discord is active. It does **not** print any SKU, postal code, webhook, or other user-defined private values. Use `python preflight.py --json` for a sanitized machine-readable report. If the private `config.json` is missing, the preflight exits nonzero instead of silently approving the built-in example defaults. Offline preflight **cannot** confirm whether an Apple SKU is live or a store has stock.

To run **one controlled live test on Windows CMD** with Discord delivery safely disabled, without modifying your normal local state/history paths, use a separate terminal:

```bat
cd /d "%USERPROFILE%\apple-stock-watcher-release"
set WATCHER_DISABLE_DISCORD=1
set STATE_FILE=%TEMP%\apple-stock-watcher-test-state.json
set HISTORY_FILE=%TEMP%\apple-stock-watcher-test-history.json
.venv\Scripts\python.exe app.py
```

Open `http://127.0.0.1:8080` or `http://127.0.0.1:8080/api/status` in that browser. The **live run does make Apple stock requests** and may call an FX service for prices; stop it with `Ctrl+C` after one check. Because these environment variables are per-terminal, close this CMD window afterward to avoid accidentally reusing test settings. The `WATCHER_DISABLE_DISCORD=1` override disables outbound Discord notifications even when a webhook exists in the local `.env`. It does not disable Apple polling. Do not perform this live test simultaneously with your production watcher using the same credentials/markets if avoidable, and respect Apple's rate limits.

## Operation and limitations

- `/` dashboard; `/api/status` latest state; `/api/history` recent stock changes; `/health` reports Flask process liveness (not proof of Apple connectivity).
- A failed Apple request produces UNKNOWN/partial results, not a confirmed stock-out. Previously available stores are retained when absent from a partial response to avoid repeated false "back in stock" alerts.
- First run may notify on products already available because the state file starts empty.
- Apple HTTP 429/541 responses trigger a longer cooldown (approximately 15 minutes), even when other regions returned usable results.
- The dashboard and API are **not authenticated**. Keep the service private or put it behind your own access control before exposing it to the Internet.
- Treat local tax and currency conversions as estimates; verify price and availability on Apple's official website before travelling or buying.

## One-command local deployment with Docker Compose

Docker Compose keeps the dashboard bound to **127.0.0.1** and stores state/history on a named volume:

```sh
# Copy the sample files first (Windows: use 'copy' instead of 'cp')
cp .env.example .env
cp config.example.json config.json
docker compose up -d --build
```

Visit http://localhost:8080. Stop with `docker compose down`; **do not** use `docker compose down -v` unless you deliberately want to delete the saved data. To follow runtime checks, run `docker compose logs -f watcher`.

For Windows CMD, use `copy .env.example .env` and `copy config.example.json config.json` before running `docker compose up -d --build`. The local dashboard is intentionally not accessible from other computers. There is no built-in authentication, so do not publish the port to the public Internet.

## Tests

Run `python -m unittest discover -s tests -v`. Tests use mock stock data and do not contact Apple or Discord.

## License

MIT. This project is an independent community utility. Apple and iPhone are trademarks of Apple Inc.
