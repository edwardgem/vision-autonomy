## T1. Stream composition (seed 1; counts are fixed by construction)

| arm | segment | good | structural | logical |
|---|---|---|---|---|
| shift | pre (items 1-380) | 342 | 38 | 0 |
| shift | post (items 381-630) | 150 | 25 | 75 |
| stationary | pre (items 1-380) | 342 | 38 | 0 |
| stationary | post (items 381-630) | 225 | 25 | 0 |

## T2. Evidence needed to certify (budget 0.10, one-sided 95% Clopper-Pearson): max proposal errors k in a slice of n

| slice n | max k |
|---|---|
| 30 | 0 |
| 40 | 0 |
| 50 | 1 |
| 60 | 1 |
| 80 | 3 |
| 100 | 4 |

## T3. Probe power: P(revoke) = P(LCB95(K, n) > 0.10), K ~ Bin(n, r), exact

| probes n | k needed | r=0.15 | r=0.2 | r=0.25 | r=0.3 | r=0.4 |
|---|---|---|---|---|---|---|
| 10.0 | 4.0 | 0.05 | 0.121 | 0.224 | 0.35 | 0.618 |
| 15.0 | 5.0 | 0.062 | 0.164 | 0.314 | 0.485 | 0.783 |
| 20.0 | 5.0 | 0.17 | 0.37 | 0.585 | 0.762 | 0.949 |
| 30.0 | 7.0 | 0.153 | 0.393 | 0.652 | 0.84 | 0.983 |
| 40.0 | 8.0 | 0.244 | 0.563 | 0.818 | 0.945 | 0.998 |
| 60.0 | 11.0 | 0.284 | 0.677 | 0.914 | 0.986 | 1.0 |

## T4. Planning simulation by option (400 streams per arm; eligible = first model accepted and good class authorized before the shift)

| option | logical prev. post | probe rate | P(model accepted) | P(eligible) | P(revoked after shift) | median items to revoke | post escapes AMP | post escapes T1 | post escapes T0 | ratio AMP/T1 | ratio AMP/T0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A: monitor as shipped (cumulative) | 0.3 | 0.3 | 0.87 | 0.838 | 0.427 | 160.0 | 20.5 | 25.2 | 36.1 | 0.81 | 0.57 |
| B: + recent-window rule W=20 | 0.3 | 0.3 | 0.87 | 0.838 | 0.818 | 100.0 | 11.6 | 25.2 | 36.1 | 0.46 | 0.32 |
| B, probe rate 0.2 | 0.3 | 0.2 | 0.87 | 0.838 | 0.728 | 125.0 | 16.8 | 28.8 | 36.1 | 0.58 | 0.47 |
| A, weaker shift | 0.2 | 0.3 | 0.87 | 0.838 | 0.113 | 130.0 | 17.2 | 18.3 | 26.2 | 0.94 | 0.66 |
| B, weaker shift | 0.2 | 0.3 | 0.87 | 0.838 | 0.618 | 110.0 | 11.6 | 18.3 | 26.2 | 0.63 | 0.44 |

## T5. Stationary arm, whole-run compliance, and assurance of the proposed success rule (§8)

| option | stationary: P(false revocation) | stationary: AMP good-class auton. error | stationary: correct exec AMP/T1 | stationary: human burden AMP | shift: AMP good-class whole-run error | assurance R=10 | assurance R=12 | assurance R=15 |
|---|---|---|---|---|---|---|---|---|
| A: monitor as shipped (cumulative) | 0.006 | 0.035 | 0.997 | 0.69 | 0.146 | 0.686 | 0.789 | 0.904 |
| B: + recent-window rule W=20 | 0.012 | 0.035 | 0.997 | 0.69 | 0.116 | 0.934 | 0.965 | 0.991 |
| B, probe rate 0.2 | 0.012 | 0.036 | 0.995 | 0.654 | 0.131 | 0.901 | 0.966 | 0.992 |
| A, weaker shift | 0.006 | 0.035 | 0.997 | 0.69 | 0.112 | 0.06 | 0.089 | 0.162 |
| B, weaker shift | 0.012 | 0.035 | 0.997 | 0.69 | 0.099 | 0.881 | 0.946 | 0.985 |

## T6. Option B details (shift arm, eligible runs)

- certified threshold (share): {0.99: 0.039, 0.98: 0.081, 0.97: 0.081, 0.95: 0.131, 0.93: 0.113, 0.9: 0.104, 0.85: 0.045, 0.8: 0.406}
- authorization item q10/q50/q90: [190.0, 210.0, 310.0]
- revocation delay q25/q50/q75 (items after shift): [70.0, 100.0, 140.0]
- never revoked: 0.182
- mean probes per run: 53.4
- defective class authorized pre-shift: 0.0

## T7. Risk-budget feasibility and the size of the shift (option B configuration, 400 streams, shift arm)

| good-class budget | P(eligible) | T0 error of authorized good slice, pre | T0 error of authorized good slice, post |
|---|---|---|---|
| 0.05 | 0.195 | 0.033 | 0.226 |
| 0.1 | 0.838 | 0.036 | 0.243 |


## T8. Assurance of the stricter 'halving' rule (rho <= 0.5 AND upper bound < 1), option B, R=12

- assurance: 0.636
