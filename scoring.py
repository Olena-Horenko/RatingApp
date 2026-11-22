from decimal import Decimal

from rounding import to_decimal
from subject_utils import get_subject_category


ZERO = Decimal("0")

DEBT_THRESHOLD = Decimal("60")


def _avg(values: list[Decimal]) -> Decimal | None:
    """Среднее арифметическое; None, если оценок нет."""
    if not values:
        return None

    return sum(values, ZERO) / Decimal(len(values))


def calculate_statistics(students, analysis):

    subject_type_map = analysis["subject_type_map"]
    subject_name_map = analysis["subject_name_map"]

    # Категория зависит только от предмета, поэтому считаем её
    # один раз на предмет, а не для каждой оценки каждого студента.
    category_by_id = {
        subject_id: get_subject_category(
            subject_name_map.get(subject_id, ""),
            subject_type
        )
        for subject_id, subject_type in subject_type_map.items()
    }

    for student in students:

        by_category = {
            "exam": [],
            "course": [],
            "practice": [],
        }

        all_marks = []

        for subject_id, mark in student.marks.items():

            # Пустая ячейка = 0 + долг
            if mark is None:
                value = ZERO

            else:
                value = to_decimal(mark)

                # "звіл", "н/б", "-" и любой другой текст
                if value is None:
                    continue

            all_marks.append(value)

            category = category_by_id.get(subject_id, "other")

            # Обычный ЗАЛ ("other") идёт только в общий средний
            if category in by_category:
                by_category[category].append(value)

        # В рейтинг входят экзамены, курсовые и практика
        rated_marks = (
            by_category["exam"]
            + by_category["course"]
            + by_category["practice"]
        )

        student.exam_average = _avg(by_category["exam"])
        student.course_average = _avg(by_category["course"])
        student.practice_average = _avg(by_category["practice"])
        student.rating = _avg(rated_marks)
        student.total_average = _avg(all_marks)

        student.debts = sum(
            1 for value in all_marks
            if value < DEBT_THRESHOLD
        )

    return students