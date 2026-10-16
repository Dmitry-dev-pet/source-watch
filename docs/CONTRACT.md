# Source Watch observation protocol — v0.1

Status: **prototype**, not a deployed API or final public standard.

## Objects and identity

- **Source** — stable `source_id`, `domain`, `transport`, `enabled`; registration is an operator-controlled configuration, not a provider permission grant.
- **Observation** — stable key `(source_id, external_id)`, canonical HTTPS `source_url`, `observed_at` (aware UTC-normalized), optional `published_at`, JSON `payload`, `complete`.
- **Change** — a transition in a complete item's payload: `created` or `updated`, the exact diff, before/after snapshots, optional domain tags, original URL and stable source identity.
- **Watch** — `watch_id`, private owner key, domain, deterministic field predicates, desired events and delivery channel.
- **Outbox delivery** — persisted `(watch_id, change_id)` once with `pending` status; not proof a recipient received anything.

The database preserves each accepted observation. Same `(source_id, external_id, observed_at)` is an immutable snapshot: an identical replay has no effect; a conflicting replay is rejected; an older unseen snapshot is rejected. An unchanged, newer complete observation updates last-seen time without producing a new change. If a payload returns to an earlier value *after* a different value, that return is a **new transition**.

The core considers no single observation proof that a listing was published at the time it was fetched. Published, edited and observed timestamps must never be conflated.

### Example synthetic observation

```json
{
  "source_id": "sample_properties",
  "external_id": "sample_42",
  "canonical_url": "https://example.org/homes/42",
  "observed_at": "2026-10-17T12:00:00+00:00",
  "published_at": null,
  "complete": true,
  "payload": {"city": "Coimbra", "rooms": 2, "price_eur": 800}
}
```

### Example synthetic change

```json
{
  "kind": "updated",
  "tags": ["price_decrease"],
  "diff": {"price_eur": [800, 750]},
  "source_id": "sample_properties",
  "external_id": "sample_42"
}
```

## Guarantees and deliberate non-guarantees

| Guaranteed by this prototype | Not guaranteed |
| --- | --- |
| Source-scoped identity and immutable timestamped captures | Provider coverage, legal permission or actual published date |
| Atomic local SQLite changes plus once-only outbox enqueue | Exactly-once Telegram/internet delivery |
| Complete-only authoritative updates | Correct handling of every partially rendered source page |
| Fail-closed filters on missing fields | Semantic truth of a report or cross-site matching |
| Source-check status never triggers implicit deletion | Detection of delisted properties |
| Deterministic transition tags | Ranking, clustering, ML matching, scoring |

## Domain-specific contracts

- **news**: `title`, `topic`, optional summary and source provenance; an update can be tagged `edited`. Story grouping, shared upstream sources and source credibility belong to the news domain, **not** the source watcher.
- **real_estate**: `city`, `rooms`, `price_eur`, optional area, property type, listing status and structured location; numeric price decrease/increase are deterministic tags. Cross-site property identity belongs to the housing domain, **not** the core.

Unknown domains are allowed and changes receive a generic `updated` tag. Producers own normalization and validation for their domain (e.g. reject invalid room counts or ambiguous currencies). All filters operate on trusted normalized fields, never directly on arbitrary HTML markup.

## Security boundary

No network in core. HTTPS URL validation here only guards metadata shape; any future fetcher must independently prevent SSRF including DNS rebinding, handle rate limiting, credentials and redirects, and prove provider rights. Source content is untrusted. Remote writes require authentication, authorization, owner scoping and audit logging that are **not** part of v0.1. A permission-gated news reader must not be implicitly widened to write.

## Compatibility / future

Version the exported JSON schema and add explicit migrations when a network API is introduced. Preserve legacy source keys and change IDs across migrations. Prevent data from one owner affecting another's notifications. The first release intentionally has no generic shell, MCP tunnel or always-on agent.
