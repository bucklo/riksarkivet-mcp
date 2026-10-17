"""Thin async client for Riksarkivet's open APIs.

- Search API:   https://data.riksarkivet.se/api/records
- Register records: https://data.riksarkivet.se/register/<id>
- IIIF:         https://lbiiif.riksarkivet.se (Presentation 3 + Image API 3)

All data used here is published by Riksarkivet as open data; images are
public domain (PDM 1.0).
"""

from __future__ import annotations

import re
from typing import Any

import httpx

SEARCH_URL = "https://data.riksarkivet.se/api/records"
DATA_URL = "https://data.riksarkivet.se"
IIIF_URL = "https://lbiiif.riksarkivet.se"
USER_AGENT = "riksarkivet-mcp (+https://github.com/bucklo/riksarkivet-mcp)"

# record_type -> search facet
FACETS = {
    "birth": "ObjectType:Register;Type:BirthRecord",
    "marriage": "ObjectType:Register;Type:MarriageRecord",
    "title_deed": "ObjectType:Register;Type:IndexOfTitleDeedsRecord",
    "register": "ObjectType:Register",
    "volume": "ObjectType:Record;Type:Volume",
    "record": "ObjectType:Record",
    "archive": "ObjectType:RecordSet;Type:Fonds",
    "series": "ObjectType:RecordSet;Type:Series",
    "place": "ObjectType:Topography",
    "parish": "ObjectType:Topography;Type:Parish",
    "settlement": "ObjectType:Topography;Type:SettlementUnit",
    "agent": "ObjectType:Agent",
}

ARCHIVE_ID = re.compile(r"^[A-Za-z0-9]{20,24}$")
IMAGE_ID = re.compile(r"^([A-Z0-9]\d{7})(?:_(\d{5}))?$")


class RiksarkivetError(Exception):
    pass


class Client:
    def __init__(self, timeout: float = 30.0) -> None:
        self._http = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        self._manifests: dict[str, dict[str, Any]] = {}

    async def _json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        r = await self._http.get(url, params=params)
        if r.status_code == 404:
            raise RiksarkivetError(f"Not found: {url}")
        r.raise_for_status()
        try:
            return r.json()
        except ValueError as e:
            raise RiksarkivetError(f"Non-JSON response from {url}") from e

    # --- search ---------------------------------------------------------

    async def search(
        self,
        text: str | None = None,
        name: str | None = None,
        place: str | None = None,
        year_min: int | None = None,
        year_max: int | None = None,
        record_type: str | None = None,
        only_digitised: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"max": max(1, min(limit, 100)), "offset": offset}
        if text:
            params["text"] = text
        if name:
            params["name"] = name
        if place:
            params["place"] = place
        if year_min is not None:
            params["year_min"] = year_min
        if year_max is not None:
            params["year_max"] = year_max
        if only_digitised:
            params["only_digitised_materials"] = "true"
        if record_type:
            if record_type not in FACETS:
                raise RiksarkivetError(
                    f"Unknown record_type {record_type!r}; use one of {', '.join(FACETS)}"
                )
            params["facet"] = FACETS[record_type]
        if not (text or name or place):
            raise RiksarkivetError("Give at least one of text, name or place")
        return await self._json(SEARCH_URL, params)

    # --- single records -------------------------------------------------

    async def register_record(self, rid: str) -> dict[str, Any]:
        return await self._json(f"{DATA_URL}/register/{rid}")

    # --- IIIF -----------------------------------------------------------

    async def collection(self, archive_id: str) -> dict[str, Any]:
        return await self._json(f"{IIIF_URL}/collection/arkiv/{archive_id}")

    async def manifest(self, volume: str) -> dict[str, Any]:
        """volume: manifest URL or image-series id such as 'A0006950'."""
        url = manifest_url(volume)
        if url not in self._manifests:
            self._manifests[url] = await self._json(url)
        return self._manifests[url]

    async def image(
        self,
        image_id: str,
        width: int = 1600,
        region: str = "full",
        rotation: int = 0,
    ) -> bytes:
        url = f"{IIIF_URL}/v3/arkis!{image_id}/{region}/{width},/{rotation}/default.jpg"
        r = await self._http.get(url, headers={"Accept": "image/jpeg"})
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
            raise RiksarkivetError(f"Could not fetch image {image_id} ({r.status_code})")
        return r.content

    async def aclose(self) -> None:
        await self._http.aclose()


def manifest_url(volume: str) -> str:
    volume = volume.strip()
    if volume.startswith("http"):
        return volume
    m = IMAGE_ID.match(volume)
    if not m:
        raise RiksarkivetError(
            f"{volume!r} is not a manifest URL or image-series id (e.g. A0006950)"
        )
    return f"{IIIF_URL}/arkis!{m.group(1)}/manifest"


def label(obj: dict[str, Any] | None) -> str:
    """First Swedish (or any) string of a IIIF language map."""
    if not obj:
        return ""
    for lang in ("sv", "none", "en"):
        if obj.get(lang):
            return obj[lang][0]
    return next(iter(obj.values()), [""])[0]


def meta(item: dict[str, Any], key_sv: str) -> str:
    for m in item.get("metadata") or []:
        if label(m.get("label")) == key_sv:
            return label(m.get("value"))
    return ""
