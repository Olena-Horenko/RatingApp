from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from analytics import format_percent
from text_utils import sort_key

PLACEHOLDER_TEXT = "Таблиця з'явиться після розрахунку рейтингу."
DEBT_COLOR = QColor("#EF4444")


def cell(text, sort_value=None, problem=False):
    """Клітинка таблиці: текст, значення для сортування, підсвічування."""
    return (text, sort_value, problem)


class SortableItem(QTableWidgetItem):
    """Сортується за sort_value (число або текст), а не за видимим текстом."""

    def __init__(self, text, sort_value=None):
        super().__init__(text)
        self.sort_value = sort_value

    def __lt__(self, other):
        mine = self.sort_value
        theirs = getattr(other, "sort_value", None)

        if mine is None:
            return theirs is not None

        if theirs is None:
            return False

        return mine < theirs


class SortableTable(QTableWidget):
    """
    Таблиця без власної вертикальної прокрутки: висота підлаштовується
    під кількість рядків, прокручує вся область розділів.
    Клік по заголовку сортує за стовпцем.
    """

    ROW_HEIGHT = 26

    def __init__(
        self,
        headers,
        tooltips,
        text_columns=(0,),
        stretch_column=None,
    ):
        super().__init__(0, len(headers))

        self._headers = list(headers)
        self._text_columns = set(text_columns)

        self.setHorizontalHeaderLabels(self._headers)

        for column, tip in enumerate(tooltips):
            self.horizontalHeaderItem(column).setToolTip(tip)

        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)

        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        vertical = self.verticalHeader()
        vertical.setVisible(False)
        vertical.setDefaultSectionSize(self.ROW_HEIGHT)
        vertical.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)

        header = self.horizontalHeader()
        header.setSectionsClickable(True)
        header.setHighlightSections(False)

        if stretch_column is None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        else:
            header.setSectionResizeMode(
                QHeaderView.ResizeMode.ResizeToContents
            )
            header.setSectionResizeMode(
                stretch_column,
                QHeaderView.ResizeMode.Stretch
            )

        header.sortIndicatorChanged.connect(self._update_arrows)

    def fill(self, rows, sort_column, order, row_data=None, checks=None):
        """
        rows — список рядків, кожен — список cell(...).
        row_data — необов'язкові дані для кожного рядка (UserRole).
        checks — список True/False: якщо задано, у першому стовпці
        кожного рядка з'являється позначка з цим початковим станом.
        """

        self.setSortingEnabled(False)
        self.setRowCount(len(rows))

        for row_index, row in enumerate(rows):

            for column, (text, sort_value, problem) in enumerate(row):

                item = SortableItem(text, sort_value)
                item.setToolTip(text)

                horizontal = (
                    Qt.AlignmentFlag.AlignLeft
                    if column in self._text_columns
                    else Qt.AlignmentFlag.AlignHCenter
                )

                item.setTextAlignment(
                    horizontal | Qt.AlignmentFlag.AlignVCenter
                )

                if problem:
                    item.setForeground(DEBT_COLOR)

                if row_data is not None:
                    item.setData(Qt.ItemDataRole.UserRole, row_data[row_index])

                if checks is not None and column == 0:
                    item.setFlags(
                        item.flags() | Qt.ItemFlag.ItemIsUserCheckable
                    )
                    item.setCheckState(
                        Qt.CheckState.Checked
                        if checks[row_index]
                        else Qt.CheckState.Unchecked
                    )

                self.setItem(row_index, column, item)

        self.setSortingEnabled(True)
        self.sortByColumn(sort_column, order)
        self._update_arrows(sort_column, order)
        self._fit_height()

    def _update_arrows(self, column, order):
        for index, base in enumerate(self._headers):

            arrow = ""

            if index == column:
                arrow = (
                    " ▲"
                    if order == Qt.SortOrder.AscendingOrder
                    else " ▼"
                )

            self.horizontalHeaderItem(index).setText(base + arrow)

    def _fit_height(self):
        header_height = self.horizontalHeader().sizeHint().height()

        self.setFixedHeight(
            header_height
            + self.ROW_HEIGHT * self.rowCount()
            + 2 * self.frameWidth()
            + 2
        )


class _ResultView(QWidget):
    """Заглушка до розрахунку + (підсумок) + таблиця + примітка."""

    def __init__(self, table, note_text):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._placeholder = self._make_label(PLACEHOLDER_TEXT, hint=True)
        self._summary = self._make_label("", hint=False)
        self._table = table
        self._note = self._make_label(note_text, hint=True)

        layout.addWidget(self._placeholder)
        layout.addWidget(self._summary)
        layout.addWidget(self._table)
        layout.addWidget(self._note)

        self.clear()

    @staticmethod
    def _make_label(text, hint):
        label = QLabel(text)
        label.setWordWrap(True)

        if hint:
            label.setObjectName("Hint")

        return label

    def clear(self):
        self._table.setRowCount(0)

        self._placeholder.setVisible(True)
        self._summary.setVisible(False)
        self._table.setVisible(False)
        self._note.setVisible(False)

    def _show_data(self, summary_text=""):
        self._placeholder.setVisible(False)

        self._summary.setText(summary_text)
        self._summary.setVisible(bool(summary_text))

        self._table.setVisible(True)
        self._note.setVisible(True)


class GroupsView(_ResultView):

    HEADERS = ["Група", "Студ.", "Сер. бал", "Борги", "Борги %", "Стип. %"]

    TOOLTIPS = [
        "Академічна група",
        "Кількість студентів у групі",
        "Середній рейтинг студентів групи",
        "Студентів хоча б з одним боргом",
        "Частка студентів з боргами",
        "Частка стипендіатів серед бюджетних студентів групи",
    ]

    def __init__(self):
        super().__init__(
            SortableTable(self.HEADERS, self.TOOLTIPS),
            "Клацніть на заголовок стовпця, щоб відсортувати групи "
            "за цим показником. Борг - оцінка нижче 60."
        )

    def set_data(self, stats):
        rows = []

        for item in stats:

            average = item.average

            rows.append([
                cell(item.name, item.name),
                cell(str(item.students), item.students),
                cell(
                    "—" if average is None else str(average),
                    None if average is None else float(average)
                ),
                cell(str(item.debtors), item.debtors, item.debtors > 0),
                cell(
                    format_percent(item.debtors_percent),
                    item.debtors_percent
                ),
                cell(
                    format_percent(item.recipients_percent),
                    item.recipients_percent
                ),
            ])

        self._table.fill(rows, 0, Qt.SortOrder.AscendingOrder)
        self._show_data()


class SubjectsView(_ResultView):

    HEADERS = [
        "Дисципліна", "Тип", "Студ.", "Борги", "Борги %", "Сер. оцінка"
    ]

    TOOLTIPS = [
        "Назва дисципліни",
        "Тип: ІСП, КР, КП або ЗАЛ",
        "Студентів з числовою оцінкою",
        "Оцінки нижче 60 (порожня клітинка рахується як 0)",
        "Частка оцінок нижче 60",
        "Середня оцінка студентів",
    ]

    def __init__(self):
        super().__init__(
            SortableTable(
                self.HEADERS,
                self.TOOLTIPS,
                stretch_column=0
            ),
            "Борг - оцінка нижче 60. Дисципліни без числових оцінок "
            "не показуються. Клацніть на заголовок, щоб змінити сортування."
        )

    def set_data(self, stats):
        ordered = sorted(
            stats,
            key=lambda item: (-item.debts, -(item.debts_percent or 0))
        )

        rows = []

        for item in ordered:

            average = item.average

            rows.append([
                cell(item.name, sort_key(item.name)),
                cell(item.subject_type, item.subject_type),
                cell(str(item.students), item.students),
                cell(str(item.debts), item.debts, item.debts > 0),
                cell(
                    format_percent(item.debts_percent),
                    item.debts_percent
                ),
                cell(
                    "—" if average is None else str(average),
                    None if average is None else float(average)
                ),
            ])

        self._table.fill(rows, 3, Qt.SortOrder.DescendingOrder)

        problem = [item for item in ordered if item.debts > 0][:3]

        if problem:
            summary = "Найбільше боргів: " + "; ".join(
                f"{item.name} ({item.debts})" for item in problem
            )
        else:
            summary = "Боргів за дисциплінами немає."

        self._show_data(summary)