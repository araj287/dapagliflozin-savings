# Generic dapagliflozin in England: what the 2025 price break saved, plan vs actual

How much did the September 2025 generic dapagliflozin price break save the NHS in England, and how does that compare with NHS England's October 2025 estimate of £560m?

## Results

| Measure | Result |
| --- | --- |
| Saving in the first year, Sep 2025 to Aug 2026 (list price, observed) | **£385m** (range across all sensitivity cases £342m to £386m) |
| Saving over Apr 2025 to Mar 2027, the £560m window (7 of 19 months projected) | **£733m** central, **£610m to £733m** across all cases |
| Generic 10mg list price | £1.307 a tablet until Aug 2025, £0.090 by Aug 2026 (−93%) |
| Why above £560m | Prices fell further than the estimate implied (+£84m); dapagliflozin volume ran above trend (+£89m) |
| Source of the extra volume | Switching within the SGLT2 class: dapagliflozin +28.9m tablets vs trend, other SGLT2 inhibitors −29.8m, class −0.8m |

This is a descriptive, counterfactual analysis of public list-price data. It does not estimate the causal effect of patent loss.

## Reproduce

```bash
pip install -r requirements.txt
python dapa_analysis.py
```

Needs Python 3.10+ and internet access to `opendata.nhsbsa.net`. The first run takes about 5 minutes; API responses are cached in `data/raw/` and `data/raw_class/`, so later runs take seconds (delete those folders to re-pull). The script prints five checks at the end and exits with an error if any fail.

Everything is in one file, `dapa_analysis.py`, in six sections. Each section starts with a `# %%` line, so in VS Code or Spyder you can run one section at a time and see its output.

| Section | What it does | Outputs |
| --- | --- | --- |
| 0. Settings | Dates, the £1.307 base price, model settings, chart style | |
| 1. Data pull | Dapagliflozin (BNF 0601023AG) from the English Prescribing Dataset, Nov 2020 to Aug 2026, plus all single-agent SGLT2 inhibitors from Sep 2023. One aggregated SQL query per month | `data/dapa_monthly_by_presentation.csv`, `data/sglt2_class_monthly.csv`, `data/code_map.csv` |
| 2. Descriptives | Price per tablet, volume, spend, brand share, actual cost vs list price | `figs/fig1`–`fig4`, `data/phase2_monthly_summary.csv` |
| 3. Counterfactual | Saving vs a flat £1.307 price; baseline A (actual volume) and B (trend volume); projection to Mar 2027 | `figs/fig5`–`fig7`, `data/phase3_*.csv` |
| 4. Plan vs actual | Reconstructs £560m and bridges it to this estimate | `figs/fig8`, `data/phase4_bridge.csv` |
| 5. Sensitivity | Nine alternative cases, interrupted time series, switching within the SGLT2 class | `figs/fig9`–`fig10`, `data/phase5_sensitivity.csv` |
| 6. Run everything | Runs sections 1 to 5 and writes every key number and check | `data/results.md` |

To add a newly published month, change `LAST_MONTH` in section 0 and rerun.

## Method in brief

- **Saving** in month t = Σ over presentations of tablets × (£1.307 − list price per tablet). £1.307 was the price of every presentation in every month from Nov 2020 to Aug 2025. Forxiga (brand) tablets carry no saving.
- **Baseline A** uses actual volume. **Baseline B** uses the volume a pre-break trend predicts (linear trend plus month-of-year effects, fitted Sep 2023 to Aug 2025), so volume above trend counts as a cost. The class analysis shows the extra volume is switching from drugs that still cost £1.307, so A is the central estimate and B a floor.
- **Projection** (Sep 2026 to Mar 2027): same month a year earlier × recent year-on-year growth (40%), last-3-month presentation mix, Aug 2026 prices held.
- **Reconciliation:** the £560m is back-solved for the generic price it implies at trend volume (£0.328 a tablet), then bridged to baseline A in a price step and a volume step.
- **Sensitivity:** projected growth 30%, 20% and 0%; the Oct 2026 price concession; actual cost instead of list price; 18- and 36-month trend windows; all pessimistic options together.

## Data notes

- **Source:** NHSBSA Open Data Portal, [English Prescribing Dataset (EPD) with SNOMED code](https://opendata.nhsbsa.net/dataset/english-prescribing-dataset-epd-with-snomed-code), Open Government Licence 3.0. Community prescribing in England only; hospital use is excluded.
- **API:** the datastore is BigQuery. The `EPD_SNOMED_YYYYMM` table name is used as both `resource_id` and the backtick-quoted table. Files up to Feb 2025 use older column names (`BNF_CHEMICAL_SUBSTANCE`, `BNF_CODE`, `BNF_DESCRIPTION`), and YEAR_MONTH changes from `YYYYMM` to `YYYY-MM` in Mar 2025. Both are handled.
- **Cost:** NIC is the Drug Tariff list price. ACTUAL_COST is NIC less the estimated pharmacy discount, plus container fees. The discount method changed in Apr 2024. Price concession months (generic 10mg in Apr, May, Jul and Aug 2026) have no discount deducted.
- **Indication:** the data has no diagnosis, so diabetes, heart failure and chronic kidney disease use cannot be separated.

## References

- NHS England, *Optimising prescribing of SGLT2 inhibitors with generic dapagliflozin*, letter to ICBs, 6 October 2025 (copy in `refs/`).
- NICE, NG28 update and news release, 18 February 2026; NG28 resource impact template (June 2026).
- Community Pharmacy England, dapagliflozin reimbursement prices from September 2025; price concessions, April to October 2026; discount deduction.
