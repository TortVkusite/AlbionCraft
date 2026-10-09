import unittest
from decimal import Decimal as D
from app.calculator import calculate, classify, demand

class CalculatorTests(unittest.TestCase):
    def calc(self, rrr='0', artifact='0', sale='2000', focus=None):
        return calculate(D('1000'),D(artifact),D(sale),D(rrr),D('100'),D('0.025'),D('0.04'),focus)
    def test_simple_and_tax(self):
        x=self.calc(); self.assertEqual(x['fees'],D('130')); self.assertEqual(x['profit'],D('770'))
    def test_artifact_is_not_returned(self):
        self.assertEqual(self.calc('0.367','500')['cost'],D('1233'))
    def test_zero_return(self):
        self.assertEqual(self.calc()['cost'],D('1100'))
    def test_return(self):
        self.assertEqual(self.calc('0.367')['cost'],D('733'))
    def test_capital_is_upfront(self):
        self.assertEqual(self.calc('0.367')['capital'],D('1150'))
    def test_focus(self):
        self.assertEqual(self.calc(focus=D('10'))['per_focus'],D('77'))
    def test_no_focus(self):
        self.assertIsNone(self.calc()['per_focus'])
    def test_negative(self):
        self.assertLess(self.calc(sale='500')['profit'],0)
    def test_invalid(self):
        with self.assertRaises(ValueError): self.calc(rrr='1')
    def test_zero_cost(self):
        self.assertIsNone(calculate(D(0),D(0),D(0),D(0),D(0),D(0),D(0))['roi'])
    def test_neutral_boundaries(self):
        for a,b in [(5,5),(-5,-5),(-10,5),(-4,0)]: self.assertEqual(classify(D(a),D(b)),'neutral')
    def test_colors(self):
        self.assertEqual(classify(D(6),D(20)),'green')
        self.assertEqual(classify(D(-20),D(6)),'blue')
        self.assertEqual(classify(D(-6),D(-6)),'red')
        self.assertEqual(classify(None,None),'unknown')
    def test_demand_unknown(self):
        self.assertEqual(demand([])['kind'],'unknown')
    def test_regular(self):
        data=[{'timestamp':f'2026-10-0{i}T00:00:00','item_count':10,'avg_price':100} for i in (1,2,3)]
        from datetime import datetime,timezone
        x=demand(data,now=datetime(2026,10,4,tzinfo=timezone.utc))
        self.assertEqual(x['kind'],'low'); self.assertEqual(x['active_days'],3)
    def test_one_sale(self):
        from datetime import datetime,timezone
        x=demand([{'timestamp':'2026-10-02T00:00:00','item_count':1,'avg_price':100}],now=datetime(2026,10,4,tzinfo=timezone.utc))
        self.assertEqual(x['kind'],'very_low')

    def test_volume_bands_boundaries_and_daily_average(self):
        from datetime import datetime,timezone,timedelta
        end=datetime(2026,10,4,tzinfo=timezone.utc)
        def measure(total):
            return demand([{'timestamp':(end-timedelta(days=1)).isoformat(),'item_count':total,'avg_price':100}],now=end)
        cases=[(0,'none'),(1,'very_low'),(7,'very_low'),(20,'very_low'),(21,'low'),
               (69,'low'),(70,'medium'),(349,'medium'),(350,'high'),(1399,'high'),
               (1400,'very_high'),(6999,'very_high'),(7000,'mass'),(69999,'mass'),(70000,'huge')]
        for total,kind in cases:
            with self.subTest(total=total):
                result=measure(total);self.assertEqual(result['kind'],kind)
                self.assertEqual(result['per_day'],total/7)
                self.assertEqual(result['observed_days'],1)
        self.assertEqual(measure(168000)['kind'],'huge') # 1,000 per hour

    def test_daily_sales_do_not_imply_large_volume(self):
        from datetime import datetime,timezone,timedelta
        end=datetime(2026,10,4,tzinfo=timezone.utc)
        rows=[{'timestamp':(end-timedelta(days=i)).isoformat(),'item_count':1,'avg_price':100} for i in range(1,8)]
        result=demand(rows,now=end)
        self.assertEqual(result['kind'],'very_low');self.assertEqual(result['active_days'],7)
        self.assertEqual(result['observed_days'],7);self.assertEqual(result['per_day'],1)
        from app.calculator import demand_tip
        self.assertIn('30.0 суток',demand_tip(result))

    def test_missing_history_not_zero_and_no_duplicate_or_current_day(self):
        from datetime import datetime,timezone
        now=datetime(2026,10,4,tzinfo=timezone.utc)
        row={'timestamp':'2026-10-03T00:00:00','item_count':7,'avg_price':100}
        result=demand([row,dict(row),dict(row,timestamp=now.isoformat(),item_count=999999)],now=now)
        self.assertEqual(result['total'],7);self.assertEqual(result['observed_days'],1)
        self.assertEqual(demand([dict(row,item_count=0)],now=now)['kind'],'none')
        self.assertEqual(demand([],now=now)['kind'],'unknown')
