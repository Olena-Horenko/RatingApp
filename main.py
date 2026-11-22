import atexit
import os
import re
import shutil
import sys
import tempfile
import time
import uuid

from PySide6.QtCore import QSettings, QThread, Qt, QUrl
from PySide6.QtGui import (
    QActionGroup,
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QPalette,
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QFileDialog,
    QTreeWidget,
    QTreeWidgetItem,
    QMessageBox,
    QFrame,
    QProgressBar,
    QScrollArea,
    QStackedWidget,
    QDialog,
)

from workers import RatingWorker
from file_safety import has_macros

from analytics import (
    calculate_group_stats,
    calculate_overview,
    calculate_subject_stats,
    format_percent,
)
from result_views import GroupsView, SubjectsView
import archive
from expulsion_dialog import ExpulsionPage
from settings_dialog import SettingsDialog
from settings_store import load_settings, save_settings

# ──────────────────────────────────────────────────────────────
#  Тимчасові файли
# ──────────────────────────────────────────────────────────────
TEMP_PREFIX = "rating_program_"

# Папки старші за цей час вважаються залишками від минулих запусків
STALE_AFTER_SECONDS = 24 * 60 * 60

# Статус, пока пользователь выбирает действие в окне с ошибками
STATUS_DECISION_NEEDED = "Статус: Потрібне рішення щодо помилок"

def cleanup_stale_temp_dirs():
    """
    Видаляє залишки тимчасових папок від минулих запусків
    (аварійне завершення, файл був відкритий в Excel тощо).

    Свіжі папки не чіпаємо: вони можуть належати іншому
    запущеному екземпляру програми.
    """
    base = tempfile.gettempdir()
    now = time.time()

    try:
        names = os.listdir(base)
    except OSError:
        return

    for name in names:

        if not name.startswith(TEMP_PREFIX):
            continue

        path = os.path.join(base, name)

        if os.path.islink(path) or not os.path.isdir(path):
            continue

        try:
            age = now - os.path.getmtime(path)
        except OSError:
            continue

        if age > STALE_AFTER_SECONDS:
            # Якщо щось зайняте, просто пропускаємо: спробуємо наступного разу
            shutil.rmtree(path, ignore_errors=True)

# ──────────────────────────────────────────────────────────────
#  Тема оформлення (плоский, мінімалістичний стиль)
# ──────────────────────────────────────────────────────────────
ACCENT = "#10B981"
ACCENT_HOVER = "#059669"
ACCENT_PRESSED = "#047857"
ACCENT_SOFT = "#ECFDF5"
BG = "#F8FAFC"
CARD = "#FFFFFF"
BORDER = "#E2E8F0"
TEXT = "#0F172A"
MUTED = "#64748B"
DANGER = "#EF4444"
WARNING = "#D97706"
SUCCESS = "#059669"

# Цвета стипендий (те же, что заливка строк в Excel-рейтинге)
SCHOLARSHIP_ORDINARY = "#C6DBD2"
SCHOLARSHIP_HIGHER = "#96BBF2"

STYLE = f"""
* {{
    font-family: "Segoe UI", "Inter", "Roboto", "Noto Sans", sans-serif;
    font-size: 13px;
    color: {TEXT};
}}

QMainWindow, QWidget#Root {{
    background: {BG};
}}

QFrame#Card {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}

QFrame#Tile {{
    background: {BG};
    border: none;
    border-radius: 10px;
}}

QFrame#Tile[kind="ordinary"] {{
    background: {SCHOLARSHIP_ORDINARY};
}}

QFrame#Tile[kind="higher"] {{
    background: {SCHOLARSHIP_HIGHER};
}}

QFrame#Tile[kind="ordinary"] QLabel#StatTitle,
QFrame#Tile[kind="higher"] QLabel#StatTitle {{
    color: #334155;
}}

QFrame#Section {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}

QScrollArea {{
    background: transparent;
    border: none;
}}

QWidget#ScrollContent {{
    background: transparent;
}}

QLabel {{
    background: transparent;
}}

QLabel#Title {{
    font-size: 20px;
    font-weight: 700;
}}

QLabel#Subtitle {{
    color: {MUTED};
    font-size: 12px;
}}

QLabel#SectionTitle {{
    font-size: 13px;
    font-weight: 600;
}}

QLabel#Hint {{
    color: {MUTED};
    font-size: 12px;
}}

QLabel#StatTitle {{
    color: {MUTED};
    font-size: 11px;
}}

QLabel#StatValue {{
    font-size: 22px;
    font-weight: 700;
}}

QLabel#StatValue[kind="danger"]  {{ color: {DANGER}; }}

QLineEdit {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus {{
    border: 1px solid {ACCENT};
    background: {CARD};
}}

/* ── Кнопки ── */
QPushButton {{
    border-radius: 8px;
    padding: 7px 14px;
    font-weight: 600;
    border: 1px solid {BORDER};
    background: {CARD};
}}
QPushButton:hover {{
    background: {ACCENT_SOFT};
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background: #D1FAE5;
}}
QPushButton:disabled {{
    color: #94A3B8;
    background: #F1F5F9;
    border-color: {BORDER};
}}

QPushButton[variant="primary"] {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    color: white;
}}
QPushButton[variant="primary"]:hover   {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton[variant="primary"]:pressed {{ background: {ACCENT_PRESSED}; }}
QPushButton[variant="primary"]:disabled {{
    background: #A7F3D0;
    border-color: #A7F3D0;
    color: white;
}}

QPushButton[variant="ghost"] {{
    background: transparent;
    border: 1px solid transparent;
    color: {MUTED};
    padding: 4px 8px;
    font-weight: 500;
}}
QPushButton[variant="ghost"]:hover {{
    background: {ACCENT_SOFT};
    color: {ACCENT_HOVER};
}}
QPushButton[variant="ghost"]:disabled {{
    background: transparent;
    border-color: transparent;
    color: #CBD5E1;
}}

/* ── Дерево ── */
QTreeWidget {{
    background: transparent;
    border: none;
    outline: none;
}}
QTreeWidget::item {{
    padding: 4px 2px;
    border-radius: 6px;
}}
QTreeWidget::item:hover {{
    background: {BG};
}}
QTreeWidget::item:selected {{
    background: {ACCENT_SOFT};
    color: {TEXT};
}}
QTreeView::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 5px;
    border: 1.5px solid #CBD5E1;
    background: {CARD};
}}
QTreeView::indicator:hover {{
    border-color: {ACCENT};
}}
QTreeView::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><path d='M3.5 8.5l3 3 6-7' fill='none' stroke='white' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/></svg>");
}}
QTreeView::indicator:indeterminate {{
    background: {CARD};
    border-color: {ACCENT};
}}

/* ── Скролбар ── */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #CBD5E1;
    border-radius: 3px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: #94A3B8; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

/* ── Прогрес ── */
QProgressBar {{
    background: #E2E8F0;
    border: none;
    border-radius: 1px;
    max-height: 2px;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 1px;
}}

/* ── Статус ── */
QLabel#Status {{
    border-radius: 8px;
    padding: 6px 12px;
    background: {CARD};
    border: 1px solid {BORDER};
    color: {MUTED};
    font-size: 12px;
}}
QLabel#Status[kind="success"] {{ background: #ECFDF5; border-color: #A7F3D0; color: {SUCCESS}; }}
QLabel#Status[kind="error"]   {{ background: #FEF2F2; border-color: #FECACA; color: {DANGER}; }}
QLabel#Status[kind="warning"] {{ background: #FFFBEB; border-color: #FDE68A; color: {WARNING}; }}
QLabel#Status[kind="busy"]    {{ background: {ACCENT_SOFT}; border-color: #A7F3D0; color: {ACCENT_HOVER}; }}

QMessageBox {{
    background: {CARD};
}}

QTableWidget {{
    background: {CARD};
    alternate-background-color: {BG};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QTableWidget::item {{
    padding: 0px 4px;
}}
QHeaderView::section {{
    background: {BG};
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 4px 4px;
    font-size: 11px;
    font-weight: 600;
}}
QHeaderView::up-arrow, QHeaderView::down-arrow {{
    image: none;
    width: 0px;
    height: 0px;
}}
QTableCornerButton::section {{
    background: {BG};
    border: none;
}}
QMenuBar {{
    background: {BG};
    border-bottom: 1px solid {BORDER};
}}
QMenuBar::item {{
    padding: 5px 12px;
    background: transparent;
    border-radius: 6px;
}}
QMenuBar::item:selected {{
    background: {ACCENT_SOFT};
}}
QMenu {{
    background: {CARD};
    border: 1px solid {BORDER};
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 22px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: {ACCENT_SOFT};
}}
"""

# ──────────────────────────────────────────────────────────────
#  Темна тема
# ──────────────────────────────────────────────────────────────
SETTINGS_ORG = "RatingProgram"
SETTINGS_APP = "RatingApp"
THEME_MODES = ("light", "dark", "system")

ICON_LIGHT = "rating_image.ico"
ICON_DARK = "rating_image_dark.ico" 

# Колір світлої теми -> колір темної. Усі кольори #RRGGBB у STYLE
# замінюються за цією таблицею за один прохід, самі стилі не дублюються.
DARK_COLORS = {
    "#059669": "#34D399",   # акцент при наведенні, текст «успіх»
    "#047857": "#0D9468",   # акцент натиснутий
    "#ECFDF5": "#12352B",   # м'який акцент (наведення, виділення)
    "#F8FAFC": "#0F172A",   # фон вікна
    "#FFFFFF": "#1E293B",   # картки, поля
    "#E2E8F0": "#334155",   # рамки
    "#0F172A": "#E2E8F0",   # текст
    "#64748B": "#94A3B8",   # приглушений текст
    "#EF4444": "#F87171",   # помилка / борг
    "#D97706": "#FBBF24",   # попередження
    "#C6DBD2": "#1F4D3F",   # плитка: звичайна стипендія
    "#96BBF2": "#1E3A6B",   # плитка: підвищена стипендія
    "#334155": "#CBD5E1",   # заголовок на кольорових плитках
    "#D1FAE5": "#14463A",   # кнопка натиснута
    "#94A3B8": "#64748B",   # неактивний текст, скролбар (наведення)
    "#F1F5F9": "#172033",   # неактивна кнопка
    "#A7F3D0": "#065F46",   # неактивна головна кнопка, рамки статусів
    "#CBD5E1": "#475569",   # рамка прапорця, скролбар
    "#FEF2F2": "#3B1519",   # статус «помилка»: фон
    "#FECACA": "#7F1D1D",   # статус «помилка»: рамка
    "#FFFBEB": "#3A2A0B",   # статус «попередження»: фон
    "#FDE68A": "#78530F",   # статус «попередження»: рамка
}

_HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}\b")


def recolor(style, mapping):
    """Замінює кольори #RRGGBB у стилі за таблицею (за один прохід)."""
    return _HEX_COLOR.sub(
        lambda match: mapping.get(match.group(0).upper(), match.group(0)),
        style
    )


STYLE_DARK = recolor(STYLE, DARK_COLORS)

# Палітра Qt потрібна для того, що не покрито стилями:
# діалоги, випадні списки, поля вводу, прапорці.
LIGHT_PALETTE = {
    "window": "#F8FAFC", "base": "#FFFFFF", "alt": "#F8FAFC",
    "button": "#FFFFFF", "text": "#0F172A", "muted": "#64748B",
    "disabled": "#94A3B8", "accent": "#10B981",
}

DARK_PALETTE = {
    "window": "#0F172A", "base": "#1E293B", "alt": "#0F172A",
    "button": "#1E293B", "text": "#E2E8F0", "muted": "#94A3B8",
    "disabled": "#64748B", "accent": "#10B981",
}


def make_palette(colors):
    palette = QPalette()

    for role, key in (
        (QPalette.ColorRole.Window, "window"),
        (QPalette.ColorRole.WindowText, "text"),
        (QPalette.ColorRole.Base, "base"),
        (QPalette.ColorRole.AlternateBase, "alt"),
        (QPalette.ColorRole.Text, "text"),
        (QPalette.ColorRole.Button, "button"),
        (QPalette.ColorRole.ButtonText, "text"),
        (QPalette.ColorRole.ToolTipBase, "base"),
        (QPalette.ColorRole.ToolTipText, "text"),
        (QPalette.ColorRole.PlaceholderText, "muted"),
        (QPalette.ColorRole.Highlight, "accent"),
    ):
        palette.setColor(role, QColor(colors[key]))

    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))

    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(
            QPalette.ColorGroup.Disabled, role, QColor(colors["disabled"])
        )

    return palette


def load_theme_mode():
    value = QSettings(SETTINGS_ORG, SETTINGS_APP).value("theme", "light")

    return value if value in THEME_MODES else "light"


def is_dark(app, mode):
    """True, якщо для режиму mode потрібна темна тема."""
    if mode == "dark":
        return True

    if mode == "system":
        try:
            return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
        except AttributeError:
            return False    # стара версія Qt: системну тему не визначити

    return False


def apply_theme(app, mode):
    dark = is_dark(app, mode)

    app.setPalette(make_palette(DARK_PALETTE if dark else LIGHT_PALETTE))
    app.setStyleSheet(STYLE_DARK if dark else STYLE)

    # Иконка окна и панели задач следует за темой
    app.setWindowIcon(
        QIcon(resource_path(ICON_DARK if dark else ICON_LIGHT))
    )


def make_card():
    """Плоска картка без тіней — легша для відмальовування."""
    card = QFrame()
    card.setObjectName("Card")
    return card


def repolish(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class CollapsibleSection(QFrame):
    """
    Розділ із заголовком і кнопкою «Розгорнути / Згорнути».
    Спочатку згорнутий: видно лише заголовок.
    """

    def __init__(self, title, content, expanded=False, parent=None):
        super().__init__(parent)

        self.setObjectName("Section")

        self._content = content
        self._expanded = expanded

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")

        self._toggle_button = QPushButton()
        self._toggle_button.setProperty("variant", "ghost")
        self._toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_button.clicked.connect(self.toggle)

        header.addWidget(title_label)
        header.addStretch()
        header.addWidget(self._toggle_button)

        layout.addLayout(header)
        layout.addWidget(content)

        self.set_expanded(expanded)

    def is_expanded(self):
        return self._expanded

    def toggle(self):
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded):
        self._expanded = expanded
        self._content.setVisible(expanded)
        self._toggle_button.setText(
            "Згорнути" if expanded else "Розгорнути"
        )


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.output_file = None   # файл рейтингу у тимчасовій папці
        self.file_path = ""

        # Тимчасова папка для порахованих рейтингів.
        # Видаляється при завершенні програми.
        self.temp_dir = tempfile.mkdtemp(prefix=TEMP_PREFIX)
        atexit.register(shutil.rmtree, self.temp_dir, True)

        self.pending_groups = []        # групи, які зараз рахуються
        self.result_groups = []         # групи поточного результату
        self.has_unsaved_result = False

        self.worker_thread = None
        self.worker = None
        self.busy = False
        self.pending_validation = None

        # Правила стипендій і кольори таблиці (зберігаються в QSettings)
        self.rules, self.colors = load_settings(
            QSettings(SETTINGS_ORG, SETTINGS_APP)
        )

        self.setWindowTitle("Підрахунок рейтингу")
        self.resize(1000, 640)
        self.setMinimumSize(860, 540)
        self.setAcceptDrops(True)

        # ── Меню «Тема» ──
        theme_menu = self.menuBar().addMenu("Тема")
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)

        self._theme_actions = {}
        current_mode = load_theme_mode()

        for mode, title in (
            ("light", "Світла"),
            ("dark", "Темна"),
            ("system", "Як у системі"),
        ):
            action = theme_menu.addAction(title)
            action.setCheckable(True)
            action.setChecked(mode == current_mode)
            theme_group.addAction(action)
            action.triggered.connect(
                lambda checked=False, chosen=mode: self.set_theme(chosen)
            )
            self._theme_actions[mode] = action
            
        # ── «Налаштування» ──
        self.settings_action = self.menuBar().addAction("Налаштування")
        self.settings_action.triggered.connect(self.open_settings)
        
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)

        # Сторінки: 0 — рейтинг, 1 — кандидати на відрахування
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self.pages = QStackedWidget()
        root_layout.addWidget(self.pages)

        rating_page = QWidget()
        self.pages.addWidget(rating_page)

        main_layout = QVBoxLayout(rating_page)
        main_layout.setContentsMargins(20, 16, 20, 14)
        main_layout.setSpacing(12)

        # ── Шапка ──
        header = QHBoxLayout()
        header.setSpacing(10)

        title = QLabel("Рейтинг студентів")
        title.setObjectName("Title")

        self.expulsion_button = QPushButton("Кандидати на відрахування >")
        self.expulsion_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.expulsion_button.clicked.connect(self.show_expulsion_page)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.expulsion_button)
        main_layout.addLayout(header)

        # ── Вибір файлу (один рядок) ──
        file_card = make_card()
        file_row = QHBoxLayout(file_card)
        file_row.setContentsMargins(12, 10, 12, 10)
        file_row.setSpacing(8)

        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText(
            "Оберіть журнал Excel або перетягніть файл у вікно..."
        )
        self.file_edit.setReadOnly(True)

        self.select_button = QPushButton("Обрати журнал")
        self.select_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_button.clicked.connect(self.select_file)

        self.start_button = QPushButton("Завантажити групи")
        self.start_button.setProperty("variant", "primary")
        self.start_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_button.clicked.connect(self.start_program)

        file_row.addWidget(self.file_edit, 1)
        file_row.addWidget(self.select_button)
        file_row.addWidget(self.start_button)

        main_layout.addWidget(file_card)

        # ── Основна область ──
        content_layout = QHBoxLayout()
        content_layout.setSpacing(12)

        # Ліворуч — дерево груп + дії
        tree_card = make_card()
        tree_layout = QVBoxLayout(tree_card)
        tree_layout.setContentsMargins(14, 12, 14, 12)
        tree_layout.setSpacing(8)

        tree_header = QHBoxLayout()
        tree_header.setSpacing(4)
        tree_title = QLabel("Групи")
        tree_title.setObjectName("SectionTitle")
        tree_header.addWidget(tree_title)
        tree_header.addStretch()

        self.expand_button = QPushButton("Розгорнути")
        self.expand_button.setProperty("variant", "ghost")
        self.expand_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.expand_button.clicked.connect(lambda: self.tree.expandAll())

        self.collapse_button = QPushButton("Згорнути")
        self.collapse_button.setProperty("variant", "ghost")
        self.collapse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.collapse_button.clicked.connect(lambda: self.tree.collapseAll())

        tree_header.addWidget(self.expand_button)
        tree_header.addWidget(self.collapse_button)
        tree_layout.addLayout(tree_header)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Пошук групи...")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self.apply_filter)
        tree_layout.addWidget(self.filter_edit)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(20)
        self.tree.setAnimated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.itemChanged.connect(self.on_item_changed)
        tree_layout.addWidget(self.tree, 1)

        # Дії та лічильник — внизу картки груп
        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)

        self.selected_label = QLabel("Обрано груп: 0")
        self.selected_label.setObjectName("Hint")

        self.cancel_button = QPushButton("Скинути")
        self.cancel_button.setProperty("variant", "ghost")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.cancel_selection)

        self.continue_button = QPushButton("Порахувати рейтинг")
        self.continue_button.setProperty("variant", "primary")
        self.continue_button.setMinimumHeight(36)
        self.continue_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.continue_button.clicked.connect(self.get_selected_groups)

        actions_row.addWidget(self.selected_label)
        actions_row.addWidget(self.cancel_button)
        actions_row.addStretch()
        actions_row.addWidget(self.continue_button)
        tree_layout.addLayout(actions_row)

        # Ліворуч — статистика (розділи, що згортаються)
        stats_card = make_card()
        stats_card.setMinimumWidth(270)
        stats_layout = QVBoxLayout(stats_card)
        stats_layout.setContentsMargins(14, 12, 14, 12)
        stats_layout.setSpacing(8)

        # ── Загальна статистика: плитки ──
        stats_grid = QGridLayout()
        stats_grid.setSpacing(8)

        self.total_students_label = QLabel("—")
        self.debtors_label = QLabel("—")
        self.ordinary_scholarship_label = QLabel("—")
        self.higher_scholarship_label = QLabel("—")

        stats_items = [
            ("Студентів", self.total_students_label, ""),
            ("З боргами", self.debtors_label, "danger"),
            ("Звичайна стипендія", self.ordinary_scholarship_label, "ordinary"),
            ("Підвищена стипендія", self.higher_scholarship_label, "higher"),
        ]

        for index, (name, value_label, kind) in enumerate(stats_items):
            tile = QFrame()
            tile.setObjectName("Tile")
            if kind:
                tile.setProperty("kind", kind)
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(12, 8, 12, 8)
            tile_layout.setSpacing(0)

            name_label = QLabel(name)
            name_label.setObjectName("StatTitle")
            name_label.setWordWrap(True)

            value_label.setObjectName("StatValue")
            if kind:
                value_label.setProperty("kind", kind)

            tile_layout.addWidget(name_label)
            tile_layout.addWidget(value_label)

            stats_grid.addWidget(tile, index // 2, index % 2)

        overview_content = QWidget()
        overview_layout = QVBoxLayout(overview_content)
        overview_layout.setContentsMargins(0, 0, 0, 0)
        overview_layout.addLayout(stats_grid)

        self.overview_section = CollapsibleSection(
            "Загальна статистика",
            overview_content
        )
        self.groups_view = GroupsView()
        self.subjects_view = SubjectsView()

        self.groups_section = CollapsibleSection(
            "Порівняння груп",
            self.groups_view
        )
        self.subjects_section = CollapsibleSection(
            "Аналіз дисциплін",
            self.subjects_view
        )

        # ── Прокручувана область з розділами ──
        sections_container = QWidget()
        sections_container.setObjectName("ScrollContent")

        sections_layout = QVBoxLayout(sections_container)
        sections_layout.setContentsMargins(0, 0, 6, 0)
        sections_layout.setSpacing(10)
        sections_layout.addWidget(self.overview_section)
        sections_layout.addWidget(self.groups_section)
        sections_layout.addWidget(self.subjects_section)
        sections_layout.addStretch()

        sections_scroll = QScrollArea()
        sections_scroll.setWidgetResizable(True)
        sections_scroll.setFrameShape(QFrame.Shape.NoFrame)
        sections_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        sections_scroll.setWidget(sections_container)

        stats_layout.addWidget(sections_scroll, 1)

        # ── Кнопки внизу картки (не прокручуються) ──
        self.save_button = QPushButton("Зберегти рейтинг")
        self.save_button.setProperty("variant", "primary")
        self.save_button.setMinimumHeight(36)
        self.save_button.setEnabled(False)
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.clicked.connect(self.save_rating)

        self.view_rating_button = QPushButton("Відкрити рейтинг")
        self.view_rating_button.setMinimumHeight(36)
        self.view_rating_button.setEnabled(False)
        self.view_rating_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.view_rating_button.clicked.connect(self.view_rating)

        stats_layout.addWidget(self.save_button)
        stats_layout.addWidget(self.view_rating_button)

        content_layout.addWidget(stats_card, 3)
        content_layout.addWidget(tree_card, 2)
        main_layout.addLayout(content_layout, 1)

        # ── Прогрес + статус ──
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        main_layout.addWidget(self.progress)

        self.status_label = QLabel()
        self.status_label.setObjectName("Status")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.status_label)

        self.expulsion_page = ExpulsionPage(archive.ARCHIVE_DIR)
        self.expulsion_page.back_requested.connect(self.show_rating_page)
        self.pages.addWidget(self.expulsion_page)

        self.set_status("Статус: Очікування")
        self._update_selection_state()
        self._update_step_buttons()

    # ──────────────────────────────────────────────────────────
    #  Допоміжне
    # ──────────────────────────────────────────────────────────
    def set_status(self, text, kind=None):
        """Показує статус; колір підбирається за змістом тексту."""

        if kind is None:
            lowered = text.lower()
            if lowered.startswith("помилка"):
                kind = "error"
            elif "готовий" in lowered or "побудовано" in lowered:
                kind = "success"
            elif (
                "скасовано" in lowered
                or "зупинено" in lowered
                or "рішення" in lowered
                or "виправте" in lowered
            ):
                kind = "warning"
            elif self.busy:
                kind = "busy"
            else:
                kind = "info"

        self.status_label.setText(text)
        self.status_label.setProperty("kind", kind)
        repolish(self.status_label)

    def _reset_statistics(self):
        """Очищує статистику попереднього розрахунку."""

        for label in (
            self.total_students_label,
            self.debtors_label,
            self.ordinary_scholarship_label,
            self.higher_scholarship_label,
        ):
            label.setText("—")
            
        self.groups_view.clear()
        self.subjects_view.clear()

    def _iter_groups(self):
        """Повертає (спеціальність, курс, елемент групи) для всіх груп."""

        for i in range(self.tree.topLevelItemCount()):
            specialty_item = self.tree.topLevelItem(i)

            for j in range(specialty_item.childCount()):
                course_item = specialty_item.child(j)

                for k in range(course_item.childCount()):
                    yield (
                        specialty_item,
                        course_item,
                        course_item.child(k),
                    )

    def _update_selection_state(self):
        count = sum(
            1
            for _, _, group in self._iter_groups()
            if group.checkState(0) == Qt.CheckState.Checked
        )

        self.selected_label.setText(f"Обрано груп: {count}")

        self.continue_button.setEnabled(
            not self.busy and count > 0
        )
        self.cancel_button.setEnabled(
            not self.busy and count > 0
        )

    def _update_step_buttons(self):
        """
        Цветом кнопок подсказывает пользователю следующий шаг.
        Зелёной всегда бывает одна из двух кнопок, они чередуются:

        файл не выбран      — зелёная «Обрати журнал»
        файл выбран         — зелёная «Завантажити групи»
        группы загружены    — зелёная «Обрати журнал»
        """

        file_chosen = bool(self.file_path)
        groups_loaded = self.tree.topLevelItemCount() > 0

        # «Завантажити групи» зелёная, только когда файл выбран,
        # а группы ещё не загружены
        load_is_next = file_chosen and not groups_loaded

        for button, is_next in (
            (self.select_button, not load_is_next),
            (self.start_button, load_is_next),
        ):
            button.setProperty(
                "variant",
                "primary" if is_next else ""
            )
            repolish(button)
    
    # ──────────────────────────────────────────────────────────
    #  Файл
    # ──────────────────────────────────────────────────────────
    def dragEnterEvent(self, event):
        if (
            event.mimeData().hasUrls()
            and not self.busy
            and self.pages.currentIndex() == 0
        ):
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith((".xlsx", ".xlsm")):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".xlsx", ".xlsm")):
                if self._confirm_discard_unsaved():
                    self._set_file(path)
                return

    def closeEvent(self, event):
        if self.busy or self.expulsion_page.is_busy():
            QMessageBox.information(
                self,
                "Зачекайте",
                "Зараз виконується обробка журналу.\n"
                "Дочекайтесь завершення і закрийте програму."
            )
            event.ignore()
            return

        if not self._confirm_discard_unsaved():
            event.ignore()
            return
        
        event.accept()
    
    def select_file(self):

        if self.busy:
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Оберіть журнал",
            "",
            "Excel files (*.xlsx *.xlsm)"
        )

        if file_path and self._confirm_discard_unsaved():
            self._set_file(file_path)

    def _set_file(self, file_path):

        self.file_path = file_path
        self.file_edit.setText(file_path)

        # Старий результат не беремо для нового журналу
        self._discard_result()
        
        self.tree.clear()
        self.filter_edit.clear()
        self._update_selection_state()
        self._update_step_buttons()

        self.set_status("Статус: Журнал обрано. Натисніть «Завантажити групи»", "info")

    # ──────────────────────────────────────────────────────────
    #  Дерево
    # ──────────────────────────────────────────────────────────
    def on_item_changed(self, item, column):

        self.tree.blockSignals(True)

        try:
            state = item.checkState(column)

            # Часткове позначення не поширюється вниз
            if state != Qt.CheckState.PartiallyChecked:
                self.set_children_checked(item, state)

            self.update_parents(item)

        finally:
            self.tree.blockSignals(False)

        self._update_selection_state()

    def apply_filter(self, text):
        """Ховає групи, які не підходять під пошуковий запит."""

        query = text.strip().lower()

        for i in range(self.tree.topLevelItemCount()):
            specialty_item = self.tree.topLevelItem(i)
            specialty_visible = False

            for j in range(specialty_item.childCount()):
                course_item = specialty_item.child(j)
                course_visible = False

                for k in range(course_item.childCount()):
                    group_item = course_item.child(k)
                    match = (
                        not query
                        or query in group_item.text(0).lower()
                    )
                    group_item.setHidden(not match)
                    course_visible = course_visible or match

                course_item.setHidden(not course_visible)
                specialty_visible = specialty_visible or course_visible

            specialty_item.setHidden(not specialty_visible)

        if query:
            self.tree.expandAll()

    def cancel_selection(self):

        if self.busy:
            return

        self.tree.blockSignals(True)

        try:
            for i in range(self.tree.topLevelItemCount()):
                specialty_item = self.tree.topLevelItem(i)
                specialty_item.setCheckState(0, Qt.CheckState.Unchecked)
                self.set_children_checked(
                    specialty_item,
                    Qt.CheckState.Unchecked,
                    include_hidden=True
                )
        finally:
            self.tree.blockSignals(False)

        self._update_selection_state()
        self.set_status("Статус: Вибір груп скасовано")

    def set_children_checked(self, item, state, include_hidden=False):
        """
        Рекурсивно встановлює стан усім дочірнім елементам.

        Приховані (відфільтровані) елементи пропускаються,
        якщо не вказано include_hidden=True.
        """
        for i in range(item.childCount()):
            child = item.child(i)

            if child.isHidden() and not include_hidden:
                continue

            child.setCheckState(0, state)
            self.set_children_checked(child, state, include_hidden)

    def update_parents(self, item):
        """
        Батько: відмічений — коли відмічені всі діти,
        частково — коли відмічена лише частина.
        """

        parent = item.parent()

        while parent is not None:
            checked = 0
            partial = False

            for i in range(parent.childCount()):
                child_state = parent.child(i).checkState(0)

                if child_state == Qt.CheckState.Checked:
                    checked += 1
                elif child_state == Qt.CheckState.PartiallyChecked:
                    partial = True

            if checked == parent.childCount():
                new_state = Qt.CheckState.Checked
            elif checked > 0 or partial:
                new_state = Qt.CheckState.PartiallyChecked
            else:
                new_state = Qt.CheckState.Unchecked

            parent.setCheckState(0, new_state)
            parent = parent.parent()

    # ──────────────────────────────────────────────────────────
    #  Результат розрахунку (тимчасовий файл + збереження)
    # ──────────────────────────────────────────────────────────

    def _update_result_buttons(self):
        """«Зберегти» і «Відкрити» доступні, коли є готовий файл."""
        has_result = bool(
            not self.busy
            and self.output_file
            and os.path.exists(self.output_file)
        )

        self.save_button.setEnabled(has_result)
        self.view_rating_button.setEnabled(has_result)

    def _discard_result(self):
        """Забуває поточний результат: видаляє тимчасовий файл і статистику."""
        if self.output_file:
            try:
                os.remove(self.output_file)
            except OSError:
                # Файл може бути відкритий в Excel — його прибере
                # очищення тимчасової папки при виході
                pass

        self.output_file = None
        self.has_unsaved_result = False
        self.result_groups = []

        self._reset_statistics()
        self._update_result_buttons()

    def _new_temp_output_path(self):
        """Унікальне ім'я, щоб не конфліктувати з файлом, відкритим в Excel."""
        return os.path.join(
            self.temp_dir,
            f"rating_{uuid.uuid4().hex[:8]}.xlsx"
        )

    def _start_calculation(self, groups):
        self.pending_groups = list(groups)

        self._start_worker(
            "calculate",
            self.file_path,
            self.pending_groups,
            self._new_temp_output_path(),
            self.rules,
            self.colors
        )

    def _suggest_file_name(self):
        """Запропоноване ім'я для вікна збереження (довгий список скорочуємо)."""
        groups = self.result_groups
        text = ", ".join(groups)

        if len(text) > 80:
            text = f"{groups[0]} +{len(groups) - 1} груп"

        return f"Рейтинг({text}).xlsx"

    def save_rating(self):
        """
        Копіює порахований рейтинг туди, куди вкаже користувач.
        Повертає True, якщо файл збережено.
        """
        if (
            not self.output_file
            or not os.path.exists(self.output_file)
        ):
            QMessageBox.warning(
                self,
                "Помилка",
                "Файл рейтингу не знайдено. Порахуйте рейтинг ще раз."
            )
            return False

        start_dir = (
            os.path.dirname(self.file_path)
            if self.file_path
            else ""
        )

        target, _ = QFileDialog.getSaveFileName(
            self,
            "Зберегти рейтинг",
            os.path.join(start_dir, self._suggest_file_name()),
            "Excel files (*.xlsx)"
        )

        if not target:
            return False

        if not target.lower().endswith(".xlsx"):
            target += ".xlsx"

        try:
            shutil.copyfile(self.output_file, target)

        except PermissionError:
            QMessageBox.critical(
                self,
                "Помилка",
                "Не вдалося зберегти файл.\n\n"
                "Можливо, він уже відкритий в Excel. "
                "Закрийте його або оберіть інше ім'я."
            )
            return False

        except OSError as error:
            QMessageBox.critical(
                self,
                "Помилка",
                f"Не вдалося зберегти файл:\n{error}"
            )
            return False

        self.has_unsaved_result = False

        self.set_status(
            f"Статус: Рейтинг збережено: {target}",
            "success"
        )

        return True

    def _confirm_discard_unsaved(self):
        """
        Перед діями, які знищать поточний результат.
        Повертає True, якщо можна продовжувати.
        """
        if not self.has_unsaved_result:
            return True

        message_box = QMessageBox(self)
        message_box.setIcon(QMessageBox.Icon.Warning)
        message_box.setWindowTitle("Рейтинг не збережено")
        message_box.setText(
            "Поточний рейтинг не збережено.\n"
            "Якщо продовжити, результат буде втрачено."
        )

        save_button = message_box.addButton(
            "Зберегти",
            QMessageBox.ButtonRole.AcceptRole
        )
        discard_button = message_box.addButton(
            "Не зберігати",
            QMessageBox.ButtonRole.DestructiveRole
        )
        message_box.addButton(
            "Скасувати",
            QMessageBox.ButtonRole.RejectRole
        )

        message_box.exec()

        clicked = message_box.clickedButton()

        if clicked is save_button:
            # Якщо користувач закрив вікно збереження — не продовжуємо
            return self.save_rating()

        return clicked is discard_button
    
    # ──────────────────────────────────────────────────────────
    #  Розрахунок
    # ──────────────────────────────────────────────────────────
    def get_selected_groups(self):

        if self.busy:
            return

        selected_groups = []
        selected_specialties = set()
        selected_courses = set()

        for specialty_item, course_item, group_item in self._iter_groups():

            if group_item.checkState(0) == Qt.CheckState.Checked:
                selected_groups.append(group_item.text(0))
                selected_specialties.add(specialty_item.text(0))
                selected_courses.add(course_item.text(0))

        if not selected_groups:
            self.set_status("Помилка: Не обрано жодної групи!")
            return

        different_specialties = len(selected_specialties) > 1
        different_courses = len(selected_courses) > 1

        # Попередження, якщо обрано групи з різних курсів та/або спеціальностей
        if different_specialties or different_courses:

            warning_text = "Обрано групи різних "

            if different_specialties:
                warning_text += "спеціальностей\n"

            if different_courses:
                warning_text += "курсів\n"

            warning_text += "\nПорахувати рейтинг для обраних груп?"

            answer = QMessageBox.question(
                self,
                "Попередження",
                warning_text,
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if answer != QMessageBox.StandardButton.Yes:
                self.set_status("Статус: Вибір скасовано")
                return

        if not self.file_path:
            self.set_status("Помилка: Спочатку оберіть журнал!")
            return

        if not self._confirm_discard_unsaved():
            return

        self._discard_result()
        self._start_calculation(selected_groups)

    def _open_journal_for_editing(self):
        """
        Открывает журнал для исправления в Excel.

        Если в журнале есть макросы, Excel их запустит (защищённый режим
        срабатывает не всегда), поэтому файл не открываем,
        а показываем папку, где он лежит.
        """
        path = os.path.abspath(self.file_path)

        if has_macros(path):

            QMessageBox.information(
                self,
                "Журнал містить макроси",
                "Цей журнал має формат із макросами (.xlsm).\n\n"
                "З міркувань безпеки програма не відкриває такі файли "
                "автоматично. Зараз відкриється папка з файлом: відкрийте "
                "його самостійно (макроси краще не вмикати) або збережіть "
                "копію як .xlsx."
            )

            QDesktopServices.openUrl(
                QUrl.fromLocalFile(os.path.dirname(path))
            )

            return

        QDesktopServices.openUrl(
            QUrl.fromLocalFile(path)
        )
    
    def view_rating(self):

        if self.output_file and os.path.exists(self.output_file):

            QDesktopServices.openUrl(
                QUrl.fromLocalFile(
                    os.path.abspath(self.output_file)
                )
            )

        else:

            QMessageBox.warning(
                self,
                "Помилка",
                "Файл рейтингу не знайдено."
            )

    def set_theme(self, mode):
        """Перемикає тему оформлення й запам'ятовує вибір."""
        QSettings(SETTINGS_ORG, SETTINGS_APP).setValue("theme", mode)
        apply_theme(QApplication.instance(), mode)

    def open_settings(self):
        """Вікно «Налаштування»: правила стипендій і кольори таблиці."""

        if self.busy:
            QMessageBox.information(
                self,
                "Налаштування",
                "Зачекайте, поки завершиться поточна операція."
            )
            return

        dialog = SettingsDialog(self.rules, self.colors, self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_rules, new_colors = dialog.result_values()

        if new_rules == self.rules and new_colors == self.colors:
            return

        self.rules = new_rules
        self.colors = new_colors

        save_settings(
            QSettings(SETTINGS_ORG, SETTINGS_APP),
            new_rules,
            new_colors
        )

        # Готовий рейтинг пораховано за старими налаштуваннями
        if not self.output_file:
            return

        answer = QMessageBox.question(
            self,
            "Перерахувати рейтинг?",
            "Налаштування змінено, а поточний рейтинг пораховано "
            "за попередніми. Перерахувати його зараз?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if answer == QMessageBox.StandardButton.Yes:
            groups = list(self.result_groups)
            self._discard_result()
            self._start_calculation(groups)
        else:
            self.set_status(
                "Статус: Налаштування змінено, а рейтинг пораховано "
                "за попередніми правилами"
            )

    def show_expulsion_page(self):
        """Переходить на сторінку кандидатів на відрахування."""

        if self.busy:
            return

        self.pages.setCurrentWidget(self.expulsion_page)
        self.settings_action.setVisible(False)
        self.setWindowTitle("Кандидати на відрахування")

    def show_rating_page(self):
        """Повертається на головну сторінку підрахунку рейтингу."""

        if self.expulsion_page.is_busy():
            return

        self.pages.setCurrentIndex(0)
        self.settings_action.setVisible(True)
        self.setWindowTitle("Підрахунок рейтингу")
    
    def start_program(self):

        if self.busy:
            return

        if not self.file_path:
            self.set_status("Помилка: Спочатку оберіть журнал!")
            return

        self._start_worker("structure", self.file_path)

    # ──────────────────────────────────────────────────────────
    #  Стан інтерфейсу
    # ──────────────────────────────────────────────────────────
    def _set_busy(self, busy):

        self.busy = busy

        self.select_button.setEnabled(not busy)
        self.start_button.setEnabled(not busy)
        self.tree.setEnabled(not busy)
        self.filter_edit.setEnabled(not busy)
        self.progress.setVisible(busy)
        self.expulsion_button.setEnabled(not busy)

        self._update_selection_state()
        self._update_step_buttons()

        self._update_result_buttons()
        
    # ──────────────────────────────────────────────────────────
    #  Worker + QThread
    # ──────────────────────────────────────────────────────────
    def _start_worker(self, operation, *args):

        if self.busy:
            return

        self._set_busy(True)

        self.set_status("Статус: Підготовка...", "busy")

        self.worker_thread = QThread(self)
        self.worker = RatingWorker()
        self.worker.moveToThread(self.worker_thread)

        self.worker.configure(operation, *args)

        # Сигнали Worker
        self.worker.status.connect(
            self._on_worker_status
        )
        self.worker.structure_finished.connect(
            self._on_structure_finished
        )
        self.worker.validation_required.connect(
            self._on_validation_required
        )
        self.worker.calculation_finished.connect(
            self._on_calculation_finished
        )
        self.worker.error.connect(
            self._on_worker_error
        )

        # Запуск Worker
        self.worker_thread.started.connect(self.worker.run)

        # Завершення потоку
        self.worker.error.connect(self.worker_thread.quit)
        self.worker.calculation_finished.connect(self.worker_thread.quit)

        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self._cleanup_thread)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)

        self.worker_thread.start()

    def _on_worker_status(self, text):
        self.set_status(text, "busy")
    
    def _on_validation_required(self, valid_sheets, validation_errors):

        self.set_status(STATUS_DECISION_NEEDED, "warning")

        message_box = QMessageBox(self)
        message_box.setIcon(QMessageBox.Icon.Warning)
        message_box.setWindowTitle("Помилки у вибраних групах")
        message_box.setText(
            "Не всі вибрані групи можна обробити.\n\n"
            "Проблемні групи:\n"
            + "\n".join(validation_errors)
        )

        edit_button = message_box.addButton(
            "Зупинити та змінити вхідний файл",
            QMessageBox.ButtonRole.AcceptRole
        )

        message_box.addButton(
            "Зупинити",
            QMessageBox.ButtonRole.RejectRole
        )

        continue_button = message_box.addButton(
            "Продовжити підрахунок інших груп",
            QMessageBox.ButtonRole.DestructiveRole
        )

        if not valid_sheets:
            continue_button.setEnabled(False)

        message_box.exec()

        clicked_button = message_box.clickedButton()

        if clicked_button is edit_button:
            self.pending_validation = {"action": "edit"}

        elif clicked_button is continue_button:
            self.pending_validation = {
                "action": "continue",
                "sheets": valid_sheets
            }

        else:
            self.pending_validation = {"action": "stop"}

        self.worker_thread.quit()

    def _on_structure_finished(self, specialties, ignored_sheets):

        self.tree.blockSignals(True)

        try:
            self.tree.clear()

            for specialty in specialties:

                specialty_item = QTreeWidgetItem([specialty.name])
                specialty_item.setCheckState(0, Qt.CheckState.Unchecked)
                self.tree.addTopLevelItem(specialty_item)

                font = specialty_item.font(0)
                font.setWeight(QFont.Weight.DemiBold)
                specialty_item.setFont(0, font)

                for course in specialty.courses:

                    course_item = QTreeWidgetItem([course.name])
                    course_item.setCheckState(0, Qt.CheckState.Unchecked)
                    specialty_item.addChild(course_item)

                    for group in course.groups:

                        group_item = QTreeWidgetItem([group.name])
                        group_item.setCheckState(0, Qt.CheckState.Unchecked)
                        course_item.addChild(group_item)

            self.tree.expandAll()

        finally:
            self.tree.blockSignals(False)

        self.filter_edit.clear()
        self._update_selection_state()
        self._update_step_buttons()

        # Інформація про нерозпізнані листи
        if ignored_sheets:

            self.set_status(STATUS_DECISION_NEEDED, "warning")

            message_box = QMessageBox(self)
            message_box.setIcon(QMessageBox.Icon.Warning)
            message_box.setWindowTitle("Нерозпізнані листи")
            message_box.setText(
                "Наступні листи не були розпізнані та не потрапили "
                "до списку груп:\n\n"
                + "\n".join(ignored_sheets)
                + "\n\nВиберіть подальшу дію."
            )

            edit_button = message_box.addButton(
                "Зупинити та змінити вхідний файл",
                QMessageBox.ButtonRole.AcceptRole
            )

            stop_button = message_box.addButton(
                "Зупинити",
                QMessageBox.ButtonRole.RejectRole
            )

            continue_button = message_box.addButton(
                "Продовжити імпорт інших листів",
                QMessageBox.ButtonRole.DestructiveRole
            )

            message_box.exec()

            clicked_button = message_box.clickedButton()

            if clicked_button is edit_button:

                self.set_status(
                    "Статус: Відкрийте журнал та виправте дані",
                    "warning"
                )

                self._open_journal_for_editing()

            elif clicked_button is stop_button:

                self.set_status("Статус: Імпорт зупинено", "warning")

            elif clicked_button is continue_button:

                self.set_status(
                    "Статус: Імпорт продовжено. "
                    "Нерозпізнані листи пропущено.",
                    "info"
                )

        else:

            self.set_status(
                "Статус: Структуру побудовано. "
                f"Спеціальностей: {len(specialties)}"
            )

        # Завершуємо потік після вибору користувача
        self.worker_thread.quit()

    def _on_calculation_finished(self, result):
        
        self.last_result = result
        self.output_file = result.output_file
        self.result_groups = list(result.group_names)
        self.has_unsaved_result = True

        self._show_result(result)

        self.set_status(
            "Статус: Рейтинг готовий. "
            f"Груп: {len(result.group_names)}, "
            f"студентів: {len(result.students)}",
            "success"
        )

    def _show_result(self, result):
        overview = calculate_overview(result)

        self.total_students_label.setText(str(overview.students))
        self.debtors_label.setText(
            f"{overview.debtors} "
            f"({format_percent(overview.debtors_percent)})"
        )
        self.ordinary_scholarship_label.setText(str(overview.ordinary))
        self.higher_scholarship_label.setText(str(overview.higher))

        self.groups_view.set_data(calculate_group_stats(result))
        self.subjects_view.set_data(calculate_subject_stats(result))

    def _on_worker_error(self, message):

        # Видаляє і недописаний тимчасовий файл
        self._discard_result()

        self.set_status("Помилка: обробку не завершено", "error")

        QMessageBox.critical(self, "Помилка", message)

    def _cleanup_thread(self):

        pending_validation = self.pending_validation
        self.pending_validation = None

        self.worker = None
        self.worker_thread = None

        self._set_busy(False)

        if pending_validation is None:
            return

        action = pending_validation["action"]

        if action == "stop":
            self.set_status("Статус: Підрахунок зупинено", "warning")
            return

        if action == "edit":

            self.set_status(
                "Статус: Відкрийте журнал та виправте дані",
                "warning"
            )

            self._open_journal_for_editing()

            return

        if action == "continue":
            self._start_calculation(pending_validation["sheets"])

def resource_path(relative_path):
    """Шлях до файлу ресурсу: працює і з .py, і зі зібраного .exe."""
    base_path = getattr(sys, "_MEIPASS", None) or os.path.dirname(
        os.path.abspath(__file__)
    )

    return os.path.join(base_path, relative_path)

def main():

    cleanup_stale_temp_dirs()

    # Видалене з архіву зберігається обмежений час, потім стирається
    try:
        archive.purge_deleted(
            archive.ARCHIVE_DIR, archive.DELETED_RETENTION_DAYS
        )
    except Exception:
        pass    # очистка не повинна заважати запуску

    # Щоб на панелі задач Windows була іконка програми, а не Python
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "ratingprogram.rating.1"
            )
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_theme(app, load_theme_mode())

    # В режиме «Системна» следуем за сменой темы в ОС (Qt 6.5+)
    try:
        app.styleHints().colorSchemeChanged.connect(
            lambda *_: apply_theme(app, load_theme_mode())
            if load_theme_mode() == "system"
            else None
        )
    except AttributeError:
        pass
    
    window = MainWindow()
    window.show()

    sys.exit(app.exec())
    
if __name__ == "__main__":
    main()