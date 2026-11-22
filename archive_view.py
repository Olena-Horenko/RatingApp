from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

import archive
from result_views import SortableTable, cell


def elided_label(text, width, object_name="Hint"):
    """Мітка, яка скорочує довгий текст посередині; повний — у підказці."""
    label = QLabel()
    label.setObjectName(object_name)
    label.setToolTip(text)
    label.setText(
        label.fontMetrics().elidedText(
            text, Qt.TextElideMode.ElideMiddle, width
        )
    )
    return label


def _newest_first(sessions):
    return sorted(
        sessions,
        key=lambda item: (item[0], archive.SESSIONS.index(item[1])),
        reverse=True
    )


class ArchiveDeleteDialog(QDialog):
    """Вибір сесій і груп, які треба видалити з архіву."""

    def __init__(self, sessions, settings, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Видалити з архіву")
        self.resize(560, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        hint = QLabel(
            "Позначте сесію цілком або окремі групи. Файли не стираються "
            "одразу: вони переносяться в папку «_deleted» всередині архіву "
            f"і зберігаються {archive.DELETED_RETENTION_DAYS} днів, "
            "після чого стираються автоматично. Протягом цього часу їх "
            "можна повернути вручну."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)

        for year, session, groups in _newest_first(sessions):

            title = (
                f"{archive.academic_year_label(year)} "
                f"{archive.SESSION_LABELS[session].lower()}  "
                f"({len(groups)})"
            )

            session_item = QTreeWidgetItem([title])
            session_item.setFlags(
                session_item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsAutoTristate
            )
            session_item.setCheckState(0, Qt.CheckState.Unchecked)

            self._tree.addTopLevelItem(session_item)

            for group in groups:

                child = QTreeWidgetItem(
                    [archive.group_label(group, year, settings)]
                )
                child.setFlags(
                    child.flags() | Qt.ItemFlag.ItemIsUserCheckable
                )
                child.setCheckState(0, Qt.CheckState.Unchecked)
                child.setData(
                    0, Qt.ItemDataRole.UserRole, (year, session, group)
                )

                session_item.addChild(child)

        self._tree.expandAll()
        layout.addWidget(self._tree, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(
            "Видалити позначені"
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            "Скасувати"
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected(self):
        """[(рік, сесія, група)] позначених груп."""
        result = []

        for top in range(self._tree.topLevelItemCount()):

            session_item = self._tree.topLevelItem(top)

            for index in range(session_item.childCount()):

                child = session_item.child(index)

                if child.checkState(0) == Qt.CheckState.Checked:
                    result.append(
                        child.data(0, Qt.ItemDataRole.UserRole)
                    )

        return result

    def accept(self):

        items = self.selected()

        if not items:
            QMessageBox.information(
                self,
                "Нічого не позначено",
                "Позначте хоча б одну сесію або групу."
            )
            return

        answer = QMessageBox.question(
            self,
            "Видалити з архіву?",
            f"З архіву буде видалено груп: {len(items)}.\n\n"
            "Файли буде перенесено в папку «_deleted» всередині архіву "
            f"на {archive.DELETED_RETENTION_DAYS} днів. Борги за ці сесії "
            "перестануть враховуватись при розрахунку кандидатів на "
            "відрахування.\n\nПродовжити?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if answer == QMessageBox.StandardButton.Yes:
            super().accept()


class ArchiveViewDialog(QDialog):
    """Які сесії та групи вже є в архіві (з можливістю видалення)."""

    HEADERS = ["Навчальний рік", "Сесія", "Груп", "Групи"]

    TOOLTIPS = [
        "Навчальний рік, до якого належить сесія",
        "Зимова або літня сесія",
        "Кількість груп у цій сесії",
        "Групи сесії. Для магістрів вказано рік вступу на магістратуру",
    ]

    def __init__(self, archive_root, parent=None):
        super().__init__(parent)

        self._root = archive_root
        self._sessions = []
        self._settings = {}

        # Чи щось видалено: сторінка відрахувань після цього очищає таблицю
        self.changed = False

        self.setWindowTitle("Архів сесій")
        self.resize(820, 480)
        self.setMinimumSize(620, 340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        layout.addWidget(
            elided_label(f"Папка архіву: {archive_root}", 760)
        )

        # Вміст (таблиця або повідомлення) перебудовується після видалення
        self._body = QVBoxLayout()
        self._body.setSpacing(10)
        layout.addLayout(self._body, 1)

        button_row = QHBoxLayout()

        self.delete_button = QPushButton("Видалити")
        self.delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_button.clicked.connect(self._delete)

        self.purge_button = QPushButton("Очистити видалене")
        self.purge_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.purge_button.setToolTip(
            "Остаточно стерти все з папки «_deleted». "
            f"Інакше вона очищається сама через "
            f"{archive.DELETED_RETENTION_DAYS} днів."
        )
        self.purge_button.clicked.connect(self._purge)

        close_button = QPushButton("Закрити")
        close_button.clicked.connect(self.accept)

        button_row.addWidget(self.delete_button)
        button_row.addWidget(self.purge_button)
        button_row.addStretch()
        button_row.addWidget(close_button)

        layout.addLayout(button_row)

        self._reload()

    def _clear_body(self):
        while self._body.count():

            item = self._body.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

    def _refresh_purge_button(self):
        count = archive.deleted_count(self._root)

        self.purge_button.setEnabled(count > 0)
        self.purge_button.setText(
            f"Очистити видалене ({count})"
            if count
            else "Очистити видалене"
        )

    def _reload(self):

        self._clear_body()

        self._sessions = archive.list_archive(self._root)
        self._settings = archive.load_group_settings(self._root)

        self.delete_button.setEnabled(bool(self._sessions))
        self._refresh_purge_button()

        if not self._sessions:
            empty = QLabel(
                "Архів порожній. Додайте журнал кнопкою "
                "«Додати журнал в архів»."
            )
            empty.setWordWrap(True)

            self._body.addWidget(empty)
            self._body.addStretch()
            return

        self._body.addWidget(
            self._build_table(self._sessions, self._settings), 1
        )

        note = QLabel(
            "Клацніть на заголовок стовпця, щоб змінити сортування. "
            "Повний список груп видно в підказці, якщо він не вміщується. "
            f"Видалене зберігається {archive.DELETED_RETENTION_DAYS} днів "
            "у папці «_deleted», потім стирається автоматично."
        )
        note.setObjectName("Hint")
        note.setWordWrap(True)

        self._body.addWidget(note)

    def _delete(self):

        dialog = ArchiveDeleteDialog(self._sessions, self._settings, self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        moved, failed = archive.delete_sessions(
            self._root, dialog.selected()
        )

        if moved:
            self.changed = True

        self._reload()

        if failed:
            QMessageBox.warning(
                self,
                "Не все видалено",
                "Не вдалося видалити:\n\n"
                + "\n".join(failed[:15])
                + ("\n…" if len(failed) > 15 else "")
                + "\n\nМожливо, файл відкритий в іншій програмі."
            )

    def _purge(self):

        count = archive.deleted_count(self._root)

        if count == 0:
            return

        answer = QMessageBox.question(
            self,
            "Очистити видалене?",
            f"З папки «_deleted» буде остаточно стерто груп: {count}.\n\n"
            "Відновити їх після цього буде неможливо.\n\nПродовжити?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        archive.purge_deleted(self._root)

        remaining = archive.deleted_count(self._root)
        self._refresh_purge_button()

        if remaining:
            QMessageBox.warning(
                self,
                "Не все стерто",
                f"Не вдалося стерти груп: {remaining}. "
                "Можливо, файли відкриті в іншій програмі."
            )

    def _build_table(self, sessions, settings):

        table = SortableTable(
            self.HEADERS,
            self.TOOLTIPS,
            text_columns=(0, 3),
            stretch_column=3,
        )

        rows = []

        for year, session, groups in sessions:

            labels = ", ".join(
                archive.group_label(group, year, settings)
                for group in groups
            )

            # Пізніша сесія має більше значення: літня за зимову того ж року
            order = year * 2 + archive.SESSIONS.index(session)

            rows.append([
                cell(archive.academic_year_label(year), order),
                cell(archive.SESSION_LABELS[session], order),
                cell(str(len(groups)), len(groups)),
                cell(labels, labels.lower()),
            ])

        table.fill(rows, 0, Qt.SortOrder.DescendingOrder)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(table)

        return scroll