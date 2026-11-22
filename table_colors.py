"""
Кольори таблиць рейтингу: значення за замовчуванням і перевірка.
Чиста логіка без Qt, щоб її було легко перевіряти.
 
Кольори зберігаються як рядки "RRGGBB" (великими літерами, без "#").
 
Якщо двоколірний режим вимкнено, скрізь використовується лише перший
колір пари, тобто всі рядки таблиці мають однаковий фон.
"""
 
import re
from dataclasses import asdict, dataclass, fields
 
_HEX = re.compile(r"#?([0-9A-Fa-f]{6})")
 
# Колір другого рядка шапки та кольори боргів не налаштовуються
HEADER_SECOND_COLOR = "FFFFFF"
 
 
def normalize_color(value, default):
    """
    "#e2e2e2" / "E2E2E2" -> "E2E2E2".
    Усе інше (не рядок, не шість шістнадцяткових цифр) -> default.
    """
    if isinstance(value, str):
        match = _HEX.fullmatch(value.strip())
 
        if match:
            return match.group(1).upper()
 
    return default
 
 
@dataclass(frozen=True)
class TableColors:
 
    # Двоколірний режим: чергувати перший і другий колір пари
    two_tone: bool = True
 
    # Рядки таблиці
    table_1: str = "E2E2E2"
    table_2: str = "FFFFFF"
 
    # Шапка таблиці (перший рядок шапки)
    header: str = "EEEEEE"
 
    # Стовпець ПІБ у рядках без стипендії
    pib_1: str = "E2E2E2"
    pib_2: str = "EEEEEE"
 
    # Виділення стандартної стипендії на листі «Рейтинг»
    ordinary_1: str = "C6DBD2"
    ordinary_2: str = "D1E7DD"
 
    # Виділення підвищеної стипендії на листі «Рейтинг»
    higher_1: str = "96BBF2"
    higher_2: str = "9EC5FE"

    # Підсвічування боргів на листі «Рейтинг_боржники»
    debt_1: str = "E9E1CA"
    debt_2: str = "F5EDD5"

    # ── Вибір кольору для рядка ──
    # shaded=True: 1-й, 3-й, 5-й студент... (перший колір пари)
 
    def _pick(self, first, second, shaded):
        return first if shaded or not self.two_tone else second
 
    def row_color(self, shaded):
        return self._pick(self.table_1, self.table_2, shaded)
 
    def pib_color(self, shaded):
        return self._pick(self.pib_1, self.pib_2, shaded)
 
    def debt_color(self, shaded):
        return self._pick(self.debt_1, self.debt_2, shaded)
 
    def scholarship_color(self, scholarship, shaded):
        """Колір рядка зі стипендією або None, якщо стипендії немає."""
        if scholarship == "Звичайна":
            return self._pick(self.ordinary_1, self.ordinary_2, shaded)
 
        if scholarship == "Підвищена":
            return self._pick(self.higher_1, self.higher_2, shaded)
 
        return None
 
    @classmethod
    def from_dict(cls, data):
        """Кольори зі словника (наприклад, з QSettings); некоректні -> типові."""
        if not isinstance(data, dict):
            data = {}
 
        default = cls()
        values = {}
 
        for item in fields(cls):
 
            fallback = getattr(default, item.name)
            raw = data.get(item.name, fallback)
 
            if item.type is bool:
                values[item.name] = (
                    raw if isinstance(raw, bool) else fallback
                )
            else:
                values[item.name] = normalize_color(raw, fallback)
 
        return cls(**values)
 
    def to_dict(self):
        return asdict(self)
 
 
DEFAULT_COLORS = TableColors()

# ──────────────────────────────────────────────
#  Читабельність чорного тексту на кольорі
# ──────────────────────────────────────────────

# У таблицях рейтингу шрифт завжди чорний. 4.5 — рекомендований
# контраст WCAG для звичайного тексту.
MIN_CONTRAST = 4.5


def _luminance(color):
    """Відносна яскравість кольору "RRGGBB" (0 = чорний, 1 = білий)."""
    channels = []

    for index in (0, 2, 4):
        value = int(color[index:index + 2], 16) / 255

        channels.append(
            value / 12.92
            if value <= 0.03928
            else ((value + 0.055) / 1.055) ** 2.4
        )

    return (
        0.2126 * channels[0]
        + 0.7152 * channels[1]
        + 0.0722 * channels[2]
    )


def contrast_ratio(color_a, color_b="000000"):
    """Контраст двох кольорів "RRGGBB": від 1 (однакові) до 21."""
    lighter, darker = sorted(
        (_luminance(color_a), _luminance(color_b)),
        reverse=True
    )

    return (lighter + 0.05) / (darker + 0.05)


def unreadable_fields(colors):
    """
    Імена полів, на яких чорний текст погано читається.
    Другі кольори пар перевіряються, лише якщо двоколірний режим увімкнено.
    """
    names = [
        "table_1", "header", "pib_1", "ordinary_1", "higher_1", "debt_1"
    ]

    if colors.two_tone:
        names += ["table_2", "pib_2", "ordinary_2", "higher_2", "debt_2"]

    return [
        name for name in names
        if contrast_ratio(getattr(colors, name)) < MIN_CONTRAST
    ]