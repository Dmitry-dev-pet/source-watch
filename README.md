# Source Watch — public core prototype v0.1

**One observation contract. Many monitored domains.**

`source-watch` is a small, dependency-free Python 3.12+ prototype for turning **approved, normalized source observations** into **versioned changes** and a **durable notification outbox**. It is designed to be used by independent news, property, product-price and other monitors — not to become an AI agent.

**Status: offline proof of concept.** There is **no live website fetching, Telegram integration, auto-scheduler, MCP server, account login, web UI or production deployment**. Synthetic examples are not real property listings or news. Every provider adapter will require separate review of access rights, security and privacy.

## Verify locally

```bash
python3 -m unittest discover -s tests -v
python3 -m source_watch.demo
```

The demo is fully offline; all source URLs use `example.org` and no network is touched.

## Why this is common across news and real estate

| Stage | News | Real estate | Shared core |
| --- | --- | --- | --- |
| Source | Public RSS / approved feed | Provider feed / official alerts | Explicit registration, scope |
| Observation | One article/report | One listing | Stable `(source_id, external_id)` and observed timestamp |
| Revision | Edited headline | New asking price | Immutable observation, changed-fields diff |
| Domain semantics | Edited, same underlying story | Price drop, same property on multiple sites | **Outside** core, separate domain modules |
| Subscription | Topic | City/budget/rooms | Domain filters and event kinds |
| Delivery | Daily digest | Immediate alert | Transactional, idempotent **outbox** (not a sender) |

**The core does not group across sources.** Two reports describing one event are distinct items until a news-specific clustering layer groups them. Two ads for one house are distinct until a housing-specific entity matcher links them. Never equate similarity with verified identity.

## Demonstrated behavior

- Register synthetic sources (`news`, `real_estate`) and create independent watches.
- Record first complete observation (`created`), a changed payload (`updated`) and subsequent unchanged snapshots (no duplicate changes).
- A housing price decrease is tagged `price_decrease`; an edited news report is tagged `edited`.
- Preserve observed snapshots and original source URLs. Timestamps are timezone-aware.
- A partial capture is recorded but cannot create or modify the authoritative current item.
- Stale or failed checks do not imply removal; deleting listings requires a separate authoritative lifecycle policy.
- Matching writes outbox entries atomically with their changes. Re-ingesting the same observation never creates another outbox row.
- Notifications are **pending**, not actually delivered; exactly-once remote delivery is not claimed.

## Minimal example

```python
from datetime import datetime, timezone
from source_watch import SourceWatch, Observation

with SourceWatch("monitor.sqlite") as w:
    w.add_source("houses", "real_estate", "fixture")
    w.add_watch("coimbra_t2", "local_user", "real_estate", {
        "city": {"eq": "Coimbra"},
        "rooms": {"gte": 2},
        "price_eur": {"lte": 800},
    }, events=("created", "price_decrease"), channel="console")
    change = w.observe(Observation(
        source_id="houses", external_id="listing_1",
        canonical_url="https://example.org/homes/1",
        observed_at=datetime.now(timezone.utc),
        payload={"city": "Coimbra", "rooms": 2, "price_eur": 750},
    ))
    print(change.kind, len(w.outbox()))
```

## Architecture

```text
approved independent adapters  [future]
            |
   normalized Observation
            v
     source_watch core
     | provenance / SQLite
     | versioned change diff
     | deterministic domain tags
     | watch rules & outbox
            |
    domain product services [future]
      news / real estate
            |
   Telegram, CLI, read-only API [future]
```

Use a provider's approved API, mail notification or feed where permitted. This repository contains no Idealista scraping code. The architecture is designed to be source-neutral and independently installable; it must not require access to any private agent, repository, messaging account or LLM subscription.

## Security and contribution boundaries

- Raw fetched text is **untrusted data**, not code or instructions. No untrusted URL is fetched by this package.
- Credentials, personal subscriptions, SQLite data and message bodies are never committed to Git.
- Source rights, permission for collection and permission to disclose content to an AI are **separate** decisions.
- No user identity or authorization enforcement is provided at the network boundary in v0.1. All `add_source`/`add_watch` calls are for trusted offline callers only. Any exposed API requires authenticated, owner-scoped access first.
- SQLite assumes a single application instance; cross-host multi-writer sync and remote notification delivery are out of scope.
- Do not incorporate third-party scraper source code without verifying its license.

See [the v0.1 contract](docs/CONTRACT.md) and [next milestones](docs/ROADMAP.md).

## License

MIT. New implementation written independently from third-party donor repositories.
