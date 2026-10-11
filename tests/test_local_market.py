import json,tempfile,threading,unittest
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from datetime import datetime,timezone,timedelta
from app.local_market import make_server,LocalStore,merge_local,decode_orders,SOURCE

class LocalMarketTests(unittest.TestCase):
    def test_screenshot_price_and_legacy_quotes(self):
        order=decode_orders({'Orders':[self.order(ItemTypeId='T4_MAIN_SWORD',UnitPriceSilver=49820000)]})[0]
        self.assertEqual(order[5],4982)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'cache.sqlite';store=LocalStore(path)
            legacy=[dict(price=49820000,amount=1,observed=order[7],expires=order[8])]
            store.db.execute('INSERT INTO local_quotes VALUES(?,?,?,?,?)',('T4_MAIN_SWORD','Thetford',1,'sell_price_min',json.dumps(legacy)));store.db.commit()
            self.assertEqual(store.prices(['T4_MAIN_SWORD'])[0]['sell_price_min'],4982)
            store.save([order]);store.close()
            store=LocalStore(path)
            self.assertEqual(store.prices(['T4_MAIN_SWORD'])[0]['sell_price_min'],4982)
            store.close()
    def order(self,**changes):
        o=dict(Id=1,ItemTypeId='T4_ORE',LocationId='0007',QualityLevel=1,EnchantmentLevel=0,UnitPriceSilver=3210000,Amount=40,AuctionType='offer',Expires=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
        o.update(changes);return o
    def test_http_store_and_replace_latest_page(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'cache.sqlite';counts=[]
            server=make_server(path,'test-secret',counts.append,0)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            def post(endpoint,body):
                return urlopen(Request(base+endpoint,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'}),timeout=3)
            try:
                with post('/test-secret/marketorders.ingest',{'Orders':[self.order(),self.order(Id=2,UnitPriceSilver=3500000)]}) as response:self.assertEqual(response.status,200)
                store=LocalStore(path)
                self.assertEqual(store.prices(['T4_ORE'])[0]['sell_price_min'],321)
                self.assertEqual(store.prices(['T4_ORE'])[0]['sell_price_min_amount'],40)
                with post('/test-secret/marketorders.ingest',{'Orders':[self.order(UnitPriceSilver=4000000)]}):pass
                self.assertEqual(store.prices(['T4_ORE'])[0]['sell_price_min'],400)
                self.assertEqual(counts,[2,1])
                with self.assertRaises(HTTPError) as err:post('/wrong/marketorders.ingest',{'Orders':[self.order()]})
                self.assertEqual(err.exception.code,404)
                err.exception.close()
                with self.assertRaises(HTTPError) as err:post('/test-secret/marketorders.ingest',{'bad':[]})
                self.assertEqual(err.exception.code,400)
                err.exception.close()
                self.assertEqual(store.prices(['T4_ORE'],datetime.now(timezone.utc)+timedelta(days=2)),[])
                store.close()
            finally:server.shutdown();server.server_close();thread.join()
    def test_fresh_local_overrides_old_api_per_side(self):
        now=datetime.now(timezone.utc)
        old=dict(item_id='T4_ORE',city='Thetford',quality=1,sell_price_min=200,sell_price_min_date=(now-timedelta(hours=3)).isoformat(),buy_price_max=190,buy_price_max_date=now.isoformat())
        local=dict(item_id='T4_ORE',city='Thetford',quality=1,sell_price_min=321,sell_price_min_date=now.isoformat())
        result=merge_local([old],[local])[0]
        self.assertEqual(result['sell_price_min'],321);self.assertEqual(result['buy_price_max'],190)
        self.assertEqual(result['sell_price_min_source'],SOURCE)
        self.assertEqual(old['sell_price_min'],200)
        self.assertEqual(merge_local([old],[]),[old])
        local['sell_price_min_date']=(now-timedelta(days=2)).isoformat()
        self.assertEqual(merge_local([old],[local])[0]['sell_price_min'],200)
    def test_validation_and_enchanted_material(self):
        for changes in [dict(UnitPriceSilver=True),dict(UnitPriceSilver=1.5),dict(LocationId='99999'),dict(Amount=0),dict(ItemTypeId='../bad'),dict(EnchantmentLevel=8)]:
            self.assertEqual(decode_orders({'Orders':[self.order(**changes)]}),[])
        row=decode_orders({'Orders':[self.order(ItemTypeId='T4_ORE_LEVEL1',EnchantmentLevel=1)]})[0]
        self.assertEqual(row[1],'T4_ORE_LEVEL1@1')
        self.assertEqual(row[5],321)

    def test_material_ids_keep_tier_and_enchantment_across_client_formats(self):
        for uid,level in [('T4_METALBAR_LEVEL3',0),('T4_METALBAR_LEVEL3',3),
                ('T4_METALBAR_LEVEL3@3',3),('T4_METALBAR',3),('T4_METALBAR@3',3)]:
            with self.subTest(uid=uid,level=level):
                row=decode_orders({'Orders':[self.order(ItemTypeId=uid,EnchantmentLevel=level)]})[0]
                self.assertEqual(row[1],'T4_METALBAR_LEVEL3@3')
        rows=decode_orders({'Orders':[self.order(Id=n,ItemTypeId=uid,EnchantmentLevel=level)
            for n,(uid,level) in enumerate([('T4_METALBAR',0),('T4_METALBAR',1),('T4_METALBAR',3),('T5_METALBAR',3)],1)]})
        self.assertEqual([r[1] for r in rows],['T4_METALBAR','T4_METALBAR_LEVEL1@1','T4_METALBAR_LEVEL3@3','T5_METALBAR_LEVEL3@3'])

    def test_previously_saved_resource_aliases_use_latest_page_and_unfiltered_read(self):
        with tempfile.TemporaryDirectory() as folder:
            store=LocalStore(Path(folder)/'cache.sqlite')
            newer=decode_orders({'Orders':[self.order(ItemTypeId='T4_METALBAR_LEVEL3',EnchantmentLevel=3,UnitPriceSilver=5000000)]})[0]
            old=[dict(price=100,amount=1,observed=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(),expires=newer[8],unit='silver')]
            store.db.execute('INSERT INTO local_quotes VALUES(?,?,?,?,?)',('T4_METALBAR@3','Thetford',1,'sell_price_min',json.dumps(old)));store.db.commit()
            self.assertEqual(store.prices(['T4_METALBAR_LEVEL3@3'])[0]['sell_price_min'],100)
            store.save([newer]);store.save(decode_orders({'Orders':[self.order(ItemTypeId='T4_METALBAR')]}))
            prices={r['item_id']:r['sell_price_min'] for r in store.prices()}
            self.assertEqual(prices,{'T4_METALBAR_LEVEL3@3':500,'T4_METALBAR':321})
            self.assertEqual(store.prices(['T4_METALBAR_LEVEL3@3'])[0]['sell_price_min'],500)
            store.close()

if __name__=='__main__':unittest.main()
