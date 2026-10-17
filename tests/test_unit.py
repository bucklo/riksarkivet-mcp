import pytest

from riksarkivet_mcp.client import RiksarkivetError, label, manifest_url
from riksarkivet_mcp.server import _canvases, _page_to_image


def canvas(lbl):
    return {"label": {"sv": [lbl]}}


MAN = {
    "items": [
        canvas("Bild 1"),
        canvas("Bild 4 / Sida 1"),
        canvas("Bild 5 / Sida 2"),
        canvas("Bild 6 / Sida 4"),
        canvas("Bild 7 / Sida 6"),
    ]
}


def test_canvases_parse():
    assert [(b, s) for b, s, _ in _canvases(MAN)] == [
        (1, ""),
        (4, "1"),
        (5, "2"),
        (6, "4"),
        (7, "6"),
    ]


@pytest.mark.parametrize(
    "page,image", [("1", 4), ("2", 5), ("3", 5), ("4", 6), ("7", 7), ("x", None)]
)
def test_page_to_image(page, image):
    assert _page_to_image(_canvases(MAN), page) == image


def test_manifest_url():
    assert manifest_url("A0006950") == "https://lbiiif.riksarkivet.se/arkis!A0006950/manifest"
    assert manifest_url("A0006950_00010").endswith("arkis!A0006950/manifest")
    assert manifest_url("https://x/y") == "https://x/y"
    with pytest.raises(RiksarkivetError):
        manifest_url("Heda")


def test_label():
    assert label({"en": ["a"], "sv": ["b"]}) == "b"
    assert label({"none": ["c"]}) == "c"
    assert label(None) == ""
