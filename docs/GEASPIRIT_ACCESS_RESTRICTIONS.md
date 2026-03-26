# GeaSpirit — Access Restrictions Audit

**Date:** 2026-03-26

| # | Resource | Expected Location | Status | Blocker | Unblock Action |
|---|----------|------------------|--------|---------|---------------|
| 1 | GA Bouguer gravity grid | manual_drop/gravity/ | BLOCKED_BY_PORTAL | WCS/REST return HTML portal page, not data | Operator downloads from ecat.ga.gov.au or GADDS portal |
| 2 | Peru EMIT L2A granules | manual_drop/peru_emit/ | BLOCKED_BY_DOWNLOAD | 2 granules truncated (54%, 41%). Download timeouts. | Operator re-downloads from search.earthdata.nasa.gov |
| 3 | Arizona Earth MRI geophysics | manual_drop/arizona_earthmri/ | BLOCKED_BY_DOWNLOAD | Data found on ScienceBase but not downloaded | Operator downloads from sciencebase.gov/catalog/item/67fe127ed4be0201e1518b12 |
| 4 | MINDAT API key | ~/.mindat_key | BLOCKED_BY_AUTH | No API key file exists | Register free at api.mindat.org, save key to ~/.mindat_key |
| 5 | EMAG2v3 global magnetics | — | BLOCKED_BY_URL | NOAA URL returns 404 (file moved) | Find updated download URL at ngdc.noaa.gov |
| 6 | WGM2012 Bouguer gravity | — | BLOCKED_BY_URL | BGI URL returns 301 redirect | Find updated URL at bgi.obs-mip.fr |
| 7 | GSWA detailed AEM | data/aem/ | BLOCKED_BY_PORTAL | Needs manual check at DMIRS portal | Check geodownloads.dmirs.wa.gov.au for Kalgoorlie coverage |
| 8 | ECOSTRESS Collection 2 | — | NOT_YET_DOWNLOADED | Path confirmed via GEE/earthaccess, not downloaded | Use earthaccess Python library to download |
| 9 | Prithvi-EO-2.0 weights | — | NOT_YET_DOWNLOADED | Available on HuggingFace (1.34 GB) | pip install, download from ibm-nasa-geospatial/Prithvi-EO-2.0-300M-TL |
| 10 | GEE Python API | — | NOT_CONFIGURED | Needs Google Cloud project | earthengine-api + project registration |
| 11 | Macrostrat geology (unbiased) | — | PARTIALLY_WORKING | API works but experiment had bias | Re-run querying BOTH deposits and background |
| 12 | GA national gravity (THREDDS) | — | BLOCKED_BY_CATALOG | THREDDS catalog doesn't list gravity | Try alternative NCI paths or ecat.ga.gov.au |
