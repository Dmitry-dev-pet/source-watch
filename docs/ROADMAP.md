# Roadmap: small, test-first extraction

## M0 — offline proof (this archive)

- [x] Common Observation → Change → durable Outbox implementation.
- [x] News edit and real-estate price-drop fixtures and unit tests.
- [x] Repeat delivery enqueue safety, partial capture safety, no false removal on source failure.
- [x] Independent Python package, MIT license, no third-party code or credentials.

## M1 — production-worthy core (future)

- [ ] Schema migrations, source revision replays, bounded retention/backup/restore, concurrency tests and package distribution.
- [ ] Watch edits with owner-scoped API, audit trail and idempotent update version.
- [ ] Domain field normalization contracts; explicit source freshness/staleness and per-source error visibility.
- [ ] Transactional outbox worker with retry/backoff and delivery receipts (at-least-once network semantics).
- [ ] Property/listing dedup only after conservative, reversible entity matching tests.
- [ ] A synthetic Docker Compose smoke and minimal CLI before any remote ingress.

## M2 — Portuguese housing application (future, separately authorized)

- [ ] Provider-approved source adapter(s): official saved-search email importer or approved API/feed.
- [ ] User-specific searches for locations, budgets, bedrooms and sale/rent.
- [ ] Telegram Bot API sender with separate bot token, **never** the news exporter's Telegram user session.
- [ ] Real two-source validation; source updates and price history; delivery integrity and freshness report.

## M3 — optional news integration (future)

- [ ] Contract-compare with existing private news aggregator, without copying private data or credentials.
- [ ] Incremental adoption where contract tests prove equivalent idempotency and provenance behavior.
- [ ] Keep news story clustering separate from property matching.
- [ ] Optional authenticated read-only route through existing shared Truthrail gateway; no new tunnel by default.

Neither creating this public repo, deploying containers, polling external sources nor registering an active Alfred capability is implied by the offline proof. Each needs a separate verified operational step.
