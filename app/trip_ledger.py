"""Saved route estimates and actual figures; never silently commit forecast facts."""
import json,sqlite3,re
from datetime import datetime,timezone
from decimal import Decimal as D


def plan_snapshot(plan,buy,craft,settings=None):
    rows={}
    def add(kind,uid,qty,amount=None):
        key=(kind,uid);row=rows.setdefault(key,dict(kind=kind,item_id=uid,quantity='0',amount='0' if amount is not None else None))
        row['quantity']=str(D(row['quantity'])+D(qty))
        if amount is not None:row['amount']=str(D(row['amount'])+D(amount))
    from .trip_optimizer import shopping
    goods=shopping(plan)
    for uid,part in goods.items():add('purchase',uid,part['quantity'],part.get('cost',D(part['price'])*part['quantity']))
    for lot in plan.get('existing',[]):add('stock',lot['item_id'],lot['used'],lot['price']*lot['used'])
    for line in plan['lines']:
        uid=line['candidate'].recipe.item_id;add('production',uid,line['quantity'])
        sold=line.get('sold',line['quantity']);gross=line['calc']['sale']*line['operations']
        if sold:add('sale',uid,sold,gross)
    for uid,qty in plan.get('stocks',{}).items():
        if qty>D('0.00001'):add('leftover',uid,qty)
    if not plan.get('chain'):
        for uid,part in goods.items():
            if part['returned']:add('leftover',uid,part['returned'])
    station=sum((l['calc']['station']*l['operations'] for l in plan['lines']),D(0))
    other=sum((l['calc']['fixed']*l['operations'] for l in plan['lines']),D(0))
    fees=sum((l['calc']['fees']*l['operations'] for l in plan['lines']),D(0))
    revenue=plan.get('revenue',sum(((l['calc']['sale']-l['calc']['fees'])*l['operations'] for l in plan['lines']),D(0)))
    cash_profit=revenue-plan['purchase']-plan.get('stock_value',0)-station-other
    return dict(buy=buy,craft=craft,profit=str(cash_profit),model_profit=str(plan['profit']),purchase=str(plan['purchase']),stock=str(plan.get('stock_value',0)),revenue=str(revenue),station=str(station),other=str(other),sale_fees=str(fees),rows=list(rows.values()),settings=settings or {},created=datetime.now(timezone.utc).isoformat())


def actual_summary(snapshot,facts):
    rows=facts.get('rows',[]);totals={k:D(0) for k in ('purchase','stock','sale')};missing=[]
    expected={(r['kind'],r['item_id']) for r in snapshot['rows']}
    present=set()
    for row in rows:
        kind=row['kind'];key=(kind,row['item_id'])
        if key in present:raise ValueError('Повтор строки фактических данных')
        if not re.fullmatch(r'[A-Z0-9_@]+',row['item_id']):raise ValueError('Неверный предмет')
        present.add(key)
        if kind not in ('purchase','stock','sale','production','leftover'):raise ValueError('Неизвестная строка сверки')
        qty=row.get('quantity');amount=row.get('amount')
        for name,value in [('quantity',qty),('amount',amount)]:
            if value in (None,''):continue
            number=D(str(value))
            if not number.is_finite() or number<0:raise ValueError('Фактические значения должны быть неотрицательными')
            if name=='quantity' and number!=number.to_integral_value():raise ValueError('Фактическое количество — целое число')
        if qty in (None,'') or kind in totals and amount in (None,''):missing.append(key)
        elif kind in totals:totals[kind]+=D(str(amount))
    missing.extend(expected-present)
    costs={}
    for key in ('station','other','sale_fees'):
        value=facts.get(key)
        if value in (None,''):missing.append(key);costs[key]=D(0);continue
        costs[key]=D(str(value))
        if not costs[key].is_finite() or costs[key]<0:raise ValueError('Расходы должны быть неотрицательными')
    profit=totals['sale']-totals['purchase']-totals['stock']-sum(costs.values())
    complete=not missing
    expected_gross=D(snapshot['revenue'])+D(snapshot['sale_fees'])
    changes=dict(sale=totals['sale']-expected_gross,purchase=-(totals['purchase']-D(snapshot['purchase'])),stock=-(totals['stock']-D(snapshot['stock'])))
    changes.update({key:-(costs[key]-D(snapshot[key])) for key in costs})
    return dict(profit=profit if complete else None,delta=profit-D(snapshot['profit']) if complete else None,missing=missing,totals=totals,costs=costs,changes=changes,closed=bool(facts.get('closed')) and complete)


class TripLedger:
    def __init__(self,path):
        self.db=sqlite3.connect(path,timeout=10)
        self.db.execute('CREATE TABLE IF NOT EXISTS trip_runs (id INTEGER PRIMARY KEY,player TEXT,stamp TEXT,snapshot TEXT,facts TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS journal (id INTEGER PRIMARY KEY,stamp TEXT,player TEXT,payload TEXT)');self.db.commit()
    def create(self,player,snapshot):
        with self.db:
            return self.db.execute('INSERT INTO trip_runs(player,stamp,snapshot,facts) VALUES(?,?,?,?)',(player,datetime.now(timezone.utc).isoformat(),json.dumps(snapshot,ensure_ascii=False),json.dumps({}))).lastrowid
    def entries(self,player):
        return [dict(id=i,stamp=stamp,snapshot=json.loads(s),facts=json.loads(f)) for i,stamp,s,f in self.db.execute('SELECT id,stamp,snapshot,facts FROM trip_runs WHERE player=? ORDER BY id DESC',(player,))]
    def add_row(self,player,run_id,kind,uid):
        row=self.db.execute('SELECT snapshot,facts FROM trip_runs WHERE id=? AND player=?',(run_id,player)).fetchone()
        if not row or kind not in ('purchase','stock','production','sale','leftover') or not re.fullmatch(r'[A-Z0-9_@]+',uid):raise ValueError('Неверная строка ходки')
        snapshot=json.loads(row[0]);facts=json.loads(row[1])
        if any(r['kind']==kind and r['item_id']==uid for r in snapshot['rows']):raise ValueError('Эта строка уже есть; измени её количество и сумму')
        snapshot['rows'].append(dict(kind=kind,item_id=uid,quantity='0',amount='0' if kind in ('purchase','stock','sale') else None));facts['closed']=False
        with self.db:
            self.db.execute('UPDATE trip_runs SET snapshot=?,facts=? WHERE id=? AND player=?',(json.dumps(snapshot,ensure_ascii=False),json.dumps(facts,ensure_ascii=False),run_id,player))
            linked=[i for i,payload in self.db.execute('SELECT id,payload FROM journal WHERE player=?',(player,)) if json.loads(payload).get('trip_run_id')==run_id]
            for i in linked:self.db.execute('DELETE FROM journal WHERE id=?',(i,))
    def save(self,player,run_id,facts):
        row=self.db.execute('SELECT snapshot FROM trip_runs WHERE id=? AND player=?',(run_id,player)).fetchone()
        if not row:raise ValueError('Ходка не найдена')
        snapshot=json.loads(row[0]);summary=actual_summary(snapshot,facts)
        if facts.get('closed') and not summary['closed']:raise ValueError('Заполни все фактические значения. Для отсутствующего количества и расходов введи 0.')
        with self.db:
            self.db.execute('UPDATE trip_runs SET facts=? WHERE id=? AND player=?',(json.dumps(facts,ensure_ascii=False),run_id,player))
            linked=[i for i,payload in self.db.execute('SELECT id,payload FROM journal WHERE player=?',(player,)) if json.loads(payload).get('trip_run_id')==run_id]
            for i in linked:self.db.execute('DELETE FROM journal WHERE id=?',(i,))
            if summary['closed']:
                payload=dict(type='Сделка',item='Ходка: '+snapshot['buy']+' → '+snapshot['craft'],quantity=sum(int(D(r['quantity'])) for r in facts['rows'] if r['kind']=='sale'),cost=str(summary['totals']['purchase']+summary['totals']['stock']),revenue=str(summary['totals']['sale']),fees=str(sum(summary['costs'].values())),profit=str(summary['profit']),profit_estimate=snapshot['profit'],trip_run_id=run_id)
                self.db.execute('INSERT INTO journal(stamp,player,payload) VALUES(?,?,?)',(datetime.now(timezone.utc).isoformat(),player,json.dumps(payload,ensure_ascii=False)))
        return summary
    def close(self):self.db.close()
