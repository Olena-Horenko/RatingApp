from datetime import datetime

from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment, PatternFill

from rating import (
    ALIGN_CENTER,
    ALIGN_HEADER,
    ALIGN_LEFT,
    FONT,
    FONT_BOLD,
    build_rating_structure,
    fill_rating_students
)

from rating_rules import GENERAL_NOTES, describe_rules
from rounding import round_down_2
from table_colors import DEFAULT_COLORS

DATABASE_SHEET = "БазаДаних"
PARAMETERS_SHEET = "Параметри"

HEADER_FILL = PatternFill(
    fill_type="solid",
    fgColor="E6E6E6"
)

MAX_COLUMN_WIDTH = 40

def _display_stat(value):
    rounded = round_down_2(value)

    if rounded is None:
        return "-"

    return rounded

def _text_width(value):
    """Ширина самой длинной строки в значении ячейки."""
    if value is None:
        return 0

    lines = str(value).splitlines() or [""]

    return max(len(line) for line in lines)


def build_database_sheet(workbook, students, analysis):
    """
    Создаёт лист БазаДаних:
    заголовки, студенты с оценками и статистика.
    """

    worksheet = workbook.create_sheet(DATABASE_SHEET)

    subject_type_map = analysis["subject_type_map"]
    subject_name_map = analysis["subject_name_map"]

    subject_ids = sorted(subject_type_map.keys())

    # ── Заголовки ──

    headers = ["ПІБ", "Б/К", "Група"]

    for subject_id in subject_ids:

        subject_name = subject_name_map[subject_id]
        subject_type = subject_type_map[subject_id]

        if subject_type == "ІСП":
            headers.append(subject_name)
        else:
            # КР, КП, ЗАЛ — тип в скобках
            headers.append(f"{subject_name} ({subject_type})")

    headers.extend([
        "Сер. бал (ІСП)",
        "Сер. бал (КР)",
        "Сер. бал (диференційовані заліки)",
        "Рейтинг",
        "Загальний середній",
        "Кількість боргів"
    ])

    # Ширина колонок считается по ходу записи
    widths = [_text_width(header) for header in headers]

    worksheet.append(headers)

    # ── Студенты ──

    for student in students:

        row = [
            student.pib,
            student.bk,
            student.group_name,
        ]

        row.extend(
            student.marks.get(subject_id, "-")
            for subject_id in subject_ids
        )

        row.extend([
            _display_stat(student.exam_average),
            _display_stat(student.course_average),
            _display_stat(student.practice_average),
            _display_stat(student.rating),
            _display_stat(student.total_average),
            student.debts,
        ])

        for index, value in enumerate(row):
            width = _text_width(value)

            if width > widths[index]:
                widths[index] = width

        worksheet.append(row)

    # ── Ширина колонок ──

    for index, width in enumerate(widths, start=1):
        worksheet.column_dimensions[
            get_column_letter(index)
        ].width = min(width + 2, MAX_COLUMN_WIDTH)

    # ── Оформление ──

    for cell in worksheet[1]:
        cell.font = FONT_BOLD
        cell.fill = HEADER_FILL
        cell.alignment = ALIGN_HEADER

    for row in worksheet.iter_rows(min_row=2):

        for cell in row:
            cell.font = FONT
            cell.alignment = ALIGN_CENTER

        # ПІБ — слева
        row[0].alignment = ALIGN_LEFT

    return worksheet


def build_parameters_sheet(workbook, rules, budget_students=None, now=None):
    """
    Лист «Параметри»: за якими правилами пораховано рейтинг.
    Так за друкованим списком завжди можна дізнатися відсотки й пороги.
    """
    worksheet = workbook.create_sheet(PARAMETERS_SHEET)

    wrap = Alignment(
        horizontal="left", vertical="top", wrap_text=True
    )

    def add_row(label, text="", bold=False, fill=None):
        worksheet.append([label, text])
        row = worksheet[worksheet.max_row]

        for cell in row:
            cell.font = FONT_BOLD if bold else FONT
            cell.alignment = wrap

            if fill is not None:
                cell.fill = fill

    now = now or datetime.now()

    add_row("Параметри розрахунку рейтингу", bold=True, fill=HEADER_FILL)
    add_row("Дата розрахунку", now.strftime("%d.%m.%Y %H:%M"))

    if budget_students is not None:
        ordinary = sum(
            1 for student in budget_students
            if student.scholarship == "Звичайна"
        )
        higher = sum(
            1 for student in budget_students
            if student.scholarship == "Підвищена"
        )

        add_row("Бюджетних студентів у розрахунку", len(budget_students))
        add_row(
            "Призначено стипендій",
            f"стандартних: {ordinary}, підвищених: {higher}"
        )

    for title, rows in describe_rules(rules):
        add_row("")
        add_row(title, bold=True, fill=HEADER_FILL)

        for label, text in rows:
            add_row(label, text)

    add_row("")

    for note in GENERAL_NOTES:
        add_row("Примітка", note)

    worksheet.column_dimensions["A"].width = 34
    worksheet.column_dimensions["B"].width = 70

    # Друк: усі стовпці на одній сторінці по ширині
    worksheet.page_setup.orientation = "landscape"
    worksheet.page_setup.fitToWidth = 1
    worksheet.page_setup.fitToHeight = 0
    worksheet.sheet_properties.pageSetUpPr.fitToPage = True

    return worksheet


def _neutralize_formulas(workbook):
    """
    Превращает «формулы» обратно в обычный текст.

    openpyxl считает формулой любую строку, начинающуюся с "=".
    Данные приходят из чужих журналов, поэтому такая строка (в ПІБ, Б/К
    или оценке) попала бы в рейтинг как работающая формула.
    Собственных формул программа не пишет, поэтому все они лишние.
    """
    for worksheet in workbook.worksheets:

        for row in worksheet.iter_rows():

            for cell in row:

                if cell.data_type == "f":
                    cell.data_type = "s"


def save_database_file(
    file_path,
    students,
    analysis,
    debt_free_students=None,
    debtors=None,
    colors=DEFAULT_COLORS,
    rules=None
):
    workbook = Workbook()

    default_sheet = workbook.active
    workbook.remove(default_sheet)

    # БазаДаних
    build_database_sheet(
        workbook,
        students,
        analysis
    )

    # У Рейтинг відображаються тільки студенти без боргів
    if debt_free_students is not None:

        worksheet = build_rating_structure(
            workbook,
            analysis,
            sheet_name="Рейтинг",
            include_debts=False,
            colors=colors
        )

        fill_rating_students(
            worksheet,
            debt_free_students,
            analysis,
            include_debts=False,
            colors=colors
        )

    # Створення листу Рейтинг_боржники
    if debtors:

        debtor_worksheet = build_rating_structure(
            workbook,
            analysis,
            sheet_name="Рейтинг_боржники",
            include_debts=True,
            colors=colors
        )

        fill_rating_students(
            debtor_worksheet,
            debtors,
            analysis,
            include_debts=True,
            colors=colors
        )

    # Параметри розрахунку: за якими правилами пораховано рейтинг
    if rules is not None:

        budget_students = (
            None
            if debt_free_students is None and debtors is None
            else list(debt_free_students or []) + list(debtors or [])
        )

        build_parameters_sheet(workbook, rules, budget_students)

    # Чужі дані не повинні потрапити в рейтинг як формули
    _neutralize_formulas(workbook)
    
    # Збереження
    workbook.save(file_path)
    workbook.close()