#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    ListFlowable,
    ListItem,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


PAGE_SIZE = A4
MARGIN_X = 18 * mm
MARGIN_TOP = 16 * mm
MARGIN_BOTTOM = 16 * mm
DOC_WIDTH = PAGE_SIZE[0] - 2 * MARGIN_X

FONT_CANDIDATES = [
    (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
]

MONO_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Courier New.ttf",
    "/System/Library/Fonts/Supplemental/Andale Mono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]


def register_fonts() -> None:
    regular_font = None
    for regular, bold in FONT_CANDIDATES:
        regular_path = Path(regular)
        bold_path = Path(bold)
        if regular_path.exists() and bold_path.exists():
            pdfmetrics.registerFont(TTFont("DocSans", str(regular_path)))
            pdfmetrics.registerFont(TTFont("DocSans-Bold", str(bold_path)))
            regular_font = regular_path
            break
    if regular_font is None:
        raise SystemExit("No Cyrillic TrueType font found for PDF generation")

    mono_font = next((Path(path) for path in MONO_FONT_CANDIDATES if Path(path).exists()), regular_font)
    pdfmetrics.registerFont(TTFont("DocMono", str(mono_font)))


def build_styles():
    styles = getSampleStyleSheet()
    base = ParagraphStyle(
        "DocBase",
        parent=styles["BodyText"],
        fontName="DocSans",
        fontSize=9.4,
        leading=12.4,
        spaceAfter=4,
    )
    styles.add(base)
    styles.add(ParagraphStyle("DocTitle", parent=base, fontName="DocSans-Bold", fontSize=18, leading=22, spaceAfter=10))
    styles.add(ParagraphStyle("DocH1", parent=base, fontName="DocSans-Bold", fontSize=15, leading=18, spaceBefore=8, spaceAfter=7))
    styles.add(ParagraphStyle("DocH2", parent=base, fontName="DocSans-Bold", fontSize=12, leading=15, spaceBefore=8, spaceAfter=5))
    styles.add(ParagraphStyle("DocH3", parent=base, fontName="DocSans-Bold", fontSize=10.5, leading=13, spaceBefore=6, spaceAfter=4))
    styles.add(ParagraphStyle("DocCode", parent=base, fontName="DocMono", fontSize=7.5, leading=9, leftIndent=4, rightIndent=4, backColor=colors.HexColor("#f2f2f2")))
    styles.add(ParagraphStyle("DocList", parent=base, leftIndent=8, firstLineIndent=0))
    styles.add(ParagraphStyle("DocCaption", parent=base, fontSize=8.4, leading=10.5, textColor=colors.HexColor("#666666"), alignment=1))
    return styles


def default_title(source: Path) -> str:
    name = source.stem
    prefix = "MK61s-mini-"
    if name.startswith(prefix):
        return "MK61s mini " + name[len(prefix):]
    return name.replace("-", " ")


def inline(text: str) -> str:
    out: list[str] = []
    parts = text.split("`")
    for index, part in enumerate(parts):
        if index % 2:
            font = "Courier" if all(ord(ch) < 128 for ch in part) else "DocSans"
            out.append('<font name="%s">%s</font>' % (font, escape(part)))
        else:
            escaped = escape(part)
            escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
            out.append(escaped)
    return "".join(out)


def make_table(lines: list[str], base_style) -> list:
    rows = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        rows.append([Paragraph(inline(cell), base_style) for cell in cells])
    if not rows:
        return []

    col_count = max(len(row) for row in rows)
    for row in rows:
        while len(row) < col_count:
            row.append(Paragraph("", base_style))

    col_widths = [DOC_WIDTH / col_count] * col_count
    table = Table(rows, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "DocSans"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.4),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b8b8b8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return [table, Spacer(1, 5)]


def flush_paragraph(buffer: list[str], story: list, style) -> None:
    if not buffer:
        return
    story.append(Paragraph(inline(" ".join(buffer)), style))
    buffer.clear()


def flush_list(buffer: list[str], story: list, styles, ordered: bool) -> None:
    if not buffer:
        return
    items = [ListItem(Paragraph(inline(item), styles["DocList"])) for item in buffer]
    story.append(ListFlowable(items, bulletType="1" if ordered else "bullet", start="1" if ordered else "circle", leftIndent=12))
    story.append(Spacer(1, 3))
    buffer.clear()


def add_image(line: str, source_dir: Path, story: list, styles) -> bool:
    match = re.match(r"!\[(.*?)\]\((.*?)\)", line)
    if not match:
        return False
    alt = match.group(1).strip()
    image_path = (source_dir / match.group(2).strip()).resolve()
    if not image_path.exists():
        story.append(Paragraph(inline("[missing image: %s]" % image_path.name), styles["DocBase"]))
        return True

    image = Image(str(image_path))
    if image.drawWidth > DOC_WIDTH:
        scale = DOC_WIDTH / image.drawWidth
        image.drawWidth *= scale
        image.drawHeight *= scale
    story.append(image)
    if alt:
        story.append(Paragraph(inline(alt), styles["DocCaption"]))
    story.append(Spacer(1, 5))
    return True


def build_story(markdown: str, source_dir: Path, styles) -> list:
    story = []
    paragraph: list[str] = []
    bullets: list[str] = []
    ordered: list[str] = []
    code: list[str] = []
    table: list[str] = []
    in_code = False

    def flush_blocks() -> None:
        flush_paragraph(paragraph, story, styles["DocBase"])
        flush_list(bullets, story, styles, False)
        flush_list(ordered, story, styles, True)

    for raw in markdown.splitlines():
        line = raw.rstrip()

        if line.startswith("```"):
            flush_blocks()
            if in_code:
                story.append(Preformatted("\n".join(code), styles["DocCode"], maxLineLength=92))
                story.append(Spacer(1, 5))
                code.clear()
            in_code = not in_code
            continue

        if in_code:
            code.append(line)
            continue

        if line.startswith("|"):
            flush_blocks()
            table.append(line)
            continue
        if table:
            story.extend(make_table(table, styles["DocBase"]))
            table.clear()

        if not line:
            flush_blocks()
            continue

        if add_image(line, source_dir, story, styles):
            flush_blocks()
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            flush_blocks()
            level = len(heading.group(1))
            style_name = "DocTitle" if level == 1 else "DocH1" if level == 2 else "DocH2" if level == 3 else "DocH3"
            story.append(Paragraph(inline(heading.group(2)), styles[style_name]))
            continue

        if line.startswith("- "):
            flush_paragraph(paragraph, story, styles["DocBase"])
            flush_list(ordered, story, styles, True)
            bullets.append(line[2:])
            continue

        numbered = re.match(r"^\d+\.\s+(.*)$", line)
        if numbered:
            flush_paragraph(paragraph, story, styles["DocBase"])
            flush_list(bullets, story, styles, False)
            ordered.append(numbered.group(1))
            continue

        if bullets:
            bullets[-1] += " " + line.strip()
            continue
        if ordered:
            ordered[-1] += " " + line.strip()
            continue

        paragraph.append(line)

    if table:
        story.extend(make_table(table, styles["DocBase"]))
    flush_blocks()
    return story


def footer(title: str):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("DocSans", 8)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(MARGIN_X, 10 * mm, title)
        canvas.drawRightString(PAGE_SIZE[0] - MARGIN_X, 10 * mm, str(doc.page))
        canvas.restoreState()

    return draw


def build_pdf(source: Path, output: Path, title: str) -> None:
    register_fonts()
    styles = build_styles()
    doc = SimpleDocTemplate(
        str(output),
        pagesize=PAGE_SIZE,
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        title=title,
    )
    markdown = source.read_text(encoding="utf-8")
    doc.build(build_story(markdown, source.parent, styles), onFirstPage=footer(title), onLaterPages=footer(title))


def discover_sources(source_dir: Path) -> list[Path]:
    sources = sorted(path for path in source_dir.glob("*.md") if path.is_file())
    if not sources:
        raise SystemExit(f"No Markdown documents found in {source_dir}")
    return sources


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Build one PDF per Markdown document; without arguments, build every doc/src/*.md."
    )
    parser.add_argument("sources", nargs="*", type=Path)
    parser.add_argument("--source-dir", type=Path, default=script_dir / "src")
    parser.add_argument("--output-dir", type=Path, default=script_dir)
    parser.add_argument("-o", "--output", type=Path,
                        help="Exact output path; valid only with one explicit source")
    parser.add_argument("--title", help="PDF title; valid only with one explicit source")
    args = parser.parse_args()

    if (args.output or args.title) and len(args.sources) != 1:
        parser.error("--output and --title require exactly one explicit source")

    sources = [source.resolve() for source in args.sources]
    if not sources:
        sources = discover_sources(args.source_dir.resolve())

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    for source in sources:
        if not source.is_file():
            raise SystemExit(f"Markdown source does not exist: {source}")
        output = args.output.resolve() if args.output else output_dir / f"{source.stem}.pdf"
        title = args.title if args.title else default_title(source)
        temporary = output.with_name(f".{output.name}.tmp")
        build_pdf(source, temporary, title)
        temporary.replace(output)
        print(output)


if __name__ == "__main__":
    main()
