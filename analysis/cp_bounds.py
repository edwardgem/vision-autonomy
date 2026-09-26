"""Exact one-sided Clopper-Pearson bounds, as used by the governance platform's authority lifecycle.

Same algorithm as the platform's implementation (regularized incomplete beta via Lentz's continued fraction, inverted
by bisection to 1e-12), so qualification and revocation decisions recomputed here match the platform bit for bit,
including cases that sit exactly on a risk budget. Vendored so that the Experiment 3 analyses run without the platform.

    cp_upper(k, n, conf): one-sided upper bound on the error rate given k errors in n trials (1.0 if k >= n)
    cp_lower(k, n, conf): one-sided lower bound (0.0 if k <= 0)
"""
import math


def _betacf(a, b, x):
    maxit, eps, fpmin = 300, 3e-16, 1e-300
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1 / d
    h = d
    for m in range(1, maxit + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        d = fpmin if abs(d) < fpmin else d
        c = 1 + aa / c
        c = fpmin if abs(c) < fpmin else c
        d = 1 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        d = fpmin if abs(d) < fpmin else d
        c = 1 + aa / c
        c = fpmin if abs(c) < fpmin else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < eps:
            break
    return h


def inc_beta(x, a, b):
    """Regularized incomplete beta function I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return bt * _betacf(a, b, x) / a
    return 1 - bt * _betacf(b, a, 1 - x) / b


def _inc_beta_inv(p, a, b):
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if inc_beta(mid, a, b) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-12:
            break
    return (lo + hi) / 2


def cp_upper(k, n, conf):
    if n <= 0 or k >= n:
        return 1.0
    return _inc_beta_inv(conf, k + 1, n - k)


def cp_lower(k, n, conf):
    if n <= 0 or k <= 0:
        return 0.0
    return _inc_beta_inv(1 - conf, k, n - k + 1)
