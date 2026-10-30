"""Explicit, allowlisted Apple Retail pickup regional adapters.

These are undocumented Apple endpoints. Experimental markets retain explicit
opt-in even when a bounded live check has been recorded; see the coverage docs.
"""
from dataclasses import dataclass
import re
import unicodedata


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

# Additional adapters remain opt-in; bounded live observations are recorded separately.
REGIONS.update({
    "AU": Region("AU", "Australia", "AUD", "https://www.apple.com/au/shop/retail/pickup-message", True),
    "AT": Region("AT", "Austria", "EUR", "https://www.apple.com/at/shop/retail/pickup-message", True),
    "BE": Region("BE", "Belgium", "EUR", "https://www.apple.com/be-fr/shop/retail/pickup-message", True),
    "BR": Region("BR", "Brazil", "BRL", "https://www.apple.com/br/shop/retail/pickup-message", True),
    "CN": Region("CN", "China mainland", "CNY", "https://www.apple.com.cn/shop/retail/pickup-message", True),
    "DE": Region("DE", "Germany", "EUR", "https://www.apple.com/de/shop/retail/pickup-message", True),
    "HK": Region("HK", "Hong Kong", "HKD", "https://www.apple.com/hk/shop/retail/pickup-message", True),
    "IN": Region("IN", "India", "INR", "https://www.apple.com/in/shop/retail/pickup-message", True),
    "IT": Region("IT", "Italy", "EUR", "https://www.apple.com/it/shop/retail/pickup-message", True),
    "JP": Region("JP", "Japan", "JPY", "https://www.apple.com/jp/shop/retail/pickup-message", True),
    "MY": Region("MY", "Malaysia", "MYR", "https://www.apple.com/my/shop/retail/pickup-message", True),
    "MX": Region("MX", "Mexico", "MXN", "https://www.apple.com/mx/shop/retail/pickup-message", True),
    "NL": Region("NL", "Netherlands", "EUR", "https://www.apple.com/nl/shop/retail/pickup-message", True),
    "SG": Region("SG", "Singapore", "SGD", "https://www.apple.com/sg/shop/retail/pickup-message", True),
    "KR": Region("KR", "South Korea", "KRW", "https://www.apple.com/kr/shop/retail/pickup-message", True),
    "ES": Region("ES", "Spain", "EUR", "https://www.apple.com/es/shop/retail/pickup-message", True),
    "SE": Region("SE", "Sweden", "SEK", "https://www.apple.com/se/shop/retail/pickup-message", True),
    "CH": Region("CH", "Switzerland", "CHF", "https://www.apple.com/ch-fr/shop/retail/pickup-message", True),
    "TW": Region("TW", "Taiwan", "TWD", "https://www.apple.com/tw/shop/retail/pickup-message", True),
    "TH": Region("TH", "Thailand", "THB", "https://www.apple.com/th/shop/retail/pickup-message", True),
    "TR": Region("TR", "Türkiye", "TRY", "https://www.apple.com/tr/shop/retail/pickup-message", True),
    "AE": Region("AE", "United Arab Emirates", "AED", "https://www.apple.com/ae/shop/retail/pickup-message", True),
})

# Derive catalog bases from the same fixed allowlisted pickup routes.
def shop_base_for(market):
    return REGIONS[market].pickup_url.removesuffix("/shop/retail/pickup-message")


def price_limit_for(currency):
    """Input safety caps in currency units, not product price estimates."""
    return {"JPY": 10_000_000, "KRW": 100_000_000, "INR": 10_000_000,
            "TWD": 10_000_000, "THB": 10_000_000, "TRY": 10_000_000}.get(currency, 100_000)


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
    if any(ord(c) < 32 or ord(c) == 127 for c in location):
        raise ValueError("Location contains control characters")
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
    if market not in REGIONS:
        raise ValueError("Unsupported region")
    if market not in {"US", "CA", "FR", "GB"} and not all(
        c.isalnum() or unicodedata.category(c).startswith("M") or c in " -.'’()," for c in value
    ):
        raise ValueError("Location must be a postal code or city name")
    return value
