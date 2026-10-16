"""EPUB parsing under strict size / zip-bomb / path-traversal limits. Worker-only."""

from __future__ import annotations

import io
import posixpath
import zipfile
from dataclasses import dataclass, field
from urllib.parse import unquote

from lxml import etree

from app.core.errors import DomainError
from app.ingestion.constants import (
    EPUB_MAX_COMPRESSION_RATIO,
    EPUB_MAX_FILE_BYTES,
    EPUB_MAX_FILES,
    EPUB_MAX_UNCOMPRESSED_BYTES,
    EPUB_RATIO_MIN_BYTES,
)

_CONTAINER_NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
_OPF_NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
}
_XHTML_NS = {"h": "http://www.w3.org/1999/xhtml"}
_NCX_NS = {"n": "http://www.daisy.org/z3986/2005/ncx/"}
_ENC_NS = {
    "e": "urn:oasis:names:tc:opendocument:xmlns:container",
    "x": "http://www.w3.org/2001/04/xmlenc#",
}
# Font obfuscation is ubiquitous and harmless; any other cipher on a text file means real DRM.
_FONT_OBFUSCATION = {"http://www.idpf.org/2008/embedding", "http://ns.adobe.com/pdf/enc#RC"}


def _xml_parser() -> etree.XMLParser:
    """Hardened: no entity expansion, no DTD loading, no network."""
    return etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True, huge_tree=False)


def _parse_xml(raw: bytes, what: str) -> etree._Element:
    try:
        return etree.fromstring(raw, parser=_xml_parser())
    except etree.XMLSyntaxError as exc:
        raise EpubParseError(f"Invalid {what}") from exc


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
        names = _NameIndex(zf)
        opf_path = _opf_path(zf, names)
        opf_dir = posixpath.dirname(opf_path)
        opf = _parse_xml(_read_member(zf, names, opf_path), "package document")
        title = _dc_title(opf) or "Untitled"
        manifest = _manifest(opf)
        spine_paths: list[tuple[str, str]] = []  # (manifest href, resolved path)
        for item_id in _spine_ids(opf):
            item = manifest.get(item_id)
            if item is None:
                continue
            full = _safe_join(opf_dir, item.href)
            if _is_xhtml(full, item.media_type):
                spine_paths.append((item.href, full))
        _reject_drm(zf, names, {full for _, full in spine_paths})
        toc = _toc_titles(zf, names, opf, manifest, opf_dir)
        sections: list[ParsedSection] = []
        skipped = 0
        for href, full in spine_paths:
            raw = _try_read(zf, names, full)
            if raw is None:  # listed in the spine but absent: skip it, keep the rest of the book
                skipped += 1
                continue
            text, heading = _xhtml_text(raw)
            if not text.strip():
                continue
            label = toc.get(full) or heading or posixpath.basename(href)
            sections.append(
                ParsedSection(title=label[:500], spine_href=full[:1000], text=text, depth=0)
            )
        if not sections:
            raise EpubParseError("EPUB has no readable text sections")
        stats = {"skipped_missing_items": skipped} if skipped else {}
        return ParsedBook(title=title[:200], sections=sections, stats=stats)


class _NameIndex:
    """Zip member lookup tolerant of case differences between the manifest and the archive."""

    def __init__(self, zf: zipfile.ZipFile) -> None:
        self.exact = set(zf.namelist())
        self.lower = {n.lower(): n for n in self.exact}

    def resolve(self, name: str) -> str | None:
        if name in self.exact:
            return name
        return self.lower.get(name.lower())


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
            info.file_size > EPUB_RATIO_MIN_BYTES
            and info.compress_size > 0
            and info.file_size / info.compress_size > EPUB_MAX_COMPRESSION_RATIO
        ):
            raise EpubParseError("Suspicious compression ratio")
        total_uncomp += info.file_size
        if total_uncomp > EPUB_MAX_UNCOMPRESSED_BYTES:
            raise EpubParseError("EPUB uncompressed size too large")


def _try_read(zf: zipfile.ZipFile, names: _NameIndex, name: str) -> bytes | None:
    real = names.resolve(name)
    if real is None:
        return None
    data = zf.read(real)
    if len(data) > EPUB_MAX_FILE_BYTES:
        raise EpubParseError("EPUB entry too large after inflate")
    return data


def _read_member(zf: zipfile.ZipFile, names: _NameIndex, name: str) -> bytes:
    data = _try_read(zf, names, name)
    if data is None:
        raise EpubParseError("Missing EPUB member")
    return data


def _opf_path(zf: zipfile.ZipFile, names: _NameIndex) -> str:
    container = _parse_xml(_read_member(zf, names, "META-INF/container.xml"), "container.xml")
    rootfile = container.find(".//c:rootfile", _CONTAINER_NS)
    if rootfile is None or not rootfile.get("full-path"):
        raise EpubParseError("Missing rootfile in container.xml")
    path = unquote(str(rootfile.get("full-path") or "")).replace("\\", "/")
    if path.startswith("/") or ".." in path.split("/"):
        raise EpubParseError("Unsafe rootfile path")
    return path


def _dc_title(opf: etree._Element) -> str | None:
    el = opf.find(".//dc:title", _OPF_NS)
    if el is not None and el.text:
        return str(el.text).strip()
    return None


@dataclass(frozen=True)
class _Item:
    href: str
    media_type: str
    properties: str


def _manifest(opf: etree._Element) -> dict[str, _Item]:
    out: dict[str, _Item] = {}
    for item in opf.findall(".//opf:manifest/opf:item", _OPF_NS):
        item_id = item.get("id")
        href = item.get("href")
        if item_id and href:
            out[item_id] = _Item(
                href.replace("\\", "/"),
                (item.get("media-type") or "").lower(),
                item.get("properties") or "",
            )
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
    href = unquote(href.split("#", 1)[0].split("?", 1)[0]).replace("\\", "/")
    joined = posixpath.normpath(posixpath.join(base, href) if base else href)
    if joined.startswith("..") or joined.startswith("/"):
        raise EpubParseError("Path traversal in spine href")
    return joined


def _is_xhtml(path: str, media_type: str = "") -> bool:
    if media_type in ("application/xhtml+xml", "text/html"):
        return True
    return path.lower().endswith((".xhtml", ".html", ".htm", ".xml"))


def _reject_drm(zf: zipfile.ZipFile, names: _NameIndex, content_paths: set[str]) -> None:
    """Fail clearly (rather than ingest ciphertext) when a text file is DRM-encrypted."""
    raw = _try_read(zf, names, "META-INF/encryption.xml")
    if raw is None:
        return
    try:
        root = etree.fromstring(raw, parser=_xml_parser())
    except etree.XMLSyntaxError:
        return
    lowered = {p.lower() for p in content_paths}
    for data in root.iterfind(".//x:EncryptedData", _ENC_NS):
        method = data.find("x:EncryptionMethod", _ENC_NS)
        ref = data.find(".//x:CipherReference", _ENC_NS)
        if method is None or ref is None:
            continue
        algorithm = method.get("Algorithm") or ""
        uri = unquote(ref.get("URI") or "").lstrip("/").lower()
        if algorithm not in _FONT_OBFUSCATION and uri in lowered:
            raise EpubParseError("This EPUB is DRM-protected and cannot be read")


def _toc_titles(
    zf: zipfile.ZipFile,
    names: _NameIndex,
    opf: etree._Element,
    manifest: dict[str, _Item],
    opf_dir: str,
) -> dict[str, str]:
    """Chapter labels from the EPUB3 nav document or the EPUB2 NCX, keyed by resolved path.
    Best effort: any problem just means we fall back to the heading inside the file."""
    titles: dict[str, str] = {}

    def add(href: str, label: str, base: str) -> None:
        label = " ".join(label.split())
        if not href or not label:
            return
        try:
            path = _safe_join(base, href)
        except EpubParseError:
            return
        titles.setdefault(path, label)

    try:
        for item in manifest.values():
            if "nav" in item.properties.split():
                raw = _try_read(zf, names, _safe_join(opf_dir, item.href))
                if raw is None:
                    continue
                root = etree.fromstring(raw, parser=_xml_parser())
                base = posixpath.dirname(_safe_join(opf_dir, item.href))
                for nav in root.iter("{*}nav"):
                    kinds = [v for k, v in nav.attrib.items() if k.endswith("type")]
                    if "toc" not in " ".join(kinds).split():
                        continue
                    for a in nav.iter("{*}a"):
                        add(a.get("href") or "", "".join(a.itertext()), base)
        if not titles:
            spine = opf.find(".//opf:spine", _OPF_NS)
            toc_id = spine.get("toc") if spine is not None else None
            ncx = manifest.get(toc_id or "")
            if ncx is not None:
                raw = _try_read(zf, names, _safe_join(opf_dir, ncx.href))
                if raw is not None:
                    root = etree.fromstring(raw, parser=_xml_parser())
                    base = posixpath.dirname(_safe_join(opf_dir, ncx.href))
                    for point in root.iter("{*}navPoint"):
                        text = point.find("n:navLabel/n:text", _NCX_NS)
                        content = point.find("n:content", _NCX_NS)
                        if text is not None and content is not None:
                            add(content.get("src") or "", "".join(text.itertext()), base)
    except (etree.XMLSyntaxError, EpubParseError, KeyError):
        return titles
    return titles


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
        root = etree.fromstring(raw, parser=_xml_parser())
    except etree.XMLSyntaxError:
        # Some EPUBs ship HTML that isn't well-formed XML; use the recovering HTML parser.
        try:
            root = etree.fromstring(raw, parser=etree.HTMLParser(recover=True, no_network=True))
        except etree.XMLSyntaxError:
            return "", None
        if root is None:
            return "", None
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
