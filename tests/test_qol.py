import unittest,tempfile,json
from pathlib import Path
from decimal import Decimal as D
from datetime import datetime,timezone,timedelta
from dataclasses import replace
from app.models import Recipe,Ingredient
from app.scanner import scan
from app.preferences import exclusion_key,is_excluded,save_settings
from app.recommendations import build_recommendations
from app.own_orders import OwnOrderStore,order_totals,import_user_snapshot


class QoLTests(unittest.TestCase):
    def test_exclusions_cover_tiers_enchantments_and_resource_aliases(self):
        recipes=[Recipe(uid,'Предмет',0,()) for uid in ('T4_MAIN_SWORD','T8_MAIN_SWORD@3','T4_METALBAR_LEVEL3@3','T8_METALBAR')]
        self.assertEqual([exclusion_key(r) for r in recipes],['MAIN_SWORD','MAIN_SWORD','METALBAR','METALBAR'])
        self.assertTrue(is_excluded(recipes[1],dict(excluded_items=['MAIN_SWORD'])))
        self.assertFalse(is_excluded(recipes[2],dict(excluded_items=['MAIN_SWORD'])))

    def test_settings_round_trip_none_masks_and_unrelated_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.json';data=dict(view=dict(craft='Martlock',family=None,quality='any',enchantment='custom'),quality_mask=[1,2],local_token='test')
            save_settings(path,data);self.assertEqual(json.loads(path.read_text(encoding='utf-8')),data)
            self.assertFalse(path.with_suffix('.tmp').exists())

    def rows(self):
        r=Recipe('T4_MAIN_SWORD','Палаш',0,(Ingredient('T4_METALBAR',2,True),Ingredient('T4_LEATHER',1,True)))
        stamp=datetime.now(timezone.utc).isoformat()
        prices=[dict(item_id=uid,city='Thetford',quality=1,sell_price_min=value,sell_price_min_date=stamp)
            for uid,value in [('T4_MAIN_SWORD',300),('T4_METALBAR',100),('T4_LEATHER',10)]]
        settings=dict(auto_rules=True,activity='craft',same_city=True,other='0',general={'Thetford':dict(rrr='0',focus_rrr='36.7',station='0')})
        return scan([r,replace(r,variant=1)],prices,[],['Thetford'],['Thetford'],['Thetford'],settings,1,None)

    def test_shared_materials_deduplicated_and_missing_old_future_separate(self):
        rows=self.rows();rows.append(dict(rows[0],recipe=replace(rows[0]['recipe'],item_id='T4_MAIN_AXE')))
        old=(datetime.now(timezone.utc)-timedelta(hours=7)).isoformat()
        for row in rows:
            row['parts'][0]['date']=old;row['parts'][1]['date']=None;row['parts'][1]['price']=None
        data=build_recommendations(rows,{})
        components=[p for p in data['update'] if p['role']=='Компонент']
        self.assertEqual(len(components),2)
        self.assertEqual({p['state'] for p in components},{'Нет цены','Сильно устарело'})
        self.assertEqual(components[0]['recipes'],2)
        for row in rows:row['parts'][0]['date']=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
        self.assertIn('Дата в будущем',[p['state'] for p in build_recommendations(rows,{})['update']])

    def test_candidates_obey_roi_and_budget_and_do_not_invent_profit(self):
        rows=self.rows();data=build_recommendations(rows,{})
        self.assertTrue(data['candidates'])
        self.assertFalse(build_recommendations(rows,dict(result_limits={'purchase_max':'100'}))['candidates'])
        self.assertFalse(build_recommendations(rows,dict(recommendations={'roi_min':'10000','roi_max':'20000'}))['candidates'])
        for row in rows:row.update(base=None,focus=None)
        self.assertFalse(build_recommendations(rows,{})['candidates'])


class OwnOrderTests(unittest.TestCase):
    def order(self,**updates):
        value=dict(city='Thetford',side='buy',name='Предмет',quantity=10,price='100',cost=None,status='active');value.update(updates);return value
    def test_reserved_is_separate_from_sales_and_actual_costs(self):
        orders=[self.order(),self.order(side='sell',quantity=2,price='200',cost='80'),self.order(side='sell',quantity=1,price='500')]
        x=order_totals(orders,'8')
        self.assertEqual((x['buy'],x['sell'],x['net'],x['cost'],x['invested'],x['unknown_cost']),(1000,900,828,160,1160,1))
        self.assertEqual(order_totals([self.order(status='cancelled'),self.order(status='finished')],8)['active'],0)
    def test_save_atomic_and_invalid_input_keeps_saved_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            s=OwnOrderStore(Path(folder)/'player.sqlite');s.save([self.order()])
            old=s.orders()
            for value in ['NaN','Infinity','-1']:
                with self.assertRaises(ValueError):s.save([self.order(price=value)])
                self.assertEqual(s.orders(),old)
            with self.assertRaises(ValueError):s.save([self.order(quantity=1.5)])
            s.close()
    def test_user_screenshot_amounts_and_one_time_import(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'player.sqlite';self.assertTrue(import_user_snapshot(path))
            store=OwnOrderStore(path);rows=store.orders();self.assertEqual(len(rows),8)
            x=order_totals(rows,8)
            self.assertEqual((x['buy'],x['sell'],x['order_value']),(184858,261243,446101))
            self.assertEqual(x['unknown_cost'],4)
            store.save([]);store.close()
            self.assertFalse(import_user_snapshot(path))
            store=OwnOrderStore(path);self.assertEqual(store.orders(),[]);store.close()
