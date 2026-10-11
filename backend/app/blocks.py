"""Lesson step blocks: the components a tutor step can show, their Gemini schema, and server-side validation."""

import math

FRACTION_VISUALS = ("fraction-circles", "fraction-bars", "number-line")
ITEM_VISUALS = ("flow", "comparison")
VISUAL_TYPES = [*FRACTION_VISUALS, *ITEM_VISUALS, "bar-chart", "line-graph", "table"]
BLOCK_TYPES = ["text", "callout", *VISUAL_TYPES]
MAX_BLOCKS = 8
MAX_VISUALS = 4

FRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "numerator": {"type": "integer", "minimum": 0, "maximum": 24},
        "denominator": {"type": "integer", "minimum": 1, "maximum": 12},
        "label": {"type": "string"},
    },
    "required": ["numerator", "denominator", "label"],
}

# One flat object for every block type keeps the schema within constructs Vertex AI already accepts here.
BLOCK_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": BLOCK_TYPES},
        "text": {"type": "string", "description": "text: one short paragraph. callout: the one sentence to highlight."},
        "caption": {"type": "string", "description": "callout: a 1-3 word label such as Remember, Tip or Example. Every other non-text block: a short title."},
        "fractions": {"type": "array", "items": FRACTION_SCHEMA, "maxItems": 4,
                      "description": "fraction-circles, fraction-bars and number-line: the fractions to draw."},
        "items": {
            "type": "array", "maxItems": 6, "description": "flow: the steps in order. comparison: 2-3 ideas side by side.",
            "items": {"type": "object", "properties": {"label": {"type": "string"}, "detail": {"type": "string"}},
                      "required": ["label", "detail"]},
        },
        "data": {
            "type": "array", "maxItems": 8, "description": "bar-chart: one bar per category.",
            "items": {"type": "object", "properties": {"label": {"type": "string"}, "value": {"type": "number"}},
                      "required": ["label", "value"]},
        },
        "points": {
            "type": "array", "maxItems": 12, "description": "line-graph: the points to join, in order of x.",
            "items": {"type": "object", "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
                      "required": ["x", "y"]},
        },
        "xLabel": {"type": "string", "description": "line-graph: what the x-axis measures, with units."},
        "yLabel": {"type": "string", "description": "bar-chart and line-graph: what the values measure, with units."},
        "columns": {"type": "array", "items": {"type": "string"}, "maxItems": 4, "description": "table: the column headings."},
        "rows": {
            "type": "array", "maxItems": 8, "description": "table: one list of cells per row, in column order.",
            "items": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
        },
    },
    "required": ["type"],
}


def _text(value, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _fractions(raw) -> list[dict]:
    fractions = []
    for item in (raw or [])[:4]:
        numerator = _number(item.get("numerator")) if isinstance(item, dict) else None
        denominator = _number(item.get("denominator")) if isinstance(item, dict) else None
        if numerator is None or denominator is None:
            continue
        top, bottom = max(0, min(24, int(numerator))), max(1, min(12, int(denominator)))
        fractions.append({"numerator": top, "denominator": bottom, "label": _text(item.get("label"), 40) or f"{top}/{bottom}"})
    return fractions


def clean_visual(raw) -> dict | None:
    """Return a render-safe copy of one diagram, chart or table, or None if it can't be drawn."""
    if not isinstance(raw, dict) or raw.get("type") not in VISUAL_TYPES:
        return None
    kind = raw["type"]
    visual = {"type": kind, "caption": _text(raw.get("caption"), 160), "fractions": [], "items": []}
    if kind in FRACTION_VISUALS:
        visual["fractions"] = _fractions(raw.get("fractions"))
        return visual if visual["fractions"] else None
    if kind in ITEM_VISUALS:
        visual["items"] = [{"label": _text(item.get("label"), 60), "detail": _text(item.get("detail"), 240)}
                           for item in (raw.get("items") or [])[:6] if isinstance(item, dict)]
        return visual if visual["items"] else None
    if kind == "bar-chart":
        data = [{"label": _text(bar.get("label"), 40), "value": value} for bar in (raw.get("data") or [])[:8]
                if isinstance(bar, dict) and (value := _number(bar.get("value"))) is not None]
        return {**visual, "data": data, "yLabel": _text(raw.get("yLabel"), 60)} if data else None
    if kind == "line-graph":
        points = [{"x": x, "y": y} for point in (raw.get("points") or [])[:12] if isinstance(point, dict)
                  and (x := _number(point.get("x"))) is not None and (y := _number(point.get("y"))) is not None]
        points.sort(key=lambda point: point["x"])
        return ({**visual, "points": points, "xLabel": _text(raw.get("xLabel"), 60), "yLabel": _text(raw.get("yLabel"), 60)}
                if len(points) >= 2 else None)
    columns = [_text(column, 40) for column in (raw.get("columns") or [])[:4]]
    rows = [[_text(cell, 80) for cell in row[:len(columns)]] + [""] * (len(columns) - len(row))
            for row in (raw.get("rows") or [])[:8] if isinstance(row, list)]
    return {**visual, "columns": columns, "rows": rows} if columns and rows else None


def to_content(raw_blocks) -> list[dict]:
    """Validate blocks in display order, dropping any that can't be shown and capping their number."""
    content: list[dict] = []
    visuals = 0
    for block in raw_blocks or []:
        if len(content) == MAX_BLOCKS:
            break
        if not isinstance(block, dict):
            continue
        if block.get("type") in ("text", "callout"):
            text = _text(block.get("text"), 2000)
            if text and block["type"] == "text":
                content.append({"type": "text", "text": text})
            elif text:
                content.append({"type": "callout", "label": _text(block.get("caption"), 40) or "Remember", "text": text})
        elif visuals < MAX_VISUALS and (visual := clean_visual(block)):
            content.append({"type": "visual", "visual": visual})
            visuals += 1
    return content


def texts(content: list[dict]) -> list[str]:
    return [block["text"] for block in content if block["type"] in ("text", "callout")]
