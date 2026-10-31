# v1.1 worldwide — final review candidate

October 31, 2026. Prepared in PR #16; not a published release. Runtime version
remains `1.1.0-dev` until the release decision. Published v1.0.0 is unchanged.

## Corrected behavior

- Store-first setup: country/currency and adapter limitations are shown before
  discovering regional variants. A store in preparation does not add an invalid
  area. Complete the local search and regional product selection, then add it.
- Existing areas offer a country-specific product action. Missing associations,
  empty locations, duplicate regional variants and exceeded budgets are visible
  before saving. Manual products have Edit/Remove actions. Regional product
  selections are shared by areas in the same country and are not copied abroad.
- Stores sharing one country/search reuse an area. Existing all-store searches
  show an explicit notice before being narrowed to a selected store. Country
  changes clear the old store IDs; product-country changes require a regional
  replacement. Editing a manual SKU clears its previous discovered attributes.
- Late catalog/model responses cannot populate another country's preview. No SKU,
  price, tax, carrier attribute or pickup compatibility is invented.
- Invalid Apple schemas are unknown errors. Known foreign store IDs cannot be
  used as a country's stock. Missing target stores/variants stay unknown.
- Expired observations become unknown on the dashboard/API; a failed attempt
  does not refresh the previous observation date. Old rows are not returned as
  current stock. The threshold follows the configured polling interval.
- Discord summaries identify country, store ID and regional SKU, with duplicate
  messages suppressed for duplicate legacy product IDs. State keys and the
  conservative global partial-scan stock-loss protection are retained.

## Confirmed scope and limits

The directory contains 535 entries in 27 countries/territories. Of the 26 markets
with adapters, US/CA retain their V1 evidence. The 24 others require experimental
opt-in: 21 have the recorded bounded two-SKU check; FR/DE remain partial, Brazil
unconfirmed. Macao is directory-only. These are not all-store/all-product claims.
See the [original live results and followups](REGIONAL_VALIDATION.md).

V1 US/Canada configuration fields remain supported. Legacy duplicate product IDs
remain readable/runnable; the editor asks to resolve duplicate regional entries
before saving. Adding/removing stores does not delete products silently. Nothing
starts polling or sends Discord messages from the configurator.

## Validation

146 offline Python tests pass locally, including a full-form DOM interaction
test with fake regional data, edit/removal paths, late responses and request
budgets. The earlier small directory mock was replaced by this full DOM test.
Eleven new backend regressions cover schema/country/eligibility/freshness/alerts.
CI runs Python 3.12/3.14 on Windows/Ubuntu and installs the test-only DOM packages
from the lockfile. Runtime dependencies are unchanged.

No extra Apple, Discord or FX checks were needed for these reproduced failures.
The completed live campaign was not repeated. No private configuration, webhook,
logs, state, raw response captures or generated HTML are included in the PR.

## One optional visual smoke check

The browser's saved/managed localhost rule blocked visual access during the
previous session. It was not bypassed. DOM interactions are automated; actual
browser layout/focus rendering remains unconfirmed.

On a disposable copy of your configuration in the local wizard:

1. Keep US/CA products, select France and a store, enable experimental markets,
   then **Configure selected store**. Check that no French area is added yet.
2. Enter the store's complete local postal code; **Choose regional products**.
   Find one model, choose a small variant selection and add it to the watchlist.
   Discovery is an optional real Apple request; stop if throttled.
3. **Add completed store selection**. Confirm the French area shows its store,
   EUR and regional product count. Remove the French model: a clear correction
   action should appear. Choose regional products again or remove the area.

Save/restart only when you intend to apply the chosen settings. No repeated
US/CA scan, Discord test or global campaign is required for this visual check.

## Publication boundary

This PR is prepared for final review. Merging main, choosing a final version/tag,
publishing a Release and deploying Railway require the owner's explicit decision.
