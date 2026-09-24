**T4. Results by anomaly type over the full stream (good / structural / logical).**

| Condition | Type | N | Accuracy | Error rate | Autonomous rate | Autonomous error rate |
|---|---|---|---|---|---|---|
| A Human oracle | good | 575 | 1.000 | 0.000 | 0.000 | — |
| A Human oracle | structural | 432 | 1.000 | 0.000 | 0.000 | — |
| A Human oracle | logical | 561 | 1.000 | 0.000 | 0.000 | — |
| B Model only | good | 575 | 0.951 | 0.049 | 1.000 | 0.049 |
| B Model only | structural | 432 | 0.606 | 0.394 | 1.000 | 0.394 |
| B Model only | logical | 561 | 0.458 | 0.542 | 1.000 | 0.542 |
| C Static HITL (δ=1σ) | good | 575 | 0.990 | 0.010 | 0.797 | 0.013 |
| C Static HITL (δ=1σ) | structural | 432 | 0.769 | 0.231 | 0.690 | 0.336 |
| C Static HITL (δ=1σ) | logical | 561 | 0.595 | 0.405 | 0.779 | 0.519 |

Error rate = 1 − accuracy: for defect types it is the false-acceptance rate, for good images the false-rejection rate. anomaly_type was never visible to AMP.
