import unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from app.models import Recipe,Ingredient
from app.enchantment import upgrade_paths,comparison_price_ids,prefer_enchanted
from app.catalog import load_catalog
from app.scanner import scan
from app.item_names import item_name,recipe_variant,has_known_price


class EnchantmentComparisonTests(unittest.TestCase):
    def setUp(self):
        self.uid='T4_SHOES_CLOTH_ROYAL'
        self.recipe=Recipe(self.uid,'Сандалии',0,(),category='armors',base_id=self.uid)
        self.row=dict(recipe=self.recipe,sell='Thetford',quality=1,sale_side='sell_price_min',issues=[])
        self.prices=[self.price(self.uid,10000),self.price(self.uid+'@1',10672),self.price('T4_RUNE',7)]

    def price(self,uid,value,quality=1,city='Thetford',age=0):
        return dict(item_id=uid,quality=quality,city=city,sell_price_min=value,
            sell_price_min_date=(datetime.now(timezone.utc)-timedelta(minutes=age)).isoformat())

    def compare(self,age=None):
        return prefer_enchanted([self.row],self.prices,age)

    def test_shoes_exact_672_boundary_and_no_flat_1000_threshold(self):
        kept,hidden=self.compare()
        self.assertFalse(kept);self.assertEqual(hidden[0]['alternative']['upgrade_cost'],672)
        self.prices[1]['sell_price_min']=10673
        self.assertTrue(self.compare()[0])
        self.prices[1]['sell_price_min']=11000
        self.assertTrue(self.compare()[0])

    def test_all_intermediate_steps_and_only_steps_after_current_enchantment(self):
        self.prices=[self.price(self.uid,10000),self.price(self.uid+'@2',11632),
            self.price('T4_RUNE',7),self.price('T4_SOUL',10)]
        self.assertEqual(self.compare()[1][0]['alternative']['upgrade_cost'],96*(7+10))
        self.prices[1]['sell_price_min']=11633
        self.assertTrue(self.compare()[0])
        from dataclasses import replace
        self.row['recipe']=replace(self.recipe,item_id=self.uid+'@1',enchantment=1)
        self.prices=[self.price(self.uid+'@1',10000),self.price(self.uid+'@3',12880),
            self.price('T4_SOUL',10),self.price('T4_RELIC',20)]
        self.assertEqual(self.compare()[1][0]['alternative']['upgrade_cost'],96*(10+20))

    def test_missing_reagent_does_not_hide_but_cheaper_upgrade_needs_none(self):
        self.prices.pop()
        self.assertTrue(self.compare()[0])
        self.assertIn('Руна',' '.join(self.row['issues']))
        self.prices[1]['sell_price_min']=9999
        hidden=self.compare()[1]
        self.assertTrue(hidden);self.assertIsNone(hidden[0]['alternative']['upgrade_cost'])

    def test_old_future_other_city_and_lower_quality_do_not_hide(self):
        for field,value in [('city','Martlock'),('sell_price_min_date',self.price('X',1,age=31)['sell_price_min_date']),
                ('sell_price_min_date',self.price('X',1,age=-10)['sell_price_min_date'])]:
            with self.subTest(field=field,value=value):
                self.prices[1]=self.price(self.uid+'@1',10672);self.prices[1][field]=value
                self.assertTrue(self.compare()[0])
        self.prices[1]=self.price(self.uid+'@1',10672,quality=1)
        self.row['quality']=2;self.prices[0]['quality']=2
        self.assertTrue(self.compare()[0])
        self.prices[1]['quality']=3
        self.assertFalse(self.compare()[0])
        self.row['sale_side']='buy_price_max'
        self.assertTrue(self.compare()[0])

    def test_stale_reagent_and_stale_base_cannot_hide_fresh_or_old_result(self):
        self.prices[2]=self.price('T4_RUNE',7,age=31)
        self.assertTrue(self.compare()[0])
        self.assertFalse(self.compare(60)[0])
        self.prices[2]=self.price('T4_RUNE',7)
        self.prices[0]=self.price(self.uid,10000,age=31)
        self.assertTrue(self.compare()[0])

    def test_four_is_not_invented_and_weapon_quantities_differ(self):
        paths=upgrade_paths()
        self.assertNotIn((self.uid,0,4),paths)
        self.assertEqual(paths[('T4_MAIN_SWORD',0,1)][0][0].amount,288)
        self.assertEqual(paths[('T4_2H_CLAYMORE',0,1)][0][0].amount,384)
        self.prices[1]=self.price(self.uid+'@4',10001)
        self.assertTrue(self.compare()[0])

    def test_only_showing_zero_still_loads_all_upgrade_comparisons_and_reagents(self):
        catalog=load_catalog(Path(__file__).resolve().parents[1])
        ids=comparison_price_ids([self.recipe],catalog)
        self.assertTrue({self.uid+'@1',self.uid+'@2',self.uid+'@3','T4_RUNE','T4_SOUL','T4_RELIC'}<=ids)
        self.assertNotIn('T4_MAIN_SWORD@1',ids)


class ReportedRecipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.catalog=load_catalog(Path(__file__).resolve().parents[1])

    def test_mistcaller_reagent_alternatives_and_game_names(self):
        recipes=[r for r in self.catalog if r.item_id=='T4_OFF_HORN_KEEPER@2' and r.path=='Прямой крафт']
        self.assertEqual(len(recipes),2)
        self.assertEqual([[(i.item_id,i.amount) for i in r.ingredients[:2]] for r in recipes],
            [[('T4_PLANKS_LEVEL2@2',4),('T4_CLOTH_LEVEL2@2',4)]]*2)
        self.assertIn('Рунический горн',recipe_variant(recipes[0]))
        self.assertIn('Кристаллизованный дух',recipe_variant(recipes[1]))
        self.assertIn('Редкие сосновые брусья',item_name('T4_PLANKS_LEVEL2@2'))
        self.assertIn('T4.2',item_name('T4_PLANKS_LEVEL2@2'))

    def test_royal_missing_materials_remains_priced_and_quality_is_preserved(self):
        recipes=[r for r in self.catalog if r.item_id=='T4_SHOES_CLOTH_ROYAL@2' and r.path=='Прямой крафт']
        self.assertEqual(len(recipes),3)
        self.assertTrue(all(r.ingredients[0].preserve_quality for r in recipes))
        date=datetime.now(timezone.utc).isoformat()
        def quote(uid,q,value):return dict(item_id=uid,city='Thetford',quality=q,sell_price_min=value,sell_price_min_date=date)
        prices=[quote(recipes[0].item_id,2,132987)]
        settings=dict(auto_rules=True,activity='craft',same_city=True,other='0')
        rows=scan(recipes,prices,[],['Thetford'],['Thetford'],['Thetford'],settings,2,None)
        self.assertEqual(len(rows),3);self.assertTrue(all(has_known_price(row) for row in rows))
        self.assertTrue(all(row['base'] is None for row in rows))
        self.assertIn('Сандалии',rows[0]['reasons'][0]);self.assertNotIn('T4_SHOES',rows[0]['reasons'][0])
        prices.extend([quote(recipes[0].ingredients[0].item_id,1,1),quote(recipes[0].ingredients[0].item_id,2,5000),
            quote('QUESTITEM_TOKEN_ROYAL_T4',1,100)])
        row=scan([recipes[0]],prices,[],['Thetford'],['Thetford'],['Thetford'],settings,2,None)[0]
        self.assertEqual(row['purchase_cost'],5200)
        self.assertEqual(row['parts'][0]['quality'],2)
        self.assertIsNotNone(row['base'])
        chosen=scan([recipes[0]],prices,[],['Thetford'],['Thetford'],['Thetford'],settings,'any',None)[0]
        self.assertEqual(chosen['quality'],2);self.assertEqual(chosen['purchase_cost'],5200)
        missing=scan([recipes[1]],prices[:1],[],['Thetford'],['Thetford'],['Thetford'],settings,'any',None)[0]
        self.assertEqual(missing['quality'],2);self.assertEqual(missing['sale'],132987)
