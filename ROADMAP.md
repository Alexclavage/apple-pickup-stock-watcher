# Roadmap

Apple Pickup Stock Watcher is an independent, self-hosted project. Its long-term goal is to let users monitor **any supported Apple product configuration at any official Apple Retail Store worldwide**, with country-aware catalogs, per-store availability, and opt-in notifications. Monitoring must remain reliable, respectful of Apple's services, and honest about coverage gaps.

This roadmap is directional, not a promise that a feature already exists.

## Product vision — Worldwide monitoring by selected area

**Simplest onboarding:** the user chooses a **country/region + postal code or city**, adds one or more monitoring areas, selects products and optionally narrows monitoring to individual official Apple Retail Stores returned for each area. This scales conceptually to countries around the world **after their regional pickup APIs and product catalogs have been verified**.

- One monitoring area is the default. Multiple areas may span different countries; each has its own market, currency, query location and discovered stores.
- The user can choose **all Apple Retail Stores returned for an area**, or specific stores, and set notifications per product/store.
- Areas can overlap. Deduplicate stores and overlapping product/store pairs; never treat a missed or stale check as "out of stock".
- Support search coverage and show **last successfully checked at**, last error, and an explicit **not checked / unknown** status for each monitored area and store.
- The number of areas is configurable but bounded by a conservative request budget. Queue and stagger checks rather than poll all areas at once.
- The interface must display a clear warning before enabling multiple areas: more locations increase requests and may cause Apple's rate limits, slower refresh, missed checks, or temporary suspension of monitoring.
- Estimate request cost before saving (areas × regional product batches, after deduplication), and communicate a realistic *approximate* refresh cadence. Never promise fixed intervals or uninterrupted coverage.
- The goal is broad worldwide choice **without maintaining or querying every store on Earth by default**. A postal code or city only covers whatever nearby stores that regional endpoint returns; it is not guaranteed to include every store in the city or country.

### Implementation milestones

- [x] Define region/currency/location adapters for established US/CA and opt-in experimental FR/GB (live validation still required)
- [x] Introduce a reusable **list of market + postal/city monitoring areas** for US and Canada (other countries planned)
- [x] Read legacy `search_zips` / `ca_location` and migrate automatically when no `monitoring_areas` list exists
- [x] Let the local setup wizard add, edit and remove up to 8 areas across supported US/CA markets
- [ ] Discover nearby Apple Retail Stores for each area and let the user select individual stores or all returned stores
- [x] Deduplicate overlapping store/product combinations and avoid reporting conflicting observations as confirmed stock-out
- [ ] Add market-specific SKU batching when verified and needed
- [ ] Add a scheduler with per-market rate budgets, pacing, retry backoff, cache and status/freshness metadata
- [x] Display an explicit multiple-area warning and conservative 8-area cap
- [x] Stop remaining area requests when Apple rate-limits a scan
- [ ] Independently validate France and UK pickup queries using real local SKUs and store locations; then promote them from experimental to supported
- [ ] Expand to other European and Asia-Pacific markets only after verification
- [ ] Add optional coverage reports and store index **only if** useful for finding gaps; a global authoritative store registry is not required for the basic UX

**Limits:** Apple's pickup endpoints are undocumented and may change or throttle traffic. Product SKUs and supported search formats vary by market, and not all goods can be collected in store. Worldwide coverage is a roadmap goal, **not a current feature**. US/CA are established; FR/GB are opt-in experimental until validated live.

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

## Variant choice: colour / storage / carrier

- [x] Preview actual regional Apple SKU variants before adding a model
- [x] Optional colour and capacity filters populated from Apple product dimensions
- [x] Conditional carrier or carrier-free filter only for variants with explicit Apple metadata; never infer "unlocked" from an absent field
- [x] Handle carrier-ambiguous duplicate SKU records as unknown
- [x] Permit filtering a model with more than 48 discovered SKUs down to a safe selection
- [ ] Validate carrier selection behavior against real Apple checkout pages; carrier account activation may be separate from stock SKUs
- [ ] Provide multiple value selection per dimension (several colours/capacities in one group) when needed

## Human-friendly identifiers and selection feedback

- [x] Generate descriptive product IDs from model, capacity, colour, verified carrier when available and country; preserve existing IDs
- [x] Generate geographic area IDs from market and ZIP/postal code/city for newly added areas
- [x] Offer an opt-in one-click rename for existing area IDs without silently altering private configuration
- [x] Add accessible green bottom-right confirmations for adding/removing selections, changing areas and saving
- [ ] Allow a custom friendly display title independent of stable internal IDs in the dashboard

## Model-first configuration

- [x] Select an Apple model name in the local wizard and resolve all *currently discoverable* country-specific SKU variants in one operation
- [x] Keep model subscriptions grouped with one remove action, while leaving manual SKU editing available
- [x] Monitor variants even when their current price is not independently known
- [x] Split large product selections into twelve-SKU pickup request batches and enforce a conservative request budget
- [ ] Independently verify actual live buy-page parsing for every supported family
- [ ] Persist/refresh model subscriptions automatically and safely when Apple adds or removes variants
- [ ] Group the main monitoring dashboard by model rather than one section per SKU
- [ ] Check configured-to-order Mac and Watch bundle pickup behavior before declaring full family coverage

## P1 — Easier first-time experience

- [x] Local browser wizard for products, stores, prices and alert preferences (SKUs still provided manually)
- [x] Add optional manual-request live SKU discovery from allowlisted official Apple buy pages, with cache, per-country SKU routing and error transparency
- [ ] Extend automatic SKU discovery to all product families and accessories and independently verify live pages
- [ ] Validate stock pickup eligibility for catalog-discovered SKUs, including Watch case/band bundles and configured Macs
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
