"""
Збереження налаштувань рейтингу (правила стипендій і кольори таблиці).
 
Об'єкт QSettings передається ззовні, тому тут немає імпортів Qt
і модуль легко перевірити тестами.
"""
 
import json
 
from rating_rules import RatingRules
from table_colors import TableColors
 
RULES_KEY = "rating_rules"
COLORS_KEY = "table_colors"
 
 
def _load(settings, key, cls):
    """Читає JSON з налаштувань; будь-яка помилка -> значення за замовчуванням."""
    raw = settings.value(key, "")
 
    try:
        data = json.loads(raw) if isinstance(raw, str) and raw else {}
    except ValueError:
        data = {}
 
    return cls.from_dict(data)
 
 
def load_settings(settings):
    """Повертає (правила стипендій, кольори таблиці)."""
    return (
        _load(settings, RULES_KEY, RatingRules),
        _load(settings, COLORS_KEY, TableColors),
    )
 
 
def save_settings(settings, rules, colors):
    settings.setValue(RULES_KEY, json.dumps(rules.to_dict()))
    settings.setValue(COLORS_KEY, json.dumps(colors.to_dict()))
    settings.sync()
 