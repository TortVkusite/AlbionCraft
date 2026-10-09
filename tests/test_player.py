import unittest,tempfile
from pathlib import Path
from decimal import Decimal as D
from app.progression import advance,GameProgression,PlayerStore
from app.result_filters import in_bounds,reliability

class PlayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.game=GameProgression(Path(__file__).resolve().parents[1])
    def test_multiple_levels_exact_boundary_and_cap(self):
        self.assertEqual(advance(0,50,250,[100,200,300]),(2,0))
        self.assertEqual(advance(2,50,1000,[100,200,300]),(3,0))
        with self.assertRaises(ValueError):advance(0,100,0,[100,200])
    def test_dump_cost_and_focus(self):
        self.assertEqual(self.game.costs('CRAFT_SWORDS_SWORD')[0],28848)
        result=self.game.simulate('T4_MAIN_SWORD',8,{},0)
        self.assertEqual(result['focus'],10288)
        state={'CRAFT_SWORDS':{'level':100,'xp':0},'CRAFT_SWORDS_SWORD':{'level':100,'xp':0}}
        self.assertLess(self.game.simulate('T4_MAIN_SWORD',8,state,0)['focus'],10288)
    def test_focus_updates_during_level_gain(self):
        state={'CRAFT_SWORDS_SWORD':{'level':0,'xp':28847}}
        result=self.game.simulate('T4_MAIN_SWORD',2,state,2)
        self.assertEqual(result['states']['CRAFT_SWORDS_SWORD']['level'],1)
        self.assertLess(result['focus'],1286*2)
    def test_crafting_does_not_change_combat(self):
        state={'COMBAT_SWORDS':{'level':50,'xp':20}}
        result=self.game.simulate('T4_MAIN_SWORD',2,state,30000)
        self.assertEqual(result['states']['COMBAT_SWORDS'],state['COMBAT_SWORDS'])
    def test_journal_atomic_fact_and_undo(self):
        with tempfile.TemporaryDirectory() as d:
            s=PlayerStore(Path(d)/'p.sqlite');before={'X':{'level':1,'xp':2}};after={'X':{'level':2,'xp':3}}
            s.save('A',before);s.record('A',{'type':'План'});self.assertEqual(s.states('A'),before)
            s.record('A',{'type':'Факт','states_before':before,'states_after':after},after)
            self.assertEqual(s.states('A'),after);self.assertEqual(len(s.entries('A')),2)
            s.undo_last('A');self.assertEqual(s.states('A'),before);self.assertEqual(len(s.entries('A')),1)
            s.close();s=PlayerStore(Path(d)/'p.sqlite');self.assertEqual(s.states('A'),before);self.assertEqual(s.states('B'),{});s.close()
    def test_upper_and_lower_filters_inclusive(self):
        row={'base':{'profit':D(1000),'roi':D(10)},'purchase_cost':D(10000)}
        s={'result_limits':{'profit_min':'1000','profit_max':'1000','roi_min':'0','roi_max':'100','purchase_max':'10000'}}
        self.assertTrue(in_bounds(row,s));row['base']['roi']=D(765);self.assertFalse(in_bounds(row,s))
    def test_reliability_explains_unknown_costs(self):
        row={'reasons':[],'pending_costs':['станция']}
        status,tip=reliability(row);self.assertEqual(status,'Неполный расчёт');self.assertIn('станция',tip)
