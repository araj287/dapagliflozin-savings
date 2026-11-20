# The budget impact of generic dapagliflozin in England

How much has generic dapagliflozin saved the NHS in England since the September 2025 price break, and how does that compare with NHS England's estimate of £560m?

**Full write-up:** [`report/Generic_dapagliflozin_budget_impact_brief.pdf`](report/Generic_dapagliflozin_budget_impact_brief.pdf)

## Key findings

| Measure | Result |
| --- | --- |
| Saving in the first year, Sep 2025 to Aug 2026 (observed, no forecast) | **£386m** (£378m to £394m across cost measures and trend windows) |
| Saving over Apr 2025 to Mar 2027, NHS England's £560m window (7 of 19 months projected) | **£734m** central, **£659m to £769m** across scenarios |
| Generic 10mg price (NIC) | £1.307 a tablet until Aug 2025, £0.090 by Aug 2026 (−93%) |
| Where the £734m comes from | £644m lower prices on trend volume, £89m above-trend dapagliflozin prescribing, £1m class adjustment |
| Substitution within the SGLT2 class, first year | Dapagliflozin +28.9m tablets vs trend, other SGLT2 inhibitors −29.8m, class −0.8m |
| Comparison with NHS England | The price component alone (£644m) is £84m above the £560m, mainly because generic prices fell further than the estimate implies (about £0.33 a tablet needed vs £0.17 average) |

This is a descriptive counterfactual analysis of public prescribing data at net ingredient cost (NIC). It does not estimate the causal effect of patent loss.


## Method in brief

- **Central estimate: class-level counterfactual (baseline C).** Without generic entry, each SGLT2 inhibitor (dapagliflozin, empagliflozin, canagliflozin, ertugliflozin) is assumed to have continued at its pre-entry price and prescribing trend. The saving is counterfactual class spend minus actual class spend.
- **Baseline A** (price effect on actual volume) gives almost the same answer, because the other SGLT2 inhibitors stayed at £1.307 a tablet and total class volume stayed on trend.
- **Baseline B** (dapagliflozin alone) counts every above-trend tablet as new spending, so it treats substitution within the class as a cost. It is reported for comparison only.
- **Trends:** linear plus month-of-year effects, fitted Sep 2023 to Aug 2025. A 12-month backtest was within 1.5% for dapagliflozin and 1.8% for the class.
- **Projection (Sep 2026 to Mar 2027):** total class volume follows its trend, dapagliflozin share is held at its Aug 2026 level (81.2%), and prices are held at Aug 2026 NIC.
- **Scenarios:** rising or falling dapagliflozin share, the Oct 2026 price concession, actual cost instead of NIC, 18- and 36-month trend windows, the earlier per-drug growth rule, and a combined pessimistic case.
- **Interrupted time series:** dapagliflozin growth did not change at the price break, but accelerated from Feb 2026 (+0.9m tablets a month), coinciding with NICE's NG28 update and ICB switching programmes.

## Repository structure

```
├── report/          Final brief (PDF)
├── dapa_analysis.py Main pipeline: data pull, descriptives, baselines A and B, NHS England bridge, sensitivity, ITS
├── data/            Processed outputs and cached API pulls
├── figs/            Figures 1–10
├── baseline_c/      Class-level counterfactual (central estimate), class-consistent projection and scenarios
│   └── baseline_c_class_counterfactual.md   Equations, results and validation for baseline C
├── refs/            NHS England letter, 6 Oct 2025
└── requirements.txt
```

## Reproduce

```bash
pip install -r requirements.txt
python dapa_analysis.py
```

Needs Python 3.10+ and internet access to `opendata.nhsbsa.net`. The first run takes about 5 minutes. API responses are cached in `data/raw/` and `data/raw_class/`, so later runs take seconds (delete those folders to re-pull). The script prints five checks at the end and exits with an error if any fail.

`dapa_analysis.py` has six sections, each starting with `# %%`, so in VS Code or Spyder you can run one at a time:

| Section | What it does | Outputs |
| --- | --- | --- |
| 0. Settings | Dates, the £1.307 base price, model settings, chart style | |
| 1. Data pull | Dapagliflozin (BNF 0601023AG), Nov 2020 to Aug 2026, plus single-agent SGLT2 inhibitors. One aggregated SQL query per month | `data/dapa_monthly_by_presentation.csv`, `data/sglt2_class_monthly.csv`, `data/code_map.csv` |
| 2. Descriptives | Price per tablet, volume, spend, brand share, actual cost vs NIC | `figs/fig1`–`fig4`, `data/phase2_monthly_summary.csv` |
| 3. Counterfactual | Baselines A and B, projection to Mar 2027 | `figs/fig5`–`fig7`, `data/phase3_*.csv` |
| 4. Plan vs actual | Reconstructs the £560m and bridges it to this estimate | `figs/fig8`, `data/phase4_bridge.csv` |
| 5. Sensitivity | Alternative cases, interrupted time series, switching within the SGLT2 class | `figs/fig9`–`fig10`, `data/phase5_sensitivity.csv` |
| 6. Run everything | Runs sections 1 to 5 and writes every key number and check | `data/results.md` |

The headline baseline C figures and scenarios come from the scripts in `baseline_c/` (`pull_class.py` pulls the class data from Sep 2022, `baseline_c.py` computes baseline C, `proj_alt.py` runs the projection scenarios, `build.py` writes the results tables). See `baseline_c/baseline_c_class_counterfactual.md` for the full method.

To add a newly published month, change `LAST_MONTH` in section 0 of `dapa_analysis.py` and rerun.

## Data notes

- **Source:** NHSBSA Open Data Portal, [English Prescribing Dataset (EPD) with SNOMED code](https://opendata.nhsbsa.net/dataset/english-prescribing-dataset-epd-with-snomed-code), Open Government Licence 3.0. Community-dispensed prescribing in England only; hospital-dispensed medicines are excluded.
- **API:** the datastore is BigQuery. The `EPD_SNOMED_YYYYMM` table name is used as both `resource_id` and the backtick-quoted table. Files up to Feb 2025 use older column names (`BNF_CHEMICAL_SUBSTANCE`, `BNF_CODE`, `BNF_DESCRIPTION`), and `YEAR_MONTH` changes from `YYYYMM` to `YYYY-MM` in Mar 2025. Both are handled.
- **Cost:** NIC is the price before discounts, normally the Drug Tariff price, or the concession price when one is granted. Actual cost is NIC less the national discount deduction, plus container fees; its methodology changed in Apr 2024. Price concessions for generic 10mg were granted in Apr, May, Jul and Aug 2026.
- **Limitations:** NIC is not net cost (VPAG rebates on branded SGLT2s and Category M pharmacy margin are not captured). The data has no diagnosis, so diabetes, heart failure and chronic kidney disease use cannot be separated, and substitution is inferred from aggregates rather than observed.

## References

- NHS England, *Optimising prescribing of SGLT2 inhibitors with generic dapagliflozin*, letter to ICBs, 6 October 2025 (copy in `refs/`).
- NICE, NG28 update and news release, 18 February 2026; NG28 resource impact summary report and template, 2026.
- Community Pharmacy England: dapagliflozin reimbursement prices from September 2025; price concessions, 2026; discount deduction.
- NHSBSA, SGLT2i Opportunities Dashboard (ePACT2), 2026.

## Author

Aakash Rajoriya, BSc Economics, University of Bath
