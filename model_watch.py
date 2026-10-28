"""Product-model subscriptions resolved to verifiable regional Apple SKUs.

The model picker selects all discovered variants for a model and region. SKU
discovery occurs when the user adds the model; no inventory scan is triggered.
"""
from math import ceil

MODELS = {
    "iphone-18-pro": ("iPhone 18 Pro", "iphone-18-pro", "iphone18pro"),
    "iphone-18-pro-max": ("iPhone 18 Pro Max", "iphone-18-pro", "iphone18promax"),
    "iphone-17": ("iPhone 17", "iphone-17", None),
    "iphone-air": ("iPhone Air", "iphone-air", None),
    "ipad-pro": ("iPad Pro", "ipad-pro", None),
    "ipad-air": ("iPad Air", "ipad-air", None),
    "macbook-air": ("MacBook Air", "macbook-air", None),
    "macbook-pro": ("MacBook Pro", "macbook-pro", None),
    "mac-mini": ("Mac mini", "mac-mini", None),
    "apple-watch": ("Apple Watch", "apple-watch", None),
    "apple-watch-ultra": ("Apple Watch Ultra", "apple-watch-ultra", None),
}
MAX_SKUS_PER_MODEL = 48
MAX_PRODUCTS = 96
PRODUCT_BATCH_SIZE = 12
MAX_REQUESTS_PER_SCAN = 24


class ModelSelectionError(ValueError):
    pass


def family_for(model_id):
    if model_id not in MODELS:
        raise ModelSelectionError("Unknown Apple product model")
    return MODELS[model_id][1]


def expand_model(model_id, market, catalog_rows):
    """Return all *observed* SKU variants of the exact model, never guessed ones."""
    family_for(model_id)
    family_type = MODELS[model_id][2]
    seen = set()
    results = []
    for item in catalog_rows:
        if item.get("market") != market or item.get("family") != MODELS[model_id][1]:
            continue
        if family_type and item.get("family_type") != family_type:
            continue
        sku = item.get("part")
        if not sku or sku in seen:
            continue
        seen.add(sku)
        results.append({
            "market": market,
            "name": item["name"],
            "part": sku,
            "price": item.get("price"),
            "currency": item["currency"],
            "watch_model": model_id,
        })
    if not results:
        raise ModelSelectionError(
            "No matching Apple SKUs found for this model. Try the manual SKU option; "
            "the current Apple catalogue may be incomplete."
        )
    if len(results) > MAX_SKUS_PER_MODEL:
        raise ModelSelectionError(
            f"Apple returned {len(results)} variants, above the {MAX_SKUS_PER_MODEL}-SKU "
            "automatic model limit. Narrow the model or use advanced selection."
        )
    return sorted(results, key=lambda item: (item["name"], item["part"]))


def model_catalog_result(model_id, market, catalog_rows):
    variants = expand_model(model_id, market, catalog_rows)
    return {
        "model_id": model_id,
        "model_name": MODELS[model_id][0],
        "market": market,
        "products": variants,
        "count": len(variants),
        "missing_prices": sum(item["price"] is None for item in variants),
    }


def expected_requests(products, areas):
    """Conservative upper estimate: one request per 12 distinct SKU/market pairs."""
    if not isinstance(products, dict) or not isinstance(areas, list):
        raise ModelSelectionError("Invalid product or area selection")
    unique = {}
    for product in products.values():
        market = product.get("market")
        sku = product.get("part")
        if not isinstance(market, str) or not isinstance(sku, str):
            raise ModelSelectionError("Invalid product in request budget")
        unique.setdefault(market, set()).add(sku)
    return sum(ceil(len(unique.get(area.get("market"), set())) / PRODUCT_BATCH_SIZE) for area in areas)


def validate_request_budget(products, areas):
    if len(products) > MAX_PRODUCTS:
        raise ModelSelectionError(
            f"Up to {MAX_PRODUCTS} variant SKUs can be monitored per configuration"
        )
    cost = expected_requests(products, areas)
    if cost > MAX_REQUESTS_PER_SCAN:
        raise ModelSelectionError(
            f"Too many monitoring combinations: {cost} requests per scan "
            f"(safe limit: {MAX_REQUESTS_PER_SCAN}). Reduce models or search areas."
        )
    return cost
