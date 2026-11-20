# Baseline C: class-level counterfactual (added 2026-11-20)

**Question:** what would NHS England primary care have spent on the whole SGLT2 inhibitor class if generic dapagliflozin had never arrived? This replaces "what would dapagliflozin alone have cost".

**Answer:** Baseline C lands almost exactly on Baseline A. Baseline B is not a cautious floor. It is mis-specified, because it charges the switching that generic entry caused as if it were extra spending.

## Equations (all list-price, NIC basis; savings are zero before Sep 2025 by construction)

| Name | Formula | What it assumes |
| --- | --- | --- |
| A, price effect | Σₜ Q_act,dapa × (P₀ − P_act,dapa) | Same dapagliflozin tablets, pre-entry price |
| B, single-drug expenditure | Σₜ (Q_trend,dapa × P₀ − Q_act,dapa × P_act,dapa) | Extra dapagliflozin tablets are new spending at £1.307 |
| Price-only, trend volume | Σₜ Q_trend,dapa × (P₀ − P_act,dapa) | Trend tablets, actual price (£644m in the window; differs from B by excess tablets × actual price, about £11m) |
| **C, class expenditure** | **Σₜ [Σ_d Q_trend,d × P₀,d − Σ_d Q_act,d × P_act,d]**, d = dapagliflozin, empagliflozin, canagliflozin, ertugliflozin | Without generic entry, every SGLT2 follows its own pre-entry trend at its pre-entry price |

**Identity.** Empagliflozin and canagliflozin are £1.307 a tablet, the same as pre-entry dapagliflozin, and their prices never changed (checked Sep 2023 to Aug 2026). Ertugliflozin is £1.05 but negligible in volume. So, to within rounding:

> **C = A − P₀ × (class tablets − class trend tablets)**

C differs from A only by the class volume deviation valued at £1.307. Whether an above-trend dapagliflozin tablet is a switch or a new start that would otherwise have begun on empagliflozin doesn't matter for the saving. What matters is whether the class as a whole grew. The causal question (switch vs new start) still can't be answered with aggregate data.

## Results (£m)

| Window | A | B | **C (mono)** | C (incl. SGLT2 combos) | Dapa vs trend (m tabs) | Other SGLT2 vs trend | Class vs trend |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Observed Sep 2025 to Aug 2026 | 385.4 | 347.6 | **386.5** | 387.3 | +28.9 | −29.8 | −0.8 |
| FY 2025/26 | 176.0 | 167.3 | **173.8** | 173.9 | +6.6 | −4.9 | +1.7 |
| FY 2026/27 (7 months projected) | 556.8 | 466.1 | **545.4** | 547.0 | +69.4 | −60.7 | +8.7 |
| NICE window Apr 2025 to Mar 2027 | 732.8 | 633.4 | **719.2** | 720.8 | +76.0 | −65.6 | +10.4 |

A and B reproduce the Phase 3 figures. The observed-year C (£386.5m) also matches the Phase 5 class check (£386m), which is now set out formally.

## Projection check (Sep 2026 to Mar 2027)

The original rule (same month last year × own Mar–Aug 2026 YoY growth: dapagliflozin 1.404, empagliflozin 0.786, canagliflozin 0.807) applied to each drug separately does not keep the class consistent. Projected class volume runs 1.6m tablets a month above trend on average, against −0.07m a month in the observed year. That is why C (£719m) falls slightly below A in the window. Class-consistent alternatives:

| Projection for the 7 months | C, projected months | C, NICE window |
| --- | --- | --- |
| Original rule, per drug | 332.7 | 719.2 |
| Class at trend, dapa share held at Aug 2026 (81.2%) | 347.2 | 733.7 |
| Class at trend, share keeps rising at Mar–Aug pace (+2.1pp/month, capped at 95%) | 382.7 | 769.2 |

## Trend validation

Per-drug trends use the same specification as Phase 3: linear plus month-of-year dummies, fitted Sep 2023 to Aug 2025. Twelve-month-ahead backtest (fit Sep 2022 to Aug 2024, predict Sep 2024 to Aug 2025): dapagliflozin −1.4%, empagliflozin −2.3%, canagliflozin −3.6%, ertugliflozin −4.7%, class −1.8%. The window extrapolates the trend 19 months, beyond the 12 months tested.

## What this changes in the report

1. Headline: state A (= C) as the central estimate. Present B as a single-drug counterfactual that ignores displacement within the class, not as a lower bound.
2. Sensitivity range: the £610m lower end comes from B-based cases, so restate the range on the C basis.
3. Point 1 of the review: retitle Fig 2. Then note that the savings figure rests on flat class volume, which the aggregate data does show, not on proving switches.
4. Point 4: replace the per-drug ×1.404 rule with a class-consistent projection (class trend × dapagliflozin share), reported with held-share and rising-share variants.
5. Caveats that still apply: list price, not net cost (branded SGLT2s are subject to VPAG rebates, and generic prices fund pharmacy margin under Category M); community prescribing only.

Data: NHSBSA EPD with SNOMED, BNF 0601023 (AG, AN, AM, AX mono; AL, AR, AP, AV, AY combos), Sep 2022 to Aug 2026. Sep 2026 was not yet on the portal on 20 Nov 2026.
