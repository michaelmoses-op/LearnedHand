"""Build a minimal well-formed EPUB (our own text — not a copyrighted work)."""

from __future__ import annotations

import io
import zipfile


def make_epub(
    *,
    title: str = "Test Book",
    chapters: list[tuple[str, str]] | None = None,
) -> bytes:
    """Return EPUB bytes. `chapters` is a list of (heading, body_paragraphs)."""
    if chapters is None:
        # Enough text to produce multiple ~300–500 token chunks across sections.
        para = ("Justice is the first virtue of social institutions. " * 40).strip()
        chapters = [
            ("Chapter One", "\n\n".join([para, para, para])),
            ("Chapter Two", "\n\n".join([para, para])),
        ]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf"
      media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""",
        )
        manifest_items = []
        spine_items = []
        for i, (heading, body) in enumerate(chapters, start=1):
            name = f"chap{i}.xhtml"
            paragraphs = "".join(f"<p>{p}</p>" for p in body.split("\n\n") if p.strip())
            zf.writestr(
                f"OEBPS/{name}",
                f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{heading}</title></head>
<body><h1>{heading}</h1>{paragraphs}</body>
</html>
""",
            )
            manifest_items.append(
                f'<item id="c{i}" href="{name}" media-type="application/xhtml+xml"/>'
            )
            spine_items.append(f'<itemref idref="c{i}"/>')
        zf.writestr(
            "OEBPS/content.opf",
            f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="uid" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{title}</dc:title>
    <dc:identifier id="uid">test-epub-001</dc:identifier>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
    {"".join(manifest_items)}
  </manifest>
  <spine>
    {"".join(spine_items)}
  </spine>
</package>
""",
        )
    return buf.getvalue()
