"""Read-only Apple product-family SKU discovery with conservative request limits.

Uses public Apple buy pages, no account credentials, no third-party catalog
and no guessed SKU mappings. The page format is undocumented and may change.
"""
import math
import re
import threading
import time

import requests

from regions import region_for


# A deliberately small allowlist; new families must be manually verified.
FAMILIES = {
    "iphone-18-pro": ("iPhone", "iPhone 18 Pro"),
    "iphone-17": ("iPhone", "iPhone 17"),
    "iphone-air": ("iPhone", "iPhone Air"),
    "ipad-pro": ("iPad", "iPad Pro"),
    "ipad-air": ("iPad", "iPad Air"),
    "macbook-air": ("Mac", "MacBook Air"),
    "macbook-pro": ("Mac", "MacBook Pro"),
    "mac-mini": ("Mac", "Mac mini"),
    "apple-watch": ("Watch", "Apple Watch"),
    "apple-watch-ultra": ("Watch", "Apple Watch Ultra"),
}
CATEGORY_PATH = {"iPhone": "buy-iphone", "iPad": "buy-ipad", "Mac": "buy-mac", "Watch": "buy-watch"}
MARKET_PREFIX = {"US": "", "CA": "/ca", "FR": "/fr", "GB": "/uk"}
SKU_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,19}/[A-Za-z0-9]{1,6}$")
DATA_KEY = re.compile(rb'(?<![A-Za-z0-9_$])["\x27]?productSelectionData["\x27]?\s*:\s*\{')
MAX_HTML_BYTES = 7_000_000
MAX_RESULTS = 180
CACHE_SECONDS = 6 * 3600
MIN_REQUEST_GAP_SECONDS = 120
RATE_LIMIT_GAP_SECONDS = 900
_cache = {}
_lock = threading.Lock()
_next_request = 0.0


class CatalogError(RuntimeError):
    pass


def catalog_url(market, family, experimental=False):
    """Construct URL from fixed allowlists; never accept an arbitrary fetch URL."""
    if family not in FAMILIES:
        raise CatalogError("Unsupported product family")
    try:
        region_for(market, experimental)
    except ValueError as exc:
        raise CatalogError(str(exc)) from exc
    category = FAMILIES[family][0]
    path = CATEGORY_PATH[category]
    return f"https://www.apple.com{MARKET_PREFIX[market]}/shop/{path}/{family}"


def _extract_json_object(page, start):
    """Balance JSON braces without mistaking escaped quotes or nested objects."""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(page)):
        char = page[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == 92:
                escaped = True
            elif char == 34:
                in_string = False
        elif char == 34:
            in_string = True
        elif char == 123:
            depth += 1
        elif char == 125:
            depth -= 1
            if depth == 0:
                return page[start:index + 1]
        if depth < 0:
            return None
    return None


def _selection_data(page):
    import json

    # Prefer the live bootstrap over similarly named historical state elsewhere.
    marker = page.find(b"PRODUCT_SELECTION_BOOTSTRAP")
    candidates = (page[marker:] if marker >= 0 else page,)
    for search in candidates:
        for match in DATA_KEY.finditer(search):
            opening = match.end() - 1
            blob = _extract_json_object(search, opening)
            if not blob:
                continue
            try:
                data = json.loads(blob)
            except (UnicodeDecodeError, ValueError):
                continue
            if isinstance(data, dict) and isinstance(data.get("products"), list):
                return data
    raise CatalogError("Apple did not expose a recognizable current product catalog on this page")


def _humanize(text):
    if not isinstance(text, str):
        return ""
    text = text.replace("_", " ").replace("-", " ").strip()
    return re.sub(r"\s+", " ", text).title()


def parse_catalog_html(page, market, family):
    """Parse current Apple selection data and return only explicitly listed SKUs.

    The parser intentionally leaves price null when Apple does not include an
    unambiguous numerical price for that exact part.
    """
    if family not in FAMILIES or market not in MARKET_PREFIX:
        raise CatalogError("Unsupported catalog market or product family")
    if not isinstance(page, bytes) or len(page) > MAX_HTML_BYTES:
        raise CatalogError("Invalid or oversized catalog page")
    data = _selection_data(page)
    category, title = FAMILIES[family]
    currency = {"US": "USD", "CA": "CAD", "FR": "EUR", "GB": "GBP"}[market]
    result = {}
    for raw in data["products"]:
        if not isinstance(raw, dict):
            continue
        sku = raw.get("partNumber")
        if not isinstance(sku, str) or not SKU_RE.fullmatch(sku):
            continue
        # Many phone pages repeat the same part per carrier; deduplicate.
        if sku in result:
            continue
        details = []
        for dimension in (
            "dimensionScreensize", "dimensionCapacity", "dimensionColor",
            "dimensionMemory", "dimensionStorage", "dimensionChip",
            "dimensionConnectivity", "dimensionCaseSize",
        ):
            val = _humanize(raw.get(dimension))
            if val:
                details.append(val)
        model_title = (
            "iPhone 18 Pro Max"
            if family == "iphone-18-pro" and raw.get("familyType") == "iphone18promax"
            else title
        )
        label = " ".join([model_title, *details]).strip()
        # A genuine per-product plain numeric fullPrice may be missing; never infer it.
        price = None
        candidate_price = raw.get("price")
        if isinstance(candidate_price, dict):
            candidate_price = candidate_price.get("fullPrice")
        if (isinstance(candidate_price, (int, float))
                and not isinstance(candidate_price, bool)
                and math.isfinite(candidate_price)
                and 0 < candidate_price <= 100000):
            price = round(float(candidate_price), 2)
        result[sku] = {
            "part": sku,
            "name": label[:100],
            "price": price,
            "currency": currency,
            "market": market,
            "category": category,
            "family": family,
            "family_type": raw.get("familyType") if isinstance(raw.get("familyType"), str) else None,
        }
        if len(result) > MAX_RESULTS:
            raise CatalogError("Apple returned too many SKU variants to safely catalogue; refusing an incomplete list")
    if not result:
        raise CatalogError("No recognizable part numbers found; Apple may have changed the catalog format")
    return sorted(result.values(), key=lambda item: (item["name"], item["part"]))


def fetch_catalog(market, family, experimental=False, requester=None, clock=None):
    """One bounded HTTP request, cached for six hours and throttled on errors.

    Designed for human-triggered local wizard lookups, not periodic bulk scans.
    """
    global _next_request
    url = catalog_url(market, family, experimental)
    now = clock() if clock else time.monotonic()
    key = (market, family)
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit["at"] < CACHE_SECONDS:
            return dict(hit["response"], cached=True)
        if now < _next_request:
            raise CatalogError("Catalog request cooldown active; retry later (Apple rate-limit protection)")
        _next_request = now + MIN_REQUEST_GAP_SECONDS

    response = None
    try:
        fetch = requester or requests.get
        response = fetch(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; AppleStockWatcher/1.0)",
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=(5, 25),
            stream=True,
            allow_redirects=False,
        )
        if response.status_code in (429, 541):
            with _lock:
                _next_request = max(_next_request, now + RATE_LIMIT_GAP_SECONDS)
            raise CatalogError(f"Apple rejected catalog request (HTTP {response.status_code}); paused for 15 minutes")
        if response.status_code != 200:
            raise CatalogError(f"Apple catalog returned HTTP {response.status_code}")
        size = 0
        chunks = []
        for chunk in response.iter_content(chunk_size=65536):
            if not chunk:
                continue
            size += len(chunk)
            if size > MAX_HTML_BYTES:
                raise CatalogError("Apple catalog page exceeds safe size limit")
            chunks.append(chunk)
        items = parse_catalog_html(b"".join(chunks), market, family)
        payload = {"items": items, "source_url": url, "market": market, "family": family}
        with _lock:
            _cache[key] = {"at": now, "response": payload}
        return dict(payload, cached=False)
    except requests.RequestException as exc:
        raise CatalogError(f"Apple catalog network error: {type(exc).__name__}") from exc
    finally:
        if response is not None:
            response.close()
