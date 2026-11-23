import unittest
from datetime import datetime, timezone, timedelta
from systems.reaction_roles.services.statistics import calculate_statistics, report_from_guild

NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)
def entry(event, member='1', role='2', days=0, source='button'):
    return {'at': (NOW - timedelta(days=days)).isoformat(), 'event': event,
            'member_id': member, 'role_id': role, 'source': source}

class StatisticsTests(unittest.TestCase):
    def test_counts_and_users(self):
        data = [entry('grant'), entry('grant', '2'), entry('revoke'), entry('denied', '3'), entry('expire', '2')]
        r = calculate_statistics(data, now=NOW)
        self.assertEqual(r['counts']['grant'], 2)
        self.assertEqual(r['counts']['revoke'], 1)
        self.assertEqual(r['unique_users'], 2)
        self.assertEqual(r['top_roles'], [('2', 2)])
    def test_period_filters(self):
        data = [entry('grant', days=3), entry('grant', days=20), entry('grant', days=50)]
        self.assertEqual(calculate_statistics(data, 7, NOW)['events'], 1)
        self.assertEqual(calculate_statistics(data, 30, NOW)['events'], 2)
        self.assertEqual(calculate_statistics(data, None, NOW)['events'], 3)
    def test_empty_and_malformed(self):
        r = calculate_statistics([None, {}, {'event':'grant','at':'invalid'}, entry('bogus')], now=NOW)
        self.assertEqual(r['events'], 0)
        self.assertEqual(r['unique_users'], 0)
    def test_future_ignored(self):
        self.assertEqual(calculate_statistics([entry('grant', days=-2)], now=NOW)['events'], 0)
    def test_invalid_period(self):
        with self.assertRaises(ValueError):
            calculate_statistics([], days=1)
    def test_missing_audit(self):
        r = report_from_guild({})
        self.assertEqual(r['events'], 0)
        self.assertEqual(r['history_limit'], 500)
    def test_daily_and_sources(self):
        r = calculate_statistics([entry('grant', source='button'), entry('revoke', source='select')], now=NOW)
        self.assertEqual(r['daily'], [('2026-10-11', 2)])
        self.assertEqual(len(r['sources']), 2)
