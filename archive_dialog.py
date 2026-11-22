from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import archive
from archive_view import elided_label
import os

def _centered(widget):
    """Центрує віджет усередині клітинки таблиці."""
    holder = QWidget()

    layout = QHBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(widget)

    return holder


class ArchiveDialog(QDialog):
    """Вибір навчального року, сесії та позначок «магістр» перед записом в архів."""

    COL_GROUP = 0
    COL_MASTER = 1
    COL_YEAR = 2
    COL_STATUS = 3

    ROW_HEIGHT = 34

    def __init__(
        self,
        group_names,
        settings,
        archive_root,
        parent=None,
        source_file=""
    ):
        super().__init__(parent)

        self.setWindowTitle("Додати сесію в архів")
        self.setMinimumWidth(660)

        self._groups = list(group_names)
        self._archive_root = archive_root
        self._checks = {}
        self._spins = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        if source_file:
            layout.addWidget(
                elided_label(
                    f"Журнал: {os.path.basename(source_file)}",
                    620,
                    "SectionTitle"
                )
            )
            layout.addWidget(
                elided_label(
                    os.path.dirname(os.path.abspath(source_file)),
                    620
                )
            )
        
        # ── Навчальний рік і сесія ──
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        current_year = archive.default_academic_year()
        default_year, default_session = archive.latest_session()

        self.year_combo = QComboBox()

        for year in archive.session_years():
            self.year_combo.addItem(archive.academic_year_label(year), year)

        self.year_combo.setCurrentIndex(self.year_combo.findData(default_year))

        self.session_combo = QComboBox()

        for code in archive.SESSIONS:
            self.session_combo.addItem(archive.SESSION_LABELS[code], code)

        self.session_combo.setCurrentIndex(
            self.session_combo.findData(default_session)
        )

        # Підказка за назвою файлу (користувач може змінити)
        guess_parts = []

        if source_file:

            guess_year, guess_session = archive.guess_from_filename(
                source_file
            )

            if guess_year is not None:
                index = self.year_combo.findData(guess_year)

                if index >= 0:
                    self.year_combo.setCurrentIndex(index)
                    guess_parts.append(
                        archive.academic_year_label(guess_year)
                    )

            if guess_session is not None:
                self.session_combo.setCurrentIndex(
                    self.session_combo.findData(guess_session)
                )
                guess_parts.append(
                    archive.SESSION_LABELS[guess_session].lower()
                )

        top_row.addWidget(QLabel("Навчальний рік:"))
        top_row.addWidget(self.year_combo)
        top_row.addSpacing(16)
        top_row.addWidget(QLabel("Сесія:"))
        top_row.addWidget(self.session_combo)
        top_row.addStretch()

        layout.addLayout(top_row)

        if guess_parts:
            guess_label = QLabel(
                "Підібрано за назвою файлу: "
                + ", ".join(guess_parts)
                + ". Перевірте та за потреби виправте."
            )
            guess_label.setObjectName("Hint")
            guess_label.setWordWrap(True)
            layout.addWidget(guess_label)

        hint = QLabel(
            "Для груп магістрів поставте позначку й вкажіть рік вступу на "
            "магістратуру: бакалаврські сесії таких груп не враховуватимуться "
            "при підрахунку боргів."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ── Таблиця груп ──
        self.table = QTableWidget(len(self._groups), 4)
        self.table.setHorizontalHeaderLabels([
            "Група", "Магістр", "Рік вступу до магістратури", "Статус"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(self.ROW_HEIGHT)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setShowGrid(False)
        self.table.setMinimumHeight(
            min(len(self._groups), 10) * self.ROW_HEIGHT + 40
        )

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(
            self.COL_STATUS,
            QHeaderView.ResizeMode.Stretch
        )

        for row, group in enumerate(self._groups):

            info = settings.get(archive.group_key(group), {})

            self.table.setItem(row, self.COL_GROUP, QTableWidgetItem(group))

            check = QCheckBox()
            check.setChecked(bool(info.get("master")))

            spin = QSpinBox()
            spin.setRange(
                archive.min_admission_year(),
                archive.max_admission_year()
            )
            spin.setFixedWidth(90)
            spin.setValue(
                info.get("master_year")
                or archive.suggest_master_year(group)
                or current_year
            )
            spin.setEnabled(check.isChecked())

            # Рік можна змінювати, лише коли стоїть позначка «Магістр»
            check.toggled.connect(spin.setEnabled)

            self.table.setCellWidget(row, self.COL_MASTER, _centered(check))
            self.table.setCellWidget(row, self.COL_YEAR, _centered(spin))
            self.table.setItem(row, self.COL_STATUS, QTableWidgetItem(""))

            self._checks[group] = check
            self._spins[group] = spin

        layout.addWidget(self.table)

        # ── Кнопки ──
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Зберегти")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Скасувати")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh_status()

        self.year_combo.currentIndexChanged.connect(self._refresh_status)
        self.session_combo.currentIndexChanged.connect(self._refresh_status)

    def _existing(self):
        return archive.existing_groups(
            self._archive_root,
            self.year_combo.currentData(),
            self.session_combo.currentData(),
            self._groups
        )

    def _refresh_status(self):
        """Показує, які групи вже є в архіві за обрані рік і сесію."""
        existing = set(self._existing())

        for row, group in enumerate(self._groups):
            self.table.item(row, self.COL_STATUS).setText(
                "вже є в архіві — буде замінено"
                if group in existing
                else "нова"
            )

    def accept(self):
        existing = self._existing()

        if existing:
            answer = QMessageBox.question(
                self,
                "Замінити дані?",
                "За цю сесію в архіві вже є дані для груп:\n\n"
                + "\n".join(existing)
                + "\n\nЗамінити їх? Якщо ви помилилися з роком чи сесією, "
                "натисніть «No» і виправте їх.",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if answer != QMessageBox.StandardButton.Yes:
                return

        super().accept()

    def result_values(self):
        """Повертає (рік початку навч. року, сесія, налаштування груп)."""
        settings = {}

        for group in self._groups:

            master = self._checks[group].isChecked()

            settings[archive.group_key(group)] = {
                "master": master,
                "master_year": self._spins[group].value() if master else None,
            }

        return (
            self.year_combo.currentData(),
            self.session_combo.currentData(),
            settings
        )

def save_result_to_archive(result, parent, source_file=""):
    """
    Показує вікно «рік + сесія + магістри» і записує результат в архів.
    Повертає текст для статусу або None, якщо збереження не відбулося.
    """
    root = archive.ARCHIVE_DIR

    dialog = ArchiveDialog(
        result.group_names,
        archive.load_group_settings(root),
        root,
        parent,
        source_file
    )

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None

    year, session, new_settings = dialog.result_values()

    try:
        saved = archive.save_session(root, year, session, result)

        # Підхоплюємо групи, які вже є в налаштуваннях
        settings = archive.load_group_settings(root)
        settings.update(new_settings)
        archive.save_group_settings(root, settings)

    except OSError as error:
        QMessageBox.critical(
            parent,
            "Помилка",
            f"Не вдалося записати архів:\n{error}"
        )
        return None

    return (
        f"Сесію додано в архів "
        f"({archive.academic_year_label(year)}, "
        f"{archive.SESSION_LABELS[session].lower()}). "
        f"Груп: {len(saved)}."
    )