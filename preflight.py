"""Safe, read-only configuration preflight for Apple Stock Watcher.

No Apple catalog/pickup requests, Discord messages, file writes or worker
threads. Imports app.py to reuse its exact runtime configuration validation;
app.py starts the background worker only when executed as __main__.
"""
import argparse
from collections import Counter
import json
from math import ceil


def make_report(products, areas, config_exists, request_budget, interval,
                discord_configured=False, discord_disabled=False, batch_size=12):
    """Return only non-sensitive readiness metadata (never locations or SKUs)."""
    product_counts = Counter(product["market"] for product in products.values())
    area_counts = Counter(area["market"] for area in areas)
    all_markets = sorted(set(product_counts) | set(area_counts))
    countries = []
    for market in all_markets:
        n = product_counts[market]
        count = area_counts[market]
        countries.append({
            "market": market,
            "products": n,
            "areas": count,
            "requests_per_cycle": ceil(n / batch_size) * count,
        })
    issues = []
    notes = []
    if not config_exists:
        issues.append("No private config.json loaded; watcher would use built-in sample defaults")
    missing = sorted(market for market in product_counts if not area_counts[market])
    if missing:
        issues.append(
            "No monitoring area for configured products in: " + ", ".join(missing)
        )
    duplicates = sum(
        count - 1 for count in
        Counter((p["market"], p["part"]) for p in products.values()).values()
        if count > 1
    )
    if duplicates:
        notes.append(
            f"{duplicates} duplicate SKU entry/entries; each product ID consumes an Apple request slot"
        )
    if set(product_counts) & {"FR", "GB"}:
        notes.append("France/UK pickup support is experimental and needs live validation")
    notes.append("SKU identity and actual Apple pickup availability are NOT verified offline")
    return {
        "ready": not issues,
        "private_config": bool(config_exists),
        "markets": countries,
        "products": len(products),
        "areas": len(areas),
        "requests_per_cycle": request_budget,
        "interval_seconds": interval,
        "discord_mode": (
            "disabled for local testing" if discord_disabled
            else "configured; may send real messages" if discord_configured
            else "no webhook configured"
        ),
        "issues": issues,
        "notes": notes,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check monitoring configuration offline without contacting Apple or Discord"
    )
    parser.add_argument("--json", action="store_true", help="Output a sanitized JSON report")
    args = parser.parse_args(argv)
    try:
        import app as watcher  # Does not launch the watcher or make HTTP calls.
    except Exception as exc:
        # Avoid printing potentially secret local configuration content.
        print(
            f"ERROR: cannot load watcher settings ({type(exc).__name__}). "
            "Check config.json and environment settings."
        )
        return 2

    report = make_report(
        products=watcher.PRODUCTS,
        areas=watcher.MONITORING_AREAS,
        config_exists=watcher.CONFIG_PATH.is_file(),
        request_budget=watcher.REQUESTS_PER_SCAN,
        interval=watcher.INTERVAL,
        discord_configured=bool(watcher.DISCORD_WEBHOOK),
        discord_disabled=watcher.WATCHER_DISABLE_DISCORD,
        batch_size=watcher.PRODUCT_BATCH_SIZE,
    )
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("Apple Stock Watcher — OFFLINE preflight (no requests sent)")
        print("Status:", "READY for a controlled live check" if report["ready"] else "NEEDS ATTENTION")
        print(f"Products: {report['products']} | monitoring areas: {report['areas']}")
        for market in report["markets"]:
            print(
                f"  {market['market']}: {market['products']} products, "
                f"{market['areas']} areas, ~{market['requests_per_cycle']} requests/cycle"
            )
        print(
            f"Total estimated Apple requests/cycle: {report['requests_per_cycle']} "
            f"| minimum interval: {report['interval_seconds']} seconds"
        )
        print("Discord:", report["discord_mode"])
        for issue in report["issues"]:
            print("ACTION REQUIRED:", issue)
        for note in report["notes"]:
            print("NOTE:", note)
        if report["ready"]:
            print("Next: launch app.py only when ready for REAL Apple requests.")
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
