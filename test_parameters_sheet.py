import os
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
 
from openpyxl import Workbook, load_workbook
 
from excel_writer import PARAMETERS_SHEET, build_parameters_sheet, save_database_file
from models import DatabaseStudent
from rating_rules import DEFAULT_RULES, RatingRules, describe_rules, _scholarships
 
ANALYSIS = {
    "subject_type_map": {1: "ІСП"},
    "subject_name_map": {1: "Математика"},
    "group_column_map": {},
}
 
 
def student(index, scholarship, debts=0):
    item = DatabaseStudent(pib=f"С{index}", group_name="АМ-231", bk="Б")
    item.rating = item.total_average = item.exam_average = Decimal(90 - index)
    item.marks = {1: Decimal("90") if not debts else Decimal("40")}
    item.debts = debts
    item.scholarship = scholarship
    return item
 
 
def sheet_text(worksheet):
    return "\n".join(
        " | ".join("" if c.value is None else str(c.value) for c in row)
        for row in worksheet.iter_rows()
    )
 
 
class DescribeRulesTests(unittest.TestCase):
 
    def test_plural_forms(self):
        self.assertEqual(_scholarships(1), "1 стипендія")
        self.assertEqual(_scholarships(2), "2 стипендії")
        self.assertEqual(_scholarships(5), "5 стипендій")
        self.assertEqual(_scholarships(11), "11 стипендій")
        self.assertEqual(_scholarships(21), "21 стипендія")
 
    def test_default_description(self):
        text = str(describe_rules(DEFAULT_RULES))
 
        for expected in ("40%", "10%", "не нижче 60", "не нижче 75",
                         "не нижче 90", "менше 5", "менше 20"):
            self.assertIn(expected, text)
 
    def test_disabled_small_group(self):
        rules = RatingRules(ordinary_small_group=False)
 
        sections = dict(describe_rules(rules))
        ordinary = dict(sections["Ординарна стипендія"])
 
        self.assertEqual(ordinary["Виняток для малих груп"], "вимкнено")
 
 
class ParametersSheetTests(unittest.TestCase):
 
    def test_sheet_content(self):
        workbook = Workbook()
        students = [student(1, "Підвищена"), student(2, "Звичайна"),
                    student(3, "-"), student(4, "-", debts=1)]
 
        build_parameters_sheet(
            workbook, RatingRules(ordinary_percent=35), students,
            now=datetime(2026, 11, 9, 14, 5)
        )
 
        text = sheet_text(workbook[PARAMETERS_SHEET])
 
        self.assertIn("09.11.2026 14:05", text)
        self.assertIn("Бюджетних студентів у розрахунку | 4", text)
        self.assertIn("стандартних: 1, підвищених: 1", text)
        self.assertIn("перші 35% бюджетників", text)
 
    def test_saved_file_has_parameters_sheet_last(self):
        free = [student(1, "Підвищена"), student(2, "-")]
        debtors = [student(3, "-", debts=1)]
 
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "t.xlsx")
 
            save_database_file(
                path, free + debtors, ANALYSIS, free, debtors,
                rules=DEFAULT_RULES
            )
 
            workbook = load_workbook(path)
 
        self.assertEqual(
            workbook.sheetnames,
            ["БазаДаних", "Рейтинг", "Рейтинг_боржники", PARAMETERS_SHEET]
        )
        self.assertIn(
            "Бюджетних студентів у розрахунку | 3",
            sheet_text(workbook[PARAMETERS_SHEET])
        )
 
    def test_without_rules_no_sheet(self):
        free = [student(1, "-")]
 
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "t.xlsx")
            save_database_file(path, free, ANALYSIS, free, [])
            workbook = load_workbook(path)
 
        self.assertNotIn(PARAMETERS_SHEET, workbook.sheetnames)
 
 
if __name__ == "__main__":
    unittest.main()
