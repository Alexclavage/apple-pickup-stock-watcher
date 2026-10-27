# Roadmap

Apple Pickup Stock Watcher is a small, independent, self-hosted project. The goal is **reliable, configurable monitoring**, not aggressive scraping.

This roadmap is directional, not a promise that a feature already exists.

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
- [ ] More countries/stores, only when verified against regional Apple responses
- [ ] Community feedback on real use cases, and maintainers/contributors

## Principles

- Respect Apple's service terms; avoid high-volume requests and do not circumvent rate limits.
- Unavailable and unknown are different states: never announce stock loss from an error.
- Preserve privacy: no committed credentials, no public dashboard by default.
- Features should be independently tested and documented before being checked off.
