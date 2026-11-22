import unittest

from rating_rules import RatingRules
from settings_store import COLORS_KEY, RULES_KEY, load_settings, save_settings
from table_colors import DEFAULT_COLORS, TableColors


class FakeSettings:
    """Мінімальна заміна QSettings."""

    def __init__(self):
        self.data = {}
        self.synced = False

    def value(self, key, default=None):
        return self.data.get(key, default)

    def setValue(self, key, value):
        self.data[key] = value

    def sync(self):
        self.synced = True


class SettingsStoreTests(unittest.TestCase):

    def test_empty_settings_give_defaults(self):
        rules, colors = load_settings(FakeSettings())

        self.assertEqual(rules, RatingRules())
        self.assertEqual(colors, DEFAULT_COLORS)

    def test_roundtrip(self):
        settings = FakeSettings()
        rules = RatingRules(ordinary_percent=35, higher_min_rating=95)
        colors = TableColors(two_tone=False, header="123ABC")

        save_settings(settings, rules, colors)

        self.assertTrue(settings.synced)
        self.assertEqual(load_settings(settings), (rules, colors))

    def test_old_settings_without_debt_colors(self):
        # налаштування, збережені до появи кольору боргів
        settings = FakeSettings()
        settings.data[COLORS_KEY] = '{"two_tone": false, "header": "123ABC"}'

        _, colors = load_settings(settings)

        self.assertFalse(colors.two_tone)
        self.assertEqual(colors.header, "123ABC")
        self.assertEqual(colors.debt_1, DEFAULT_COLORS.debt_1)
        self.assertEqual(colors.debt_2, DEFAULT_COLORS.debt_2)

    def test_broken_json_gives_defaults(self):
        settings = FakeSettings()
        settings.data[RULES_KEY] = "{not json"
        settings.data[COLORS_KEY] = 12345

        rules, colors = load_settings(settings)

        self.assertEqual(rules, RatingRules())
        self.assertEqual(colors, DEFAULT_COLORS)

    def test_tampered_values_are_sanitized(self):
        settings = FakeSettings()
        settings.data[RULES_KEY] = '{"ordinary_min_mark": 5, "higher_percent": 999}'
        settings.data[COLORS_KEY] = '{"header": "zzz"}'

        rules, colors = load_settings(settings)

        self.assertEqual(rules.ordinary_min_mark, 60)
        self.assertEqual(rules.higher_percent, rules.ordinary_percent)
        self.assertEqual(colors.header, DEFAULT_COLORS.header)


if __name__ == "__main__":
    unittest.main()