"""
Правила призначення стипендій: значення за замовчуванням і перевірка.
Чиста логіка без Qt, щоб її було легко перевіряти.
 
Значення за замовчуванням відповідають правилам університету:
 
Ординарна стипендія
    * студентів 1-4: одна стипендія першому підходящому за рейтингом,
      якщо його рейтинговий бал >= 75;
    * студентів 5 і більше: перші 40% за рейтингом (округлення вниз);
    * у всіх випадках немає боргів і всі оцінки >= 60.
 
Підвищена стипендія
    * студентів менше 20: одна стипендія;
    * студентів 20 і більше: 10% (округлення вниз);
    * немає боргів, усі оцінки >= 75, рейтинговий бал >= 90.
 
Якщо студент не підходить, перевіряється наступний: місце не пропадає.
"""
 
from dataclasses import asdict, dataclass, fields
 
MARK_MIN = 60
MARK_MAX = 100
 
 
@dataclass(frozen=True)
class RatingRules:
 
    # ── Ординарна стипендія ──
    ordinary_percent: int = 40
    ordinary_min_mark: int = 60
 
    # Виняток для малих груп (бюджетників менше ordinary_small_group_limit)
    ordinary_small_group: bool = True
    ordinary_small_group_limit: int = 5
    ordinary_small_group_count: int = 1
    # Рейтинговий бал перевіряється лише в малих групах
    ordinary_small_group_min_rating: int = 75
 
    # ── Підвищена стипендія ──
    higher_percent: int = 10
    higher_min_mark: int = 75
    higher_min_rating: int = 90
 
    # Виняток для малих груп (бюджетників менше higher_small_group_limit)
    higher_small_group: bool = True
    higher_small_group_limit: int = 20
    higher_small_group_count: int = 1
 
    @classmethod
    def from_dict(cls, data):
        """
        Правила зі словника (наприклад, з QSettings).
        Некоректні значення замінюються на типові, числа обмежуються
        допустимим діапазоном, а підвищена не може бути м'якшою за стандартну.
        """
        if not isinstance(data, dict):
            data = {}
 
        default = cls()
        values = {}
 
        for item in fields(cls):
 
            raw = data.get(item.name, getattr(default, item.name))
 
            if item.type is bool:
                values[item.name] = (
                    raw if isinstance(raw, bool)
                    else getattr(default, item.name)
                )
                continue
 
            low, high = RANGES[item.name]
 
            try:
                if isinstance(raw, bool):
                    raise ValueError
 
                number = int(raw)
 
            except (TypeError, ValueError):
                number = getattr(default, item.name)
 
            values[item.name] = max(low, min(high, number))
 
        # Підвищена не м'якша за стандартну
        values["higher_percent"] = min(
            values["higher_percent"], values["ordinary_percent"]
        )
        values["higher_min_mark"] = max(
            values["higher_min_mark"], values["ordinary_min_mark"]
        )
        values["higher_min_rating"] = max(
            values["higher_min_rating"],
            values["ordinary_small_group_min_rating"]
        )
 
        return cls(**values)
 
    def to_dict(self):
        return asdict(self)
 
 
# Допустимі межі (включно). Усі бали: від 60 до 100.
RANGES = {
    "ordinary_percent": (1, 100),
    "ordinary_min_mark": (MARK_MIN, MARK_MAX),
    "ordinary_small_group_limit": (2, 100),
    "ordinary_small_group_count": (1, 10),
    "ordinary_small_group_min_rating": (MARK_MIN, MARK_MAX),
    "higher_percent": (1, 100),
    "higher_min_mark": (MARK_MIN, MARK_MAX),
    "higher_min_rating": (MARK_MIN, MARK_MAX),
    "higher_small_group_limit": (2, 100),
    "higher_small_group_count": (1, 10),
}
 
DEFAULT_RULES = RatingRules()

# ──────────────────────────────────────────────
#  Опис правил текстом (для листа «Параметри» в Excel)
# ──────────────────────────────────────────────

def _scholarships(count):
    """1 стипендія, 2-4 стипендії, 5+ стипендій."""
    if count % 10 == 1 and count % 100 != 11:
        return f"{count} стипендія"

    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return f"{count} стипендії"

    return f"{count} стипендій"


def _small_group_text(enabled, limit, count, extra=""):
    if not enabled:
        return "вимкнено"

    return (
        f"якщо бюджетників менше {limit}: {_scholarships(count)}{extra}"
    )


def describe_rules(rules):
    """
    [(заголовок розділу, [(назва, текст), ...]), ...]
    Усе українською, готове для запису в таблицю.
    """
    ordinary_small = _small_group_text(
        rules.ordinary_small_group,
        rules.ordinary_small_group_limit,
        rules.ordinary_small_group_count,
        f"; рейтинговий бал не нижче {rules.ordinary_small_group_min_rating}"
    )

    higher_small = _small_group_text(
        rules.higher_small_group,
        rules.higher_small_group_limit,
        rules.higher_small_group_count
    )

    return [
        ("Ординарна стипендія", [
            (
                "Кількість стипендій",
                f"перші {rules.ordinary_percent}% бюджетників "
                "за рейтингом (округлення вниз)"
            ),
            (
                "Вимоги до студента",
                f"немає боргів, усі оцінки не нижче "
                f"{rules.ordinary_min_mark}"
            ),
            ("Виняток для малих груп", ordinary_small),
        ]),
        ("Підвищена стипендія", [
            (
                "Кількість стипендій",
                f"перші {rules.higher_percent}% бюджетників "
                "за рейтингом (округлення вниз)"
            ),
            (
                "Вимоги до студента",
                f"немає боргів, усі оцінки не нижче "
                f"{rules.higher_min_mark}, рейтинговий бал не нижче "
                f"{rules.higher_min_rating}"
            ),
            ("Виняток для малих груп", higher_small),
        ]),
    ]


GENERAL_NOTES = (
    "Якщо студент не підходить за умовами, перевіряється наступний "
    "за рейтингом: місце не пропадає.",
    "Підвищені стипендії входять до загальної кількості стандартних.",
    "Борг: оцінка нижче 60 (порожня клітинка рахується як 0).",
)