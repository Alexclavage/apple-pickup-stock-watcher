"""Explicit one-shot real integration checks; never start the polling worker.

No network traffic without --confirm-live / --confirm-send. Apple checks never
write local state/history or send Discord alerts. Sensitive webhook, SKU and
location values are intentionally excluded from printed results.
"""
import argparse
from collections import Counter
from contextlib import redirect_stdout
from io import StringIO
import os
import re

import requests
from dotenv import load_dotenv


WEBHOOK_URL = re.compile(
    r"^https://discord[.]com/api/webhooks/[0-9]+/[A-Za-z0-9._-]+/?$"
)
TEST_MESSAGE = (
    "🍎 Apple Stock Watcher V1 RC — integration delivery test. "
    "This message was sent on purpose from a local one-shot check. "
    "It is NOT a real stock alert."
)


def send_discord_test(webhook, disabled, post=requests.post):
    """Send exactly one intentional test message. No secrets in return text."""
    if disabled:
        return False, "Discord delivery is disabled in this CMD (WATCHER_DISABLE_DISCORD=1)."
    if not webhook:
        return False, "No DISCORD_WEBHOOK configured in the local .env."
    if not WEBHOOK_URL.fullmatch(webhook):
        return False, "Discord webhook must use a direct https://discord.com/api/webhooks/ URL."
    try:
        response = post(
            webhook,
            json={"content": TEST_MESSAGE, "allowed_mentions": {"parse": []}},
            timeout=15,
        )
        status = response.status_code
    except Exception as exc:
        # Requests exceptions can include the full secret URL; don't print them.
        return False, "Discord network error: " + type(exc).__name__
    if status in (200, 204):
        return True, "Discord accepted exactly one test message (HTTP " + str(status) + ")."
    if status == 429:
        return False, "Discord rate limited this test (HTTP 429); do not retry immediately."
    return False, "Discord rejected the test (HTTP " + str(status) + "). No webhook URL displayed."


def summarize_apple(products, areas, items, errors):
    """Aggregate real observations without printing private locations or SKUs."""
    market_counts = Counter(p["market"] for p in products.values())
    area_counts = Counter(a["market"] for a in areas)
    observed_by_market = {}
    output = []
    for market in sorted(market_counts):
        rows = [x for x in items if x.get("market") == market]
        observed_by_market[market] = {x.get("product_id") for x in rows}
        statuses = Counter(x.get("status", "unknown") for x in rows)
        unique_stores = {x.get("storeNumber") for x in rows if x.get("storeNumber")}
        output.append({
            "market": market,
            "configured_products": market_counts[market],
            "areas": area_counts[market],
            "stores": len(unique_stores),
            "observed_product_ids": len(observed_by_market[market]),
            "available": statuses["available"],
            "unavailable": statuses["unavailable"],
            "unknown": statuses["unknown"],
        })
    has_multiple_confirmed = any(
        row["observed_product_ids"] >= 2 and row["unknown"] == 0
        for row in output
    )
    complete = bool(items) and not errors and all(
        row["unknown"] == 0
        and row["observed_product_ids"] == row["configured_products"]
        for row in output if row["configured_products"]
    )
    return {"complete": complete, "multiple_variants_observed": has_multiple_confirmed,
            "issues": len(errors), "markets": output}


def check_apple_once(watcher):
    if not watcher.CONFIG_PATH.is_file():
        print("REFUSED: private config.json is missing; do not query Apple using defaults.")
        return 2
    unique = {}
    for p in watcher.PRODUCTS.values():
        unique.setdefault(p["market"], set()).add(p["part"])
    if not any(len(skus) >= 2 for skus in unique.values()):
        print("REFUSED: configure at least two DISTINCT SKUs in the SAME country before the multi-variant test.")
        print("Use the local setup wizard and Save; this check never edits your config.")
        return 2
    print("Sending ONE real Apple scan across configured areas. No Discord alerts or state/history writes.")
    try:
        # Hide worker debug lines which may contain user-chosen area IDs.
        with redirect_stdout(StringIO()):
            items, errors = watcher.fetch_all()
    except Exception as exc:
        # Never print raw exceptions that might contain locations or private IDs.
        print("Apple check could not finish: " + type(exc).__name__ + ".")
        return 1
    result = summarize_apple(watcher.PRODUCTS, watcher.MONITORING_AREAS, items, errors)
    for row in result["markets"]:
        print(
            f'{row["market"]}: {row["configured_products"]} configured variants, '
            f'{row["observed_product_ids"]} observed, {row["areas"]} area(s), '
            f'{row["stores"]} returned store(s) | '
            f'available={row["available"]}, unavailable={row["unavailable"]}, '
            f'unknown={row["unknown"]}'
        )
    print("Coverage issues:", result["issues"], "(details kept out of shared output)")
    if result["complete"] and result["multiple_variants_observed"]:
        print("PASS: multi-variant Apple responses observed with complete checked coverage.")
        return 0
    print("INCOMPLETE: no assertion of sold-out stock. Inspect local /api/status if needed.")
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="One-shot opt-in integration checks; no worker or state writes"
    )
    sub = parser.add_subparsers(dest="mode", required=True)
    apple = sub.add_parser("apple", help="One real Apple scan, requires 2+ distinct same-market SKUs")
    apple.add_argument("--confirm-live", action="store_true")
    discord = sub.add_parser("discord", help="Send one explicit message to a PRIVATE TEST webhook")
    discord.add_argument("--confirm-send", action="store_true")
    args = parser.parse_args(argv)

    if args.mode == "apple":
        if not args.confirm_live:
            print("REFUSED: add --confirm-live to authorize one REAL Apple pickup scan.")
            return 2
        try:
            import app as watcher  # Import only; never starts worker or writes state.
        except Exception as exc:
            print("Cannot load local watcher config (" + type(exc).__name__ + ").")
            return 2
        return check_apple_once(watcher)

    if not args.confirm_send:
        print("REFUSED: add --confirm-send to send ONE message to your TEST Discord webhook.")
        return 2
    load_dotenv()
    disabled = os.getenv("WATCHER_DISABLE_DISCORD", "").strip().lower() in {
        "1", "true", "yes", "on",
    }
    success, description = send_discord_test(
        os.getenv("DISCORD_WEBHOOK", ""), disabled
    )
    print(description)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
