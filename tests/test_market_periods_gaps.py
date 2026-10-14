import json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from decimal import Decimal as D
from app.local_market import decode_history,LocalStore
from app.calculator import demand,demand_text,demand_tip
from app.price_gaps import find_gaps
from app.market_memory import MarketMemory,archive_volumes

NOW=datetime(2026,10,14,13,30,tzinfo=timezone.utc)


def ticks(dt):return int((dt-datetime(1,1,1,tzinfo=timezone.utc)).total_seconds())*10_000_000


def history(scale,count=100,now=NOW):
    days,bucket=((1,1),(7,6),(28,24))[scale];end=now.replace(hour=now.hour//bucket*bucket,minute=0,second=0,microsecond=0)
    points=[dict(Timestamp=ticks(end-timedelta(hours=bucket*n)),ItemAmount=count,SilverAmount=count*40000*10000) for n in range(1,days*24//bucket+1)]
    return dict(AlbionId=42,LocationId='0007',QualityLevel=1,Timescale=scale,MarketHistories=points)


def quote(levels=None,stamp=None):
    stamp=stamp or NOW.isoformat()
    return dict(item_id='T4_MAIN_SWORD',city='Thetford',quality=1,local_observations=dict(
        sell_price_min_date=stamp,sell_price_min_levels=levels or [dict(price=40000,quantity=100),dict(price=60000,quantity=40)]))


SETTINGS=dict(auto_rules=False,setup='2.5',tax='8',other='0')


class MarketPeriodsGapsTests(unittest.TestCase):
    def test_http_capture_accepts_all_three_game_views(self):
        from app.local_market import make_server
        from urllib.request import Request,urlopen
        import threading
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'prices.sqlite';counts=[];server=make_server(path,'period-test',counts.append,0)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                for scale in (2,1,0):
                    payload=history(scale,now=datetime.now(timezone.utc))
                    payload['AlbionId']=next(k for k,v in __import__('app.local_market',fromlist=['item_indexes']).item_indexes().items() if v=='T4_MAIN_SWORD')
                    with urlopen(Request(f'http://127.0.0.1:{server.server_port}/period-test/markethistories.ingest',data=json.dumps(payload).encode()),timeout=3) as response:self.assertEqual(response.status,200)
                store=LocalStore(path)
                try:
                    self.assertEqual(store.db.execute('SELECT COUNT(*) FROM local_history_windows').fetchone()[0],3)
                    self.assertEqual(store.histories({'T4_MAIN_SWORD'})[0]['period_days'],1)
                    self.assertTrue(all(count<0 for count in counts));self.assertEqual(len(counts),3)
                finally:store.close()
            finally:server.shutdown();server.server_close();thread.join()

    def test_captured_orders_keep_other_levels_for_gap_detection(self):
        from app.local_market import decode_orders
        with tempfile.TemporaryDirectory() as folder:
            store=LocalStore(Path(folder)/'prices.sqlite');now=datetime.now(timezone.utc)
            try:
                raw=dict(ItemTypeId='T4_MAIN_SWORD',LocationId='0007',QualityLevel=1,EnchantmentLevel=0,AuctionType='offer',Expires=(now+timedelta(days=1)).isoformat())
                store.save(decode_orders({'Orders':[dict(raw,Id=1,UnitPriceSilver=40000*10000,Amount=100),dict(raw,Id=2,UnitPriceSilver=60000*10000,Amount=40)]}))
                prices=__import__('app.local_market',fromlist=['merge_local']).merge_local([],store.prices())
                result=find_gaps(prices,[],SETTINGS,datetime.now(timezone.utc))[0]
                self.assertEqual(result['quantity'],100);self.assertEqual(result['reference'],60000)
            finally:store.close()
    def test_all_game_views_have_daily_units_and_correct_bucket_coverage(self):
        for scale,period,bucket,expected in [(0,1,1,2400),(1,7,6,400),(2,28,24,100)]:
            with self.subTest(scale=scale):
                h=decode_history(history(scale),{42:'T4_MAIN_SWORD'},NOW);info=demand(h,NOW)
                self.assertEqual(info['per_day'],expected);self.assertEqual(info['period_days'],period)
                self.assertEqual(info['bucket_hours'],bucket);self.assertEqual(info['coverage'],1)
                self.assertEqual(info['average'],40000)
                self.assertIn({1:'24 ч.',7:'7 дней',28:'4 недели'}[period],demand_text(info))
        self.assertIsNone(decode_history(dict(history(0),Timescale=True),{42:'T4_MAIN_SWORD'},NOW))

    def test_incomplete_future_duplicate_and_outside_buckets_do_not_count(self):
        raw=history(0);raw['MarketHistories']+=raw['MarketHistories'][:1]
        raw['MarketHistories']+=[dict(Timestamp=ticks(NOW.replace(minute=0)),ItemAmount=999999,SilverAmount=10000),dict(Timestamp=ticks(NOW+timedelta(days=1)),ItemAmount=999999,SilverAmount=10000),dict(Timestamp=ticks(NOW-timedelta(days=30)),ItemAmount=999999,SilverAmount=10000)]
        h=decode_history(raw,{42:'T4_MAIN_SWORD'},NOW);self.assertEqual(demand(h,NOW)['total'],2400)
        sparse=decode_history(dict(history(2),MarketHistories=history(2)['MarketHistories'][:1]),{42:'T4_MAIN_SWORD'},NOW)
        result=demand(sparse,NOW);self.assertEqual(result['per_day'],100/28);self.assertEqual(result['coverage'],1/28)
        self.assertIn('нижняя оценка',demand_tip(result))
        sparse['data'][0]['item_count']=1
        self.assertIn('(0,04 шт./день)',demand_text(demand(sparse,NOW)))

    def test_views_are_retained_separately_and_latest_view_is_selected(self):
        # Decode with the real clock so LocalStore's one-day freshness policy
        # stays meaningful regardless of the calendar date of the test runner.
        with tempfile.TemporaryDirectory() as folder:
            store=LocalStore(Path(folder)/'prices.sqlite')
            try:
                base=datetime.now(timezone.utc)
                for scale in (2,0,1):
                    h=decode_history(history(scale),{42:'T4_MAIN_SWORD'},NOW)
                    h['observed']=(base+timedelta(seconds=scale-3)).isoformat();store.save_history(h)
                self.assertEqual(store.db.execute('SELECT COUNT(*) FROM local_history_windows').fetchone()[0],3)
                self.assertEqual(store.histories({'T4_MAIN_SWORD'})[0]['period_days'],28)
                h=decode_history(history(0),{42:'T4_MAIN_SWORD'},NOW);h['observed']=datetime.now(timezone.utc).isoformat();store.save_history(h)
                self.assertEqual(store.histories({'T4_MAIN_SWORD'})[0]['period_days'],1)
                self.assertEqual(store.histories({'T5_MAIN_SWORD'}),[])
            finally:store.close()

    def test_archive_does_not_sum_daily_and_six_hour_versions_of_same_trades(self):
        with tempfile.TemporaryDirectory() as folder:
            store=MarketMemory(Path(folder)/'prices.sqlite')
            try:
                store.db.execute('INSERT INTO volume_history VALUES(?,?,?,?,?,?,?)',('T4_MAIN_SWORD','Thetford',1,(NOW-timedelta(days=30)).isoformat(),400,40000,'Local'))
                self.assertEqual(store.volumes('T4_MAIN_SWORD','Thetford')[0]['bucket_hours'],6)
                a=decode_history(history(1),{42:'T4_MAIN_SWORD'},NOW);b=decode_history(history(2,400),{42:'T4_MAIN_SWORD'},NOW)
                a['observed']=(NOW-timedelta(minutes=1)).isoformat();b['observed']=NOW.isoformat()
                archive_volumes(store.db,[a,b],'Local');store.db.commit();rows=store.volumes('T4_MAIN_SWORD','Thetford')
                self.assertEqual(len(rows),28);self.assertTrue(all(r['count']==400 and r['period_days']==28 for r in rows))
                self.assertGreater(store.db.execute('SELECT COUNT(*) FROM volume_windows').fetchone()[0],28)
            finally:store.close()

    def test_hundred_at_40000_to_60000_includes_sell_fees_and_upfront_cash(self):
        result=find_gaps([quote()],[],SETTINGS,NOW)[0]
        self.assertEqual(result['quantity'],100);self.assertEqual(result['purchase'],D(4000000))
        self.assertEqual(result['target'],59999);self.assertEqual(result['profit'],D('1369910.5'))
        self.assertEqual(result['cash'],D('4149997.5'));self.assertEqual(result['remaining_quantity'],40)
        self.assertEqual(result['demand']['kind'],'unknown')

    def test_small_gaps_after_fees_or_insufficient_cash_are_rejected(self):
        self.assertEqual(find_gaps([quote([dict(price=40000,quantity=100),dict(price=42000,quantity=20)])],[],SETTINGS,NOW),[])
        self.assertEqual(find_gaps([quote()],[],dict(SETTINGS,price_gaps=dict(budget=4000000)),NOW),[])
        self.assertEqual(len(find_gaps([quote()],[],dict(SETTINGS,price_gaps=dict(budget=4150000)),NOW)),1)

    def test_duplicate_price_levels_are_aggregated_and_stale_pages_rejected(self):
        levels=[dict(price=40000,quantity=50),dict(price=40000,quantity=50),dict(price=60000,quantity=40)]
        self.assertEqual(find_gaps([quote(levels)],[],SETTINGS,NOW)[0]['quantity'],100)
        for stamp in [(NOW-timedelta(minutes=16)).isoformat(),(NOW+timedelta(minutes=1)).isoformat()]:self.assertEqual(find_gaps([quote(stamp=stamp)],[],SETTINGS,NOW),[])
        self.assertEqual(find_gaps([dict(item_id='T4_MAIN_SWORD',city='Thetford',quality=1,sell_price_min=40000)],[],SETTINGS,NOW),[])
        large=[dict(price=10000+n,quantity=1) for n in range(4999)]+[dict(price=60000,quantity=40)]
        result=find_gaps([quote(large)],[],SETTINGS,NOW)[0]
        self.assertEqual(result['quantity'],4999);self.assertEqual(len(result['levels']),5000)

    def test_missing_expenses_are_marked_and_demand_uses_matching_quality(self):
        h=decode_history(history(2),{42:'T4_MAIN_SWORD'},NOW)
        result=find_gaps([quote()],[dict(h,quality=2)],dict(SETTINGS,other=''),NOW)[0]
        self.assertTrue(result['pending']);self.assertEqual(result['demand']['kind'],'unknown')
        self.assertEqual(find_gaps([quote()],[h],SETTINGS,NOW)[0]['demand']['per_day'],100)
