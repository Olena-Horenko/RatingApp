"""
Список студентів, рекомендованих на відрахування (Word, .docx).

Оформлення повторює зразок деканату: заголовок з двох рядків,
таблиця «ПІБ / Бюджет-контракт / Група», комірка групи об'єднана
по рядках студентів цієї групи.

Лише стандартна бібліотека (zipfile), додаткових пакетів не потрібно.
Чиста логіка без Qt.
"""

import re
import zipfile
from xml.sax.saxutils import escape

import archive
from rating import is_budget_student
from text_utils import sort_key

SESSION_GENITIVE = {"winter": "Зимової", "summer": "Літньої"}

# Ширини колонок (twips): ПІБ, форма, кількість боргів, група
COLUMN_WIDTHS = (4106, 1241, 1400, 1089)

FONT = (
    '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" '
    'w:cs="Times New Roman"/>'
)


def _group_sort_key(group_name):
    """Спеціальність за алфавітом, усередині неї старші номери першими."""
    key = archive.group_key(group_name)
    match = re.fullmatch(r"(.+)-(\d+)", key)

    if match is None:
        return (key, 0)

    return (match.group(1), -int(match.group(2)))


def build_title_lines(start_year, session):
    return [
        "Список студентів, рекомендованих на відрахування за результатами",
        f"{SESSION_GENITIVE[session]} сесії "
        f"{start_year}-{start_year + 1}н.р.",
    ]


def group_candidates(candidates):
    """
    [(назва групи, [студенти])] у порядку для документа:
    групи за спеціальністю й номером, студенти за алфавітом.
    """
    by_group = {}

    for item in candidates:
        by_group.setdefault(item.group_name, []).append(item)

    return [
        (
            group,
            sorted(by_group[group], key=lambda item: sort_key(item.pib))
        )
        for group in sorted(by_group, key=_group_sort_key)
    ]


# ──────────────────────────────────────────────
#  XML
# ──────────────────────────────────────────────

def _run(text, size, bold=False):
    return (
        "<w:r><w:rPr>"
        f"{FONT}{'<w:b/>' if bold else ''}"
        f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
        '<w:lang w:val="uk-UA"/></w:rPr>'
        f'<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'
    )


def _paragraph(texts, size, center=False, bold=False, after_zero=True):
    """texts — список рядків: кожен стає окремим абзацом комірки."""
    spacing = (
        '<w:spacing w:after="0" w:line="360" w:lineRule="auto"/>'
        if after_zero
        else '<w:spacing w:line="360" w:lineRule="auto"/>'
    )

    alignment = '<w:jc w:val="center"/>' if center else ""

    result = []

    for text in texts:
        result.append(
            "<w:p><w:pPr>"
            f"{spacing}"
            f"{alignment}"
            "</w:pPr>"
            f"{_run(text, size, bold) if text else ''}"
            "</w:p>"
        )

    return "".join(result)


def _cell(width, content, merge=None):
    """merge: None, 'restart' або 'continue' (вертикальне об'єднання)."""
    merge_xml = {
        None: "",
        "restart": '<w:vMerge w:val="restart"/>',
        "continue": "<w:vMerge/>",
    }[merge]

    return (
        "<w:tc><w:tcPr>"
        f'<w:tcW w:w="{width}" w:type="dxa"/>'
        f"{merge_xml}"
        '<w:vAlign w:val="center"/>'
        f"</w:tcPr>{content}</w:tc>"
    )


def _row(cells):
    return (
        '<w:tr><w:trPr><w:cantSplit/><w:jc w:val="center"/></w:trPr>'
        f'{"".join(cells)}</w:tr>'
    )


def _header_row():
    widths = COLUMN_WIDTHS

    return (
        "<w:tr><w:trPr><w:cantSplit/><w:tblHeader/>"
        '<w:jc w:val="center"/></w:trPr>'
        + _cell(widths[0], _paragraph(["ПІБ"], 24, True, True, False))
        + _cell(
            widths[1],
            _paragraph(["Бюджет", "контракт"], 24, True, True, False)
        )
        + _cell(
            widths[2],
            _paragraph(["Кількість", "боргів"], 24, True, True, False)
        )
        + _cell(widths[3], _paragraph(["Група"], 24, True, True, False))
        + "</w:tr>"
    )


def _body_rows(grouped):
    widths = COLUMN_WIDTHS
    rows = []

    for group, students in grouped:

        for index, student in enumerate(students):

            form = "б" if is_budget_student(student) else "к"

            if index == 0:
                group_cell = _cell(
                    widths[3],
                    _paragraph([group], 24, True, False, False),
                    "restart" if len(students) > 1 else None
                )
            else:
                group_cell = _cell(
                    widths[3],
                    _paragraph([""], 24, True, False, False),
                    "continue"
                )

            rows.append(_row([
                _cell(
                    widths[0],
                    _paragraph([student.pib], 24, False, False, False)
                ),
                _cell(
                    widths[1],
                    _paragraph([form], 24, True, False, False)
                ),
                _cell(
                    widths[2],
                    _paragraph(
                        [str(student.debts_count)], 24, True, False, False
                    )
                ),
                group_cell,
            ]))
            
    return "".join(rows)


_BORDERS = "".join(
    f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
    for side in ("top", "left", "bottom", "right", "insideH", "insideV")
)


def build_document_xml(start_year, session, candidates):

    title = "".join(
        _paragraph([line], 28)
        for line in build_title_lines(start_year, session)
    )

    spacer = _paragraph([""], 24)

    table = (
        "<w:tbl><w:tblPr>"
        '<w:tblW w:w="0" w:type="auto"/><w:jc w:val="center"/>'
        f"<w:tblBorders>{_BORDERS}</w:tblBorders>"
        '<w:tblLayout w:type="fixed"/>'
        "</w:tblPr><w:tblGrid>"
        + "".join(f'<w:gridCol w:w="{width}"/>' for width in COLUMN_WIDTHS)
        + "</w:tblGrid>"
        + _header_row()
        + _body_rows(group_candidates(candidates))
        + "</w:tbl>"
    )

    section = (
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="850" w:bottom="1134" '
        'w:left="1701" w:header="708" w:footer="708" w:gutter="0"/>'
        "</w:sectPr>"
    )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main">'
        f"<w:body>{title}{spacer}{table}"
        # Після таблиці Word вимагає абзац
        f"{_paragraph([''], 24)}{section}</w:body></w:document>"
    )


STYLES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:styles xmlns:w="http://schemas.openxmlformats.org/'
    'wordprocessingml/2006/main"><w:docDefaults><w:rPrDefault><w:rPr>'
    f"{FONT}"
    '<w:sz w:val="24"/><w:szCs w:val="24"/>'
    '<w:lang w:val="uk-UA" w:eastAsia="uk-UA" w:bidi="ar-SA"/>'
    "</w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>"
    '<w:spacing w:after="0" w:line="240" w:lineRule="auto"/>'
    "</w:pPr></w:pPrDefault></w:docDefaults>"
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
    '<w:name w:val="Normal"/><w:qFormat/></w:style></w:styles>'
)

CONTENT_TYPES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
    'content-types">'
    '<Default Extension="rels" ContentType="application/vnd.'
    'openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.'
    'openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/vnd.'
    'openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    "</Types>"
)

ROOT_RELS_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
    '2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
    'openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/></Relationships>'
)

DOCUMENT_RELS_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
    '2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
    'openxmlformats.org/officeDocument/2006/relationships/styles" '
    'Target="styles.xml"/></Relationships>'
)


def save_recommendation_list(file_path, start_year, session, candidates):
    """Записує .docx зі списком кандидатів на відрахування."""

    with zipfile.ZipFile(file_path, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
        package.writestr("_rels/.rels", ROOT_RELS_XML)
        package.writestr(
            "word/document.xml",
            build_document_xml(start_year, session, candidates)
        )
        package.writestr("word/_rels/document.xml.rels", DOCUMENT_RELS_XML)
        package.writestr("word/styles.xml", STYLES_XML)