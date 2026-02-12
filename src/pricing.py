import math

def round_up_to_x90(price: float) -> float:
    # rotunjire în sus la .90 (>= price)
    return math.ceil(price - 0.90) + 0.90

def compute_final_price_ron(
    source_price: float | None,
    currency: str | None,
    eur_ron: float,
    gbp_ron: float,
    markup_percent: float = 100.0,
    missing_price_fallback_ron: float = 1.0
) -> float:
    # dacă lipsește preț -> fallback fix (1 RON)
    if source_price is None or currency is None:
        return float(missing_price_fallback_ron)

    currency = currency.upper()

    if currency == "RON":
        base_ron = source_price
    elif currency == "EUR":
        base_ron = source_price * eur_ron
    elif currency == "GBP":
        base_ron = source_price * gbp_ron
    else:
        return float(missing_price_fallback_ron)

    final = base_ron * (1 + markup_percent / 100.0)

    # pentru prețuri calculate, dacă e prea mic, forțăm minim 1.90 ca să păstreze .90 logic
    if final < 1.90:
        final = 1.90

    return float(round_up_to_x90(final))
