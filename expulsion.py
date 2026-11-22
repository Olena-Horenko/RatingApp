"""
Підрахунок боргів за весь час навчання за архівом сесій.
Чиста логіка без Qt.
"""

import json
import os
from dataclasses import dataclass, field
from difflib import SequenceMatcher

import archive
from rounding import to_decimal
from scoring import DEBT_THRESHOLD
from text_utils import norm_key, sort_key

# Від якої схожості ПІБ пропонувати «це один студент»
SIMILARITY = 0.88


@dataclass
class DebtItem:
    session_label: str
    subject: str
    subject_type: str
    mark: str


@dataclass
class DebtCandidate:
    pib: str
    group_name: str
    bk: str
    sessions_expected: int
    sessions_found: int = 0
    ambiguous: bool = False        # в журналі є однофамільці
    debts: list = field(default_factory=list)

    @property
    def debts_count(self):
        return len(self.debts)


@dataclass
class DebtReport:
    groups: list = field(default_factory=list)       # групи вибраної сесії
    missing: dict = field(default_factory=dict)      # група -> [(рік, сесія)]
    skipped: list = field(default_factory=list)      # (група, причина)
    blocked: bool = False                            # є прогалини, чекаємо рішення
    students_checked: int = 0
    candidates: list = field(default_factory=list)


@dataclass
class NameSuggestion:
    group: str
    new_pib: str       # як написано у вибраній сесії
    old_pib: str       # схожий запис зі старішої сесії
    new_key: str
    old_key: str
    ratio: float
    sessions: list = field(default_factory=list)


def session_label(year, session):
    return (
        f"{archive.academic_year_label(year)} "
        f"{archive.SESSION_LABELS[session].lower()}"
    )


def sessions_between(first_year, last_year, last_session):
    """(рік, сесія) від зимової first_year до (last_year, last_session)."""
    last_index = archive.SESSIONS.index(last_session)
    result = []

    for year in range(first_year, last_year + 1):
        for index, session in enumerate(archive.SESSIONS):

            if year == last_year and index > last_index:
                break

            result.append((year, session))

    return result


def first_study_year(group_name, settings):
    """Рік, з якого рахуємо борги: вступ на магістратуру або в назві групи."""
    info = settings.get(archive.group_key(group_name), {})

    if info.get("master") and info.get("master_year"):
        return info["master_year"]

    return archive.admission_year(group_name)


def _load_record(path):
    """Запис сесії групи або None, якщо файлу немає чи він пошкоджений."""
    try:
        with open(path, encoding="utf-8") as file:
            data = json.load(file)

    except (OSError, ValueError):
        return None

    if (
        not isinstance(data, dict)
        or not isinstance(data.get("subjects"), list)
        or not isinstance(data.get("students"), list)
    ):
        return None

    return data


def _is_debt(mark):
    # Порожня клітинка = 0 = борг; "н/б", "звіл" та інший текст не враховуємо
    if mark is None:
        return True

    number = to_decimal(mark)

    return number is not None and number < DEBT_THRESHOLD


def _session_debts(record, student, label):
    marks = student.get("marks", [])
    items = []

    for index, subject in enumerate(record["subjects"]):

        if index >= len(marks):
            continue

        mark = marks[index]

        if _is_debt(mark):
            items.append(DebtItem(
                session_label=label,
                subject=subject.get("name", "?"),
                subject_type=subject.get("type", ""),
                mark="порожньо" if mark is None else str(mark),
            ))

    return items


def _canonical(aliases, key):
    """Приводить варіант ПІБ до основного (з обмеженням ланцюжка)."""
    for _ in range(5):

        main = aliases.get(key)

        if main is None or main == key:
            break

        key = main

    return key


def _index_students(record, aliases):
    index = {}

    for student in record["students"]:

        key = _canonical(aliases, norm_key(student.get("pib")))

        index.setdefault(key, []).append(student)

    return index


def _target_records(root, year, session):
    """{назва групи: запис} для всіх груп вибраної сесії."""
    folder = os.path.join(
        root, archive.academic_year_folder(year), session
    )

    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return {}

    records = {}

    for name in names:

        if not name.lower().endswith(".json"):
            continue

        record = _load_record(os.path.join(folder, name))

        if record is not None and record.get("group"):
            records[record["group"]] = record

    return records


def _prepare(root, target_year, target_session):
    """
    Читає потрібні сесії кожної групи.

    Повертає (targets, plans, missing, skipped_groups), де
    plans = {група: (записи за сесіями, очікувані сесії, аліаси)}.
    Сесії, позначені «не навчалися», в очікувані не входять.
    """
    settings = archive.load_group_settings(root)
    overrides = archive.load_overrides(root)

    target_key = (target_year, target_session)
    targets = _target_records(root, target_year, target_session)

    plans = {}
    missing = {}
    skipped_groups = []

    for group, target_record in targets.items():

        group_id = archive.group_key(group)

        first = first_study_year(group, settings)

        if first is None:
            skipped_groups.append(
                (group, "у назві групи немає року вступу")
            )
            continue

        if first > target_year:
            skipped_groups.append(
                (group, "група ще не вступила в цей рік")
            )
            continue

        not_studied = set(overrides["skipped"].get(group_id, []))

        # Вибрана сесія існує, тому її позначка «не навчалися» не діє
        expected = [
            key
            for key in sessions_between(first, target_year, target_session)
            if key == target_key
            or archive.session_key(*key) not in not_studied
        ]

        records = {}
        absent = []

        for key in expected:

            if key == target_key:
                records[key] = target_record
                continue

            record = _load_record(
                archive.group_file(root, key[0], key[1], group)
            )

            if record is None:
                absent.append(key)
            else:
                records[key] = record

        if absent:
            missing[group] = absent

        plans[group] = (
            records,
            expected,
            overrides["aliases"].get(group_id, {})
        )

    return targets, plans, missing, skipped_groups


def calculate_debts(
    root,
    target_year,
    target_session,
    threshold,
    allow_missing=False
):
    """
    Кандидати з кількістю боргів >= threshold за всі сесії групи
    до (target_year, target_session) включно.

    Якщо в архіві бракує сесій і allow_missing=False, повертає звіт
    з blocked=True і порожнім списком кандидатів: інтерфейс питає
    користувача, що робити.
    """
    targets, plans, missing, skipped_groups = _prepare(
        root, target_year, target_session
    )

    report = DebtReport(
        groups=sorted(targets),
        missing=missing,
        skipped=skipped_groups,
    )

    if missing and not allow_missing:
        report.blocked = True
        return report

    target_key = (target_year, target_session)

    for group, (records, expected, aliases) in plans.items():

        indexes = {
            key: _index_students(record, aliases)
            for key, record in records.items()
        }

        for entry in records[target_key]["students"]:

            report.students_checked += 1

            name_key = _canonical(aliases, norm_key(entry.get("pib")))

            candidate = DebtCandidate(
                pib=entry.get("pib", ""),
                group_name=group,
                bk=entry.get("bk", ""),
                sessions_expected=len(expected),
            )

            for key in expected:

                record = records.get(key)

                if record is None:
                    continue

                found = indexes[key].get(name_key)

                # Студента немає в цій сесії (вступив пізніше, академвідпустка)
                if not found:
                    continue

                if len(found) > 1:
                    candidate.ambiguous = True

                # У вибраній сесії беремо саме цей запис, а не першого однофамільця
                source = entry if key == target_key else found[0]

                candidate.sessions_found += 1
                candidate.debts.extend(
                    _session_debts(record, source, session_label(*key))
                )

            if candidate.debts_count >= threshold:
                report.candidates.append(candidate)

    report.candidates.sort(
        key=lambda item: (
            -item.debts_count, item.group_name, sort_key(item.pib)
        )
    )

    return report


def find_name_suggestions(root, target_year, target_session):
    """
    Студенти вибраної сесії, яких немає в старішій сесії, і схожі на них
    записи, яких немає серед студентів вибраної сесії:
    ймовірно, це той самий студент з помилкою в ПІБ.
    """
    _, plans, _, _ = _prepare(root, target_year, target_session)

    target_key = (target_year, target_session)

    found = {}   # (група, новий ключ, старий ключ) -> NameSuggestion

    for group, (records, expected, aliases) in plans.items():

        current = {}

        for student in records[target_key]["students"]:

            key = _canonical(aliases, norm_key(student.get("pib")))
            current[key] = student.get("pib", "")

        for key in expected:

            if key == target_key or key not in records:
                continue

            old = _index_students(records[key], aliases)

            unmatched_old = {
                old_key: students[0].get("pib", "")
                for old_key, students in old.items()
                if old_key not in current
            }

            if not unmatched_old:
                continue

            for new_key, new_pib in current.items():

                if new_key in old:
                    continue

                best = None

                for old_key, old_pib in unmatched_old.items():

                    ratio = SequenceMatcher(None, new_key, old_key).ratio()

                    if ratio >= SIMILARITY and (
                        best is None or ratio > best[0]
                    ):
                        best = (ratio, old_key, old_pib)

                if best is None:
                    continue

                ratio, old_key, old_pib = best

                suggestion = found.setdefault(
                    (group, new_key, old_key),
                    NameSuggestion(
                        group=group,
                        new_pib=new_pib,
                        old_pib=old_pib,
                        new_key=new_key,
                        old_key=old_key,
                        ratio=ratio,
                    )
                )

                suggestion.sessions.append(session_label(*key))

    return sorted(
        found.values(),
        key=lambda item: (item.group, sort_key (item.new_pib))
    )