import unittest
from decimal import Decimal

from openpyxl import Workbook

from models import DatabaseStudent
from rating import build_rating_structure, fill_rating_students
from table_colors import (
    DEFAULT_COLORS,
    TableColors,
    contrast_ratio,
    normalize_color,
    unreadable_fields,
)

ANALYSIS = {
    "subject_type_map": {1: "ІСП"},
    "subject_name_map": {1: "Математика"},
    "group_column_map": {},
}


def student(index, scholarship, debts=0):
    item = DatabaseStudent(pib=f"Студент {index}", group_name="АМ-231")
    item.rating = item.total_average = Decimal(90 - index)
    item.exam_average = item.rating
    item.marks = {1: Decimal("90") if debts == 0 else Decimal("40")}
    item.debts = debts
    item.scholarship = scholarship
    return item


def build_sheet(students, colors, include_debts=True):
    workbook = Workbook()

    sheet = build_rating_structure(
        workbook, ANALYSIS, "T", include_debts=include_debts, colors=colors
    )
    fill_rating_students(
        sheet, students, ANALYSIS, include_debts=include_debts, colors=colors
    )

    return sheet


def color(sheet, row, column):
    # openpyxl хранит цвет как "00RRGGBB"
    return sheet.cell(row=row, column=column).fill.fgColor.rgb[-6:]


class NormalizeColorTests(unittest.TestCase):

    def test_accepts_hash_and_lowercase(self):
        self.assertEqual(normalize_color("#e2e2e2", "000000"), "E2E2E2")
        self.assertEqual(normalize_color(" c6dbd2 ", "000000"), "C6DBD2")

    def test_rejects_garbage(self):
        for value in (None, 123, "", "#FFF", "GGGGGG", "E2E2E2E2", ["E2E2E2"]):
            self.assertEqual(normalize_color(value, "ABCDEF"), "ABCDEF")


class TableColorsTests(unittest.TestCase):

    def test_defaults(self):
        colors = DEFAULT_COLORS

        self.assertTrue(colors.two_tone)
        self.assertEqual(colors.row_color(True), "E2E2E2")
        self.assertEqual(colors.row_color(False), "FFFFFF")
        self.assertEqual(colors.pib_color(False), "EEEEEE")
        self.assertEqual(colors.header, "EEEEEE")
        self.assertEqual(colors.scholarship_color("Звичайна", True), "C6DBD2")
        self.assertEqual(colors.scholarship_color("Звичайна", False), "D1E7DD")
        self.assertEqual(colors.scholarship_color("Підвищена", True), "96BBF2")
        self.assertEqual(colors.scholarship_color("Підвищена", False), "9EC5FE")
        self.assertEqual(colors.debt_color(True), "E9E1CA")
        self.assertEqual(colors.debt_color(False), "F5EDD5")
        self.assertIsNone(colors.scholarship_color("-", True))
        self.assertIsNone(colors.scholarship_color(None, False))

    def test_two_tone_off_uses_only_first_color(self):
        colors = TableColors(two_tone=False)

        for shaded in (True, False):
            self.assertEqual(colors.row_color(shaded), "E2E2E2")
            self.assertEqual(colors.pib_color(shaded), "E2E2E2")
            self.assertEqual(colors.debt_color(shaded), "E9E1CA")
            self.assertEqual(
                colors.scholarship_color("Звичайна", shaded), "C6DBD2"
            )
            self.assertEqual(
                colors.scholarship_color("Підвищена", shaded), "96BBF2"
            )

    def test_from_dict(self):
        self.assertEqual(TableColors.from_dict(DEFAULT_COLORS.to_dict()),
                         DEFAULT_COLORS)

        colors = TableColors.from_dict({
            "table_1": "#aabbcc",
            "table_2": "bad",
            "two_tone": "yes",
        })

        self.assertEqual(colors.table_1, "AABBCC")
        self.assertEqual(colors.table_2, "FFFFFF")
        self.assertTrue(colors.two_tone)

        self.assertEqual(TableColors.from_dict(None), DEFAULT_COLORS)


class ExcelSheetColorsTests(unittest.TestCase):

    def setUp(self):
        self.students = [
            student(1, "Підвищена"),
            student(2, "Звичайна"),
            student(3, "-"),
            student(4, "-"),
            student(5, "-", debts=1),
        ]

    def test_default_colors_in_sheet(self):
        sheet = build_sheet(self.students, DEFAULT_COLORS)

        # шапка
        self.assertEqual(color(sheet, 1, 1), "EEEEEE")
        self.assertEqual(color(sheet, 2, 1), "FFFFFF")

        # дані починаються з 3-го рядка; 2 = номер ПІБ-колонки
        self.assertEqual(color(sheet, 3, 1), "96BBF2")   # підвищена, shaded
        self.assertEqual(color(sheet, 4, 1), "D1E7DD")   # звичайна, не shaded
        self.assertEqual(color(sheet, 5, 1), "E2E2E2")   # без стипендії
        self.assertEqual(color(sheet, 5, 2), "E2E2E2")   # ПІБ, shaded
        self.assertEqual(color(sheet, 6, 1), "FFFFFF")
        self.assertEqual(color(sheet, 6, 2), "EEEEEE")   # ПІБ, не shaded

    def test_two_tone_off_in_sheet(self):
        sheet = build_sheet(self.students, TableColors(two_tone=False))

        self.assertEqual(color(sheet, 4, 1), "C6DBD2")   # звичайна
        self.assertEqual(color(sheet, 6, 1), "E2E2E2")
        self.assertEqual(color(sheet, 6, 2), "E2E2E2")

    def test_custom_colors_in_sheet(self):
        colors = TableColors(
            two_tone=False, table_1="111111", header="222222",
            higher_1="333333", ordinary_1="444444", pib_1="555555",
            debt_1="666666",
        )
        sheet = build_sheet(self.students, colors)

        self.assertEqual(color(sheet, 1, 1), "222222")
        self.assertEqual(color(sheet, 3, 1), "333333")
        self.assertEqual(color(sheet, 4, 1), "444444")
        self.assertEqual(color(sheet, 5, 1), "111111")
        self.assertEqual(color(sheet, 5, 2), "555555")

        # борг студента 5: хоча б одна клітинка має колір боргів
        debt_colors = {
            cell.fill.fgColor.rgb[-6:]
            for row in sheet.iter_rows(min_row=3) for cell in row
        }
        self.assertIn("666666", debt_colors)


class ContrastTests(unittest.TestCase):

    def test_contrast_ratio_extremes(self):
        self.assertAlmostEqual(contrast_ratio("000000", "FFFFFF"), 21, places=1)
        self.assertAlmostEqual(contrast_ratio("123456", "123456"), 1, places=3)

    def test_default_colors_are_readable(self):
        self.assertEqual(unreadable_fields(DEFAULT_COLORS), [])

    def test_debt_color_is_checked(self):
        self.assertEqual(
            unreadable_fields(TableColors(debt_1="222222")), ["debt_1"]
        )
        self.assertEqual(
            unreadable_fields(TableColors(debt_2="222222")), ["debt_2"]
        )
        self.assertEqual(
            unreadable_fields(TableColors(two_tone=False, debt_2="222222")),
            []
        )

    def test_dark_color_is_reported(self):
        colors = TableColors(header="222222", ordinary_1="3366CC")

        self.assertEqual(unreadable_fields(colors), ["header", "ordinary_1"])

    def test_second_colors_ignored_when_two_tone_off(self):
        dark = "111111"

        self.assertEqual(
            unreadable_fields(TableColors(two_tone=True, table_2=dark)),
            ["table_2"]
        )
        self.assertEqual(
            unreadable_fields(TableColors(two_tone=False, table_2=dark)),
            []
        )


if __name__ == "__main__":
    unittest.main()