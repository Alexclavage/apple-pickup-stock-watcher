"""Explicit, allowlisted Apple Retail pickup regional adapters.

These are undocumented Apple endpoints. Regions marked experimental have not
yet been independently verified by this project's maintainers.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Region:
    code: str
    name: str
    currency: str
    pickup_url: str
    experimental: bool = False


REGIONS = {
    "US": Region("US", "United States", "USD", "https://www.apple.com/shop/retail/pickup-message"),
    "CA": Region("CA", "Canada", "CAD", "https://www.apple.com/ca/shop/retail/pickup-message"),
    "FR": Region("FR", "France", "EUR", "https://www.apple.com/fr/shop/retail/pickup-message", True),
    "GB": Region("GB", "United Kingdom", "GBP", "https://www.apple.com/uk/shop/retail/pickup-message", True),
}


def region_for(market, enable_experimental=False):
    if market not in REGIONS:
        raise ValueError(f"Unsupported region: {market}")
    region = REGIONS[market]
    if region.experimental and not enable_experimental:
        raise ValueError(f"{region.name} is experimental and requires enable_experimental_regions=true")
    return region


def normalize_location(market, location):
    """Validate a location, not guarantee the endpoint recognizes it."""
    if not isinstance(location, str):
        raise ValueError("Location must be a string")
    value = " ".join(location.strip().split())
    if not 2 <= len(value) <= 64:
        raise ValueError("Location must contain 2-64 characters")
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Location contains control characters")
    if market == "US" and not re.fullmatch(r"[0-9]{5}", value):
        raise ValueError("US searches require a five-digit ZIP code")
    if market == "FR" and not (
        re.fullmatch(r"[0-9]{5}", value)
        or re.fullmatch(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’ .-]{1,63}", value)
    ):
        raise ValueError("France searches require a five-digit postal code or city name")
    if market == "GB" and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 '’.-]{1,63}", value):
        raise ValueError("UK searches require a postcode or city name")
    if market == "CA" and not re.fullmatch(r"[A-Za-z0-9À-ÿ][A-Za-z0-9À-ÿ '’.-]{1,63}", value):
        raise ValueError("Canada searches require a postal code or city name")
    return value
