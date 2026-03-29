# Quick Geological Search Playbook

Date: 2026-03-29
Version: v1

How to go from coordinates to useful geological information.
This playbook is for manual research and operator-driven data discovery.
It complements the automated `build_geological_area_search_engine_v1.py` script.

---

## Step 1: Reverse Geocode

**Goal:** Turn raw coordinates into human-readable place names.

- Input: lat, lon (or bounding box)
- Tools:
  - Nominatim (free, no auth): https://nominatim.openstreetmap.org/
  - Google Maps API (limited free tier): requires API key
- Output: Country, state/province, municipality, nearby landmarks

**Automated:** The search engine script calls Nominatim automatically.
**Manual fallback:** If Nominatim is down, use Google Maps or OpenStreetMap directly.

---

## Step 2: Identify Geological Context

**Goal:** Establish the geological province, belt, and formation.

- Query Macrostrat API at coordinates:
  - `https://macrostrat.org/api/mobile/map_query?lat={lat}&lng={lon}&z=10`
  - Returns: lithology, formation name, age, stratigraphic column
- Identify the geological province / belt / domain:
  - Examples: "Eastern Goldfields", "Andes Copper Belt", "Zambian Copperbelt"
  - These names are often more useful for searching than coordinates
- If Macrostrat returns sparse data: use expected belt from domain knowledge or
  consult the GeaSpirit zone metadata in `GEASPIRIT_FREE_DATA_ACCESS_MAP_V1.json`

**Coverage reality:**
- Macrostrat US coverage: GOOD
- Macrostrat Australia coverage: MODERATE
- Macrostrat South America, Africa: SPARSE — may return no data

---

## Step 3: Expand Search Terms

Generate queries from the geological context. Tier 1 is highest specificity.

**Tier 1 — Belt level (most specific):**
- `[Belt name] geological map`
- `[Belt name] mineral deposits`
- `[Belt name] geophysical survey`

**Tier 2 — Formation level:**
- `[Formation name] mineralization`
- `[Formation name] geology report`

**Tier 3 — State / national survey level:**
- `[State/Province] geological survey [deposit type]`
- `[National survey name] [city] geology`

**Tier 4 — Locality level:**
- `[City] geology`
- `[City] mineral deposit`
- `[City] mining district`

**Tier 5 — Geophysics data:**
- `[City] Earth MRI geophysics`
- `[Country] airborne magnetics survey`

**Note:** These are suggestions for manual use. The search engine script generates them
automatically but does NOT run them against any external search engine.

---

## Step 4: Prioritize Sources

Run searches against these sources in priority order:

1. **National geological survey websites**
   - Australia: GA (ga.gov.au), GSWA (dmirs.wa.gov.au)
   - Chile: SERNAGEOMIN (sernageomin.cl)
   - Zambia: GSZ (gsz.gov.zm)
   - USA: USGS (usgs.gov), state surveys (e.g., AZGS for Arizona)
   - Peru: INGEMMET (ingemmet.gob.pe)
   - Canada: NRCan (nrcan.gc.ca)
   - South Africa: CGS (geoscience.org.za)

2. **USGS MRDS** — mineral resources database globally
   - REST API: `https://mrdata.usgs.gov/mrds/search-mrds.php`
   - No auth required

3. **Macrostrat API** — geological context at any coordinate
   - `https://macrostrat.org/api/`
   - No auth required

4. **OneGeology portal** — global geological maps (WMS/WFS)
   - `http://www.onegeology.org/`
   - Quality varies significantly by country layer

5. **Academic repositories**
   - GeoRef, Google Scholar with geology terms
   - Add "open access" or "preprint" to find free full text

6. **State / provincial mining departments**
   - Often have more detailed local maps than national surveys

---

## Step 5: Assess Coverage Confidence

| Confidence | Criteria |
|------------|----------|
| HIGH | Major mining district, established geological survey, downloadable reports, MRDS well populated |
| MEDIUM | Known mineral province, some public data, partial MRDS coverage, survey data behind portal |
| LOW | Remote area, minimal survey coverage, MRDS sparse, no downloadable geology |

---

## Step 6: When to Escalate

| Situation | Action |
|-----------|--------|
| Area name found, major survey exists, reports downloadable | Quick search sufficient — download and ingest |
| Multiple datasets found, need systematic download | Escalate to formal data ingestion pipeline |
| Portal access blocked, data behind authentication | Document as BLOCKED_BY_PORTAL, add to operator checklist |
| Area is remote with no survey data | Document as LOW coverage, note in zone metadata |
| Geology available but format is incompatible | Document format barrier, request operator conversion |

---

## Example: Kalgoorlie, Western Australia

- **Coordinates:** -30.75, 121.47
- **Reverse geocode:** Kalgoorlie-Boulder, Western Australia, Australia
- **Geological context:** Eastern Goldfields Superterrane, Yilgarn Craton (Archean)
- **Key search terms:**
  - "Kalgoorlie geology"
  - "Eastern Goldfields mineral deposits"
  - "GSWA Kalgoorlie"
  - "Yilgarn craton gold"
  - "Norseman-Wiluna greenstone belt"
- **Best sources:** GSWA (state), GA (national), OZMIN (deposits), NCI THREDDS (magnetics)
- **Coverage confidence:** HIGH — one of the most surveyed areas in the world
- **Key open data available:**
  - GA TMI magnetics via NCI THREDDS (operationalized in Phase 7)
  - OZMIN mineral occurrences (operationalized as training labels)
  - GSWA geology maps (portal — blocked for automated access, manual download possible)
  - GA gravity (GADDS portal — blocked for automated access)

---

## Example: Chuquicamata, Chile

- **Coordinates:** -22.32, -68.93
- **Reverse geocode:** Calama, Antofagasta Region, Chile
- **Geological context:** Central Andes Porphyry Copper Belt, Eocene-Miocene intrusions
- **Key search terms:**
  - "Chuquicamata geology"
  - "Atacama porphyry copper"
  - "SERNAGEOMIN Antofagasta geological map"
  - "Chile porphyry copper belt geophysics"
- **Best sources:** SERNAGEOMIN (Chilean survey), USGS copper assessment, MRDS
- **Coverage confidence:** HIGH — flagship porphyry copper district
- **Key open data available:**
  - MRDS deposits (operationalized as labels)
  - EMIT mineralogy (validated — Phases 6A-6E)
  - Landsat thermal (validated)
  - SERNAGEOMIN geology maps (manual download, not automated)

---

## Example: Zambian Copperbelt

- **Coordinates:** -12.81, 28.21
- **Reverse geocode:** Kitwe, Copperbelt Province, Zambia
- **Geological context:** Central African Copperbelt, Katangan Supergroup (Neoproterozoic)
- **Key search terms:**
  - "Zambian Copperbelt geology"
  - "Katangan Supergroup mineralization"
  - "GSZ Copperbelt geological map"
  - "Central African Copperbelt sediment hosted copper"
- **Best sources:** GSZ (Zambia survey), MRDS, academic literature (strong for this belt)
- **Coverage confidence:** MEDIUM — well-known district but GSZ data access is limited
- **Key open data available:**
  - MRDS deposits (operationalized)
  - Macrostrat (sparse — Katangan Supergroup partially mapped)
  - Academic literature via Google Scholar is the strongest open data source for this belt

---

## Example: Globe-Miami, Arizona

- **Coordinates:** 33.42, -110.87
- **Reverse geocode:** Globe, Gila County, Arizona, USA
- **Geological context:** Arizona Transition Zone, Laramide porphyry belt
- **Key search terms:**
  - "Globe-Miami mining district Arizona"
  - "Arizona porphyry copper geology"
  - "AZGS Gila County geological map"
  - "USGS Earth MRI Arizona"
- **Best sources:** USGS, AZGS, MRDS, Earth MRI (ScienceBase — partially accessible)
- **Coverage confidence:** HIGH — well-mapped US mining district
- **Key open data available:**
  - MRDS deposits (operationalized)
  - USGS geological maps (downloadable via NGMDB)
  - Macrostrat US coverage is good
  - Earth MRI: check ScienceBase for Arizona items

---

## Access Honesty Reminders

- If a portal returns HTML instead of data: it is BLOCKED_BY_PORTAL. Document it, do not retry automatically.
- If an API requires authentication you do not have: it is BLOCKED_BY_AUTH. Document it, do not invent a workaround.
- Macrostrat may return empty responses for some international areas — this is a data coverage gap, not a code error.
- MRDS search results vary by endpoint version — always validate counts against expected geology.
- Never use search term results as training labels — they are for human orientation only.
