"""EPUB parsing under strict size / zip-bomb / path-traversal limits. Worker-only."""

from __future__ import annotations

import io
import posixpath
import zipfile
from dataclasses import dataclass, field

from lxml import etree

from app.core.errors import DomainError
from app.ingestion.constants import (
    EPUB_MAX_COMPRESSION_RATIO,
    EPUB_MAX_FILE_BYTES,
    EPUB_MAX_FILES,
    EPUB_MAX_UNCOMPRESSED_BYTES,
)

_CONTAINER_NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
_OPF_NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
}
_XHTML_NS = {"h": "http://www.w3.org/1999/xhtml"}


class EpubParseError(DomainError):
    code = "epub_invalid"
    title = "Invalid or unsafe EPUB"


@dataclass
class ParsedSection:
    title: str
    spine_href: str
    text: str
    depth: int = 0
    # PDF only: [[char_offset, page_number], ...] sorted by offset.
    page_map: list[list[int]] | None = None
    page_start: int | None = None
    page_end: int | None = None


@dataclass
class ParsedBook:
    title: str
    sections: list[ParsedSection] = field(default_factory=list)
    # Counters from the parser (e.g. stripped header/footer lines); never text.
    stats: dict[str, int] = field(default_factory=dict)


def parse_epub(data: bytes) -> ParsedBook:
    """Parse an EPUB bytes blob into ordered sections. Raises EpubParseError on abuse/invalid."""
    if len(data) < 4 or data[:2] != b"PK":
        raise EpubParseError("Not a ZIP/EPUB archive")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise EpubParseError("Corrupt ZIP") from exc

    with zf:
        _assert_safe_zip(zf)
        opf_path = _opf_path(zf)
        opf_dir = posixpath.dirname(opf_path)
        opf = etree.fromstring(_read_member(zf, opf_path))
        title = _dc_title(opf) or "Untitled"
        manifest = _manifest(opf)
        spine_ids = _spine_ids(opf)
        sections: list[ParsedSection] = []
        for item_id in spine_ids:
            href = manifest.get(item_id)
            if not href:
                continue
            full = _safe_join(opf_dir, href)
            if not _is_xhtml(full):
                continue
            raw = _read_member(zf, full)
            text, heading = _xhtml_text(raw)
            if not text.strip():
                continue
            sections.append(
                ParsedSection(
                    title=(heading or posixpath.basename(href))[:500],
                    spine_href=full[:1000],
                    text=text,
                    depth=0,
                )
            )
        if not sections:
            raise EpubParseError("EPUB has no readable text sections")
        return ParsedBook(title=title[:200], sections=sections)


def _assert_safe_zip(zf: zipfile.ZipFile) -> None:
    infos = zf.infolist()
    if len(infos) > EPUB_MAX_FILES:
        raise EpubParseError("Too many files in EPUB")
    total_uncomp = 0
    for info in infos:
        name = info.filename.replace("\\", "/")
        if name.startswith("/") or ".." in name.split("/"):
            raise EpubParseError("Path traversal in EPUB entry")
        if info.file_size > EPUB_MAX_FILE_BYTES:
            raise EpubParseError("EPUB entry too large")
        if (
            info.compress_size > 0
            and info.file_size / info.compress_size > EPUB_MAX_COMPRESSION_RATIO
        ):
            raise EpubParseError("Suspicious compression ratio")
        total_uncomp += info.file_size
        if total_uncomp > EPUB_MAX_UNCOMPRESSED_BYTES:
            raise EpubParseError("EPUB uncompressed size too large")


def _read_member(zf: zipfile.ZipFile, name: str) -> bytes:
    try:
        data = zf.read(name)
    except KeyError as exc:
        raise EpubParseError("Missing EPUB member") from exc
    if len(data) > EPUB_MAX_FILE_BYTES:
        raise EpubParseError("EPUB entry too large after inflate")
    return data


def _opf_path(zf: zipfile.ZipFile) -> str:
    try:
        container = etree.fromstring(_read_member(zf, "META-INF/container.xml"))
    except etree.XMLSyntaxError as exc:
        raise EpubParseError("Invalid container.xml") from exc
    rootfile = container.find(".//c:rootfile", _CONTAINER_NS)
    if rootfile is None or not rootfile.get("full-path"):
        raise EpubParseError("Missing rootfile in container.xml")
    path = str(rootfile.get("full-path") or "").replace("\\", "/")
    if path.startswith("/") or ".." in path.split("/"):
        raise EpubParseError("Unsafe rootfile path")
    return path


def _dc_title(opf: etree._Element) -> str | None:
    el = opf.find(".//dc:title", _OPF_NS)
    if el is not None and el.text:
        return str(el.text).strip()
    return None


def _manifest(opf: etree._Element) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in opf.findall(".//opf:manifest/opf:item", _OPF_NS):
        item_id = item.get("id")
        href = item.get("href")
        if item_id and href:
            out[item_id] = href.replace("\\", "/")
    return out


def _spine_ids(opf: etree._Element) -> list[str]:
    ids: list[str] = []
    for itemref in opf.findall(".//opf:spine/opf:itemref", _OPF_NS):
        ref = itemref.get("idref")
        if ref:
            ids.append(ref)
    return ids


def _safe_join(base: str, href: str) -> str:
    # Strip fragment / query; resolve relative to OPF dir without escaping the package root.
    href = href.split("#", 1)[0].split("?", 1)[0].replace("\\", "/")
    joined = posixpath.normpath(posixpath.join(base, href) if base else href)
    if joined.startswith("..") or joined.startswith("/"):
        raise EpubParseError("Path traversal in spine href")
    return joined


def _is_xhtml(path: str) -> bool:
    lower = path.lower()
    return lower.endswith((".xhtml", ".html", ".htm", ".xml"))


_BLOCK_TAGS = frozenset(
    {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "dt", "dd", "tr"}
)


def _local(el: etree._Element) -> str:
    return etree.QName(el).localname.lower() if "}" in str(el.tag) else str(el.tag).lower()


def _clean_text(text: str) -> str:
    """Collapse runs of whitespace but keep explicit line breaks."""
    lines = (" ".join(line.split()) for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def _is_block(el: etree._Element) -> bool:
    return isinstance(el.tag, str) and _local(el) in _BLOCK_TAGS


def _has_block_descendant(el: etree._Element) -> bool:
    return any(_is_block(d) for d in el.iterdescendants())


def _collect_blocks(el: etree._Element, out: list[str]) -> None:
    """One paragraph per innermost block. A wrapper <div>/<blockquote> is not emitted as well as
    its children (that duplicated text), and loose text between nested blocks stays a paragraph."""
    if not _has_block_descendant(el):
        text = _clean_text("".join(el.itertext()))
        if text:
            out.append(text)
        return
    loose = el.text or ""

    def flush() -> None:
        nonlocal loose
        text = _clean_text(loose)
        if text:
            out.append(text)
        loose = ""

    for child in el:
        if isinstance(child.tag, str) and (_is_block(child) or _has_block_descendant(child)):
            flush()
            _collect_blocks(child, out)
        elif isinstance(child.tag, str):
            loose += "".join(child.itertext())
        loose += child.tail or ""
    flush()


def _xhtml_text(raw: bytes) -> tuple[str, str | None]:
    try:
        root = etree.fromstring(raw)
    except etree.XMLSyntaxError:
        # Some EPUBs ship HTML that isn't well-formed XML; use recover parser.
        parser = etree.HTMLParser(recover=True)
        root = etree.fromstring(raw, parser=parser)
    heading = None
    for tag in ("h1", "h2", "h3", "title"):
        el = root.find(f".//h:{tag}", _XHTML_NS)
        if el is None:
            el = root.find(f".//{tag}")
        if el is not None and "".join(el.itertext()).strip():
            heading = " ".join("".join(el.itertext()).split())[:500]
            break
    # Drop script/style
    for bad in root.xpath("//*[local-name()='script' or local-name()='style']"):
        parent = bad.getparent()
        if parent is not None:
            parent.remove(bad)
    body = root.find(".//h:body", _XHTML_NS)
    if body is None:
        body = root.find(".//body")
    target = body if body is not None else root
    # <br> becomes a real line break (verse, addresses); other whitespace collapses.
    for br in target.iter():
        if isinstance(br.tag, str) and _local(br) == "br":
            br.tail = "\n" + (br.tail or "")
    parts: list[str] = []
    _collect_blocks(target, parts)
    if not parts:
        t = _clean_text("".join(target.itertext()))
        if t:
            parts.append(t)
    return "\n\n".join(parts), heading
