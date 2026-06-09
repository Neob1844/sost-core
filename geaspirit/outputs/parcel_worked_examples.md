# GeaSpirit — Cadastral-Reference Worked Examples (open-data triage)

Honest S0/S1 geological triage starting from a single cadastral reference:
reference → coordinates → polygon → geology → geological heritage → mining context → report.
Open public data only. Never a guarantee of ore; the spectral/engine pass over each
polygon is the next step. Confidence bands are deliberately conservative.

---

## 0. Cabezo Negro — Spain (baseline, already published)
- **Parcel:** Cabezo Negro, Campos del Río, Murcia
- **Cadastral ref:** 30014A010002510000IM · 38.02893, −1.31265 · ~5.6 ha
- **Geology:** Barqueros volcanic complex — lamproite (ultrapotassic volcanic rock); surrounding basin gypsum, marls, evaporites.
- **Metals read:** No open metal evidence. Potential for gypsum, aggregates, volcanic building stone.
- **Constraint:** Similar Murcian volcanic hills catalogued as LIG/IELIG geosites — heritage could limit extraction.
- **Confidence:** LOW → MEDIUM-LOW.

---

## 1. Salsigne — France
- **Parcel:** Salsigne (Aude, Occitanie), Salsigne–Cabardès gold–arsenic district, southern Montagne Noire
- **Cadastral ref:** `11372000AE0103` (IGN/Etalab apicarto cadastre, INSEE 11372, section AE, n° 0103) — **API-verified**
- **Coords / area:** 43.3285 N, 2.3665 E · ~0.32 ha (contenance 3,150 m²)
- **Geology:** Lower-Cambrian schists, sandstones, dolomitic limestones (Hercynian Montagne Noire), cut by N–S faults; district Au–As mineralisation in quartz–sulphide bodies (arsenopyrite, pyrite, galena, chalcopyrite), driven by ~305 Ma Cabardès granite.
- **Metals read:** District-scale world-class Au–As–(Ag–Cu) (~120 t Au, ~400 kt As historically). Parcel-specific: no open occurrence/assay — favourable setting only.
- **Constraint:** INPG geosite LRO1005 (Salsigne open-pit); Natura 2000 adjacent (Gorges de la Clamoux FR9101451, Montagne Noire occidentale FR7300944); **legacy arsenic/heavy-metal contamination** — State-managed post-mine liability.
- **Confidence:** MEDIUM-LOW (ref/coords API-verified; regional geology well documented; no parcel-level assay).
- **Sources:** apicarto.ign.fr/api/cadastre/parcelle?code_insee=11372 · inpn.mnhn.fr/site/inpg/LRO1005 · fr.wikipedia.org/wiki/Mine_d'or_de_Salsigne · lithotheque.ac-montpellier.fr/mine-d-or-salsigne · inpn.mnhn.fr/site/natura2000/FR7300944

---

## 2. Cínovec — Czech Republic
- **Parcel:** Cínovec (cadastral area / k.ú.), municipality Dubí, okres Teplice, Ústecký kraj; eastern Krušné hory / Erzgebirge, Czech–German border
- **Cadastral ref:** cadastral area **Cínovec, code 617741** (ČÚZK-verified); sample ordinary parcel **22/1**, 33,868 m² (~3.39 ha) — *parcel number from an open ČÚZK-data aggregator, not re-pulled from the primary ČÚZK service*
- **Coords / area:** 50.7212, 13.7938 · ~3.39 ha (cited parcel)
- **Geology:** Cínovec (Zinnwald) granite cupola — late-Variscan, highly fractionated Li-F rare-metal granite of the Krušné hory/Erzgebirge batholith (Saxothuringian; Teplice caldera system); F/Li/Rb/Cs/Nb/Ta/Sn/W enriched. Greisen + flat quartz veins (cassiterite, wolframite, zinnwaldite) in the cupola at depth.
- **Metals read:** Plausibly Li (zinnwaldite), Sn (cassiterite), W (wolframite) + accessory Rb/Cs/Nb/Ta/U at depth across the cupola. Large but low-grade, at depth; no open parcel-level resource — proximity to cupola only.
- **Constraint:** Erzgebirge/Krušnohoří UNESCO Mining Region setting (Czech cores elsewhere); Natura 2000 Východní Krušnohoří (EVL + SPA); Cínovecké rašeliniště peatland reserve; active **EU-strategic lithium project** (Geomet / European Metals). CHKO Krušné hory proposed, not yet declared.
- **Confidence:** MEDIUM (geology/history/ku code well supported; parcel number aggregator-sourced; no parcel-level assay).
- **Sources:** whc.unesco.org/en/list/1478 · regiony.kurzy.cz/katastr/ku/617741 · pubs.geoscienceworld.org (Greisen-hosted Li, Erzgebirge) · cs.wikipedia.org/wiki/Cínovec_(Dubí) · geomet-cz.com / europeanmet.com

---

## 3. Norberg (Kärrgruvan / Bolagshagen) — Sweden
- **Parcel:** Bolagshagen residential blocks, Kärrgruvan, Norberg kommun; Bergslagen ore province
- **Cadastral ref:** **Kallmora 2:46, 2:48, 2:49** ("kvarteret Bolagshagen") — from Norberg municipal record/press; *exact polygon/area not pulled from Lantmäteriet's authenticated cadastre*
- **Coords / area:** ~60.096 N, 15.933 E (Kärrgruvan locality centroid) · area not openly published
- **Geology:** Bergslagen — ~1.90–1.88 Ga Palaeoproterozoic felsic metavolcanics ("leptite/hälleflinta") + dolomitic-calcitic marble + skarn; Norberg = carbonate/skarn-hosted iron (magnetite–hematite), historic grades ~43–62% Fe. Adjacent Kärrgruvan workings + Klackberg dolomite reserve confirm setting.
- **Metals read:** Plausibly skarn/banded iron oxides (Fe). No open evidence of base/precious metal under the parcel; documented output is iron only; mining ceased 20th century.
- **Constraint:** Occupied residential land (89 apartments, municipally owned) in a culturally protected historic mining landscape (Ekomuseum Bergslagen; Klackberg reserve 1.5 km W) — effectively non-prospectable in practice. No Natura 2000/geosite confirmed on the parcel.
- **Confidence:** MEDIUM-LOW (designation/locality/regional geology verified; parcel-level bedrock inferred from district map; area/polygon not openly published).
- **Sources:** en.wikipedia.org/wiki/Kärrgruvan · norberg.se (Kallmora 2:46/2:48/2:49 förvärv) · sv.wikipedia.org/wiki/Bolagshagen · mindat.org/loc-122548 · lansstyrelsen.se/.../klackberg · ekomuseum.se (Norbergs gruvmuseum)

---

### Method note
Layers processed per parcel (open data): cadastral resolution → coordinates/footprint →
bedrock geology (national survey) → geological heritage / protected areas (geosite inventories,
Natura 2000, reserves) → mining context (district history, nearby occurrences) → honest metals read
→ conservative confidence band. The proprietary spectral/fusion engine pass (S2+) is the documented next step.
