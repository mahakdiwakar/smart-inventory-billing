from decimal import Decimal, ROUND_HALF_UP

def dec(v, default="0"):
    try:
        return Decimal(str(v if v not in (None, "") else default))
    except Exception:
        raise ValueError(f"Invalid number: {v!r}")

def q2(v):
    return Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
