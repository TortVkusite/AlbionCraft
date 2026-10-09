import json,unittest
from datetime import datetime,timezone,timedelta
from app.builds import parse_grind,variant,evaluate
from app.models import Recipe,Ingredient

class BuildTests(unittest.TestCase):
    def test_public_metadata_only_main_slots_and_dedup(self):
        row=dict(slug='test',weapon_id='T8_MAIN_SWORD',helmet_id='T8_HEAD_CLOTH_SET1',helmet_id_alt='T8_HEAD_PLATE_SET1',category='CORRUPTED_DUNGEON',upvote_count=12,title='Example')
        data={'props':{'pageProps':{'initialBuilds':[row,row,dict(row,slug='../bad')],'initialHasMore':True}}}
        html='<script id="__NEXT_DATA__" type="application/json">'+json.dumps(data)+'</script>'
        result=parse_grind(html)
        self.assertEqual(len(result['builds']),1);self.assertTrue(result['has_more'])
        self.assertNotIn('helmet_id_alt',result['builds'][0]['items']);self.assertEqual(result['builds'][0]['votes'],12)
        with self.assertRaises(ValueError):parse_grind('site format changed')
    def test_variant_and_consumables(self):
        self.assertEqual(variant('T8_MAIN_SWORD@2','weapon_id',4,1),'T4_MAIN_SWORD@1')
        self.assertEqual(variant('T7_MEAL_OMELETTE','food_id',4,1),'T7_MEAL_OMELETTE')
    def test_missing_price_does_not_make_complete_cheap_set(self):
        b=dict(items={'weapon_id':'T8_MAIN_SWORD','helmet_id':'T8_HEAD_CLOTH_SET1'})
        stamp=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
        prices=[dict(item_id='T4_MAIN_SWORD',city='Thetford',quality=2,sell_price_min=1000,sell_price_min_date=stamp),
                dict(item_id='T4_MAIN_SWORD',city='Thetford',quality=1,sell_price_min=2000,sell_price_min_date=stamp)]
        result=evaluate(b,prices,[],'Thetford',4,0,None,[],{})
        self.assertFalse(result['complete']);self.assertEqual(result['cost'],1000)
        self.assertEqual(result['parts'][0]['quality'],2);self.assertEqual(result['missing'],['T4_HEAD_CLOTH_SET1'])
    def test_profit_uses_existing_market_calculations_and_same_quality(self):
        b=dict(items={'weapon_id':'T8_MAIN_SWORD'})
        stamp=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
        prices=[dict(item_id=uid,city='Thetford',quality=q,sell_price_min=sale,buy_price_max=buy,sell_price_min_date=stamp,buy_price_max_date=stamp) for uid,q,sale,buy in [('T4_MAIN_SWORD',1,2000,1000),('T4_METALBAR',1,100,80)]]
        r=Recipe('T4_MAIN_SWORD','Меч',0,(Ingredient('T4_METALBAR',10,True),),nutrition='10')
        settings=dict(auto_rules=True,other='0',station_rates={'Thetford':'0'},setup='2.5',tax='8')
        result=evaluate(b,prices,[],'Thetford',4,0,None,[r],settings)
        self.assertTrue(result['complete']);part=result['parts'][0]
        self.assertIsNotNone(part['craft']);self.assertIsNotNone(part['flip'])
        self.assertEqual(part['flip']['sale'],2000);self.assertEqual(part['flip']['purchase_cost'],1000)
        self.assertLess(part['flip']['base']['profit'],1000)

    def test_all_tiers_and_enchantments_skip_nonexistent_variants(self):
        from app.builds import build_variants
        build=dict(items={'weapon_id':'T8_MAIN_SWORD','boots_id':'T8_SHOES_PLATE_SET1','food_id':'T7_MEAL_OMELETTE'})
        available={'T3_MAIN_SWORD','T3_SHOES_PLATE_SET1','T4_MAIN_SWORD','T4_SHOES_PLATE_SET1',
                   'T4_MAIN_SWORD@1','T4_SHOES_PLATE_SET1@1','T8_MAIN_SWORD@4','T8_SHOES_PLATE_SET1@4'}
        self.assertEqual(build_variants(build,None,None,available),[(3,0),(4,0),(4,1),(8,4)])
        self.assertEqual(build_variants(build,4,None,available),[(4,0),(4,1)])
        self.assertEqual(build_variants(build,None,0,available),[(3,0),(4,0)])

    def test_shared_item_cache_does_not_merge_build_variants_or_slots(self):
        first=dict(id='first',items={'weapon_id':'T8_MAIN_SWORD'})
        second=dict(id='second',items={'offhand_id':'T8_MAIN_SWORD'})
        context={}
        a=evaluate(first,[],[],'Thetford',4,0,None,[],{},context)
        b=evaluate(second,[],[],'Thetford',4,0,None,[],{},context)
        self.assertEqual(a['parts'][0]['slot'],'weapon_id');self.assertEqual(b['parts'][0]['slot'],'offhand_id')
        self.assertNotEqual(a['key'],b['key']);self.assertFalse(a['complete']);self.assertFalse(b['complete'])
