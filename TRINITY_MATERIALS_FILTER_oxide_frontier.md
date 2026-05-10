# Trinity / Materials Discovery — Chemistry Filter `oxide_frontier`

> **DRY-RUN chemistry filter.** Closed rules: charge balance, element whitelist, toxicity gate, criticality flag, known-demo exclusion. Not a synthesis recipe and not a performance claim.

- **Schema**: `trinity-materials-candidate-filter/v0.1`
- **Family**: `oxide_frontier`
- **Generated (UTC)**: 2026-05-10T00:00:00+00:00
- **Summary**: accept=`8`, reject=`42`, flag=`0`

## Decisions

| id | formula | family | verdict | reasons | flags |
| --- | --- | --- | --- | --- | --- |
| `MX-0001` | `NiAl2O4` | `spinel` | **accept** | — | — |
| `MX-0002` | `CoV2O4` | `spinel` | **reject** | charge_balance_nonzero:expected_0_got_4 | — |
| `MX-0003` | `FeMn2O4` | `spinel` | **reject** | charge_balance_nonzero:expected_0_got_-2 | — |
| `MX-0004` | `ZnMn2O4` | `spinel` | **reject** | charge_balance_nonzero:expected_0_got_-2 | — |
| `MX-0005` | `CuCr2O4` | `spinel` | **accept** | — | — |
| `MX-0006` | `NiMn2O4` | `spinel` | **reject** | charge_balance_nonzero:expected_0_got_-2 | — |
| `MX-0007` | `NiMn2O4` | `spinel` | **reject** | charge_balance_nonzero:expected_0_got_-2 | — |
| `MX-0008` | `MnAl2O4` | `spinel` | **accept** | — | — |
| `MX-0009` | `ZnCr2O4` | `spinel` | **accept** | — | — |
| `MX-0010` | `NiFe2O4` | `spinel` | **accept** | — | — |
| `MX-0011` | `NiV2O4` | `spinel` | **reject** | charge_balance_nonzero:expected_0_got_4 | — |
| `MX-0012` | `MgV2O4` | `spinel` | **reject** | charge_balance_nonzero:expected_0_got_4 | — |
| `MX-0013` | `FeGa2O4` | `spinel` | **accept** | — | — |
| `MX-0014` | `NiV2O4` | `spinel` | **reject** | charge_balance_nonzero:expected_0_got_4 | — |
| `MX-0015` | `SrNiO3` | `perovskite` | **reject** | charge_balance_nonzero:expected_0_got_-2 | — |
| `MX-0016` | `SrTiO3` | `perovskite` | **accept** | — | — |
| `MX-0017` | `CaMnO3` | `perovskite` | **reject** | charge_balance_nonzero:expected_0_got_-2 | — |
| `MX-0018` | `YCoO3` | `perovskite` | **reject** | charge_balance_nonzero:expected_0_got_-1 | — |
| `MX-0019` | `LaCoO3` | `perovskite` | **reject** | charge_balance_nonzero:expected_0_got_-1 | — |
| `MX-0020` | `NdTiO3` | `perovskite` | **reject** | charge_balance_nonzero:expected_0_got_1 | — |
| `MX-0021` | `CaZrO3` | `perovskite` | **accept** | — | — |
| `MX-0022` | `LaTiO3` | `perovskite` | **reject** | charge_balance_nonzero:expected_0_got_1 | — |
| `MX-0023` | `BaNiO3` | `perovskite` | **reject** | charge_balance_nonzero:expected_0_got_-2 | — |
| `MX-0024` | `YTaO3` | `perovskite` | **reject** | charge_balance_nonzero:expected_0_got_2 | — |
| `MX-0025` | `NdMnO3` | `perovskite` | **reject** | charge_balance_nonzero:expected_0_got_-1 | — |
| `MX-0026` | `NdTaO3` | `perovskite` | **reject** | charge_balance_nonzero:expected_0_got_2 | — |
| `MX-0027` | `LaCoO3` | `perovskite` | **reject** | charge_balance_nonzero:expected_0_got_-1 | — |
| `MX-0028` | `PrNiO3` | `perovskite` | **reject** | charge_balance_nonzero:expected_0_got_-1 | — |
| `MX-0029` | `SrNiO3` | `perovskite` | **reject** | charge_balance_nonzero:expected_0_got_-2 | — |
| `MX-0030` | `BaMnO3` | `perovskite` | **reject** | charge_balance_nonzero:expected_0_got_-2 | — |
| `MX-0031` | `LaHfO3` | `perovskite` | **reject** | charge_balance_nonzero:expected_0_got_1 | — |
| `MX-0032` | `CaMnO3` | `perovskite` | **reject** | charge_balance_nonzero:expected_0_got_-2 | — |
| `MX-0033` | `BaNbO3` | `perovskite` | **reject** | charge_balance_nonzero:expected_0_got_1 | — |
| `MX-0034` | `NdMnO3` | `perovskite` | **reject** | charge_balance_nonzero:expected_0_got_-1 | — |
| `MX-0035` | `KNiO2` | `layered_oxide` | **reject** | charge_balance_nonzero:expected_0_got_-1 | — |
| `MX-0036` | `NaMnO2` | `layered_oxide` | **reject** | charge_balance_nonzero:expected_0_got_-1 | — |
| `MX-0037` | `NaCoO2` | `layered_oxide` | **reject** | charge_balance_nonzero:expected_0_got_-1 | — |
| `MX-0038` | `LiTiO2` | `layered_oxide` | **reject** | charge_balance_nonzero:expected_0_got_1 | — |
| `MX-0039` | `NaVO2` | `layered_oxide` | **reject** | charge_balance_nonzero:expected_0_got_2 | — |
| `MX-0040` | `KTiO2` | `layered_oxide` | **reject** | charge_balance_nonzero:expected_0_got_1 | — |
| `MX-0041` | `LiTiO2` | `layered_oxide` | **reject** | charge_balance_nonzero:expected_0_got_1 | — |
| `MX-0042` | `KCoO2` | `layered_oxide` | **reject** | charge_balance_nonzero:expected_0_got_-1 | — |
| `MX-0043` | `LiCoO2` | `layered_oxide` | **reject** | charge_balance_nonzero:expected_0_got_-1 | — |
| `MX-0044` | `LiTiO2` | `layered_oxide` | **reject** | charge_balance_nonzero:expected_0_got_1 | — |
| `MX-0045` | `ZrCr2O7` | `oxide_interface` | **reject** | charge_balance_nonzero:expected_0_got_-4 | — |
| `MX-0046` | `ZrCr2O7` | `oxide_interface` | **reject** | charge_balance_nonzero:expected_0_got_-4 | — |
| `MX-0047` | `SnCr2O7` | `oxide_interface` | **reject** | charge_balance_nonzero:expected_0_got_-4 | — |
| `MX-0048` | `CeAl2O7` | `oxide_interface` | **reject** | charge_balance_nonzero:expected_0_got_-4 | — |
| `MX-0049` | `CeCr2O7` | `oxide_interface` | **reject** | charge_balance_nonzero:expected_0_got_-4 | — |
| `MX-0050` | `ZrAl2O7` | `oxide_interface` | **reject** | charge_balance_nonzero:expected_0_got_-4 | — |
