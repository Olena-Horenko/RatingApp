"""
Аналітика по результату розрахунку: загальна статистика,
порівняння груп, аналіз дисциплін.
Чиста логіка без Qt, щоб її було легко перевіряти.
"""

from dataclasses import dataclass
from decimal import Decimal

from rounding import round_down_2, to_decimal
from scoring import DEBT_THRESHOLD, ZERO

SCHOLARSHIPS = ("Звичайна", "Підвищена")


@dataclass
class OverviewStats:
    students: int
    debtors: int
    debtors_percent: float | None
    ordinary: int
    higher: int


@dataclass
class GroupStats:
    name: str
    students: int
    average: Decimal | None        # середній рейтинг студентів групи
    debtors: int                   # студенти хоча б з одним боргом
    debtors_percent: float | None
    budget_students: int
    recipients: int                # стипендіати
    recipients_percent: float | None   # частка серед бюджетників групи


@dataclass
class SubjectStats:
    name: str
    subject_type: str
    students: int                  # студенти з числовою оцінкою
    debts: int
    debts_percent: float | None
    average: Decimal | None


def _percent(part, total):
    return None if total == 0 else part * 100 / total


def _mean(values):
    if not values:
        return None

    return sum(values, ZERO) / Decimal(len(values))


def format_percent(value):
    return "—" if value is None else f"{value:.1f}%"


def calculate_overview(result):
    students = result.students

    debtors = sum(1 for student in students if student.debts > 0)

    ordinary = sum(
        1 for student in result.budget_students
        if student.scholarship == "Звичайна"
    )

    higher = sum(
        1 for student in result.budget_students
        if student.scholarship == "Підвищена"
    )

    return OverviewStats(
        students=len(students),
        debtors=debtors,
        debtors_percent=_percent(debtors, len(students)),
        ordinary=ordinary,
        higher=higher,
    )


def calculate_group_stats(result):
    budget_ids = {id(student) for student in result.budget_students}

    by_group = {name: [] for name in result.group_names}

    for student in result.students:
        by_group.setdefault(student.group_name, []).append(student)

    stats = []

    for name, students in by_group.items():

        if not students:
            continue

        ratings = [
            student.rating
            for student in students
            if student.rating is not None
        ]

        debtors = sum(1 for student in students if student.debts > 0)

        budget = [
            student for student in students
            if id(student) in budget_ids
        ]

        recipients = sum(
            1 for student in budget
            if student.scholarship in SCHOLARSHIPS
        )

        stats.append(GroupStats(
            name=name,
            students=len(students),
            average=round_down_2(_mean(ratings)),
            debtors=debtors,
            debtors_percent=_percent(debtors, len(students)),
            budget_students=len(budget),
            recipients=recipients,
            recipients_percent=_percent(recipients, len(budget)),
        ))

    return stats


def calculate_subject_stats(result):
    subject_type_map = result.analysis["subject_type_map"]
    subject_name_map = result.analysis["subject_name_map"]

    stats = []

    for subject_id in sorted(subject_type_map):

        values = []

        for student in result.students:

            mark = student.marks.get(subject_id, "-")

            # Порожня клітинка існуючого предмета = 0 і борг
            if mark is None:
                value = ZERO
            else:
                value = to_decimal(mark)

                # "-", "н/б", "звіл" та інший текст не враховуємо
                if value is None:
                    continue

            values.append(value)

        # Предмети без числових оцінок (наприклад, звичайні заліки) пропускаємо
        if not values:
            continue

        debts = sum(1 for value in values if value < DEBT_THRESHOLD)

        stats.append(SubjectStats(
            name=subject_name_map[subject_id],
            subject_type=subject_type_map[subject_id],
            students=len(values),
            debts=debts,
            debts_percent=_percent(debts, len(values)),
            average=round_down_2(_mean(values)),
        ))

    return stats