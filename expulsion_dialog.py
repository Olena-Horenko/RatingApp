import os
from datetime import date

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QWidget,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QDialogButtonBox,
    QListWidget,
    QListWidgetItem,
)

import archive
import expulsion
import recommendation_docx
from text_utils import norm_key, sort_key
from archive_dialog import save_result_to_archive
from archive_view import ArchiveViewDialog
from rating import is_budget_student
from result_views import SortableTable, cell
from workers import FunctionWorker, RatingWorker


def _missing_lines(missing, limit=12):
    lines = []

    for group, sessions in list(missing.items())[:limit]:
        names = ", ".join(
            expulsion.session_label(year, session)
            for year, session in sessions
        )
        lines.append(f"{group}: {names}")

    extra = len(missing) - limit

    if extra > 0:
        lines.append(f"… та ще груп: {extra}")

    return lines


class NameMatchDialog(QDialog):
    """Підтвердження, що схожі ПІБ у різних сесіях — один студент."""

    def __init__(self, suggestions, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Схожі ПІБ")
        self.resize(820, 440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        hint = QLabel(
            "Цих студентів немає в старих сесіях під тим самим ПІБ, але там "
            "є дуже схожий запис. Позначте пари, де це одна й та сама людина: "
            "їхні борги об'єднаються. Решту не позначайте."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._list = QListWidget()
        self._pairs = []

        for item in suggestions:

            row = QListWidgetItem(
                f"{item.group}:  «{item.new_pib}»  ≈  «{item.old_pib}»  "
                f"({', '.join(item.sessions)}; "
                f"збіг {round(item.ratio * 100)}%)"
            )
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            row.setCheckState(Qt.CheckState.Unchecked)

            self._list.addItem(row)
            self._pairs.append((row, item))

        layout.addWidget(self._list, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(
            "Об'єднати позначені"
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            "Скасувати"
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def confirmed(self):
        return [
            item
            for row, item in self._pairs
            if row.checkState() == Qt.CheckState.Checked
        ]


class AliasManageDialog(QDialog):
    """Список об'єднаних ПІБ із можливістю скасувати об'єднання."""

    def __init__(self, overrides, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Об'єднані ПІБ")
        self.resize(720, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        hint = QLabel(
            "Ці пари ПІБ вважаються одним студентом. Позначте пари, "
            "об'єднання яких треба скасувати: після цього записи "
            "рахуватимуться окремо."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._list = QListWidget()
        self._entries = []

        names = overrides.get("alias_names", {})

        for group, items in sorted(overrides["aliases"].items()):

            for alt_key, main_key in sorted(items.items()):

                pair = names.get(group, {}).get(alt_key)

                if not (isinstance(pair, list) and len(pair) == 2):
                    pair = [alt_key, main_key]

                row = QListWidgetItem(
                    f"{group}:  «{pair[0]}»  =  «{pair[1]}»"
                )
                row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                row.setCheckState(Qt.CheckState.Unchecked)

                self._list.addItem(row)
                self._entries.append((row, group, alt_key))

        layout.addWidget(self._list, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(
            "Скасувати об'єднання позначених"
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            "Закрити"
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def confirmed(self):
        """[(група, ключ_варіанта)] позначених пар."""
        return [
            (group, alt_key)
            for row, group, alt_key in self._entries
            if row.checkState() == Qt.CheckState.Checked
        ]


class ExpulsionPage(QWidget):
    """Сторінка «Кандидати на відрахування» всередині головного вікна."""

    back_requested = Signal()

    HEADERS = [
        "Вкл.", "ПІБ", "Група", "Форма", "Борги", "Сесії", "Дисципліни"
    ]

    TOOLTIPS = [
        "Позначка: студент потрапить у список для Word. "
        "Зніміть, щоб виключити його",
        "Прізвище, ім'я, по батькові",
        "Академічна група",
        "Форма навчання (за стовпцем Б/К)",
        "Кількість боргів за всі враховані сесії",
        "Сесій, у яких знайдено студента / очікувалося. "
        "Червоним — студента знайдено не скрізь або є однофамільці",
        "Дисципліни з боргами: оцінка і сесія",
    ]

    def __init__(self, archive_root, parent=None):
        super().__init__(parent)

        self._root = archive_root

        self._busy = False
        self._thread = None
        self._worker = None
        
        # Фонове завдання (розрахунок кандидатів)
        self._task_thread = None
        self._task_worker = None
        self._task_callback = None
        self._task_result = None
        self._task_error = None
        self._task_error_text = None
        
        self._prepared = None    # (результат, помилки) після читання журналу
        self._import_path = ""
        self._suggestions = []
        self._last_export = None   # (рік, сесія, кандидати) останнього розрахунку

        self._excluded = set()     # знятi позначки: (рік, сесія, група, ПІБ)
        self._filling = False      # іде заповнення таблиці

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 14)
        layout.setSpacing(10)

        # ── Шапка: назад + назва сторінки ──
        header = QHBoxLayout()
        header.setSpacing(12)

        self.back_button = QPushButton("< Назад до підрахунку рейтингу")
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.clicked.connect(self.back_requested.emit)

        title = QLabel("Кандидати на відрахування")
        title.setObjectName("Title")

        header.addWidget(self.back_button)
        header.addWidget(title)
        header.addStretch()

        layout.addLayout(header)

        # ── Додавання журналу в архів ──
        import_row = QHBoxLayout()
        import_row.setSpacing(8)

        self.import_button = QPushButton("Додати журнал в архів")
        self.import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_button.clicked.connect(self._choose_journal)

        import_hint = QLabel(
            "Додайте журнал однієї сесії. Усі його групи потраплять в архів."
        )
        import_hint.setObjectName("Hint")
        import_hint.setWordWrap(True)

        self.view_button = QPushButton("Переглянути архів")
        self.view_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.view_button.clicked.connect(self._open_archive_view)

        import_row.addWidget(self.import_button)
        import_row.addWidget(self.view_button)
        import_row.addWidget(import_hint, 1)

        layout.addLayout(import_row)

        # ── Параметри ──
        row = QHBoxLayout()
        row.setSpacing(8)

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

        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(1, 99)
        self.threshold_spin.setValue(5)

        self.calculate_button = QPushButton("Розрахувати")
        self.calculate_button.setProperty("variant", "primary")
        self.calculate_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.calculate_button.clicked.connect(self._calculate)

        row.addWidget(QLabel("До сесії:"))
        row.addWidget(self.year_combo)
        row.addWidget(self.session_combo)
        row.addSpacing(16)
        row.addWidget(QLabel("Мінімум боргів для відрахування:"))
        row.addWidget(self.threshold_spin)
        row.addStretch()
        row.addWidget(self.calculate_button)

        layout.addLayout(row)

        self.summary = QLabel("Оберіть сесію, поріг і натисніть «Розрахувати».")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # ── Таблиця (прокручується разом з діалогом) ──
        self.table = SortableTable(
            self.HEADERS,
            self.TOOLTIPS,
            text_columns=(1, 2, 6),
            stretch_column=6,
        )
        self.table.setVisible(False)
        self.table.itemChanged.connect(self._on_item_changed)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.table)
        layout.addWidget(scroll, 1)

        note = QLabel(
            "Борг - оцінка нижче 60 або порожня клітинка. Враховуються всі "
            "збережені сесії групи від першої до обраної. Студент шукається "
            "за групою та ПІБ; якщо його немає в якійсь сесії, вона "
            "пропускається."
            " Зніміть позначку у стовпці «Вкл.», щоб виключити студента зі списку для Word."
        )
        note.setObjectName("Hint")
        note.setWordWrap(True)
        layout.addWidget(note)

        close_row = QHBoxLayout()

        self.match_button = QPushButton("Схожі ПІБ…")
        self.match_button.clicked.connect(self._open_matches)

        self.reset_button = QPushButton("Скинути «не навчалися»")
        self.reset_button.clicked.connect(self._reset_skipped)

        self.export_button = QPushButton("Зберегти список у Word")
        self.export_button.setProperty("variant", "primary")
        self.export_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_button.clicked.connect(self._export_list)

        self.selection_label = QLabel("")
        self.selection_label.setObjectName("Hint")

        self.alias_button = QPushButton("Об'єднані ПІБ…")
        self.alias_button.clicked.connect(self._open_aliases)

        close_row.addWidget(self.match_button)
        close_row.addWidget(self.alias_button)
        close_row.addWidget(self.reset_button)
        close_row.addStretch()
        close_row.addWidget(self.selection_label)
        close_row.addWidget(self.export_button)

        self._set_suggestions([])
        self._set_export(None, None, [])
        self._refresh_alias_button()

        layout.addLayout(close_row)

    # ──────────────────────────────────────────────
    #  Додавання журналу в архів
    # ──────────────────────────────────────────────
    
    def _set_busy(self, busy):
        self._busy = busy

        for widget in (
            self.back_button,
            self.import_button,
            self.view_button,
            self.calculate_button,
            self.year_combo,
            self.session_combo,
            self.threshold_spin,
            self.export_button,
        ):
            widget.setEnabled(not busy)
            
        self._update_export_state()
        
        self.progress.setVisible(busy)

    def is_busy(self):
        return self._busy

    def _choose_journal(self):

        if self._busy:
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Оберіть журнал сесії",
            "",
            "Excel files (*.xlsx *.xlsm)"
        )

        if file_path:
            self._start_import(file_path)

    def _open_archive_view(self):

        if self._busy:
            return

        dialog = ArchiveViewDialog(self._root, self)
        dialog.exec()

        if dialog.changed:
            # Таблиця кандидатів уже не відповідає архіву
            self._show_empty(
                "Архів змінено. Натисніть «Розрахувати», щоб оновити таблицю."
            )
    
    def _start_import(self, file_path):

        self._import_path = file_path

        self._set_busy(True)
        self.summary.setText(
            f"Читання журналу: {os.path.basename(file_path)}..."
        )

        self._thread = QThread(self)
        self._worker = RatingWorker()
        self._worker.moveToThread(self._thread)

        self._worker.configure("archive_prepare", file_path)

        self._worker.status.connect(self._on_import_status)
        self._worker.archive_prepared.connect(self._on_prepared)
        self._worker.error.connect(self._on_import_error)

        self._thread.started.connect(self._worker.run)

        self._worker.archive_prepared.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)

        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    def _on_import_status(self, text):
        self.summary.setText(text.replace("Статус: ", ""))

    def _on_prepared(self, result, errors):
        # Діалог покажемо після завершення потоку
        self._prepared = (result, errors)

    def _on_import_error(self, message):
        self.summary.setText("Журнал не додано в архів.")
        QMessageBox.critical(self, "Помилка", message)

    def _on_thread_finished(self):

        prepared = self._prepared

        self._prepared = None
        self._worker = None
        self._thread = None

        self._set_busy(False)

        if prepared is not None:
            self._finish_import(*prepared)

    def _finish_import(self, result, errors):

        if errors:
            answer = QMessageBox.question(
                self,
                "Помилки у групах",
                "Не всі групи журналу можна додати в архів:\n\n"
                + "\n".join(errors)
                + "\n\nДодати решту груп?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if answer != QMessageBox.StandardButton.Yes:
                self.summary.setText("Журнал не додано в архів.")
                return

        message = save_result_to_archive(result, self, self._import_path)

        if message is None:
            self.summary.setText("Журнал не додано в архів.")
            return

        # Стара таблиця вже не відповідає архіву
        self.table.setRowCount(0)
        self.table.setVisible(False)

        self.summary.setText(
            message + " Натисніть «Розрахувати», щоб оновити таблицю."
        )

    # ──────────────────────────────────────────────
    #  Розрахунок кандидатів (у фоновому потоці)
    # ──────────────────────────────────────────────

    def _run_in_background(
        self,
        function,
        callback,
        status_text=None,
        error_text=None
    ):
        """
        Виконує function() в окремому потоці, щоб вікно не підвисало.
        Коли потік завершиться, викликається callback(результат).
        error_text — що показати в підсумку, якщо завдання не вдалося.
        """
        self._set_busy(True)

        if status_text:
            self.summary.setText(status_text)

        self._task_callback = callback
        self._task_result = None
        self._task_error = None
        self._task_error_text = error_text

        self._task_thread = QThread(self)
        self._task_worker = FunctionWorker(function)
        self._task_worker.moveToThread(self._task_thread)

        self._task_thread.started.connect(self._task_worker.run)

        self._task_worker.done.connect(self._on_task_done)
        self._task_worker.failed.connect(self._on_task_failed)

        self._task_worker.done.connect(self._task_thread.quit)
        self._task_worker.failed.connect(self._task_thread.quit)

        self._task_thread.finished.connect(self._task_worker.deleteLater)
        self._task_thread.finished.connect(self._on_task_thread_finished)
        self._task_thread.finished.connect(self._task_thread.deleteLater)

        self._task_thread.start()

    def _on_task_done(self, result):
        self._task_result = result

    def _on_task_failed(self, message):
        self._task_error = message

    def _on_task_thread_finished(self):

        callback = self._task_callback
        result = self._task_result
        error = self._task_error
        error_text = self._task_error_text

        self._task_callback = None
        self._task_result = None
        self._task_error = None
        self._task_error_text = None
        self._task_worker = None
        self._task_thread = None

        self._set_busy(False)

        if error is not None:

            if error_text:
                self.summary.setText(error_text)

            QMessageBox.critical(self, "Помилка", error)
            return

        if callback is not None:
            callback(result)

    def _calculate(self):

        if self._busy:
            return

        year = self.year_combo.currentData()
        session = self.session_combo.currentData()
        threshold = self.threshold_spin.value()

        self._run_in_background(
            lambda: expulsion.calculate_debts(
                self._root, year, session, threshold
            ),
            lambda report: self._on_first_report(
                report, year, session, threshold
            ),
            "Розрахунок кандидатів на відрахування...",
            "Розрахунок не виконано."
        )

    def _on_first_report(self, report, year, session, threshold):

        if not report.groups:
            self._show_empty(
                "В архіві немає даних за обрану сесію. "
                "Додайте її кнопкою «Додати журнал в архів»."
            )
            return

        if report.blocked:

            choice = self._ask_missing(report)

            if choice == "cancel":
                self._show_empty(
                    "Розрахунок скасовано: додайте відсутні сесії в архів."
                )
                return

            if choice == "never":
                archive.add_skipped_sessions(
                    self._root,
                    [
                        (group, missing_year, missing_session)
                        for group, sessions in report.missing.items()
                        for missing_year, missing_session in sessions
                    ]
                )

            allow_missing = choice != "never"

            self._run_in_background(
                lambda: expulsion.calculate_debts(
                    self._root, year, session, threshold,
                    allow_missing=allow_missing
                ),
                lambda result: self._finish_calculation(
                    result, year, session, threshold
                ),
                "Розрахунок кандидатів на відрахування...",
                "Розрахунок не виконано."
            )
            return

        self._finish_calculation(report, year, session, threshold)

    def _finish_calculation(self, report, year, session, threshold):

        self._show_report(report, threshold, year, session)
        self._set_export(year, session, report.candidates)

        # Пошук схожих ПІБ теж читає архів: робимо його у фоні
        self._run_in_background(
            lambda: expulsion.find_name_suggestions(
                self._root, year, session
            ),
            self._on_suggestions
        )

    def _on_suggestions(self, suggestions):

        self._set_suggestions(suggestions)

        if suggestions:
            self.summary.setText(
                self.summary.text()
                + f" Можливі збіги ПІБ між сесіями: {len(suggestions)} "
                "(кнопка «Схожі ПІБ»)."
            )

    def _ask_missing(self, report):
        """'once' — без цих сесій цього разу, 'never' — запам'ятати, 'cancel'."""

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Не вистачає сесій")
        box.setText(
            "В архіві немає (або пошкоджено) таких сесій:\n\n"
            + "\n".join(_missing_lines(report.missing))
            + "\n\nЩо робити?\n"
            "• «Продовжити без них» — борги за ці сесії не враховуються "
            "лише цього разу.\n"
            "• «Вони не навчалися» — для цих груп ці сесії більше не "
            "вимагатимуться (позначку можна скинути кнопкою внизу вікна)."
        )

        once = box.addButton(
            "Продовжити без них",
            QMessageBox.ButtonRole.AcceptRole
        )
        never = box.addButton(
            "Вони не навчалися",
            QMessageBox.ButtonRole.ActionRole
        )
        cancel = box.addButton(
            "Скасувати",
            QMessageBox.ButtonRole.RejectRole
        )

        box.setDefaultButton(cancel)
        box.exec()

        clicked = box.clickedButton()

        if clicked is once:
            return "once"

        if clicked is never:
            return "never"

        return "cancel"

    def _show_empty(self, text):
        self.table.setRowCount(0)
        self.table.setVisible(False)
        self.summary.setText(text)
        self._set_suggestions([])
        self._set_export(None, None, [])

    def _set_suggestions(self, suggestions):
        self._suggestions = suggestions

        self.match_button.setEnabled(bool(suggestions))
        self.match_button.setText(
            f"Схожі ПІБ ({len(suggestions)})…"
            if suggestions
            else "Схожі ПІБ…"
        )

    @staticmethod
    def _exclusion_key(year, session, candidate):
        return (
            year,
            session,
            archive.group_key(candidate.group_name),
            norm_key(candidate.pib),
        )

    def _set_export(self, year, session, candidates):
        self._last_export = (
            (year, session, list(candidates)) if candidates else None
        )

        self._update_export_state()

    def _selected_candidates(self):
        """Кандидати з позначкою у таблиці (порядок як у таблиці)."""

        if self._last_export is None:
            return []

        candidates = self._last_export[2]
        selected = []

        for row in range(self.table.rowCount()):

            item = self.table.item(row, 0)

            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue

            index = item.data(Qt.ItemDataRole.UserRole)

            if isinstance(index, int) and 0 <= index < len(candidates):
                selected.append(candidates[index])

        return selected

    def _update_export_state(self):
        """Кнопка Word і лічильник «У список: N з M»."""

        total = len(self._last_export[2]) if self._last_export else 0
        chosen = len(self._selected_candidates()) if total else 0

        self.export_button.setEnabled(not self._busy and chosen > 0)
        self.selection_label.setText(
            f"У список: {chosen} з {total}" if total else ""
        )

    def _on_item_changed(self, item):
        """Користувач змінив позначку: запам'ятовуємо виключення."""

        if self._filling or item.column() != 0 or self._last_export is None:
            return

        index = item.data(Qt.ItemDataRole.UserRole)
        year, session, candidates = self._last_export

        if not isinstance(index, int) or not 0 <= index < len(candidates):
            return

        key = self._exclusion_key(year, session, candidates[index])

        if item.checkState() == Qt.CheckState.Checked:
            self._excluded.discard(key)
        else:
            self._excluded.add(key)

        self._update_export_state()

    def _export_list(self):
        """Зберігає позначених кандидатів у Word за зразком списку."""

        if self._busy or self._last_export is None:
            return

        year, session, all_candidates = self._last_export
        candidates = self._selected_candidates()

        if not candidates:
            QMessageBox.information(
                self,
                "Список порожній",
                "Позначте хоча б одного студента у стовпці «Вкл.»."
            )
            return

        default_name = (
            f"Рекомендовані на відрахування {date.today():%d_%m_%Y}.docx"
        )

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Зберегти список",
            default_name,
            "Word (*.docx)"
        )

        if not file_path:
            return

        if not file_path.lower().endswith(".docx"):
            file_path += ".docx"

        try:
            recommendation_docx.save_recommendation_list(
                file_path, year, session, candidates
            )

        except PermissionError:
            QMessageBox.critical(
                self,
                "Помилка",
                "Не вдалося зберегти файл. Можливо, він відкритий у Word. "
                "Закрийте його та повторіть спробу."
            )
            return

        except OSError as error:
            QMessageBox.critical(
                self,
                "Помилка",
                f"Не вдалося зберегти файл:\n{error}"
            )
            return

        self.summary.setText(
            f"Список збережено: {file_path} "
            f"(студентів: {len(candidates)} з {len(all_candidates)})."
        )

    def _open_matches(self):

        if self._busy or not self._suggestions:
            return

        dialog = NameMatchDialog(self._suggestions, self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        confirmed = dialog.confirmed()

        if not confirmed:
            return

        archive.add_aliases(
            self._root,
            [
                (
                    item.group,
                    item.old_key,
                    item.new_key,
                    item.old_pib,
                    item.new_pib,
                )
                for item in confirmed
            ]
        )

        self._refresh_alias_button()

        # Перераховуємо з урахуванням нових об'єднань
        self._calculate()

    def _reset_skipped(self):

        if self._busy:
            return

        answer = QMessageBox.question(
            self,
            "Скинути позначки?",
            "Усі позначки «вони не навчалися» буде знято: відсутні сесії "
            "знову вимагатимуться при розрахунку.\n\nПродовжити?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if answer == QMessageBox.StandardButton.Yes:
            archive.clear_skipped_sessions(self._root)
            self.summary.setText("Позначки «не навчалися» скинуто.")

    def _refresh_alias_button(self):
        overrides = archive.load_overrides(self._root)
        count = sum(len(items) for items in overrides["aliases"].values())

        self.alias_button.setEnabled(count > 0)
        self.alias_button.setText(
            f"Об'єднані ПІБ ({count})…" if count else "Об'єднані ПІБ…"
        )

    def _open_aliases(self):

        if self._busy:
            return

        dialog = AliasManageDialog(
            archive.load_overrides(self._root), self
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        chosen = dialog.confirmed()

        if not chosen:
            return

        archive.remove_aliases(self._root, chosen)
        self._refresh_alias_button()

        self._show_empty(
            f"Скасовано об'єднань: {len(chosen)}. "
            "Натисніть «Розрахувати», щоб оновити таблицю."
        )

    def _show_report(self, report, threshold, year, session):

        text = (
            f"Перевірено студентів: {report.students_checked}. "
            f"З боргами ≥ {threshold}: {len(report.candidates)}."
        )

        if report.missing:
            text += f" Груп з пропущеними сесіями: {len(report.missing)}."

        if report.skipped:
            text += " Пропущено групи: " + "; ".join(
                f"{group} ({reason})" for group, reason in report.skipped
            ) + "."

        self.summary.setText(text)

        if not report.candidates:
            self.table.setRowCount(0)
            self.table.setVisible(False)
            return

        rows = []
        row_data = []
        checks = []

        for index, item in enumerate(report.candidates):

            debts_text = "; ".join(
                f"{debt.subject} — {debt.mark} [{debt.session_label}]"
                for debt in item.debts
            )

            incomplete = (
                item.sessions_found < item.sessions_expected
                or item.ambiguous
            )

            form = "Бюджет" if is_budget_student(item) else "Контракт"

            rows.append([
                cell("", 0),
                cell(item.pib, sort_key (item.pib)),
                cell(item.group_name, item.group_name),
                cell(form, form),
                cell(str(item.debts_count), item.debts_count, True),
                cell(
                    f"{item.sessions_found}/{item.sessions_expected}",
                    item.sessions_found - item.sessions_expected,
                    incomplete
                ),
                cell(debts_text, debts_text.lower()),
            ])

            # Індекс кандидата лежить у рядку таблиці й переживає сортування
            row_data.append(index)
            checks.append(
                self._exclusion_key(year, session, item)
                not in self._excluded
            )

        # Під час заповнення таблиці позначки не обробляємо
        self._filling = True

        try:
            self.table.fill(
                rows, 4, Qt.SortOrder.DescendingOrder, row_data, checks
            )
        finally:
            self._filling = False

        self.table.setVisible(True)