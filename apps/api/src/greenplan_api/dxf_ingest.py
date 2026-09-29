from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
import math
import re
from typing import Any, Iterable, Iterator, Sequence, TypeVar

from ezdxf.entities import DXFEntity


@dataclass(frozen=True)
class LayerClassification:
    layer_id: str
    class_code: str
    semantic_status: str
    confidence: float
    reason: str


@dataclass(frozen=True)
class Primitive:
    entity: DXFEntity
    effective_layer: str
    source_handle: str | None


def layer_key(name: str) -> str:
    normalized = re.sub(r"\s+", " ", name.strip().casefold())
    return f"cad-{sha1(normalized.encode('utf-8')).hexdigest()[:12]}"


def classify_layer(name: str) -> LayerClassification:
    value = name.casefold().replace("ё", "е")
    rules: list[tuple[tuple[str, ...], str, float, str]] = [
        (("границ работ", "граница работ"), "territory.work_boundary", 0.94, "work boundary"),
        (("треугольник видим", "зона видим"), "territory.visibility_zone", 0.94, "visibility zone"),
        (("техническая зона метро",), "territory.metro_technical_zone", 0.96, "metro technical zone"),
        (("санитарно-защит", "сзз"), "territory.sanitary_protection_zone", 0.94, "sanitary protection zone"),
        (("охранная зона",), "territory.utility_protection_zone", 0.86, "utility protection zone"),
        (("водопровод",), "utility.water.pipeline", 0.94, "water pipeline"),
        (("дренаж", "водосток", "ливнев"), "utility.drainage.pipeline", 0.92, "drainage pipeline"),
        (("канализац",), "utility.sewer.pipeline", 0.94, "sewer pipeline"),
        (("теплосет", "тепловая сет", "тепловые сет", "теплопровод", "теплотрас"), "utility.heat.pipeline", 0.94, "heat network"),
        (("кабель связи", "мгтс", "телеком", "связи"), "utility.telecom.cable", 0.91, "telecom cable"),
        (("вл ", "воздушная лини", "лэп"), "utility.power.overhead", 0.91, "overhead power line"),
        (("кабель электр", "электрос", "освещен", "заземлен"), "utility.power.cable", 0.90, "power cable"),
        (("газопровод", "газоснаб"), "utility.gas.pipeline", 0.94, "gas pipeline"),
        (("подпорн",), "structure.retaining_wall", 0.94, "retaining wall"),
        (("наружная стен", "стена здан"), "structure.wall.external", 0.92, "external building wall"),
        (("опора", "мачт"), "structure.support", 0.84, "support or mast"),
        (("здан", "строен", "сооруж"), "structure.building", 0.80, "building"),
        (("откос", "подошва откоса", "бровка откоса", "бровка террас"), "terrain.slope_toe", 0.94, "slope or terrace toe"),
        (("край трамва", "трамвайн"), "transport.tram.track_edge", 0.92, "tram track edge"),
        (("край тротуар", "край дорожк", "тротуар"), "transport.pedestrian.path_edge", 0.88, "pedestrian path edge"),
        (("велодорож", "велосипедн"), "transport.cycleway.edge", 0.90, "cycleway edge"),
        (("борт", "бордюр"), "transport.road.curb", 0.87, "road curb"),
        (("край проезж", "кромка проезж", "обочин"), "transport.road.edge", 0.90, "road edge"),
        (("проезж", "дорог", "проезд"), "transport.road.carriageway", 0.78, "carriageway"),
        (("канава", "кювет"), "transport.ditch.edge", 0.88, "ditch edge"),
        (("кустар",), "vegetation.shrub", 0.82, "shrub"),
        (("дерев",), "vegetation.tree", 0.82, "tree"),
        (("газон", "трава", "травянист"), "vegetation.grass", 0.80, "grass vegetation"),
        (("дендр", "растени", "зелены", "озелен"), "vegetation.mixed", 0.72, "mixed vegetation"),
        (("рельеф", "горизонтал", "отметк"), "terrain", 0.72, "terrain"),
    ]
    for needles, class_code, confidence, reason in rules:
        if any(needle in value for needle in needles):
            return LayerClassification(
                layer_id=layer_key(name), class_code=class_code,
                semantic_status="inferred", confidence=confidence, reason=reason,
            )
    return LayerClassification(
        layer_id=layer_key(name), class_code="unknown.constraint",
        semantic_status="needs_review", confidence=0.25,
        reason="no deterministic layer-name rule matched",
    )


def iter_primitives(entities: Iterable[DXFEntity], max_depth: int = 16) -> Iterator[Primitive]:
    def visit(entity: DXFEntity, inherited_layer: str | None, source_handle: str | None, depth: int):
        raw_layer = str(entity.dxf.get("layer", "0"))
        effective_layer = inherited_layer if raw_layer == "0" and inherited_layer else raw_layer
        handle = source_handle or entity.dxf.get("handle")
        if entity.dxftype() == "INSERT" and depth < max_depth:
            try:
                children = entity.virtual_entities()
                for child in children:
                    yield from visit(child, effective_layer, handle, depth + 1)
            except Exception:
                return
            return
        yield Primitive(entity=entity, effective_layer=effective_layer, source_handle=handle)

    for item in entities:
        yield from visit(item, None, None, 0)


def _xy(point: Any) -> list[float]:
    return [float(point[0]), float(point[1])]


def _finite(points: Sequence[Sequence[float]]) -> bool:
    return bool(points) and all(math.isfinite(value) for point in points for value in point[:2])


def _line(points: list[list[float]]) -> dict[str, Any] | None:
    if len(points) < 2 or not _finite(points):
        return None
    return {"type": "LineString", "coordinates": points}


def _polygon(points: list[list[float]]) -> dict[str, Any] | None:
    if len(points) < 3 or not _finite(points):
        return None
    if points[0] != points[-1]:
        points.append(points[0].copy())
    return {"type": "Polygon", "coordinates": [points]}


def entity_to_geojson(entity: DXFEntity) -> dict[str, Any] | None:
    kind = entity.dxftype()
    try:
        if kind == "LINE":
            return _line([_xy(entity.dxf.start), _xy(entity.dxf.end)])
        if kind == "LWPOLYLINE":
            points = [[float(x), float(y)] for x, y in entity.get_points("xy")]
            return _polygon(points) if entity.closed else _line(points)
        if kind == "POLYLINE":
            points = [_xy(vertex.dxf.location) for vertex in entity.vertices]
            return _polygon(points) if entity.is_closed else _line(points)
        if kind == "CIRCLE":
            center = entity.dxf.center
            radius = float(entity.dxf.radius)
            points = [
                [float(center.x + radius * math.cos(angle)), float(center.y + radius * math.sin(angle))]
                for angle in (index * 2 * math.pi / 24 for index in range(24))
            ]
            return _polygon(points)
        if kind == "ARC":
            center = entity.dxf.center
            radius = float(entity.dxf.radius)
            start = math.radians(float(entity.dxf.start_angle))
            end = math.radians(float(entity.dxf.end_angle))
            if end <= start:
                end += 2 * math.pi
            steps = max(4, min(32, math.ceil((end - start) / (math.pi / 16))))
            points = [
                [
                    float(center.x + radius * math.cos(start + (end - start) * index / steps)),
                    float(center.y + radius * math.sin(start + (end - start) * index / steps)),
                ]
                for index in range(steps + 1)
            ]
            return _line(points)
        if kind in {"POINT", "TEXT", "MTEXT", "ATTRIB"}:
            location = entity.dxf.get("location") or entity.dxf.get("insert")
            return {"type": "Point", "coordinates": _xy(location)} if location else None
        if kind == "SOLID":
            return _polygon([_xy(entity.dxf.get(f"vtx{index}")) for index in range(4)])
        if kind in {"SPLINE", "ELLIPSE"}:
            points = [_xy(point) for point in entity.flattening(0.25)]
            return _line(points)
    except (AttributeError, TypeError, ValueError, ZeroDivisionError):
        return None
    return None


T = TypeVar("T")


def select_layer_entities(records: Sequence[T], limit: int) -> list[T]:
    if limit <= 0:
        return []
    if len(records) <= limit:
        return list(records)
    if limit == 1:
        return [records[0]]
    indices = [round(index * (len(records) - 1) / (limit - 1)) for index in range(limit)]
    return [records[index] for index in indices]
