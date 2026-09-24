**T4 (Experiment 2). Results by anomaly type over the full stream.**

| Condition | Type | N | Error rate | Autonomous rate | Autonomous error rate |
|---|---|---|---|---|---|
| A Human oracle | good | 575 | 0.000 | 0.000 | — |
| A Human oracle | structural | 432 | 0.000 | 0.000 | — |
| A Human oracle | logical | 561 | 0.000 | 0.000 | — |
| B Model only | good | 575 | 0.049 | 1.000 | 0.049 |
| B Model only | structural | 432 | 0.394 | 1.000 | 0.394 |
| B Model only | logical | 561 | 0.542 | 1.000 | 0.542 |
| D1 AMP (Exp 1), mean ± SD (5 seeds) | good | 575 | 0.002 ± 0.004 | 0.014 ± 0.031 | 0.125 (n=1/5) |
| D1 AMP (Exp 1), mean ± SD (5 seeds) | structural | 432 | 0.003 ± 0.007 | 0.019 ± 0.043 | 0.167 (n=1/5) |
| D1 AMP (Exp 1), mean ± SD (5 seeds) | logical | 561 | 0.005 ± 0.010 | 0.024 ± 0.053 | 0.194 (n=1/5) |
| D2 AMP (Exp 2), mean ± SD (5 seeds) | good | 575 | 0.003 ± 0.004 | 0.015 ± 0.030 | 0.718 ± 0.489 (n=3/5) |
| D2 AMP (Exp 2), mean ± SD (5 seeds) | structural | 432 | 0.003 ± 0.007 | 0.087 ± 0.024 | 0.030 ± 0.068 |
| D2 AMP (Exp 2), mean ± SD (5 seeds) | logical | 561 | 0.006 ± 0.012 | 0.093 ± 0.025 | 0.047 ± 0.096 |

anomaly_type was never visible to AMP.
