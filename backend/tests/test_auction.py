import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier

from pydantic import ValidationError
from app.auction import Invalid, Store
from app.models import RFQCreate, QuoteCreate


class AuctionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.now = datetime(2026, 11, 25, 10, 0, tzinfo=timezone.utc)
        self.store = Store(Path(self.temp.name) / 'test.sqlite3', clock=lambda: self.now)
        self.rfq = self.create()

    def tearDown(self):
        self.temp.cleanup()

    def payload(self, **changes):
        return dict(name='Road freight', reference='RFQ-1', currency='INR',
                    start_at=(self.now-timedelta(hours=1)).isoformat(),
                    close_at=(self.now+timedelta(minutes=10)).isoformat(),
                    forced_close_at=(self.now+timedelta(minutes=22)).isoformat(),
                    service_date='2026-12-01', british_enabled=True, trigger_minutes=10,
                    extension_minutes=5, triggers=['bid_received'], **changes)

    def create(self, **changes):
        data = self.payload()
        data.update(changes)
        return self.store.create(RFQCreate.model_validate(data))

    def quote(self, carrier='A', freight='100', **changes):
        data = dict(carrier=carrier, freight=freight, origin='0', destination='0',
                    transit_days=3, valid_until=(self.now+timedelta(days=1)).isoformat())
        data.update(changes)
        return data

    def bid(self, carrier='A', freight='100', **changes):
        return self.store.bid(self.rfq, QuoteCreate.model_validate(self.quote(carrier, freight, **changes)))

    def view(self):
        return self.store.detail(self.rfq)

    def set_triggers(self, triggers):
        with self.store.connection(write=True) as db:
            db.execute('UPDATE rfqs SET triggers=? WHERE id=?', (json.dumps(triggers), self.rfq))

    def test_first_bid_does_not_extend(self):
        self.assertFalse(self.bid()['extended'])
        self.assertEqual(self.view()['rfq']['extension_count'], 0)

    def test_lower_non_leading_quote_is_accepted_without_extension(self):
        self.bid('A', '100')
        self.bid('B', '130')
        self.assertFalse(self.bid('B', '120')['extended'])
        self.assertEqual([q['carrier'] for q in self.view()['rankings']], ['A', 'B'])

    def test_repeated_extensions_are_capped(self):
        self.bid('A', '100')
        self.assertTrue(self.bid('B', '90')['extended'])  # close 10:15
        self.now += timedelta(minutes=5)
        self.assertTrue(self.bid('C', '80')['extended'])  # close 10:20
        self.now += timedelta(minutes=5)
        self.assertTrue(self.bid('D', '70')['extended'])  # capped at 10:22
        self.assertFalse(self.bid('E', '60')['extended'])
        v = self.view()
        self.assertEqual(v['rfq']['close_at'], v['rfq']['forced_close_at'])
        self.assertEqual(v['rfq']['extension_count'], 3)
        self.assertTrue(next(e for e in v['events'] if e['kind']=='extension')['details']['capped'])
        self.now += timedelta(minutes=12)
        self.assertEqual(self.view()['rfq']['status'], 'Force Closed')
        with self.assertRaises(Invalid):
            self.bid('F', '50')

    def test_multiple_matching_triggers_add_only_one_extension(self):
        self.set_triggers(['bid_received','rank_change','l1_change'])
        self.bid('A', '100')
        self.bid('B', '90')
        v = self.view()
        self.assertEqual(v['rfq']['extension_count'], 1)
        event = next(e for e in v['events'] if e['kind']=='extension')
        self.assertEqual(set(event['details']['triggers']), {'bid_received','rank_change','l1_change'})
        self.assertEqual(datetime.fromisoformat(v['rfq']['close_at']).minute, 15)

    def test_leader_improving_own_price_does_not_change_l1_identity(self):
        self.set_triggers(['l1_change'])
        self.bid('A', '100')
        self.assertFalse(self.bid('A', '90')['extended'])
        self.assertTrue(self.bid('B', '80')['extended'])

    def test_rank_trigger_ignores_first_bid_and_unchanged_ranks(self):
        self.set_triggers(['rank_change'])
        self.assertFalse(self.bid('A', '100')['extended'])
        self.assertFalse(self.bid('B', '140')['extended'])
        self.assertFalse(self.bid('C', '120')['extended'])  # B moves but no new low.
        self.assertTrue(self.bid('C', '90')['extended'])

    def test_trigger_window_moves_with_current_close(self):
        self.bid('A', '100')
        self.bid('B', '90')  # close now +15; now is outside updated 10-minute window.
        self.assertFalse(self.bid('C', '80')['extended'])
        self.now += timedelta(minutes=5)  # inclusive window boundary
        self.assertTrue(self.bid('D', '70')['extended'])

    def test_outside_window_no_extension(self):
        self.now -= timedelta(minutes=1)
        self.bid('A', '100')
        self.assertFalse(self.bid('B', '90')['extended'])

    def test_reject_at_exact_close_and_after_without_log_changes(self):
        self.bid()
        self.now += timedelta(minutes=10)
        for offset in (0, 1, 3600):
            self.now += timedelta(seconds=offset)
            with self.assertRaises(Invalid):
                self.bid('B', '90')
        self.assertEqual(self.view()['rfq']['bid_count'], 1)
        self.assertEqual(len(self.view()['events']), 2)

    def test_normal_close_stays_closed_past_forced_deadline(self):
        self.now += timedelta(hours=1)
        self.assertEqual(self.view()['rfq']['status'], 'Closed')

    def test_scheduled_and_exact_start(self):
        start = self.now + timedelta(minutes=2)
        self.rfq = self.create(reference='RFQ-2', start_at=start.isoformat())
        self.assertEqual(self.view()['rfq']['status'], 'Scheduled')
        with self.assertRaises(Invalid):
            self.bid()
        self.now = start
        self.bid()
        self.assertEqual(self.view()['rfq']['status'], 'Active')

    def test_standard_rfq_never_extends(self):
        self.rfq = self.create(reference='RFQ-2', british_enabled=False, triggers=[])
        self.bid('A', '100')
        self.assertFalse(self.bid('B', '90')['extended'])

    def test_ties_rejected_against_current_total(self):
        self.bid('A', '100', origin='5', destination='10')
        with self.assertRaisesRegex(Invalid, 'Equal totals'):
            self.bid('B', '110', origin='5')
        self.assertEqual(self.view()['rfq']['bid_count'], 1)

    def test_revisions_lower_own_total_and_keep_history(self):
        self.bid(' Carrier  A ', '100')
        self.bid('carrier a', '90')
        for price in ('90', '110'):
            with self.assertRaises(Invalid):
                self.bid('CARRIER A', price)
        v = self.view()
        self.assertEqual(len(v['rankings']), 1)
        self.assertEqual(len(v['quotes']), 2)
        self.assertEqual(sum(q['current'] for q in v['quotes']), 1)
        self.assertEqual(v['rankings'][0]['total_cents'], 9000)

    def test_tie_with_superseded_quote_is_allowed(self):
        self.bid('A', '100')
        self.bid('A', '90')
        self.bid('B', '100')
        self.assertEqual(self.view()['rfq']['suppliers'], 2)

    def test_decimal_amounts_sum_exactly(self):
        self.bid(freight='0.10', origin='0.20', destination='0.30')
        self.assertEqual(self.view()['rankings'][0]['total_cents'], 60)

    def test_invalid_quote_fields_do_not_write(self):
        bad = [dict(freight=v) for v in ['NaN','Infinity','-1','1.001','1000000001',True,{},None]]
        bad += [dict(transit_days=v) for v in [0,-1,1.2,True]]
        bad += [dict(carrier=' '), dict(freight='0'), dict(valid_until=self.now.isoformat()),
                dict(valid_until='2026-11-26T10:00:00')]
        for change in bad:
            with self.subTest(change=change), self.assertRaises((Invalid, ValidationError)):
                self.bid(**change)
        self.assertEqual(self.view()['rfq']['bid_count'], 0)
        self.assertEqual(len(self.view()['events']), 1)

    def test_validate_creation(self):
        base = self.payload()
        bad = [dict(forced_close_at=base['close_at']), dict(close_at=base['start_at']),
               dict(trigger_minutes=0), dict(extension_minutes=True), dict(triggers=[]),
               dict(triggers=['unknown']), dict(currency='XXX'), dict(service_date='2026-02-30'),
               dict(start_at='2026-11-25T09:00:00'), dict(close_at=self.now.isoformat()),
               dict(british_enabled='true'), dict(name=' ')]
        for change in bad:
            with self.subTest(change=change), self.assertRaises((Invalid, ValidationError)):
                self.create(reference='RFQ-2', **change)
        with self.assertRaisesRegex(Invalid, 'already exists'):
            self.create(reference='rfq-1')
        self.assertEqual(len(self.store.list()['rfqs']), 1)

    def test_utc_normalization(self):
        p = self.payload()
        p.update(reference='OFFSET',start_at='2026-11-25T14:30:00+05:30',
                 close_at='2026-11-25T15:40:00+05:30',forced_close_at='2026-11-25T15:52:00+05:30')
        new = self.store.create(RFQCreate.model_validate(p))
        self.assertEqual(self.store.detail(new)['rfq']['close_at'], self.view()['rfq']['close_at'])

    def test_not_found(self):
        with self.assertRaises(Invalid) as result:
            self.store.detail(999)
        self.assertEqual(result.exception.status,404)

    def test_concurrent_equal_bids_accept_exactly_one(self):
        self.bid('First', '200')
        barrier = Barrier(2)
        def place(carrier):
            barrier.wait()
            try:
                self.bid(carrier, '100')
                return True
            except Invalid:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(place,['A','B']))
        self.assertEqual(sum(results),1)
        v = self.view()
        self.assertEqual(v['rfq']['bid_count'],2)
        self.assertEqual(v['rfq']['extension_count'],1)
        self.assertEqual(len(v['events']),4)

    def test_persistence_after_reopening(self):
        self.bid()
        reopened = Store(self.store.path, clock=lambda:self.now)
        self.assertEqual(reopened.detail(self.rfq)['rankings'][0]['total_cents'],10000)

    def test_database_enforces_forced_cap(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store.connection(write=True) as db:
                db.execute('UPDATE rfqs SET close_at=forced_close_at+1 WHERE id=?',(self.rfq,))


if __name__ == '__main__':
    unittest.main()
