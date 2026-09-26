**T1. Test stream and PatchCore perception (seed 0, frozen scores). Proposal = raw score >= tau (0.95 quantile of validation-normal scores).**

| Category | Good | Structural | Logical | AUROC all | AUROC logical | AUROC structural | tau | Proposal FA rate | Proposal FR rate |
|---|---|---|---|---|---|---|---|---|---|
| breakfast_box | 102 | 90 | 83 | 0.857 | 0.864 | 0.851 | 43.43 | 0.277 | 0.078 |
| juice_bottle | 94 | 94 | 142 | 0.925 | 0.908 | 0.950 | 33.78 | 0.148 | 0.085 |
| pushpins | 138 | 81 | 91 | 0.741 | 0.696 | 0.792 | 43.03 | 0.657 | 0.051 |
| screw_bag | 122 | 82 | 137 | 0.704 | 0.611 | 0.861 | 51.94 | 0.808 | 0.016 |
| splicing_connectors | 119 | 85 | 108 | 0.833 | 0.782 | 0.898 | 41.66 | 0.523 | 0.025 |
| All (macro AUROC) | 575 | 432 | 561 | 0.812 | 0.772 | 0.870 | - | 0.477 | 0.049 |

Test stream is anomaly-heavy (63.3%): a benchmark distribution, not a production rate. AUROC is threshold-free; FA/FR rates are for the fixed-threshold proposal.
