import logging
import os

from PySide6.QtCore import QObject, Signal, Slot
from openpyxl import load_workbook

from excel_reader import (
    build_journal_structure,
    get_selected_sheets,
    parse_sheet_name, 
    read_sheets,
    validate_selected_groups,
    analyze_selected_groups,
    import_students,
)

from excel_writer import save_database_file

from scoring import calculate_statistics
from rating_rules import DEFAULT_RULES
from table_colors import DEFAULT_COLORS

from rating import (
    get_budget_students,
    get_debt_free_students,
    get_debtors,
    calculate_scholarships,
)

from file_safety import JournalFileError, check_workbook_file
from models import CalculationResult

LOG_FILE = os.path.join(
    os.path.dirname(
        os.path.abspath(__file__)
    ),
    "rating_program.log"
)


logger = logging.getLogger("rating_program")
logger.setLevel(logging.ERROR)

if not logger.handlers:

    handler = logging.FileHandler(
        LOG_FILE,
        encoding="utf-8"
    )

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    handler.setFormatter(formatter)
    logger.addHandler(handler)


class FunctionWorker(QObject):
    """Виконує довільну функцію у фоновому потоці й повертає результат."""

    done = Signal(object)
    failed = Signal(str)

    def __init__(self, function):
        super().__init__()

        self._function = function

    @Slot()
    def run(self):

        try:
            result = self._function()

        except Exception:

            logger.exception(
                "Помилка у фоновому завданні"
            )

            self.failed.emit(
                "Не вдалося виконати розрахунок. "
                "Подробиці записано в log-файл."
            )

            return

        self.done.emit(result)


class RatingWorker(QObject):

    status = Signal(str)

    structure_finished = Signal(
        object,
        list
    )

    validation_required = Signal(
        object,
        list
    )
    
    calculation_finished = Signal(object)
    archive_prepared = Signal(object, list)
    error = Signal(str)

    def __init__(self):
        super().__init__()

        self.operation = None
        self.operation_args = ()

    def configure(
        self,
        operation,
        *args
    ):
        self.operation = operation
        self.operation_args = args

    @Slot()
    def run(self):

        if self.operation == "structure":

            self.load_structure(
                *self.operation_args
            )

        elif self.operation == "calculate":

            self.calculate(
                *self.operation_args
            )

        elif self.operation == "archive_prepare":

            self.prepare_archive(
                *self.operation_args
            )
        
        else:

            self.error.emit(
                "Не задана операція."
            )

    def _load_workbook(
        self,
        file_path
    ):
        check_workbook_file(file_path)

        try:
            return load_workbook(
                filename=file_path,
                data_only=True,
                read_only=True,
                keep_vba=False,      # макросы не загружаются и не выполняются
                keep_links=False     # внешние связи не читаются
            )

        except OSError as error:
            raise JournalFileError(
                "Не вдалося відкрити файл журналу. Перевірте, що він існує "
                "і не заблокований іншою програмою."
            ) from error

        except Exception as error:
            # Вместо технического текста openpyxl показываем понятный
            raise JournalFileError(
                "Не вдалося прочитати файл як книгу Excel. "
                "Можливо, він пошкоджений або має некоректний формат."
            ) from error
            
    @Slot(str)
    def load_structure(
        self,
        file_path
    ):

        workbook = None

        try:

            self.status.emit(
                "Статус: Читання журналу..."
            )

            workbook = self._load_workbook(
                file_path
            )

            (
                specialties,
                ignored_sheets
            ) = build_journal_structure(
                workbook
            )

            self.structure_finished.emit(
                specialties,
                ignored_sheets
            )

        except JournalFileError as error:

            logger.error(
                "Файл журналу відхилено: %s",
                error
            )

            self.error.emit(
                str(error)
            )

        except Exception:

            logger.exception(
                "Помилка побудови структури"
            )

            self.error.emit(
                "Не вдалося прочитати журнал."
            )

        finally:

            if workbook is not None:
                workbook.close()

    @Slot(str, object, str, object, object)
    def calculate(
        self,
        file_path,
        selected_groups,
        output_file,
        rules=None,
        colors=None
    ):
        rules = DEFAULT_RULES if rules is None else rules
        colors = DEFAULT_COLORS if colors is None else colors

        workbook = None

        try:

            self.status.emit(
                "Статус: Відкриття журналу..."
            )

            workbook = self._load_workbook(
                file_path
            )

            self.status.emit(
                "Статус: Перевірка груп..."
            )

            selected_sheets = (
                get_selected_sheets(
                    workbook,
                    selected_groups
                )
            )

            found_groups = {
                name.upper()
                for name in selected_sheets
            }

            missing_groups = [
                group
                for group in selected_groups
                if group.upper()
                not in found_groups
            ]

            if missing_groups:

                raise ValueError(
                    "Не знайдено вибрані групи: "
                    + ", ".join(missing_groups)
                )
            
            self.status.emit(
                "Статус: Читання листів..."
            )

            sheets = read_sheets(
                workbook,
                selected_sheets
            )
            
            self.status.emit(
                "Статус: Перевірка структури груп..."
            )

            (
                valid_sheets,
                validation_errors
            ) = validate_selected_groups(
                sheets,
                selected_sheets
            )
            
            if validation_errors:

                self.validation_required.emit(
                    valid_sheets,
                    validation_errors
                )

                return
            
            self.status.emit(
                "Статус: Аналіз дисциплін..."
            )

            analysis = (
                analyze_selected_groups(
                    sheets,
                    valid_sheets
                )
            )

            self.status.emit(
                "Статус: Імпорт студентів..."
            )

            students = import_students(
                sheets,
                valid_sheets,
                analysis
            )

            self.status.emit(
                "Статус: Розрахунок рейтингу..."
            )

            students = calculate_statistics(
                students,
                analysis
            )

            self.status.emit(
                "Статус: Розподіл стипендій..."
            )

            budget_students = get_budget_students(students)

            # Список уже отсортирован по рейтингу
            ranked_students = calculate_scholarships(
                budget_students,
                rules
            )

            # Фильтрация сохраняет порядок, повторная сортировка не нужна
            debt_free_students = get_debt_free_students(ranked_students)
            debtors = get_debtors(ranked_students)

            self.status.emit(
                "Статус: Збереження..."
            )

            try:

                save_database_file(
                    output_file,
                    students,
                    analysis,
                    debt_free_students,
                    debtors,
                    colors=colors,
                    rules=rules
                )

            except PermissionError:

                logger.exception(
                    "Помилка збереження файлу: %s",
                    output_file
                )

                self.error.emit(
                    "Не вдалося зберегти файл рейтингу.\n\n"
                    "Можливо, він уже відкритий в Excel. "
                    "Закрийте файл та повторіть спробу."
                )

                return

            self.calculation_finished.emit(
                CalculationResult(
                    output_file=output_file,
                    group_names=list(valid_sheets),
                    students=students,
                    budget_students=ranked_students,
                    analysis=analysis
                )
            )

        except ValueError as error:

            logger.error(
                "Помилка даних: %s",
                error
            )

            self.error.emit(
                str(error)
            )

        except Exception:

            logger.exception(
                "Неочікувана помилка"
            )

            self.error.emit(
                "Не вдалося розрахувати рейтинг. "
                "Подробиці записано в log-файл."
            )

        finally:

            if workbook is not None:
                workbook.close()
    
    @Slot(str)
    def prepare_archive(
        self,
        file_path
    ):
        """
        Читає всі групи журналу для архіву: без рейтингу й стипендій.
        Повертає результат з оцінками та список помилок по групах,
        які обробити не можна.
        """

        workbook = None

        try:

            self.status.emit(
                "Статус: Відкриття журналу..."
            )

            workbook = self._load_workbook(
                file_path
            )

            group_sheets = [
                name
                for name in workbook.sheetnames
                if parse_sheet_name(name) is not None
            ]

            if not group_sheets:

                raise ValueError(
                    "У журналі не знайдено жодної групи "
                    "(листи з назвою за форматом XX-123)."
                )

            self.status.emit(
                "Статус: Читання листів..."
            )

            sheets = read_sheets(
                workbook,
                group_sheets
            )

            self.status.emit(
                "Статус: Перевірка структури груп..."
            )

            (
                valid_sheets,
                validation_errors
            ) = validate_selected_groups(
                sheets,
                group_sheets
            )

            if not valid_sheets:

                raise ValueError(
                    "Жодну групу журналу не можна обробити:\n\n"
                    + "\n".join(validation_errors)
                )

            self.status.emit(
                "Статус: Імпорт студентів..."
            )

            analysis = analyze_selected_groups(
                sheets,
                valid_sheets
            )

            students = import_students(
                sheets,
                valid_sheets,
                analysis
            )

            self.archive_prepared.emit(
                CalculationResult(
                    output_file="",
                    group_names=list(valid_sheets),
                    students=students,
                    budget_students=[],
                    analysis=analysis
                ),
                validation_errors
            )

        except JournalFileError as error:

            logger.error(
                "Файл журналу відхилено: %s",
                error
            )

            self.error.emit(
                str(error)
            )

        except ValueError as error:

            logger.error(
                "Журнал не додано в архів: %s",
                error
            )

            self.error.emit(
                str(error)
            )

        except Exception:

            logger.exception(
                "Помилка підготовки журналу для архіву"
            )

            self.error.emit(
                "Не вдалося прочитати журнал. "
                "Подробиці записано в log-файл."
            )

        finally:

            if workbook is not None:
                workbook.close()