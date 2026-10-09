"""Cash and fractional ROI objectives for the same integer feasible set."""
from time import monotonic


def optimize(milp, money, purchase, bounds, constraints, time_limit, objective='profit'):
    import numpy as np
    from scipy.optimize import LinearConstraint
    if objective not in ('profit', 'roi'):
        raise ValueError('Неизвестная цель подбора')
    money=np.asarray(money,dtype=float)
    purchase=np.asarray(purchase,dtype=float)
    deadline=monotonic()+time_limit
    def run(coeff, extra=None):
        scale=max(float(np.max(np.abs(coeff))),1)
        result=milp(coeff/scale,integrality=np.ones(len(coeff)),bounds=bounds,
            constraints=constraints if extra is None else [constraints,extra],
            options={'time_limit':max(.001,deadline-monotonic()),'mip_rel_gap':0})
        return result,scale
    result,scale=run(money)
    if objective=='profit' or result.x is None:
        return result,scale
    x=np.rint(result.x)
    cost=float(purchase@x); profit=float(-money@x)
    if cost<=0 or profit<=0:
        result.mip_dual_bound=None
        return result,scale
    best=result; ratio=profit/cost; proven=False
    # Dinkelbach: maximize profit - ratio * purchases, preserving all limits.
    # The zero plan is feasible. Its zero residual proves the previous
    # positive plan optimal only when the inner MILP is itself proven optimal.
    for _ in range(64):
        if monotonic()>=deadline:break
        trial,_=run(money+ratio*purchase)
        if trial.x is None:break
        x=np.rint(trial.x); cost=float(purchase@x); profit=float(-money@x)
        residual=profit-ratio*cost
        tolerance=1e-7
        if cost>0 and profit/cost>ratio:
            best=trial;ratio=profit/cost
        if trial.status==0 and residual<=tolerance:
            proven=True;break
        if trial.status!=0:break
    # Equal ROI: prefer the largest cash profit, rather than an arbitrary lot.
    if proven and monotonic()<deadline:
        tie=LinearConstraint(money+ratio*purchase,-np.inf,1e-7)
        trial,_=run(money,tie)
        if trial.x is not None:
            x=np.rint(trial.x);cost=float(purchase@x)
            if cost>0 and float(-money@x)/cost>=ratio-1e-9:best=trial
    best.status=0 if proven else 1
    best.mip_dual_bound=None  # A cash bound is not a bound on fractional ROI.
    best.message='Максимальный ROI доказан' if proven else 'Лучший найденный ROI; оптимум не доказан'
    return best,scale
