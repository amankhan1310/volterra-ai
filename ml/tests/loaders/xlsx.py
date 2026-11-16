# ruff: noqa: E501  (fixed OOXML namespace and content-type URIs cannot be wrapped)
"""A minimal .xlsx writer for test fixtures (standard library only; generated data only).

Numbers are written as numbers, strings inline, and datetimes as Excel serial numbers with a
date-time number format, so readers (python-calamine) return them as datetimes, like the real
Arbin exports.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date, datetime
from typing import Any
from xml.sax.saxutils import escape

_EPOCH = datetime(1899, 12, 30)


def _col(k: int) -> str:
    name = ""
    k += 1
    while k:
        k, r = divmod(k - 1, 26)
        name = chr(65 + r) + name
    return name


def _cell(ref: str, value: Any) -> str:
    if isinstance(value, datetime | date):
        dt = value if isinstance(value, datetime) else datetime(value.year, value.month, value.day)
        serial = (dt - _EPOCH).total_seconds() / 86400.0
        return f'<c r="{ref}" s="1"><v>{serial!r}</v></c>'
    if isinstance(value, str):
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
    return f'<c r="{ref}"><v>{float(value)!r}</v></c>'


def xlsx_bytes(sheets: list[tuple[str, list[list[Any]]]]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{k + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for k in range(len(sheets))
            )
            + "</Types>",
        )
        z.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        z.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            + "".join(
                f'<sheet name="{escape(name)}" sheetId="{k + 1}" r:id="rId{k + 1}"/>'
                for k, (name, _) in enumerate(sheets)
            )
            + "</sheets></workbook>",
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                f'<Relationship Id="rId{k + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{k + 1}.xml"/>'
                for k in range(len(sheets))
            )
            + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            "</Relationships>",
        )
        z.writestr(
            "xl/styles.xml",
            '<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="1"><font/></fonts><fills count="1"><fill/></fills><borders count="1"><border/></borders>'
            '<cellStyleXfs count="1"><xf/></cellStyleXfs>'
            '<cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="22" applyNumberFormat="1"/></cellXfs>'
            "</styleSheet>",
        )
        for k, (_, rows) in enumerate(sheets):
            body = "".join(
                f'<row r="{r + 1}">'
                + "".join(_cell(f"{_col(c)}{r + 1}", v) for c, v in enumerate(row) if v is not None)
                + "</row>"
                for r, row in enumerate(rows)
            )
            z.writestr(
                f"xl/worksheets/sheet{k + 1}.xml",
                '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f"<sheetData>{body}</sheetData></worksheet>",
            )
    return out.getvalue()
