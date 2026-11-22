import math
import re
from decimal import Decimal, ROUND_DOWN

_NUMERIC_TEXT = re.compile(r"\d+(?:\.\d+)?")


def to_decimal(value):
    """
    Преобразует оценку в Decimal.

    Принимает: int, float, Decimal и текст-число ("85", " 85 ", "85,5").
    Возвращает None для всего остального:
    None, bool, "звіл", "н/б", "-", NaN/inf.
    """
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, Decimal):
        return value if value.is_finite() else None

    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return Decimal(str(value))

    if isinstance(value, str):
        text = value.replace("\u00a0", "").strip().replace(",", ".")
        if _NUMERIC_TEXT.fullmatch(text):
            return Decimal(text)

    return None

def round_down_2(value):
    """Округляет положительное значение вниз до сотых."""
    if value is None:
        return None

    decimal_value = (
        value
        if isinstance(value, Decimal)
        else Decimal(str(value))
    )

    return decimal_value.quantize(
        Decimal("0.01"),
        rounding=ROUND_DOWN
    )