import unittest
from datetime import datetime, timezone
from app.models import quote

class PricesTest(unittest.TestCase):
    def test_missing_not_zero(self):
        self.assertIsNone(quote({'sell_price_min':0},'sell_price_min')[0])
    def test_missing_timestamp(self):
        self.assertIsNone(quote({'sell_price_min':100},'sell_price_min')[0])
    def test_stale(self):
        row={'sell_price_min':100,'sell_price_min_date':'2026-10-02T10:00:00Z'}
        self.assertEqual(quote(row,'sell_price_min',now=datetime(2026,10,2,11,tzinfo=timezone.utc))[2],'устарело')
    def test_sides_independent(self):
        row={'sell_price_min':100,'sell_price_min_date':'2026-10-02T10:00:00Z','buy_price_max':0}
        self.assertIsNone(quote(row,'buy_price_max')[0])
        self.assertEqual(quote(row,'sell_price_min')[0],100)
    def test_naive_flagged(self):
        row={'sell_price_min':100,'sell_price_min_date':'2026-10-02T10:00:00'}
        self.assertIn('требует проверки',quote(row,'sell_price_min')[2])
    def test_future(self):
        row={'sell_price_min':100,'sell_price_min_date':'2026-10-03T10:00:00Z'}
        self.assertEqual(quote(row,'sell_price_min',now=datetime(2026,10,2,tzinfo=timezone.utc))[2],'дата в будущем')
    def test_malformed(self):
        self.assertIsNone(quote({'sell_price_min':'100'},'sell_price_min')[0])
