# DWG inventory

Input: `dataset`

## Summary

| Metric | Files |
|---|---:|
| Total DWG | 1009 |
| Already AC1032 / target DXF 2018 | 495 |
| Earlier recognised DWG candidates | 324 |
| Unknown AC signatures; converter probe required | 0 |
| Not recognised as DWG | 190 |

## Version distribution

| Signature | AutoCAD release | Conversion readiness | Files |
|---|---|---|---:|
| AC1015 | R2000 | candidate_same_or_newer_dxf | 148 |
| AC1018 | R2004 | candidate_same_or_newer_dxf | 12 |
| AC1021 | R2007 | candidate_same_or_newer_dxf | 18 |
| AC1024 | R2010 | candidate_same_or_newer_dxf | 87 |
| AC1027 | R2013-R2017 | candidate_same_or_newer_dxf | 59 |
| AC1032 | R2018-R2025 | target_ac1032 | 495 |
| n/a | not_recognized_as_dwg | rejected_before_conversion | 190 |

## Interpretation

`target_ac1032` and `candidate_same_or_newer_dxf` mean only that the six-byte file header is a known DWG release for the intended conversion path. They are **not** a no-loss guarantee. A conversion gate must still check entities, layers, blocks, XREF, proxy/custom objects, fonts, extents and visual output.

`converter_probe_required` means the header is an `AC*` value outside this script's public mapping. It must be tested with the approved converter before it enters the planning pipeline.

## Next command after installing an approved converter

Run the converter on a copy of a small pilot directory, retain the original DWG, target DXF 2018/AC1032, and write its log alongside this inventory. Do not batch-convert all input files until the pilot conversion gate passes.
