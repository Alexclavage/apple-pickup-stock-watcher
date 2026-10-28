"""Present configured Apple products as model-centric store availability groups.

Pure and read-only: all availability is derived from the latest already collected
pickup observations. This module does not call Apple or mutate saved watcher state.
"""
from collections import OrderedDict

from model_watch import MODELS

STATUS_CLASSES = {"available", "unavailable", "unknown", "partial"}


def _display_variant(product):
    parts = [product.get("storage"), product.get("color")]
    if not any(parts):
        return product.get("name") or product.get("part") or "Apple product"
    return " · ".join(str(x) for x in parts if x)


def build_model_groups(products, observations, scan_status="starting", checked_at=None):
    """Group a SKU list by market and model, with one availability row per store.

    Safety rules:
    - A missing SKU in an observed store is UNKNOWN, not sold out.
    - A failed/never-started scan is UNKNOWN even if the snapshot has stale rows.
    - A partial scan never yields an unqualified model-wide 'unavailable'.
    - No store list claims exhaustive geographic coverage.
    """
    buckets = OrderedDict()
    product_to_bucket = {}
    for product_id, product in products.items():
        market = product.get("market", "")
        model_id = product.get("watch_model")
        if model_id in MODELS:
            identity = (market, "model", model_id)
            title = MODELS[model_id][0]
        else:
            identity = (market, "sku", product_id)
            title = product.get("name") or product_id
        if identity not in buckets:
            buckets[identity] = {
                "id": f"{market}:{identity[1]}:{identity[2]}",
                "model_id": model_id if model_id in MODELS else None,
                "title": title,
                "market": market,
                "variants": [],
                "stores": [],
                "available_stores": 0,
                "checked_stores": 0,
                "status": "unknown",
                "status_label": "Awaiting check",
                "checked_at": checked_at,
                "partial": False,
                "reliable": False,
            }
        buckets[identity]["variants"].append({
            "product_id": product_id,
            "name": product.get("name") or product_id,
            "label": _display_variant(product),
            "storage": product.get("storage"),
            "color": product.get("color"),
            "carrier": product.get("carrier"),
            "part": product.get("part"),
            "currency": product.get("currency"),
            "price": product.get("price"),
        })
        product_to_bucket[product_id] = identity

    # An error snapshot can still contain previously obtained rows. Those
    # observations must not be shown as current confirmed availability.
    fresh = bool(checked_at) and scan_status in {"available", "unavailable", "partial"}
    by_store = {key: OrderedDict() for key in buckets}
    if fresh:
        for row in observations or []:
            identity = product_to_bucket.get(row.get("product_id"))
            if identity is None:
                continue
            store_id = row.get("storeNumber")
            if not store_id:
                continue
            store_key = (row.get("market"), str(store_id))
            stores = by_store[identity]
            if store_key not in stores:
                stores[store_key] = {
                    "id": str(store_id),
                    "name": str(row.get("storeName") or store_id),
                    "city": str(row.get("city") or ""),
                    "state": str(row.get("state") or ""),
                    "postal_code": row.get("postalCode") or "",
                    "items": {},
                }
            stores[store_key]["items"][row["product_id"]] = row

    results = []
    for identity, group in buckets.items():
        stores = by_store[identity]
        total = len(group["variants"])
        has_unknown = False
        for store in stores.values():
            entries = []
            for variant in group["variants"]:
                row = store["items"].get(variant["product_id"])
                status = row.get("status", "unknown") if row else "unknown"
                if status not in {"available", "unavailable"}:
                    status = "unknown"
                    has_unknown = True
                entries.append({
                    **variant,
                    "status": status,
                    "quote": str(row.get("quote") or "") if row else "Not returned in this check",
                    "price": row.get("price", variant["price"]) if row else variant["price"],
                    "total": row.get("total") if row else None,
                    "total_eur": row.get("total_eur") if row else None,
                })
            available_count = sum(x["status"] == "available" for x in entries)
            unavailable_count = sum(x["status"] == "unavailable" for x in entries)
            unknown_count = total - available_count - unavailable_count
            if available_count:
                state = "available"
                label = f"{available_count} available variant{'s' if available_count != 1 else ''}"
            elif unknown_count:
                state = "unknown"
                label = "Availability incomplete"
            else:
                state = "unavailable"
                label = "No selected variants available in this store"
            group["stores"].append({
                "id": store["id"],
                "name": store["name"],
                "city": store["city"],
                "state": store["state"],
                "postal_code": store["postal_code"],
                "status": state,
                "status_label": label,
                "available": available_count,
                "unavailable": unavailable_count,
                "unknown": unknown_count,
                "variants": entries,
            })
        group["variant_count"] = len(group["variants"])
        group["colors"] = sorted({v["color"] for v in group["variants"] if v["color"]})
        group["storages"] = sorted({v["storage"] for v in group["variants"] if v["storage"]})
        group["checked_stores"] = len(group["stores"])
        group["available_stores"] = sum(store["available"] > 0 for store in group["stores"])
        group["reliable"] = fresh
        group["partial"] = scan_status == "partial" or has_unknown
        if not fresh:
            group["status"] = "unknown"
            group["status_label"] = "No current confirmed check"
        elif group["partial"]:
            group["status"] = "partial"
            group["status_label"] = (
                f"{group['available_stores']} stores with confirmed stock; coverage partial"
                if group["available_stores"] else "Verification incomplete"
            )
        elif group["available_stores"]:
            group["status"] = "available"
            group["status_label"] = f"{group['available_stores']} stores with selected variants available"
        elif group["checked_stores"]:
            group["status"] = "unavailable"
            group["status_label"] = "No selected variants in checked stores"
        else:
            group["status"] = "unknown"
            group["status_label"] = "No stores returned"
        group["stores"].sort(key=lambda store: (
            {"available": 0, "unknown": 1, "unavailable": 2}[store["status"]],
            store["name"].casefold(),
            store["id"],
        ))
        results.append(group)
    return results
