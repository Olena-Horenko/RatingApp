from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
 
from rating_rules import DEFAULT_RULES, RANGES, RatingRules
from table_colors import (
    DEFAULT_COLORS,
    HEADER_SECOND_COLOR,
    TableColors,
    unreadable_fields,
)
 
# Поля, які залежать від відповідного прапорця «виняток для малих груп»
ORDINARY_SMALL_FIELDS = (
    "ordinary_small_group_limit",
    "ordinary_small_group_count",
    "ordinary_small_group_min_rating",
)
HIGHER_SMALL_FIELDS = (
    "higher_small_group_limit",
    "higher_small_group_count",
)
 
# Другі кольори пар: вимикаються, коли двоколірний режим вимкнено
SECOND_COLOR_FIELDS = (
    "table_2", "pib_2", "ordinary_2", "higher_2", "debt_2"
)

# Назви кольорів для попередження про поганий контраст
COLOR_TITLES = {
    "table_1": "колір таблиці",
    "table_2": "другий колір таблиці",
    "header": "колір шапки",
    "pib_1": "колір стовпця ПІБ",
    "pib_2": "другий колір стовпця ПІБ",
    "ordinary_1": "колір стандартної стипендії",
    "ordinary_2": "другий колір стандартної стипендії",
    "higher_1": "колір підвищеної стипендії",
    "higher_2": "другий колір підвищеної стипендії",
    "debt_1": "колір підсвічування боргів",
    "debt_2": "другий колір підсвічування боргів",
}

# Рядки предпросмотру: (підпис, вид рядка, перший колір пари?)
PREVIEW_ROWS = (
    ("Шапка", "header", True),
    ("Шапка, 2-й рядок", "header2", True),
    ("Без стипендії", "none", True),
    ("Без стипендії", "none", False),
    ("Ординарна", "ordinary", True),
    ("Ординарна", "ordinary", False),
    ("Підвищена", "higher", True),
    ("Підвищена", "higher", False),
    ("З боргами", "debt", True),
    ("З боргами", "debt", False),
)

PREVIEW_COLUMNS = 5     # №, ПІБ, Група, Оцінка, Борги
PREVIEW_PIB_COLUMN = 1
PREVIEW_DEBT_COLUMNS = (3, 4)
 
class ColorButton(QPushButton):
    """Кнопка-зразок: показує колір і його код, за кліком відкриває палітру."""
 
    changed = Signal()
 
    def __init__(self, color):
        super().__init__()
 
        self._color = color
 
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(110, 28)
        self.clicked.connect(self._choose)
 
        self._refresh()
 
    def color(self):
        return self._color
 
    def set_color(self, color):
        self._color = color
        self._refresh()
 
    def _choose(self):
        chosen = QColorDialog.getColor(
            QColor(f"#{self._color}"),
            self,
            "Оберіть колір"
        )
 
        if not chosen.isValid():
            return
 
        # "#rrggbb" -> "RRGGBB"
        self._color = chosen.name().upper().lstrip("#")
 
        self._refresh()
        self.changed.emit()
 
    def _refresh(self):
        text_color = (
            "#000000"
            if QColor(f"#{self._color}").lightness() > 140
            else "#FFFFFF"
        )
 
        self.setText(f"#{self._color}")
        self.setToolTip("Клацніть, щоб змінити колір")
        self.setStyleSheet(
            "QPushButton {"
            f" background-color: #{self._color};"
            f" color: {text_color};"
            " border: 1px solid #888888;"
            " border-radius: 4px;"
            "}"
            "QPushButton:disabled {"
            " border: 1px dashed #AAAAAA;"
            " color: #888888;"
            "}"
        )


class ColorPreview(QWidget):
    """
    Зразок таблиці рейтингу з текстом «абв»: видно, чи читається текст.
    Кольори беруться з того самого TableColors, що й для Excel;
    шрифт чорний, як у Excel, незалежно від теми програми.
    """

    def __init__(self):
        super().__init__()

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)

        self._cells = []

        for row, (title, kind, shaded) in enumerate(PREVIEW_ROWS):

            label = QLabel(title)
            label.setObjectName("Hint")
            label.setContentsMargins(0, 0, 10, 0)
            grid.addWidget(label, row, 0)

            cells = []

            for column in range(PREVIEW_COLUMNS):
                cell = QLabel("абв")
                cell.setMinimumHeight(26)
                cell.setAlignment(
                    Qt.AlignmentFlag.AlignVCenter
                    | (
                        Qt.AlignmentFlag.AlignLeft
                        if column == PREVIEW_PIB_COLUMN
                        else Qt.AlignmentFlag.AlignHCenter
                    )
                )
                grid.addWidget(cell, row, column + 1)
                cells.append(cell)

            self._cells.append(cells)

        grid.setColumnStretch(0, 0)

        for column in range(1, PREVIEW_COLUMNS + 1):
            grid.setColumnStretch(column, 1)

    @staticmethod
    def _cell_color(colors, kind, shaded, column):
        if kind == "header":
            return colors.header

        if kind == "header2":
            return HEADER_SECOND_COLOR

        if kind == "ordinary":
            return colors.scholarship_color("Звичайна", shaded)

        if kind == "higher":
            return colors.scholarship_color("Підвищена", shaded)

        # Рядок без стипендії: ПІБ має свій колір, борги — свій
        if column == PREVIEW_PIB_COLUMN:
            return colors.pib_color(shaded)

        if kind == "debt" and column in PREVIEW_DEBT_COLUMNS:
            return colors.debt_color(shaded)

        return colors.row_color(shaded)

    def show_colors(self, colors):
        for (title, kind, shaded), cells in zip(PREVIEW_ROWS, self._cells):

            weight = "bold" if kind.startswith("header") else "normal"

            for column, cell in enumerate(cells):

                color = self._cell_color(colors, kind, shaded, column)

                cell.setStyleSheet(
                    f"background-color: #{color};"
                    " color: #000000;"
                    f" font-weight: {weight};"
                    " border-bottom: 1px solid #D9D9D9;"
                    " padding: 0px 6px;"
                )

 
def _title(text):
    label = QLabel(text)
    label.setObjectName("SectionTitle")
    return label
 
 
def _hint(text):
    label = QLabel(text)
    label.setObjectName("Hint")
    label.setWordWrap(True)
    return label
 
 
class SettingsDialog(QDialog):
    """Правила підрахунку рейтингу та оформлення таблиць."""
 
    def __init__(self, rules, colors, parent=None):
        super().__init__(parent)
 
        self.setWindowTitle("Налаштування")
        self.resize(640, 680)
        self.setMinimumSize(520, 420)
 
        self._rules = rules
        self._colors = colors
 
        self._spins = {}
        self._checks = {}
        self._color_buttons = {}
 
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)
 
        # Вміст прокручується: на малих екранах він не вміщується
        content = QWidget()
        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(0, 0, 8, 0)
        self._layout.setSpacing(8)
 
        self._build_rules()
        self._layout.addSpacing(10)
        self._build_appearance()
        self._layout.addStretch()
 
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
 
        # ── Кнопки ──
        bottom = QHBoxLayout()
 
        reset_button = QPushButton("Скинути налаштування до початкових")
        reset_button.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_button.clicked.connect(self._reset)
 
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(
            "Зберегти"
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            "Скасувати"
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
 
        bottom.addWidget(reset_button)
        bottom.addStretch()
        bottom.addWidget(buttons)
 
        outer.addLayout(bottom)
 
        self._load_rules(rules)
        self._load_colors(colors)
 
    # ──────────────────────────────────────────────────────────
    #  Побудова вікна
    # ──────────────────────────────────────────────────────────
    def _add_row(self, text, *widgets, indent=0):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.setContentsMargins(indent, 0, 0, 0)
 
        row.addWidget(QLabel(text))
        row.addStretch()
 
        for widget in widgets:
            row.addWidget(widget)
 
        self._layout.addLayout(row)
 
    def _spin(self, name, suffix=""):
        low, high = RANGES[name]
 
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setSuffix(suffix)
        spin.setFixedWidth(90)
 
        self._spins[name] = spin
 
        return spin
 
    def _small_group_check(self, name, fields):
        check = QCheckBox("Виняток для малих груп")
 
        def update(enabled):
            for field_name in fields:
                self._spins[field_name].setEnabled(enabled)
 
        check.toggled.connect(update)
 
        self._checks[name] = check
        self._layout.addWidget(check)
 
        return update
 
    def _build_rules(self):
        self._layout.addWidget(_title("Правила підрахунку рейтингу"))
 
        # ── Ординарна стипендія ──
        self._layout.addWidget(_title("1. Ординарна стипендія"))
        self._layout.addWidget(
            _hint("Студент бюджетної форми повинен:")
        )
 
        self._add_row(
            "Потрапити в топ", self._spin("ordinary_percent", " %")
        )
        self._add_row(
            "Мати усі оцінки не нижче",
            self._spin("ordinary_min_mark")
        )
 
        # Спочатку створюємо поля, потім прапорець: він їх вмикає/вимикає
        limit = self._spin("ordinary_small_group_limit")
        count = self._spin("ordinary_small_group_count")
        rating = self._spin("ordinary_small_group_min_rating")
 
        update_ordinary = self._small_group_check(
            "ordinary_small_group", ORDINARY_SMALL_FIELDS
        )
 
        self._add_row(
            "Якщо кількість бюджетників менше", limit, indent=20
        )
        self._add_row(
            "то кількість стандартних стипендій", count, indent=20
        )
        self._add_row(
            "і рейтинговий бал студента не нижче (лише в малих групах)",
            rating,
            indent=20
        )
        self._update_ordinary_small = update_ordinary
 
        # ── Підвищена стипендія ──
        self._layout.addSpacing(6)
        self._layout.addWidget(_title("2. Підвищена стипендія"))
        self._layout.addWidget(
            _hint("Студент бюджетної форми повинен:")
        )
 
        self._add_row(
            "Потрапити в топ", self._spin("higher_percent", " %")
        )
        self._add_row(
            "Мати усі оцінки не нижче", self._spin("higher_min_mark")
        )
        self._add_row(
            "Мати рейтинговий бал не нижче",
            self._spin("higher_min_rating")
        )
 
        limit = self._spin("higher_small_group_limit")
        count = self._spin("higher_small_group_count")
 
        update_higher = self._small_group_check(
            "higher_small_group", HIGHER_SMALL_FIELDS
        )
 
        self._add_row(
            "Якщо кількість бюджетників менше", limit, indent=20
        )
        self._add_row(
            "то кількість підвищених стипендій", count, indent=20
        )
        self._update_higher_small = update_higher
 
        self._layout.addWidget(
            _hint(
                "Кількість стипендій у відсотках округлюється вниз. "
                "Якщо студент не підходить за умовами, перевіряється "
                "наступний за рейтингом. Усі бали: від 60 до 100. "
                "Борг (оцінка нижче 60) не налаштовується."
            )
        )
 
    def _color_pair(self, text, first, second=None):
        buttons = [self._color_button(first)]
 
        if second is not None:
            buttons.append(self._color_button(second))
 
        self._add_row(text, *buttons)
 
    def _color_button(self, name):
        button = ColorButton(getattr(DEFAULT_COLORS, name))
        button.changed.connect(self._update_preview)
        self._color_buttons[name] = button
        return button
 
    def _build_appearance(self):
        self._layout.addWidget(_title("Оформлення рейтингу"))
 
        self.two_tone_check = QCheckBox(
            "Чергувати кольори рядків (двоколірна таблиця)"
        )
        self.two_tone_check.toggled.connect(self._update_two_tone)
        self._layout.addWidget(self.two_tone_check)
 
        self._color_pair("Колір таблиці", "table_1", "table_2")
        self._color_pair("Колір шапки таблиці", "header")
        self._color_pair("Колір стовпця ПІБ", "pib_1", "pib_2")
        self._color_pair(
            "Виділення ординарної стипендії на листі «Рейтинг»",
            "ordinary_1",
            "ordinary_2"
        )
        self._color_pair(
            "Виділення підвищеної стипендії на листі «Рейтинг»",
            "higher_1",
            "higher_2"
        )
        
        self._color_pair(
            "Підсвічування боргів на листі «Рейтинг_боржники»",
            "debt_1",
            "debt_2"
        )
        
        self._layout.addWidget(
            _hint(
                "Якщо двоколірний режим вимкнено, використовується "
                "лише перший колір кожної пари."
            )
        )

        # ── Попередній перегляд ──
        self._layout.addSpacing(4)
        self._layout.addWidget(_title("Попередній перегляд"))

        self._preview = ColorPreview()
        self._layout.addWidget(self._preview)

        self._contrast_label = _hint("")
        self._contrast_label.setStyleSheet("color: #B45309;")
        self._layout.addWidget(self._contrast_label)
        
    # ──────────────────────────────────────────────────────────
    #  Значення <-> віджети
    # ──────────────────────────────────────────────────────────
    def _update_two_tone(self, enabled):
        for name in SECOND_COLOR_FIELDS:
            self._color_buttons[name].setEnabled(enabled)
        
        self._update_preview()
 
    def _load_rules(self, rules):
        for name, spin in self._spins.items():
            spin.setValue(getattr(rules, name))
 
        for name, check in self._checks.items():
            check.setChecked(getattr(rules, name))
 
        # toggled не спрацьовує, якщо стан прапорця не змінився
        self._update_ordinary_small(
            self._checks["ordinary_small_group"].isChecked()
        )
        self._update_higher_small(
            self._checks["higher_small_group"].isChecked()
        )
 
    def _load_colors(self, colors):
        for name, button in self._color_buttons.items():
            button.set_color(getattr(colors, name))
 
        self.two_tone_check.setChecked(colors.two_tone)
        self._update_two_tone(colors.two_tone)
        self._update_preview()
        
    def _update_preview(self):
        """Перемальовує зразок таблиці й показує попередження про контраст."""
        _, colors_data = self._collect()
        colors = TableColors.from_dict(colors_data)

        self._preview.show_colors(colors)

        bad = unreadable_fields(colors)

        if bad:
            self._contrast_label.setText(
                "Чорний текст може погано читатися на кольорах: "
                + ", ".join(
                    f"{COLOR_TITLES[name]} (#{getattr(colors, name)})"
                    for name in bad
                )
                + "."
            )
        else:
            self._contrast_label.setText("")

        self._contrast_label.setVisible(bool(bad))
 
    def _collect(self):
        rules_data = {
            name: spin.value() for name, spin in self._spins.items()
        }
        rules_data.update({
            name: check.isChecked()
            for name, check in self._checks.items()
        })
 
        colors_data = {
            name: button.color()
            for name, button in self._color_buttons.items()
        }
        colors_data["two_tone"] = self.two_tone_check.isChecked()
 
        return rules_data, colors_data
 
    def _reset(self):
        """Повертає початкові значення у вікно (зберігаються кнопкою «Зберегти»)."""
        self._load_rules(DEFAULT_RULES)
        self._load_colors(DEFAULT_COLORS)
 
    def accept(self):
        rules_data, colors_data = self._collect()
 
        rules = RatingRules.from_dict(rules_data)
 
        # Підвищена стипендія не може бути м'якшою за стандартну
        if rules.to_dict() != rules_data:
            self._load_rules(rules)
 
            QMessageBox.information(
                self,
                "Значення скориговано",
                "Умови підвищеної стипендії не можуть бути м'якшими за "
                "умови стандартної (відсоток, мінімальна оцінка, "
                "рейтинговий бал). Значення виправлено. Перевірте їх і "
                "натисніть «Зберегти» ще раз."
            )
            return
 
        self._rules = rules
        self._colors = TableColors.from_dict(colors_data)
 
        super().accept()
 
    def result_values(self):
        """Повертає (правила стипендій, кольори таблиці)."""
        return self._rules, self._colors
