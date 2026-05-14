# Karl Hommik design drainage formulas — implementation reference

This document mirrors the formulas implemented in
`backend/services/hommik.py`, with their PDF source, the rationale for
each constant, and the assumptions HydroCalc bakes in. **No constant in
this file may differ from the constants in code.** If you change either,
change both, and bump `formula_revision` in `backend/config.py`.

## Source

All formulas are taken from `TÜ_projekt_protsess.pdf` page 3–5
(customer-provided, retrieved 2026-05-12). They originate from Karl
Hommik's empirical equations for Estonian river basins, calibrated for
catchments above 100 km² and for use designing hydrotechnical
infrastructure.

## Symbol map

| PDF symbol     | Code identifier               | Units            |
|----------------|-------------------------------|------------------|
| `q̄`           | `q_bar`                       | l/(s·km²)        |
| `q̄_k`         | `q_bar_k`                     | l/(s·km²)        |
| `Δq`           | `delta_q`                     | l/(s·km²)        |
| `q_95%`        | `q95`                         | l/(s·km²)        |
| `k_95%`        | `k95`                         | dimensionless    |
| `r_s`          | `r_s`                         | dimensionless    |
| `r`            | `r`                           | dimensionless    |
| `q_veg.max.p%` | `q_veg_max`                   | l/(s·km²)        |
| `q_kev.maks.p%`| `q_kev_max`                   | l/(s·km²)        |
| `Q_%`          | `Q` (`Q_from_modulus`)        | l/s              |
| `A`            | `A_km2`                       | km²              |
| `p`            | `p_percent`                   | %                |
| `A_ms`, `A_r`, `A_km`, `B`, `C` | same           | % of catchment   |
| `a`            | `a_wet_mineral_plus_akm`      | % of catchment   |
| `maaparandus`  | `maaparandus`                 | % of catchment   |

## Formulas

### (1.1) Annual drainage norm

```
q̄ = q̄_k + Δq
```

`q̄_k` is read from the official Maa-amet cartogram of annual climatic
drainage norm. Until that raster is provided, HydroCalc uses a
placeholder constant (7.0 l/(s·km²) — typical Estonian average), and
every result carries `q_bar_k_source = "placeholder"`. **Placeholder
results are not legally defensible.**

### (1.2) Local correction Δq

```
Δq = 0.020·a + 0.30·q_95% − 1.00
```

The `a` parameter is defined in the PDF as "võsastunud ja metsastunud
liigniiske mineraalmaa ja kuivendatud madalsoo osakaal" — the share of
brushed/forested **wet** mineral land plus drained low-bog. ETAK does
not tag "liigniiske" directly. HydroCalc derives `a` as:

```
a = (B ∩ A_ms, expressed as % of catchment) + A_km
```

i.e. the spatial intersection of ETAK 305 (wooded mineral) and ETAK 306
(märgala) gives the wet-mineral B component, plus the A_km share. The
mapping is implemented in `backend/services/landcover.py` (Phase 3) and
documented in every PDF report as an explicit assumption.

### (1.3) Autumn peak modulus

```
q_veg.max.p% = q̄ · [ (26 − 11.5·log10(p+1)) / (A+1)^0.11 ]^(1 − k_95% − r_s)
```

### (1.4) Daily-mean modular coefficient

```
k_95% = q_95% / q̄
```

### (1.5) Autumn peak-flow parameter

```
r_s = 0.005·(A_ms + A_r − 0.2·A_km − 0.1·B − 0.6·C) − 0.02
```

### (1.6) Spring peak modulus

```
q_kev.maks.p% = q̄ · [ (112 − 52·log10(p+1)) / (A+1)^0.14 ]^(1 − k_95% − r)
```

### (1.7) Spring peak-flow parameter

```
r = 0.004·[A_ms + 0.4·(A_r + A_km) + B + 0.2·C] − 0.20
```

### (1.8) Flow rate from modulus

```
Q_% = q_% · A    (l/s, with q in l/(s·km²) and A in km²)
```

Divide by 1000 for m³/s.

## Constraints

* **Area floor (PDF page 5).** If `A < 100 km²`, the formulas are
  evaluated with `A := 100 km²` and `p := 10 %`. The Hommik formulas are
  not calibrated below 100 km². HydroCalc flags the result with
  `area_floored_to_100km2: true` so the engineer can see the
  substitution in the report.

## Assumptions and known risks

1. **Logarithm convention.** The PDF writes `log`. The legacy code uses
   `log10`, which is the Estonian/Soviet empirical convention. HydroCalc
   follows `log10`. If the customer expects `ln`, change the constants
   in `hommik.py:q_veg_max` and `q_kev_max`, and bump
   `formula_revision`.

2. **Wet-mineral derivation.** The `a` parameter mapping (above) is our
   best interpretation of "võsastunud ja metsastunud liigniiske
   mineraalmaa". Confirm with the customer if a different source defines
   "liigniiske" more precisely (e.g. soil-map intersection).

3. **q̄_k placeholder.** Until the cartogram raster lands, every
   calculation that runs through HydroCalc is non-defensible. The PDF
   footer flags this; the React UI surfaces a banner.

4. **Spring > autumn check.** A sanity test asserts `q_kev_max >
   q_veg_max` for the worked example. This is not a strict scientific
   guarantee but is true for the vast majority of Estonian catchments;
   if a future regression flips the inequality, investigate.

## Worked example

| Parameter           | Value                                                |
|---------------------|------------------------------------------------------|
| A                   | 100 km² (boundary case)                              |
| p                   | 10 %                                                 |
| q̄_k                | 7.0 l/(s·km²)                                        |
| q_95%               | 2.0 l/(s·km²)                                        |
| A_ms, A_r, A_km, B, C | 10, 5, 15, 30, 40 % (sum = 100)                    |
| a                   | 20 %                                                 |

Computed (by hand and by HydroCalc, identically to 4 sig. fig.):

| Step                  | Value                                              |
|-----------------------|----------------------------------------------------|
| Δq                    | 0.000 l/(s·km²)                                    |
| q̄                    | 7.000 l/(s·km²)                                    |
| k_95%                 | 0.2857                                             |
| r_s                   | −0.095                                             |
| r                     | 0.024                                              |
| q_veg.max             | 39.31 l/(s·km²)                                    |
| q_kev.maks            | 73.74 l/(s·km²)                                    |
| Q_veg                 | 3.931 m³/s                                         |
| Q_kev                 | 7.374 m³/s                                         |

The test in `tests/test_hommik.py::TestComputeWorkedExample` pins these
values to four significant figures.
