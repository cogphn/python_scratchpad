"""Helpers for interpreting SpacetimeDB's SATS-JSON schema and values.

See https://spacetimedb.com/docs/sats-json for the encoding.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

_PRIMITIVES = {
    "Bool": "bool", "I8": "i8", "U8": "u8", "I16": "i16", "U16": "u16",
    "I32": "i32", "U32": "u32", "I64": "i64", "U64": "u64", "I128": "i128",
    "U128": "u128", "I256": "i256", "U256": "u256", "F32": "f32", "F64": "f64",
    "String": "string",
}

# Special product types SpacetimeDB encodes with a single magic field name.
_SPECIAL_PRODUCTS = {
    "__identity__": "Identity",
    "__connection_id__": "ConnectionId",
    "__timestamp_micros_since_unix_epoch__": "Timestamp",
    "__time_duration_micros__": "TimeDuration",
    "__uuid__": "Uuid",
}


# ------------------------------------------------------------------ typespace
class Typespace:
    def __init__(self, module_def: dict):
        self.types: list[dict] = (module_def.get("typespace") or {}).get("types") or []
        # Map typespace index -> human readable name from module `types`.
        self.names: dict[int, str] = {}
        for t in module_def.get("types") or []:
            name = t.get("name") or {}
            if isinstance(name, dict):
                scope = name.get("scope") or []
                label = ".".join([*scope, name.get("name", "?")])
            else:
                label = str(name)
            ref = t.get("ty")
            if isinstance(ref, int):
                self.names[ref] = label

    def resolve(self, ty: dict) -> dict:
        """Follow ``Ref`` indirections."""
        seen = 0
        while isinstance(ty, dict) and "Ref" in ty and seen < 32:
            idx = ty["Ref"]
            if not isinstance(idx, int) or idx >= len(self.types):
                return ty
            ty = self.types[idx]
            seen += 1
        return ty

    # ---------------------------------------------------------- naming
    def type_name(self, ty: Any, depth: int = 0) -> str:
        if not isinstance(ty, dict) or not ty:
            return "?"
        key, val = next(iter(ty.items()))
        if key in _PRIMITIVES:
            return _PRIMITIVES[key]
        if key == "Ref":
            name = self.names.get(val)
            if name:
                return name
            return self.type_name(self.resolve(ty), depth + 1) if depth < 8 else f"ref#{val}"
        if key == "Array":
            return f"{self.type_name(val, depth + 1)}[]"
        if key == "Product":
            elements = val.get("elements") or []
            if len(elements) == 1:
                fname = _elem_name(elements[0])
                if fname in _SPECIAL_PRODUCTS:
                    return _SPECIAL_PRODUCTS[fname]
            if depth > 2:
                return "struct"
            inner = ", ".join(
                f"{_elem_name(e) or i}: {self.type_name(e.get('algebraic_type'), depth + 1)}"
                for i, e in enumerate(elements)
            )
            return f"{{{inner}}}"
        if key == "Sum":
            variants = val.get("variants") or []
            vnames = [_elem_name(v) for v in variants]
            if set(vnames) == {"some", "none"}:
                some = next(v for v in variants if _elem_name(v) == "some")
                return f"Option<{self.type_name(some.get('algebraic_type'), depth + 1)}>"
            if vnames == ["Interval", "Time"]:
                return "ScheduleAt"
            if depth > 2:
                return "enum"
            inner = " | ".join(
                n if _is_unit(v.get("algebraic_type")) else f"{n}({self.type_name(v.get('algebraic_type'), depth + 1)})"
                for n, v in zip(vnames, variants)
            )
            return f"enum{{{inner}}}"
        return key

    # ---------------------------------------------------------- values
    def format_value(self, value: Any, ty: Any, depth: int = 0) -> str:
        """Render a SATS-JSON value as a compact human-readable string."""
        if ty is None:
            return _dump(value)
        ty = self.resolve(ty) if isinstance(ty, dict) else ty
        if not isinstance(ty, dict) or not ty:
            return _dump(value)
        key, val = next(iter(ty.items()))

        if key in _PRIMITIVES:
            if key == "String":
                return str(value)
            if key == "Bool":
                return "true" if value else "false"
            return _dump(value)

        if key == "Array":
            if isinstance(value, list):
                inner = ", ".join(self.format_value(v, val, depth + 1) for v in value[:50])
                more = f", … (+{len(value) - 50})" if len(value) > 50 else ""
                return f"[{inner}{more}]"
            return _dump(value)

        if key == "Product":
            elements = val.get("elements") or []
            if len(elements) == 1 and _elem_name(elements[0]) in _SPECIAL_PRODUCTS:
                return _format_special(_elem_name(elements[0]), _unwrap_single(value))
            fields = _product_fields(value, elements)
            inner = ", ".join(
                f"{name}: {self.format_value(v, e.get('algebraic_type'), depth + 1)}"
                for (name, v), e in zip(fields, elements)
            )
            return f"{{{inner}}}"

        if key == "Sum":
            variants = val.get("variants") or []
            tag, payload = _sum_parts(value, variants)
            if tag is None:
                return _dump(value)
            vnames = [_elem_name(v) for v in variants]
            variant = next((v for v in variants if _elem_name(v) == tag), None)
            vty = variant.get("algebraic_type") if variant else None
            if set(vnames) == {"some", "none"}:
                if tag == "none":
                    return "null"
                return self.format_value(payload, vty, depth + 1)
            if _is_unit(vty):
                return tag
            return f"{tag}({self.format_value(payload, vty, depth + 1)})"

        return _dump(value)


# ------------------------------------------------------------------ schema
@dataclass
class Column:
    index: int
    name: str
    type_name: str
    type: Any
    primary_key: bool = False
    auto_inc: bool = False
    unique: bool = False
    indexed: bool = False


@dataclass
class TableDef:
    name: str
    columns: list[Column]
    access: str  # Public / Private
    kind: str  # User / System
    indexes: list[dict] = field(default_factory=list)
    constraints: list[dict] = field(default_factory=list)
    scheduled: bool = False
    product_type_ref: int | None = None
    row_count: int | None = None

    @property
    def is_public(self) -> bool:
        return self.access.lower() == "public"


@dataclass
class ReducerDef:
    name: str
    params: list[tuple[str, str]]
    lifecycle: str | None = None


@dataclass
class ModuleSchema:
    tables: list[TableDef]
    reducers: list[ReducerDef]
    types: list[tuple[str, str]]
    typespace: Typespace
    raw: dict

    def table(self, name: str) -> TableDef | None:
        return next((t for t in self.tables if t.name == name), None)


def parse_schema(module_def: dict) -> ModuleSchema:
    ts = Typespace(module_def)
    tables: list[TableDef] = []
    for raw in module_def.get("tables") or []:
        ref = raw.get("product_type_ref")
        product = ts.resolve({"Ref": ref}) if isinstance(ref, int) else {}
        elements = (product.get("Product") or {}).get("elements") or []
        pk = set(raw.get("primary_key") or [])
        seq_cols = {s.get("column") for s in raw.get("sequences") or []}
        unique_cols: set[int] = set()
        for c in raw.get("constraints") or []:
            data = c.get("data") or {}
            uniq = data.get("Unique") or {}
            cols = uniq.get("columns")
            if isinstance(cols, list) and len(cols) == 1:
                unique_cols.add(cols[0])
        indexed_cols: set[int] = set()
        indexes = []
        for ix in raw.get("indexes") or []:
            algo = ix.get("algorithm") or {}
            kind, cols = next(iter(algo.items())) if algo else ("?", [])
            if isinstance(cols, int):
                cols = [cols]
            indexes.append({
                "name": _tag_value(ix.get("name")) or ix.get("accessor_name") or "",
                "kind": kind,
                "columns": [_elem_name(elements[c]) if c < len(elements) else str(c) for c in cols],
            })
            indexed_cols.update(cols)
        columns = [
            Column(
                index=i,
                name=_elem_name(e) or f"col{i}",
                type_name=ts.type_name(e.get("algebraic_type")),
                type=e.get("algebraic_type"),
                primary_key=i in pk,
                auto_inc=i in seq_cols,
                unique=i in unique_cols or i in pk,
                indexed=i in indexed_cols,
            )
            for i, e in enumerate(elements)
        ]
        constraints = [
            {"name": _tag_value(c.get("name")) or "", "kind": next(iter((c.get("data") or {"?": 0}).keys()))}
            for c in raw.get("constraints") or []
        ]
        schedule = raw.get("schedule")
        tables.append(TableDef(
            name=raw.get("name", "?"),
            columns=columns,
            access=_tag_only(raw.get("table_access"), "Private"),
            kind=_tag_only(raw.get("table_type"), "User"),
            indexes=indexes,
            constraints=constraints,
            scheduled=bool(schedule) and "some" in schedule,
            product_type_ref=ref,
        ))
    tables.sort(key=lambda t: t.name)

    reducers: list[ReducerDef] = []
    for raw in module_def.get("reducers") or []:
        params = (raw.get("params") or {}).get("elements") or []
        lifecycle = raw.get("lifecycle")
        lc = None
        if isinstance(lifecycle, dict) and "some" in lifecycle:
            lc = _tag_only(lifecycle["some"], None)
        reducers.append(ReducerDef(
            name=raw.get("name", "?"),
            params=[(_elem_name(p) or f"arg{i}", ts.type_name(p.get("algebraic_type"))) for i, p in enumerate(params)],
            lifecycle=lc,
        ))
    reducers.sort(key=lambda r: (r.lifecycle is None, r.name))

    types = [(name, ts.type_name(ts.types[idx]) if idx < len(ts.types) else "?") for idx, name in sorted(ts.names.items())]
    return ModuleSchema(tables=tables, reducers=reducers, types=types, typespace=ts, raw=module_def)


# -------------------------------------------------------------- SQL results
@dataclass
class ResultSet:
    columns: list[str]
    types: list[str]
    rows: list[list[str]]
    raw_rows: list[Any]
    duration_micros: int | None = None

    @property
    def row_count(self) -> int:
        return len(self.rows)


def parse_result(stmt: dict, ts: Typespace | None = None) -> ResultSet:
    ts = ts or Typespace({})
    elements = (stmt.get("schema") or {}).get("elements") or []
    columns = [_elem_name(e) or f"col{i}" for i, e in enumerate(elements)]
    types = [ts.type_name(e.get("algebraic_type")) for e in elements]
    rows: list[list[str]] = []
    raw_rows = stmt.get("rows") or []
    for row in raw_rows:
        fields = _product_fields(row, elements)
        rows.append([ts.format_value(v, e.get("algebraic_type")) for (_, v), e in zip(fields, elements)])
    return ResultSet(columns, types, rows, raw_rows, stmt.get("total_duration_micros"))


# ----------------------------------------------------------------- helpers
def _elem_name(e: dict) -> str | None:
    name = e.get("name") if isinstance(e, dict) else None
    return _tag_value(name)


def _tag_value(v: Any) -> str | None:
    """Extract ``{"some": x}`` -> x; strings pass through; ``{"none": []}`` -> None."""
    if isinstance(v, dict):
        if "some" in v:
            return v["some"]
        return None
    if isinstance(v, str):
        return v
    return None


def _tag_only(v: Any, default: Any) -> Any:
    """``{"Public": []}`` -> "Public"."""
    if isinstance(v, dict) and v:
        return next(iter(v.keys()))
    if isinstance(v, str):
        return v
    return default


def _is_unit(ty: Any) -> bool:
    if not isinstance(ty, dict):
        return True
    prod = ty.get("Product")
    return isinstance(prod, dict) and not (prod.get("elements") or [])


def _unwrap_single(value: Any) -> Any:
    if isinstance(value, list) and len(value) == 1:
        return value[0]
    if isinstance(value, dict) and len(value) == 1:
        return next(iter(value.values()))
    return value


def _product_fields(value: Any, elements: list[dict]) -> list[tuple[str, Any]]:
    names = [_elem_name(e) or f"col{i}" for i, e in enumerate(elements)]
    if isinstance(value, list):
        return list(zip(names, value))
    if isinstance(value, dict):
        return [(n, value.get(n)) for n in names]
    return [(names[0] if names else "value", value)]


def _sum_parts(value: Any, variants: list[dict]) -> tuple[str | None, Any]:
    if isinstance(value, dict) and len(value) == 1:
        tag, payload = next(iter(value.items()))
        if tag.isdigit():
            idx = int(tag)
            tag = _elem_name(variants[idx]) if idx < len(variants) else tag
        return tag, payload
    if isinstance(value, list) and len(value) == 2 and isinstance(value[0], int):
        idx = value[0]
        tag = _elem_name(variants[idx]) if idx < len(variants) else str(idx)
        return tag, value[1]
    if isinstance(value, str):
        return value, []
    return None, value


def _format_special(kind: str, raw: Any) -> str:
    if kind == "__timestamp_micros_since_unix_epoch__":
        micros = _to_int(raw)
        if micros is not None:
            try:
                dt = datetime.fromtimestamp(micros / 1_000_000, tz=timezone.utc)
                return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " UTC"
            except (OverflowError, OSError, ValueError):
                pass
        return _dump(raw)
    if kind == "__time_duration_micros__":
        micros = _to_int(raw)
        if micros is not None:
            return f"{micros / 1_000_000:g}s"
        return _dump(raw)
    if kind in ("__identity__", "__connection_id__"):
        width = 64 if kind == "__identity__" else 32
        if isinstance(raw, int):
            return f"{raw:0{width}x}"
        if isinstance(raw, str):
            if raw.isdigit():
                return f"{int(raw):0{width}x}"
            return raw[2:] if raw.startswith("0x") else raw
        return str(raw)
    return _dump(raw)


def _to_int(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        try:
            return int(v)
        except ValueError:
            return None
    return None


def _dump(v: Any) -> str:
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(v)
