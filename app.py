import os, json, time, random, threading, math
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template_string
from history import append_history, read_history, transition_event
from monitoring_areas import legacy_areas, validate_monitoring_areas, uncovered_product_markets, MAX_MONITORING_AREAS
from regions import REGIONS, region_for
from model_watch import PRODUCT_BATCH_SIZE, MAX_PRODUCTS, validate_request_budget
from dashboard_groups import build_model_groups

VERSION = "1.0.0"

load_dotenv()

# ========================= CONFIG =========================
INTERVAL = max(120, int(os.getenv("CHECK_INTERVAL", "300")))
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")
# Local testing override: do not send to Discord even if .env contains a webhook.
WATCHER_DISABLE_DISCORD = os.getenv("WATCHER_DISABLE_DISCORD", "").strip().lower() in {"1", "true", "yes", "on"}
STATE_FILE = Path(os.getenv("STATE_FILE", "state_v43.json"))
HISTORY_FILE = Path(os.getenv("HISTORY_FILE", "history.json"))
HISTORY_MAX_EVENTS = max(0, int(os.getenv("HISTORY_MAX_EVENTS", "500")))

US_URL = "https://www.apple.com/shop/retail/pickup-message"
CA_URL = "https://www.apple.com/ca/shop/retail/pickup-message"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*"}

PRODUCTS = {
    "us_max": {"market":"US","name":"iPhone 18 Pro Max 1TB Silver","part":"MJWE4LL/A","price":1899.0,"currency":"USD"},
    "us_pro": {"market":"US","name":"iPhone 18 Pro 1TB Silver","part":"MJQD4LL/A","price":1799.0,"currency":"USD"},
    "us_pro_512": {"market":"US","name":"iPhone 18 Pro 512GB Silver","part":"MJQ84LL/A","price":1399.0,"currency":"USD"},
    "ca_max": {"market":"CA","name":"iPhone 18 Pro Max 1TB Silver","part":"MJXF4VC/A","price":2799.0,"currency":"CAD"},
    "ca_pro": {"market":"CA","name":"iPhone 18 Pro 1TB Silver","part":"MJRG4VC/A","price":2649.0,"currency":"CAD"},
    "ca_pro_512": {"market": "CA","name": "iPhone 18 Pro 512GB Silver","part": "MJRC4VC/A","price": 2049.0,"currency": "CAD"},
}

US_PRODUCT_IDS = ["us_max", "us_pro", "us_pro_512"]
CA_PRODUCT_IDS = ["ca_max", "ca_pro", "ca_pro_512"]
SEARCH_ZIPS = {"NYC":"10001", "DELAWARE":"19702", "DC":"20001", "BUFFALO":"14225", "CLARENDON":"22201"}
ALLOWED_STATES = {"DE","NY","NJ","PA","MD","DC","VA"}
US_PRIORITY_STORE = "R102"       # Christiana Mall
CA_TARGET_STORE = "R121"         # Eaton Centre
CA_LOCATION = "M5B 2H1"

# Optional user configuration. See config.example.json.
# Missing config.json preserves the original V4.5 defaults.
CONFIG_PATH = Path(os.getenv("WATCHER_CONFIG", "config.json"))
ALERT_STORE_IDS = None
ALERT_PRODUCT_IDS = None
ENABLE_EXPERIMENTAL_REGIONS = False
if CONFIG_PATH.exists():
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        raise ValueError("Watcher config must be a JSON object")
    ENABLE_EXPERIMENTAL_REGIONS = cfg.get("enable_experimental_regions", False)
    if not isinstance(ENABLE_EXPERIMENTAL_REGIONS, bool):
        raise ValueError("enable_experimental_regions must be a boolean")
    if "products" in cfg:
        products = cfg["products"]
        if not isinstance(products, dict) or not 1 <= len(products) <= MAX_PRODUCTS:
            raise ValueError("products must be a nonempty JSON object")
        for pid, product in products.items():
            if not isinstance(product, dict):
                raise ValueError(f"Invalid product configuration: {pid}")
            try:
                region = region_for(product.get("market"), ENABLE_EXPERIMENTAL_REGIONS)
            except ValueError as exc:
                raise ValueError(f"Invalid market for product {pid}: {exc}") from exc
            if product.get("currency") != region.currency:
                raise ValueError(f"Product {pid} requires currency {region.currency}")
            if not all(product.get(field) for field in ("name", "part", "currency")):
                raise ValueError(f"Product {pid} must have name, part and currency")
            price = product.get("price")
            if price is not None and (
                isinstance(price, bool)
                or not isinstance(price, (int, float))
                or not math.isfinite(price)
                or not 0 <= price <= 100000
            ):
                raise ValueError(f"Product {pid} must have a finite nonnegative numeric price")
        PRODUCTS = products
    if "search_zips" in cfg:
        if not isinstance(cfg["search_zips"], dict):
            raise ValueError("search_zips must be an object")
        SEARCH_ZIPS = {str(k): str(v) for k, v in cfg["search_zips"].items()}
    if "allowed_states" in cfg:
        if not isinstance(cfg["allowed_states"], list):
            raise ValueError("allowed_states must be a list")
        ALLOWED_STATES = {str(s).upper() for s in cfg["allowed_states"]}
    US_PRIORITY_STORE = str(cfg.get("us_priority_store", US_PRIORITY_STORE))
    CA_TARGET_STORE = str(cfg.get("ca_target_store", CA_TARGET_STORE))
    CA_LOCATION = str(cfg.get("ca_location", CA_LOCATION))
    CA_TAX_RATE = float(cfg.get("ca_tax_rate", 0.13))
    for option in ("alert_store_ids", "alert_product_ids"):
        if option not in cfg:
            continue
        value = cfg[option]
        if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
            raise ValueError(f"{option} must be a list of nonempty strings")
        if option == "alert_store_ids":
            ALERT_STORE_IDS = set(value)
        else:
            unknown_ids = set(value) - set(PRODUCTS)
            if unknown_ids:
                raise ValueError(f"Unknown alert product IDs: {sorted(unknown_ids)}")
            ALERT_PRODUCT_IDS = set(value)
else:
    CA_TAX_RATE = 0.13
MARKET_PRODUCT_IDS = {market: [pid for pid, p in PRODUCTS.items() if p["market"] == market] for market in REGIONS}
US_PRODUCT_IDS = MARKET_PRODUCT_IDS["US"]
CA_PRODUCT_IDS = MARKET_PRODUCT_IDS["CA"]
if any(p["market"] in {"FR", "GB"} for p in PRODUCTS.values()) and (
    not CONFIG_PATH.exists() or "monitoring_areas" not in cfg
):
    raise ValueError("France/UK products require explicit monitoring_areas in config.json")
MONITORING_AREAS = (
    validate_monitoring_areas(cfg["monitoring_areas"], PRODUCTS, enable_experimental=ENABLE_EXPERIMENTAL_REGIONS)
    if CONFIG_PATH.exists() and "monitoring_areas" in cfg
    else legacy_areas(SEARCH_ZIPS, CA_LOCATION, CA_TARGET_STORE, PRODUCTS)
)
# With several locations, avoid polling as aggressively as a single-location watcher.
REQUESTS_PER_SCAN = validate_request_budget(PRODUCTS, MONITORING_AREAS)
INTERVAL = max(INTERVAL, 300 if len(MONITORING_AREAS) > 1 else 120, 600 if len(MONITORING_AREAS) > 4 or REQUESTS_PER_SCAN > 4 else 120, 900 if REQUESTS_PER_SCAN > 12 else 120)
if not any(MARKET_PRODUCT_IDS.values()):
    raise ValueError("Configure at least one product")
if not 0 <= CA_TAX_RATE <= 1:
    raise ValueError("ca_tax_rate must be a fraction between 0 and 1")

FX_REFRESH_SECONDS = 21600
fx_cache = {}

app = Flask(__name__)
lock = threading.Lock()
latest = {"status":"starting","checked_at":None,"items":[],"error":None,"consecutive_errors":0}

# ========================= UTILS =========================
def now():
    return datetime.now(timezone.utc).isoformat()

def load_state():
    """Treat malformed or incompatible JSON state as an empty prior state.

    A file containing valid JSON like [] or {"available_keys": [[]]} used
    to crash poll_once(), including its exception handler, killing the worker.
    """
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return {}
    if not isinstance(state, dict):
        return {}
    available_keys = state.get("available_keys", [])
    if not isinstance(available_keys, list) or any(
        not isinstance(key, str) or not key for key in available_keys
    ):
        return {}
    if "watcher_error" in state and not isinstance(state["watcher_error"], bool):
        return {}
    return state

def save_state(data):
    try:
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(STATE_FILE)
    except Exception as e:
        print("State save error:", e, flush=True)

def safe_discord(message=None, embeds=None):
    if WATCHER_DISABLE_DISCORD or not DISCORD_WEBHOOK: return
    payload = {}
    if message: payload["content"] = message
    if embeds: payload["embeds"] = embeds
    if not payload: return
    try:
        r = requests.post(DISCORD_WEBHOOK, json=payload, timeout=15)
        r.raise_for_status()
    except Exception as e:
        # Requests exceptions can include the complete webhook URL (with its
        # secret token). Never print URLs or response bodies to console logs.
        status = getattr(getattr(e, "response", None), "status_code", None)
        detail = f"HTTP {status}" if isinstance(status, int) else type(e).__name__
        print(f"Discord delivery error: {detail}", flush=True)

# ========================= FX =========================
def get_eur_rate(currency):
    if currency == "EUR": return 1.0, None
    t = time.time(); cached = fx_cache.get(currency)
    if cached and t - cached["updated_at"] < FX_REFRESH_SECONDS:
        return cached["rate"], cached["date"]
    try:
        url = f"https://api.frankfurter.dev/v2/rate/{currency.lower()}/eur"
        r = requests.get(url, headers=HEADERS, timeout=15); r.raise_for_status()
        data = r.json(); rate = float(data["rate"]); date = data.get("date")
        if rate <= 0: raise ValueError("invalid FX rate")
        fx_cache[currency] = {"rate":rate,"date":date,"updated_at":t}
        print(f"FX {currency}/EUR: {rate} ({date})", flush=True)
        return rate, date
    except Exception as e:
        print(f"FX {currency}/EUR error:", e, flush=True)
        if cached: return cached["rate"], cached["date"]
        return None, None

# ========================= TAXES / MONEY =========================
def us_tax_rate(store):
    state = (store.get("state") or "").upper()
    city = (store.get("city") or "").lower()
    name = (store.get("storeName") or "").lower()

    if state == "DE":
        return 0.0
    if state == "NJ":
        return 0.06625
    if state == "VA" and (city == "arlington" or "clarendon" in name):
        return 0.06
    if state == "MD":
        return 0.06
    if state == "DC":
        return 0.06
    if state == "PA":
        return 0.08 if city == "philadelphia" or "walnut street" in name else 0.06

    if state == "NY":
        nyc_names = {
            "fifth avenue",
            "grand central",
            "soho",
            "upper west side",
            "upper east side",
            "west 14th street",
            "world trade center"
        }

        if city in {
            "new york",
            "manhattan",
            "brooklyn",
            "bronx",
            "queens",
            "staten island"
        } or any(x in name for x in nyc_names):
            return 0.08875

        if city in {"buffalo", "cheektowaga"} or "walden galleria" in name:
            return 0.0875

        return None

    return None

def money_info(product, store):
    if product["price"] is None:
        return {"tax_rate": None, "tax_amount": None, "total": None,
                "price_eur": None, "tax_amount_eur": None, "total_eur": None,
                "fx_rate": None, "fx_date": None, "tax_included": False}
    if product["market"] in {"FR", "GB"}:
        # Consumer list prices provided by the user are presumed VAT-inclusive.
        # Itemized VAT is not calculated without verified product/invoice data.
        price = product["price"]
        rate, date = get_eur_rate(product["currency"])
        converted = round(price * rate, 2) if rate is not None else None
        return {"tax_rate": None, "tax_amount": None, "total": price,
                "price_eur": converted, "tax_amount_eur": None,
                "total_eur": converted, "fx_rate": rate, "fx_date": date,
                "tax_included": True}
    tax = CA_TAX_RATE if product["market"] == "CA" else us_tax_rate(store)
    if tax is None:
        return {"tax_rate":None,"tax_amount":None,"total":None,"price_eur":None,"tax_amount_eur":None,"total_eur":None,"fx_rate":None,"fx_date":None}
    price = product["price"]
    tax_amount = round(price * tax + 1e-9, 2); total = round(price + tax_amount + 1e-9, 2)
    rate, date = get_eur_rate(product["currency"])
    conv = lambda x: round(x * rate, 2) if rate is not None else None
    return {"tax_rate":tax,"tax_amount":tax_amount,"total":total,"price_eur":conv(price),"tax_amount_eur":conv(tax_amount),"total_eur":conv(total),"fx_rate":rate,"fx_date":date}

# ========================= APPLE =========================
def fetch_market(url, location, product_ids):
    params = {"pl":"true", "location":location}
    for i, pid in enumerate(product_ids):
        params[f"mts.{i}"] = "regular"
        params[f"parts.{i}"] = PRODUCTS[pid]["part"]
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=30)
    except requests.RequestException as exc:
        # HTTP client exception strings often include the complete request URL:
        # postal locations and monitored part numbers must not leak to logs,
        # dashboard errors or Discord notifications.
        raise RuntimeError(f"Apple connection failed ({type(exc).__name__})") from None
    if r.status_code in (429, 541): raise RuntimeError(f"APPLE_{r.status_code}")
    if r.status_code != 200: raise RuntimeError(f"Apple HTTP {r.status_code}")
    try: data = r.json()
    except Exception: raise RuntimeError("Apple returned invalid JSON")
    return (data.get("body") or {}).get("stores") or []

def status_from_availability(av):
    display = av.get("pickupDisplay")
    if not display: return "unknown"
    d = str(display).strip().lower()
    if d == "available": return "available"
    if d in {"unavailable","notavailable","not-available"}: return "unavailable"
    return "unknown"

def parse_item(raw, pid):
    product = PRODUCTS[pid]
    av = ((raw.get("partsAvailability") or {}).get(product["part"]) or {})
    item = {
        "key": f"{pid}:{raw.get('storeNumber')}", "product_id":pid, "market":product["market"],
        "productName":product["name"], "part":product["part"], "price":product["price"], "currency":product["currency"],
        "storeNumber":raw.get("storeNumber"), "storeName":raw.get("storeName"), "city":raw.get("city"), "state":raw.get("state"),
        "postalCode":((raw.get("address") or {}).get("postalCode") or raw.get("postalCode")),
        "distance":raw.get("storeDistanceWithUnit"), "pickupDisplay":av.get("pickupDisplay") or "unknown",
        "quote":av.get("pickupSearchQuote") or "Unknown", "status":status_from_availability(av),
    }
    item.update(money_info(product, item)); return item

def merge_area_results(existing, current):
    """Conflicting nearby-area observations must not cause a false notification."""
    if existing is None:
        return current
    if existing.get("quote") == "Conflicting results across monitoring areas":
        return existing
    old_status = existing["status"]
    new_status = current["status"]
    if old_status == new_status:
        return current
    if old_status == "unknown":
        return current
    if new_status == "unknown":
        return existing
    combined = dict(current)
    combined["status"] = "unknown"
    combined["pickupDisplay"] = "unknown"
    combined["quote"] = "Conflicting results across monitoring areas"
    return combined


def fetch_all():
    dedup = {}
    errors = [
        f"No monitoring area configured for {market}; its products were NOT checked"
        for market in uncovered_product_markets(PRODUCTS, MONITORING_AREAS)
    ]
    rate_limited = False
    for index, area in enumerate(MONITORING_AREAS):
        market = area["market"]
        product_ids = US_PRODUCT_IDS if market == "US" else CA_PRODUCT_IDS if market == "CA" else MARKET_PRODUCT_IDS.get(market, [])
        url = REGIONS[market].pickup_url
        if not product_ids:
            continue
        desired = set(area["store_ids"])
        baseline_stores = None
        for offset in range(0, len(product_ids), PRODUCT_BATCH_SIZE):
            batch_ids = product_ids[offset:offset + PRODUCT_BATCH_SIZE]
            matched_stores_in_batch = set()
            try:
                stores = fetch_market(url, area["location"], batch_ids)
                for raw in stores:
                    store_id = raw.get("storeNumber")
                    if not store_id or (desired and store_id not in desired):
                        continue
                    if market == "US" and ALLOWED_STATES and (raw.get("state") or "").upper() not in ALLOWED_STATES:
                        continue
                    matched_stores_in_batch.add(store_id)
                    for product_id in batch_ids:
                        item = parse_item(raw, product_id)
                        dedup[item["key"]] = merge_area_results(dedup.get(item["key"]), item)
            except Exception as exc:
                message = str(exc)
                errors.append(f'{area["id"]} batch {offset // PRODUCT_BATCH_SIZE + 1}: {message}')
                print(f'{area["id"]}: {message}', flush=True)
                if message in {"APPLE_429", "APPLE_541"}:
                    rate_limited = True
                break
            # Validate store coverage for each product batch. A successful
            # first batch cannot prove that later SKU batches were checked.
            if not matched_stores_in_batch:
                errors.append(
                    f'{area["id"]} batch {offset // PRODUCT_BATCH_SIZE + 1}: '
                    'no matching Apple Stores returned; availability unknown (selected variants not verified)'
                )
            elif desired - matched_stores_in_batch:
                errors.append(
                    f'{area["id"]} batch {offset // PRODUCT_BATCH_SIZE + 1}: '
                    'some selected Apple Stores were not returned; selected variants not fully verified'
                )
            # Without an explicit store filter, multiple SKU batches may
            # return different nearby stores. Treat the missing SKU/store
            # combinations as unknown coverage rather than a full negative.
            if baseline_stores is None:
                baseline_stores = matched_stores_in_batch
            elif not desired and matched_stores_in_batch != baseline_stores:
                errors.append(
                    f'{area["id"]} batch {offset // PRODUCT_BATCH_SIZE + 1}: '
                    'Apple Store coverage differs between SKU batches; availability partial'
                )
            if offset + PRODUCT_BATCH_SIZE < len(product_ids):
                time.sleep(random.uniform(2.0, 4.0))
        if rate_limited:
            break
        if index < len(MONITORING_AREAS) - 1:
            time.sleep(random.uniform(2.0, 4.0))

    if not dedup:
        if rate_limited:
            raise RuntimeError("APPLE_RATE_LIMIT_ALL")
        if errors:
            raise RuntimeError(" | ".join(errors))
        raise RuntimeError("No Apple stores returned")
    if rate_limited:
        errors.append("Apple 429/541 rate limit: remaining areas skipped, monitoring will slow down")

    status_order = {"available":0,"unavailable":1,"unknown":2}
    product_order = {pid: n for n, pid in enumerate(PRODUCTS)}
    def sk(x):
        priority = 0 if (x["market"]=="US" and x["storeNumber"]==US_PRIORITY_STORE) or (x["market"]=="CA" and x["storeNumber"]==CA_TARGET_STORE) else 1
        return (product_order[x["product_id"]], status_order.get(x["status"],3), priority, x["total"] if x["total"] is not None else 999999, x["storeName"] or "")
    items = sorted(dedup.values(), key=sk)
    return items, errors

# ========================= DISCORD =========================
def money_symbol(currency): return {"USD":"$","CAD":"$","EUR":"€","GBP":"£"}.get(currency, currency + " ")

def compact_product_name(item):
    return item["productName"]

def price_total_text(item):
    sym = money_symbol(item["currency"]); cur = item["currency"]
    if item.get("price") is None:
        return "Price not confirmed by Apple — check the product page"
    if item.get("total") is None:
        return f"{sym}{item['price']:,.2f} {cur} • total inconnu"
    eur = f" • €{item['total_eur']:,.2f}" if item.get("total_eur") is not None else ""
    return f"{sym}{item['total']:,.2f} {cur}{eur}"

def priority_store_embed(item, available=True):
    sym = money_symbol(item["currency"]); cur = item["currency"]
    if available:
        title = f"⭐ PRIORITY STORE — {compact_product_name(item)} DISPONIBLE"
        color = 0xF5A623
        description = "**PRIORITY STORE • verify local tax before purchase**"
    else:
        title = f"❌ PRIORITY STORE — {compact_product_name(item)} n’est plus disponible"
        color = 0xE74C3C
        description = "La cible prioritaire était disponible au cycle précédent."
    tax = "Inconnue" if item.get("tax_rate") is None else f"{item['tax_rate']*100:.3f}% • +{sym}{item['tax_amount']:,.2f}"
    return {
        "title": title, "description": description, "color": color,
        "fields": [
            {"name":"📍 Magasin","value":f"Apple {item['storeName']} — {item.get('city') or ''}, {item.get('state') or ''}","inline":False},
            {"name":"💵 Prix","value":f"{sym}{item['price']:,.2f} {cur}" if item.get("price") is not None else "Not confirmed", "inline":True},
            {"name":"🧾 Taxe","value":tax,"inline":True},
            {"name":"💳 Total","value":price_total_text(item),"inline":True},
            {"name":"📦 Retrait","value":item.get("quote") or item.get("pickupDisplay") or "—","inline":True},
            {"name":"🔎 SKU","value":f"`{item['part']}` • `{item['storeNumber']}`","inline":True},
        ],
        "footer":{"text":f"Apple Stock Watcher V{VERSION} • vérifie sur Apple avant de te déplacer"}
    }

def bounded_discord_description(items, formatter, separator="\n\n"):
    """Keep Discord embeds below their 4096-character description limit.

    A busy cycle can contain hundreds of SKU/store rows. The summary always
    counts ALL events, but displays only the first fitting examples. This is
    not an exactly-once delivery mechanism.
    """
    lines = []
    used = 0
    for item in items[:20]:
        line = str(formatter(item))
        if len(line) > 500:
            line = line[:499] + "…"
        increase = len(line) + (len(separator) if lines else 0)
        # Reserve space for the omitted-count line and Unicode characters.
        if used + increase > 3500:
            break
        lines.append(line)
        used += increase
    omitted = len(items) - len(lines)
    if omitted:
        lines.append(f"… et **{omitted}** autre(s) résultat(s).")
    return separator.join(lines)


def normal_available_embed(items):
    # One compact card per cycle, instead of one Discord message per store.
    def line(item):
        where = f"Apple {item['storeName']} — {item.get('city') or ''}, {item.get('state') or ''}"
        return f"🟢 **{compact_product_name(item)}** • {where}\n↳ **{price_total_text(item)}** • {item.get('quote') or 'Available'}"
    return {"title":f"🟢 {len(items)} nouvelle(s) disponibilité(s)",
            "description":bounded_discord_description(items, line),
            "color":0x2ECC71,
            "footer":{"text":f"Apple Stock Watcher V{VERSION} • non-priority stores"}}


def unavailable_embed(items):
    def line(item):
        return f"🔴 **{compact_product_name(item)}** • Apple {item['storeName']} — {item.get('city') or ''}, {item.get('state') or ''}"
    return {"title":f"🔴 {len(items)} stock(s) redevenu(s) indisponible(s)",
            "description":bounded_discord_description(items, line, separator="\n"),
            "color":0xE74C3C,
            "footer":{"text":"Transition confirmée AVAILABLE → UNAVAILABLE"}}

def is_alert_target(item):
    return (
        (ALERT_STORE_IDS is None or item.get("storeNumber") in ALERT_STORE_IDS)
        and (ALERT_PRODUCT_IDS is None or item.get("product_id") in ALERT_PRODUCT_IDS)
    )


def send_stock_changes(new_available, newly_unavailable):
    new_available = [x for x in new_available if is_alert_target(x)]
    newly_unavailable = [x for x in newly_unavailable if is_alert_target(x)]
    priority_up = [x for x in new_available if x.get("storeNumber") == US_PRIORITY_STORE and x.get("market") == "US"]
    normal_up = [x for x in new_available if x not in priority_up]
    priority_down = [x for x in newly_unavailable if x.get("storeNumber") == US_PRIORITY_STORE and x.get("market") == "US"]
    normal_down = [x for x in newly_unavailable if x not in priority_down]
    for item in priority_up: safe_discord(embeds=[priority_store_embed(item, True)])
    if normal_up: safe_discord(embeds=[normal_available_embed(normal_up)])
    for item in priority_down: safe_discord(embeds=[priority_store_embed(item, False)])
    if normal_down: safe_discord(embeds=[unavailable_embed(normal_down)])

# ========================= POLLING =========================
def poll_once():
    global latest
    checked = now(); previous = load_state()
    try:
        items, partial_errors = fetch_all()
        available = [x for x in items if x["status"] == "available"]
        previous_available = set(previous.get("available_keys") or [])
        # A partial scan can report "unavailable" at one store while another
        # regional/batched request failed. Never clear a previously available
        # key or send a stock-out alert until the entire cycle has succeeded.
        # Confirmed "available" observations can still be announced immediately.
        fully_verified = not partial_errors and all(x["status"] != "unknown" for x in items)
        seen = {x["key"]: x["status"] for x in items}
        current_available = {x["key"] for x in available} | {
            key for key in previous_available
            if not fully_verified or seen.get(key) in (None, "unknown")
        }
        new_available = [x for x in available if x["key"] not in previous_available]

        current_by_key = {x["key"]: x for x in items}
        newly_unavailable = []
        if fully_verified:
            for key in previous_available - current_available:
                item = current_by_key.get(key)
                if item and item.get("status") == "unavailable":
                    newly_unavailable.append(item)

        send_stock_changes(new_available, newly_unavailable)

        # A partial batch/region response is not a complete recovery from an
        # earlier outage. Do not send a misleading "restored" notification
        # until every configured area and selected SKU has been checked.
        was_in_error = previous.get("watcher_error") is True
        if was_in_error and fully_verified:
            safe_discord(f"✅ **Apple Stock Watcher V{VERSION} rétabli**\nLa surveillance fonctionne de nouveau.")
        save_state({
            "available_keys": sorted(current_available),
            "watcher_error": was_in_error and not fully_verified,
            "checked_at": checked,
        })
        changes = (
            [transition_event(item, "available", checked) for item in new_available]
            + [transition_event(item, "unavailable", checked) for item in newly_unavailable]
        )
        append_history(HISTORY_FILE, changes, max_entries=HISTORY_MAX_EVENTS)
        if partial_errors or any(x["status"] == "unknown" for x in items):
            overall = "partial"
        elif available:
            overall = "available"
        else:
            overall = "unavailable"
        with lock:
            latest = {"status":overall,"checked_at":checked,"items":items,"error":" | ".join(partial_errors) if partial_errors else None,"consecutive_errors":0}
        print(checked, f"{len(items)} product/store rows", f"{len(available)} available", ("PARTIAL" if partial_errors else "OK"), flush=True)
        if any(("APPLE_429" in err or "APPLE_541" in err or "Apple 429" in err or "Apple 541" in err) for err in partial_errors):
            return max(INTERVAL, 900)
        return INTERVAL
    except Exception as e:
        error = str(e)
        with lock: errors = latest.get("consecutive_errors",0)+1
        if previous.get("watcher_error") is not True:
            safe_discord(f"⚠️ **Apple Stock Watcher V{VERSION} en erreur**\nErreur : {error}\nLe statut est UNKNOWN — jamais interprété comme rupture.")
        save_state({"available_keys":previous.get("available_keys",[]),"watcher_error":True,"checked_at":checked,"error":error})
        with lock: latest = {"status":"unknown","checked_at":checked,"items":latest.get("items",[]),"error":error,"consecutive_errors":errors}
        print(checked,"UNKNOWN:",error,flush=True)
        if error in {"APPLE_429", "APPLE_541", "APPLE_RATE_LIMIT_ALL"}: return 900
        return min(900,max(INTERVAL,INTERVAL*errors))

def worker():
    while True:
        delay = poll_once(); time.sleep(max(120, delay + random.randint(-15,15)))

# ========================= WEB UI =========================
HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Apple Stock Watcher V{{version}}</title><style>

/* Apple-inspired dashboard skin */
:root{color-scheme:dark;--bg:#000000;--panel:#11151c;--panel2:#161b24;--line:#2b3442;--text:#f5f6fa;--muted:#9ba8bd;--green:#32d583;--red:#ff6475;--input:#151b25}
:root[data-theme="light"]{color-scheme:light;--bg:#f4f6fa;--panel:#fff;--panel2:#f7f9fc;--line:#dbe1e9;--text:#111827;--muted:#64748b;--green:#128a50;--red:#c83548;--input:#f9fafb}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;max-width:1550px;margin:0 auto;padding:28px;background:var(--bg);color:var(--text);min-height:100vh;transition:background .2s,color .2s}
.header{display:flex;justify-content:space-between;align-items:center;gap:14px;margin-bottom:22px}.header h1{font-size:clamp(25px,3vw,38px);letter-spacing:-.045em;margin:0 0 7px}.header .sub{color:var(--muted);margin:0;font-size:14px}.theme-toggle,.filter-btn{background:var(--panel);border:1px solid var(--line);border-radius:999px;color:var(--text);padding:11px 16px;font-size:14px;cursor:pointer;transition:border-color .2s,background .2s}.theme-toggle:hover,.filter-btn:hover{border-color:var(--muted)}.theme-toggle:focus-visible,.filter-btn:focus-visible,#shopSearch:focus-visible{outline:2px solid #83b4ff;outline-offset:2px}
.search-panel,.summary,.section,.activity-panel{background:var(--panel);border:1px solid var(--line);border-radius:20px;padding:20px;margin-bottom:18px;box-shadow:0 8px 30px #00000012}.search-panel{padding:14px 18px}.search-panel input,#shopSearch{display:block;width:100%;padding:14px 15px;font-size:16px;background:var(--input);border:1px solid var(--line);border-radius:13px;color:var(--text);outline:none}.search-panel input::placeholder{color:var(--muted)}#searchCount{font-size:12px;color:var(--muted);margin:9px 3px 0}.summary{line-height:1.8;color:var(--muted)}.summary b{color:var(--text)}.filters{display:flex;gap:9px;flex-wrap:wrap;margin:0 0 20px}.filter-btn.active{background:#273a53;border-color:#79aaff;color:#fff}:root[data-theme="light"] .filter-btn.active{background:#e5f0ff;color:#174b9b}
.section{padding:22px}.section h2,.activity-panel h2{font-size:clamp(19px,2vw,26px);letter-spacing:-.035em;margin:0 0 8px}.meta{font-size:13px;color:var(--muted);margin-bottom:18px;line-height:1.7}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.card{min-width:0;background:var(--panel2);border:1px solid var(--line);border-radius:16px;padding:18px;transition:transform .15s,border-color .15s}.card:hover{transform:translateY(-2px)}.card.available{border-color:var(--green);background:linear-gradient(145deg,rgba(30,160,100,.11),var(--panel2) 65%)}.card.unavailable{border-color:var(--red);background:linear-gradient(145deg,rgba(215,60,80,.08),var(--panel2) 65%)}.card.unknown{border-color:var(--line)}.card.target{box-shadow:inset 0 0 0 1px #e5b74b}.name{font-weight:700;font-size:17px;margin-bottom:7px}.card .badge{display:inline-block;border-radius:999px;padding:5px 10px;margin:11px 0;font-weight:700;font-size:11px;letter-spacing:.035em}.available .badge{background:rgba(50,213,131,.14);color:var(--green)}.unavailable .badge{background:rgba(255,100,117,.13);color:var(--red)}.unknown .badge{background:rgba(148,163,184,.16);color:var(--muted)}.card .money{line-height:1.7;font-size:14px;margin-top:10px}.card .sku{font-size:12px;color:var(--muted);overflow-wrap:anywhere}.card>div:nth-child(2){color:var(--muted);font-size:13px}.error{color:var(--red);font-weight:650}.empty-search{display:none;text-align:center;color:var(--muted);padding:28px 12px}.empty-search.visible{display:block}
@media(max-width:950px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:650px){body{padding:14px}.header{align-items:flex-start}.header h1{font-size:25px}.theme-toggle{padding:9px 11px;font-size:12px}.grid{grid-template-columns:1fr}.section,.summary{padding:16px}.search-panel{padding:12px}}

.model-head{display:flex;gap:12px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap}
.model-status{border:1px solid var(--line);padding:7px 12px;border-radius:999px;font-size:12px;font-weight:650;max-width:100%}
.model-status.available{color:var(--green);border-color:var(--green)}
.model-status.unavailable{color:var(--red);border-color:var(--red)}
.model-status.partial,.model-status.unknown{color:var(--muted)}
.model-note{color:var(--muted);font-size:12px;margin:12px 0}
.variant-details{border-top:1px solid var(--line);margin:15px 0 0;padding:12px 0 0;color:var(--muted);font-size:13px}
.variant-details summary{cursor:pointer;color:var(--text);font-weight:600}
.variant-details ul{padding-left:21px;margin-bottom:0}
.variant-details li{padding:4px 0;overflow-wrap:anywhere}
.store-variant-list{margin:8px 0 0;padding:0;list-style:none}
.store-variant-list li{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;border-top:1px solid var(--line);padding:9px 0}
.variant-availability{font-weight:650;font-size:12px}
.variant-availability.available{color:var(--green)}.variant-availability.unavailable{color:var(--red)}.variant-availability.unknown{color:var(--muted)}
.coverage-notice{margin:10px 0;padding:11px 13px;background:var(--panel2);border:1px solid var(--line);border-radius:12px;color:var(--muted);font-size:13px}
.store-meta{font-size:12px;color:var(--muted)}
.activity-event{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:11px 0;border-top:1px solid var(--line);font-size:13px}.activity-event small{color:var(--muted);margin-left:auto}.activity-status{display:inline-block;padding:5px 9px;border-radius:10px;font-size:11px;font-weight:700}.activity-status.available{background:rgba(50,213,131,.14);color:var(--green)}.activity-status.unavailable{background:rgba(255,100,117,.13);color:var(--red)}
</style></head><body><header class="header"><div><h1> Apple Stock Watcher V{{version}}</h1><p class="sub">{{products|length}} configured products • selected regions pickup availability • dashboard refresh 30 s</p></div><button type="button" id="themeToggle" class="theme-toggle" aria-label="Changer le thème">☀ Mode clair</button></header>

<div class="search-panel">
    <input id="shopSearch" type="search"
           placeholder="Rechercher un modèle, Apple Store, une ville..."
           aria-label="Rechercher un Apple Store"
           autocomplete="off">
    <div id="searchCount"></div>
</div>
<div class="summary"><b>Global:</b> <span class="overall-{{latest.status|e}}">{{latest.status|upper}}</span>
&nbsp; • &nbsp; <b>Dernier check:</b>
{% if latest.checked_at %}<time class="local-datetime" datetime="{{latest.checked_at|e}}">{{latest.checked_at}}</time>{% else %}—{% endif %}
&nbsp; • &nbsp; <b>Intervalle:</b> ~{{interval}} s
{% if latest.error %}<div class="error">⚠ {{latest.error}}</div>{% endif %}
{% if uncovered_markets %}<div class="coverage-notice">Zones manquantes : {{uncovered_markets|join(', ')}}. Les produits de ces pays ne sont pas vérifiés et ne doivent pas être considérés comme indisponibles.</div>{% endif %}
</div>
<div class="activity-panel">
<h2>Recent stock changes</h2>
<p class="meta">Observed availability changes, including first-run availability. Latest events first.</p>
{% if history %}
<div class="activity-events">
{% for e in history %}
<div class="activity-event">
<span class="activity-status {{e.type}}">{{'IN STOCK' if e.type=='available' else 'SOLD OUT'}}</span>
<span>{{e.product or e.product_id}} · Apple {{e.store or e.store_id}}{% if e.city %}, {{e.city}}{% endif %}</span>
<small>{{e.at}}</small>
</div>
{% endfor %}
</div>
{% else %}<div class="meta">No stock changes recorded yet. Monitoring will populate this automatically.</div>{% endif %}
</div>
<div class="filters" aria-label="Filtrer les disponibilités"><button type="button" class="filter-btn active" data-filter="all" aria-pressed="true">Tous</button><button type="button" class="filter-btn" data-filter="available" aria-pressed="false">● Disponibles</button><button type="button" class="filter-btn" data-filter="unavailable" aria-pressed="false">● En rupture</button><button type="button" class="filter-btn" data-filter="unknown" aria-pressed="false">● Inconnus</button><button type="button" class="filter-btn" data-filter="priority" aria-pressed="false">★ Prioritaires</button></div>
<div id="emptySearch" class="empty-search">Aucun magasin confirmé ne correspond aux filtres. Les zones inconnues ne sont pas des ruptures de stock.</div>
{% for group in groups %}
<section class="section" data-model="{{group.id|e}}">
  <div class="model-head">
    <div>
      <h2>{{ {'US':'🇺🇸','CA':'🇨🇦','FR':'🇫🇷','GB':'🇬🇧'}.get(group.market,'🌍') }} {{group.title}}</h2>
      <div class="meta">{{group.market}} · {{group.variant_count}} selected variant{{'s' if group.variant_count != 1 else ''}}
      {% if group.colors %} · {{group.colors|join(', ')}}{% endif %}
      {% if group.storages %} · {{group.storages|join(', ')}}{% endif %}</div>
    </div>
    <span class="model-status {{group.status}}">{{group.status_label}}</span>
  </div>
  {% if not group.reliable %}
    <div class="coverage-notice">No current verified availability. The watcher may be starting, paused or experiencing an error. Previous results are not shown as confirmed stock.</div>
  {% elif group.partial %}
    <div class="coverage-notice">Partial verification: some stores, products or areas may be missing. Missing results do not mean out of stock.</div>
  {% endif %}
  <div class="grid">
  {% for store in group.stores %}
    <article class="card {{store.status}} {% if store.id in [priority_us, target_ca] %}target{% endif %}"
       data-search="{{ (group.title ~ ' ' ~ store.name ~ ' ' ~ store.city ~ ' ' ~ store.state ~ ' ' ~ store.id)|lower|e }}">
      <div class="name">Apple {{store.name}}</div>
      <div class="store-meta">{{store.city}}{% if store.state %}, {{store.state}}{% endif %} · {{store.id}}</div>
      <div class="badge">{{store.status_label}}</div>
      <div class="store-meta">{{store.available}} available · {{store.unavailable}} unavailable · {{store.unknown}} unknown</div>
      <details class="variant-details">
        <summary>See {{store.variants|length}} selected variants</summary>
        <ul class="store-variant-list">
        {% for v in store.variants %}
          <li>
            <span><b>{{v.label}}</b><br><small>{{v.part}}</small></span>
            <span class="variant-availability {{v.status}}">{{v.status|upper}}
            {% if v.price is not none %}<br><small>{{money_symbol(v.currency)}}{{'%.2f'|format(v.price)}} {{v.currency}}</small>{% else %}<br><small>Price unconfirmed</small>{% endif %}
            </span>
          </li>
        {% endfor %}
        </ul>
      </details>
    </article>
  {% else %}
    <div class="card unknown" data-search="{{ (group.title ~ ' ' ~ group.market ~ ' unknown missing location')|lower|e }}">
      <div class="name">No confirmed store observations</div>
      <div class="badge">UNKNOWN — not a stock-out</div>
      <p class="store-meta">No verified results for this model in the chosen monitoring areas.</p>
    </div>
  {% endfor %}
  </div>
  <details class="variant-details">
    <summary>Show configured model variants ({{group.variant_count}})</summary>
    <ul>{% for v in group.variants %}
      <li>{{v.label}} · {{v.part}}{% if v.carrier %} · {{v.carrier}}{% endif %}</li>
    {% endfor %}</ul>
  </details>
</section>
{% endfor %}


<script id="watcher-redesign-js">
(function(){
 const root=document.documentElement;
 const themeButton=document.getElementById('themeToggle');
 function applyTheme(theme){root.dataset.theme=theme;themeButton.textContent=theme==='dark'?'☀ Mode clair':'☾ Mode sombre';try{localStorage.setItem('watcher-theme',theme)}catch(e){}}
 let theme='dark';try{theme=localStorage.getItem('watcher-theme')||'dark'}catch(e){}
 applyTheme(theme);
 themeButton.addEventListener('click',()=>applyTheme(root.dataset.theme==='dark'?'light':'dark'));
 const input=document.getElementById('shopSearch');
 const count=document.getElementById('searchCount');
 const buttons=[...document.querySelectorAll('.filter-btn')];
 const sections=[...document.querySelectorAll('.section')];
 const empty=document.getElementById('emptySearch');
 let filter='all';
 function update(){
   const q=(input?.value||'').trim().toLocaleLowerCase();let shown=0,total=0;
   sections.forEach(section=>{
     let sectionVisible=0;
     section.querySelectorAll('.card[data-search]').forEach(card=>{
       total++;
       const matchesText=!q||(card.dataset.search||'').toLocaleLowerCase().includes(q);
       const matchesFilter=filter==='all'||(filter==='priority'?card.classList.contains('target'):card.classList.contains(filter));
       const show=matchesText&&matchesFilter;card.style.display=show?'':'none';
       if(show){shown++;sectionVisible++}
     });
     section.style.display=sectionVisible?'':'none';
   });
   if(count)count.textContent=shown+' carte(s) affichée(s) sur '+total+' (magasins vérifiés et zones inconnues)';
   if(empty)empty.classList.toggle('visible',shown===0);
 }
 if(input){try{input.value=sessionStorage.getItem('watcher-search')||''}catch(e){}input.addEventListener('input',()=>{try{sessionStorage.setItem('watcher-search',input.value)}catch(e){}update()})}
 buttons.forEach(btn=>btn.addEventListener('click',()=>{filter=btn.dataset.filter;buttons.forEach(b=>{b.classList.toggle('active',b===btn);b.setAttribute('aria-pressed',String(b===btn))});update()}));
 update();
 // Localize shown times without changing canonical UTC timestamps.
 document.querySelectorAll('time.local-datetime').forEach(node=>{
   const date=new Date(node.getAttribute('datetime'));
   if(!Number.isNaN(date.getTime())){
     node.textContent=date.toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'});
     node.title=node.getAttribute('datetime');
   }
 });
 // Keep 30-second refresh without losing search or theme.
 setInterval(()=>window.location.reload(),30000);
})();
</script>
</body></html>'''

@app.route("/")
def home():
    with lock: snap = dict(latest); snap["items"] = list(latest.get("items",[]))
    groups = build_model_groups(
        PRODUCTS, snap["items"], scan_status=snap.get("status", "starting"),
        checked_at=snap.get("checked_at"), monitoring_areas=MONITORING_AREAS,
    )
    return render_template_string(
        HTML, latest=snap, groups=groups, products=PRODUCTS, interval=INTERVAL, version=VERSION,
        priority_us=US_PRIORITY_STORE, target_ca=CA_TARGET_STORE,
        history=read_history(HISTORY_FILE, limit=20), money_symbol=money_symbol,
        uncovered_markets=uncovered_product_markets(PRODUCTS, MONITORING_AREAS),
    )

@app.route("/api/status")
def api_status():
    with lock: return jsonify(latest)

@app.route("/api/history")
def api_history():
    return jsonify({"events": read_history(HISTORY_FILE, limit=100)})

@app.route("/health")
def health(): return jsonify({"ok":True,"version":VERSION})

def dashboard_bind_host(environ=None):
    """Default to localhost: this dashboard has no user authentication."""
    config = os.environ if environ is None else environ
    return config.get("WATCHER_HOST") or "127.0.0.1"


if __name__ == "__main__":
    threading.Thread(target=worker, daemon=True).start()
    port = int(os.getenv("PORT","8080"))
    app.run(host=dashboard_bind_host(), port=port, debug=False, use_reloader=False)
