import os
import zipfile

MACRO_EXTENSIONS = (".xlsm", ".xltm")

# Журнал — обычная таблица; десятки мегабайт уже подозрительно
MAX_FILE_SIZE = 50 * 1024 * 1024            # размер файла на диске
MAX_UNCOMPRESSED_SIZE = 500 * 1024 * 1024   # размер после распаковки
MAX_ARCHIVE_ENTRIES = 5000                  # число файлов внутри архива


class JournalFileError(ValueError):
    """Журнал не прошёл проверку безопасности (текст — для пользователя)."""


def has_macros(file_path):
    """
    True, если журнал может содержать макросы:
    расширение макро-формата или внутри архива есть vbaProject.bin.
    """
    if file_path.lower().endswith(MACRO_EXTENSIONS):
        return True

    try:
        with zipfile.ZipFile(file_path) as archive:
            return any(
                name.lower().endswith("vbaproject.bin")
                for name in archive.namelist()
            )
    except (OSError, zipfile.BadZipFile):
        return False


def check_workbook_file(file_path):
    """
    Проверяет файл до того, как его откроет openpyxl.
    При проблеме бросает JournalFileError с понятным текстом.
    """
    try:
        size = os.path.getsize(file_path)
    except OSError:
        raise JournalFileError("Не вдалося відкрити файл журналу.")

    if size > MAX_FILE_SIZE:
        raise JournalFileError(
            f"Файл журналу завеликий ({size // (1024 * 1024)} МБ). "
            f"Допустимо не більше {MAX_FILE_SIZE // (1024 * 1024)} МБ."
        )

    try:
        with zipfile.ZipFile(file_path) as archive:
            entries = archive.infolist()
            names = {entry.filename for entry in entries}

            if len(entries) > MAX_ARCHIVE_ENTRIES:
                raise JournalFileError(
                    "Файл має підозріло складну структуру "
                    "і не буде оброблений."
                )

            # Розмір після розпакування за заявленими даними архіву
            total = sum(entry.file_size for entry in entries)

            if total > MAX_UNCOMPRESSED_SIZE:
                raise JournalFileError(
                    "Файл займає підозріло багато пам'яті після "
                    "розпакування і не буде оброблений."
                )

            if (
                "[Content_Types].xml" not in names
                or "xl/workbook.xml" not in names
            ):
                raise JournalFileError(
                    "Файл не схожий на книгу Excel (.xlsx)."
                )

    except zipfile.BadZipFile:
        raise JournalFileError(
            "Не вдалося прочитати файл як книгу Excel. "
            "Можливо, він пошкоджений або захищений паролем."
        )