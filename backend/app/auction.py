"""Auction rules and SQLite transactions. HTTP routes live in main.py."""
import json
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import QuoteCreate, RFQCreate

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
UTC = timezone.utc


def utcnow():
    return datetime.now(UTC)


def millis(value):
    return int(value.timestamp() * 1000)


def iso(value):
    return datetime.fromtimestamp(value / 1000, UTC).isoformat(timespec='milliseconds')


class Invalid(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class Store:
    def __init__(self, path, clock=utcnow):
        self.path, self.clock = str(path), clock
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript((BACKEND_ROOT / 'schema.sql').read_text())

    @contextmanager
    def connection(self, write=False):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            if write:
                db.commit()
        except Exception:
            if write:
                db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def get(db, rfq_id):
        row = db.execute('SELECT * FROM rfqs WHERE id=?', (rfq_id,)).fetchone()
        if row is None:
            raise Invalid('RFQ not found.', 404)
        return dict(row)

    @staticmethod
    def latest(db, rfq_id):
        rows = db.execute('''SELECT q.* FROM quotes q WHERE rfq_id=? AND NOT EXISTS
            (SELECT 1 FROM quotes newer WHERE newer.rfq_id=q.rfq_id
             AND newer.carrier_key=q.carrier_key AND newer.id>q.id)
            ORDER BY total_cents, id''', (rfq_id,)).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def event(db, rfq_id, kind, now, details):
        db.execute('INSERT INTO events(rfq_id,kind,occurred_at,details) VALUES(?,?,?,?)',
                   (rfq_id, kind, now, json.dumps(details)))

    @staticmethod
    def public_quote(q):
        return {**{k: v for k, v in q.items() if k != 'carrier_key'},
                'submitted_at': iso(q['submitted_at']), 'valid_until': iso(q['valid_until'])}

    def public_rfq(self, db, row, now):
        current = self.latest(db, row['id'])
        if now < row['start_at']:
            status = 'Scheduled'
        elif now < row['close_at']:
            status = 'Active'
        else:
            status = 'Force Closed' if row['close_at'] == row['forced_close_at'] else 'Closed'
        return {**row, **{k: iso(row[k]) for k in
                ('start_at', 'original_close_at', 'close_at', 'forced_close_at', 'created_at')},
                'triggers': json.loads(row['triggers']), 'british_enabled': bool(row['british_enabled']),
                'status': status, 'lowest_cents': current[0]['total_cents'] if current else None,
                'suppliers': len(current),
                'bid_count': db.execute('SELECT count(*) FROM quotes WHERE rfq_id=?', (row['id'],)).fetchone()[0],
                'extension_count': db.execute("SELECT count(*) FROM events WHERE rfq_id=? AND kind='extension'",
                                              (row['id'],)).fetchone()[0]}

    def list(self):
        with self.connection() as db:
            db.execute('BEGIN')  # One consistent snapshot across the list and rankings.
            now = millis(self.clock())
            return {'rfqs': [self.public_rfq(db, dict(r), now) for r in
                             db.execute('SELECT * FROM rfqs ORDER BY id DESC').fetchall()],
                    'server_time': iso(now)}

    def detail(self, rfq_id):
        with self.connection() as db:
            db.execute('BEGIN')
            now = millis(self.clock())
            row = self.get(db, rfq_id)
            current = self.latest(db, rfq_id)
            latest_ids = {q['id'] for q in current}
            history = [dict(q) for q in db.execute(
                'SELECT * FROM quotes WHERE rfq_id=? ORDER BY total_cents,id', (rfq_id,))]
            events = [{**dict(e), 'occurred_at': iso(e['occurred_at']), 'details': json.loads(e['details'])}
                      for e in db.execute('SELECT * FROM events WHERE rfq_id=? ORDER BY id DESC', (rfq_id,))]
            return {'rfq': self.public_rfq(db, row, now),
                    'rankings': [{**self.public_quote(q), 'rank': i + 1} for i, q in enumerate(current)],
                    'quotes': [{**self.public_quote(q), 'current': q['id'] in latest_ids} for q in history],
                    'events': events, 'server_time': iso(now)}

    def create(self, data: RFQCreate):
        name, reference, currency = data.name, data.reference.upper(), data.currency
        start, close, forced = map(millis, (data.start_at, data.close_at, data.forced_close_at))
        service_date = data.service_date.isoformat()
        enabled = data.british_enabled
        x, y = data.trigger_minutes, data.extension_minutes
        triggers = sorted(set(data.triggers))
        with self.connection(write=True) as db:
            now = millis(self.clock())
            if close <= now:
                raise Invalid('Bid close must be in the future.')
            try:
                cur = db.execute('''INSERT INTO rfqs(reference,name,currency,start_at,original_close_at,
                    close_at,forced_close_at,service_date,british_enabled,trigger_minutes,extension_minutes,
                    triggers,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (reference, name, currency, start, close, close, forced, service_date,
                     int(enabled), x, y, json.dumps(triggers), now))
            except sqlite3.IntegrityError:
                raise Invalid('That reference ID already exists.', 409) from None
            self.event(db, cur.lastrowid, 'created', now, {'message': 'RFQ created.'})
            return cur.lastrowid

    def bid(self, rfq_id, data: QuoteCreate):
        carrier = data.carrier
        key = unicodedata.normalize('NFKC', carrier).casefold()
        amounts = [int(amount * 100) for amount in (data.freight, data.origin, data.destination)]
        total = sum(amounts)
        if total <= 0:
            raise Invalid('The quote total must be greater than zero.')
        transit = data.transit_days
        validity = millis(data.valid_until)
        with self.connection(write=True) as db:
            # Lock first, then read the clock and price: concurrent bids cannot use stale state.
            now = millis(self.clock())
            row = self.get(db, rfq_id)
            if now < row['start_at']:
                raise Invalid('Bidding has not started.', 409)
            if now >= row['close_at'] or now >= row['forced_close_at']:
                raise Invalid('This auction is closed. No more bids can be accepted.', 409)
            if validity <= now:
                raise Invalid('Quote validity must be in the future.')
            before = self.latest(db, rfq_id)
            own = next((q for q in before if q['carrier_key'] == key), None)
            if own and total >= own['total_cents']:
                raise Invalid('A revised quote must be strictly below your previous total.', 409)
            if any(q['carrier_key'] != key and q['total_cents'] == total for q in before):
                raise Invalid('Equal totals are not allowed. Another supplier already has this total.', 409)
            cur = db.execute('''INSERT INTO quotes(rfq_id,carrier,carrier_key,freight_cents,origin_cents,
                destination_cents,total_cents,transit_days,valid_until,submitted_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)''', (rfq_id, carrier, key, *amounts, total, transit, validity, now))
            self.event(db, rfq_id, 'bid', now, {'quote_id': cur.lastrowid, 'carrier': carrier,
                                              'total_cents': total, 'message': f'{carrier} submitted a quote.'})
            after = self.latest(db, rfq_id)
            old_ranks = {q['carrier_key']: i for i, q in enumerate(before)}
            new_ranks = {q['carrier_key']: i for i, q in enumerate(after)}
            matched = ['bid_received']
            if any(new_ranks[k] != v for k, v in old_ranks.items()):
                matched.append('rank_change')
            if before and before[0]['carrier_key'] != after[0]['carrier_key']:
                matched.append('l1_change')
            matched = [t for t in matched if t in json.loads(row['triggers'])]
            # The first bid has no previous lowest to beat and never extends the auction.
            improves_lowest = bool(before) and total < before[0]['total_cents']
            in_window = now >= row['close_at'] - row['trigger_minutes'] * 60000
            extended = False
            if row['british_enabled'] and improves_lowest and in_window and matched:
                new_close = min(row['close_at'] + row['extension_minutes'] * 60000, row['forced_close_at'])
                if new_close > row['close_at']:
                    db.execute('UPDATE rfqs SET close_at=? WHERE id=?', (new_close, rfq_id))
                    self.event(db, rfq_id, 'extension', now, {
                        'quote_id': cur.lastrowid, 'old_close_at': iso(row['close_at']),
                        'new_close_at': iso(new_close), 'triggers': matched,
                        'capped': new_close == row['forced_close_at'],
                        'message': 'New lowest quote inside the trigger window; auction extended.'})
                    extended = True
            return {'quote_id': cur.lastrowid, 'extended': extended}


def seed(store):
    if store.list()['rfqs']:
        return
    now = utcnow()
    def payload(ref, name, close_minutes, trigger='bid_received'):
        return RFQCreate(reference=ref, name=name, currency='INR', start_at=(now-timedelta(hours=1)).isoformat(),
                    close_at=(now+timedelta(minutes=close_minutes)).isoformat(),
                    forced_close_at=(now+timedelta(minutes=close_minutes+30)).isoformat(),
                    service_date=(now+timedelta(days=7)).date().isoformat(), british_enabled=True,
                    trigger_minutes=10, extension_minutes=5, triggers=[trigger])
    a = store.create(payload('RFQ-001', 'Mumbai to Bengaluru · Road freight', 8))
    b = store.create(payload('RFQ-002', 'Pune to Delhi · Express shipment', 120, 'l1_change'))
    for rfq_id, carrier, freight in [(a, 'Blue Dart', '42000'), (a, 'Delhivery', '39500'),
                                      (a, 'TCI Express', '41000'), (b, 'Gati', '68000')]:
        store.bid(rfq_id, QuoteCreate(carrier=carrier, freight=freight, origin='1500', destination='1000',
                              transit_days=3, valid_until=(now+timedelta(days=10)).isoformat()))
    scheduled = payload('RFQ-003', 'Chennai to Hyderabad · Weekly delivery', 180)
    scheduled.start_at = now + timedelta(hours=1)
    store.create(scheduled)
