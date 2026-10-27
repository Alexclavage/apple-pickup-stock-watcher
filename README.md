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

## Customize products and stores

Edit `config.json`. Each item in `products` requires `market` (`US` or `CA`), `name`, Apple's region-specific `part` / SKU, `price` (number), and `currency`. Set `search_zips` for US searches, with `allowed_states` as a whitelist of results. For Canada, set `ca_location` to a postal code. Set `ca_target_store` to an Apple Store ID, or `""` to include all returned Canadian stores. `us_priority_store` highlights a US store and sends individual notifications.

The supplied example contains illustrative SKU / price configuration from October 2026; prices, product availability, SKU identifiers, exchange rates and local tax estimates need independent verification. Only US jurisdictions implemented in `us_tax_rate` return tax estimates; unknown US jurisdictions show unknown totals. **Canadian tax is a manually configurable estimate (`ca_tax_rate`, default 0.13), not a nationwide tax rate.**

Without `config.json`, defaults from the original V4.5 are used. Minimum check interval is 120 seconds, but slower monitoring is recommended.

## Operation and limitations

- `/` dashboard; `/api/status` latest state; `/health` reports Flask process liveness (not proof of Apple connectivity).
- A failed Apple request produces UNKNOWN/partial results, not a confirmed stock-out. Previously available stores are retained when absent from a partial response to avoid repeated false "back in stock" alerts.
- First run may notify on products already available because the state file starts empty.
- The dashboard and API are **not authenticated**. Keep the service private or put it behind your own access control before exposing it to the Internet.
- Treat local tax and currency conversions as estimates; verify price and availability on Apple's official website before travelling or buying.

## Tests

Run `python -m unittest discover -s tests -v`. Tests use mock stock data and do not contact Apple or Discord.

## License

MIT. This project is an independent community utility. Apple and iPhone are trademarks of Apple Inc.
