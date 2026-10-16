"""Real-world EPUB/PDF quirks: the parser should read what it can and fail with a clear reason."""

from __future__ import annotations

import io
import uuid
import zipfile
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.ingestion.parse_epub import EpubParseError, parse_epub
from app.ingestion.parse_pdf import parse_pdf
from app.jobs.worker import process_one
from tests.pdf_fixture import make_owner_locked_pdf, make_pdf
from tests.test_hierarchical import _wipe_jobs  # noqa: F401

PARA = "Being is that which is, and thought is the measure of being. " * 12
CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="{opf}" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""


def _xhtml(body: str, title: str = "") -> str:
    return (
        '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml">'
        f"<head><title>{title}</title></head><body>{body}</body></html>"
    )


def _build(
    files: dict[str, str | bytes],
    *,
    manifest: str,
    spine: str,
    opf: str = "OEBPS/content.opf",
    opf_extra: str = "",
    spine_attrs: str = "",
) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER.format(opf=opf))
        zf.writestr(
            opf,
            '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Quirky</dc:title>'
            f"</metadata><manifest>{manifest}</manifest><spine {spine_attrs}>{spine}</spine>"
            f"{opf_extra}</package>",
        )
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_percent_encoded_hrefs_and_case_mismatch_are_resolved() -> None:
    data = _build(
        {
            "OEBPS/Chapter One.xhtml": _xhtml(f"<h1>One</h1><p>{PARA}</p>"),
            "OEBPS/Text/Two.xhtml": _xhtml(f"<h1>Two</h1><p>{PARA}</p>"),
        },
        manifest=(
            '<item id="a" href="Chapter%20One.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="b" href="text/two.xhtml" media-type="application/xhtml+xml"/>'
        ),
        spine='<itemref idref="a"/><itemref idref="b"/>',
    )
    assert [s.title for s in parse_epub(data).sections] == ["One", "Two"]


def test_missing_spine_item_is_skipped_not_fatal() -> None:
    data = _build(
        {"OEBPS/a.xhtml": _xhtml(f"<h1>Only</h1><p>{PARA}</p>")},
        manifest=(
            '<item id="a" href="a.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="b" href="gone.xhtml" media-type="application/xhtml+xml"/>'
        ),
        spine='<itemref idref="b"/><itemref idref="a"/>',
    )
    book = parse_epub(data)
    assert [s.title for s in book.sections] == ["Only"]
    assert book.stats["skipped_missing_items"] == 1


def test_html_media_type_without_html_extension_is_read() -> None:
    data = _build(
        {"OEBPS/chapter.dat": _xhtml(f"<h1>Odd</h1><p>{PARA}</p>")},
        manifest='<item id="a" href="chapter.dat" media-type="application/xhtml+xml"/>',
        spine='<itemref idref="a"/>',
    )
    assert parse_epub(data).sections[0].title == "Odd"


def test_toc_titles_from_nav_and_ncx_beat_filenames() -> None:
    body = f"<p>{PARA}</p>"  # no heading inside the file
    nav = (
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
        '<body><nav epub:type="toc"><ol>'
        '<li><a href="c1.xhtml">The Allegory of the Cave</a></li>'
        '<li><a href="c2.xhtml#top">On the Good</a></li></ol></nav></body></html>'
    )
    data = _build(
        {"OEBPS/c1.xhtml": _xhtml(body), "OEBPS/c2.xhtml": _xhtml(body), "OEBPS/nav.xhtml": nav},
        manifest=(
            '<item id="n" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
            '<item id="a" href="c1.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="b" href="c2.xhtml" media-type="application/xhtml+xml"/>'
        ),
        spine='<itemref idref="a"/><itemref idref="b"/>',
    )
    assert [s.title for s in parse_epub(data).sections] == [
        "The Allegory of the Cave",
        "On the Good",
    ]
    ncx = (
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap>'
        '<navPoint id="p1"><navLabel><text>Meditation I</text></navLabel>'
        '<content src="c1.xhtml"/></navPoint></navMap></ncx>'
    )
    data = _build(
        {"OEBPS/c1.xhtml": _xhtml(body), "OEBPS/toc.ncx": ncx},
        manifest=(
            '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
            '<item id="a" href="c1.xhtml" media-type="application/xhtml+xml"/>'
        ),
        spine='<itemref idref="a"/>',
        spine_attrs='toc="ncx"',
    )
    assert parse_epub(data).sections[0].title == "Meditation I"


def test_drm_encrypted_text_is_reported_but_font_obfuscation_is_fine() -> None:
    enc = (
        '<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
        'xmlns:enc="http://www.w3.org/2001/04/xmlenc#">'
        '<enc:EncryptedData><enc:EncryptionMethod Algorithm="{alg}"/>'
        '<enc:CipherData><enc:CipherReference URI="{uri}"/></enc:CipherData>'
        "</enc:EncryptedData></encryption>"
    )
    kwargs: dict[str, Any] = {
        "manifest": '<item id="a" href="a.xhtml" media-type="application/xhtml+xml"/>',
        "spine": '<itemref idref="a"/>',
    }
    files = {"OEBPS/a.xhtml": _xhtml(f"<h1>A</h1><p>{PARA}</p>")}
    drm = _build(
        {
            **files,
            "META-INF/encryption.xml": enc.format(
                alg="http://www.w3.org/2001/04/xmlenc#aes128-cbc", uri="OEBPS/a.xhtml"
            ),
        },
        **kwargs,
    )
    with pytest.raises(EpubParseError, match="DRM"):
        parse_epub(drm)
    fonts = _build(
        {
            **files,
            "META-INF/encryption.xml": enc.format(
                alg="http://www.idpf.org/2008/embedding", uri="OEBPS/font.otf"
            ),
        },
        **kwargs,
    )
    assert parse_epub(fonts).sections


def test_malformed_xml_raises_a_clear_error_not_a_crash() -> None:
    data = _build(
        {},
        manifest="",
        spine="",
    )
    bad = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(bad, "w") as dst:
        for info in src.infolist():
            raw = src.read(info.filename)
            dst.writestr(info.filename, b"<package><oops" if info.filename.endswith("opf") else raw)
    with pytest.raises(EpubParseError, match="Invalid"):
        parse_epub(bad.getvalue())


def test_xxe_entities_are_not_expanded(tmp_path: Any) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET-VALUE")
    doc = (
        f'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file://{secret}">]>'
        '<html xmlns="http://www.w3.org/1999/xhtml"><body><h1>H</h1>'
        f"<p>&x; {PARA}</p></body></html>"
    )
    data = _build(
        {"OEBPS/a.xhtml": doc},
        manifest='<item id="a" href="a.xhtml" media-type="application/xhtml+xml"/>',
        spine='<itemref idref="a"/>',
    )
    text = " ".join(s.text for s in parse_epub(data).sections)
    assert "TOP-SECRET-VALUE" not in text


def test_many_small_blank_pages_do_not_trip_the_zip_bomb_check() -> None:
    files: dict[str, str | bytes] = {f"OEBPS/pad{i}.xhtml": " " * 40_000 for i in range(5)}
    files["OEBPS/a.xhtml"] = _xhtml(f"<h1>A</h1><p>{PARA}</p>")
    data = _build(
        files,
        manifest='<item id="a" href="a.xhtml" media-type="application/xhtml+xml"/>',
        spine='<itemref idref="a"/>',
    )
    assert parse_epub(data).sections


# ---- PDF ---------------------------------------------------------------------------------


async def test_owner_password_only_pdf_opens_without_a_password() -> None:
    book = await parse_pdf(make_owner_locked_pdf())
    assert book.sections


@pytest.mark.usefixtures("user_a")
async def test_pdf_with_junk_before_the_header_is_accepted(
    app: FastAPI, client: AsyncClient
) -> None:
    r = await client.post(
        "/api/v1/documents",
        content=b"\r\n\x00junk from a scanner\r\n" + make_pdf(),
        headers={"X-Filename": "Scan.PDF"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["format"] == "pdf"


@pytest.mark.usefixtures("user_a")
async def test_failed_ingest_reports_the_reason(app: FastAPI, client: AsyncClient) -> None:
    from tests.pdf_fixture import make_image_only_pdf

    r = await client.post(
        "/api/v1/documents", content=make_image_only_pdf(), headers={"X-Filename": "scan.pdf"}
    )
    doc_id = uuid.UUID(r.json()["id"])
    assert await process_one(app.state.sessionmaker, "compat-worker")
    st = (await client.get(f"/api/v1/documents/{doc_id}/status")).json()
    assert st["status"] == "failed" and "pdf_no_text_layer" in st["error"]


def test_default_upload_limit_is_generous() -> None:
    from app.core.config import Settings

    assert Settings.model_fields["max_upload_bytes"].default >= 250 * 1024 * 1024
