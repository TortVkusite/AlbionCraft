import json,math,sqlite3
from pathlib import Path
from fnmatch import fnmatchcase
from datetime import datetime,timezone
from .catalog import many

def advance(level,progress,fame,costs):
    if level<0 or level>len(costs) or progress<0 or fame<0 or not math.isfinite(progress) or not math.isfinite(fame):raise ValueError('Некорректный опыт')
    if level<len(costs) and progress>=costs[level]:raise ValueError('Опыт внутри уровня должен быть меньше опыта до следующего')
    if level==len(costs):return level,0
    progress+=fame
    while level<len(costs) and progress>=costs[level]:progress-=costs[level];level+=1
    return level,progress if level<len(costs) else 0

class GameProgression:
    def __init__(self,root):
        from .paths import catalog_root
        self.root=catalog_root(root)
        achievements=json.loads((self.root/'research/achievements.json').read_text(encoding='utf-8-sig'))['achievements']
        self.nodes={};self.templates={t['@name']:t for t in achievements['template']}
        for n in achievements['templateachievement']:
            if 'baselevels' in self.templates.get(n.get('@usetemplate'),{}):self.nodes[n['@id']]=n
        self.game=json.loads((self.root/'research/full_gamedata.json').read_text(encoding='utf-8-sig'))['AO-GameData']
        self.items={}
        for group in json.loads((self.root/'research/items.json').read_text(encoding='utf-8-sig'))['items'].values():
            for item in many(group):
                if item.get('@uniquename'):self.items[item['@uniquename']]=item
    def costs(self,node):
        n=self.nodes[node];template=self.templates[n['@usetemplate']]
        factor=float(n.get('@famemultiplier',1))
        return [round(float(line.strip().split(';')[0])*factor) for line in template['baselevels']['#text'].splitlines() if line.strip()][:100]
    def matching(self,uid,kind):
        base=uid.split('@')[0]
        return [key for key,n in self.nodes.items() if key.startswith(kind+'_') and n['@usetemplate'] in (kind+'_BASE',kind+'_SPEC')
            and any(fnmatchcase(base,p['@pattern']) for p in many((n.get('itemlist') or {}).get('itempattern')))]
    def focus_coefficients(self,uid):
        base=uid.split('@')[0];result={};tier=int(base.split('_')[0][1:])
        for key,node in self.nodes.items():
            for bonus in many((node.get('baserewards') or {}).get('bonus')):
                if (bonus.get('@type')=='craftingfocuscostreduction'
                    and int(bonus.get('@mintier',0))<=tier<=int(bonus.get('@maxtier',99))
                    and any(fnmatchcase(base,p['@pattern']) for p in many(bonus.get('itempattern')))):result[key]=result.get(key,0)+float(bonus['@bonus'])
        return result
    def requirements(self,uid,variant=0):
        base=uid.split('@')[0];item=self.items.get(base,{})
        if '@' in uid and item.get('@enchantmentlevel','0')=='0':
            level=uid.split('@')[1];item=next((e for e in many((item.get('enchantments') or {}).get('enchantment')) if e['@enchantmentlevel']==level),{})
        req=many(item.get('craftingrequirements'))
        return req[variant] if 0<=variant<len(req) else {}
    def base_focus(self,uid):
        req=self.requirements(uid)
        return int(req['@craftingfocus']) if '@craftingfocus' in req else None
    def simulate(self,uid,quantity,states,fame_each,focus=True,kind='CRAFT',focus_each=None,recipe=None):
        if quantity<1 or quantity>100000:raise ValueError('Количество должно быть от 1 до 100000')
        req=self.requirements(uid,recipe.variant if recipe else 0)
        output=(recipe.output_count if recipe else int(req.get('@amountcrafted','1'))) if kind=='CRAFT' else 1
        if quantity%output:raise ValueError(f'Количество должно быть кратно выходу рецепта: {output} шт.')
        states={k:dict(v) for k,v in states.items()};active=self.matching(uid,kind);costs={k:self.costs(k) for k in active}
        before={k:dict(states.get(k,dict(level=0,xp=0))) for k in active}
        for key in active:states.setdefault(key,dict(level=0,xp=0));advance(states[key]['level'],states[key]['xp'],0,costs[key])
        coefficients=self.focus_coefficients(uid);base=int(req['@craftingfocus']) if '@craftingfocus' in req else None;constant=float(self.game['ActionFocus']['@costreductionconstant'])
        total_focus=0 if not focus else None if base is None and focus_each is None else 0
        for _ in range(quantity//output):
            if focus and total_focus is not None:
                efficiency=sum(value*states.get(key,{}).get('level',0) for key,value in coefficients.items())
                total_focus+=float(focus_each)*output if focus_each is not None else math.ceil(base/constant**efficiency)
            for key in active:
                level,xp=advance(states[key]['level'],states[key]['xp'],fame_each*output,costs[key]);states[key]=dict(level=level,xp=xp)
        return dict(states=states,before=before,active=active,focus=total_focus,fame=quantity*fame_each)

class PlayerStore:
    def __init__(self,path):
        self.db=sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS player_nodes (player TEXT,node TEXT,level INTEGER,xp REAL,PRIMARY KEY(player,node))')
        self.db.execute('CREATE TABLE IF NOT EXISTS journal (id INTEGER PRIMARY KEY,stamp TEXT,player TEXT,payload TEXT)');self.db.commit()
    def states(self,player):return {node:dict(level=level,xp=xp) for node,level,xp in self.db.execute('SELECT node,level,xp FROM player_nodes WHERE player=?',(player,))}
    def save(self,player,states):
        with self.db:self.db.executemany('INSERT OR REPLACE INTO player_nodes VALUES(?,?,?,?)',[(player,k,v['level'],v['xp']) for k,v in states.items()])
    def record(self,player,payload,states=None):
        with self.db:
            if payload.get('stock_changes'):
                from .trip_inventory import apply_consumption
                apply_consumption(self.db,player,payload['stock_changes'])
            self.db.execute('INSERT INTO journal(stamp,player,payload) VALUES(?,?,?)',(datetime.now(timezone.utc).isoformat(),player,json.dumps(payload,ensure_ascii=False)))
            if states is not None:self.db.executemany('INSERT OR REPLACE INTO player_nodes VALUES(?,?,?,?)',[(player,k,v['level'],v['xp']) for k,v in states.items()])
    def entries(self,player):return [(i,stamp,json.loads(payload)) for i,stamp,payload in self.db.execute('SELECT id,stamp,payload FROM journal WHERE player=? ORDER BY id DESC',(player,))]
    def undo_last(self,player):
        row=self.db.execute('SELECT id,payload FROM journal WHERE player=? ORDER BY id DESC LIMIT 1',(player,)).fetchone()
        if not row:return
        payload=json.loads(row[1])
        if 'states_after' in payload and self.states(player)!=payload['states_after']:raise ValueError('Профиль менялся после записи. Отмена не должна перезаписывать новые уровни.')
        with self.db:
            if payload.get('stock_changes'):
                from .trip_inventory import apply_consumption
                apply_consumption(self.db,player,payload['stock_changes'],reverse=True)
            if 'states_before' in payload:
                self.db.execute('DELETE FROM player_nodes WHERE player=?',(player,))
                self.db.executemany('INSERT INTO player_nodes VALUES(?,?,?,?)',[(player,k,v['level'],v['xp']) for k,v in payload['states_before'].items()])
            self.db.execute('DELETE FROM journal WHERE id=?',(row[0],))
    def close(self):self.db.close()
