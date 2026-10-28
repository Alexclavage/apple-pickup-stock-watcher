"""Local-only configuration wizard for Apple Stock Watcher.

Launch with: python setup_wizard.py
The wizard binds to loopback, is not part of the public monitoring server,
and never reads or writes Discord webhook credentials.
"""
import argparse
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import tempfile

from flask import Flask, abort, jsonify, render_template_string, request
from monitoring_areas import MAX_MONITORING_AREAS, legacy_areas, validate_monitoring_areas
from regions import region_for
from catalog_discovery import CatalogError, FAMILIES, fetch_catalog
from model_watch import MODELS, MAX_PRODUCTS, family_for, model_catalog_result, ModelSelectionError, validate_request_budget, MAX_SKUS_PER_MODEL


ROOT = Path(__file__).resolve().parent
PRODUCT_ID = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,39}$")
SKU = re.compile(r"^[a-zA-Z0-9/_-]{3,32}$")
STORE_ID = re.compile(r"^[a-zA-Z0-9_-]{2,20}$")
AREA_NAME = re.compile(r"^[a-zA-Z0-9 _-]{1,32}$")
US_ZIP = re.compile(r"^[0-9]{5}$")
STATE = re.compile(r"^[A-Z]{2}$")


class InvalidConfig(ValueError):
    pass


def _string(value, name, limit=120, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise InvalidConfig(f"{name} must be a {'possibly empty ' if empty else ''}string (max {limit} characters)")
    return value.strip()


def _string_list(value, name, regex=None, max_items=100):
    if not isinstance(value, list) or len(value) > max_items:
        raise InvalidConfig(f"{name} must be an array with at most {max_items} elements")
    values = []
    for entry in value:
        entry = _string(entry, name, limit=40)
        if regex and not regex.fullmatch(entry):
            raise InvalidConfig(f"{name} contains an invalid value: {entry[:24]}")
        if entry in values:
            raise InvalidConfig(f"{name} contains duplicates")
        values.append(entry)
    return values


def validate_config(cfg):
    """Validate wizard-owned fields before overwriting any local file."""
    if not isinstance(cfg, dict):
        raise InvalidConfig("Configuration must be an object")

    enable_experimental = cfg.get("enable_experimental_regions", False)
    if not isinstance(enable_experimental, bool):
        raise InvalidConfig("enable_experimental_regions must be true or false")
    products = cfg.get("products")
    if not isinstance(products, dict) or not 1 <= len(products) <= MAX_PRODUCTS:
        raise InvalidConfig(f"Add between 1 and {MAX_PRODUCTS} product variants")
    result = {}
    for product_id, item in products.items():
        if not isinstance(product_id, str) or not PRODUCT_ID.fullmatch(product_id):
            raise InvalidConfig("Product IDs must start with a letter and contain letters, digits, underscores or hyphens")
        if not isinstance(item, dict):
            raise InvalidConfig(f"Product {product_id} must be an object")
        market = item.get("market")
        try:
            region = region_for(market, enable_experimental)
        except ValueError as exc:
            raise InvalidConfig(f"Invalid country for {product_id}: {exc}") from exc
        currency = item.get("currency")
        if currency != region.currency:
            raise InvalidConfig(f"Invalid currency for {product_id}")
        sku = _string(item.get("part"), f"SKU for {product_id}", 32)
        if not SKU.fullmatch(sku):
            raise InvalidConfig(f"Invalid SKU for {product_id}")
        price = item.get("price")
        if price is not None and (isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or not 0 <= price <= 100000):
            raise InvalidConfig(f"Price for {product_id} must be a valid nonnegative number")
        watch_model = item.get("watch_model")
        if watch_model is not None and watch_model not in MODELS:
            raise InvalidConfig(f"Unknown monitored model for {product_id}")
        result[product_id] = {
            "market": market,
            "name": _string(item.get("name"), f"Name for {product_id}", 100),
            "part": sku,
            "price": price,
            "currency": currency,
        }
        if watch_model is not None:
            result[product_id]["watch_model"] = watch_model
        for attribute in ("color", "storage", "carrier"):
            value = item.get(attribute)
            if value is not None:
                result[product_id][attribute] = _string(value, attribute, limit=64)

    zips = cfg.get("search_zips", {})
    if not isinstance(zips, dict) or len(zips) > 20:
        raise InvalidConfig("US search regions must be an object with at most 20 entries")
    valid_zips = {}
    for name, postal in zips.items():
        if not isinstance(name, str) or not AREA_NAME.fullmatch(name):
            raise InvalidConfig("US region names can contain only letters, digits, spaces, hyphens and underscores")
        if not isinstance(postal, str) or not US_ZIP.fullmatch(postal):
            raise InvalidConfig(f"US ZIP for {name} must contain exactly 5 digits")
        valid_zips[name] = postal
    if "monitoring_areas" not in cfg and any(item["market"] == "US" for item in result.values()) and not valid_zips:
        raise InvalidConfig("Add a US ZIP search region for US products")

    states = _string_list(cfg.get("allowed_states", []), "Allowed US states", STATE, 51)
    us_store = _string(cfg.get("us_priority_store", ""), "Priority US store", 20, empty=True)
    ca_store = _string(cfg.get("ca_target_store", ""), "Target Canadian store", 20, empty=True)
    for title, value in (("Priority US store", us_store), ("Target Canadian store", ca_store)):
        if value and not STORE_ID.fullmatch(value):
            raise InvalidConfig(f"{title} has invalid characters")

    ca_postal = _string(cfg.get("ca_location", ""), "Canadian location", 24, empty=True)
    if "monitoring_areas" not in cfg and any(item["market"] == "CA" for item in result.values()) and not ca_postal:
        raise InvalidConfig("Enter a Canadian location when monitoring Canadian products")
    tax = cfg.get("ca_tax_rate", 0.13)
    if isinstance(tax, bool) or not isinstance(tax, (int, float)) or not math.isfinite(tax) or not 0 <= tax <= 1:
        raise InvalidConfig("Canadian tax estimate must be between 0 and 1")

    output = {
        "enable_experimental_regions": enable_experimental,
        "products": result,
        "search_zips": valid_zips,
        "allowed_states": states,
        "us_priority_store": us_store,
        "ca_location": ca_postal,
        "ca_target_store": ca_store,
        "ca_tax_rate": tax,
    }
    if "monitoring_areas" in cfg:
        try:
            output["monitoring_areas"] = validate_monitoring_areas(cfg["monitoring_areas"], result, enable_experimental=enable_experimental)
        except ValueError as exc:
            raise InvalidConfig(str(exc)) from exc
    if "monitoring_areas" in output:
        areas_for_budget = output["monitoring_areas"]
    else:
        try:
            areas_for_budget = legacy_areas(valid_zips, ca_postal, ca_store, result)
        except ValueError as exc:
            raise InvalidConfig(str(exc)) from exc
    try:
        validate_request_budget(result, areas_for_budget)
    except ModelSelectionError as exc:
        raise InvalidConfig(str(exc)) from exc
    for key, regex in (("alert_store_ids", STORE_ID), ("alert_product_ids", PRODUCT_ID)):
        if key in cfg:
            values = _string_list(cfg[key], key, regex)
            if key == "alert_product_ids" and not set(values).issubset(result):
                raise InvalidConfig("Alert products must refer to configured product IDs")
            output[key] = values
    return output


WIZARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Apple Watcher — Local Setup</title>
<style>
:root{color-scheme:dark;--bg:#000;--panel:#101216;--border:#30343d;--text:#f8f8fa;--muted:#a1a8b5;--blue:#2997ff;--green:#30d985;--red:#ff6575}
*{box-sizing:border-box}body{font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:var(--bg);color:var(--text);margin:0;padding:30px 20px}
main{max-width:1050px;margin:auto}header{margin-bottom:25px}h1{font-size:clamp(27px,5vw,40px);margin:0 0 8px;letter-spacing:-.04em}h2{font-size:21px;letter-spacing:-.025em;margin:0 0 7px}p{margin:0 0 15px;color:var(--muted)}
section{background:var(--panel);border:1px solid var(--border);border-radius:21px;padding:22px;margin-bottom:18px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:11px}.full{grid-column:1/-1}
label{display:block;color:var(--muted);font-size:13px;margin-bottom:5px}input,select{width:100%;border:1px solid var(--border);border-radius:10px;background:#191d25;color:var(--text);font:inherit;padding:10px 11px;outline:none;min-width:0}
input:focus,select:focus{border-color:var(--blue)}button{font:inherit;cursor:pointer;border:1px solid var(--border);background:#222833;color:var(--text);padding:10px 16px;border-radius:12px}
button.primary{background:var(--blue);border-color:var(--blue);color:#fff;font-weight:650}button.remove{color:#ff9fa6;border-color:#58333c;background:#28191d}button:disabled{opacity:.6;cursor:wait}
.toolbar{display:flex;gap:12px;justify-content:space-between;align-items:center;flex-wrap:wrap;margin-bottom:13px}
.entry{background:#171a20;padding:16px;border:1px solid var(--border);border-radius:15px;margin-bottom:10px}
.entry-top{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:12px}
.entry-top strong{font-size:13px}small{font-size:12px;color:var(--muted)}.info{background:#102218;border:1px solid #225238;padding:11px 15px;border-radius:12px;color:#d6f7df;margin-bottom:16px}
.actions{display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin:20px 0}#message{min-height:22px;color:var(--muted)}.toggle{display:flex;align-items:center;gap:8px;color:var(--text);margin:7px 0 12px}.toggle input{width:auto}
@media(max-width:750px){.grid,.fields{grid-template-columns:1fr}.full{grid-column:1}section{padding:16px}body{padding:20px 12px}}
.area-warning{border:1px solid #b18533;background:#30230f;color:#ffd997;padding:14px 16px;border-radius:14px;margin-top:12px}.area-warning p{color:#f0d3a6;margin:4px 0 0}.area-warning[hidden]{display:none}
.model-filters{border:1px solid var(--border);padding:15px;border-radius:15px;background:#191c25;margin:15px 0}.model-filters[hidden]{display:none}.filter-help{font-size:12px;color:var(--muted);padding:4px 0}.model-watch{border:1px solid #315580;background:#142337;border-radius:14px;padding:13px 15px;margin:9px 0;display:flex;gap:12px;align-items:center;justify-content:space-between}.model-watch strong{display:block}.model-watch small{display:block}.model-watch button{flex-shrink:0}.advanced{margin-top:18px}.advanced summary{cursor:pointer;color:#9dbef0;font-weight:600;padding:10px 0}
.has-pending .toast-zone{bottom:85px}
@media(max-width:620px){.has-pending .toast-zone{bottom:145px}}
.toast-zone{position:fixed;right:20px;bottom:20px;z-index:1000;width:min(390px,calc(100vw - 32px));pointer-events:none}
.toast-success{background:#123926;border:1px solid #2e9566;color:#e1ffeb;border-radius:14px;padding:13px 17px;box-shadow:0 14px 45px #000a;display:flex;gap:12px;align-items:center;animation:toast-in .2s ease-out}
.toast-success strong{color:#81e8ae;font-size:19px}.toast-success span{font-size:13px;line-height:1.4}
@keyframes toast-in{from{transform:translateY(10px);opacity:0}to{transform:translateY(0);opacity:1}}
.area-subtitle{font-size:12px;color:var(--muted)}.area-entry-title{display:flex;flex-direction:column;gap:2px}
.setup-progress{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:17px;color:var(--muted);font-size:12px}
.setup-progress span{padding:7px 10px;background:#1a1c22;border:1px solid var(--border);border-radius:999px}
.setup-progress span.current{border-color:#407bb9;color:#d5eaff;background:#172638}
.watch-summary{margin:18px 0;padding:17px;background:#171b22;border:1px solid #394351;border-radius:16px}
.watch-summary h2{font-size:18px;margin:0 0 5px}.watch-summary p{font-size:13px;margin:0 0 10px}
.watch-summary-title{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}
.watch-summary-list{display:flex;flex-direction:column;gap:8px}
.watch-group{border:1px solid #344252;background:#202832;border-radius:12px;padding:12px 14px;display:flex;align-items:center;justify-content:space-between;gap:12px}
.watch-group strong{font-size:14px;display:block;color:var(--text)}.watch-group small{line-height:1.5}
.watch-empty{color:#aab4c2;font-size:13px;padding:12px 2px}
.setup-state{padding:13px 16px;background:#17232d;border:1px solid #436279;border-radius:13px;margin:12px 0 22px;display:flex;align-items:flex-start;gap:11px}
.setup-state strong{display:block;font-size:14px}.setup-state p{margin:2px 0 0;font-size:12px}.setup-state[data-state="dirty"]{background:#302414;border-color:#8d6635}.setup-state[data-state="saved"]{background:#162b22;border-color:#33785b}.setup-state[data-state="preview"]{background:#302414;border-color:#8d6635}
.preview-warning{font-size:13px;color:#f7d39f;background:#332618;border:1px solid #775d36;border-radius:10px;padding:10px 13px;margin:10px 0}
.preview-warning[hidden]{display:none}
.save-dock{position:fixed;bottom:0;left:0;right:0;z-index:900;background:rgba(14,17,23,.98);border-top:1px solid #454e5e;box-shadow:0 -10px 30px #0008;padding:11px max(18px,calc((100vw - 1050px)/2));display:flex;justify-content:space-between;align-items:center;gap:16px}
.save-dock[hidden]{display:none}.save-dock strong{font-size:13px}.save-dock small{display:block}.save-dock button{flex-shrink:0}
body.has-pending{padding-bottom:95px}
@media(max-width:620px){.save-dock{flex-wrap:wrap;gap:8px}.save-dock button{width:100%}body.has-pending{padding-bottom:160px}}
.catalog-entry{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px;border-top:1px solid var(--border)}.catalog-entry strong{display:block;font-size:13px}.catalog-entry small{display:block}.catalog-entry button{flex-shrink:0}.catalog-list{max-height:330px;overflow:auto;margin:12px 0}.catalog-status{font-size:13px;color:var(--muted);margin:12px 0}
</style>
</head><body><main>
<header><small>APPLE STOCK WATCHER / LOCAL SETUP</small><h1>Make it yours.</h1><p>Configure products, stores, prices and alerts without editing JSON.</p></header>
<div class="info">🔒 This wizard runs only on your computer (127.0.0.1). No webhook secrets are displayed or saved here.</div>
<div class="setup-progress" aria-label="Setup steps">
<span id="stepFind" class="current">1. Find a model</span><span id="stepChoose">2. Add variants</span><span id="stepSave">3. Save</span><span id="stepRestart">4. Restart watcher</span>
</div>
<div class="setup-state" id="setupState" data-state="loading" role="status" aria-live="polite">
<span id="setupStateIcon" aria-hidden="true">◌</span>
<div><strong id="setupStateTitle">Reading local configuration…</strong><p id="setupStateDetail">Products are only monitored after they are saved and the watcher is restarted.</p></div>
</div>
<section>
<label class="toggle"><input id="experimentalRegions" type="checkbox"> Enable France/UK preview (experimental)</label>
<p>France/UK pickup responses still need live verification. Other countries are not supported yet.</p>
<h2>1. Choose a product model</h2>
<p>Just choose the model name. Choose a model, then optionally narrow down by colour, storage and carrier connection. By default, all discovered variants are included.</p>
<div class="fields">
<div><label for="modelPicker">Apple model</label><select id="modelPicker">{% for model in model_choices %}<option value="{{model.id}}">{{model.name}}</option>{% endfor %}</select></div>
<div><label for="modelMarket">Country</label><select id="modelMarket"><option value="US">United States</option><option value="CA">Canada</option><option value="FR">France (experimental)</option><option value="GB">United Kingdom (experimental)</option></select></div>
</div>
<div class="actions"><button id="watchModel" type="button" class="primary">1. Find variants</button><span id="modelStatus" class="catalog-status" role="status" aria-live="polite"></span></div>
<div id="modelOptions" class="model-filters" hidden>
<h2>2. Choose variants (optional)</h2>
<p>All values are selected by default. Narrow the selection or leave everything as-is.</p>
<div class="fields">
<div><label for="modelColor">Colour</label><select id="modelColor"><option value="">All discovered colours</option></select></div>
<div><label for="modelStorage">Storage</label><select id="modelStorage"><option value="">All discovered capacities</option></select></div>
<div class="full"><label for="modelCarrier">Carrier connection</label><select id="modelCarrier"><option value="">Any / not specified</option></select></div>
</div>
<div id="carrierNote" class="filter-help">Carrier connection is not always encoded in Apple product SKUs.</div>
<div class="actions">
<button id="applyModelFilters" type="button" class="primary">2. Add selected variants to watchlist</button>
<button id="discardPreview" type="button">Discard preview</button>
<span id="modelCount" class="catalog-status" role="status" aria-live="polite"></span></div>
<div id="previewWarning" class="preview-warning" hidden>These are only search results. Click “Add selected variants to watchlist” to include them in your configuration.</div>
<small>Choosing “without carrier” is only possible when Apple's data explicitly identifies the corresponding item. Carrier activation at checkout is not proof of a separate stock SKU.</small>
</div>
<div class="watch-summary" id="watchSummary">
<div class="watch-summary-title"><h2>Your watchlist</h2><strong id="watchSummaryCount">0 variants</strong></div>
<p id="watchSummaryHelp">Only products listed below are included when you save. Finding variants does not add them automatically.</p>
<div class="watch-summary-list" id="monitoredModels"></div>
<div id="watchAreaSummary" class="area-subtitle"></div>
</div>
<small>Models are resolved from Apple's public product page when added, not continuously refreshed. Some variants (especially build-to-order Macs and Apple Watch bundles) may not support pickup. Unknown prices remain unknown.</small>
<details class="advanced" id="advancedProducts"><summary>Advanced: individual SKUs and manual product editing</summary>
<div class="toolbar"><p>Review exact part numbers, edit a variant, or add your own SKU.</p><button id="addProduct" type="button">+ Add SKU manually</button></div>
<div id="products"></div>
</details>
</section>
<details class="advanced"><summary>Advanced: browse individual Apple SKUs</summary>
<div>
<h2>Discover Apple products — preview</h2>
<p>Search the live official Apple buying pages on demand. SKU discovery is experimental: model variations and prices can be incomplete or change without notice. You always review the selected entry before saving.</p>
<div class="fields">
<div><label for="catalogMarket">Country</label><select id="catalogMarket"><option value="US">United States</option><option value="CA">Canada</option><option value="FR">France (experimental)</option><option value="GB">United Kingdom (experimental)</option></select></div>
<div><label for="catalogFamily">Product family</label><select id="catalogFamily">
<option value="iphone-18-pro">iPhone 18 Pro / Pro Max</option><option value="iphone-17">iPhone 17</option><option value="iphone-air">iPhone Air</option>
<option value="ipad-pro">iPad Pro</option><option value="ipad-air">iPad Air</option>
<option value="macbook-air">MacBook Air</option><option value="macbook-pro">MacBook Pro</option><option value="mac-mini">Mac mini</option>
<option value="apple-watch">Apple Watch (limited)</option><option value="apple-watch-ultra">Apple Watch Ultra (limited)</option>
</select></div>
</div>
<div class="actions"><button id="findCatalog" type="button" class="primary">Find Apple SKUs</button><span id="catalogStatus" class="catalog-status" role="status" aria-live="polite"></span></div>
<label for="catalogFilter">Filter discovered variants</label><input id="catalogFilter" type="search" placeholder="Search model, capacity, colour or SKU" disabled>
<div id="catalogResults" class="catalog-list"></div>
<small>One official Apple page request at a time, cached for six hours. Missing prices must be entered manually. Apple's store pickup API does not guarantee availability for all products (especially customised Macs and Watch bundles).</small>
</div>
</details>
<section>
<div class="toolbar"><div><h2>2. Monitoring areas</h2><p>Select a country and postal code or city for each area. US currently requires a five-digit ZIP; Canada also accepts a city, but postal codes are recommended. Countries beyond US/Canada will be added as validated.</p></div>
<div class="toolbar"><button id="addRegion" type="button">+ Add area</button><button id="renameAreas" type="button">Rename area IDs from locations</button></div></div>
<div id="regions"></div>
<div class="info" id="areaEstimate" role="status" aria-live="polite">Estimated requests: 1 per area per scan.</div>
<div id="areaWarning" class="area-warning" hidden><strong>⚠ Multiple monitoring areas</strong><p>More areas mean more Apple requests. Monitoring may become slower, return partial results, or be temporarily interrupted by rate limits. The app spaces requests, stops a scan when Apple throttles it, and never reports missed checks as confirmed out-of-stock.</p></div>
</section>
<div class="grid">
<section><h2>3. United States</h2><p>Advanced: filter which US states may appear in monitoring results.</p>
<label for="states">Allowed US states (comma-separated, blank = all)</label><input id="states" placeholder="DE, NY, NJ, PA">
<label for="priority" style="margin-top:12px">Priority US store ID (optional)</label><input id="priority" placeholder="R102"></section>
<section><h2>Canadian tax estimate</h2><p>Only a configurable estimate, not a nationwide tax rate.</p>
<label for="caTax">Estimated sales tax (%)</label><input id="caTax" type="number" min="0" max="100" step=".01" placeholder="13"></section>
</div>
<section><h2>4. Discord alert filters</h2><p>These filters affect notifications, not what appears on the dashboard. Configure your Discord webhook separately in your private .env file.</p>
<div class="grid"><div>
<label class="toggle"><input id="allStores" type="checkbox" checked> Alert for all stores</label>
<label for="alertStores">Store IDs when filtering (comma separated)</label><input id="alertStores" placeholder="R102, R121" disabled>
</div><div>
<label class="toggle"><input id="allProducts" type="checkbox" checked> Alert for all configured products</label>
<label for="alertProducts">Product IDs when filtering (comma separated)</label><input id="alertProducts" placeholder="us_pro_512" disabled>
</div></div><small>Uncheck and leave a field empty to disable notifications for that dimension.</small>
</section>
<div class="actions"><button class="primary" type="button" id="save">3. Save private configuration</button><span id="message" role="status" aria-live="polite"></span></div>
<p>Saved to <code>config.json</code> next to the watcher. Restart the watcher to apply changes. This wizard does not start monitoring or send notifications.</p>
</main>
<div class="save-dock" id="saveDock" hidden>
<div><strong id="saveDockText">Unsaved configuration changes</strong><small>Not applied to the watcher until saved and restarted</small></div>
<button id="saveSticky" type="button" class="primary">Save changes</button>
</div>
<div id="toastZone" class="toast-zone" role="status" aria-live="polite" aria-atomic="true"></div>
<template id="productTemplate"><article class="entry product-entry"><div class="entry-top"><strong>Product</strong><button type="button" class="remove">Remove</button></div><div class="fields">
<div><label>Product ID (auto-generated for selected variants)</label><input class="pid" placeholder="iphone_18_pro_max_512gb_silver_ca" maxlength="40"></div>
<div><label>Market</label><select class="market"><option value="US">United States</option><option value="CA">Canada</option><option value="FR">France (experimental)</option><option value="GB">United Kingdom (experimental)</option></select></div>
<div class="full"><label>Display name</label><input class="pname" placeholder="iPhone 18 Pro 512GB Silver" maxlength="100"></div>
<div><label>Apple SKU</label><input class="sku" placeholder="MJQ84LL/A" maxlength="32"></div>
<div><label>Price before tax</label><input class="price" type="number" min="0" max="100000" step=".01"></div>
</div></article></template>
<template id="regionTemplate"><article class="entry region-entry"><div class="entry-top"><div class="area-entry-title"><strong class="areaTitle">Monitoring area</strong><span class="area-subtitle">One location can monitor multiple products in this country</span></div><button type="button" class="remove">Remove</button></div><div class="fields">
<div><label>Area ID (country + postal code / city)</label><input class="areaId" placeholder="us_19702" maxlength="32"></div>
<div><label>Country</label><select class="country"><option value="US">United States</option><option value="CA">Canada</option><option value="FR">France (experimental)</option><option value="GB">United Kingdom (experimental)</option></select></div>
<div><label>ZIP / postal code or city</label><input class="location" placeholder="19702 or M5B 2H1" maxlength="64"></div>
<div><label>Apple Store IDs (optional; blank = all returned)</label><input class="areaStores" placeholder="R102, R121"></div>
</div></article></template>
<script>
const TOKEN = {{ token | tojson }};
let original = {};
let isLoadingConfig=true;
let hasSavedFile=false;
let hasUnsavedChanges=false;
const el = id => document.getElementById(id);
function refreshSetupState(){
  const products=document.querySelectorAll(".product-entry").length;
  const areas=document.querySelectorAll(".region-entry").length;
  const inPreview=!!modelPreview&&!el("modelOptions").hidden;
  const state=hasUnsavedChanges?"dirty":inPreview?"preview":hasSavedFile?"saved":"example";
  el("setupState").dataset.state=state;
  el("setupStateIcon").textContent=hasUnsavedChanges?"●":hasSavedFile?"✓":"○";
  el("setupStateTitle").textContent=hasUnsavedChanges
    ?"Changes not saved"
    :inPreview?"Variants found — not added yet"
    :hasSavedFile?"Configuration saved on this computer":"Example configuration — not yet saved";
  el("setupStateDetail").textContent=hasUnsavedChanges
    ?products+" selected variants in "+areas+" areas."+
      (inPreview?" You also have a preview that has NOT been added.":" Save changes, then restart the watcher.")
    :inPreview?modelPreview.count+" variants found. Select the options and click Add selected variants before saving."
    :hasSavedFile?"Saved in config.json. Restart the watcher to apply; this page does not check whether monitoring is running."
    :"This example is not your active setup. Add a model, save a private configuration and restart the watcher.";
  el("stepFind").classList.toggle("current",!modelPreview&&!hasUnsavedChanges&&!hasSavedFile);
  el("stepChoose").classList.toggle("current",inPreview);
  el("stepSave").classList.toggle("current",hasUnsavedChanges);
  el("stepRestart").classList.toggle("current",!hasUnsavedChanges&&hasSavedFile);
  const showDock=hasUnsavedChanges;
  el("saveDock").hidden=!showDock;
  document.body.classList.toggle("has-pending",showDock);
  el("saveDockText").textContent=products+" selected variants · "+areas+" areas · unsaved changes";
}
function markDirty(){
  if(isLoadingConfig)return;
  hasUnsavedChanges=true;
  renderMonitoredModels();
  updateAreaWarning();
  refreshSetupState();
}
const splitIds = value => value.split(",").map(s=>s.trim()).filter(Boolean);
function slugPart(value){
  return String(value||"").normalize("NFKD").replace(/[\u0300-\u036f]/g,"").toLowerCase()
    .replace(/[^a-z0-9]+/g,"_").replace(/^_+|_+$/g,"");
}
function productIdForVariant(item,modelId){
  const model=slugPart(modelId||item.name||"apple").slice(0,23);
  const storage=slugPart(item.storage).replace(/^([0-9]+)_?(gb|tb)$/,"$1$2");
  const details=[model,storage,slugPart(item.color)];
  if(item.carrier)details.push(item.carrier==="unlocked"?"simfree":slugPart(item.carrier));
  const market=slugPart(item.market||"us");
  const suffix="_"+market;
  const head=details.filter(Boolean).join("_").slice(0,40-suffix.length).replace(/_+$/g,"");
  return (head||"apple_product")+suffix;
}
function uniqueId(base,used,maxLength){
  let id=base.slice(0,maxLength),number=2;
  while(used.has(id)){
    const suffix="_"+number++;
    id=base.slice(0,maxLength-suffix.length).replace(/_+$/g,"")+suffix;
  }
  used.add(id);
  return id;
}
function areaIdFromLocation(market,location){
  const code=slugPart(market||"us");
  const raw=String(location||"new").trim();
  const postal=/^[A-Za-z][0-9][A-Za-z]\s?[0-9][A-Za-z][0-9]$/.test(raw);
  const place=slugPart(postal?raw.replace(/\s/g,""):raw);
  return (code+"_"+place).slice(0,32).replace(/_+$/g,"");
}
function showToast(message){
  const host=el("toastZone");
  host.replaceChildren();
  const toast=document.createElement("div");toast.className="toast-success";
  const check=document.createElement("strong");check.textContent="✓";
  const label=document.createElement("span");label.textContent=message;
  toast.append(check,label);host.append(toast);
  const current=toast;
  setTimeout(()=>{if(host.firstChild===current)current.remove();},4200);
}
let catalogRows = [];
function renderCatalog(){
  const container=el("catalogResults");container.replaceChildren();
  const phrase=el("catalogFilter").value.toLowerCase().trim();
  let matches=catalogRows.filter(p=>(p.name+" "+p.part).toLowerCase().includes(phrase));
  for(const item of matches.slice(0,80)){
    const row=document.createElement("div");row.className="catalog-entry";
    const info=document.createElement("div");
    const title=document.createElement("strong");title.textContent=item.name;
    const meta=document.createElement("small");meta.textContent=item.part+" • "+item.currency+" • "+(item.price===null?"Price not supplied by Apple; enter manually":item.price.toFixed(2));
    info.append(title,meta);
    const add=document.createElement("button");add.type="button";add.textContent="Add";
    add.addEventListener("click",()=>{
      const already=[...document.querySelectorAll(".product-entry")].some(root=>
        root.querySelector(".market").value===item.market&&root.querySelector(".sku").value.toUpperCase()===item.part.toUpperCase());
      if(already){status("This SKU is already in your product list.",true);return;}
      const id=productIdForVariant(item,item.family||item.name);
      const existing=new Set([...document.querySelectorAll(".pid")].map(node=>node.value));
      const finalId=uniqueId(id,existing,40);
      productRow(finalId,item);
      markDirty();
      status("Added "+item.part+". Review details before saving.");
      showToast("Added "+item.name+" to your selection. Save to apply.");
      el("advancedProducts").open=true;
      el("products").lastElementChild.scrollIntoView({behavior:"smooth",block:"center"});
    });
    row.append(info,add);container.append(row);
  }
  if(matches.length>80){const note=document.createElement("small");note.textContent=(matches.length-80)+" more variants: type in the filter to narrow down.";container.append(note);}
}
async function discoverCatalog(){
  const button=el("findCatalog");
  const market=el("catalogMarket").value;
  if(["FR","GB"].includes(market)&&!el("experimentalRegions").checked){
    el("catalogStatus").textContent="Check the experimental France/UK checkbox above first.";
    return;
  }
  button.disabled=true;el("catalogStatus").textContent="Reading Apple's product page…";
  try{
    const r=await fetch("/api/catalog/discover",{method:"POST",
      headers:{"Content-Type":"application/json","X-Setup-Token":TOKEN},
      body:JSON.stringify({market,family:el("catalogFamily").value,experimental:el("experimentalRegions").checked})});
    const data=await r.json();
    if(!r.ok)throw Error(data.error||"Apple catalog unavailable");
    catalogRows=data.items||[];
    el("catalogFilter").disabled=false;el("catalogFilter").value="";
    renderCatalog();
    el("catalogStatus").textContent=catalogRows.length+" variants • "+(data.cached?"cached":"fresh")+". Check the SKU and current price on Apple's website.";
  }catch(e){catalogRows=[];el("catalogResults").replaceChildren();el("catalogFilter").disabled=true;
    el("catalogStatus").textContent=String(e.message||e);
  }finally{button.disabled=false;}
}
function renderMonitoredModels(){
  const container=el("monitoredModels");container.replaceChildren();
  const roots=[...document.querySelectorAll(".product-entry")];
  const groups=new Map();
  const manual=[];
  for(const root of roots){
    const model=root.dataset.watchModel;
    if(!model){manual.push(root);continue;}
    const market=root.querySelector(".market").value;
    const key=market+"|"+model;
    if(!groups.has(key))groups.set(key,[]);
    groups.get(key).push(root);
  }
  el("watchSummaryCount").textContent=roots.length+" variant"+(roots.length===1?"":"s")+" selected";
  el("watchSummaryHelp").textContent=roots.length
    ? "This is your actual selection. Any change requires Save, then a watcher restart."
    : "Nothing selected yet. Finding variants is only a preview: click Add selected variants before Save.";
  for(const [key,variants] of groups){
    const [market,model]=key.split("|");
    const row=document.createElement("div");row.className="watch-group";
    const details=document.createElement("div");
    const name=document.createElement("strong");
    name.textContent=(el("modelPicker").querySelector('option[value="'+model+'"]')?.textContent||model)+" · "+market;
    const colors=[...new Set(variants.map(root=>root.dataset.color).filter(Boolean))];
    const capacities=[...new Set(variants.map(root=>root.dataset.storage).filter(Boolean))];
    const descriptions=[
      variants.length+" SKU variant"+(variants.length===1?"":"s"),
      colors.length?colors.slice(0,3).join(", ")+(colors.length>3?" +"+(colors.length-3):""):"colour unspecified",
      capacities.length?capacities.join(", "):"storage unspecified",
    ];
    const info=document.createElement("small");info.textContent=descriptions.join(" · ");
    details.append(name,info);
    const remove=document.createElement("button");remove.className="remove";remove.type="button";remove.textContent="Remove";
    remove.addEventListener("click",()=>{
      for(const root of variants)root.remove();
      markDirty();
      status("Model removed from the editor. Save changes to apply.");
      showToast("Removed "+variants.length+" variant"+(variants.length===1?"":"s")+" of "+model+". Save to apply.");
    });
    row.append(details,remove);container.append(row);
  }
  if(manual.length){
    const row=document.createElement("div");row.className="watch-group";
    const info=document.createElement("div");
    const title=document.createElement("strong");title.textContent="Other manually configured products";
    const detail=document.createElement("small");
    detail.textContent=manual.length+" SKU variant"+(manual.length===1?"":"s")+
      " · Edit or remove individually in Advanced";
    info.append(title,detail);row.append(info);container.append(row);
  }
  if(!roots.length){
    const empty=document.createElement("div");empty.className="watch-empty";
    empty.textContent="No products in your watchlist yet. Select a model, find variants, then click Add selected variants.";
    container.append(empty);
  }
  const areaRows=[...document.querySelectorAll(".region-entry")];
  const areas=areaRows.map(root=>{
    const market=root.querySelector(".country").value;
    const location=root.querySelector(".location").value.trim()||"location not entered";
    const stores=root.querySelector(".areaStores").value.trim();
    return market+" "+location+(stores?" · stores "+stores:" · all nearby returned stores");
  });
  const configuredMarkets=new Set(roots.map(root=>root.querySelector(".market").value));
  const areaMarkets=new Set(areaRows.map(root=>root.querySelector(".country").value));
  const missing=[...configuredMarkets].filter(market=>!areaMarkets.has(market)).sort();
  el("watchAreaSummary").textContent="Monitoring areas ("+areas.length+"): "+(areas.join(" | ")||"none configured")+
    (missing.length?" ⚠ No area for "+missing.join(", ")+": these products will NOT be checked.":"");
  el("watchAreaSummary").style.color=missing.length?"#f7c66f":"";
}
let modelPreview=null;

function clearModelPreview(){
  modelPreview=null;
  el("modelOptions").hidden=true;
  el("previewWarning").hidden=true;
  el("modelStatus").textContent="";
  el("modelCount").textContent="";
  refreshSetupState();
}
function fillFacetSelect(id,values,allLabel){
  const select=el(id);select.replaceChildren();
  const all=document.createElement("option");all.value="";all.textContent=allLabel;select.append(all);
  for(const value of values){
    const option=document.createElement("option");option.value=value;option.textContent=value;
    select.append(option);
  }
  select.disabled=values.length===0;
}
function populateCarrierFilter(options){
  const carriers=options.carriers||[];
  const select=el("modelCarrier");
  fillFacetSelect("modelCarrier",[],"Any carrier / unspecified");
  if(carriers.length===0){
    el("carrierNote").textContent="Apple does not identify carrier activation for these SKU variants. You can monitor them, but carrier-free status cannot be guaranteed.";
    return;
  }
  select.disabled=false;
  if(carriers.includes("unlocked")){
    const option=document.createElement("option");option.value="unlocked";option.textContent="Without a carrier (verified in catalog)";
    select.append(option);
  }
  const connected=carriers.filter(c=>c!=="unlocked");
  if(connected.length){
    const any=document.createElement("option");any.value="__connected__";any.textContent="With a carrier (any identified)";
    select.append(any);
    for(const carrier of connected){
      const option=document.createElement("option");option.value="carrier:"+carrier;option.textContent=carrier;
      select.append(option);
    }
  }
  const unknown=options.carrier_unknown||0;
  el("carrierNote").textContent=unknown
    ? "Apple does not identify the carrier for "+unknown+" variants. Selecting a carrier excludes those unverified variants. Activation may be chosen at checkout."
    : "Carrier values are taken only from explicit Apple catalog fields; they do not guarantee a particular plan or SIM installation.";
}
function matchingModelRows(){
  if(!modelPreview)return [];
  const color=el("modelColor").value;
  const storage=el("modelStorage").value;
  const carrier=el("modelCarrier").value;
  return modelPreview.products.filter(item=>{
    if(color&&item.color!==color)return false;
    if(storage&&item.storage!==storage)return false;
    if(carrier==="unlocked"&&item.carrier!=="unlocked")return false;
    if(carrier==="__connected__"&&(!item.carrier||item.carrier==="unlocked"))return false;
    if(carrier.startsWith("carrier:")&&item.carrier!==carrier.slice(8))return false;
    return true;
  });
}
function updateModelPreview(){
  if(!modelPreview)return;
  const matches=matchingModelRows();
  const count=matches.length;
  const missing=matches.filter(x=>x.price===null).length;
  el("modelCount").textContent=count+" matching SKU"+(count===1?"":"s")+
    (missing?" · "+missing+" prices unknown":"")+
    (count>48?" · exceeds 48-SKU model limit":"");
  el("applyModelFilters").disabled=count===0||count>48;
  el("applyModelFilters").textContent="2. Add "+count+" selected variant"+(count===1?"":"s")+" to watchlist";
}
async function watchSelectedModel(){
  const btn=el("watchModel"),modelId=el("modelPicker").value,market=el("modelMarket").value;
  clearModelPreview();
  const availableMarkets=new Set([...document.querySelectorAll(".region-entry .country")].map(i=>i.value));
  if(!availableMarkets.has(market)){el("modelStatus").textContent="Add a monitoring area for "+market+" first.";return;}
  if(["FR","GB"].includes(market)&&!el("experimentalRegions").checked){
    el("modelStatus").textContent="Enable experimental France/UK first.";return;
  }
  btn.disabled=true;el("modelStatus").textContent="Finding regional variants from Apple…";
  try{
    const r=await fetch("/api/catalog/model",{method:"POST",
      headers:{"Content-Type":"application/json","X-Setup-Token":TOKEN},
      body:JSON.stringify({market,model_id:modelId,experimental:el("experimentalRegions").checked})});
    const result=await r.json();
    if(!r.ok)throw Error(result.error||"Unable to resolve model");
    modelPreview=result;
    const options=result.options||{colors:[],storages:[],carriers:[],carrier_unknown:result.count};
    fillFacetSelect("modelColor",options.colors||[],"All discovered colours");
    fillFacetSelect("modelStorage",options.storages||[],"All discovered capacities");
    populateCarrierFilter(options);
    el("modelOptions").hidden=false;
    el("previewWarning").hidden=false;
    updateModelPreview();
    refreshSetupState();
    el("modelStatus").textContent=result.count+" variants found ("+
      (result.cached?"cached":"fresh")+"). Select filters, then click Add selected variants.";
  }catch(error){el("modelStatus").textContent=String(error.message||error);}
  finally{btn.disabled=false;}
}
function applyModelSelection(){
  if(!modelPreview){el("modelStatus").textContent="Choose a model before selecting options.";return;}
  const {model_id:modelId,market}=modelPreview;
  const wanted=matchingModelRows();
  if(!wanted.length){el("modelCount").textContent="No variants match these options.";return;}
  if(wanted.length>48){el("modelCount").textContent="Narrow the selection to 48 variants or fewer.";return;}
  const current=[...document.querySelectorAll(".product-entry")];
  const other=current.filter(root=>root.dataset.watchModel!==modelId||root.querySelector(".market").value!==market);
  if(other.length+wanted.length>96){el("modelCount").textContent="Too many SKU variants (96 maximum). Remove another model.";return;}
  const projected=new Map();
  for(const root of other){
    const m=root.querySelector(".market").value;
    if(!projected.has(m))projected.set(m,new Set());
    projected.get(m).add(root.querySelector(".sku").value.toUpperCase());
  }
  for(const item of wanted){
    if(!projected.has(item.market))projected.set(item.market,new Set());
    projected.get(item.market).add(item.part.toUpperCase());
  }
  let estimated=0;
  document.querySelectorAll(".region-entry").forEach(root=>{
    const m=root.querySelector(".country").value;
    estimated+=Math.ceil((projected.get(m)?.size||0)/12);
  });
  if(estimated>24){el("modelCount").textContent=estimated+" Apple requests/scan exceeds the safe limit (24). Remove a model or area.";return;}
  for(const root of current){
    if(root.dataset.watchModel===modelId&&root.querySelector(".market").value===market)root.remove();
  }
  const taken=new Set([...document.querySelectorAll(".pid")].map(x=>x.value));
  let added=0,overlaps=0;
  for(const item of wanted){
    const duplicate=[...document.querySelectorAll(".product-entry")].some(root=>
      root.querySelector(".market").value===item.market&&root.querySelector(".sku").value.toUpperCase()===item.part.toUpperCase());
    if(duplicate){overlaps++;continue;}
    const id=productIdForVariant(item,modelId);
    const unique=uniqueId(id,taken,40);
    productRow(unique,{...item,watch_model:modelId});added++;
  }
  markDirty();
  const missing=wanted.filter(x=>x.price===null).length;
  el("modelStatus").textContent=added+" variants prepared for monitoring"+
    (overlaps?" ("+overlaps+" already present)":"")+
    ". "+missing+" prices unconfirmed. Click Save to apply.";
  if(added>0){
    showToast("Added "+added+" variant"+(added===1?"":"s")+" to your watchlist. Save to apply.");
    // A completed selection is no longer an uncommitted preview.
    modelPreview=null;
    el("modelOptions").hidden=true;
    el("previewWarning").hidden=true;
    el("watchSummary").scrollIntoView({behavior:"smooth",block:"center"});
  }
}
function productRow(id, p) {
  const root=el("productTemplate").content.firstElementChild.cloneNode(true);
  root.querySelector(".pid").value=id||"";
  root.querySelector(".market").value=p.market||"US";
  root.querySelector(".pname").value=p.name||"";
  root.querySelector(".sku").value=p.part||"";
  root.querySelector(".price").value=p.price??"";
  root.dataset.watchModel=p.watch_model||"";
  root.dataset.color=p.color||"";
  root.dataset.storage=p.storage||"";
  root.dataset.carrier=p.carrier||"";
  root.querySelector(".market").addEventListener("change",()=>{if(["FR","GB"].includes(root.querySelector(".market").value)&&!el("experimentalRegions").checked)status("France/UK requires checking the experimental preview box explicitly.",true);});
  root.querySelector(".remove").addEventListener("click",()=>{
    const name=root.querySelector(".pname").value||root.querySelector(".pid").value||"product";
    root.remove();markDirty();
    showToast("Removed "+name+". Save to apply.");
  });
  el("products").appendChild(root);renderMonitoredModels();
}
function refreshAreaRow(root){
  const market=root.querySelector(".country").value;
  const location=root.querySelector(".location").value.trim();
  const country=root.querySelector(".country").selectedOptions[0]?.textContent||market;
  root.querySelector(".areaTitle").textContent=country+(location?" · "+location:" · new location");
  if(root.dataset.autoAreaId==="true"){
    const used=new Set([...document.querySelectorAll(".region-entry")].filter(row=>row!==root)
      .map(row=>row.querySelector(".areaId").value));
    root.querySelector(".areaId").value=uniqueId(areaIdFromLocation(market,location),used,32);
  }
  updateAreaWarning();
}
function regionRow(area){
  const root=el("regionTemplate").content.firstElementChild.cloneNode(true);
  const id=root.querySelector(".areaId"),country=root.querySelector(".country");
  const location=root.querySelector(".location");
  root.dataset.autoAreaId=area.autoId||!area.id?"true":"false";
  id.value=area.id||"";
  country.value=area.market||"US";
  location.value=area.location||"";
  root.querySelector(".areaStores").value=(area.store_ids||[]).join(", ");
  id.addEventListener("input",()=>{root.dataset.autoAreaId="false";updateAreaWarning()});
  country.addEventListener("change",()=>refreshAreaRow(root));
  location.addEventListener("input",()=>refreshAreaRow(root));
  root.querySelector(".remove").addEventListener("click",()=>{
    const label=root.querySelector(".areaTitle").textContent;
    root.remove();markDirty();
    showToast("Removed area "+label+". Save to apply.");
  });
  root.querySelector(".areaStores").addEventListener("input",updateAreaWarning);
  el("regions").appendChild(root);
  refreshAreaRow(root);
  markDirty();
}
function updateAreaWarning(){
  const count=document.querySelectorAll(".region-entry").length;
  el("areaWarning").hidden=count<2;
  const skuCounts=new Map();
  document.querySelectorAll(".product-entry").forEach(root=>{
    const market=root.querySelector(".market").value,sku=root.querySelector(".sku").value.toUpperCase();
    if(!skuCounts.has(market))skuCounts.set(market,new Set());
    if(sku)skuCounts.get(market).add(sku);
  });
  let budget=0;
  document.querySelectorAll(".region-entry").forEach(root=>{
    budget+=Math.ceil((skuCounts.get(root.querySelector(".country").value)?.size||0)/12);
  });
  el("areaEstimate").textContent=count+" areas • approximately "+budget+
    " pickup requests per scan (limit 24; up to 12 SKUs per request). Estimates exclude retries. Maximum 8 areas.";
}
function loadForm(cfg){
  isLoadingConfig=true;
  original=cfg; el("products").replaceChildren();el("regions").replaceChildren();
  el("experimentalRegions").checked=cfg.enable_experimental_regions===true;
  Object.entries(cfg.products||{}).forEach(([id,p])=>productRow(id,p));
  const areas=Object.hasOwn(cfg,"monitoring_areas")?cfg.monitoring_areas:[
    ...Object.entries(cfg.search_zips||{}).map(([name,zip],i)=>({id:"us_"+(i+1),market:"US",location:zip,store_ids:[]})),
    ...(Object.values(cfg.products||{}).some(p=>p.market==="CA")&&cfg.ca_location?[{id:"ca_1",market:"CA",location:cfg.ca_location,store_ids:cfg.ca_target_store?[cfg.ca_target_store]:[]}]:[])
  ];
  areas.forEach(area=>regionRow(area));
  const markets=[...new Set(areas.map(area=>area.market))];
  if(markets.length===1)el("modelMarket").value=markets[0];
  el("states").value=(cfg.allowed_states||[]).join(", ");
  el("priority").value=cfg.us_priority_store||"";
  el("caTax").value=Number(cfg.ca_tax_rate??0.13)*100;
  el("allStores").checked=!Object.hasOwn(cfg,"alert_store_ids");
  el("allProducts").checked=!Object.hasOwn(cfg,"alert_product_ids");
  el("alertStores").value=(cfg.alert_store_ids||[]).join(", ");
  el("alertProducts").value=(cfg.alert_product_ids||[]).join(", ");
  toggleAlertFields();updateAreaWarning();renderMonitoredModels();
  isLoadingConfig=false;
  hasUnsavedChanges=false;
  refreshSetupState();
}
function toggleAlertFields(){
  el("alertStores").disabled=el("allStores").checked;
  el("alertProducts").disabled=el("allProducts").checked;
}
function collect(){
  const data={...original,products:{}};
  data.enable_experimental_regions=el("experimentalRegions").checked;
  document.querySelectorAll(".product-entry").forEach(root=>{
    const id=root.querySelector(".pid").value.trim();
    if(!id)throw Error("Every product needs an ID.");
    if(Object.hasOwn(data.products,id))throw Error("Duplicate product ID: "+id);
    const market=root.querySelector(".market").value;
    const priceInput=root.querySelector(".price").value;
    // Unknown prices from Apple are allowed: availability can still be monitored.
    data.products[id]={
      market,
      name:root.querySelector(".pname").value.trim(),
      part:root.querySelector(".sku").value.trim(),
      price:priceInput===""?null:Number(priceInput),
      currency:({US:"USD",CA:"CAD",FR:"EUR",GB:"GBP"})[market]
    };
    if(root.dataset.watchModel)data.products[id].watch_model=root.dataset.watchModel;
    for(const attribute of ["color","storage","carrier"]){
      if(root.dataset[attribute])data.products[id][attribute]=root.dataset[attribute];
    }
  });
  data.monitoring_areas=[];
  document.querySelectorAll(".region-entry").forEach(root=>{
    const id=root.querySelector(".areaId").value.trim();
    const market=root.querySelector(".country").value;
    const location=root.querySelector(".location").value.trim();
    if(!id)throw Error("Every monitoring area needs an ID.");
    data.monitoring_areas.push({id,market,location,store_ids:splitIds(root.querySelector(".areaStores").value)});
  });
  data.allowed_states=splitIds(el("states").value).map(s=>s.toUpperCase());
  data.us_priority_store=el("priority").value.trim();
  if(el("caTax").value==="")throw Error("Enter an estimated Canadian tax percentage.");
  data.ca_tax_rate=Number(el("caTax").value)/100;
  if(el("allStores").checked)delete data.alert_store_ids;
  else data.alert_store_ids=splitIds(el("alertStores").value);
  if(el("allProducts").checked)delete data.alert_product_ids;
  else data.alert_product_ids=splitIds(el("alertProducts").value).filter(id=>Object.hasOwn(data.products,id));
  return data;
}
function status(message,error=false){el("message").textContent=message;el("message").style.color=error?"#ff7c8b":"#55e29d";}
async function start(){
  try{
    const r=await fetch("/api/config",{cache:"no-store"});
    const payload=await r.json();if(!r.ok)throw Error(payload.error||"Cannot read configuration");
    hasSavedFile=payload.exists===true;
    loadForm(payload.config);
    status(payload.exists?"Existing private configuration loaded.":"Example configuration loaded; save to create your own.");
  }catch(error){status(String(error),true);}
}
el("addProduct").addEventListener("click",()=>{
  productRow("",{market:"US"});
  markDirty();
  status("New manual product added to the editor. Fill in its details, then Save.");
});
el("watchModel").addEventListener("click",watchSelectedModel);
el("applyModelFilters").addEventListener("click",applyModelSelection);
el("discardPreview").addEventListener("click",()=>{
  clearModelPreview();
  status("Preview discarded. Your saved and selected products were not changed.");
});
["modelColor","modelStorage","modelCarrier"].forEach(id=>el(id).addEventListener("change",updateModelPreview));
["modelPicker","modelMarket","experimentalRegions"].forEach(id=>el(id).addEventListener("change",clearModelPreview));
el("findCatalog").addEventListener("click",discoverCatalog);
el("catalogFilter").addEventListener("input",renderCatalog);
el("addRegion").addEventListener("click",()=>{
  const count=document.querySelectorAll(".region-entry").length;
  if(count>=8){status("Maximum 8 areas to protect Apple endpoints; remove an area first.",true);return}
  regionRow({market:"US",location:"",store_ids:[],autoId:true});
  markDirty();
});
el("renameAreas").addEventListener("click",()=>{
  const roots=[...document.querySelectorAll(".region-entry")];
  if(!roots.length){status("Add a monitoring area first.",true);return;}
  roots.forEach(root=>{
    root.dataset.autoAreaId="true";
    refreshAreaRow(root);
  });
  markDirty();
  showToast("Updated "+roots.length+" area IDs using country and location. Save to apply.");
});
el("allStores").addEventListener("change",toggleAlertFields);
const previewInputs=new Set(["modelPicker","modelMarket","modelColor","modelStorage","modelCarrier","catalogMarket","catalogFamily","catalogFilter"]);
function onConfigurationEdit(event){
  if(isLoadingConfig || previewInputs.has(event.target.id))return;
  if(event.target.closest(".product-entry") ||
     event.target.closest(".region-entry") ||
     ["experimentalRegions","states","priority","caTax","allStores","alertStores","allProducts","alertProducts"].includes(event.target.id)){
    markDirty();
  }
}
document.addEventListener("input",onConfigurationEdit);
document.addEventListener("change",onConfigurationEdit);
el("saveSticky").addEventListener("click",()=>el("save").click());
el("allProducts").addEventListener("change",toggleAlertFields);
el("save").addEventListener("click",async()=>{
  if(modelPreview&&!el("modelOptions").hidden){
    status("You found variants but have not added them. Click Add selected variants or Discard preview before saving.",true);
    el("modelOptions").scrollIntoView({behavior:"smooth",block:"center"});
    return;
  }
  const button=el("save");button.disabled=true;
  el("saveSticky").disabled=true;
  try{
    const data=collect();
    const r=await fetch("/api/config",{
      method:"POST",headers:{"Content-Type":"application/json","X-Setup-Token":TOKEN},
      body:JSON.stringify(data)
    });
    const response=await r.json();
    if(!r.ok)throw Error(response.error||"Save failed");
    hasSavedFile=true;
    loadForm(response.config);
    status("Saved locally. Restart your watcher to use the new settings.");
    showToast("Configuration saved. Restart the watcher to apply.");
  }catch(error){status(error.message||String(error),true);}
  finally{button.disabled=false;el("saveSticky").disabled=false;}
});
start();
</script></body></html>"""


def create_wizard_app(config_path=None, sample_path=None):
    path = Path(config_path) if config_path is not None else ROOT / "config.json"
    example = Path(sample_path) if sample_path is not None else ROOT / "config.example.json"
    csrf_token = secrets.token_urlsafe(32)
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 65536

    @app.before_request
    def local_only():
        if request.remote_addr not in ("127.0.0.1", "::1", None):
            abort(403)
        if request.host.split(":")[0].lower() not in ("127.0.0.1", "localhost", "[::1]"):
            abort(403)

    @app.after_request
    def privacy_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/")
    def index():
        return render_template_string(
            WIZARD_HTML, token=csrf_token,
            model_choices=[{"id": key, "name": item[0]} for key, item in MODELS.items()],
        )

    @app.get("/api/config")
    def read_config():
        target = path if path.is_file() else example
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
            clean = validate_config(raw)
        except (OSError, ValueError) as exc:
            return jsonify({"error": f"Cannot read {target.name}: {exc}"}), 422
        # Send only validated, UI-owned fields to the browser. Private
        # custom settings remain on disk and are merged during saving.
        return jsonify({"config": clean, "exists": path.is_file()})

    @app.post("/api/catalog/model")
    def resolve_model():
        origin = request.headers.get("Origin")
        if origin and origin != request.host_url.rstrip("/"):
            return jsonify({"error": "Request origin not allowed"}), 403
        if not hmac.compare_digest(request.headers.get("X-Setup-Token", ""), csrf_token):
            return jsonify({"error": "Setup token missing or invalid"}), 403
        selection = request.get_json(silent=True)
        if not isinstance(selection, dict):
            return jsonify({"error": "Invalid model selection"}), 422
        try:
            model_id = selection.get("model_id")
            market = selection.get("market")
            family = family_for(model_id)
            fetched = fetch_catalog(
                market, family, experimental=selection.get("experimental") is True,
            )
            result = model_catalog_result(model_id, market, fetched["items"])
            result["cached"] = fetched.get("cached", False)
            return jsonify(result)
        except (CatalogError, ModelSelectionError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 422

    @app.post("/api/catalog/discover")
    def discover_catalog():
        origin = request.headers.get("Origin")
        if origin and origin != request.host_url.rstrip("/"):
            return jsonify({"error": "Request origin not allowed"}), 403
        if not hmac.compare_digest(request.headers.get("X-Setup-Token", ""), csrf_token):
            return jsonify({"error": "Setup token missing or invalid"}), 403
        selection = request.get_json(silent=True)
        if not isinstance(selection, dict):
            return jsonify({"error": "Invalid catalog selection"}), 422
        try:
            market = selection.get("market")
            family = selection.get("family")
            experimental = selection.get("experimental") is True
            result = fetch_catalog(market, family, experimental=experimental)
            return jsonify(result)
        except CatalogError as exc:
            return jsonify({"error": str(exc)}), 422

    @app.post("/api/config")
    def write_config():
        origin = request.headers.get("Origin")
        if origin and origin != request.host_url.rstrip("/"):
            return jsonify({"error": "Request origin not allowed"}), 403
        provided = request.headers.get("X-Setup-Token", "")
        if not hmac.compare_digest(provided, csrf_token):
            return jsonify({"error": "Setup token missing or invalid"}), 403
        try:
            incoming = request.get_json(silent=True)
            clean = validate_config(incoming)
            # Preserve unknown local settings without revealing them through
            # GET /api/config. Old installations may include private keys.
            existing = {}
            if path.is_file():
                existing = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(existing, dict):
                    raise InvalidConfig("Existing configuration must be a JSON object")
            data = {**existing, **incoming, **clean}
            path.parent.mkdir(parents=True, exist_ok=True)
            # Preserve the most recent working configuration before replacing it.
            if path.is_file():
                previous = path.read_bytes()
                backup = path.with_name(path.name + ".bak")
                backup.write_bytes(previous)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, prefix=".watcher-config-",
                suffix=".tmp", delete=False
            ) as temp:
                temp.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
                temp_path = Path(temp.name)
            try:
                os.replace(temp_path, path)
            finally:
                temp_path.unlink(missing_ok=True)
        except InvalidConfig as exc:
            return jsonify({"error": str(exc)}), 422
        except ValueError as exc:
            return jsonify({"error": f"Cannot read existing configuration: {exc}"}), 422
        except OSError as exc:
            return jsonify({"error": f"Could not save local configuration: {exc}"}), 500
        # Never echo potentially sensitive unknown JSON fields to the browser.
        return jsonify({"saved": True, "config": clean})

    return app


def main():
    parser = argparse.ArgumentParser(description="Edit Apple Watcher config in a local browser")
    parser.add_argument("--port", type=int, default=8091)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    print(f"Open http://127.0.0.1:{args.port} to configure the watcher.", flush=True)
    print("The wizard listens only on this computer. Press Ctrl+C to stop.", flush=True)
    create_wizard_app().run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
