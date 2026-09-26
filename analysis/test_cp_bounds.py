"""Tests for analysis/cp_bounds.py. python -m analysis.test_cp_bounds

1. Agreement with scipy's Beta quantiles (the textbook Clopper-Pearson definition) to 1e-9.
2. The certification table of EXPERIMENT_PLAN_3 (T2): at budget 0.10 and 95%, the largest error count k that still
   certifies in a slice of n rows.
3. The probe-power table of EXPERIMENT_PLAN_3 (T3): errors needed to revoke with n probes.
"""
from scipy.stats import beta
from analysis.cp_bounds import cp_lower, cp_upper


def test_matches_scipy():
    worst = 0.0
    for n in range(1, 201):
        for k in range(0, n + 1):
            for conf in (0.90, 0.95, 0.99):
                u_ref = 1.0 if k >= n else beta.ppf(conf, k + 1, n - k)
                l_ref = 0.0 if k <= 0 else beta.ppf(1 - conf, k, n - k + 1)
                worst = max(worst, abs(cp_upper(k, n, conf) - u_ref), abs(cp_lower(k, n, conf) - l_ref))
    assert worst < 1e-9, worst


def test_certification_table_T2():
    expected = {30: 0, 40: 0, 50: 1, 60: 1, 80: 3, 100: 4}
    for n, kmax in expected.items():
        got = max(k for k in range(n + 1) if cp_upper(k, n, 0.95) <= 0.10)
        assert got == kmax, (n, got, kmax)


def test_revocation_threshold_T3():
    expected = {10: 4, 15: 5, 20: 5, 30: 7, 40: 8, 60: 11}
    for n, kneed in expected.items():
        got = min(k for k in range(n + 1) if cp_lower(k, n, 0.95) > 0.10)
        assert got == kneed, (n, got, kneed)


if __name__ == "__main__":
    test_matches_scipy(); test_certification_table_T2(); test_revocation_threshold_T3()
    print("cp_bounds: all tests passed")
