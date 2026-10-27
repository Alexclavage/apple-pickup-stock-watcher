# Roadmap

Apple Pickup Stock Watcher is an independent, self-hosted project. Its long-term goal is to let users monitor **any supported Apple product configuration at any official Apple Retail Store worldwide**, with country-aware catalogs, per-store availability, and opt-in notifications. Monitoring must remain reliable, respectful of Apple's services, and honest about coverage gaps.

This roadmap is directional, not a promise that a feature already exists.

## Product vision — Worldwide Apple Retail coverage (top priority)

**Worldwide** means every country or region where Apple operates a physical Apple Retail Store, not merely a list of capital cities, the nearest stores, or all retailers that resell Apple products. The user should be able to:

- Browse **Country/region → City → Individual Apple Retail Store**, and select any store or all stores in a supported region.
- Choose from discoverable local product catalogs (iPhone, Mac, iPad, Apple Watch, AirPods, accessories), including region-specific SKUs, options, local prices and currencies.
- Monitor **one product at one store**, several product/store combinations, or opt in to a broader global search.
- Receive alerts only for chosen combinations and review freshness/last-successful-check metadata per store.
- See explicit **Supported / Not supported / Temporarily unavailable / Not recently checked** coverage states. A missing response must never be shown as "out of stock".

### International architecture milestones

- [ ] Country/region registry: storefront domain/path, locale, currency, local product SKUs, tax-estimate capability, and supported pickup query behavior
- [ ] Verified index of **every official Apple Retail Store** per supported country, including stable store ID, city and geographic coordinates where available
- [ ] Store discovery/refresh job from publicly accessible official lists or verified regional responses; detect renamed, closed and newly opened stores
- [ ] Location-query coverage planner: identify the minimum reasonable postal-code/location queries needed to reach **each selected store**, since nearby-store endpoints return only a subset
- [ ] Per-country product catalog adapters; validate representative SKU/store responses for each new country before marking it supported
- [ ] One store and multi-store selectors in the visual setup wizard; filters and groups for country/city
- [ ] Rate-limited scheduler shared across selected products/stores, deduped requests, response cache, batching when supported, bounded concurrency, backoff, and observation timestamps
- [ ] Coverage verification tests: no duplicate store IDs, every published store has a tested query location, no incorrect "available" or "unavailable" on failures
- [ ] Regional rollout: US/Canada validation → France/UK and nearby European markets → Asia-Pacific → all verified official retail regions
- [ ] Optional **global monitoring** mode with explicitly slower refresh and transparent resource limits; do not poll every SKU in every store by default

**Limits:** This depends on undocumented regional Apple pickup responses that can change, rate-limit, or be unavailable. Not all products have store-pickup availability. Worldwide support is a goal, not a current feature; the app currently implements only US and Canadian checks. Country or store coverage is only claimed after successful validation.

## P0 — Reliability and privacy

- [x] Configurable product SKU and US/Canada store locations
- [x] Track confirmed transitions without treating unknown responses as stock-outs
- [x] Target Discord alerts to configured store IDs and product IDs
- [x] Use longer cooldowns after Apple HTTP 429/541 limits
- [x] Bounded, locally stored stock-change history and JSON API
- [x] Cross-platform offline regression suite
- [x] Local-only Docker Compose with persistent state
- [ ] Production-ready server and supervised background polling (single scheduler)
- [ ] Controlled retry, rate-limit budgeting and request error telemetry
- [ ] Protected dashboard/API for internet-facing deployments
- [ ] Document persistent storage setup on Railway

## P1 — Easier first-time experience

- [x] Local browser wizard for products, stores, prices and alert preferences (SKUs still provided manually)
- [ ] Optional discovery/validation of regional product SKUs using verifiable public sources
- [ ] Clearer dashboard freshness indicators and per-store last successful check
- [ ] Browser filtering that persists across auto-refresh
- [ ] Optional first-run notification suppression and quiet hours
- [ ] Screenshots or short demo GIF in README and a tagged release

## P2 — Higher-value stock insights

- [ ] Opt-in historical snapshots, not just transitions, to estimate availability trends
- [ ] Export history to CSV or JSON, with retention and privacy controls
- [ ] Optional notification channels beyond Discord
- [ ] Community feedback on real use cases, and maintainers/contributors

## Principles

- Respect Apple's service terms; avoid high-volume requests and do not circumvent rate limits.
- Unavailable and unknown are different states: never announce stock loss from an error.
- Preserve privacy: no committed credentials, no public dashboard by default.
- Features should be independently tested and documented before being checked off.
