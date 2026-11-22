from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional


@dataclass
class Group:
    name: str


@dataclass
class Course:
    name: str
    groups: list[Group] = field(default_factory=list)

    def add_group(self, group: Group) -> None:
        self.groups.append(group)


@dataclass
class Specialty:
    name: str
    courses: list[Course] = field(default_factory=list)

    def add_course(self, course: Course) -> None:
        self.courses.append(course)
        

@dataclass
class DatabaseStudent:
    pib: str
    group_name: str
    bk: str = ""

    marks: dict[int, Any] = field(default_factory=dict)

    # None = значение ещё не рассчитано / отсутствует
    exam_average: Optional[Decimal] = None
    course_average: Optional[Decimal] = None
    practice_average: Optional[Decimal] = None
    rating: Optional[Decimal] = None
    total_average: Optional[Decimal] = None

    debts: int = 0
    scholarship: Optional[str] = None
    
    
@dataclass
class CalculationResult:
    """Повний результат розрахунку, який воркер передає інтерфейсу."""

    output_file: str
    group_names: list[str]
    students: list[DatabaseStudent]
    budget_students: list[DatabaseStudent]
    analysis: dict[str, Any]