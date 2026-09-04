#!/usr/bin/env python3
"""Build a portable DOCX report from a small JSON source using Python stdlib only.

Usage:
    python scripts/build_report.py --input report-source.json --output report.docx
    python scripts/build_report.py --self-test

The generator is a deterministic fallback for platforms without a native document
tool. It supports headings, answer-first key-message paragraphs, bullets, tables,
PNG/JPEG/SVG figures, engineering-figure metadata, figure takeaways, claim limits,
alt text and external source links. A generated file still requires visual
rendering or opening before G5 can be marked complete.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import struct
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr


ROOT = Path(__file__).resolve().parent.parent
EMU_PER_INCH = 914400
PAGE_WIDTH_IN = 6.25
REPORT_SCHEMA_VERSION = "1.1"
MATURITY_LEVELS = {"V0", "V1", "V2", "V3"}
FIGURE_TYPES = {
    "F1-object-structure",
    "F2-problem-failure",
    "F3-system-architecture",
    "F4-mechanism-section",
    "F5-motion-sequence",
    "F6-force-energy-material-path",
    "F7-safety-boundary",
    "F8-process-operation",
    "F9-validation-decision",
}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", newline="\n")


def _text(value: object) -> str:
    return escape(str(value), {'"': "&quot;"})


def _run(text: str, *, bold: bool = False, color: str | None = None, size: int = 22) -> str:
    props: list[str] = [f'<w:sz w:val="{size}"/>', f'<w:szCs w:val="{size}"/>']
    if bold:
        props.append("<w:b/><w:bCs/>")
    if color:
        props.append(f'<w:color w:val="{color}"/>')
    return f"<w:r><w:rPr>{''.join(props)}</w:rPr><w:t xml:space=\"preserve\">{_text(text)}</w:t></w:r>"


def _paragraph(
    text: str,
    *,
    style: str | None = None,
    bold: bool = False,
    color: str | None = None,
    size: int = 22,
    align: str | None = None,
    before: int = 0,
    after: int = 120,
) -> str:
    ppr: list[str] = []
    if style:
        ppr.append(f'<w:pStyle w:val="{style}"/>')
    if align:
        ppr.append(f'<w:jc w:val="{align}"/>')
    ppr.append(f'<w:spacing w:before="{before}" w:after="{after}" w:line="330" w:lineRule="auto"/>')
    return f"<w:p><w:pPr>{''.join(ppr)}</w:pPr>{_run(text, bold=bold, color=color, size=size)}</w:p>"


def _page_break() -> str:
    return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


def _cell(text: object, *, header: bool = False, width: int = 2400) -> str:
    shade = '<w:shd w:fill="D9EEF2"/>' if header else ""
    value = _paragraph(str(text), bold=header, size=19, after=40)
    return (
        f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{shade}'
        '<w:tcMar><w:top w:w="80" w:type="dxa"/><w:left w:w="100" w:type="dxa"/>'
        '<w:bottom w:w="80" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tcMar>'
        f"</w:tcPr>{value}</w:tc>"
    )


def _table(headers: list[object], rows: list[list[object]]) -> str:
    columns = max(1, len(headers))
    width = max(900, 9360 // columns)
    borders = (
        '<w:tblBorders><w:top w:val="single" w:sz="6" w:color="A7B6C2"/>'
        '<w:left w:val="single" w:sz="6" w:color="A7B6C2"/>'
        '<w:bottom w:val="single" w:sz="6" w:color="A7B6C2"/>'
        '<w:right w:val="single" w:sz="6" w:color="A7B6C2"/>'
        '<w:insideH w:val="single" w:sz="4" w:color="C9D3DB"/>'
        '<w:insideV w:val="single" w:sz="4" w:color="C9D3DB"/></w:tblBorders>'
    )
    xml = [f'<w:tbl><w:tblPr><w:tblW w:w="9360" w:type="dxa"/>{borders}</w:tblPr>']
    if headers:
        xml.append('<w:tr><w:trPr><w:tblHeader/></w:trPr>')
        xml.extend(_cell(value, header=True, width=width) for value in headers)
        xml.append("</w:tr>")
    for row in rows:
        values = list(row[:columns]) + [""] * max(0, columns - len(row))
        xml.append("<w:tr>")
        xml.extend(_cell(value, width=width) for value in values)
        xml.append("</w:tr>")
    xml.append("</w:tbl>")
    xml.append(_paragraph("", size=8, after=30))
    return "".join(xml)


def _callout(text: str) -> str:
    """Render one answer-first message as a normal paragraph, not a decorative box."""
    return _paragraph(text, bold=True, size=23, before=80, after=180)


def _image_dimensions(path: Path) -> tuple[float, float]:
    suffix = path.suffix.lower()
    if suffix == ".png":
        raw = path.read_bytes()[:24]
        if raw[:8] == b"\x89PNG\r\n\x1a\n" and len(raw) >= 24:
            width, height = struct.unpack(">II", raw[16:24])
            if width and height:
                return float(width), float(height)
    if suffix == ".svg":
        head = path.read_text(encoding="utf-8", errors="ignore")[:4096]
        match = re.search(r"viewBox\s*=\s*['\"]\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)", head)
        if match:
            return float(match.group(1)), float(match.group(2))
        width = re.search(r"\bwidth\s*=\s*['\"]([\d.]+)", head)
        height = re.search(r"\bheight\s*=\s*['\"]([\d.]+)", head)
        if width and height:
            return float(width.group(1)), float(height.group(1))
    return 1600.0, 900.0


def _figure_xml(rel_id: str, doc_pr_id: int, path: Path, alt: str) -> str:
    width_px, height_px = _image_dimensions(path)
    width_emu = int(PAGE_WIDTH_IN * EMU_PER_INCH)
    height_emu = int(width_emu * height_px / width_px)
    max_height = int(5.8 * EMU_PER_INCH)
    if height_emu > max_height:
        scale = max_height / height_emu
        height_emu = max_height
        width_emu = int(width_emu * scale)
    alt_attr = quoteattr(alt)
    return f"""
<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:before="120" w:after="80"/></w:pPr><w:r><w:drawing>
  <wp:inline distT="0" distB="0" distL="0" distR="0">
    <wp:extent cx="{width_emu}" cy="{height_emu}"/>
    <wp:effectExtent l="0" t="0" r="0" b="0"/>
    <wp:docPr id="{doc_pr_id}" name="Figure {doc_pr_id}" descr={alt_attr}/>
    <wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>
    <a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
      <pic:pic><pic:nvPicPr><pic:cNvPr id="0" name="{_text(path.name)}"/><pic:cNvPicPr/></pic:nvPicPr>
      <pic:blipFill><a:blip r:embed="{rel_id}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
      <pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{width_emu}" cy="{height_emu}"/></a:xfrm>
      <a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>
    </a:graphicData></a:graphic>
  </wp:inline>
</w:drawing></w:r></w:p>
"""


def _resolve_asset(input_path: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() and candidate.is_file():
        return candidate
    for base in [input_path.parent, ROOT]:
        resolved = (base / candidate).resolve()
        if resolved.is_file():
            return resolved
    raise FileNotFoundError(f"figure not found: {value}")


def _styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Aptos" w:eastAsia="Microsoft YaHei" w:hAnsi="Aptos"/><w:sz w:val="22"/><w:szCs w:val="22"/><w:lang w:val="zh-CN" w:eastAsia="zh-CN"/></w:rPr></w:rPrDefault>
  <w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="330" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:jc w:val="center"/><w:spacing w:before="900" w:after="240"/></w:pPr><w:rPr><w:b/><w:color w:val="000000"/><w:sz w:val="48"/><w:szCs w:val="48"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:jc w:val="center"/><w:spacing w:after="300"/></w:pPr><w:rPr><w:color w:val="000000"/><w:sz w:val="28"/><w:szCs w:val="28"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="300" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:color w:val="000000"/><w:sz w:val="32"/><w:szCs w:val="32"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="220" w:after="100"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:color w:val="000000"/><w:sz w:val="26"/><w:szCs w:val="26"/></w:rPr></w:style>
  <w:style w:type="character" w:styleId="Hyperlink"><w:name w:val="Hyperlink"/><w:rPr><w:color w:val="0563C1"/><w:u w:val="single"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="Caption"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:jc w:val="center"/><w:spacing w:after="160"/></w:pPr><w:rPr><w:color w:val="486581"/><w:sz w:val="19"/><w:szCs w:val="19"/></w:rPr></w:style>
</w:styles>"""


def build_report(source_path: Path, output_path: Path) -> dict[str, object]:
    data = json.loads(source_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {REPORT_SCHEMA_VERSION}")
    title = str(data.get("title", "技术方案报告")).strip()
    if not title:
        raise ValueError("title cannot be empty")

    relationships: list[str] = []
    media: list[tuple[str, bytes]] = []
    content_types: dict[str, str] = {}
    rel_counter = 1
    doc_pr_id = 1
    body: list[str] = []

    body.append(_paragraph(title, style="Title", bold=True, size=48, align="center"))
    subtitle = str(data.get("subtitle", "")).strip()
    if subtitle:
        body.append(_paragraph(subtitle, style="Subtitle", size=28, align="center"))
    status = str(data.get("status", "")).strip()
    if status:
        body.append(_paragraph(status, bold=True, color="147D92", size=22, align="center", before=180))
    metadata = data.get("metadata", {})
    if isinstance(metadata, dict):
        for key, value in metadata.items():
            body.append(_paragraph(f"{key}：{value}", size=20, align="center", after=80))
    body.append(_page_break())

    figure_count = 0
    for section in data.get("sections", []):
        if not isinstance(section, dict):
            continue
        heading = str(section.get("title", "")).strip()
        level = int(section.get("level", 1))
        if heading:
            body.append(_paragraph(heading, style="Heading1" if level <= 1 else "Heading2", bold=True, size=32 if level <= 1 else 26))
        for block in section.get("blocks", []):
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if kind == "paragraph":
                body.append(_paragraph(str(block.get("text", ""))))
            elif kind == "key_message":
                message = str(block.get("text", "")).strip()
                if not message:
                    raise ValueError("key_message text cannot be empty")
                body.append(_callout(message))
            elif kind == "page_break":
                body.append(_page_break())
            elif kind == "bullets":
                for item in block.get("items", []):
                    body.append(_paragraph(f"• {item}", after=70))
            elif kind == "table":
                headers = list(block.get("headers", []))
                rows = [list(row) for row in block.get("rows", [])]
                body.append(_table(headers, rows))
            elif kind == "figure":
                path = _resolve_asset(source_path, str(block.get("path", "")))
                suffix = path.suffix.lower().lstrip(".")
                if suffix == "jpg":
                    suffix = "jpeg"
                mime = {"png": "image/png", "jpeg": "image/jpeg", "svg": "image/svg+xml"}.get(suffix)
                if not mime:
                    raise ValueError(f"unsupported figure type: {path.suffix}")
                alt = str(block.get("alt", "")).strip()
                caption = str(block.get("caption", "")).strip()
                figure_id = str(block.get("figure_id", "")).strip()
                figure_type = str(block.get("figure_type", "")).strip()
                design_status = str(block.get("design_status", "")).strip()
                main_message = str(block.get("main_message", "")).strip()
                claim_limit = str(block.get("claim_limit", "")).strip()
                if not alt or not caption or not figure_id:
                    raise ValueError(f"figure requires figure_id, caption and alt text: {path}")
                if figure_type not in FIGURE_TYPES:
                    raise ValueError(f"unsupported figure_type for {figure_id}: {figure_type}")
                if design_status not in MATURITY_LEVELS:
                    raise ValueError(f"design_status must be V0-V3 for {figure_id}")
                if len(main_message) < 8 or len(claim_limit) < 8:
                    raise ValueError(f"figure requires main_message and claim_limit: {figure_id}")
                rel_id = f"rId{rel_counter}"
                rel_counter += 1
                target_name = f"image{len(media) + 1}.{suffix}"
                relationships.append(
                    f'<Relationship Id="{rel_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{target_name}"/>'
                )
                media.append((target_name, path.read_bytes()))
                content_types[suffix] = mime
                body.append(_figure_xml(rel_id, doc_pr_id, path, alt))
                doc_pr_id += 1
                figure_count += 1
                caption_text = caption if design_status in caption else f"{caption}（{design_status} 概念原理图）"
                body.append(_paragraph(caption_text, style="Caption", size=19, align="center", after=70))
                body.append(_paragraph(f"图示要点：{main_message}", bold=True, color="102A43", size=19, after=55))
                body.append(_paragraph(f"证据边界：{claim_limit}", color="627D98", size=18, after=150))

    sources = data.get("sources", [])
    source_count = 0
    if sources:
        body.append(_paragraph("参考来源", style="Heading1", bold=True, size=32))
    for source in sources:
        if not isinstance(source, dict):
            continue
        sid = str(source.get("id", "")).strip()
        name = str(source.get("title", "")).strip()
        claim = str(source.get("claim", "")).strip()
        url = str(source.get("url", "")).strip()
        prefix = " | ".join(value for value in [sid, name, claim] if value)
        if url.startswith(("https://", "http://")):
            rel_id = f"rId{rel_counter}"
            rel_counter += 1
            relationships.append(
                f'<Relationship Id="{rel_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target={quoteattr(url)} TargetMode="External"/>'
            )
            link = (
                f'<w:hyperlink r:id="{rel_id}"><w:r><w:rPr><w:rStyle w:val="Hyperlink"/></w:rPr>'
                f'<w:t>{_text(url)}</w:t></w:r></w:hyperlink>'
            )
            body.append(f'<w:p><w:pPr><w:spacing w:after="100"/></w:pPr>{_run(prefix + " | ", size=19)}{link}</w:p>')
        else:
            body.append(_paragraph(prefix, size=19))
        source_count += 1

    sect = (
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1276" '
        'w:bottom="1134" w:left="1276" w:header="600" w:footer="600" w:gutter="0"/></w:sectPr>'
    )
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
<w:body>{''.join(body)}{sect}</w:body></w:document>"""

    defaults = [
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
    ]
    for ext, mime in sorted(content_types.items()):
        defaults.append(f'<Default Extension="{ext}" ContentType="{mime}"/>')
    content_types_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">{''.join(defaults)}
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""
    package_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""
    document_rels = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
{''.join(relationships)}</Relationships>"""
    created = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    core_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>{_text(title)}</dc:title><dc:creator>TRIZ Worker Innovation Research Skill</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified></cp:coreProperties>"""
    app_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>TRIZ Worker Innovation Research Skill</Application></Properties>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", content_types_xml)
        package.writestr("_rels/.rels", package_rels)
        package.writestr("word/document.xml", document_xml)
        package.writestr("word/styles.xml", _styles_xml())
        package.writestr("word/_rels/document.xml.rels", document_rels)
        package.writestr("docProps/core.xml", core_xml)
        package.writestr("docProps/app.xml", app_xml)
        for name, payload in media:
            package.writestr(f"word/media/{name}", payload)

    return {
        "output": str(output_path),
        "bytes": output_path.stat().st_size,
        "figures": figure_count,
        "figure_metadata_complete": True,
        "sources": source_count,
        "visual_verification_required": True,
    }


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="triz-report-") as tmp:
        root = Path(tmp)
        svg = root / "figure.svg"
        svg.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450"><rect width="800" height="450" fill="#eef6f8"/><text x="80" y="220">作用机理</text></svg>',
            encoding="utf-8",
        )
        source = root / "report.json"
        source.write_text(
            json.dumps(
                {
                    "schema_version": "1.1",
                    "title": "自检技术报告",
                    "status": "V0 概念研究",
                    "sections": [
                        {
                            "title": "1. 摘要",
                            "level": 1,
                            "blocks": [
                                {"type": "paragraph", "text": "自检段落"},
                                {"type": "table", "headers": ["方法", "难点"], "rows": [["受控作用", "降低失效"]]},
                                {
                                    "type": "figure",
                                    "figure_id": "FIG-1-1",
                                    "figure_type": "F4-mechanism-section",
                                    "design_status": "V0",
                                    "path": "figure.svg",
                                    "caption": "图1-1 自检作用机理图",
                                    "alt": "自检对象、工具界面、作用方向和被保护区域。",
                                    "main_message": "受控工具界面把输入作用传递给目标对象。",
                                    "claim_limit": "V0 概念机理，结构与效果尚未验证。"
                                },
                            ],
                        }
                    ],
                    "sources": [{"id": "SRC-01", "title": "自检来源", "url": "https://example.com/source", "claim": "支持自检"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        output = root / "report.docx"
        result = build_report(source, output)
        with zipfile.ZipFile(output) as package:
            assert package.testzip() is None
            names = set(package.namelist())
            assert "word/document.xml" in names
            assert "word/media/image1.svg" in names
            document = package.read("word/document.xml").decode("utf-8")
            rels = package.read("word/_rels/document.xml.rels").decode("utf-8")
            assert "自检对象、工具界面、作用方向和被保护区域" in document
            assert "图示要点" in document and "证据边界" in document
            assert 'TargetMode="External"' in rels
        assert result["figures"] == 1 and result["sources"] == 1 and result["figure_metadata_complete"] is True
    print("REPORT_SELF_TEST_PASS")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="JSON report source")
    parser.add_argument("--output", type=Path, help="output DOCX path")
    parser.add_argument("--self-test", action="store_true", help="run built-in self-test")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    if args.input is None or args.output is None:
        print("error: --input and --output are required", file=sys.stderr)
        return 2
    try:
        result = build_report(args.input.resolve(), args.output.resolve())
    except (OSError, ValueError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
