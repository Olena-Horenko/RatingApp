from typing import Any
from text_utils import norm

def is_course_subject(subject_type: str) -> bool:
    """Проверяет, является ли предмет курсовой работой или проектом."""
    return norm(subject_type) in ("КР", "КП")


def is_practice_subject(
    subject_name: str,
    subject_type: str
) -> bool:
    """Проверяет, является ли предмет практикой."""
    if norm(subject_type) != "ЗАЛ":
        return False

    text = norm(subject_name)

    return (
        "ПРАКТИКА" in text
        or "ВІЙСЬКОВА" in text
    )


def get_subject_category(
    subject_name: str,
    subject_type: str
) -> str:
    """
    Категории:
    exam
    course
    practice
    other
    """

    normalized_type = norm(subject_type)

    if normalized_type == "ІСП":
        return "exam"

    elif is_course_subject(normalized_type):
        return "course"

    elif is_practice_subject(
        subject_name,
        normalized_type
    ):
        return "practice"

    return "other"


def get_subject_groups(
    analysis: dict[str, Any]
) -> dict[str, list[int]]:
    """Группирует все предметы по категориям."""

    subject_type_map = analysis["subject_type_map"]
    subject_name_map = analysis["subject_name_map"]

    groups = {
        "exam": [],
        "course": [],
        "practice": [],
    }

    for subject_id in sorted(subject_type_map):

        category = get_subject_category(
            subject_name_map.get(subject_id, ""),
            subject_type_map.get(subject_id, "")
        )

        if category in groups:
            groups[category].append(subject_id)

    return groups

