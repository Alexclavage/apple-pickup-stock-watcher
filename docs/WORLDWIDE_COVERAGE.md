# Worldwide Apple Store selection

Next-version branch; not part of the published `v1.0.0` tag.

## Directory evidence

The snapshot in `data/apple_stores.json` records **535 store links across 27
countries/territories** from the country selector and rendered store entries on
[Apple's official directory](https://www.apple.com/retail/storelist/), observed
October 30, 2026. It contains public store ID, name, city and official retail URL.
The IDs came from Apple's `data-store-number` attributes, never inferred from names.
No availability, private configuration, postal search or user data was collected.

Snapshot presence does not establish that a store is open today, that every store
is listed, that pickup is enabled, or that a particular product can be collected.
Changes to the directory require a reviewed snapshot refresh, not background scraping.

## What the implementation does

- Browse/search all snapshot countries, cities, names and IDs offline in the
  wizard. Opening an official store link is a separate user action.
- Prepare a store with its local postal search and regional products. Adding it
  creates a complete draft area (or joins the same country/search), not an empty
  area that later fails with "no configured FR products". Save/restart remains explicit.
- Show regional currency, adapter limits, associated product count and configuration
  issues separately from live pickup coverage. Existing areas have a regional
  product action; removals expose missing associations immediately.
- Source country options and currencies from one region registry, including China
  on `www.apple.com.cn`; no arbitrary request URL input.
- Require `enable_experimental_regions: true` for **every market except US/CA**.
  This flag now covers all additional markets, including existing FR/GB settings.
- Require explicit monitoring areas for products outside US/CA. Legacy US/Canada
  configurations retain their previous mapping. Existing area/request budgets stay.
- Treat unrecognized, missing, failed or rate-limited stock responses as unknown
  or partial; no store-index entry is interpreted as stock.
- Keep new-market tax/total/FX estimates unknown instead of applying US/Canada tax
  rules or assuming VAT inclusion. Existing FR/GB behavior is retained.
- Use currency-specific numeric input caps for JPY/KRW/INR/TWD/THB/TRY so ordinary
  high-denomination prices are not rejected by the inherited dollar-sized cap.

The TRY cap was added after observing Apple's Turkish iPhone 18 Pro page with
prices over 100,000 TRY. This changes input validation, not estimated prices:
[official Turkish storefront](https://www.apple.com/tr/shop/buy-iphone/iphone-18-pro).

## Evidence levels

**US/CA:** prior user-reported live results validate selected combinations only.
There is no new assertion that every listed US/CA store has been checked.

**24 other selectable markets:** experimental route candidates. The regional
pickup/catalog paths follow regional storefront conventions. The
[live verification record](REGIONAL_VALIDATION.md) distinguishes the bounded
checks already performed from unverified combinations; it is not endpoint documentation. HTTP redirects,
localization, Apple regional pickup restrictions or parser differences may prevent
them working. Offline tests prove routing/currency/gating and fail-closed behavior;
live results only cover the recorded inputs. No promotion to supported status is implied.

**Macao:** both stores can be browsed and opened on Apple; adding a monitoring
area is disabled. No Macao stock route or substitution via Hong Kong is invented.

## Validation before promoting a market

For each additional market: verify the actual regional storefront and pickup URL,
obtain real regional SKUs, make a small authorized check with known local search
inputs and explicit store IDs, and record observed SKU/store coverage. Confirm
missing-store/variant behavior, catalog localization and cooldown handling.
Do not replay completed US/CA or Discord validation as a new gate.

The parser and request engine are shared, but live evidence is market-specific.
No mass worldwide probing, account/cookie collection, proxy rotation or rate-limit
circumvention is introduced. A blocked regional endpoint stays experimental/unknown.

## Operational scope

This enables worldwide **choice**, not a simultaneous scan of all 535 stores.
At most eight areas, 96 products and 24 pickup requests per scan remain allowed.
One search location may omit even a selected store: the watcher then reports a
coverage issue rather than sold out. Directory selection does not auto-group
remote stores under one search location or increase the request budget.
The advanced US state filter still applies: clear it for nationwide US choice.

No merge, new tag/release or Railway deployment is included in this work.

## October 31 stabilization

The recorded October 30 observations remain historical evidence: **21/24** extra
markets have a complete two-SKU check in the selected area, **FR/DE** remain
partial with `ineligible` values, **BR** remains unconfirmed, and **MO** is
directory-only. No new nationwide campaign or market promotion was performed.

Malformed/missing store lists now fail explicitly as unknown. Known store IDs
from another country are rejected in configuration and skipped in responses.
Unknown/new IDs are not falsely assigned a country by the snapshot. A changed
product country cannot silently reuse a regional SKU. Late catalog responses
are discarded after a country/model/family change.

The dashboard expires observations after `max(300, 2 * INTERVAL + 60)` seconds,
distinguishes last attempt from last received observations, and shows selected
stores omitted by Apple as unknown. Discord summaries include country, store ID
and regional SKU; duplicate legacy product IDs for one SKU do not duplicate an
alert. Existing global partial-scan protection against false stock loss remains.

### Future scale, beyond v1.1

v1.1 groups only stores sharing the same country and local search; every area
uses that country's SKU batches. It retains eight areas and 24 requests per cycle.
A simultaneous global service would need a central scheduler, regional queues,
shared result storage, per-pair observation times and a global request/cooldown
budget. Sharding must not multiply the Apple request budget or circumvent limits.
That is future work, not part of this release candidate.
