"""Smoke tests against the real APIs. Run with: uv run pytest -m live"""

import pytest

from riksarkivet_mcp import server

pytestmark = pytest.mark.live


async def test_find_place_historical_parish():
    out = await server.find_place("Harstad")
    assert "Harstads församling" in out


async def test_search_birth_register():
    out = await server.search_records(name="Svensson", place="Rödeby", record_type="birth", limit=3)
    assert "BirthRecord" in out


async def test_parish_archive_lists_birth_books():
    out = await server.parish_archive("Appuna", series="C")
    assert "A0006950" in out


async def test_get_page_returns_image_and_citation():
    info, img = await server.get_page("A0006950", page="12", width=600)
    assert "Källhänvisning: Appuna kyrkoarkiv" in info
    assert img.data[:2] == b"\xff\xd8"
