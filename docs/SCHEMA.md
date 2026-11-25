# Database design

`backend/schema.sql` is the executable source of truth. All three tables are created automatically on startup; no migrations or external database service are required.

## rfqs

One row per RFQ, including the immutable configuration and mutable current close.

| Columns | Meaning |
| --- | --- |
| `id` | Integer primary key |
| `reference` | Required, unique, uppercase reference ID |
| `name`, `currency` | RFQ title and single currency (INR, USD, EUR, GBP) |
| `start_at` | Inclusive start timestamp |
| `original_close_at` | Original exclusive bid deadline |
| `close_at` | Current exclusive deadline, updated only by extensions |
| `forced_close_at` | Immutable hard cap |
| `service_date` | ISO date of pickup/service |
| `british_enabled` | Boolean stored as 0/1 |
| `trigger_minutes`, `extension_minutes` | X and Y, positive whole minutes |
| `triggers` | JSON array of selected trigger keys; three fixed choices do not need a separate table |
| `created_at` | Creation timestamp |

Database checks enforce `start < original_close <= current_close <= forced_close` and `original_close < forced_close`. The API also validates dates, currency, field lengths, trigger keys, and numeric ranges. Status is computed, not stored, so it cannot go stale.

## quotes

One immutable row per accepted quote, including every revision.

| Columns | Meaning |
| --- | --- |
| `id` | Integer primary key; insertion order also identifies the latest quote |
| `rfq_id` | Foreign key to `rfqs.id` |
| `carrier`, `carrier_key` | Display name and normalized identity (Unicode compatibility + collapsed whitespace + case folding) |
| `freight_cents`, `origin_cents`, `destination_cents` | Nonnegative amounts in minor currency units |
| `total_cents` | Positive sum of the three amounts; checked by the database |
| `transit_days` | Positive integer transit duration |
| `valid_until` | Quote validity timestamp |
| `submitted_at` | Server-recorded acceptance timestamp |

Index `(rfq_id, carrier_key, id DESC)` supports latest-quote lookup. A supplier's latest row per RFQ is the active quote; earlier rows remain visible as superseded. Rankings sort active quotes by total. Unique current totals and decreasing own revisions are enforced inside the serialized bid transaction because a normal UNIQUE constraint on immutable history would incorrectly reject prices used only in superseded quotes.

A separate supplier table would imply a supplier registration lifecycle that this assignment does not require. Identity is scoped to an RFQ and derived from the carrier name. A production system should replace this with authenticated supplier IDs.

## events

Append-only activity created in the same transaction as its action.

| Columns | Meaning |
| --- | --- |
| `id` | Integer primary key; deterministic activity order |
| `rfq_id` | Foreign key to `rfqs.id` |
| `kind` | `created`, `bid`, or `extension` |
| `occurred_at` | Server timestamp |
| `details` | JSON event payload |

Bid payloads include quote ID, carrier, and total. Extension payloads include quote ID, old/new close, all matched triggers, whether the hard cap was reached, and a human-readable reason. Index `(rfq_id, id DESC)` supports the newest-first activity log. Rejected bids create no quote, event, or deadline change. This is application-level history, not a tamper-proof audit system.

## Conventions and relationships

```text
rfqs (1) ─────< (many) quotes
     (1) ─────< (many) events
```

All timestamp columns use UTC Unix milliseconds; the API returns ISO strings. Money uses integers to avoid floating-point comparison errors. Foreign keys are enabled on every connection. SQLite WAL and `BEGIN IMMEDIATE` serialize writes, including rank comparisons and deadline updates. The API has no delete operation, preserving historical rows.
