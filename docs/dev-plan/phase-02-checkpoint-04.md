# Phase 2 — checkpoint 04: deep zoom and viewport paging

- Status: Verified checkpoint; Phase 2 remains In progress
- Date: 2026-09-25

## Problem found on real data

The first pilot import stored only a deterministic per-layer sample: 5,122 objects for Песчаный and 9,154 for Куликовская. The browser then loaded one full-extent collection and merely enlarged it. Deep zoom could therefore expose neither missing objects nor CAD detail. Full drawing extents also contain remote sheet and service fragments, making the street itself small at 100% fit.

## Changes

- unlimited pilot import now means every supported primitive, not the old per-layer cap;
- mutable-model refresh explicitly deletes child geometries before parent objects, satisfying immutability guards during repeat import;
- the API uses the PostGIS geometry GiST index for every viewport bbox;
- the browser debounces viewport changes and reloads the visible bbox after pan, zoom or bearing change;
- LOD is selected from the current zoom;
- overview requests return at most 6,000 simplified objects; detailed LOD returns at most 12,000;
- result ordering no longer exhausts the limit on alphabetically early source layers;
- maximum zoom increased from 4,000% to 10,000,000%;
- wheel response and zoom buttons were made stronger;
- point markers now retain approximately constant screen size instead of growing with the original document extent;
- the control displays the number of objects currently loaded for the viewport.

## Full import result

| Project | Traversed primitives | Stored supported geometries | Previous sample |
|---|---:|---:|---:|
| Песчаный переулок | 99,418 | 87,728 | 5,122 |
| Куликовская улица | 143,742 | 135,765 | 9,154 |

The database now contains 223,493 pilot geometries. Unsupported primitives remain reported in model import statistics.

## Browser evidence

Repeated wheel events were dispatched over the dense street cluster. Each settled viewport caused a new API bbox request:

| Zoom | Visible viewBox size | Returned objects |
|---:|---:|---:|
| 332% | about 1,009 × 629 | 12,000 |
| 1,102% | about 304 × 189 | 12,000 |
| 3,660% | about 92 × 57 | 4,109 |
| 12,151% | about 28 × 17 | 1,467 |
| 40,343% | about 8.3 × 5.2 | 113 |

This proves that deep zoom retrieves progressively local PostGIS content rather than scaling the original overview sample.

## Coordinate caveat

The pilot coordinate spaces are recorded as metre-based `cad_local`, but their CRS status remains `candidate`. Distances should be treated as CAD units compatible with metres until a control-point or declared-CRS verification is accepted.
