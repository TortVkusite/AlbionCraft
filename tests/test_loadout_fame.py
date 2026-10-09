import unittest,itertools
from pathlib import Path
from datetime import datetime,timezone,timedelta
from app.progression import GameProgression,advance
from app.catalog import load_catalog
from app.destiny import build_branches
from app.loadout import item_power,cheapest,variants
from app.fame_optimizer import prepare,plan,solve_groups

ROOT=Path(__file__).resolve().parents[1]
def price(uid,value,q=1,age=1,city='Thetford'):
    return dict(item_id=uid,city=city,quality=q,sell_price_min=value,sell_price_min_date=(datetime.now(timezone.utc)-timedelta(minutes=age)).isoformat())

class LoadoutFameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game=GameProgression(ROOT);cls.branches=build_branches(cls.game,load_catalog(ROOT))
    def test_equal_base_ip_but_tier_mastery_matters(self):
        g=self.game;self.assertEqual(item_power(g,'T5_MAIN_SWORD@1'),item_power(g,'T6_MAIN_SWORD'))
        states={'COMBAT_SWORDS_SWORD':dict(level=100,xp=0)}
        self.assertGreater(item_power(g,'T6_MAIN_SWORD',1,states),item_power(g,'T5_MAIN_SWORD@1',1,states))
        p=[price('T5_MAIN_SWORD@1',100),price('T6_MAIN_SWORD',1000)]
        self.assertEqual(cheapest(g,'T6_MAIN_SWORD',p,'Thetford')['best']['price'],100)
        self.assertEqual(cheapest(g,'T6_MAIN_SWORD',p,'Thetford',states)['best']['price'],1000)
    def test_missing_old_wrong_city_and_future_prices_cannot_win(self):
        g=self.game;p=[price('T4_MAIN_SWORD@3',100),price('T7_MAIN_SWORD',200),price('T8_MAIN_SWORD',1,age=31),price('T6_MAIN_SWORD@1',2,city='Martlock'),price('T5_MAIN_SWORD@2',3,age=-10)]
        r=cheapest(g,'T7_MAIN_SWORD',p,'Thetford');self.assertEqual(r['best']['item_id'],'T4_MAIN_SWORD@3');self.assertTrue(r['missing'])
        self.assertEqual(cheapest(g,'T7_MAIN_SWORD',p,'Thetford',max_age=None)['best']['item_id'],'T8_MAIN_SWORD')
        self.assertIsNone(cheapest(g,'T8_MAIN_SWORD@3',p,'Thetford')['best'])
    def test_quality_and_real_variants(self):
        g=self.game;p=[price('T4_MAIN_SWORD@2',10,q=5),price('T7_MAIN_SWORD',100)]
        self.assertEqual(cheapest(g,'T7_MAIN_SWORD',p,'Thetford',quality=None)['best']['quality'],5)
        self.assertEqual(cheapest(g,'T7_MAIN_SWORD',p,'Thetford',quality=1)['best']['price'],100)
        self.assertNotIn('T2_MAIN_SWORD@3',variants(g,'T4_MAIN_SWORD'))
        self.assertEqual(item_power(g,'T4_BAG@1'),item_power(g,'T5_BAG'))
    def test_one_item_uses_credit_ratio_and_existing_progress(self):
        g=self.game;b=next(b for b in self.branches if b.key=='COMBAT_SWORDS');states={'COMBAT_SWORDS_SWORD':dict(level=20,xp=100)}
        r=plan(g,b,states,'T4_MAIN_SWORD',1000000,'level')
        self.assertEqual((r['lines'][0]['level'],r['lines'][0]['xp']),advance(20,100,2000000,g.costs('COMBAT_SWORDS_SWORD')))
        self.assertEqual(states['COMBAT_SWORDS_SWORD'],dict(level=20,xp=100))
        capped=plan(g,b,{'COMBAT_SWORDS_SWORD':dict(level=100,xp=0)},'T4_MAIN_SWORD',1000000,'level');self.assertEqual(capped['spent'],0)
    def test_all_slot_ratios_and_branch_cross_bonuses(self):
        g=self.game;b=next(b for b in self.branches if b.key=='COMBAT_SWORDS')
        groups=prepare(g,b,{},'T4_MAIN_SWORD',1000000,'item')
        self.assertGreater(next(x for x in groups if x['node']=='COMBAT_SWORDS_SWORD')['choices'][1]['gain'],2)
        self.assertGreater(next(x for x in groups if x['node']=='COMBAT_SWORDS_CLAYMORE')['choices'][1]['gain'],0)
        for uid,ratio in [('T4_OFF_SHIELD',40),('T4_ARMOR_LEATHER_SET1',4),('T4_SHOES_LEATHER_SET1',8)]:
            key=g.items[uid].get('@combatspecachievement')
            branch=next(b for b in self.branches if b.mode=='COMBAT' and (key in b.nodes if key else b.key=='COMBAT_SHIELDS'))
            groups=prepare(g,branch,{},uid,1000000,'level');self.assertEqual(groups[0]['ratio'],ratio)
    def test_optimizer_matches_full_enumeration_not_ratio_greedy(self):
        groups=[dict(node='a',before=dict(level=0,xp=0),ratio=2,choices=[dict(level=0,xp=0,cost=0,gain=0),dict(level=1,xp=0,cost=6,gain=12)]),dict(node='b',before=dict(level=0,xp=0),ratio=2,choices=[dict(level=0,xp=0,cost=0,gain=0),dict(level=1,xp=0,cost=5,gain=9),dict(level=2,xp=0,cost=10,gain=18)])]
        for budget in (0,5,10,11,20):
            possible=[p for p in itertools.product(*(g['choices'] for g in groups)) if sum(c['cost'] for c in p)<=budget]
            expected=max(possible,key=lambda p:(sum(c['gain'] for c in p),-sum(c['cost'] for c in p)))
            actual=solve_groups(groups,budget)
            self.assertTrue(actual['optimal']);self.assertEqual(actual['gain'],sum(c['gain'] for c in expected));self.assertEqual(actual['spent'],sum(c['cost'] for c in expected))
    def test_profile_limits_and_invalid_credit_budget(self):
        g=self.game;b=next(b for b in self.branches if b.key=='COMBAT_SWORDS')
        with self.assertRaises(ValueError):prepare(g,b,{},'T4_BAG',1000)
        with self.assertRaises(ValueError):prepare(g,b,{},'T4_MAIN_SWORD',-1)
        with self.assertRaises(ValueError):prepare(g,b,{'COMBAT_SWORDS_SWORD':dict(level=101,xp=0)},'T4_MAIN_SWORD',1000)

if __name__=='__main__':unittest.main()
