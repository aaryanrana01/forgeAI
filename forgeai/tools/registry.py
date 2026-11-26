"""The tool registry the factory can choose from.

Each tool declares
  * `when_to_use` - what kind of brief needs it (shown to the selector model)
  * `precondition` - a deterministic check that the brief/documents can
    actually justify the tool. The selector proposes, the precondition vetoes:
    an HR agent with a weather tool is a factory defect, so we do not let the
    model's opinion alone decide.
"""

from __future__ import annotations

import ast
import csv
import datetime as dt
import io
import operator
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import requests

from ..textutil import tokens

# --------------------------------------------------------------------------- tools


def _csv_rows(path: Path) -> tuple[list[str], list[dict]]:
    reader = csv.DictReader(io.StringIO(path.read_text(errors="ignore")))
    rows = [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in reader]
    return [c.strip() for c in reader.fieldnames or []], rows


def csv_lookup(args: dict, ctx: dict) -> dict:
    """Filter rows of a bound CSV file. args: {filters: {column: value}, query: str, limit: int}"""
    files: list[str] = ctx["config"].get("files", [])
    knowledge = Path(ctx["knowledge_dir"])
    want_file = args.get("file")
    targets = [f for f in files if not want_file or f == want_file] or files
    filters = args.get("filters") or {}
    if isinstance(filters, list):  # tolerate [{"column":..,"value":..}]
        filters = {f.get("column", ""): f.get("value", "") for f in filters if isinstance(f, dict)}
    query = str(args.get("query") or "")
    limit = int(args.get("limit") or 5)
    results = []
    for fname in targets:
        cols, rows = _csv_rows(knowledge / fname)
        lc = {c.lower(): c for c in cols}
        for r in rows:
            ok = True
            for k, v in filters.items():
                col = lc.get(str(k).lower().strip())
                if col is None:
                    # unknown column: match the value anywhere in the row
                    ok = str(v).lower() in " ".join(r.values()).lower()
                else:
                    cell = r.get(col, "").lower()
                    val = str(v).lower().strip()
                    ok = val == cell or val in cell
                if not ok:
                    break
            if ok:
                results.append((fname, r))
    if query:
        q = set(tokens(query))
        scored = []
        for fname, r in results:
            rt = set(tokens(" ".join(r.values())))
            raw = " ".join(r.values()).lower()
            exact = sum(1 for w in re.findall(r"[a-z0-9\-]{4,}", query.lower()) if w in raw)
            scored.append((len(q & rt) + 2 * exact, fname, r))
        scored = [s for s in scored if s[0] > 0] or ([] if not filters else scored)
        scored.sort(key=lambda s: -s[0])
        results = [(f, r) for _, f, r in scored]
    return {"rows": [dict(r, _file=f) for f, r in results[:limit]], "total_matches": len(results)}


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
        ast.FloorDiv: operator.floordiv, ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCS = {"round": round, "min": min, "max": max, "abs": abs, "sum": lambda *a: sum(a)}


def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _safe_eval(node.left), _safe_eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("exponent too large")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        return _FUNCS[node.func.id](*[_safe_eval(a) for a in node.args])
    raise ValueError(f"unsupported expression element: {ast.dump(node)[:60]}")


def calculator(args: dict, ctx: dict) -> dict:
    expr = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", str(args.get("expression", "")))
    expr = re.sub(r"(?<=[\d)])\s*[x×]\s*(?=[\d(])", "*", expr)
    expr = re.sub(r"[$€£₹]|usd|inr|eur", "", expr, flags=re.I)
    try:
        val = _safe_eval(ast.parse(expr, mode="eval"))
        if isinstance(val, float):
            val = round(val, 4)
        return {"expression": expr, "result": val}
    except Exception as e:
        return {"expression": expr, "error": str(e)}


def current_date(args: dict, ctx: dict) -> dict:
    today = ctx.get("today") or dt.date.today()
    out: dict[str, Any] = {"today": today.isoformat(), "weekday": today.strftime("%A")}
    add = args.get("add_days")
    if add not in (None, ""):
        try:
            n = int(float(add))
            target = today + dt.timedelta(days=n)
            out.update({"add_days": n, "result_date": target.isoformat(), "result_weekday": target.strftime("%A")})
        except ValueError:
            out["error"] = f"add_days must be a number, got {add!r}"
    return out


def weather(args: dict, ctx: dict) -> dict:
    """Keyless open-meteo forecast. args: {location: str} or {latitude, longitude}"""
    try:
        lat, lon, name = args.get("latitude"), args.get("longitude"), args.get("location", "")
        if (lat is None or lon is None) and name:
            g = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                             params={"name": name, "count": 1}, timeout=15).json()
            if not g.get("results"):
                return {"error": f"location not found: {name}"}
            lat, lon, name = g["results"][0]["latitude"], g["results"][0]["longitude"], g["results"][0]["name"]
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon, "current": "temperature_2m,wind_speed_10m,weather_code",
            "daily": "temperature_2m_max,temperature_2m_min,wind_speed_10m_max", "forecast_days": 3,
            "timezone": "auto"}, timeout=15).json()
        return {"location": name, "latitude": lat, "longitude": lon, "current": r.get("current"),
                "daily": r.get("daily")}
    except Exception as e:
        return {"error": f"weather service unavailable: {e}"}


# ---------------------------------------------------------------- preconditions

_KW = {
    "weather": r"\b(weather|forecast|wind|storm|rain|temperature outside|sea state|wave|cyclone|monsoon)\b",
    "calculator": r"\b(total|sum|cost|price|calculat|compute|quantit|percent|discount|multipl|convert|order value)\w*",
    "current_date": r"\b(today|date|deadline|due|when will|arriv|deliver|eta|lead time|days from now|expir|"
                    r"schedul|this week|next week|calendar)\w*",
}


def _pre_csv(req_text: str, docs: list) -> tuple[bool, str]:
    csvs = [d.doc_id for d in docs if d.kind == "csv"]
    return (bool(csvs), f"CSV files present: {csvs}" if csvs else "no CSV file in the document folder")


def _pre_kw(name: str) -> Callable:
    def check(req_text: str, docs: list) -> tuple[bool, str]:
        m = re.search(_KW[name], req_text.lower())
        return (bool(m), f"requirements mention '{m.group(0)}'" if m else
                f"requirements never mention a need this tool serves (pattern: {name})")
    return check


@dataclass
class Tool:
    name: str
    description: str
    when_to_use: str
    input_schema: dict
    fn: Callable[[dict, dict], dict]
    precondition: Callable[[str, list], tuple[bool, str]]
    needs_network: bool = False

    def run(self, args: dict, ctx: dict) -> dict:
        try:
            return self.fn(args or {}, ctx)
        except Exception as e:  # tools must never crash the agent
            return {"error": f"{type(e).__name__}: {e}"}


REGISTRY: dict[str, Tool] = {
    "csv_lookup": Tool(
        "csv_lookup",
        "Look up rows in a CSV table from the knowledge base by column filters and/or keywords.",
        "Brief needs exact values from a structured table (catalogue, price list, inventory, roster).",
        {"filters": "object {column_name: value} (optional)", "query": "keywords (optional)",
         "limit": "max rows, default 5"},
        csv_lookup, _pre_csv),
    "calculator": Tool(
        "calculator",
        "Evaluate an arithmetic expression exactly, e.g. '3 * 1245.50 + 80'.",
        "Brief needs arithmetic: totals, costs, quantities, percentages, conversions.",
        {"expression": "arithmetic expression using + - * / ( ) round min max"},
        calculator, _pre_kw("calculator")),
    "current_date": Tool(
        "current_date",
        "Return today's date and optionally the date N days from today.",
        "Brief needs today's date or date arithmetic: deadlines, delivery/arrival dates, expiries.",
        {"add_days": "integer (optional)"},
        current_date, _pre_kw("current_date")),
    "weather": Tool(
        "weather",
        "Current weather and 3-day forecast for a place (open-meteo, no key).",
        "Brief needs live weather or sea/wind conditions for a location.",
        {"location": "place name", "latitude": "optional", "longitude": "optional"},
        weather, _pre_kw("weather"), needs_network=True),
}


def tool_catalog_text() -> str:
    return "\n".join(f"- {t.name}: {t.description} USE WHEN: {t.when_to_use}" for t in REGISTRY.values())


def build_tools(bindings) -> dict[str, tuple[Tool, dict]]:
    out = {}
    for b in bindings:
        if b.name in REGISTRY:
            out[b.name] = (REGISTRY[b.name], b.config)
    return out
