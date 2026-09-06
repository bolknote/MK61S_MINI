#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import unicodedata
from html import escape, unescape
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
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
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ),
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
    styles.add(ParagraphStyle("DocTitle", parent=base, fontName="DocSans-Bold", fontSize=18, leading=22, spaceAfter=10, keepWithNext=1))
    styles.add(ParagraphStyle("DocH1", parent=base, fontName="DocSans-Bold", fontSize=15, leading=18, spaceBefore=8, spaceAfter=7, keepWithNext=1))
    styles.add(ParagraphStyle("DocH2", parent=base, fontName="DocSans-Bold", fontSize=12, leading=15, spaceBefore=8, spaceAfter=5, keepWithNext=1))
    styles.add(ParagraphStyle("DocH3", parent=base, fontName="DocSans-Bold", fontSize=10.5, leading=13, spaceBefore=6, spaceAfter=4, keepWithNext=1))
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


def heading_anchor(text: str) -> str:
    # Match the heading fragments used by GitHub, including Cyrillic titles.
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text).lower()
    return "".join(
        char for char in text
        if char in "-_ " or unicodedata.category(char)[0] in "LN"
    ).replace(" ", "-")


def inline(text: str, resolve_link=None) -> str:
    # Protect inline-code spans before parsing links.  Splitting on backticks
    # first loses links such as [`guide.md`](guide.md), because the link then
    # spans three independently processed fragments.
    code_spans: list[str] = []

    def stash_code(match: re.Match[str]) -> str:
        marker = f"MK61CODEPLACEHOLDER{len(code_spans)}END"
        value = match.group(1)
        font = "Courier" if all(ord(ch) < 128 for ch in value) else "DocSans"
        code_spans.append('<font name="%s">%s</font>' % (font, escape(value)))
        return marker

    protected = re.sub(r"`([^`]*)`", stash_code, text)
    rendered = escape(protected)
    rendered = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda match: '<link href="%s" color="#1a5fb4">%s</link>' % (
            escape(resolve_link(unescape(match.group(2))), quote=True)
            if resolve_link else match.group(2), match.group(1),
        ),
        rendered,
    )
    rendered = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", rendered)
    for index, code_span in enumerate(code_spans):
        rendered = rendered.replace(f"MK61CODEPLACEHOLDER{index}END", code_span)
    return rendered


def make_table(lines: list[str], base_style, render_inline=inline) -> list:
    rows = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        rows.append([Paragraph(render_inline(cell), base_style) for cell in cells])
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


def flush_paragraph(buffer: list[str], story: list, style, render_inline=inline) -> None:
    if not buffer:
        return
    story.append(Paragraph(render_inline(" ".join(buffer)), style))
    buffer.clear()


def flush_list(buffer: list[str], story: list, styles, ordered: bool, render_inline=inline) -> None:
    if not buffer:
        return
    items = [ListItem(Paragraph(render_inline(item), styles["DocList"])) for item in buffer]
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
    block = [image]
    if alt:
        block.append(Paragraph(inline(alt), styles["DocCaption"]))
    block.append(Spacer(1, 5))
    story.append(KeepTogether(block))
    return True


def build_story(markdown: str, source_dir: Path, styles, render_inline=inline) -> list:
    story = []
    paragraph: list[str] = []
    bullets: list[str] = []
    ordered: list[str] = []
    code: list[str] = []
    table: list[str] = []
    in_code = False
    anchors: set[str] = set()

    def flush_blocks() -> None:
        flush_paragraph(paragraph, story, styles["DocBase"], render_inline)
        flush_list(bullets, story, styles, False, render_inline)
        flush_list(ordered, story, styles, True, render_inline)

    for raw in markdown.splitlines():
        line = raw.rstrip()

        if line.startswith("```"):
            flush_blocks()
            if in_code:
                # Keep a short example on one page; oversized listings may split.
                story.append(KeepTogether([
                    Preformatted("\n".join(code), styles["DocCode"], maxLineLength=92),
                    Spacer(1, 5),
                ]))
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
            story.extend(make_table(table, styles["DocBase"], render_inline))
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
            title = heading.group(2)
            base_anchor = heading_anchor(title)
            anchor = base_anchor
            suffix = 1
            while anchor in anchors:
                anchor = f"{base_anchor}-{suffix}"
                suffix += 1
            anchors.add(anchor)
            story.append(Paragraph(
                f'<a name="{escape(anchor, quote=True)}"/>' + render_inline(title),
                styles[style_name],
            ))
            continue

        if line.startswith("- "):
            flush_paragraph(paragraph, story, styles["DocBase"], render_inline)
            flush_list(ordered, story, styles, True, render_inline)
            bullets.append(line[2:])
            continue

        numbered = re.match(r"^\d+\.\s+(.*)$", line)
        if numbered:
            flush_paragraph(paragraph, story, styles["DocBase"], render_inline)
            flush_list(bullets, story, styles, False, render_inline)
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
        story.extend(make_table(table, styles["DocBase"], render_inline))
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
    source = source.resolve()
    output = output.resolve()
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

    def resolve_link(target: str) -> str:
        parts = urlsplit(target)
        if parts.scheme or parts.netloc:
            return target
        if not parts.path:
            return "#" + unquote(parts.fragment) if parts.fragment else target
        path = (source.parent / unquote(parts.path)).resolve()
        if path == source.resolve() and parts.fragment:
            return "#" + unquote(parts.fragment)
        # Sibling manuals are built together. Source/code links must instead
        # remain relative to the PDF directory, which differs from doc/src.
        if path.suffix == ".md" and path.parent == source.parent.resolve() and not parts.fragment:
            path = output.parent / (path.stem + ".pdf")
        relative = Path(os.path.relpath(path, output.parent)).as_posix()
        return urlunsplit(("", "", quote(relative, safe="/"), parts.query, parts.fragment))

    render_inline = lambda text: inline(text, resolve_link)
    doc.build(build_story(markdown, source.parent, styles, render_inline),
              onFirstPage=footer(title), onLaterPages=footer(title))


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
