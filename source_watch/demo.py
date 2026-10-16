"""Synthetic two-domain smoke test; no network, Telegram login or LLM."""
from datetime import datetime, timezone, timedelta
import json
from .core import SourceWatch, Observation


def main() -> None:
    t = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
    with SourceWatch() as watch:
        watch.add_source("feed_1", "news", "fixture")
        watch.add_source("housing_1", "real_estate", "fixture")
        watch.add_watch("ai_digest", "demo_owner", "news", {"topic": {"eq": "ai"}},
                        events=("created", "edited"), channel="console")
        watch.add_watch("coimbra_t2", "demo_owner", "real_estate",
                        {"city": {"eq": "Coimbra"}, "rooms": {"gte": 2},
                         "price_eur": {"lte": 800}},
                        events=("created", "price_decrease"), channel="console")
        fixtures = [
            Observation("feed_1", "post_7", "https://example.org/tech/post-7", t,
                        {"title": "New AI release", "topic": "ai"}),
            Observation("feed_1", "post_7", "https://example.org/tech/post-7", t + timedelta(minutes=1),
                        {"title": "New AI release — corrected", "topic": "ai"}),
            Observation("housing_1", "listing_42", "https://example.org/homes/42", t,
                        {"city": "Coimbra", "rooms": 2, "price_eur": 800}),
            Observation("housing_1", "listing_42", "https://example.org/homes/42", t + timedelta(minutes=2),
                        {"city": "Coimbra", "rooms": 2, "price_eur": 750}),
            Observation("housing_1", "listing_42", "https://example.org/homes/42", t + timedelta(minutes=3),
                        {"city": "Coimbra", "rooms": 2, "price_eur": 750}),
        ]
        for obs in fixtures:
            watch.observe(obs)
        result = {
            "events": [{"domain": c.domain, "kind": c.kind, "tags": c.tags,
                        "changed_fields": list(c.diff)} for c in watch.changes()],
            "outbox": [{"watch_id": n["watch_id"], "status": n["status"]} for n in watch.outbox()],
            "counts": watch.counts(),
            "network_calls": 0,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
