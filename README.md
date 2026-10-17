# riksarkivet-mcp

An [MCP](https://modelcontextprotocol.io) server for **Riksarkivet** (the Swedish National Archives) open data. It lets an AI assistant do Swedish genealogy research from start to finish: work out which parish a village belongs to, find the digitised church books, and **fetch and read the scanned pages**, getting back a ready-made source citation.

It only uses Riksarkivet's public, keyless APIs:

| API | Used for |
|---|---|
| [Search API](https://data.riksarkivet.se/api/records) | archive catalogue, topography, indexed birth/marriage/title-deed registers |
| [IIIF Presentation & Image API](https://lbiiif.riksarkivet.se) | browsing digitised volumes and fetching page images |

Metadata is open data and the images are public domain (PDM 1.0).

## Tools

| Tool | What it does |
|---|---|
| `search_records` | Free text / name / place / year search, filterable by record type (`birth`, `marriage`, `title_deed`, `volume`, `archive`, `place`, `parish`, `settlement`, `agent`, …) |
| `get_register_record` | Full entry of an indexed register record: parents, occupations, residence, witnesses, volume and page |
| `find_place` | Village/farm/parish → parish and province, including historical parishes (e.g. *Harstad, merged into Väderstad 1891*) |
| `parish_archive` | A parish's digitised church-book volumes grouped by series (C births, A I household examinations, E I marriages, F deaths, …), with date ranges and volume ids |
| `browse` | Walk any archive in IIIF (fonds → series → volumes), including court records, military rolls and maps |
| `volume_pages` | A volume's date range, remarks, and image number → printed page number map |
| `get_page` | Returns a page image (whole page or a zoomed region) plus its *Källhänvisning* and viewer link |

### Typical flow

```
find_place("Kälstad")            → Källstad, Källstads församling, Östergötland
parish_archive("Heda", "C")      → C/5 (1870-1888) [volume: A0001234] …
volume_pages("A0001234")         → Bild:Sida map
get_page("A0001234", image=57)   → scan + "Heda kyrkoarkiv, Födelse- och dopböcker, SE/VALA/00128/C/5 (1870-1888), bildid: A0001234_00057, sida 108"
get_page("A0001234", image=57, region="pct:0,40,60,30", width=2000)   → zoom on one entry
```

## Limitations

- **Coverage of images.** Only volumes that Riksarkivet scanned itself are served over IIIF, and for most parishes that means roughly 1840–1900. Other periods may be available on [sok.riksarkivet.se](https://sok.riksarkivet.se) or through ArkivDigital.
- **Indexed registers are regional.** The searchable birth and marriage registers mainly cover Skåne, Blekinge, Halland and parts of Norrland. An empty search result does not mean a record doesn't exist, so read the church books with `get_page` instead.
- **No census search.** The census databases (folkräkningar) and other database searches on sok.riksarkivet.se have no public API and are not included.

## Install

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/bucklo/riksarkivet-mcp
cd riksarkivet-mcp
uv sync
```

### Claude Code

```bash
claude mcp add riksarkivet -- uv run --directory /path/to/riksarkivet-mcp riksarkivet-mcp
```

### Claude Desktop / other clients

```json
{
  "mcpServers": {
    "riksarkivet": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/riksarkivet-mcp", "riksarkivet-mcp"]
    }
  }
}
```

## Development

```bash
uv run pytest            # unit tests
uv run pytest -m live    # smoke tests against the real APIs
uv run ruff check .
```

## License

MIT. Not affiliated with Riksarkivet.
