# Regional live verification evidence

October 30, 2026. Explicitly authorized, bounded checks using the PR #16 runtime.

Campaign progress: **4/24 additional markets**. In progress; unlisted markets have no new result.

Method: one iPhone 18 Pro family catalog, the first two distinct parsed SKU references,
and one public city/postal search per market. No private config, state/history,
polling worker, FX lookup or Discord calls. Catalog requests are spaced by at
least 120 seconds; an Apple 429/541 stops the remaining campaign without retries.

| Market | Parsed variants | Returned stores | Known / unknown observations | Complete two-SKU check | Directory IDs compared |
| --- | ---: | ---: | --- | --- | --- |
| FR | 32 | 10 | 18 / 2 | No | Not checked in this pass |
| GB | 32 | 12 | 24 / 0 | Yes | Not checked in this pass |
| AU | 32 | 9 | 18 / 0 | Yes | Not checked in this pass |
| AT | 32 | 1 | 2 / 0 | Yes | Not checked in this pass |

## Limits

- These are responses for selected variants and one area, not a full-country
  inventory or proof of current availability for every listed store/product.
- A complete check means both SKU statuses were present for every returned
  store in that response; it does not establish coverage of omitted stores.
- The first four checks did not compare store IDs to the directory snapshot.
  Later checks do; missing IDs can also indicate a stale snapshot.
- All additional markets remain experimental. Recorded evidence does not
  disable opt-in or promote all product families to supported.
- Prices absent from the catalog remain unknown; no invented numeric prices.
- Browser access to the isolated local wizard was blocked by a saved permission
  or managed policy. Visual end-to-end testing remains unconfirmed.

## Sources and diagnostic results

The [machine-readable aggregate](../data/regional_validation.json) includes
the exact regional catalog and pickup URL for each performed check. No private
search input or SKU selections are published.

- FR: [catalog](https://www.apple.com/fr/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/fr/shop/retail/pickup-message).
- GB: [catalog](https://www.apple.com/uk/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/uk/shop/retail/pickup-message).
- AU: [catalog](https://www.apple.com/au/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/au/shop/retail/pickup-message).
- AT: [catalog](https://www.apple.com/at/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/at/shop/retail/pickup-message).
