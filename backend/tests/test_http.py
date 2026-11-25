import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(Path(self.temp.name) / 'http.sqlite3'))
        self.client.__enter__()
        self.now = datetime.now(timezone.utc)

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def rfq_payload(self, **changes):
        data = dict(name='HTTP Freight', reference='HTTP-1', currency='INR',
                    start_at=(self.now-timedelta(minutes=1)).isoformat(),
                    close_at=(self.now+timedelta(minutes=5)).isoformat(),
                    forced_close_at=(self.now+timedelta(minutes=30)).isoformat(),
                    service_date='2026-12-01', british_enabled=True, trigger_minutes=10,
                    extension_minutes=5, triggers=['bid_received', 'rank_change', 'l1_change'])
        return {**data, **changes}

    def quote_payload(self, **changes):
        return dict(carrier='Test A', freight='100', origin='0', destination='0', transit_days=2,
                    valid_until=(self.now+timedelta(days=1)).isoformat()) | changes

    def test_static_files(self):
        index = self.client.get('/')
        self.assertEqual(index.status_code, 200)
        self.assertIn('text/html', index.headers['content-type'])
        assets = re.findall(r'(?:src|href)="(/assets/[^" ]+)"', index.text)
        self.assertEqual(len(assets), 2)
        for path in assets:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertGreater(len(response.content), 100)

    def test_create_bid_and_read(self):
        response = self.client.post('/api/rfqs', json=self.rfq_payload())
        self.assertEqual(response.status_code, 201)
        rfq_id = response.json()['id']
        path = f'/api/rfqs/{rfq_id}/quotes'
        first = self.client.post(path, json=self.quote_payload())
        self.assertEqual(first.status_code, 201)
        self.assertFalse(first.json()['extended'])
        second = self.client.post(path, json=self.quote_payload(carrier='Test B', freight='90'))
        self.assertEqual(second.status_code, 201)
        self.assertTrue(second.json()['extended'])
        detail = self.client.get(f'/api/rfqs/{rfq_id}').json()
        self.assertEqual(detail['rankings'][0]['carrier'], 'Test B')
        self.assertEqual(detail['rfq']['extension_count'], 1)
        self.assertEqual(detail['rfq']['bid_count'], 2)
        self.assertEqual(self.client.get('/api/rfqs').status_code, 200)

    def test_fastapi_validation_and_error_envelope(self):
        for body in ['not json', '[]', '{"broken"', '{}']:
            with self.subTest(body=body):
                response = self.client.post('/api/rfqs', content=body, headers={'content-type': 'application/json'})
                self.assertEqual(response.status_code, 422)
                self.assertIsInstance(response.json()['error'], str)
        for changes in [dict(trigger_minutes=0), dict(triggers=['unknown']),
                        dict(forced_close_at=self.rfq_payload()['close_at']),
                        dict(start_at='2026-11-25T09:00:00'), dict(extra='unrecognized')]:
            with self.subTest(changes=changes):
                response = self.client.post('/api/rfqs', json=self.rfq_payload(**changes))
                self.assertEqual(response.status_code, 422)
                self.assertIn('error', response.json())
        self.assertEqual(self.client.post('/api/rfqs', content='text', headers={'content-type': 'text/plain'}).status_code, 422)
        self.assertEqual(self.client.get('/api/rfqs/not-a-number').status_code, 422)
        self.assertEqual(self.client.put('/api/rfqs', json={}).status_code, 405)

    def test_conflict_rejections_do_not_write(self):
        rfq_id = self.client.post('/api/rfqs', json=self.rfq_payload()).json()['id']
        path = f'/api/rfqs/{rfq_id}/quotes'
        self.client.post(path, json=self.quote_payload())
        tie = self.client.post(path, json=self.quote_payload(carrier='Test B'))
        self.assertEqual(tie.status_code, 409)
        self.assertIn('Equal totals', tie.json()['error'])
        duplicate = self.client.post('/api/rfqs', json=self.rfq_payload())
        self.assertEqual(duplicate.status_code, 409)
        invalid = self.client.post(path, json=self.quote_payload(carrier='Test C', freight='1.001'))
        self.assertEqual(invalid.status_code, 422)
        detail = self.client.get(f'/api/rfqs/{rfq_id}').json()
        self.assertEqual(detail['rfq']['bid_count'], 1)
        self.assertEqual(len(detail['events']), 2)

    def test_missing_routes_and_static_traversal(self):
        for path in ['/missing', '/api/rfqs/99999', '/../server.py', '/assets/../server.py', '/assets/missing.js']:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertIn('error', response.json())

    def test_api_only_deployment_needs_no_frontend(self):
        with TestClient(create_app(Path(self.temp.name) / 'api-only.sqlite3', serve_frontend=False)) as client:
            self.assertEqual(client.get('/api/rfqs').status_code, 200)
            self.assertEqual(client.get('/docs').status_code, 200)
            self.assertEqual(client.get('/').status_code, 404)
            self.assertEqual(client.get('/assets/missing.js').status_code, 404)

    def test_separate_frontend_cors(self):
        origin = 'https://rfq.example.test'
        app = create_app(Path(self.temp.name) / 'cors.sqlite3', serve_frontend=False,
                         allowed_origins=[origin])
        with TestClient(app) as client:
            headers = {'Origin': origin, 'Access-Control-Request-Method': 'POST',
                       'Access-Control-Request-Headers': 'Content-Type'}
            allowed = client.options('/api/rfqs', headers=headers)
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(allowed.headers['access-control-allow-origin'], origin)
            actual = client.get('/api/rfqs', headers={'Origin': origin})
            self.assertEqual(actual.headers['access-control-allow-origin'], origin)
            headers['Origin'] = 'https://other.example.test'
            denied = client.options('/api/rfqs', headers=headers)
            self.assertEqual(denied.status_code, 400)
            self.assertNotIn('access-control-allow-origin', denied.headers)

    def test_documented_request_models(self):
        self.assertEqual(self.client.get('/docs').status_code, 200)
        spec = self.client.get('/openapi.json').json()
        self.assertIn('/api/rfqs', spec['paths'])
        self.assertIn('/api/rfqs/{rfq_id}/quotes', spec['paths'])
        models = spec['components']['schemas']
        self.assertIn('RFQCreate', models)
        self.assertIn('QuoteCreate', models)
        self.assertIn('triggers', models['RFQCreate']['properties'])

    def test_closed_auction_returns_conflict(self):
        path = Path(self.temp.name) / 'closed.sqlite3'
        clock = [self.now]
        with TestClient(create_app(path, clock=lambda: clock[0])) as client:
            rfq_id = client.post('/api/rfqs', json=self.rfq_payload()).json()['id']
            clock[0] += timedelta(minutes=5)
            response = client.post(f'/api/rfqs/{rfq_id}/quotes', json=self.quote_payload())
            self.assertEqual(response.status_code, 409)
            self.assertEqual(client.get(f'/api/rfqs/{rfq_id}').json()['rfq']['bid_count'], 0)

    def test_seed_and_existing_database_on_restart(self):
        path = Path(self.temp.name) / 'seed.sqlite3'
        with TestClient(create_app(path, seed_demo=True)) as client:
            first = client.get('/api/rfqs').json()['rfqs']
            self.assertEqual(len(first), 3)
            self.assertEqual(sum(r['bid_count'] for r in first), 4)
        with TestClient(create_app(path, seed_demo=True)) as client:
            second = client.get('/api/rfqs').json()['rfqs']
            self.assertEqual([(r['id'], r['name'], r['bid_count']) for r in first],
                             [(r['id'], r['name'], r['bid_count']) for r in second])


if __name__ == '__main__':
    unittest.main()
