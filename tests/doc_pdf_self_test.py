#!/usr/bin/env python3
"""PDF build regression checks; requires reportlab and pypdf."""
from pathlib import Path
import sys
import tempfile
import unittest

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "doc"))
from build_md_pdf import build_pdf


class PdfBuildTests(unittest.TestCase):
    def render(self, markdown, source_subdirectory=""):
        work = tempfile.TemporaryDirectory(prefix="mk61-doc-pdf-")
        self.addCleanup(work.cleanup)
        source = Path(work.name) / source_subdirectory / "manual.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        output = Path(work.name) / "manual.pdf"
        source.write_text(markdown, encoding="utf-8")
        build_pdf(source, output, "MK61s PDF test")
        return PdfReader(output)

    def test_cyrillic_contents_and_duplicate_headings(self):
        pdf = self.render(
            "# Руководство\n\n"
            "[Первый](#память-c) и [второй](#память-c-1).\n\n"
            "## Память C++\n\nПервый раздел.\n\n"
            "## Память C++\n\nВторой раздел.\n"
        )
        links = [annotation.get_object() for page in pdf.pages
                 for annotation in page.get("/Annots", [])]
        self.assertEqual(len(links), 2)
        destinations = [link["/Dest"] for link in links]
        for destination in destinations:
            self.assertEqual(destination[0].get_object()["/Type"], "/Page")
        self.assertNotEqual(destinations[0], destinations[1])
        self.assertIn("Память C++", pdf.pages[0].extract_text())

    def test_links_follow_the_pdf_output_directory(self):
        pdf = self.render(
            "# Links\n\n[Manual](other.md)\n\n"
            "[Source](../../code/main.c?language=C&line=1)\n\n"
            "[Web](https://example.org/manual?a=1&b=2)\n",
            source_subdirectory="src",
        )
        links = [annotation.get_object()["/A"]["/URI"] for page in pdf.pages
                 for annotation in page.get("/Annots", [])]
        self.assertEqual(links, [
            "other.pdf", "../code/main.c?language=C&line=1",
            "https://example.org/manual?a=1&b=2",
        ])

    def test_short_code_example_stays_on_one_page(self):
        code = ["int first_line;", *[f"int variable_{i};" for i in range(12)],
                "int last_line;"]
        pdf = self.render(
            "# Example\n\n" + "Paragraph.\n\n" * 40 +
            "```c\n" + "\n".join(code) + "\n```\n"
        )
        pages = [page.extract_text() for page in pdf.pages]
        self.assertGreater(len(pages), 1)
        first = next(i for i, text in enumerate(pages) if "int first_line;" in text)
        last = next(i for i, text in enumerate(pages) if "int last_line;" in text)
        self.assertEqual(first, last)

    def test_image_and_caption_stay_on_one_page(self):
        with tempfile.TemporaryDirectory(prefix="mk61-doc-image-") as work:
            directory = Path(work)
            (directory / "image.ppm").write_bytes(
                b"P6\n40 45\n255\n" + b"\x00\x00\x00" * 40 * 45
            )
            source = directory / "manual.md"
            output = directory / "manual.pdf"
            source.write_text(
                "# Example\n\n" + "Paragraph.\n\n" * 36 +
                "![Figure caption](image.ppm)\n", encoding="utf-8",
            )
            build_pdf(source, output, "MK61s PDF test")
            pdf = PdfReader(output)
            image_pages = [i for i, page in enumerate(pdf.pages) if page.images]
            caption_pages = [i for i, page in enumerate(pdf.pages)
                             if "Figure caption" in page.extract_text()]
            self.assertEqual(len(image_pages), 1)
            self.assertEqual(image_pages, caption_pages)


if __name__ == "__main__":
    unittest.main()
