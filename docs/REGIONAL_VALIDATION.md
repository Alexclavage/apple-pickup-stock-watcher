# Regional live verification evidence

October 30, 2026. Explicitly authorized, bounded checks using the PR #16 runtime.

Campaign progress: **24/24 additional markets**. Completed.

Latest recorded attempts: **21/24 markets** have a complete bounded
two-SKU check. This is not a count of fully supported countries or all stores.

Initial method: one iPhone 18 Pro family catalog, the first two distinct parsed SKU references,
and one public city/postal search per market. Targeted followups, when present,
are recorded separately below without discarding the initial results. No private config, state/history,
polling worker, FX lookup or Discord calls. Catalog requests are spaced by at
least 120 seconds; an Apple 429/541 stops the remaining campaign without retries.

| Market | Parsed variants | Returned stores | Known / unknown observations | Complete two-SKU check | Directory IDs compared |
| --- | ---: | ---: | --- | --- | --- |
| FR | 32 | 10 | 18 / 2 | No | Not checked in this pass |
| GB | 32 | 12 | 24 / 0 | Yes | Not checked in this pass |
| AU | 32 | 9 | 18 / 0 | Yes | Not checked in this pass |
| AT | 32 | 1 | 2 / 0 | Yes | Not checked in this pass |
| BE | 32 | 1 | 2 / 0 | Yes | Yes; 0 absent from snapshot |
| BR | 32 | 0 | 0 / 0 | No | Not applicable: empty result |
| CN | 32 | 0 | 0 / 0 | No | Not applicable: empty result |
| DE | 32 | 4 | 2 / 6 | No | Yes; 0 absent from snapshot |
| HK | 32 | 6 | 12 / 0 | Yes | Yes; 0 absent from snapshot |
| IN | 32 | 3 | 6 / 0 | Yes | Yes; 0 absent from snapshot |
| IT | 32 | 10 | 20 / 0 | Yes | Yes; 0 absent from snapshot |
| JP | 32 | 6 | 12 / 0 | Yes | Yes; 0 absent from snapshot |
| MY | 32 | 1 | 2 / 0 | Yes | Yes; 0 absent from snapshot |
| MX | 32 | 2 | 4 / 0 | Yes | Yes; 0 absent from snapshot |
| NL | 32 | 0 | 0 / 0 | No | Not applicable: empty result |
| SG | 32 | 3 | 6 / 0 | Yes | Yes; 0 absent from snapshot |
| KR | 32 | 7 | 14 / 0 | Yes | Yes; 0 absent from snapshot |
| ES | 32 | 2 | 4 / 0 | Yes | Yes; 0 absent from snapshot |
| SE | 32 | 1 | 2 / 0 | Yes | Yes; 0 absent from snapshot |
| CH | 32 | 4 | 8 / 0 | Yes | Yes; 0 absent from snapshot |
| TW | 32 | 2 | 4 / 0 | Yes | Yes; 0 absent from snapshot |
| TH | 32 | 2 | 4 / 0 | Yes | Yes; 0 absent from snapshot |
| TR | 32 | 3 | 6 / 0 | Yes | Yes; 0 absent from snapshot |
| AE | 32 | 5 | 10 / 0 | Yes | Yes; 0 absent from snapshot |

## Targeted diagnostic followups

| Market | Purpose | Returned stores | Known / unknown observations | Complete two-SKU check |
| --- | --- | ---: | --- | --- |
| FR | Diagnose unknown statuses using same public postal search | 10 | 18 / 2 | No |
| DE | Diagnose unknown statuses using same public postal search | 4 | 2 / 6 | No |
| BR | Public VillageMall postal code without separator | 0 | 0 / 0 | No |
| CN | Full postal code from official Hong Kong Plaza structured address | 12 | 24 / 0 | Yes |
| NL | Full postal code from official Apple Amsterdam address | 3 | 6 / 0 | Yes |

The wizard shows the latest valid recorded attempt for a market. Original
partial/empty results remain visible above and in the machine-readable history.

- FR: unrecognized pickup display values: `ineligible`; missing requested SKU entries: 0.
- DE: unrecognized pickup display values: `ineligible`; missing requested SKU entries: 0.
- BR: HTTP 200 response without a `body.stores` list. This is unconfirmed coverage, not evidence that all stores are sold out.

An `ineligible` display remains unknown in the runtime. A pickup eligibility
restriction is not enough to infer physical stock or trigger a stock-loss alert.


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
- BE: [catalog](https://www.apple.com/be-fr/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/be-fr/shop/retail/pickup-message).
- BR: [catalog](https://www.apple.com/br/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/br/shop/retail/pickup-message).
- CN: [catalog](https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com.cn/shop/retail/pickup-message).
- DE: [catalog](https://www.apple.com/de/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/de/shop/retail/pickup-message).
- HK: [catalog](https://www.apple.com/hk/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/hk/shop/retail/pickup-message).
- IN: [catalog](https://www.apple.com/in/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/in/shop/retail/pickup-message).
- IT: [catalog](https://www.apple.com/it/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/it/shop/retail/pickup-message).
- JP: [catalog](https://www.apple.com/jp/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/jp/shop/retail/pickup-message).
- MY: [catalog](https://www.apple.com/my/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/my/shop/retail/pickup-message).
- MX: [catalog](https://www.apple.com/mx/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/mx/shop/retail/pickup-message).
- NL: [catalog](https://www.apple.com/nl/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/nl/shop/retail/pickup-message).
- SG: [catalog](https://www.apple.com/sg/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/sg/shop/retail/pickup-message).
- KR: [catalog](https://www.apple.com/kr/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/kr/shop/retail/pickup-message).
- ES: [catalog](https://www.apple.com/es/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/es/shop/retail/pickup-message).
- SE: [catalog](https://www.apple.com/se/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/se/shop/retail/pickup-message).
- CH: [catalog](https://www.apple.com/ch-fr/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/ch-fr/shop/retail/pickup-message).
- TW: [catalog](https://www.apple.com/tw/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/tw/shop/retail/pickup-message).
- TH: [catalog](https://www.apple.com/th/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/th/shop/retail/pickup-message).
- TR: [catalog](https://www.apple.com/tr/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/tr/shop/retail/pickup-message).
- AE: [catalog](https://www.apple.com/ae/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/ae/shop/retail/pickup-message).
- FR: [catalog](https://www.apple.com/fr/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/fr/shop/retail/pickup-message).
- DE: [catalog](https://www.apple.com/de/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/de/shop/retail/pickup-message).
- BR: [catalog](https://www.apple.com/br/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/br/shop/retail/pickup-message).
  Public location reference: [official Apple store address](https://www.apple.com/br/retail/villagemall/).
- CN: [catalog](https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com.cn/shop/retail/pickup-message).
  Public location reference: [official Apple store address](https://www.apple.com.cn/retail/hongkongplaza/).
- NL: [catalog](https://www.apple.com/nl/shop/buy-iphone/iphone-18-pro), [pickup endpoint](https://www.apple.com/nl/shop/retail/pickup-message).
  Public location reference: [official Apple store address](https://www.apple.com/nl/retail/amsterdam/).
