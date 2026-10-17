"""MCP server exposing Riksarkivet (Swedish National Archives) open data."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from mcp.server.mcpserver import Image, MCPServer

from .client import IMAGE_ID, Client, RiksarkivetError, label, meta

mcp = MCPServer(
    "riksarkivet",
    instructions=(
        "Tools for Swedish genealogy and archive research against Riksarkivet's open APIs. "
        "Typical flow for church records: find_place (village/farm -> parish) -> "
        "parish_archive (which volumes are digitised, with date ranges) -> volume_pages "
        "(map page numbers to image numbers) -> get_page (fetch the scan and read it). "
        "Birth books are chronological, so jump to an estimated image and step forward/back. "
        "Indexed person registers (search_records with record_type birth/marriage) only cover "
        "some regions (mainly Skåne, Blekinge, Halland and parts of Norrland) - an empty result "
        "does not mean the event is missing from the church books. Censuses "
        "(folkräkningar) are not available through these APIs."
    ),
)

_client: Client | None = None


def client() -> Client:
    global _client
    if _client is None:
        _client = Client()
    return _client


def _fmt_item(it: dict[str, Any]) -> str:
    md = it.get("metadata") or {}
    typ = it.get("type", "")
    rid = it.get("id", "")
    if typ in ("BirthRecord", "MarriageRecord", "IndexOfTitleDeedsRecord"):
        fields = ", ".join(f"{k}: {v}" for k, v in md.items() if v)
        return f"- [{typ}] {it.get('caption') or ''} — {fields} (id: {rid})"
    parts = []
    if md.get("referenceCode"):
        parts.append(md["referenceCode"])
    if md.get("date"):
        parts.append(md["date"].strip())
    hier = " > ".join(h["caption"] for h in md.get("hierarchy") or [])
    if hier:
        parts.append(f"in {hier}")
    part_of = ", ".join(p["caption"] for p in md.get("partOf") or [])
    if part_of:
        parts.append(f"part of {part_of}")
    if md.get("onlyDigitisedMaterials"):
        parts.append("digitised")
    caption = it.get("caption") or md.get("referenceCode") or ""
    return f"- [{typ}] {caption} — {'; '.join(parts)} (id: {rid})"


@mcp.tool()
async def search_records(
    text: str | None = None,
    name: str | None = None,
    place: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    record_type: str | None = None,
    only_digitised: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> str:
    """Search Riksarkivet's catalogue and indexed registers.

    text: free text. name: person name. place: parish/place name.
    year_min/year_max: restrict by year.
    record_type: birth, marriage, title_deed, register, volume, record, archive (fonds),
      series, place, parish, settlement, agent. Omit for everything.
    only_digitised: only material with scanned images.
    limit (max 100) / offset for paging.

    Note: indexed birth/marriage registers cover only some regions; use parish_archive +
    get_page to read church books directly elsewhere (e.g. Östergötland).
    """
    try:
        data = await client().search(
            text, name, place, year_min, year_max, record_type, only_digitised, limit, offset
        )
    except RiksarkivetError as e:
        return f"Error: {e}"
    items = data.get("items") or []
    head = f"{data.get('totalHits', 0)} hits (showing {offset + 1}-{offset + len(items)})"
    if not items:
        return head
    return head + "\n" + "\n".join(_fmt_item(it) for it in items)


@mcp.tool()
async def get_register_record(record_id: str) -> str:
    """Full details of an indexed register entry (birth, marriage, title deed) by its id
    from search_records - parents, occupations, residence, witnesses, volume/page."""
    try:
        rec = await client().register_record(record_id.rsplit("/", 1)[-1])
    except RiksarkivetError as e:
        return f"Error: {e}"
    return "\n".join(f"{k}: {v}" for k, v in rec.items() if v not in (None, ""))


@mcp.tool()
async def find_place(name: str, limit: int = 10) -> str:
    """Look up a place (village, farm, parish) in Riksarkivet's topographic register and
    show which parish/province it belongs to, including historical parishes
    (e.g. Harstad parish, merged into Väderstad 1891)."""
    try:
        data = await client().search(text=name, record_type="place", limit=limit)
    except RiksarkivetError as e:
        return f"Error: {e}"
    items = data.get("items") or []
    if not items:
        return (
            f"No place named {name!r}. Try spelling variants (ä/e, k/ck, single/double "
            "consonants, -stad/-sta) or the modern name."
        )
    lines = []
    for it in items:
        md = it.get("metadata") or {}
        part_of = "; ".join(
            f"{p['caption']}" + (f" ({p['date'].strip()})" if p.get("date") else "")
            for p in md.get("partOf") or []
        )
        lines.append(f"- [{it.get('type')}] {it.get('caption')} — {part_of}")
    return "\n".join(lines)


async def _find_fonds(parish: str) -> list[dict[str, Any]]:
    name = parish.strip()
    if not name.lower().endswith("kyrkoarkiv"):
        name = f"{name} kyrkoarkiv"
    data = await client().search(text=name, record_type="archive", limit=25)
    stem = parish.strip().lower().removesuffix(" kyrkoarkiv")
    items = data.get("items") or []
    exact = [i for i in items if (i.get("caption") or "").lower().startswith(stem)]
    return exact or items[:5]


def _volume_line(v: dict[str, Any]) -> str:
    lab = label(v.get("label"))
    if v.get("type") == "Manifest" and not lab.startswith("Se:"):
        vid = v["id"].split("arkis!")[-1].split("/")[0] if "arkis!" in v["id"] else v["id"]
        return f"    - {lab}  [volume: {vid}]"
    return f"    - {lab}"


@mcp.tool()
async def parish_archive(parish: str, series: str | None = None) -> str:
    """List the digitised volumes of a parish's church archive (kyrkoarkiv), grouped by
    series, with date ranges and the volume id to pass to volume_pages/get_page.

    parish: e.g. "Heda", "Väderstad", "Appuna".
    series: optional filter on series code or name, e.g. "C" (födelse- och dopböcker),
      "A I" (husförhörslängder), "E I" (vigsel), "F" (död), "A II" (församlingsböcker),
      "B" (flyttningslängder).

    Only volumes scanned by Riksarkivet itself are listed (mostly c. 1840-1900). Lines
    starting "Se:" mean the records are bound into another listed volume.
    """
    try:
        fonds = await _find_fonds(parish)
    except RiksarkivetError as e:
        return f"Error: {e}"
    if not fonds:
        return f"No church archive found for {parish!r}."
    out = []
    for f in fonds[:3]:
        fid = f["id"]
        try:
            col = await client().collection(fid)
        except (RiksarkivetError, Exception):  # noqa: BLE001 - IIIF may lack the fonds
            out.append(f"{f.get('caption')} (id {fid}): no digitised material listed")
            continue
        all_series = col.get("items") or []
        if series:
            s = series.strip().lower()
            all_series = [
                x
                for x in all_series
                if label(x.get("label")).lower().startswith(s + " ")
                or s in label(x.get("label")).lower()
            ]
        subs = await asyncio.gather(
            *(client().collection(x["id"].rsplit("/", 1)[-1]) for x in all_series),
            return_exceptions=True,
        )
        out.append(f"{label(col.get('label')) or f.get('caption')} (archive id {fid})")
        if not all_series:
            out.append("  (no matching series)")
        for x, sub in zip(all_series, subs):
            out.append(f"  {label(x.get('label'))}")
            if isinstance(sub, Exception):
                out.append("    (could not load)")
                continue
            vols = sub.get("items") or []
            out.extend(_volume_line(v) for v in vols)
            if not vols:
                out.append("    (none)")
    return "\n".join(out)


@mcp.tool()
async def browse(archive_id: str) -> str:
    """List the children of any Riksarkivet archive unit in IIIF (fonds -> series ->
    volumes). Use for non-church archives too (courts, military rolls, maps). archive_id
    is the id from search_records or parish_archive."""
    try:
        col = await client().collection(archive_id.rsplit("/", 1)[-1])
    except RiksarkivetError as e:
        return f"Error: {e}"
    lines = [label(col.get("label"))]
    for s in (col.get("summary") or {}).get("sv", []):
        lines.append(f"  {s}")
    for it in col.get("items") or []:
        if it.get("type") == "Collection":
            lines.append(
                f"  - {label(it.get('label'))}  [archive id: {it['id'].rsplit('/', 1)[-1]}]"
            )
        else:
            lines.append(_volume_line(it).replace("    ", "  ", 1))
    if not col.get("items"):
        lines.append("  (no digitised children)")
    return "\n".join(lines)


_PAGE = re.compile(r"Bild\s+(\d+)(?:\s*/\s*Sida\s+(\S+))?")


def _canvases(man: dict[str, Any]) -> list[tuple[int, str, dict[str, Any]]]:
    res = []
    for c in man.get("items") or []:
        m = _PAGE.search(label(c.get("label")))
        if m:
            res.append((int(m.group(1)), m.group(2) or "", c))
    return res


@mcp.tool()
async def volume_pages(volume: str) -> str:
    """Show a volume's title, date range, remarks and the mapping image number -> printed
    page number (Bild:Sida). volume: id like 'A0006950' or a manifest URL."""
    try:
        man = await client().manifest(volume)
    except RiksarkivetError as e:
        return f"Error: {e}"
    cans = _canvases(man)
    lines = [label(man.get("label"))]
    for key in ("Datering", "Anmärkning"):
        v = meta(man, key)
        if v:
            lines.append(f"{key}: {v}")
    lines.append(f"{len(cans)} images. Bild:Sida —")
    lines.append(" ".join(f"{b}:{s}" if s else f"{b}" for b, s, _ in cans))
    return "\n".join(lines)


def _page_to_image(cans: list[tuple[int, str, dict[str, Any]]], page: str) -> int | None:
    for b, s, _ in cans:
        if s == page:
            return b
    try:
        want = int(page)
    except ValueError:
        return None
    best = None
    for b, s, _ in cans:  # spreads: label carries the left page, so take nearest lower
        if s.isdigit() and int(s) <= want:
            best = b
    return best


_REGION = re.compile(r"^(full|square|\d+,\d+,\d+,\d+|pct:[\d.]+,[\d.]+,[\d.]+,[\d.]+)$")


@mcp.tool()
async def get_page(
    volume: str,
    image: int | None = None,
    page: str | None = None,
    width: int = 1600,
    region: str = "full",
    rotation: int = 0,
) -> list[Any]:
    """Fetch a scanned page so it can be read. Returns the image plus a ready-made source
    citation (Källhänvisning) and viewer link.

    volume: volume id like 'A0006950', a manifest URL, or a full image id
      like 'A0006950_00010' (then image is taken from it).
    image: image number (Bild). page: printed page number (Sida) instead of image.
    width: output width in px (400-3000). Use ~1600 for an overview, then zoom with region.
    region: 'full', 'pct:x,y,w,h' (percent of the page) or 'x,y,w,h' pixels - e.g.
      'pct:50,0,50,50' = top-right quarter, good for reading small handwriting.
    rotation: 0/90/180/270.
    """
    try:
        m = IMAGE_ID.match(volume.strip())
        if m and m.group(2):
            volume, image = m.group(1), int(m.group(2))
        if not _REGION.match(region):
            return [f"Error: bad region {region!r}"]
        man = await client().manifest(volume)
        cans = _canvases(man)
        if image is None and page is not None:
            image = _page_to_image(cans, page)
            if image is None:
                return [f"Error: page {page} not found; see volume_pages"]
        if image is None:
            return ["Error: give image or page"]
        canvas = next((c for b, _, c in cans if b == image), None)
        if canvas is None:
            return [f"Error: image {image} not in volume ({len(cans)} images)"]
        bildid = meta(canvas, "Bildid")
        data = await client().image(
            bildid, width=max(400, min(width, 3000)), region=region, rotation=rotation
        )
    except RiksarkivetError as e:
        return [f"Error: {e}"]
    info = (
        f"{label(canvas.get('label'))} of {len(cans)} — bildid {bildid}\n"
        f"Källhänvisning: {meta(canvas, 'Källhänvisning')}\n"
        f"Viewer: {meta(canvas, 'Länk')}"
    )
    return [info, Image(data=data, format="jpeg")]


def main() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    mcp.run()


if __name__ == "__main__":
    main()
