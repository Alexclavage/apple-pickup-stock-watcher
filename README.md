# Apple Stock Watcher

An independent, unofficial, self-hosted Apple Store pickup availability checker. Includes a Flask dashboard, Discord alerts on stock changes, selectable product SKUs, optional EUR conversions, and tax estimates. **It does not purchase or reserve products.** Not affiliated with Apple.

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

The watcher includes a **separate browser-based setup wizard**, so you can manage products, Apple SKUs, US ZIP search areas, Canadian store, estimated tax and Discord alert filters without manually editing JSON.

On Windows CMD, after installing dependencies with the Quick start commands:

```bat
.venv\Scripts\python.exe setup_wizard.py
```

On macOS/Linux run `python setup_wizard.py` inside the activated environment. Open **http://127.0.0.1:8091**, edit the fields and click **Save private configuration**. The wizard reads `config.json` or starts with `config.example.json`. If it overwrites an existing config, it keeps one private backup in `config.json.bak`; both are excluded from Git and Docker. Restart the watcher after saving.

**Security:** the wizard is not part of the public dashboard. It binds to `127.0.0.1` only, checks origin and request tokens for saves, and never displays or saves your Discord webhook. Do not forward this port to the public Internet. An Apple SKU still needs to be obtained and verified manually; this UI does not scrape a SKU catalogue or validate actual inventory.

## Customize products and stores

Edit `config.json`. Each item in `products` requires `market` (`US` or `CA`), `name`, Apple's region-specific `part` / SKU, `price` (number), and `currency`. Set `search_zips` for US searches, with `allowed_states` as a whitelist of results. For Canada, set `ca_location` to a postal code. Set `ca_target_store` to an Apple Store ID, or `""` to include all returned Canadian stores. `us_priority_store` highlights a US store and sends individual notifications.

The supplied example contains illustrative SKU / price configuration from October 2026; prices, product availability, SKU identifiers, exchange rates and local tax estimates need independent verification. Only US jurisdictions implemented in `us_tax_rate` return tax estimates; unknown US jurisdictions show unknown totals. **Canadian tax is a manually configurable estimate (`ca_tax_rate`, default 0.13), not a nationwide tax rate.**

Without `config.json`, defaults from the original V4.5 are used. Minimum check interval is 120 seconds, but slower monitoring is recommended.

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
