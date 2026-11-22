import unittest
from decimal import Decimal
 
from models import DatabaseStudent
from rating import calculate_scholarships, higher_quota, ordinary_quota
from rating_rules import DEFAULT_RULES, RatingRules
 
 
def student(name, rating, debts=0, marks=None):
    """Студент з уже порахованим рейтингом (бюджет)."""
    item = DatabaseStudent(pib=name, group_name="АМ-231")
    item.rating = Decimal(str(rating))
    item.total_average = item.rating
    item.debts = debts
    item.marks = {1: Decimal("80")} if marks is None else marks
    return item
 
 
def awarded(students):
    return {item.pib: item.scholarship for item in students}
 
 
class QuotaTests(unittest.TestCase):
 
    def test_ordinary_quota(self):
        expected = {
            0: 0, 1: 1, 2: 1, 3: 1, 4: 1,   # малі групи: одна
            5: 2, 7: 2, 8: 3, 9: 3, 10: 4,  # 40% вниз
            20: 8, 25: 10,
        }
        for total, quota in expected.items():
            self.assertEqual(ordinary_quota(total), quota, total)
 
    def test_higher_quota(self):
        expected = {0: 0, 1: 1, 10: 1, 19: 1, 20: 2, 25: 2, 39: 3, 40: 4}
        for total, quota in expected.items():
            self.assertEqual(higher_quota(total), quota, total)
 
    def test_small_group_exception_off(self):
        rules = RatingRules(ordinary_small_group=False,
                            higher_small_group=False)
 
        self.assertEqual(ordinary_quota(2, rules), 0)
        self.assertEqual(ordinary_quota(3, rules), 1)
        self.assertEqual(higher_quota(15, rules), 1)
        self.assertEqual(higher_quota(9, rules), 0)
 
 
class OrdinaryScholarshipTests(unittest.TestCase):
 
    def test_single_student_needs_rating_75(self):
        low = calculate_scholarships([student("А", 74.99)])
        high = calculate_scholarships([student("А", 75)])
 
        self.assertEqual(low[0].scholarship, "-")
        self.assertEqual(high[0].scholarship, "Звичайна")
 
    def test_small_group_place_moves_to_next(self):
        students = [
            student("Борг", 85, debts=1,
                    marks={1: Decimal("50")}),
            student("Другий", 76),
            student("Третій", 70),
        ]
 
        result = awarded(calculate_scholarships(students))
 
        self.assertEqual(result["Борг"], "-")
        self.assertEqual(result["Другий"], "Звичайна")
        self.assertEqual(result["Третій"], "-")
 
    def test_small_group_only_one_scholarship(self):
        students = [student(f"С{i}", 80 - i) for i in range(4)]
 
        given = [
            item for item in calculate_scholarships(students)
            if item.scholarship != "-"
        ]
 
        self.assertEqual(len(given), 1)
 
    def test_rating_not_checked_from_five_students(self):
        students = [student(f"С{i}", 70 - i) for i in range(5)]
 
        result = awarded(calculate_scholarships(students))
 
        self.assertEqual(result["С0"], "Звичайна")
        self.assertEqual(result["С1"], "Звичайна")
        self.assertEqual(result["С2"], "-")
 
    def test_debtors_are_skipped_place_kept(self):
        students = [
            student("Д1", 95, debts=1, marks={1: Decimal("59")}),
            student("Д2", 94, debts=1, marks={1: Decimal("59")}),
        ] + [student(f"С{i}", 80 - i) for i in range(8)]
 
        result = calculate_scholarships(students)
        given = [item for item in result if item.scholarship != "-"]
 
        # 10 бюджетників -> 4 стипендії, усі в студентів без боргів
        self.assertEqual(len(given), 4)
        self.assertTrue(all(item.debts == 0 for item in given))
        self.assertEqual(given[0].pib, "С0")
 
    def test_empty_mark_is_not_eligible(self):
        students = [student(f"С{i}", 80 - i) for i in range(5)]
        students[0].marks = {1: None}   # порожня оцінка = 0
        students[0].debts = 1
 
        result = awarded(calculate_scholarships(students))
 
        self.assertEqual(result["С0"], "-")
 
    def test_text_marks_are_ignored(self):
        students = [student("А", 80, marks={1: "н/б", 2: Decimal("70")})]
 
        self.assertEqual(
            calculate_scholarships(students)[0].scholarship, "Звичайна"
        )
 
    def test_empty_list(self):
        self.assertEqual(calculate_scholarships([]), [])
 
 
class HigherScholarshipTests(unittest.TestCase):
 
    def test_higher_replaces_ordinary_and_counts_in_quota(self):
        students = [student("А", 92)]
 
        self.assertEqual(
            calculate_scholarships(students)[0].scholarship, "Підвищена"
        )
 
        students = [student(f"С{i}", 95 - i) for i in range(10)]
        result = calculate_scholarships(students)
        kinds = [item.scholarship for item in result]
 
        # 10 студентів: 4 стандартні разом з підвищеною, підвищена одна
        self.assertEqual(kinds.count("Підвищена"), 1)
        self.assertEqual(kinds.count("Звичайна"), 3)
 
    def test_higher_needs_all_marks_75(self):
        students = [
            student("А", 95, marks={1: Decimal("100"), 2: Decimal("74")}),
            student("Б", 91),
        ]
 
        result = awarded(calculate_scholarships(students))
 
        self.assertEqual(result["А"], "-")
        self.assertEqual(result["Б"], "Підвищена")
 
    def test_higher_place_is_not_lost_in_big_group(self):
        # 25 студентів -> 2 підвищені. Перші двоє не підходять за оцінкою,
        # тому стипендії дістаються наступним підходящим.
        students = [
            student("П1", 99, marks={1: Decimal("70")}),
            student("П2", 98, marks={1: Decimal("70")}),
        ] + [student(f"С{i}", 97 - i) for i in range(23)]
 
        result = awarded(calculate_scholarships(students))
 
        self.assertEqual(result["П1"], "Звичайна")
        self.assertEqual(result["П2"], "Звичайна")
        self.assertEqual(result["С0"], "Підвищена")
        self.assertEqual(result["С1"], "Підвищена")
        self.assertEqual(
            sum(1 for value in result.values() if value == "Підвищена"), 2
        )
 
    def test_total_never_exceeds_ordinary_quota(self):
        students = [student(f"С{i}", 99 - i * 0.1) for i in range(30)]
 
        given = [
            item for item in calculate_scholarships(students)
            if item.scholarship != "-"
        ]
 
        self.assertEqual(len(given), ordinary_quota(30))
 
    def test_rating_90_required(self):
        students = [student("А", 89.99)]
 
        self.assertEqual(
            calculate_scholarships(students)[0].scholarship, "Звичайна"
        )
 
 
class RulesValidationTests(unittest.TestCase):
 
    def test_defaults_roundtrip(self):
        self.assertEqual(
            RatingRules.from_dict(DEFAULT_RULES.to_dict()), DEFAULT_RULES
        )
 
    def test_garbage_gives_defaults(self):
        for data in (None, "x", [], {"ordinary_percent": "abc"}):
            self.assertEqual(
                RatingRules.from_dict(data).ordinary_percent, 40
            )
 
    def test_marks_are_clamped_to_60_100(self):
        rules = RatingRules.from_dict({
            "ordinary_min_mark": 10,
            "higher_min_rating": 500,
            "ordinary_small_group_min_rating": 0,
        })
 
        self.assertEqual(rules.ordinary_min_mark, 60)
        self.assertEqual(rules.higher_min_rating, 100)
        self.assertEqual(rules.ordinary_small_group_min_rating, 60)
 
    def test_higher_not_softer_than_ordinary(self):
        rules = RatingRules.from_dict({
            "ordinary_percent": 30,
            "higher_percent": 50,
            "ordinary_min_mark": 80,
            "higher_min_mark": 65,
        })
 
        self.assertEqual(rules.higher_percent, 30)
        self.assertEqual(rules.higher_min_mark, 80)
 
    def test_bool_is_not_a_number(self):
        rules = RatingRules.from_dict({"ordinary_percent": True,
                                       "ordinary_small_group": "yes"})
 
        self.assertEqual(rules.ordinary_percent, 40)
        self.assertTrue(rules.ordinary_small_group)
 
    def test_custom_rules_are_used(self):
        rules = RatingRules(ordinary_percent=50, ordinary_min_mark=70)
        students = [student(f"С{i}", 80 - i) for i in range(10)]
        students[0].marks = {1: Decimal("65")}   # нижче 70
 
        result = awarded(calculate_scholarships(students, rules))
 
        self.assertEqual(result["С0"], "-")
        self.assertEqual(
            sum(1 for value in result.values() if value != "-"), 5
        )
 
 
if __name__ == "__main__":
    unittest.main()
 