"""Dependency-free SQLite observation → change → durable outbox pipeline.

This package deliberately performs NO fetching, autonomous scheduling, account
login, LLM inference or outbound notifications. Callers supply approved input.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .domains import change_tags, matches

IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
EVENT_TYPES = frozenset({"created", "updated", "price_decrease", "price_increase", "details_changed", "edited"})
FILTER_OPERATORS = frozenset({"eq", "gte", "lte", "contains", "in"})
MAX_PAYLOAD_BYTES = 32768


def _id(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field} must be 1–64 safe characters")
    return value


def _iso(dt: datetime, *, field: str) -> str:
    if not isinstance(dt, datetime) or dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware datetime")
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _json(value: Any, *, limit: int = MAX_PAYLOAD_BYTES) -> str:
    try:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
        if len(text.encode("utf-8")) > limit:
            raise ValueError("JSON payload exceeds size limit")
        return text
    except (TypeError, OverflowError, ValueError) as exc:
        raise ValueError("invalid, non-finite or oversized JSON") from exc


def _url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 33 for c in value):
        raise ValueError("invalid source URL")
    try:
        u = urlsplit(value)
        host = u.hostname
        if u.scheme != "https" or not host or u.username or u.password or u.port is not None or u.fragment:
            raise ValueError("source URL must be canonical HTTPS without credentials or fragment")
        hostname = host.casefold().rstrip(".")
        if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith((".local", ".internal", ".localhost")):
            raise ValueError("local host forbidden")
        try:
            addr = ipaddress.ip_address(hostname)
        except ValueError:
            if "." not in hostname:
                raise ValueError("URL needs a DNS hostname")
        else:
            if not addr.is_global:
                raise ValueError("nonpublic IP forbidden")
        return value
    except ValueError as exc:
        raise ValueError("invalid or unsafe source URL") from exc


def _sha(*segments: str) -> str:
    return hashlib.sha256("\x1f".join(segments).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Observation:
    source_id: str
    external_id: str
    canonical_url: str
    observed_at: datetime
    payload: dict[str, Any]
    published_at: datetime | None = None
    complete: bool = True


@dataclass(frozen=True, slots=True)
class Change:
    change_id: str
    source_id: str
    external_id: str
    domain: str
    canonical_url: str
    observed_at: str
    kind: str
    tags: tuple[str, ...]
    diff: dict[str, list[Any]]
    before: dict[str, Any] | None
    after: dict[str, Any]


class SourceWatch:
    """A synchronous, offline, single-writer SQLite store.

    Concurrent consumers use independent connections. Writers are serialized
    through SQLite BEGIN IMMEDIATE. Source registration and rule management
    require a trusted caller; there is no HTTP authorization in this prototype.
    """

    def __init__(self, db_path: str | Path = ":memory:"):
        self.db = sqlite3.connect(str(db_path), timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS sources (
            source_id TEXT PRIMARY KEY, domain TEXT NOT NULL,
            transport TEXT NOT NULL, enabled INTEGER NOT NULL CHECK(enabled IN (0,1))
          );
          CREATE TABLE IF NOT EXISTS observations (
            observation_id TEXT PRIMARY KEY, source_id TEXT NOT NULL,
            external_id TEXT NOT NULL, canonical_url TEXT NOT NULL,
            observed_at TEXT NOT NULL, published_at TEXT,
            payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
            complete INTEGER NOT NULL CHECK(complete IN (0,1)),
            UNIQUE(source_id, external_id, observed_at),
            FOREIGN KEY(source_id) REFERENCES sources(source_id)
          );
          CREATE TABLE IF NOT EXISTS items (
            source_id TEXT NOT NULL, external_id TEXT NOT NULL,
            domain TEXT NOT NULL, canonical_url TEXT NOT NULL,
            published_at TEXT, payload_json TEXT NOT NULL,
            payload_hash TEXT NOT NULL, last_seen_at TEXT NOT NULL,
            PRIMARY KEY(source_id, external_id),
            FOREIGN KEY(source_id) REFERENCES sources(source_id)
          );
          CREATE TABLE IF NOT EXISTS changes (
            change_id TEXT PRIMARY KEY, observation_id TEXT NOT NULL UNIQUE,
            source_id TEXT NOT NULL, external_id TEXT NOT NULL,
            domain TEXT NOT NULL, canonical_url TEXT NOT NULL,
            observed_at TEXT NOT NULL, kind TEXT NOT NULL,
            tags_json TEXT NOT NULL, diff_json TEXT NOT NULL,
            before_json TEXT, after_json TEXT NOT NULL,
            FOREIGN KEY(observation_id) REFERENCES observations(observation_id)
          );
          CREATE TABLE IF NOT EXISTS watches (
            watch_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
            domain TEXT NOT NULL, channel TEXT NOT NULL,
            filters_json TEXT NOT NULL, events_json TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1))
          );
          CREATE TABLE IF NOT EXISTS outbox (
            delivery_id TEXT PRIMARY KEY, watch_id TEXT NOT NULL,
            change_id TEXT NOT NULL, channel TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            UNIQUE(watch_id, change_id),
            FOREIGN KEY(watch_id) REFERENCES watches(watch_id),
            FOREIGN KEY(change_id) REFERENCES changes(change_id)
          );
          CREATE TABLE IF NOT EXISTS source_checks (
            source_id TEXT NOT NULL, checked_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('ok','partial','error')),
            PRIMARY KEY(source_id, checked_at),
            FOREIGN KEY(source_id) REFERENCES sources(source_id)
          );
        """)

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "SourceWatch":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def add_source(self, source_id: str, domain: str, transport: str, *, enabled: bool = True) -> None:
        _id(source_id, field="source_id")
        _id(domain, field="domain")
        _id(transport, field="transport")
        if type(enabled) is not bool:
            raise ValueError("enabled must be boolean")
        try:
            self.db.execute("INSERT INTO sources VALUES (?, ?, ?, ?)",
                            (source_id, domain, transport, int(enabled)))
        except sqlite3.IntegrityError as exc:
            raise ValueError("source already registered") from exc

    def add_watch(self, watch_id: str, owner_id: str, domain: str,
                  filters: dict[str, dict[str, Any]],
                  *, events: tuple[str, ...] = ("created",),
                  channel: str = "console", enabled: bool = True) -> None:
        for name, value in (("watch_id", watch_id), ("owner_id", owner_id),
                            ("domain", domain), ("channel", channel)):
            _id(value, field=name)
        if not isinstance(filters, dict) or not all(
            isinstance(k, str) and IDENTIFIER.fullmatch(k) and isinstance(v, dict)
            and bool(v) and set(v) <= FILTER_OPERATORS for k, v in filters.items()
        ):
            raise ValueError("invalid filter predicates")
        if not isinstance(events, tuple) or not events or any(e not in EVENT_TYPES for e in events):
            raise ValueError("invalid event subscription")
        if type(enabled) is not bool:
            raise ValueError("enabled must be boolean")
        serialized_filters = _json(filters, limit=8192)
        serialized_events = _json(list(events), limit=1024)
        try:
            self.db.execute("INSERT INTO watches VALUES (?,?,?,?,?,?,?)",
                (watch_id, owner_id, domain, channel, serialized_filters, serialized_events, int(enabled)))
        except sqlite3.IntegrityError as exc:
            raise ValueError("watch already exists") from exc

    def set_watch_enabled(self, watch_id: str, owner_id: str, enabled: bool) -> bool:
        _id(watch_id, field="watch_id")
        _id(owner_id, field="owner_id")
        if type(enabled) is not bool:
            raise ValueError("enabled must be boolean")
        cur = self.db.execute("UPDATE watches SET enabled=? WHERE watch_id=? AND owner_id=?",
                              (int(enabled), watch_id, owner_id))
        return cur.rowcount == 1

    def record_check(self, source_id: str, checked_at: datetime, status: str) -> None:
        if status not in {"ok", "partial", "error"}:
            raise ValueError("invalid source check status")
        self.db.execute("INSERT OR IGNORE INTO source_checks VALUES (?,?,?)",
                        (_id(source_id, field="source_id"), _iso(checked_at, field="checked_at"), status))
        # In particular, a missing item never causes deletion in this contract.

    def observe(self, observation: Observation) -> Change | None:
        if not isinstance(observation, Observation):
            raise TypeError("expected Observation")
        sid = _id(observation.source_id, field="source_id")
        if not isinstance(observation.external_id, str) or not 1 <= len(observation.external_id) <= 256:
            raise ValueError("external_id must have 1–256 characters")
        ext = observation.external_id
        url = _url(observation.canonical_url)
        observed = _iso(observation.observed_at, field="observed_at")
        published = _iso(observation.published_at, field="published_at") if observation.published_at is not None else None
        if not isinstance(observation.payload, dict) or any(not isinstance(k, str) or not k for k in observation.payload):
            raise ValueError("payload must be a JSON object with nonempty string keys")
        payload_json = _json(observation.payload)
        digest = _sha(payload_json)
        if type(observation.complete) is not bool:
            raise ValueError("complete must be boolean")
        oid = _sha(sid, ext, observed)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            source = self.db.execute("SELECT domain, enabled FROM sources WHERE source_id=?", (sid,)).fetchone()
            if source is None or source["enabled"] != 1:
                raise ValueError("unknown or disabled source")
            existing_obs = self.db.execute(
                "SELECT payload_hash, canonical_url, published_at, complete FROM observations WHERE observation_id=?", (oid,)
            ).fetchone()
            if existing_obs is not None:
                if (existing_obs["payload_hash"] != digest or existing_obs["complete"] != int(observation.complete)
                    or existing_obs["canonical_url"] != url or existing_obs["published_at"] != published):
                    raise ValueError("conflicting observation at the same timestamp")
                self.db.commit()
                return None
            newest = self.db.execute("SELECT MAX(observed_at) FROM observations WHERE source_id=? AND external_id=?",
                                    (sid, ext)).fetchone()[0]
            if newest is not None and observed <= newest:
                raise ValueError("out-of-order observation")
            self.db.execute("""INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?)""",
                            (oid, sid, ext, url, observed, published, payload_json, digest, int(observation.complete)))
            if not observation.complete:
                self.db.commit()
                return None
            old = self.db.execute("SELECT * FROM items WHERE source_id=? AND external_id=?", (sid, ext)).fetchone()
            before = json.loads(old["payload_json"]) if old else None
            if old is None:
                kind = "created"
                self.db.execute("INSERT INTO items VALUES (?,?,?,?,?,?,?,?)",
                     (sid, ext, source["domain"], url, published, payload_json, digest, observed))
            else:
                if observed <= old["last_seen_at"]:
                    raise ValueError("out-of-order complete observation")
                kind = "updated" if old["payload_hash"] != digest else "unchanged"
                self.db.execute("""UPDATE items SET canonical_url=?, published_at=?,
                         payload_json=?, payload_hash=?, last_seen_at=?
                         WHERE source_id=? AND external_id=?""",
                     (url, published or old["published_at"], payload_json, digest, observed, sid, ext))
            if kind == "unchanged":
                self.db.commit()
                return None
            diff: dict[str, list[Any]] = {}
            for key in set((before or {}).keys()) | set(observation.payload.keys()):
                prior, current = (before or {}).get(key), observation.payload.get(key)
                if key not in (before or {}) or key not in observation.payload or prior != current:
                    diff[key] = [prior, current]
            tags = change_tags(source["domain"], before, observation.payload, kind)
            change_id = _sha("change", oid)
            self.db.execute("INSERT INTO changes VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (change_id, oid, sid, ext, source["domain"], url, observed, kind,
                 _json(list(tags)), _json(diff), _json(before) if before is not None else None, payload_json))
            for watch in self.db.execute("SELECT * FROM watches WHERE enabled=1 AND domain=?", (source["domain"],)):
                rules = json.loads(watch["filters_json"])
                events = set(json.loads(watch["events_json"]))
                if not (events & ({kind} | set(tags))) or not matches(rules, observation.payload):
                    continue
                delivery_id = _sha("delivery", watch["watch_id"], change_id)
                self.db.execute("INSERT INTO outbox(delivery_id,watch_id,change_id,channel) VALUES (?,?,?,?)",
                                (delivery_id, watch["watch_id"], change_id, watch["channel"]))
            self.db.commit()
            return Change(change_id, sid, ext, source["domain"], url, observed,
                          kind, tags, diff, before, dict(observation.payload))
        except Exception:
            self.db.rollback()
            raise

    def changes(self) -> list[Change]:
        result = []
        for row in self.db.execute("SELECT * FROM changes ORDER BY observed_at, change_id"):
            result.append(Change(row["change_id"], row["source_id"], row["external_id"],
                                 row["domain"], row["canonical_url"], row["observed_at"],
                                 row["kind"], tuple(json.loads(row["tags_json"])),
                                 json.loads(row["diff_json"]),
                                 json.loads(row["before_json"]) if row["before_json"] is not None else None,
                                 json.loads(row["after_json"])))
        return result

    def outbox(self) -> list[dict[str, str]]:
        return [dict(row) for row in self.db.execute(
            "SELECT delivery_id,watch_id,change_id,channel,status FROM outbox ORDER BY rowid")]

    def counts(self) -> dict[str, int]:
        return {table: self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("sources", "observations", "items", "changes", "watches", "outbox", "source_checks")}
