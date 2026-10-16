"""Domain-specific event meaning; core never imports websites or models."""
from __future__ import annotations
from typing import Any


def change_tags(domain: str, before: dict[str, Any] | None,
                after: dict[str, Any], kind: str) -> tuple[str, ...]:
    if kind == "created":
        return ()
    if domain == "real_estate":
        old, new = (before or {}).get("price_eur"), after.get("price_eur")
        if isinstance(old, (int, float)) and not isinstance(old, bool) and isinstance(new, (int, float)) and not isinstance(new, bool):
            if new < old:
                return ("price_decrease",)
            if new > old:
                return ("price_increase",)
        return ("details_changed",)
    if domain == "news":
        return ("edited",)
    return ("updated",)


def matches(filters: dict[str, dict[str, Any]], payload: dict[str, Any]) -> bool:
    """Pure, fail-closed predicates over normalized payload fields."""
    for field, predicates in filters.items():
        if field not in payload:
            return False
        value = payload[field]
        for op, arg in predicates.items():
            if op == "eq":
                ok = type(value) is type(arg) and value == arg
            elif op in {"gte", "lte"}:
                numeric = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool)
                ok = numeric(value) and numeric(arg) and (value >= arg if op == "gte" else value <= arg)
            elif op == "contains":
                ok = isinstance(value, str) and isinstance(arg, str) and arg.casefold() in value.casefold()
            elif op == "in":
                ok = isinstance(arg, list) and any(type(x) is type(value) and x == value for x in arg)
            else:
                ok = False
            if not ok:
                return False
    return True
