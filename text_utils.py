import re

# Латинские буквы, которые визуально совпадают с кириллическими.
# Слева латиница, справа кириллица (в том же порядке).
_LAT_TO_CYR = str.maketrans(
    "ABCEHIKMOPTXaceiopx",
    "АВСЕНІКМОРТХасеіорх",
)


def norm(value) -> str:
    """
    Приводит значение из Excel к единому виду для сравнения:
    None -> "", обрезает пробелы, верхний регистр,
    латинские двойники -> кириллица.
    """
    if value is None:
        return ""

    return str(value).strip().upper().translate(_LAT_TO_CYR)

def norm_key(value) -> str:
    """
    Ключ для сравнения названий предметов.

    Помимо norm(): схлопывает любые пробельные символы
    (двойные пробелы, переносы строк, неразрывный пробел) в один пробел.
    """
    return re.sub(r"\s+", " ", norm(value))

# Український алфавіт: і, ї, є, ґ стоять на своїх місцях, а не в кінці,
# як за кодами символів (так сортує звичайне str.lower()).
_UK_ALPHABET = "абвгґдеєжзиіїйклмнопрстуфхцчшщьюя"
_UK_ORDER = {letter: index for index, letter in enumerate(_UK_ALPHABET)}
_APOSTROPHES = "'’ʼ`"


def sort_key(value) -> tuple:
    """
    Ключ для сортування рядків за українським алфавітом без урахування
    регістру й апострофа. Пробіли, цифри та інші символи йдуть
    перед літерами.
    """
    text = "" if value is None else str(value).lower()

    return tuple(
        _UK_ORDER[char] if char in _UK_ORDER else ord(char) - 1_000_000
        for char in text
        if char not in _APOSTROPHES
    )