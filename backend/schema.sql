PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS rfqs (
    id INTEGER PRIMARY KEY,
    reference TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    currency TEXT NOT NULL CHECK(currency IN ('INR','USD','EUR','GBP')),
    start_at INTEGER NOT NULL,
    original_close_at INTEGER NOT NULL,
    close_at INTEGER NOT NULL,
    forced_close_at INTEGER NOT NULL,
    service_date TEXT NOT NULL,
    british_enabled INTEGER NOT NULL CHECK(british_enabled IN (0,1)),
    trigger_minutes INTEGER NOT NULL CHECK(trigger_minutes > 0),
    extension_minutes INTEGER NOT NULL CHECK(extension_minutes > 0),
    triggers TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    CHECK(start_at < original_close_at),
    CHECK(original_close_at <= close_at),
    CHECK(original_close_at < forced_close_at),
    CHECK(close_at <= forced_close_at)
);
CREATE TABLE IF NOT EXISTS quotes (
    id INTEGER PRIMARY KEY,
    rfq_id INTEGER NOT NULL REFERENCES rfqs(id),
    carrier TEXT NOT NULL,
    carrier_key TEXT NOT NULL,
    freight_cents INTEGER NOT NULL CHECK(freight_cents >= 0),
    origin_cents INTEGER NOT NULL CHECK(origin_cents >= 0),
    destination_cents INTEGER NOT NULL CHECK(destination_cents >= 0),
    total_cents INTEGER NOT NULL CHECK(total_cents > 0),
    transit_days INTEGER NOT NULL CHECK(transit_days > 0),
    valid_until INTEGER NOT NULL,
    submitted_at INTEGER NOT NULL,
    CHECK(total_cents = freight_cents + origin_cents + destination_cents)
);
CREATE INDEX IF NOT EXISTS quotes_supplier ON quotes(rfq_id, carrier_key, id DESC);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    rfq_id INTEGER NOT NULL REFERENCES rfqs(id),
    kind TEXT NOT NULL CHECK(kind IN ('created','bid','extension')),
    occurred_at INTEGER NOT NULL,
    details TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_rfq ON events(rfq_id, id DESC);
