# Conditional batch sale forecasts

**Question:** if demand stays comparable and my order receives a chosen share
of market trades, how likely is this batch to sell before my next check?

This is a statistical working model, not a calibrated probability for a player's
order. Personal share is an input. Complete queue priority, competitor arrivals,
future prices and hour-of-day activity are not observed. Assumptions accompany
the result instead of being hidden inside a confidence score.

## Evidence gates

Select one item, city, quality and window: 24 hours, seven days, four weeks, or
the latest view. Sources include API history, local capture and peer history
already in the current market snapshot.

- Only complete intervals ending before the current UTC boundary are accepted.
- Duplicate/overlapping buckets cannot increase volume. Windows are alternatives.
- Missing intervals are unknown, not zero trades.
- Requires 75% coverage, at least three buckets, 18 observed hours and one traded
  unit. Latest bucket end must be within `max(36, 2 × bucket_hours)` hours.
- Future observation timestamps are rejected.

Accepted incomplete coverage assumes observed intervals are representative.
Collection bias can violate this. Short windows miss weekday differences; long
windows react more slowly to changes. The UI shows these limits.

## Model

Let `C` be traded units, `D` observed days, `m` the mean bucket count and `v` its
sample variance. A Jeffreys prior gives the pure-Poisson rate posterior
`Gamma(C + 0.5, rate=D)`. Observed extra-Poisson variation widens uncertainty:

```text
market_mean = (C + 0.5) / D
extra_cv_squared = max(0, (v - m) / m²)
alpha = 1 / (1 / (C + 0.5) + extra_cv_squared)
beta = alpha / market_mean
lambda ~ Gamma(shape=alpha, rate=beta)
```

The dispersion adjustment is a conservative working assumption, not an exact
posterior under a fitted time-series model. One uncertain latent rate applies
throughout the forecast, giving a coherent monotone completion-time CDF.

For share `s` (a fraction), horizon `t` in days and quantity `Q`:

```text
N(t) | lambda ~ Poisson(lambda × s × t)
N(t) ~ NegativeBinomial(alpha, p = beta / (beta + s × t))
P(batch completed by t) = P(N(t) >= Q)
T_completion ~ BetaPrime(Q, alpha, scale=beta/s)
```

Median and 10th/80th/90th completion percentiles use that same distribution.
The 10–90% range is an 80% **model** interval. Quantiles beyond one year are
displayed as such, rather than suggesting a precise distant date.

Expected units sold are `E[min(N,Q)]`, not `Q × P(N>=Q)`. With `mu=E[N]`:

```text
E[min(N,Q)] = mu × CDF_NB(Q-2; alpha+1,p) + Q × SF_NB(Q-1; alpha,p)
expected_remaining = Q - E[min(N,Q)]
```

Sensitivity compares half, selected and twice the personal share, bounded to
0.01–100%. Existing deterministic haul scenarios remain available independently.

## Reproduce validation

```powershell
.venv\Scripts\python.exe -m unittest tests.test_sale_forecast -v
.venv\Scripts\python.exe scripts/forecast_validation.py
```

Tests cover closed forms, monotonicity, quantile/CDF consistency, capped counts,
bursty volume, stale/sparse/overlapping history, source isolation and large inputs.
A seeded simulation draws 100,000 samples from the stated model and checks
agreement with analytic probabilities and intervals. This is **not a backtest
against personal sales**. Real calibration needs timestamped order outcomes,
including unsuccessful/cancelled orders, and their price/queue conditions.

Numerical references: [SciPy negative binomial](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.nbinom.html),
[Gamma](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.gamma.html),
[beta prime](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.betaprime.html).

Code: [`sale_forecast.py`](../app/sale_forecast.py), [`sale_forecast_dialog.py`](../app/sale_forecast_dialog.py).
