# Architecture — Apple Stock Watcher V1 RC

This document describes the **actual current Python modules**, not a proposed rewrite.

## Process boundaries

| Module | Role | External network |
| --- | --- | --- |
| `app.py` | Loads private config; runs a **single** polling loop; provides the dashboard, JSON status/history and optional Discord notifications | Apple pickup, optional FX, optional Discord |
| `setup_wizard.py` | Independent localhost-only browser configuration editor; maintains validated config and backups | Apple **buy pages** only when the user explicitly requests catalog discovery |
| `catalog_discovery.py` | On-demand, allowlisted Apple page parser with cache and cooldown | Apple buy pages, not stock endpoint |
| `model_watch.py` | Selects verified model SKUs, enforces variant and pickup request budgets | None |
| `monitoring_areas.py` / `regions.py` | Area/market validation, postcode rules and regional pickup endpoints | None |
| `dashboard_groups.py` | Read-only view aggregation by market/model/Apple Store | None |
| `history.py` | Bounded best-effort local history of confirmed transitions | None |
| `preflight.py` | **Offline** read-only readiness report (imports app config but does not run polling) | None |

Both servers are Flask development servers for local use; **neither has built-in authentication**. The dashboard defaults to 127.0.0.1:8080 and the wizard to 127.0.0.1:8091. Explicit `WATCHER_HOST=0.0.0.0` enables dashboard network binding, but only behind external access control. Do not publish wizard port 8091.

## Data flow

```text
config.example.json --copy/edit--> config.json (private)
                                      |
                 +--------------------+---------------------+
                 |                                          |
      setup_wizard.py (8091)                       app.py (8080)
      select model + variants                      load/validate config
      save backed-up config                        |
                 |                                 | poll by market + area
         catalog_discovery.py                      | SKU batches <= 12
         official Apple buy pages                  v
                                                Apple pickup
                                                  |
                             +--------------------+------------------+
                             |                    |                  |
                       status snapshot        transitions          grouped view
                       /api/status            state/history        dashboard /
                                             optional Discord      /api/history
```

**Config vs runtime:** `Save` in the wizard does not restart the worker. Restart `app.py` to apply. The configuration can include products without matching monitoring areas; the preflight and live status flag these as unverified, not unavailable.

## Availability classification

1. The poller submits product identifiers to Apple **in batches of 12** per monitoring area, with a maximum configured request budget and conservative cooldowns.
2. For every batch, store coverage is checked. Missing/changed store sets, missing selected store IDs, unsupported markets, Apple errors and missing product statuses result in **partial/unknown** rather than a confirmed stock-out.
3. Product/store observations are deduplicated when areas overlap; conflicting results for the same key become unknown.
4. `AVAILABLE` is a concrete observed positive. `UNAVAILABLE` means negative **only after a fully verified check**. A negative in a partial scan is provisional and appears unknown in model cards.
5. The persisted available set survives incomplete scans so that a missing batch cannot cause a false stock-out alert. Stock-out transitions are deferred until a complete cycle.
6. New confirmed positive observations may still trigger alerts during a partial cycle. A Discord “restored” message requires a fully verified cycle.

**Caveat:** passing a complete check only verifies the specific responses returned for configured areas and SKU/store combinations. It cannot prove citywide or nationwide absence of stock, and the Apple endpoint is undocumented.

## Persistence and error policy

- `config.json` is private user intent, backed up by the wizard on Save; existing unrecognized keys stay on disk and are not exposed in wizard JSON responses.
- `STATE_FILE` stores the most recent available keys and watcher error state, used across restarts. File replacement is best effort and assumes a single worker.
- `HISTORY_FILE` stores bounded confirmed events; corrupted or unavailable history returns an empty list and does not crash polling.
- `latest` is an in-memory status snapshot; no current verified observation is asserted after a failed cycle.
- Discord sending is best effort, **not exactly-once delivery**. Turn it off for testing with `WATCHER_DISABLE_DISCORD=1`. Webhook secrets must not appear in console error logs.

## Safety and release boundaries

- `preflight.py` does not make network calls, start polling, or write state. It validates configuration coverage and budget only.
- All CI unit tests mock Apple/FX/Discord and are not proof of real inventory for every region.
- FR/GB region adapters, on-demand Apple product catalog parsing, carrier metadata and made-to-order products need independent live validation.
- Docker Compose publishes the dashboard to host loopback by default. Hosted services must explicitly opt into binding, supply secrets via environment, and arrange authentication/network restrictions.
- Never connect more than one worker to the same state/history files. Never upload real `config.json` or `.env` to GitHub.
