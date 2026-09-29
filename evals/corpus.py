"""Built-in synthetic demo book: "The Chronicle of Saltmere" (original text, no copyright).

Each chapter mixes a few fact paragraphs (the gold passages the demo questions target) with
themed filler, so retrieval has real distractors. Deterministic: same bytes every run, so the
document hash — and therefore ingestion — can be reused between eval runs.
"""

from __future__ import annotations

import io
import random
import zipfile
from xml.sax.saxutils import escape

DEMO_TITLE = "The Chronicle of Saltmere"

# (chapter title, fact paragraphs, filler sentences)
_CHAPTERS: list[tuple[str, list[str], list[str]]] = [
    (
        "The Harbor Ledger",
        [
            "Harbormaster Elsbeth Marlowe recorded forty-two ships entering Saltmere harbor in the "
            "spring of 1611, more than any season before it, and she noted each hull by name.",
            "The lighthouse keeper Tobias Wren rebuilt the beacon tower with grey granite after "
            "the storm of 1623 had split the old timber frame from top to base.",
            "Salt cod was the harbor's chief export, sold each autumn to merchants from Bergen who "
            "arrived with the first cold winds and left before the ice.",
            "A tide table posted on the customs house door was updated every Sunday by the "
            "apprentice Nell Ashby, who copied the figures from the keeper's notebook.",
        ],
        [
            "Gulls wheeled over the quay while the nets dried in long grey rows.",
            "The pilots argued about the shoals at the mouth of the bay every evening.",
            "Ropes creaked against the bollards as the tide turned toward the sea.",
            "Children sold mussels from buckets at the foot of the customs steps.",
            "A bell on the pier warned the fishing boats when fog came in from the north.",
            "The ledger pages smelled of tar and were stained with salt spray.",
        ],
    ),
    (
        "The Orchard on the Hill",
        [
            "The Calder family planted three hundred apple trees on the eastern slope in 1702, "
            "clearing the gorse by hand over one long summer.",
            "Beekeeper Ines Varga introduced twelve hives to pollinate the blossom, doubling the "
            "harvest within two years and earning her a seat at the parish table.",
            "The russet variety known as Saltmere Gold ripens late in October and stores until "
            "March if it is wrapped in paper and kept from the frost.",
            "Pruning was done in February by the same crew every year, working from the top of "
            "the slope down toward the stone wall.",
        ],
        [
            "Petals drifted over the lane each May and stuck to the wheels of the carts.",
            "The press house held the smell of cider long after the last barrel was sealed.",
            "Wasps gathered in the fallen fruit and the pickers moved slowly among them.",
            "Frost came early one year and the whole hill went silent for a week.",
            "The wall along the road was rebuilt stone by stone after each hard winter.",
            "Children were paid a penny a basket to gather windfalls from the long grass.",
        ],
    ),
    (
        "Fire and Iron",
        [
            "The foundry's first furnace was fired in 1748 by the ironmaster Corwin Hale, using "
            "charcoal carried in from the northern woods by mule train.",
            "Its cast-iron bell, weighing nine hundred pounds, still hangs in the market square "
            "and was rung to mark the end of every working shift.",
            "Workers struck for shorter hours in 1791, winning a ten-hour day after three weeks "
            "of silence at the gates and a petition signed by every moulder.",
            "The pattern shop stored wooden models for every casting, each one numbered and "
            "hung on pegs along the whitewashed wall.",
        ],
        [
            "Sparks fell like orange rain when the crucibles were tipped at dusk.",
            "The smiths tested each hammer by its ring before they trusted it with a blow.",
            "Soot lay on the windowsills of every house within a mile of the works.",
            "The furnace roared through the night and lit the underside of the clouds.",
            "Apprentices learned to read the colour of the metal before they learned to write.",
            "Carters queued along the lane with coal, sand and sacks of limestone.",
        ],
    ),
    (
        "The Net Loft School",
        [
            "The Saltmere school opened in 1805 in a converted net loft with thirty pupils under "
            "Miss Agnes Dorr, who had walked from the county town to take the post.",
            "Pupils learned arithmetic by counting barrels of salt cod on the quay, adding each "
            "day's landing to a slate that hung beside the door.",
            "Slates were cleaned with a rag dipped in seawater, and the school smelled faintly of "
            "fish until the new floor was laid in 1812.",
        ],
        [
            "The loft stairs were steep and every child knew which step groaned.",
            "Winter lessons were held close to the stove with coats on and fingers tucked away.",
            "On fine days the older pupils read aloud on the sea wall while the boats came in.",
            "A map of the coast hung crooked above the desk and nobody dared to straighten it.",
            "Parents paid in fish, eggs and firewood when there was no coin to spare.",
        ],
    ),
    (
        "The Great Flood",
        [
            "The great flood of 1866 rose four feet above the harbor wall and carried away the "
            "lower bridge before the sun had cleared the eastern hills.",
            "Neighbors sheltered forty families in the foundry's cooling shed until the water "
            "fell, sharing bread, blankets and one enormous iron kettle.",
            "The parish register lists sixty-one cottages damaged and none lost to the flood "
            "itself, a fact the vicar recorded with evident astonishment.",
        ],
        [
            "The river turned the colour of strong tea and carried whole hedges downstream.",
            "By noon the market square was a lake with the bell tower standing in it.",
            "Boys rowed along the high street in fish tubs and were scolded by no one.",
            "When the water withdrew it left silt, splintered planks and a single startled cow.",
            "The mill wheel spun idly for days, turned by the current alone.",
        ],
    ),
    (
        "The Subscription Library",
        [
            "The subscription library was founded by widow Marta Quill, who donated her late "
            "husband's six hundred books and kept the key on a ribbon round her neck.",
            "Membership cost two shillings a year, waived for schoolchildren, and the borrowing "
            "register was closed each Saturday evening at seven.",
            "The reading room's oak table was made from a timber salvaged after the flood, and "
            "its scars were never sanded away.",
        ],
        [
            "Dust motes drifted through the afternoon light between the tall shelves.",
            "Members whispered out of habit even when the room was empty.",
            "A stove in the corner was lit only when the ink began to freeze in the wells.",
            "New arrivals were announced on a card pinned beside the door.",
            "The librarian dusted each spine with a feather before closing on Saturday.",
        ],
    ),
]


def demo_chapters() -> list[tuple[str, str]]:
    """(title, body) per chapter; fact paragraphs are interleaved with filler deterministically."""
    rng = random.Random(1611)  # noqa: S311 - deterministic fixture, not security
    out: list[tuple[str, str]] = []
    for title, facts, filler in _CHAPTERS:
        paragraphs: list[str] = []
        pool = filler[:]
        for fact in facts:
            rng.shuffle(pool)
            paragraphs.append(" ".join(pool[:2] + [fact] + pool[2:4]))
            # Filler-only paragraphs give retrieval real distractors (~5 chunks per chapter).
            for _ in range(3):
                paragraphs.append(" ".join(rng.sample(filler, k=len(filler))))
        out.append((title, "\n\n".join(paragraphs)))
    return out


def demo_epub() -> bytes:
    """Deterministic EPUB bytes (fixed timestamps) so the file hash is stable."""
    chapters = demo_chapters()
    buf = io.BytesIO()
    stamp = (2020, 1, 1, 0, 0, 0)

    def add(zf: zipfile.ZipFile, name: str, data: str, stored: bool = False) -> None:
        info = zipfile.ZipInfo(name, date_time=stamp)
        info.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
        zf.writestr(info, data)

    with zipfile.ZipFile(buf, "w") as zf:
        add(zf, "mimetype", "application/epub+zip", stored=True)
        add(
            zf,
            "META-INF/container.xml",
            '<?xml version="1.0"?>'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        manifest: list[str] = []
        spine: list[str] = []
        for i, (title, body) in enumerate(chapters, start=1):
            paras = "".join(f"<p>{escape(p)}</p>" for p in body.split("\n\n"))
            add(
                zf,
                f"OEBPS/chap{i}.xhtml",
                '<?xml version="1.0" encoding="utf-8"?>'
                '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>'
                f"{escape(title)}</title></head><body><h1>{escape(title)}</h1>{paras}</body></html>",
            )
            manifest.append(
                f'<item id="c{i}" href="chap{i}.xhtml" media-type="application/xhtml+xml"/>'
            )
            spine.append(f'<itemref idref="c{i}"/>')
        add(
            zf,
            "OEBPS/content.opf",
            '<?xml version="1.0" encoding="utf-8"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="uid" version="2.0">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f'<dc:title>{escape(DEMO_TITLE)}</dc:title><dc:identifier id="uid">saltmere-demo'
            "</dc:identifier><dc:language>en</dc:language></metadata>"
            f"<manifest>{''.join(manifest)}</manifest><spine>{''.join(spine)}</spine></package>",
        )
    return buf.getvalue()
