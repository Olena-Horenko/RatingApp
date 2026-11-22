"""
Архів сесій: формули курсу та семестру, збереження порахованих журналів.
Чиста логіка без Qt.

Структура папки архіву:

    <ARCHIVE_DIR>/
        groups.json            — налаштування груп (магістр, рік вступу)
        2026-27/
            winter/
                АМ-231.json    — одна група за одну сесію
            summer/
"""

import json
import os
import re
import tempfile
import shutil
from datetime import date, datetime, timedelta

from rounding import to_decimal
from text_utils import norm, norm_key

# Де лежить архів. Змінити місце можна тут, в одному рядку.
ARCHIVE_DIR = os.path.join(os.path.expanduser("~"), "RatingArchive")

SESSIONS = ("winter", "summer")
SESSION_LABELS = {"winter": "Зимова", "summer": "Літня"}

FORMAT_VERSION = 1
SETTINGS_FILE = "groups.json"


# ──────────────────────────────────────────────
#  Навчальний рік, курс, семестр
# ──────────────────────────────────────────────

MAX_YEARS_BACK = 15

# Орієнтири навчального календаря: (місяць, день).
ACADEMIC_YEAR_START = (9, 1)      # початок навчального року
WINTER_SESSION_START = (12, 1)    # з цього дня зимова вважається настала
SUMMER_SESSION_START = (7, 1)     # з цього дня літня вважається настала


def _since(today, start):
    """True, якщо сьогодні не раніше за (місяць, день) у поточному році."""
    return (today.month, today.day) >= start


def default_academic_year(today=None):
    today = today or date.today()

    return (
        today.year
        if _since(today, ACADEMIC_YEAR_START)
        else today.year - 1
    )


def latest_session(today=None):
    today = today or date.today()
    year = default_academic_year(today)

    if (
        _since(today, WINTER_SESSION_START)
        or not _since(today, SUMMER_SESSION_START)
    ):
        return year, "winter"

    if not _since(today, ACADEMIC_YEAR_START):
        return year, "summer"

    return year - 1, "summer"


def session_years(today=None):
    """Навчальні роки для вибору: від поточного до MAX_YEARS_BACK років тому."""
    top = default_academic_year(today)

    return list(range(top, top - MAX_YEARS_BACK - 1, -1))

def max_admission_year(today=None):
    """Не пізніше початку поточного навчального року."""
    return default_academic_year(today)


def min_admission_year(today=None):
    return max_admission_year(today) - MAX_YEARS_BACK


def academic_year_label(start_year):
    """2026 -> '2026/27'"""
    return f"{start_year}/{(start_year + 1) % 100:02d}"


def academic_year_folder(start_year):
    """2026 -> '2026-27' (для імені папки)"""
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def group_key(group_name):
    """
    Єдиний вигляд назви групи для файлів і налаштувань.
    norm() ще й замінює латинські двійники кирилицею (AM-231 = АМ-231).
    """
    return norm(group_name)


def admission_year(group_name):
    """'АМ-231' -> 2023. None, якщо назва не за форматом XX-123."""
    match = re.fullmatch(r".{2}-(\d{2})\d", group_key(group_name))

    return None if match is None else 2000 + int(match.group(1))


def suggest_master_year(group_name):
    """Підказка: вступ на магістратуру = рік вступу на бакалаврат + 4."""
    admitted = admission_year(group_name)

    return None if admitted is None else admitted + 4


def course_number(group_name, start_year, group_settings=None):
    """
    Курс групи в навчальному році start_year.

    Для магістрів (позначка в налаштуваннях) рахується від року
    вступу на магістратуру, для решти — від року в назві групи.
    """
    info = (group_settings or {}).get(group_key(group_name), {})

    if info.get("master") and info.get("master_year"):
        return start_year - info["master_year"] + 1

    admitted = admission_year(group_name)

    return None if admitted is None else start_year - admitted + 1


def semester_number(course, session):
    """Курс 4, зимова -> 7; курс 4, літня -> 8."""
    return 2 * (course - 1) + (1 if session == "winter" else 2)

# ──────────────────────────────────────────────
#  Підказка за назвою файлу
# ──────────────────────────────────────────────

# Рік 20xx; через дефіс, слеш чи підкреслення може йти другий:
# 2025-2026 або 2025-26
_YEAR_IN_NAME = re.compile(
    r"(?<!\d)(20\d{2})(?:\s*[-–—/_]\s*(\d{4}|\d{2}))?(?!\d)"
)

_LETTER = "A-ZА-ЯІЇЄҐ"
_SUMMER_WORD = re.compile(rf"(?<![{_LETTER}])(?:ЛІТ|ЛЕТ)")
_WINTER_WORD = re.compile(rf"(?<![{_LETTER}])ЗИМ")


def _second_year(first, text):
    """'2026' -> 2026; '26' -> 2026 (століття береться від першого року)."""
    if len(text) == 4:
        return int(text)

    return first // 100 * 100 + int(text)


def guess_from_filename(file_name, today=None):
    """
    Підказка за назвою файлу: (рік початку навч. року | None, сесія | None).
    Лише підказка: користувач може змінити будь-яке значення.

    Сесія:
      слова «літо/літня» -> літня, «зима/зимова» -> зимова;
      якщо обидва або жодного — за роками: один рік -> літня,
      два роки (2025-2026) -> зимова.

    Рік початку навчального року:
      два роки -> перший з них;
      один рік -> літня сесія належить до попереднього навчального року
      (літо 2025 = 2024/25), зимова починається в цьому році.
    """
    today = today or date.today()

    low = today.year - MAX_YEARS_BACK
    high = today.year

    text = norm_key(os.path.splitext(os.path.basename(file_name))[0])

    summer = _SUMMER_WORD.search(text) is not None
    winter = _WINTER_WORD.search(text) is not None

    session = None

    if summer and not winter:
        session = "summer"
    elif winter and not summer:
        session = "winter"

    two_years_start = None
    single_year = None

    for match in _YEAR_IN_NAME.finditer(text):

        first = int(match.group(1))

        if not low <= first <= high:
            continue

        second = match.group(2)

        if (
            second is not None
            and _second_year(first, second) == first + 1
        ):
            two_years_start = first
            break

        if single_year is None:
            single_year = first

    if two_years_start is not None:

        return two_years_start, session or "winter"

    if single_year is not None:

        session = session or "summer"

        start = single_year - 1 if session == "summer" else single_year

        return start, session

    return None, session

# ──────────────────────────────────────────────
#  Файли архіву
# ──────────────────────────────────────────────

def group_file(root, start_year, session, group_name):
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", group_key(group_name))

    return os.path.join(
        root,
        academic_year_folder(start_year),
        session,
        f"{safe_name}.json"
    )


def existing_groups(root, start_year, session, group_names):
    """Групи, для яких ця сесія вже є в архіві."""
    return [
        name for name in group_names
        if os.path.exists(group_file(root, start_year, session, name))
    ]


YEAR_FOLDER = re.compile(r"(\d{4})-\d{2}")


def list_archive(root):
    """
    Усі сесії, які є в архіві: [(рік початку, сесія, [групи]), ...].
    Назви груп беруться з імен файлів, самі файли не читаються.
    """
    sessions = []

    try:
        year_names = os.listdir(root)
    except OSError:
        return sessions

    for year_name in year_names:

        match = YEAR_FOLDER.fullmatch(year_name)

        if match is None or not os.path.isdir(os.path.join(root, year_name)):
            continue

        year = int(match.group(1))

        for session in SESSIONS:

            try:
                names = os.listdir(os.path.join(root, year_name, session))
            except OSError:
                continue

            groups = sorted(
                name[:-5] for name in names
                if name.lower().endswith(".json")
            )

            if groups:
                sessions.append((year, session, groups))

    return sessions


def group_label(group_name, start_year, group_settings):
    """
    Назва групи для показу. Позначка «магістр» ставиться, лише якщо
    сесія не раніша за вступ на магістратуру: бакалаврські сесії
    тієї самої групи лишаються без позначки.
    """
    info = group_settings.get(group_key(group_name), {})
    master_year = info.get("master_year")

    if info.get("master") and master_year and start_year >= master_year:
        return f"{group_name} (магістр, з {master_year})"

    return group_name


def _write_json(path, data):
    """
    Пише файл через тимчасовий і підміняє його одним кроком,
    щоб збій посередині запису не залишив напівпорожній файл.
    """
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)

    descriptor, temp_path = tempfile.mkstemp(dir=folder, suffix=".tmp")

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

        os.replace(temp_path, path)

    except BaseException:
        try:
            os.remove(temp_path)
        except OSError:
            pass

        raise


def _encode_mark(mark):
    """
    None (порожня клітинка) -> null
    число -> рядок ("85", "85.5")
    "н/б", "звіл" -> як є
    """
    if mark is None:
        return None

    number = to_decimal(mark)

    if number is not None:
        return str(number)

    return str(mark).strip()


def build_group_record(group_name, start_year, session, students, analysis):
    subject_type_map = analysis["subject_type_map"]
    subject_name_map = analysis["subject_name_map"]
    column_map = analysis["group_column_map"]

    # Лише ті дисципліни, які є в цій групі
    # (у студентів решти груп для них стоїть "-")
    subject_ids = [
        subject_id
        for subject_id in sorted(subject_type_map)
        if f"{group_name}|{subject_id}" in column_map
    ]

    return {
        "version": FORMAT_VERSION,
        "group": group_name,
        "academic_year": start_year,
        "session": session,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "subjects": [
            {
                "name": subject_name_map[subject_id],
                "type": subject_type_map[subject_id],
            }
            for subject_id in subject_ids
        ],
        "students": [
            {
                "pib": student.pib,
                "bk": student.bk,
                "marks": [
                    _encode_mark(student.marks.get(subject_id))
                    for subject_id in subject_ids
                ],
            }
            for student in students
        ],
    }


def save_session(root, start_year, session, result):
    """
    Записує кожну групу результату окремим файлом.
    Існуючий файл тієї ж групи та сесії замінюється.
    Повертає список збережених груп.
    """
    saved = []

    for group_name in result.group_names:

        students = [
            student for student in result.students
            if student.group_name == group_name
        ]

        record = build_group_record(
            group_name,
            start_year,
            session,
            students,
            result.analysis
        )

        _write_json(
            group_file(root, start_year, session, group_name),
            record
        )

        saved.append(group_name)

    return saved


# ──────────────────────────────────────────────
#  Налаштування груп (магістр, рік вступу)
# ──────────────────────────────────────────────

def load_group_settings(root):
    """
    {назва_групи: {"master": bool, "master_year": int | None}}
    Ключі — group_key(). Якщо файл пошкоджений, він відкладається
    як groups.json.bad, щоб наступний запис його не затер.
    """
    return _read_json_dict(os.path.join(root, SETTINGS_FILE))

def save_group_settings(root, settings):
    _write_json(os.path.join(root, SETTINGS_FILE), settings)

# ──────────────────────────────────────────────
#  Ручні позначки: «не навчалися» і однакові ПІБ
# ──────────────────────────────────────────────

OVERRIDES_FILE = "overrides.json"


def session_key(year, session):
    """2024, 'winter' -> '2024-25/winter'"""
    return f"{academic_year_folder(year)}/{session}"


def _read_json_dict(path):
    """Словник із json-файлу; пошкоджений файл відкладається як .bad."""
    try:
        with open(path, encoding="utf-8") as file:
            data = json.load(file)

    except FileNotFoundError:
        return {}

    except (OSError, ValueError):
        try:
            os.replace(path, path + ".bad")
        except OSError:
            pass

        return {}

    return data if isinstance(data, dict) else {}


def load_overrides(root):
    """
    {"skipped": {група: ["2024-25/winter", ...]},
     "aliases": {група: {ПІБ-варіант: основний ПІБ}},
     "alias_names": {група: {ПІБ-варіант: [ім'я варіанта, основне ім'я]}}}
    Ключі груп і ПІБ — у нормалізованому вигляді.
    """
    data = _read_json_dict(os.path.join(root, OVERRIDES_FILE))

    def section(name):
        value = data.get(name)
        return value if isinstance(value, dict) else {}

    return {
        "skipped": {
            group: list(items)
            for group, items in section("skipped").items()
            if isinstance(items, list)
        },
        "aliases": {
            group: dict(items)
            for group, items in section("aliases").items()
            if isinstance(items, dict)
        },
        "alias_names": {
            group: dict(items)
            for group, items in section("alias_names").items()
            if isinstance(items, dict)
        },
    }


def save_overrides(root, overrides):
    _write_json(os.path.join(root, OVERRIDES_FILE), overrides)


def add_skipped_sessions(root, items):
    """items: [(група, рік початку, сесія), ...] — «у цій сесії не навчалися»."""
    overrides = load_overrides(root)

    for group, year, session in items:

        sessions = overrides["skipped"].setdefault(group_key(group), [])
        key = session_key(year, session)

        if key not in sessions:
            sessions.append(key)

    save_overrides(root, overrides)


def clear_skipped_sessions(root):
    overrides = load_overrides(root)
    overrides["skipped"] = {}
    save_overrides(root, overrides)


def add_aliases(root, pairs):
    """
    pairs: [(група, ключ_варіанта, ключ_основного,
             ім'я_варіанта, основне_ім'я), ...]
    """
    overrides = load_overrides(root)

    for group, alt_key, main_key, alt_name, main_name in pairs:

        group_id = group_key(group)

        overrides["aliases"].setdefault(group_id, {})[alt_key] = main_key
        overrides["alias_names"].setdefault(group_id, {})[alt_key] = [
            alt_name, main_name
        ]

    save_overrides(root, overrides)
    
def remove_aliases(root, items):
    """items: [(група, ключ_варіанта), ...] — скасувати об'єднання."""
    overrides = load_overrides(root)

    for group, alt_key in items:

        group_id = group_key(group)

        for section in ("aliases", "alias_names"):

            entries = overrides[section].get(group_id)

            if entries is None:
                continue

            entries.pop(alt_key, None)

            if not entries:
                del overrides[section][group_id]

    save_overrides(root, overrides)
    
# ──────────────────────────────────────────────
#  Видалення з архіву
# ──────────────────────────────────────────────

DELETED_FOLDER = "_deleted"
DELETED_RETENTION_DAYS = 30
_STAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"

def delete_sessions(root, items):
    """
    items: [(рік початку, сесія, група), ...].
    Файли не стираються назавжди: вони переносяться в
    <root>/_deleted/<дата-час>/<навч. рік>/<сесія>/.
    Повертає (кількість перенесених, список описів того, що не вдалося).
    """
    stamp = datetime.now().strftime(_STAMP_FORMAT)

    moved = 0
    failed = []

    for year, session, group in items:

        source = group_file(root, year, session, group)

        target = os.path.join(
            root,
            DELETED_FOLDER,
            stamp,
            academic_year_folder(year),
            session,
            os.path.basename(source)
        )

        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            os.replace(source, target)
            moved += 1

        except OSError:
            failed.append(
                f"{academic_year_label(year)} "
                f"{SESSION_LABELS[session].lower()}: {group}"
            )

    # Порожні папки сесій і років прибираємо
    for year, session, _ in items:

        year_folder = os.path.join(root, academic_year_folder(year))

        for folder in (os.path.join(year_folder, session), year_folder):
            try:
                os.rmdir(folder)
            except OSError:
                pass

    return moved, failed

def _deleted_batches(root):
    """[(папка, час видалення | None)] — партії видалення в _deleted."""
    base = os.path.join(root, DELETED_FOLDER)

    try:
        names = os.listdir(base)
    except OSError:
        return []

    batches = []

    for name in names:

        path = os.path.join(base, name)

        if not os.path.isdir(path):
            continue

        try:
            moment = datetime.strptime(name, _STAMP_FORMAT)
        except ValueError:
            moment = None

        batches.append((path, moment))

    return batches


def deleted_count(root):
    """Скільки груп (json-файлів) лежить у _deleted."""
    count = 0

    for path, _ in _deleted_batches(root):
        for _folder, _dirs, names in os.walk(path):
            count += sum(
                1 for name in names if name.lower().endswith(".json")
            )

    return count


def purge_deleted(root, older_than_days=None, now=None):
    """
    Остаточно стирає партії видалення з _deleted.

    older_than_days=None — усе. Число — лише партії, старші за цю кількість
    днів (за часом у назві папки; папки з іншою назвою не чіпаємо).
    Повертає кількість стертих партій.
    """
    now = now or datetime.now()
    removed = 0

    for path, moment in _deleted_batches(root):

        if older_than_days is not None:

            if (
                moment is None
                or now - moment < timedelta(days=older_than_days)
            ):
                continue

        try:
            shutil.rmtree(path)
            removed += 1
        except OSError:
            pass

    # Порожню _deleted теж прибираємо
    try:
        os.rmdir(os.path.join(root, DELETED_FOLDER))
    except OSError:
        pass

    return removed