from models import Specialty, Course, Group, DatabaseStudent
import re

from text_utils import norm, norm_key
from rounding import to_decimal
from openpyxl.utils import get_column_letter

class SheetData:
    """
    Снимок листа в памяти.

    Нумерация строк и колонок с 1, как в Excel, поэтому
    sheet.value(row, col) заменяет ws.cell(row=row, column=col).value
    """

    def __init__(self, rows):
        self.rows = rows
        self.max_row = len(rows)
        self.max_column = max(
            (len(row) for row in rows),
            default=0
        )

    def value(self, row, column):
        if 1 <= row <= self.max_row:
            cells = self.rows[row - 1]

            if 1 <= column <= len(cells):
                return cells[column - 1]

        return None


def read_sheets(workbook, sheet_names):
    """
    Читает указанные листы в память один раз.
    Возвращает: {имя_листа: SheetData}
    """

    sheets = {}

    for name in sheet_names:

        ws = workbook[name]

        # В режиме read_only размеры листа могут быть записаны
        # в файле неверно. Пусть openpyxl определит их по данным.
        if hasattr(ws, "reset_dimensions"):
            ws.reset_dimensions()

        sheets[name] = SheetData(
            list(
                ws.iter_rows(values_only=True)
            )
        )

    return sheets

def parse_sheet_name(sheet_name):
    """
    Разбирає назву листа по формату XX-123.

    Повертає: (specialty, course, group_name)
    або: None
    """

    sheet_name = sheet_name.strip()

    parts = sheet_name.split("-")

    if len(parts) != 2:
        return None

    if len(parts[0]) != 2:
        return None

    if len(parts[1]) != 3:
        return None

    if not parts[1].isdigit():
        return None

    specialty = parts[0].upper()
    course = parts[1][:2]
    group_name = sheet_name.upper()

    return specialty, course, group_name


def build_journal_structure(workbook):
    """
    Будує стуруктуру: специальность -> курс -> группа

    Повертає: specialties, ignored_sheets
    """

    specialties = []
    ignored_sheets = []

    for sheet_name in workbook.sheetnames:

        parsed = parse_sheet_name(sheet_name)

        if parsed is None:
            ignored_sheets.append(sheet_name)
            continue

        specialty_name, course_name, group_name = parsed

        specialty = next(
            (
                item
                for item in specialties
                if item.name == specialty_name
            ),
            None
        )

        if specialty is None:
            specialty = Specialty(specialty_name)
            specialties.append(specialty)

        course = next(
            (
                item
                for item in specialty.courses
                if item.name == course_name
            ),
            None
        )

        if course is None:
            course = Course(course_name)
            specialty.add_course(course)

        course.add_group(Group(group_name))

    return specialties, ignored_sheets


def get_selected_sheets(workbook, selected_groups):

    selected_groups_upper = {
        group.upper()
        for group in selected_groups
    }

    return [
        sheet_name
        for sheet_name in workbook.sheetnames
        if sheet_name.upper() in selected_groups_upper
    ]

def validate_selected_groups(
    sheets,
    selected_sheets
):
    """
    Перевіряє усі обрані групи.

    Повертає: valid_sheets — групи, які можно обробляти;
              errors — список проблемних груп.
    """

    valid_sheets = []
    errors = []

    for sheet_name in selected_sheets:

        sheet = sheets[sheet_name]

        columns = find_main_columns(sheet)

        col_pib = columns["col_pib"]

        # Перевірка стовбця ПІБ
        if col_pib is None:

            errors.append(
                f'Групу "{sheet_name}" не оброблено: '
                f'не знайдено колонку "ПІБ".'
            )

            continue

        # Перевірка рядків студентів
        rows = find_student_rows(
            sheet,
            col_pib
        )

        first_row = rows["first_student_row"]
        last_row = rows["last_student_row"]

        if (
            first_row == 0
            or last_row == 0
        ):

            errors.append(
                f'Групу "{sheet_name}" не оброблено: '
                f'не знайдено рядків студентів.'
            )

            continue
        
        # Перевірка повторюваних дисциплін
        seen_columns = {}
        has_duplicates = False

        for col, name, subject_type in read_sheet_subjects(sheet):

            key = f"{norm_key(name)}|{subject_type}"

            if key in seen_columns:

                errors.append(
                    f'Групу "{sheet_name}" не оброблено: '
                    f'дисципліна "{name}" ({subject_type}) '
                    f'повторюється у колонках '
                    f'{get_column_letter(seen_columns[key])} і '
                    f'{get_column_letter(col)}.'
                )

                has_duplicates = True
                continue

            seen_columns[key] = col

        if has_duplicates:
            continue
        
        # Група пройшла перевірку
        valid_sheets.append(
            sheet_name
        )

    return valid_sheets, errors

def find_main_columns(sheet):
    """
    Знаходить основні стовбці журналу: П.І.Б. / ПІБ; Б/К / Б/К.
    """

    col_pib = None
    col_bk = None

    for col in range(1, sheet.max_column + 1):

        txt = norm(sheet.value(1, col))

        if txt in ("П.І.Б.", "ПІБ"):
            col_pib = col

        elif txt in ("Б/К", "Б/К."):
            col_bk = col

    return {
        "col_pib": col_pib,
        "col_bk": col_bk
    }


def find_student_rows(sheet, col_pib):
    """
    Знаходить перший та останній рядок студентів.
    """

    first_student_row = 0

    for row in range(2, sheet.max_row + 1):

        value = sheet.value(row, col_pib)

        if value is not None and str(value).strip() != "":
            first_student_row = row
            break

    last_student_row = 0

    for row in range(sheet.max_row, 1, -1):

        value = sheet.value(row, col_pib)

        if value is not None and str(value).strip() != "":
            last_student_row = row
            break

    return {
        "first_student_row": first_student_row,
        "last_student_row": last_student_row
    }

def get_subject_type(sheet, subject_col):
    """
    Визначає тип дисципліни, шукає серед перших 20 рядків: ІСП, КР, КП, ЗАЛ.
    """

    for row in range(1, 21):

        txt = norm(sheet.value(row, subject_col))

        if txt in ("ІСП", "КР", "КП", "ЗАЛ"):
            return txt

    return ""

def get_subject_name(sheet, subject_col, subject_type):
    """
    Находит название дисциплины.

    Сначала ищет строку с типом дисциплины:
    ІСП, КР, КП или ЗАЛ.

    Затем идёт вверх и ищет первое подходящее
    текстовое значение.

    Пропускает:
    - пустые ячейки;
    - даты;
    - числовые значения;
    - строки, состоящие только из цифр.
    """

    found_row = 0

    # ==========================================
    # 1. Ищем тип дисциплины
    # ==========================================

    for row in range(1, 21):

        txt = norm(sheet.value(row, subject_col))

        if txt == norm(subject_type):
            found_row = row
            break

    if found_row == 0:
        return ""

    # ==========================================
    # 2. Ищем название выше типа
    # ==========================================

    for row in range(found_row - 1, 0, -1):

        value = sheet.value(row, subject_col)

        if value is None:
            continue

        txt = str(value).strip()

        # Названием считаем первую ячейку выше типа, где есть буквы.
        # Это автоматически отсеивает даты, числа и строки из цифр.
        if re.search(r"[A-Za-zА-Яа-яІіЇїЄєҐґ]", txt):
            return txt

    return ""


def read_sheet_subjects(sheet):
    """
    Возвращает предметы листа: [(колонка, название, тип), ...]
    Колонки без типа или без названия пропускаются.
    """

    subjects = []

    for subject_col in range(4, sheet.max_column + 1):

        subject_type = get_subject_type(
            sheet,
            subject_col
        )

        if subject_type == "":
            continue

        subject_name = get_subject_name(
            sheet,
            subject_col,
            subject_type
        )

        # Для отображения убираем лишние пробелы и переносы строк
        subject_name = " ".join(subject_name.split())

        if subject_name == "":
            continue

        subjects.append(
            (subject_col, subject_name, subject_type)
        )

    return subjects


def analyze_selected_groups(sheets, selected_sheets):
    """
    Анализирует выбранные группы.

    Формирует внутренние структуры:

    subject_type_map   — id предмета -> тип (ІСП / КР / КП / ЗАЛ)
    subject_name_map   — id предмета -> название
    group_column_map   — "группа|id предмета" -> колонка в журнале

    Ожидает группы, уже прошедшие validate_selected_groups
    (без повторяющихся дисциплин).
    """

    subject_dictionary = {}
    subject_type_map = {}
    subject_name_map = {}
    group_column_map = {}

    next_subject_id = 1

    for sheet_name in selected_sheets:

        sheet = sheets[sheet_name]

        for col, subject_name, subject_type in read_sheet_subjects(sheet):

            key = f"{norm_key(subject_name)}|{subject_type}"

            if key in subject_dictionary:

                subject_id = subject_dictionary[key]

            else:

                subject_id = next_subject_id

                subject_dictionary[key] = subject_id
                subject_type_map[subject_id] = subject_type
                subject_name_map[subject_id] = subject_name

                next_subject_id += 1

            group_column_map[
                f"{sheet_name}|{subject_id}"
            ] = col

    return {
        "subject_type_map": subject_type_map,
        "subject_name_map": subject_name_map,
        "group_column_map": group_column_map
    }


def import_students(sheets, selected_sheets, analysis):
    """
    Импортирует студентов из выбранных групп.

    Логика соответствует VBA ImportStudents:

    ПІБ
    Б/К
    Група
    оценки по предметам

    Пустая оценка существующего предмета -> None.
    При расчёте None расматривается как 0 и считается долгом.
    
    Если предмет отсутствует у группы -> "-".
    """

    students = []

    subject_type_map = analysis["subject_type_map"]
    group_column_map = analysis["group_column_map"]

    subject_ids = sorted(subject_type_map.keys())

    for sheet_name in selected_sheets:

        sheet = sheets[sheet_name]

        columns = find_main_columns(sheet)

        col_pib = columns["col_pib"]
        col_bk = columns["col_bk"]

        if col_pib is None:
            raise ValueError(
                f'Групу "{sheet_name}" не оброблено: '
                f'не знайдено колонку "ПІБ".'
            )

        rows = find_student_rows(
            sheet,
            col_pib
        )

        first_row = rows["first_student_row"]
        last_row = rows["last_student_row"]

        if first_row == 0 or last_row == 0:
            raise ValueError(
                f'Групу "{sheet_name}" не оброблено: '
                f'не знайдено рядків студентів.'
            )

        for row in range(first_row, last_row + 1):

            pib_value = sheet.value(row, col_pib)

            if pib_value is None:
                continue

            pib = str(pib_value).strip()

            if pib == "":
                continue

            if col_bk is not None:

                bk_value = sheet.value(row, col_bk)

                bk = (
                    ""
                    if bk_value is None
                    else str(bk_value).strip()
                )

            else:

                bk = ""

            student = DatabaseStudent(
                pib=pib,
                group_name=sheet_name,
                bk=bk
            )

            for subject_id in subject_ids:

                group_key = (
                    f"{sheet_name}|{subject_id}"
                )

                if group_key in group_column_map:

                    journal_col = group_column_map[group_key]

                    mark = sheet.value(row, journal_col)

                    if mark is None or str(mark).strip() == "":
                        mark = None

                    elif isinstance(mark, str):
                        number = to_decimal(mark)

                        # "85" / "85,5" -> настоящее число; "н/б", "звіл" остаются текстом
                        if number is not None:
                            mark = number
                    
                    student.marks[subject_id] = mark

                else:

                    student.marks[subject_id] = "-"

            students.append(student)

    return students