import unittest
from datetime import datetime,timezone,timedelta
from app.market_snapshot import merge_observation

class SnapshotTests(unittest.TestCase):
    def test_old_ui_result_cannot_replace_newer_cached_side(self):
        now=datetime.now(timezone.utc)
        recent=(now-timedelta(minutes=1)).isoformat();old=(now-timedelta(hours=1)).isoformat()
        cached=dict(item_id='T2_ORE',city='Fort Sterling',quality=1,sell_price_min=16,sell_price_min_date=recent,sell_price_min_source='fresh')
        ui=dict(cached,sell_price_min=42,sell_price_min_date=old,sell_price_min_source='old',buy_price_max=12,buy_price_max_date=recent)
        result=merge_observation(cached,ui)
        self.assertEqual(result['sell_price_min'],16);self.assertEqual(result['sell_price_min_source'],'fresh')
        self.assertEqual(result['buy_price_max'],12)
        self.assertEqual(cached['sell_price_min'],16)

    def test_zero_or_future_price_does_not_replace_valid_quote(self):
        now=datetime.now(timezone.utc)
        cached=dict(item_id='A',city='B',quality=1,sell_price_min=16,sell_price_min_date=(now-timedelta(minutes=5)).isoformat())
        for new in [dict(cached,sell_price_min=0),dict(cached,sell_price_min=99,sell_price_min_date=(now+timedelta(days=1)).isoformat())]:
            self.assertEqual(merge_observation(cached,new)['sell_price_min'],16)
