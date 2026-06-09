# GeaSpirit Old — Spectral / Multi-Satellite Engine Pass (4 worked-example parcels)

This documents the **actual engine run** over the four worked-example parcels
(Cabezo Negro · Salsigne · Cínovec · Norberg). It is the S0/S1 → S2 remote pass
that the public methodology refers to as "the next step". **It is inference from
surface signals over open satellite data — never a confirmed deposit.** Ground
truth (sampling/drilling) is always the only confirmation.

## Satellites & layers actually used (all open data)
- **Sentinel-2 (COPERNICUS/S2_SR_HARMONIZED)** — multispectral; mineral indices:
  `iron_oxide` (B4/B2), `clay_hydroxyl` (B11/B12), `ferrous_iron` (B11/B8A),
  `laterite` (B4/B3), `ndvi`.
- **Sentinel-1 (COPERNICUS/S1_GRD)** — C-band SAR: `VV`, `VH`, `VV/VH`, texture.
- **Copernicus DEM GLO-30** — `elevation`, `slope`, `tpi`, `ruggedness`.
- **Landsat-8 (LC08/C02/T1_L2)** — thermal: `LST_median`, `LST_p90`, `LST_zscore`.
- Composite window 2023-06-01 → 2024-09-30, ≤15% cloud, **30 m**, 16 bands.
- Stacks built (px / valid): Cabezo 425×336 (100%), Salsigne 461×336 (99.7%),
  Cínovec 529×335 (100%), Norberg 672×335 (100%).

Scoring here is the **heuristic proxy score** (no trained model in this pass).
Values = surface mineral indicators, not deposits. "pctile" = the parcel
centroid's percentile within its own AOI for that index.

---

## 🇪🇸 Cabezo Negro (38.02893, −1.31265)
- **AOI scan:** HIGH (>0.7) 2.3 km² · MODERATE 30.4 km² · LOW 95.1 km². Top score 0.72.
- **At the parcel centroid:** clay_hydroxyl **1.30 (82nd pctile)**, ferrous_iron **1.28 (81st)**,
  iron_oxide 1.48 (29th — *low*), laterite 1.16 (35th), NDVI 0.11 (sparse veg), ruggedness 15.3 (95th).
- **Engine read:** a **clay-hydroxyl + ferrous** surface signature, **weak iron-oxide** — coherent
  with a lamproite/volcanic + evaporite (gypsum/marl) setting, **not** a metallic gossan. The engine
  does **not** light up for base/precious metals here. Matches the honest geological read (gypsum/
  aggregates/volcanic stone; no metals). **Evidence level: S1.**

## 🇫🇷 Salsigne (43.3285, 2.3665)
- **AOI scan:** HIGH 2.0 km² · MODERATE 32.1 km² · LOW 104.5 km². Top score 0.70.
- **At the parcel centroid:** iron_oxide **1.75 (86th pctile)**, ferrous_iron **1.18 (91st)**,
  laterite 1.16 (79th), clay_hydroxyl 1.47 (16th), NDVI 0.40 (lower veg than surroundings).
- **Engine read:** the **strongest spectral signature of the four** — a co-located **iron-oxide +
  ferrous-iron (gossan-type oxidation)** anomaly with suppressed vegetation, exactly what one expects
  over an oxidising sulphide system in a world-class **Au–As–(Ag–Cu)** district. The satellites
  independently corroborate the favourable geology — but this is still a surface indicator, not ore,
  and the overriding real-world constraint remains the legacy arsenic contamination. **Evidence level: S1
  (favourable; the strongest of the set).**

## 🇨🇿 Cínovec (50.7212, 13.7938)
- **AOI scan:** HIGH 3.0 km² · MODERATE 18.1 km² · LOW 137.4 km². Top score 0.75 (highest single target of the four).
- **At the parcel centroid:** clay_hydroxyl **2.27 (75th pctile)**, iron_oxide 1.22 (56th),
  ferrous_iron 0.46 (24th — low), NDVI **0.84 (heavily vegetated)**, elevation 870 m (95th, plateau).
- **Engine read:** a **clay-hydroxyl alteration** signature consistent with greisen over the Li-Sn-W
  granite cupola, but the surface is **densely vegetated/forested**, which caps how far a spectral
  read can go — and the economic ore is **at depth** regardless. Spectral surface evidence is
  suggestive but limited; the lithium case rests on the documented cupola, not on this pass.
  **Evidence level: S1 (vegetation-limited).**

## 🇸🇪 Norberg / Bergslagen (60.096, 15.933)
- **AOI scan:** HIGH 1.3 km² · MODERATE 20.0 km² · LOW 180.1 km². Top score 0.74.
- **At the parcel centroid:** ferrous_iron **0.80 (90th pctile)**, laterite **0.96 (90th)**,
  iron_oxide 1.21 (58th), clay_hydroxyl 1.44 (5th — low), NDVI 0.47 (parcel less vegetated than AOI).
- **Engine read:** a **ferrous-iron / iron-oxide** surface signature with **low clay**, coherent with
  the dolomite-skarn **iron (magnetite–hematite)** field — i.e. the engine "sees" iron, not base/
  precious metals, matching the honest read ("iron only"). Note the parcel itself is occupied
  residential ground, so this is academic. **Evidence level: S1.**

---

## Honest conclusion
All four parcels reach **S1** on this pass (surface signal + geology), **not S2** — S2 requires real
public **geophysics/geochemistry** sampled at the asset, which none of these four have in open data.
The satellites' independent read is **coherent with the documented geology in every case**: Salsigne
shows the expected gossan-type Fe-oxide/ferrous anomaly (strongest), Norberg shows iron, Cínovec shows
greisen-type clay (vegetation-limited), and Cabezo Negro shows volcanic/evaporitic clay-ferrous with no
metallic gossan. **No deposit is claimed anywhere.** The specific feature engineering, weighting and
calibration of the engine remain proprietary; what is documented here is the open-satellite read and
its honest interpretation.
