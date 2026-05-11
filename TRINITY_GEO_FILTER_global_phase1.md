# Trinity / Geo Discovery — AOI Filter `copper_gold_critical_minerals`

> **DRY-RUN geo filter.** Closed rules: coordinate validity, demo-AOI proximity, zero-commodity rejection, bbox-overlap deduplication, protected-area flag. Not a mineral reserve claim and not a deposit confirmation.

- **Schema**: `trinity-geo-candidate-filter/v0.1`
- **Commodity**: `copper_gold_critical_minerals`
- **Mode**: `offline-belts`
- **Generated (UTC)**: 2026-05-10T00:00:00+00:00
- **Summary**: accept=`90`, reject=`10`, flag=`0`

## Decisions (first 30)

| id | name | center | verdict | reasons | flags |
| --- | --- | --- | --- | --- | --- |
| `GEO-0001` | Yilgarn Craton (West Australia) tile S26.1 E123.9 | `-26.06, 123.90` | **accept** | — | — |
| `GEO-0002` | Central Asian Orogenic Belt (Kazakhstan / Mongolia) tile N47.5 E77.1 | `47.51, 77.07` | **accept** | — | — |
| `GEO-0003` | South Atlantic margin — Brazilian shield tile S12.5 W43.4 | `-12.46, -43.36` | **accept** | — | — |
| `GEO-0004` | Pacific Rim of Fire — Japan / Kurils tile N32.5 E144.2 | `32.53, 144.16` | **accept** | — | — |
| `GEO-0005` | Carlin Trend (Nevada, USA) tile N40.9 W116.8 | `40.92, -116.77` | **accept** | — | — |
| `GEO-0006` | Tethyan Belt (Iran / Turkey / Balkans) tile N40.8 E44.5 | `40.82, 44.50` | **accept** | — | — |
| `GEO-0007` | African Copperbelt (Zambia / DRC) tile S12.4 E28.0 | `-12.37, 27.96` | **reject** | near_known_demo_aoi:'Zambia Copperbelt (reserved for future demo)' | — |
| `GEO-0008` | Lachlan Fold Belt (East Australia) tile S33.1 E145.5 | `-33.08, 145.55` | **accept** | — | — |
| `GEO-0009` | Bushveld Complex (South Africa) tile S25.3 E29.5 | `-25.25, 29.53` | **accept** | — | — |
| `GEO-0010` | Skellefte district (Sweden) tile N64.6 E17.6 | `64.57, 17.63` | **accept** | — | — |
| `GEO-0011` | Caribbean nickel belt tile N19.4 W69.1 | `19.40, -69.11` | **accept** | — | — |
| `GEO-0012` | Mesoamerica volcanic arc tile N9.2 W88.1 | `9.16, -88.09` | **accept** | — | — |
| `GEO-0013` | Fennoscandian Shield (Finland / Norway) tile N64.6 E28.4 | `64.60, 28.44` | **accept** | — | — |
| `GEO-0014` | Pacific Rim of Fire — Indonesia / Philippines tile N2.3 E126.7 | `2.30, 126.67` | **accept** | — | — |
| `GEO-0015` | Skellefte district (Sweden) tile N64.9 E20.9 | `64.88, 20.89` | **accept** | — | — |
| `GEO-0016` | Greenland east coast (rift margins) tile N66.2 W27.3 | `66.21, -27.34` | **accept** | — | — |
| `GEO-0017` | Mesoamerica volcanic arc tile N11.5 W93.3 | `11.53, -93.28` | **accept** | — | — |
| `GEO-0018` | Yangtze Craton (China) tile N26.0 E105.1 | `25.98, 105.08` | **accept** | — | — |
| `GEO-0019` | Superior Craton (Canada) tile N51.2 W90.8 | `51.16, -90.77` | **accept** | — | — |
| `GEO-0020` | Skellefte district (Sweden) tile N65.4 E18.2 | `65.40, 18.22` | **accept** | — | — |
| `GEO-0021` | Sukhoi Log belt (Russia, Lena River) tile N61.9 E112.4 | `61.94, 112.40` | **accept** | — | — |
| `GEO-0022` | Iberian Pyrite Belt (Portugal / Spain) tile N37.3 W6.6 | `37.30, -6.57` | **accept** | — | — |
| `GEO-0023` | Andean belt tile S0.6 W76.2 | `-0.64, -76.18` | **accept** | — | — |
| `GEO-0024` | Pacific Rim of Fire — Japan / Kurils tile N30.9 E148.3 | `30.86, 148.30` | **accept** | — | — |
| `GEO-0025` | Yangtze Craton (China) tile N30.6 E112.6 | `30.64, 112.55` | **accept** | — | — |
| `GEO-0026` | South Atlantic margin — Brazilian shield tile S12.2 W50.3 | `-12.19, -50.35` | **accept** | — | — |
| `GEO-0027` | Andean belt tile S15.7 W70.0 | `-15.70, -69.96` | **accept** | — | — |
| `GEO-0028` | Birimian belt (West Africa) tile N7.4 W1.7 | `7.42, -1.74` | **accept** | — | — |
| `GEO-0029` | Caribbean nickel belt tile N20.1 W73.8 | `20.10, -73.83` | **accept** | — | — |
| `GEO-0030` | South Atlantic margin — Brazilian shield tile S12.1 W50.1 | `-12.11, -50.09` | **reject** | overlap_with_previously_accepted:fraction=0.69 | — |

_(70 more decisions in the JSON.)_
