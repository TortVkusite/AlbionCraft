"""Discrete allocation of existing combat fame credits, levels 0–100."""
import math
from fnmatch import fnmatchcase
from .catalog import many
from .loadout import equipment,bonus_per_level,family
from .progression import advance

# Spending (not gaining or converting) credits. Developer's respec table:
# https://forum.albiononline.com/index.php/Thread/86790-A-Brief-Guide-to-Mastery-Re-Specialization-AKA-Re-Spec/
FAME_PER_CREDIT={'mainhand':2,'2h':2,'armor':4,'head':8,'shoes':8,'offhand':40}

def prepare(game,branch,states,uid,budget,mode='item',include_mastery=False):
    if mode not in ('level','item','branch') or type(budget) is not int or budget<0:raise ValueError('Некорректный режим или запас очков')
    item=equipment(game,uid)
    if not item or item.get('@slottype') not in FAME_PER_CREDIT:raise ValueError('Свободная слава используется только для боевых узлов')
    ratio=FAME_PER_CREDIT[item['@slottype']]
    specs=[k for k in branch.nodes if game.nodes[k]['@usetemplate'] in ('COMBAT_SPEC','COMBAT_OFF_SPEC')]
    # Offhand specializations can use COMBAT_SPEC, handled by the slot ratio.
    selected=item.get('@combatspecachievement')
    if selected not in specs:
        selected=next((k for k in specs if any(fnmatchcase(uid.split('@')[0],p['@pattern']) for p in many((game.nodes[k].get('itemlist') or {}).get('itempattern')))),None)
    if selected not in specs:raise ValueError('Предмет не принадлежит выбранной боевой ветке')
    targets=[uid] if mode!='branch' else [f'T{uid[1]}_'+family(game.nodes[k]['@itemforsprite']) for k in specs]
    keys=[selected] if mode=='level' else specs+([branch.root] if include_mastery and branch.root else [])
    groups=[]
    for key in keys:
        state=dict(states.get(key,dict(level=0,xp=0)));costs=game.costs(key);advance(state['level'],state['xp'],0,costs)
        gain=1 if mode=='level' else sum(bonus_per_level(game,key,target)*(1+float(equipment(game,target).get('@masterymodifier',0))) for target in targets)
        if gain<=0:continue
        choices=[dict(level=state['level'],xp=state['xp'],cost=0,gain=0)]
        fame=-state['xp']
        for level in range(state['level']+1,len(costs)+1):
            fame+=costs[level-1];cost=math.ceil(fame/ratio)
            if cost>budget:break
            choices.append(dict(level=level,xp=0,cost=cost,gain=round((level-state['level'])*gain,8)))
        groups.append(dict(node=key,before=state,choices=choices,ratio=ratio))
    return groups

def solve_groups(groups,budget,time_limit=10):
    import numpy as np
    from scipy.optimize import milp,Bounds,LinearConstraint
    if not groups:return dict(lines=[],spent=0,left=budget,gain=0,optimal=True)
    options=[(n,c) for n,g in enumerate(groups) for c in g['choices']];count=len(options)
    matrix=np.zeros((len(groups)+1,count))
    for j,(n,c) in enumerate(options):matrix[n,j]=1;matrix[-1,j]=c['cost']
    gains=np.array([round(c['gain']*10000) for _,c in options],dtype=float)
    constraints=LinearConstraint(matrix,[1]*len(groups)+[0],[1]*len(groups)+[budget])
    result=milp(-gains,integrality=np.ones(count),bounds=Bounds(np.zeros(count),np.ones(count)),constraints=constraints,options={'time_limit':time_limit,'mip_rel_gap':0})
    if result.x is None:raise ValueError('Подбор не завершился: '+result.message)
    optimal=result.status==0
    if optimal:
        target=round(gains@np.rint(result.x))
        tie=milp(matrix[-1]/max(budget,1),integrality=np.ones(count),bounds=Bounds(np.zeros(count),np.ones(count)),constraints=[constraints,LinearConstraint(gains,target,target)],options={'time_limit':time_limit,'mip_rel_gap':0})
        if tie.x is not None:result=tie
    chosen=[(n,c) for (n,c),v in zip(options,np.rint(result.x)) if v==1]
    if len(chosen)!=len(groups) or len({n for n,c in chosen})!=len(groups):raise ValueError('Неверное распределение решателя')
    spent=sum(c['cost'] for n,c in chosen)
    if spent>budget:raise ValueError('Распределение превысило запас очков')
    lines=[]
    for n,c in chosen:
        g=groups[n];line=dict(c,node=g['node'],before=g['before'],ratio=g['ratio'])
        # Credit spending advances XP too; ceil rounding can leave a few XP.
        level,xp=advance(g['before']['level'],g['before']['xp'],c['cost']*g['ratio'],g.get('costs',[])) if 'costs' in g else (c['level'],c['xp'])
        line.update(level=level,xp=xp);lines.append(line)
    return dict(lines=lines,spent=spent,left=budget-spent,gain=sum(c['gain'] for n,c in chosen),optimal=optimal)

def plan(game,branch,states,uid,budget,mode='item',include_mastery=False):
    groups=prepare(game,branch,states,uid,budget,mode,include_mastery)
    for g in groups:g['costs']=game.costs(g['node'])
    if mode=='level':
        g=groups[0];costs=g['costs'];before=g['before'];cap=sum(costs[before['level']:])-before['xp']
        spent=min(budget,max(0,math.ceil(cap/g['ratio'])));level,xp=advance(before['level'],before['xp'],spent*g['ratio'],costs)
        return dict(lines=[dict(node=g['node'],before=before,level=level,xp=xp,cost=spent,gain=level-before['level'],ratio=g['ratio'])],spent=spent,left=budget-spent,gain=level-before['level'],optimal=True)
    return solve_groups(groups,budget)

if __name__=='__main__':
    import sys,json
    data=json.load(sys.stdin)
    print(json.dumps(solve_groups(data['groups'],data['budget']),ensure_ascii=False))
