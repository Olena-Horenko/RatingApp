from decimal import Decimal
from functools import lru_cache

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from rating_rules import DEFAULT_RULES
from rounding import round_down_2, to_decimal
from scoring import DEBT_THRESHOLD
from subject_utils import get_subject_groups
from table_colors import DEFAULT_COLORS, HEADER_SECOND_COLOR
from text_utils import norm

# ──────────────────────────────────────────────
#  Стили листа рейтинга (создаются один раз)
# ──────────────────────────────────────────────

FONT = Font(name="Calibri", size=11)

ALIGN_CENTER = Alignment(horizontal="center", vertical="center")
ALIGN_LEFT = Alignment(horizontal="left", vertical="center")

_THIN_SIDE = Side(style="thin", color="D9D9D9")
_THICK_SIDE = Side(style="medium", color="9A9A9A")

BORDER_BOTTOM = Border(bottom=_THIN_SIDE)
BORDER_BLOCK_START = Border(left=_THICK_SIDE, bottom=_THIN_SIDE)


@lru_cache(maxsize=None)
def _solid(color):
    return PatternFill(fill_type="solid", fgColor=color)


SUBJECT_BLOCKS = ("exam", "course", "practice")

AVERAGE_ATTRIBUTE = {
    "exam": "exam_average",
    "course": "course_average",
    "practice": "practice_average",
}

# ── Шапка ──

FONT_BOLD = Font(name="Calibri", size=11, bold=True)

ALIGN_HEADER = Alignment(
    horizontal="center",
    vertical="center",
    wrap_text=True
)

BORDER_HEADER = Border(top=_THIN_SIDE, bottom=_THIN_SIDE)

BORDER_HEADER_BLOCK_START = Border(
    left=_THICK_SIDE,
    top=_THIN_SIDE,
    bottom=_THIN_SIDE
)

BLOCK_TITLES = {
    "exam": "екзамени",
    "course": "курсові проекти та роботи",
    "practice": "диференційовані заліки, захисти звітів практик",
}

def is_budget_student(student):
    """
    Проверяет форму обучения.

    Если Б/К начинается с буквы К — студент контрактной формы.
    Пустое значение и остальные значения считаются бюджетом.
    """

    bk = norm(student.bk)

    if bk.startswith("К"):
        return False

    return True


def get_budget_students(students):
    """
    Возвращает только студентов бюджетной формы обучения.
    """

    budget_students = []

    for student in students:
        if is_budget_student(student):
            budget_students.append(student)

    return budget_students

def get_debtors(students):
    """
    Возвращает студентов, у которых есть хотя бы один долг.
    """
    return [
        student
        for student in students
        if student.debts > 0
    ]
    
def get_debt_free_students(students):
    """
    Возвращает студентов без задолженностей.
    """
    return [
        student
        for student in students
        if student.debts == 0
    ]

def _rating_key(value):

    number = to_decimal(value)
    return Decimal("-1") if number is None else number

def _display_mark(value):
    if value is None:
        return 0

    return value

def sort_rating_students(students):

    return sorted(
        students,
        key=lambda student: (
            _rating_key(student.rating),
            _rating_key(student.total_average),
        ),
        reverse=True
    )
    
def _meets_requirements(student, min_mark, min_rating=None):
    """
    Чи підходить студент під умови стипендії:
    немає боргів, усі числові оцінки >= min_mark
    і (якщо min_rating задано) рейтинговий бал >= min_rating.
    """

    if student.debts > 0:
        return False

    if min_rating is not None and (
        student.rating is None
        or _rating_key(student.rating) < Decimal(min_rating)
    ):
        return False

    for mark in student.marks.values():

        # Пустая оценка = 0 -> не подходит
        if mark is None:
            return False

        number = to_decimal(mark)

        # "звіл", "н/б", "-" и другие тексты игнорируем
        if number is None:
            continue

        if number < min_mark:
            return False

    return True


def _is_small_group(total, enabled, limit):
    return enabled and 1 <= total < limit


def ordinary_quota(total, rules=DEFAULT_RULES):
    """Скільки стандартних стипендій припадає на total бюджетників."""

    if _is_small_group(
        total,
        rules.ordinary_small_group,
        rules.ordinary_small_group_limit
    ):
        return min(rules.ordinary_small_group_count, total)

    return total * rules.ordinary_percent // 100


def higher_quota(total, rules=DEFAULT_RULES):
    """Скільки підвищених стипендій припадає на total бюджетників."""

    if _is_small_group(
        total,
        rules.higher_small_group,
        rules.higher_small_group_limit
    ):
        return min(rules.higher_small_group_count, total)

    return total * rules.higher_percent // 100


def calculate_scholarships(budget_students, rules=DEFAULT_RULES):
    """
    Назначает стипендии (student.scholarship) бюджетным студентам.

    Студенти перебираються зверху вниз за рейтингом; якщо студент не
    підходить, перевіряється наступний (місце не пропадає).
    Підвищені стипендії входять у загальну кількість стандартних.

    Возвращает тот же набор студентов, отсортированный по рейтингу
    (от большего к меньшему). Вызывающий код опирается на этот порядок.
    """

    for student in budget_students:
        student.scholarship = "-"

    sorted_students = sort_rating_students(
        budget_students
    )

    total = len(sorted_students)

    # --------------------------------
    # Повышенная стипендия
    # --------------------------------

    higher_limit = higher_quota(total, rules)
    higher_count = 0

    for student in sorted_students:

        if higher_count >= higher_limit:
            break

        if _meets_requirements(
            student,
            rules.higher_min_mark,
            rules.higher_min_rating
        ):
            student.scholarship = "Підвищена"
            higher_count += 1

    # --------------------------------
    # Обычная стипендия
    # --------------------------------

    small_group = _is_small_group(
        total,
        rules.ordinary_small_group,
        rules.ordinary_small_group_limit
    )

    # Рейтинговий бал перевіряється лише в малих групах
    min_rating = (
        rules.ordinary_small_group_min_rating
        if small_group
        else None
    )

    ordinary_limit = ordinary_quota(total, rules)

    # Підвищені стипендіати вже займають місця зі стандартної квоти
    given = higher_count

    for student in sorted_students:

        if given >= ordinary_limit:
            break

        if student.scholarship != "-":
            continue

        if _meets_requirements(
            student,
            rules.ordinary_min_mark,
            min_rating
        ):
            student.scholarship = "Звичайна"
            given += 1

    return sorted_students

HEADER_CHARS_PER_LINE = 14   # ширина колонки 16 минус поля, жирный шрифт
HEADER_LINE_HEIGHT = 15
HEADER_MIN_HEIGHT = 45
HEADER_MAX_HEIGHT = 409      # предел высоты строки в Excel


def _count_wrapped_lines(text, width):
    """Сколько строк займёт текст при переносе по словам."""
    lines = 1
    current = 0

    for word in str(text).split():

        # Слово длиннее строки Excel режет по символам
        while len(word) > width:
            if current > 0:
                lines += 1
                current = 0

            word = word[width:]
            lines += 1

        if current == 0:
            current = len(word)
        elif current + 1 + len(word) <= width:
            current += 1 + len(word)
        else:
            lines += 1
            current = len(word)

    return lines

def build_rating_structure(
    workbook,
    analysis,
    sheet_name="Рейтинг",
    include_debts=True,
    colors=DEFAULT_COLORS
):
    """
    Создаёт лист с двухуровневой шапкой.
    Расположение колонок берётся из _get_column_layout,
    поэтому шапка всегда совпадает со строками студентов.
    """

    worksheet = workbook.create_sheet(sheet_name)

    layout = _get_column_layout(
        analysis,
        include_debts
    )

    subject_name_map = analysis["subject_name_map"]
    
    max_header_lines = 1 

    max_column = layout["max_column"]

    # ── Значения ──

    def merged_header(column, title):
        """Заголовок, объединённый по двум строкам шапки."""
        worksheet.cell(row=1, column=column, value=title)
        worksheet.merge_cells(
            start_row=1,
            start_column=column,
            end_row=2,
            end_column=column
        )

    merged_header(layout["number"], "№")
    merged_header(layout["pib"], "ПІБ")
    merged_header(layout["group"], "Група")

    if include_debts:
        merged_header(layout["debts"], "Кількість боргів")

    for key in SUBJECT_BLOCKS:

        block = layout[key]

        if block["start"] is None:
            continue

        # Верхняя строка: название блока на всю его ширину
        worksheet.cell(
            row=1,
            column=block["start"],
            value=BLOCK_TITLES[key]
        )

        # Нижняя строка: предметы
        for offset, subject_id in enumerate(block["subjects"]):

            subject_name = subject_name_map[subject_id]

            max_header_lines = max(
                max_header_lines,
                _count_wrapped_lines(
                    subject_name, HEADER_CHARS_PER_LINE
                )
            )
            
            worksheet.cell(
                row=2,
                column=block["start"] + offset,
                value=subject_name
            )

        worksheet.cell(
            row=2,
            column=block["average"],
            value="Середня оцінка"
        )

        worksheet.merge_cells(
            start_row=1,
            start_column=block["start"],
            end_row=1,
            end_column=block["average"]
        )

    merged_header(layout["rating"], "Рейтинг")
    merged_header(layout["scholarship"], "Стипендія")
    merged_header(layout["total_average"], "Загальний середній")

    # ── Оформление шапки ──

    block_start_columns = _block_start_columns(layout)

    for column in range(1, max_column + 1):

        border = (
            BORDER_HEADER_BLOCK_START
            if column in block_start_columns
            else BORDER_HEADER
        )

        for row, fill in (
            (1, _solid(colors.header)),
            (2, _solid(HEADER_SECOND_COLOR))
        ):
            cell = worksheet.cell(row=row, column=column)

            cell.font = FONT_BOLD
            cell.fill = fill
            cell.alignment = ALIGN_HEADER
            cell.border = border

    # ── Ширина колонок и высота строк ──

    worksheet.column_dimensions["A"].width = 4
    worksheet.column_dimensions["B"].width = 32
    worksheet.column_dimensions["C"].width = 12

    first_other_column = 4

    if include_debts:
        worksheet.column_dimensions[
            get_column_letter(layout["debts"])
        ].width = 12

        first_other_column = 5

    for column in range(first_other_column, max_column + 1):
        worksheet.column_dimensions[
            get_column_letter(column)
        ].width = 16

    # «Загальний середній» нужен только для сортировки, колонку скрываем
    worksheet.column_dimensions[
        get_column_letter(layout["total_average"])
    ].hidden = True

    worksheet.row_dimensions[1].height = 30
    worksheet.row_dimensions[2].height = min(
        max(
            HEADER_MIN_HEIGHT,
            max_header_lines * HEADER_LINE_HEIGHT + 4
        ),
        HEADER_MAX_HEIGHT
    )

    return worksheet

def _is_debt_mark(value):
    number = to_decimal(value)
    return number is not None and number < DEBT_THRESHOLD

def fill_rating_students(
    worksheet,
    budget_students,
    analysis,
    include_debts=True,
    colors=DEFAULT_COLORS
):
    """
    Заполняет лист Рейтинг студентами
    бюджетной формы обучения.
    """

    layout = _get_column_layout(
        analysis,
        include_debts
    )

    # Берём из layout, а не из worksheet.max_column:
    # у worksheet это свойство каждый раз перебирает все ячейки.
    max_column = layout["max_column"]

    block_start_columns = _block_start_columns(layout)

    for number, student in enumerate(
        budget_students,
        start=1
    ):

        row = number + 2
        shaded = number % 2 == 1

        # ── Значения ──

        worksheet.cell(row=row, column=1, value=number)
        worksheet.cell(row=row, column=2, value=student.pib)
        worksheet.cell(row=row, column=3, value=student.group_name)

        if include_debts:
            worksheet.cell(
                row=row,
                column=layout["debts"],
                value=student.debts
            )

        debt_columns = []

        for key in SUBJECT_BLOCKS:

            block = layout[key]

            if block["start"] is None:
                continue

            for offset, subject_id in enumerate(block["subjects"]):

                column = block["start"] + offset

                value = _display_mark(
                    student.marks.get(subject_id, "-")
                )

                worksheet.cell(
                    row=row,
                    column=column,
                    value=value
                )

                if include_debts and _is_debt_mark(value):
                    debt_columns.append(column)

            worksheet.cell(
                row=row,
                column=block["average"],
                value=round_down_2(
                    getattr(student, AVERAGE_ATTRIBUTE[key])
                )
            )

        worksheet.cell(
            row=row,
            column=layout["rating"],
            value=round_down_2(student.rating)
        )

        worksheet.cell(
            row=row,
            column=layout["scholarship"],
            value=student.scholarship
        )

        worksheet.cell(
            row=row,
            column=layout["total_average"],
            value=round_down_2(student.total_average)
        )

        # ── Оформление: каждой ячейке один раз ──

        scholarship_color = colors.scholarship_color(
            student.scholarship,
            shaded
        )

        row_fill = _solid(
            colors.row_color(shaded)
            if scholarship_color is None
            else scholarship_color
        )

        for column in range(1, max_column + 1):

            cell = worksheet.cell(row=row, column=column)

            cell.font = FONT
            cell.alignment = ALIGN_CENTER
            cell.border = BORDER_BOTTOM
            cell.fill = row_fill

        # ── Исключения поверх базового оформления ──

        # ПІБ: выравнивание слева; без стипендии цвет другой
        pib_cell = worksheet.cell(row=row, column=2)
        pib_cell.alignment = ALIGN_LEFT

        if scholarship_color is None:
            pib_cell.fill = _solid(colors.pib_color(shaded))

        # Подсветка долгов
        if include_debts:

            debt_fill = _solid(colors.debt_color(shaded))

            worksheet.cell(
                row=row,
                column=layout["debts"]
            ).fill = debt_fill

            for column in debt_columns:
                worksheet.cell(
                    row=row,
                    column=column
                ).fill = debt_fill

        # Толстые границы между блоками
        for column in block_start_columns:
            worksheet.cell(
                row=row,
                column=column
            ).border = BORDER_BLOCK_START

def _block_start_columns(layout):
    """Колонки, слева от которых проходит толстая граница."""

    columns = [
        layout[key]["start"]
        for key in SUBJECT_BLOCKS
        if layout[key]["start"] is not None
    ]

    columns.append(layout["rating"])

    return columns

def _get_column_layout(
    analysis,
    include_debts=True
):
    groups = get_subject_groups(analysis)

    columns = {
        "number": 1,
        "pib": 2,
        "group": 3,
        "debts": 4 if include_debts else None,
    }

    column = 5 if include_debts else 4

    for key in SUBJECT_BLOCKS:

        subject_ids = groups[key]

        block = {
            "subjects": subject_ids,
            "start": None,
            "average": None,
        }

        if subject_ids:

            block["start"] = column
            column += len(subject_ids)

            block["average"] = column
            column += 1

        columns[key] = block

    columns["rating"] = column
    column += 1

    columns["scholarship"] = column
    column += 1

    columns["total_average"] = column
    columns["max_column"] = column

    return columns