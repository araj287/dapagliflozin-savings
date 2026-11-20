"""
Generic dapagliflozin in England: what the 2025 price break saved, plan vs actual.

One script that rebuilds every number and figure in the project from the NHSBSA
public API. Run it top to bottom:

    pip install -r requirements.txt
    python dapa_analysis.py

or open it in VS Code / Spyder and run it section by section (each "# %%" line
starts a section). A full run takes about 5 minutes the first time; API responses
are cached in data/raw/ and data/raw_class/, so later runs take seconds.

Sections
  0. Settings           dates, prices, colours used everywhere
  1. Data pull          dapagliflozin from the English Prescribing Dataset, Nov 2020 to Aug 2026
  2. Descriptives       price, volume, brand share, actual cost            -> figs 1-4
  3. Counterfactual     savings vs the old £1.307 price, baselines A and B -> figs 5-7
  4. Plan vs actual     reconstruct NHS England's £560m and bridge to ours -> fig 8
  5. Sensitivity        alternative assumptions, time series, class switching -> figs 9-10
  6. Run everything     writes data/results.md with every key number and check

Outputs: data/*.csv, data/results.md, figs/fig1-fig10.
"""

# %% 0. Settings ----------------------------------------------------------------

import json
import re
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
DATA, FIGS = ROOT / "data", ROOT / "figs"
RAW, RAW_CLASS = DATA / "raw", DATA / "raw_class"
for d in (DATA, FIGS, RAW, RAW_CLASS):
    d.mkdir(parents=True, exist_ok=True)

# Data window
FIRST_MONTH, LAST_MONTH = "2020-11", "2026-08"       # update LAST_MONTH when new data is published
CLASS_FIRST_MONTH = "2023-09"

# Key dates
BREAK = pd.Timestamp("2025-09-01")                   # first month of generic pricing
LAST_OBS = pd.Timestamp(LAST_MONTH + "-01")          # last month of published data
OCT25 = pd.Timestamp("2025-10-01")
NICE_GUIDANCE = pd.Timestamp("2026-02-01")           # NICE NG28 update, 18 Feb 2026
WINDOW_START, WINDOW_END = pd.Timestamp("2025-04-01"), pd.Timestamp("2027-03-01")  # FY 2025/26 + 2026/27
COST_METHOD_CHANGE = pd.Timestamp("2024-04-01")      # NHSBSA actual-cost method change

# Prices and estimates
P_BASE = 1.307                    # £ per tablet, every presentation, Nov 2020 to Aug 2025 (£36.59 per 28)
NHSE_ESTIMATE_M = 560.0           # NHS England letter, 6 Oct 2025, £m
OCT26_CONCESSION_10MG = 4.78 / 28  # £ per tablet, Oct 2026 price concession

# Model settings
TREND_MONTHS = 24                 # months before the break used to fit the volume trend
GROWTH_MONTHS = 6                 # recent months used for the projection growth rate
MIX_MONTHS = 3                    # recent months used for the projected presentation mix

# Products
DAPA = "0601023AG"
PRESENTATIONS = {"0601023AGAAABAB": "Generic 10mg", "0601023AGAAAAAA": "Generic 5mg",
                 "0601023AGBBABAB": "Forxiga 10mg", "0601023AGBBAAAA": "Forxiga 5mg"}
PRES = list(PRESENTATIONS.values())
GENERICS = ["Generic 10mg", "Generic 5mg"]
SGLT2 = {"0601023AG": "Dapagliflozin", "0601023AN": "Empagliflozin",
         "0601023AM": "Canagliflozin", "0601023AX": "Ertugliflozin"}

# Chart style: one blue accent, everything else grey
BLUE, BLUE_LIGHT, GREY, GREY_LIGHT = "#2a78d6", "#9cc1ee", "#8a8984", "#c9c8c3"
GREEN, RED = "#0ca30c", "#d03b3b"
INK, INK_2, GRID, SHADE = "#0b0b0b", "#52514e", "#e6e5e1", "#f3f2ef"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GREY_LIGHT,
    "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK_2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.8,
    "figure.dpi": 150, "savefig.bbox": "tight", "savefig.facecolor": "white",
})
SOURCE = ("Source: NHSBSA English Prescribing Dataset with SNOMED code, BNF 0601023AG, "
          "community prescribing in England.")

GATES: dict[str, bool] = {}       # every phase records its pass/fail check here


def titles(fig, title, subtitle):
    fig.text(0.0, 1.06, title, fontsize=13, fontweight="bold", color=INK, ha="left")
    fig.text(0.0, 1.015, subtitle, fontsize=10, color=INK_2, ha="left")


def source(fig, extra="", y=-0.07, base=SOURCE):
    fig.text(0.0, y, base + ("\n" + extra if extra else ""), fontsize=7.5, color=INK_2, ha="left")


def save(fig, name):
    fig.savefig(FIGS / name)
    plt.close(fig)


def mark_break(ax, label=True, y=0.97, side="right"):
    ax.axvline(BREAK, color=GREY, lw=1, zorder=1)
    if label:
        txt = "  Price break, Sep 2025" if side == "right" else "Price break, Sep 2025  "
        ax.text(BREAK, y, txt, transform=ax.get_xaxis_transform(), color=INK_2, fontsize=9,
                va="top", ha="left" if side == "right" else "right")


def year_axis(ax):
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.tick_params(length=0)


def month_axis(ax, fmt="%b %Y"):
    ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))
    ax.tick_params(length=0)


# %% 1. Data pull ---------------------------------------------------------------
# The NHSBSA portal runs CKAN with a BigQuery datastore. For each month we send one
# SQL query that sums dapagliflozin rows by presentation, so we download a few rows
# a month instead of a multi-GB file.

API = "https://opendata.nhsbsa.net/api/3/action"
DATASET = "english-prescribing-dataset-epd-with-snomed-code"

# Files up to Feb 2025 use older column names.
SCHEMAS = {"new": dict(chem="BNF_CHEMICAL_SUBSTANCE_CODE", code="BNF_PRESENTATION_CODE", name="BNF_PRESENTATION_NAME"),
           "old": dict(chem="BNF_CHEMICAL_SUBSTANCE", code="BNF_CODE", name="BNF_DESCRIPTION")}


def month_range(start, end):
    return [d.strftime("%Y-%m") for d in pd.date_range(start + "-01", end + "-01", freq="MS")]


def get_json(url, params, tries=5):
    """Call the API, retrying on network errors and server errors (not on bad queries)."""
    for attempt in range(1, tries + 1):
        try:
            r = requests.get(url, params=params, timeout=300)
            r.raise_for_status()
            js = r.json()
            if not js.get("success", False):
                raise RuntimeError(js.get("error"))
            return js["result"]
        except Exception as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status is not None and 400 <= status < 500:
                raise RuntimeError(f"{status}: {e.response.text[:500]}") from None
            if attempt == tries:
                raise
            print(f"    retry {attempt}/{tries - 1} in {10 * attempt}s ({e})")
            time.sleep(10 * attempt)


def table_names():
    """Map 'YYYY-MM' to the BigQuery table holding that month (e.g. EPD_SNOMED_202508)."""
    pkg = get_json(f"{API}/package_show", {"id": DATASET})
    idx = {}
    for res in pkg["resources"]:
        m = re.search(r"EPD_SNOMED_(\d{4})(\d{2})", (res.get("name") or "") + " " + (res.get("url") or ""), re.I)
        if m and (res.get("datastore_active") or (res.get("format") or "").upper() == "CSV"):
            idx.setdefault(f"{m.group(1)}-{m.group(2)}", res.get("bq_table_name") or res.get("name"))
    return idx


def query(table, sql):
    res = get_json(f"{API}/datastore_search_sql", {"resource_id": table, "sql": sql})
    return res["result"]["records"] if "result" in res else res["records"]


def dapa_sql(table, schema):
    c = SCHEMAS[schema]
    num = lambda col: f"SUM(SAFE_CAST({col} AS NUMERIC)) AS {col}"
    keys = ["SAFE_CAST(YEAR_MONTH AS STRING)", c["code"], c["name"], "SAFE_CAST(SNOMED_CODE AS STRING)"]
    return (f"SELECT {keys[0]} AS YEAR_MONTH, {c['code']} AS BNF_PRESENTATION_CODE, "
            f"{c['name']} AS BNF_PRESENTATION_NAME, {keys[3]} AS SNOMED_CODE, "
            f"{num('ITEMS')}, {num('TOTAL_QUANTITY')}, {num('NIC')}, {num('ACTUAL_COST')}, COUNT(*) AS N_ROWS "
            f"FROM `{table}` WHERE {c['chem']} = '{DAPA}' GROUP BY {', '.join(keys)}")


def class_sql(table, schema):
    chem = SCHEMAS[schema]["chem"]
    codes = ", ".join(f"'{c}'" for c in SGLT2)
    return (f"SELECT SAFE_CAST(YEAR_MONTH AS STRING) AS YEAR_MONTH, {chem} AS CHEM, "
            "SUM(SAFE_CAST(TOTAL_QUANTITY AS NUMERIC)) AS TOTAL_QUANTITY, SUM(SAFE_CAST(NIC AS NUMERIC)) AS NIC "
            f"FROM `{table}` WHERE {chem} IN ({codes}) GROUP BY 1, 2")


def cached(path, fetch):
    """Return the cached API response if we have it, otherwise fetch and cache it."""
    if path.exists():
        return json.loads(path.read_text())
    records = fetch()
    path.write_text(json.dumps(records))
    time.sleep(0.5)
    return records


def normalise_month(v):
    s = str(v).strip()          # YYYYMM up to Feb 2025, YYYY-MM after
    return f"{s[:4]}-{s[4:]}" if re.fullmatch(r"\d{6}", s) else s


def pull_dapa(tables):
    rows, missing = [], []
    for ym in month_range(FIRST_MONTH, LAST_MONTH):
        if ym not in tables:
            missing.append(ym)
            continue
        schema = "old" if ym < "2025-03" else "new"
        rows += cached(RAW / f"epd_{ym.replace('-', '')}.json", lambda: query(tables[ym], dapa_sql(tables[ym], schema)))
    df = pd.DataFrame(rows)
    df["YEAR_MONTH"] = df["YEAR_MONTH"].map(normalise_month)
    for c in ["ITEMS", "TOTAL_QUANTITY", "NIC", "ACTUAL_COST", "N_ROWS"]:
        df[c] = pd.to_numeric(df[c])
    df["SNOMED_CODE"] = df["SNOMED_CODE"].astype(str).str.replace(r"\.0$", "", regex=True)
    df["presentation_label"] = df["BNF_PRESENTATION_CODE"].map(PRESENTATIONS).fillna("OTHER")
    df["is_brand"] = df["BNF_PRESENTATION_CODE"].str[9:11] != "AA"     # characters 10-11: AA = generic
    df["is_combination"] = df["BNF_PRESENTATION_NAME"].str.contains("metformin", case=False)
    df["cost_method"] = np.where(df["YEAR_MONTH"] >= "2024-04", "post_apr2024", "pre_apr2024")
    df["nic_per_unit"] = df["NIC"] / df["TOTAL_QUANTITY"]
    df["actual_cost_per_unit"] = df["ACTUAL_COST"] / df["TOTAL_QUANTITY"]
    df["actual_cost_share_of_nic"] = df["ACTUAL_COST"] / df["NIC"]
    df = df.sort_values(["YEAR_MONTH", "BNF_PRESENTATION_CODE", "SNOMED_CODE"]).reset_index(drop=True)
    return df, missing


def pull_class(tables):
    rows = []
    for ym in month_range(CLASS_FIRST_MONTH, LAST_MONTH):
        schema = "old" if ym < "2025-03" else "new"
        rows += cached(RAW_CLASS / f"{ym}.json", lambda: query(tables[ym], class_sql(tables[ym], schema)))
    df = pd.DataFrame(rows)
    df["month"] = df["YEAR_MONTH"].map(normalise_month)
    df["chemical"] = df["CHEM"].map(SGLT2)
    df[["TOTAL_QUANTITY", "NIC"]] = df[["TOTAL_QUANTITY", "NIC"]].apply(pd.to_numeric)
    return df.groupby(["month", "chemical"])[["TOTAL_QUANTITY", "NIC"]].sum().reset_index()


def check_pull(df, missing):
    """Gate 1: every month present, the four presentations in every month, and a match with the day-1 test."""
    months = month_range(FIRST_MONTH, LAST_MONTH)
    got = set(df["YEAR_MONTH"])
    core = df[df["presentation_label"] != "OTHER"]
    per_code = core.groupby("BNF_PRESENTATION_CODE")["YEAR_MONTH"].nunique()
    names = df.groupby("BNF_PRESENTATION_CODE")["BNF_PRESENTATION_NAME"].nunique()
    g10 = df[df["presentation_label"] == "Generic 10mg"].groupby("YEAR_MONTH")[["NIC", "TOTAL_QUANTITY"]].sum()
    day1 = {"2025-08": 1.307, "2025-10": 0.498}
    day1_ok = all(abs(g10.loc[m, "NIC"] / g10.loc[m, "TOTAL_QUANTITY"] - v) < 0.002 for m, v in day1.items())
    GATES["1. No missing months, codes stable, matches day-1 test"] = (
        not missing and got == set(months) and len(per_code) == 4
        and (per_code == len(months)).all() and (names == 1).all() and day1_ok)
    code_map = (df.groupby(["BNF_PRESENTATION_CODE", "BNF_PRESENTATION_NAME", "SNOMED_CODE"])
                .agg(first_month=("YEAR_MONTH", "min"), last_month=("YEAR_MONTH", "max"),
                     n_months=("YEAR_MONTH", "nunique"), items=("ITEMS", "sum")).reset_index())
    return code_map


# %% 2. Descriptives ------------------------------------------------------------

def presentations(df):
    """Monthly totals by presentation: columns (measure, presentation), index = month."""
    df = df[~df["is_combination"]].copy()
    df["month"] = pd.to_datetime(df["YEAR_MONTH"] + "-01")
    return df.groupby(["month", "presentation_label"])[["ITEMS", "TOTAL_QUANTITY", "NIC", "ACTUAL_COST"]].sum().unstack()


def monthly_summary(df, p):
    cols = ["ITEMS", "TOTAL_QUANTITY", "NIC", "ACTUAL_COST"]
    df = df[~df["is_combination"]].copy()
    df["date"] = pd.to_datetime(df["YEAR_MONTH"] + "-01")
    s = df.groupby("date")[cols].sum()
    s["brand_items"] = df[df["is_brand"]].groupby("date")["ITEMS"].sum()
    s["brand_share_items_pct"] = s["brand_items"] / s["ITEMS"] * 100
    s["nic_per_tablet_all"] = s["NIC"] / s["TOTAL_QUANTITY"]
    s["actual_share_of_nic_pct"] = s["ACTUAL_COST"] / s["NIC"] * 100
    for label, key in [("Generic 10mg", "g10"), ("Generic 5mg", "g5"), ("Forxiga 10mg", "b10"), ("Forxiga 5mg", "b5")]:
        s[f"nic_per_tablet_{key}"] = p["NIC"][label] / p["TOTAL_QUANTITY"][label]
        s[f"actual_share_of_nic_pct_{key}"] = p["ACTUAL_COST"][label] / p["NIC"][label] * 100
    g = df[~df["is_brand"]].groupby("date")[["NIC", "ACTUAL_COST"]].sum()
    b = df[df["is_brand"]].groupby("date")[["NIC", "ACTUAL_COST"]].sum()
    s["actual_share_of_nic_pct_generic"] = g["ACTUAL_COST"] / g["NIC"] * 100
    s["actual_share_of_nic_pct_brand"] = b["ACTUAL_COST"] / b["NIC"] * 100
    # Concession months: generic 10mg paid with no discount deducted, so actual cost is about 100% of list price
    s["g10_concession_month"] = (s.index >= BREAK) & (s["actual_share_of_nic_pct_g10"] > 95)
    s["cost_method"] = np.where(s.index >= COST_METHOD_CHANGE, "post_apr2024", "pre_apr2024")
    return s


def end_label(ax, s, text, color, dy=0):
    ax.annotate(text, (s.index[-1], s.iloc[-1]), xytext=(6, dy), textcoords="offset points",
                color=color if color != GREY else INK_2, fontsize=9, va="center")


def fig1_price(s):
    fig, ax = plt.subplots(figsize=(9, 4.4))
    ax.plot(s.index, s["nic_per_tablet_b10"], color=GREY, lw=2)
    ax.plot(s.index, s["nic_per_tablet_g5"], color=BLUE_LIGHT, lw=2)
    ax.plot(s.index, s["nic_per_tablet_g10"], color=BLUE, lw=2.4)
    mark_break(ax)
    first, last = s["nic_per_tablet_g10"].iloc[0], s["nic_per_tablet_g10"].iloc[-1]
    oct25 = s.loc[OCT25, "nic_per_tablet_g10"]
    ax.annotate(f"£{oct25:.3f}", (OCT25, oct25), xytext=(-46, -4), textcoords="offset points",
                color=INK, fontsize=9, fontweight="bold")
    end_label(ax, s["nic_per_tablet_g10"], f"£{last:.3f}  Generic 10mg", BLUE, dy=-6)
    end_label(ax, s["nic_per_tablet_g5"], "Generic 5mg", BLUE, dy=8)
    end_label(ax, s["nic_per_tablet_b10"], "Forxiga 10mg", GREY)
    ax.set_ylim(0, 1.45)
    ax.yaxis.set_major_formatter(lambda v, _: f"£{v:.2f}")
    ax.set_ylabel("NIC per tablet")
    year_axis(ax)
    titles(fig, f"Generic list price fell {(1 - last / first) * 100:.0f}% after the price break and was still falling in 2026",
           f"NIC per tablet: generic 10mg £{first:.3f} until Aug 2025, £{last:.3f} in {s.index[-1]:%b %Y}. "
           f"Forxiga stayed at £{s['nic_per_tablet_b10'].iloc[-1]:.3f}.")
    source(fig, "Forxiga 5mg tracks Forxiga 10mg and is omitted.", y=-0.06)
    save(fig, "fig1_price_per_tablet.png")


def fig2_volume_spend(s):
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True, gridspec_kw={"hspace": 0.28})
    tabs, spend = s["TOTAL_QUANTITY"] / 1e6, s["NIC"] / 1e6
    colours = [GREY if d < BREAK else BLUE for d in s.index]
    a1.bar(s.index, tabs, width=24, color=colours)
    a1.set_ylabel("Tablets (millions)")
    a1.set_title("Tablets dispensed per month", loc="left", fontsize=10, color=INK)
    a2.bar(s.index, spend, width=24, color=colours)
    a2.set_ylabel("NIC (£ millions)")
    a2.set_title("List-price spend per month", loc="left", fontsize=10, color=INK)
    for ax in (a1, a2):
        mark_break(ax, label=ax is a1, side="left")
        year_axis(ax)
    peak = spend[s.index < BREAK].idxmax()
    a2.annotate(f"£{spend[peak]:.1f}m", (peak, spend[peak]), xytext=(0, 4), textcoords="offset points",
                ha="center", fontsize=9, color=INK)
    a2.annotate(f"£{spend.iloc[-1]:.1f}m", (s.index[-1], spend.iloc[-1]), xytext=(0, 4), textcoords="offset points",
                ha="center", fontsize=9, color=INK, fontweight="bold")
    a1.annotate(f"{tabs.iloc[-1]:.1f}m", (s.index[-1], tabs.iloc[-1]), xytext=(0, 4), textcoords="offset points",
                ha="center", fontsize=9, color=INK)
    pre12, post12 = s.loc["2024-09-01":"2025-08-01"], s.loc[BREAK:LAST_OBS]
    vol_g = (post12["TOTAL_QUANTITY"].sum() / pre12["TOTAL_QUANTITY"].sum() - 1) * 100
    sp_g = (post12["NIC"].sum() / pre12["NIC"].sum() - 1) * 100
    titles(fig, f"Volume kept growing while spend fell to {spend.iloc[-1] / spend[peak] * 100:.0f}% of its peak",
           f"Sep 2025–Aug 2026 vs the 12 months before: tablets {vol_g:+.0f}%, NIC spend {sp_g:+.0f}%. "
           "Blue = after the price break.")
    source(fig, y=-0.06)
    save(fig, "fig2_volume_and_spend.png")
    return vol_g, sp_g


def fig3_brand_share(s):
    fig, ax = plt.subplots(figsize=(9, 3.8))
    sh = s["brand_share_items_pct"]
    ax.plot(s.index, sh, color=BLUE, lw=2.2)
    mark_break(ax)
    lo, hi = sh[s.index < BREAK].idxmin(), sh[s.index >= BREAK].idxmax()
    for d, va, dy in [(s.index[0], "bottom", 6), (lo, "top", -8), (hi, "bottom", 6), (s.index[-1], "bottom", 6)]:
        ax.annotate(f"{sh[d]:.1f}%", (d, sh[d]), xytext=(0, dy), textcoords="offset points",
                    ha="center", va=va, fontsize=9, color=INK)
    ax.set_ylim(0, sh.max() * 1.2)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.set_ylabel("Forxiga share of items")
    year_axis(ax)
    titles(fig, f"Brand share doubled after the break, from {sh[lo]:.1f}% to {sh[hi]:.1f}%, then eased",
           "Forxiga (5mg + 10mg) items as a share of all dapagliflozin items. "
           "Branded prescribing stays at the £1.307 brand price.")
    source(fig, y=-0.06)
    save(fig, "fig3_brand_share.png")
    return sh[lo], sh[hi], sh.iloc[-1]


def fig4_actual_vs_nic(s):
    fig, ax = plt.subplots(figsize=(9, 4.2))
    g, b = s["actual_share_of_nic_pct_generic"], s["actual_share_of_nic_pct_brand"]
    ax.plot(s.index, b, color=GREY, lw=2)
    ax.plot(s.index, g, color=BLUE, lw=2.2)
    conc = s.index[s["g10_concession_month"]]
    ax.scatter(conc, g[conc], s=38, color=BLUE, zorder=3, edgecolor="white", linewidth=1.5)
    mark_break(ax, y=0.08)
    ax.axvline(COST_METHOD_CHANGE, color=GREY_LIGHT, lw=1, ls="--")
    ax.text(COST_METHOD_CHANGE, 0.08, "Discount method change, Apr 2024  ", transform=ax.get_xaxis_transform(),
            color=INK_2, fontsize=9, va="top", ha="right")
    end_label(ax, g, "Generic", BLUE, dy=8)
    end_label(ax, b, "Forxiga", GREY)
    ax.scatter([pd.Timestamp("2021-01-01")], [84], s=38, color=BLUE, edgecolor="white", linewidth=1.5)
    ax.text(pd.Timestamp("2021-03-01"), 84, "Generic 10mg price concession months\n(no discount deducted): "
            + ", ".join(conc.strftime("%b %Y")), color=INK_2, fontsize=9, va="center")
    ax.set_ylim(75, 103)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.set_ylabel("Actual cost as % of NIC")
    year_axis(ax)
    post = s.loc[s.index >= BREAK]
    normal = post.loc[~post["g10_concession_month"], "actual_share_of_nic_pct_generic"]
    titles(fig, f"Generic actual cost fell to about {normal.mean():.0f}% of list price after the break",
           "After the break, generic items take the 20% generic discount deduction and brand items 5%. "
           "Before it, generic prescriptions were paid at the brand price.")
    source(fig, "\nActual cost = NIC less estimated discount plus container fees. "
                "Concession months = generic 10mg actual cost over 95% of NIC.", y=-0.06)
    save(fig, "fig4_actual_vs_nic.png")
    return list(conc.strftime("%b %Y"))


def descriptives(df, p):
    s = monthly_summary(df, p)
    s.round(6).to_csv(DATA / "phase2_monthly_summary.csv", index_label="month")
    fig1_price(s)
    vol_g, sp_g = fig2_volume_spend(s)
    share = fig3_brand_share(s)
    conc = fig4_actual_vs_nic(s)
    g10 = s["nic_per_tablet_g10"]
    pre = g10[s.index < BREAK]
    GATES["2. Price break visible in Sep 2025"] = bool(g10[BREAK] < g10[BREAK - pd.DateOffset(months=1)] * 0.95
                                                      and pre.std() / pre.mean() < 0.01)
    return {"g10": g10, "vol_g": vol_g, "sp_g": sp_g, "share": share, "concessions": conc}


# %% 3. Counterfactual ----------------------------------------------------------
# Saving in month t = tablets x (£1.307 - list price per tablet), by presentation.
#   Baseline A: actual volume (the headline).
#   Baseline B: the counterfactual uses the volume the pre-break trend predicts, so any
#               volume above trend counts as a cost at £1.307.
# Sep 2026 to Mar 2027 is projected to cover NHS England's window (Apr 2025 to Mar 2027).

def month_design(idx):
    """Columns: constant, linear time trend, 11 month-of-year dummies."""
    t = np.array([(d.year - 2020) * 12 + d.month for d in idx], float)
    dummies = [[1.0 if d.month == m else 0.0 for d in idx] for m in range(2, 13)]
    return np.column_stack([np.ones_like(t), t] + dummies)


def fit_trend(q, end, months=TREND_MONTHS):
    train = q.index[(q.index <= end) & (q.index > end - pd.DateOffset(months=months))]
    beta = np.linalg.lstsq(month_design(train), q[train].values, rcond=None)[0]
    return beta, train


def trend_line(q, months=TREND_MONTHS, index=None):
    beta, _ = fit_trend(q, BREAK - pd.DateOffset(months=1), months)
    idx = q.index if index is None else index
    return pd.Series(month_design(idx) @ beta, index=idx)


def backtest(q):
    """Fit the trend 12 months earlier and see how well it predicts the next 12 months."""
    out = []
    for end in ["2024-08-01", "2025-08-01"]:
        e = pd.Timestamp(end)
        beta, _ = fit_trend(q, e - pd.DateOffset(months=12))
        test = q.index[(q.index > e - pd.DateOffset(months=12)) & (q.index <= e)]
        out.append((f"{test[0]:%b %Y}-{test[-1]:%b %Y}", ((month_design(test) @ beta).sum() / q[test].sum() - 1) * 100))
    return out


def project(p, growth=None, oct26_price=False):
    """Sep 2026 to Mar 2027: same month a year earlier x (1 + growth), recent mix, Aug 2026 prices."""
    q = p["TOTAL_QUANTITY"]
    q_tot = q.sum(axis=1)
    last = q_tot.index[-GROWTH_MONTHS:]
    g_obs = q_tot[last].sum() / q_tot[last - pd.DateOffset(months=12)].sum() - 1
    g = g_obs if growth is None else growth
    mix = q.iloc[-MIX_MONTHS:].sum() / q_tot.iloc[-MIX_MONTHS:].sum()
    price = p["NIC"].iloc[-1] / q.iloc[-1]
    if oct26_price:
        uplift = OCT26_CONCESSION_10MG / price["Generic 10mg"]
        price = price.copy()
        price["Generic 10mg"] = OCT26_CONCESSION_10MG
        price["Generic 5mg"] *= uplift
    months = pd.date_range(LAST_OBS + pd.DateOffset(months=1), WINDOW_END, freq="MS")
    q_proj = pd.DataFrame({m: q_tot[m - pd.DateOffset(months=12)] * (1 + g) * mix for m in months}).T
    return q_proj, q_proj * price, g


def savings(p):
    for pres in PRES:   # check: every presentation cost £1.307 in every pre-break month
        pre = p.loc[p.index < BREAK]
        assert np.allclose(pre["NIC"][pres] / pre["TOTAL_QUANTITY"][pres], P_BASE, atol=0.002)
    q_proj, nic_proj, g = project(p)
    Q = pd.concat([p["TOTAL_QUANTITY"], q_proj])
    NIC = pd.concat([p["NIC"], nic_proj])
    s = pd.DataFrame(index=Q.index)
    s["status"] = np.where(s.index <= LAST_OBS, "observed", "projected")
    s["tablets"] = Q.sum(axis=1)
    s["tablets_trend"] = trend_line(p["TOTAL_QUANTITY"].sum(axis=1), index=s.index)
    s["nic"] = NIC.sum(axis=1)
    s["nic_per_tablet"] = s["nic"] / s["tablets"]
    s["cf_spend_A"] = s["tablets"] * P_BASE
    s["cf_spend_B"] = s["tablets_trend"] * P_BASE
    post = s.index >= BREAK
    s["price_effect"] = np.where(post, s["cf_spend_A"] - s["nic"], 0.0)
    s["volume_effect"] = np.where(post, (s["tablets_trend"] - s["tablets"]) * P_BASE, 0.0)
    s["saving_A"] = s["price_effect"]
    s["saving_B"] = s["price_effect"] + s["volume_effect"]
    s["cum_saving_A"] = s["saving_A"].cumsum()
    s["cum_saving_B"] = s["saving_B"].cumsum()
    return s, g, Q


def window_totals(s):
    windows = {"Observed: Sep 2025 to Aug 2026": (BREAK, LAST_OBS),
               "FY 2025/26 (Apr 2025 to Mar 2026)": (WINDOW_START, pd.Timestamp("2026-03-01")),
               "FY 2026/27 (Apr 2026 to Mar 2027), part projected": (pd.Timestamp("2026-04-01"), WINDOW_END),
               "£560m window: Apr 2025 to Mar 2027, part projected": (WINDOW_START, WINDOW_END)}
    rows = []
    for name, (a, b) in windows.items():
        x = s.loc[a:b]
        rows.append({"window": name,
                     "months_observed": int(((x["status"] == "observed") & (x.index >= BREAK)).sum()),
                     "months_projected": int((x["status"] == "projected").sum()),
                     "saving_A_m": x["saving_A"].sum() / 1e6, "saving_B_m": x["saving_B"].sum() / 1e6,
                     "price_effect_m": x["price_effect"].sum() / 1e6, "volume_effect_m": x["volume_effect"].sum() / 1e6})
    return pd.DataFrame(rows)


def fig5_cumulative(s):
    x = s.loc[BREAK:]
    obs, proj = x[x.status == "observed"], x[x.status == "projected"]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    for col, color, lw in [("cum_saving_B", GREY, 2), ("cum_saving_A", BLUE, 2.4)]:
        ax.plot(obs.index, obs[col] / 1e6, color=color, lw=lw)
        joined = pd.concat([obs[col].iloc[-1:], proj[col]])
        ax.plot(joined.index, joined / 1e6, color=color, lw=lw, ls=(0, (4, 3)))
    ax.axhline(NHSE_ESTIMATE_M, color=INK_2, lw=1, ls=(0, (2, 2)))
    ax.text(x.index[0], NHSE_ESTIMATE_M + 12, f"NHS England estimate £{NHSE_ESTIMATE_M:.0f}m (Apr 2025 to Mar 2027)",
            color=INK_2, fontsize=9)
    ax.axvspan(LAST_OBS + pd.Timedelta(days=15), x.index[-1] + pd.Timedelta(days=15), color=SHADE, zorder=0)
    ax.text(LAST_OBS + pd.Timedelta(days=25), 25, "Projected", color=INK_2, fontsize=9)
    endA, endB = x["cum_saving_A"].iloc[-1] / 1e6, x["cum_saving_B"].iloc[-1] / 1e6
    obsA, obsB = obs["cum_saving_A"].iloc[-1] / 1e6, obs["cum_saving_B"].iloc[-1] / 1e6
    ax.annotate(f"£{endA:.0f}m  A: actual volume", (x.index[-1], endA), xytext=(6, 0),
                textcoords="offset points", color=BLUE, fontsize=9, va="center")
    ax.annotate(f"£{endB:.0f}m  B: trend volume", (x.index[-1], endB), xytext=(6, 0),
                textcoords="offset points", color=INK_2, fontsize=9, va="center")
    for v, c in [(obsA, INK), (obsB, INK_2)]:
        ax.annotate(f"£{v:.0f}m", (LAST_OBS, v), xytext=(-8, 6), textcoords="offset points", ha="right", fontsize=9, color=c)
    ax.set_ylim(0, max(endA, NHSE_ESTIMATE_M) * 1.15)
    ax.yaxis.set_major_formatter(lambda v, _: f"£{v:.0f}m")
    ax.set_ylabel("Cumulative saving vs £1.307 per tablet")
    month_axis(ax)
    titles(fig, f"Savings reach £{endA:.0f}m on actual volume by Mar 2027, "
                f"{endA / NHSE_ESTIMATE_M * 100:.0f}% of NHS England's £{NHSE_ESTIMATE_M:.0f}m",
           f"Cumulative list-price saving from Sep 2025. Observed to Aug 2026 (A £{obsA:.0f}m, B £{obsB:.0f}m); "
           "dashed = projection.")
    source(fig, "A = flat £1.307 price at actual volume. B = flat £1.307 price at pre-break trend volume. "
                "Projection: Aug 2026 prices held, volume grows at the Mar-Aug 2026 year-on-year rate.")
    save(fig, "fig5_cumulative_savings.png")


def fig6_volume(s, g):
    _, train = fit_trend(s.loc[:LAST_OBS, "tablets"], BREAK - pd.DateOffset(months=1))
    fig, ax = plt.subplots(figsize=(9, 4.4))
    x = s.loc["2023-01-01":]
    obs, proj = x[x.status == "observed"], x[x.status == "projected"]
    ax.axvspan(train[0] - pd.Timedelta(days=15), train[-1] + pd.Timedelta(days=15), color=SHADE, zorder=0)
    ax.text(train[0] + pd.Timedelta(days=10), 0.97, "Trend fitted here", transform=ax.get_xaxis_transform(),
            color=INK_2, fontsize=9, va="top")
    ax.plot(obs.index, obs["tablets"] / 1e6, color=BLUE, lw=2.4)
    joined = pd.concat([obs["tablets"].iloc[-1:], proj["tablets"]])
    ax.plot(joined.index, joined / 1e6, color=BLUE, lw=2.4, ls=(0, (4, 3)))
    tr = x.loc[train[0]:]
    ax.plot(tr.index, tr["tablets_trend"] / 1e6, color=GREY, lw=2)
    for d, lab, yy in [(BREAK, "Price break", 0.06), (NICE_GUIDANCE, "NICE guidance", 0.14)]:
        ax.axvline(d, color=GREY, lw=1, zorder=1)
        ax.text(d, yy, f" {lab}", transform=ax.get_xaxis_transform(), color=INK_2, fontsize=9)
    ax.annotate("Actual", (obs.index[-1], obs["tablets"].iloc[-1] / 1e6), xytext=(-40, 14),
                textcoords="offset points", color=BLUE, fontsize=9)
    ax.annotate("Pre-break trend", (x.index[-1], x["tablets_trend"].iloc[-1] / 1e6), xytext=(6, 0),
                textcoords="offset points", color=INK_2, fontsize=9, va="center")
    gap = s.loc[BREAK:LAST_OBS]
    above = (gap["tablets"].sum() / gap["tablets_trend"].sum() - 1) * 100
    ax.set_ylim(0, None)
    ax.set_ylabel("Tablets per month (millions)")
    month_axis(ax)
    titles(fig, f"Volume ran {above:.0f}% above the pre-break trend in Sep 2025 to Aug 2026",
           f"Monthly tablets, all dapagliflozin. The gap widens after NICE's Feb 2026 guidance. "
           f"Dashed = projected at {g * 100:.0f}% year-on-year growth.")
    source(fig, f"Trend: linear time trend plus month-of-year effects, fitted on {train[0]:%b %Y} to {train[-1]:%b %Y}.")
    save(fig, "fig6_volume_vs_trend.png")
    return above


def fig7_effects(s):
    x = s.loc[BREAK:]
    proj = x.status == "projected"
    fig, ax = plt.subplots(figsize=(9, 4.4))
    for col, colour in [("price_effect", GREEN), ("volume_effect", RED)]:
        ax.bar(x.index, x[col] / 1e6, width=22, color=colour, alpha=0.75)
        ax.bar(x.index[proj], x.loc[proj, col] / 1e6, width=22, color="none", edgecolor="white", hatch="///", lw=0)
    ax.plot(x.index, x["saving_B"] / 1e6, color=INK, lw=1.8, marker="o", ms=4)
    ax.axhline(0, color=GREY, lw=1)
    ax.annotate("Net saving (baseline B)", (x.index[1], x["saving_B"].iloc[1] / 1e6), xytext=(-10, 14),
                textcoords="offset points", fontsize=9, color=INK, ha="center")
    ax.text(x.index[0], x["price_effect"].max() / 1e6 * 1.02, "Green = price effect (saving). "
            "Red = extra volume above trend, at £1.307. Hatched = projected.", fontsize=8.5, color=INK_2, va="bottom")
    ax.yaxis.set_major_formatter(lambda v, _: f"£{v:.0f}m")
    ax.set_ylabel("£ per month")
    ax.set_ylim(x["volume_effect"].min() / 1e6 * 1.25, x["price_effect"].max() / 1e6 * 1.15)
    month_axis(ax, "%b %y")
    pe, ve = x["price_effect"].sum() / 1e6, x["volume_effect"].sum() / 1e6
    titles(fig, f"Volume above trend offsets £{-ve:.0f}m of the £{pe:.0f}m price effect, Sep 2025 to Mar 2027",
           "Monthly saving split into a price effect and a volume effect, both valued at the pre-break price.")
    source(fig)
    save(fig, "fig7_price_vs_volume_effect.png")


def counterfactual(p):
    s, g, Q = savings(p)
    tot = window_totals(s)
    bt = backtest(p["TOTAL_QUANTITY"].sum(axis=1))
    s.round(2).to_csv(DATA / "phase3_monthly_savings.csv", index_label="month")
    tot.round(2).to_csv(DATA / "phase3_window_totals.csv", index=False)
    fig5_cumulative(s)
    above = fig6_volume(s, g)
    fig7_effects(s)
    ratio_A, ratio_B = (tot.iloc[-1][["saving_A_m", "saving_B_m"]] / NHSE_ESTIMATE_M)
    GATES["3. Both baselines within 0.5x to 1.5x of £560m"] = bool(ratio_B >= 0.5 and ratio_A <= 1.5)
    return {"s": s, "tot": tot, "g": g, "Q": Q, "backtest": bt, "above": above}


# %% 4. Plan vs actual ----------------------------------------------------------
# NHS England's £560m (letter of 6 Oct 2025) gives no prices or volumes. We
# (1) reconstruct what was knowable on 6 Oct 2025, (2) back-solve the generic price
# that £560m implies at trend volume, and (3) bridge £560m to our baseline A:
# a price step, then a volume step.

def generic_share_and_price(s, p, Q):
    q = Q.loc[s.index]
    share = q[GENERICS].sum(axis=1) / q.sum(axis=1)
    g_obs = p["NIC"][GENERICS].sum(axis=1) / p["TOTAL_QUANTITY"][GENERICS].sum(axis=1)
    mix = p["TOTAL_QUANTITY"][GENERICS].iloc[-MIX_MONTHS:].sum()
    price_aug = (p["NIC"][GENERICS] / p["TOTAL_QUANTITY"][GENERICS]).iloc[-1]
    price = g_obs.reindex(s.index).fillna((mix * price_aug).sum() / mix.sum())
    return share, price


def generic_saving(q_total, share, price):
    return (q_total * share * (P_BASE - price)).sum() / 1e6


def reconcile(cf, p):
    s = cf["s"].loc[BREAK:WINDOW_END]
    share, price = generic_share_and_price(s, p, cf["Q"])

    known = price.copy()                                  # what was known on 6 Oct 2025
    known[known.index >= OCT25] = price[OCT25]
    r_known_trend = generic_saving(s["tablets_trend"], share, known)
    r_known_actual = generic_saving(s["tablets"], share, known)

    sep = s["tablets_trend"].iloc[0] * share.iloc[0] * (P_BASE - price.iloc[0])
    implied = P_BASE - (NHSE_ESTIMATE_M * 1e6 - sep) / (s["tablets_trend"].iloc[1:] * share.iloc[1:]).sum()
    w = s["tablets"].iloc[1:] * share.iloc[1:]
    avg_actual = (price.iloc[1:] * w).sum() / w.sum()

    r_trend = generic_saving(s["tablets_trend"], share, price)
    r_A = generic_saving(s["tablets"], share, price)
    assert abs(r_A - s["saving_A"].sum() / 1e6) < 0.5, "bridge does not tie to baseline A"
    obs_A = s.loc[:LAST_OBS, "saving_A"].sum() / 1e6
    bridge = pd.DataFrame([("NHS England estimate (Oct 2025)", NHSE_ESTIMATE_M, "total"),
                           ("Prices fell further than assumed", r_trend - NHSE_ESTIMATE_M, "step"),
                           ("Volume above pre-break trend", r_A - r_trend, "step"),
                           ("This analysis, baseline A", r_A, "total")], columns=["item", "value_m", "kind"])
    bridge.round(2).to_csv(DATA / "phase4_bridge.csv", index=False)
    fig8_bridge(bridge, obs_A, r_A - obs_A)
    GATES["4. Gap to £560m explained by price and volume steps"] = bool(abs(bridge.value_m.iloc[1:3].sum() + NHSE_ESTIMATE_M - r_A) < 0.01)
    return {"known_trend": r_known_trend, "known_actual": r_known_actual, "trend_actual_price": r_trend,
            "A": r_A, "implied": implied, "avg_actual": avg_actual, "bridge": bridge, "obs_A": obs_A}


def fig8_bridge(bridge, obs_A, proj_A):
    fig, ax = plt.subplots(figsize=(9, 4.6))
    running = 0.0
    for i, r in bridge.iterrows():
        if r.kind == "total":
            ax.bar(i, r.value_m, color=GREY, width=0.6)
            running = r.value_m
            ax.text(i, r.value_m + 12, f"£{r.value_m:.0f}m", ha="center", fontsize=10, color=INK, fontweight="bold")
        else:
            bottom = running if r.value_m >= 0 else running + r.value_m
            ax.bar(i, abs(r.value_m), bottom=bottom, color=GREEN if r.value_m >= 0 else RED, alpha=0.75, width=0.6)
            ax.text(i, bottom + abs(r.value_m) + 12, f"{'+' if r.value_m >= 0 else '−'}£{abs(r.value_m):.0f}m",
                    ha="center", fontsize=10, color=INK)
            ax.plot([i - 0.7, i - 0.3], [running, running], color=GREY, lw=0.8)
            running += r.value_m
    last = len(bridge) - 1
    ax.plot([last - 0.7, last - 0.3], [running, running], color=GREY, lw=0.8)
    ax.bar(last, obs_A, color="#5c5b57", width=0.6)
    ax.text(last, obs_A / 2, f"Observed\n£{obs_A:.0f}m", ha="center", va="center", fontsize=8.5, color="white")
    ax.text(last, obs_A + proj_A / 2, f"Projected\n£{proj_A:.0f}m", ha="center", va="center", fontsize=8.5, color=INK)
    ax.set_xticks(range(len(bridge)))
    ax.set_xticklabels(["NHS England\nestimate (Oct 2025)", "Prices fell further\nthan assumed",
                        "Volume above\npre-break trend", "This analysis,\nbaseline A"], fontsize=9)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    ax.set_ylim(0, bridge["value_m"].max() * 1.15)
    ax.yaxis.set_major_formatter(lambda v, _: f"£{v:.0f}m")
    ax.set_ylabel("Saving, Apr 2025 to Mar 2027")
    titles(fig, f"Lower prices and higher volume each add about £{bridge.value_m.iloc[1:3].mean():.0f}m "
                f"to the £{NHSE_ESTIMATE_M:.0f}m estimate",
           "Bridge from NHS England's Oct 2025 estimate to this analysis (list-price basis). Green = adds to the saving.")
    source(fig, "The price step also absorbs any unpublished difference in NHS England's volume or scope.",
           y=-0.08, base="Source: NHS England letter, 6 Oct 2025; NHSBSA English Prescribing Dataset with SNOMED code.")
    save(fig, "fig8_bridge_560_to_ours.png")


# %% 5. Sensitivity -------------------------------------------------------------
# Rerun the savings under alternative assumptions, test when volume growth changed
# (interrupted time series), and check whether extra dapagliflozin volume came from
# other SGLT2 inhibitors.

CASES = [
    ("Base (Phase 3)", {}),
    ("Projected growth 30%", {"growth": 0.30}),
    ("Projected growth 20%", {"growth": 0.20}),
    ("Projected growth 0%", {"growth": 0.0}),
    ("Oct 2026 concession price", {"oct26_price": True}),
    ("Actual cost, not list price", {"actual_cost": True}),
    ("Trend fitted on 18 months", {"trend_months": 18}),
    ("Trend fitted on 36 months", {"trend_months": 36}),
    ("Pessimistic: all four together", {"growth": 0.20, "oct26_price": True, "actual_cost": True, "trend_months": 36}),
]


def run_case(p, growth=None, oct26_price=False, actual_cost=False, trend_months=TREND_MONTHS):
    q_obs = p["TOTAL_QUANTITY"]
    q_proj, nic_proj, g = project(p, growth, oct26_price)
    Q = pd.concat([q_obs, q_proj])
    if actual_cost:
        # counterfactual: £1.307 x each presentation's Aug 2025 actual-cost ratio;
        # projected months: projected NIC x the observed post-break actual-cost ratio
        r_pre = (p["ACTUAL_COST"] / p["NIC"]).loc[BREAK - pd.DateOffset(months=1)]
        obs = p.loc[BREAK:LAST_OBS]
        spend = pd.concat([p["ACTUAL_COST"], nic_proj * (obs["ACTUAL_COST"].sum() / obs["NIC"].sum())])
        cf_unit = P_BASE * r_pre
        mix_pre = q_obs.loc[BREAK - pd.DateOffset(months=1)]
        cf_unit_total = (cf_unit * mix_pre / mix_pre.sum()).sum()
    else:
        spend = pd.concat([p["NIC"], nic_proj])
        cf_unit = pd.Series(P_BASE, index=Q.columns)
        cf_unit_total = P_BASE
    s = pd.DataFrame(index=Q.index)
    s["spend"] = spend.sum(axis=1)
    trend = trend_line(q_obs.sum(axis=1), trend_months, index=s.index)
    post = s.index >= BREAK
    s["A"] = np.where(post, (Q * cf_unit).sum(axis=1) - s["spend"], 0.0)
    s["B"] = np.where(post, trend * cf_unit_total - s["spend"], 0.0)
    obs_w, win = s.loc[BREAK:LAST_OBS], s.loc[WINDOW_START:WINDOW_END]
    return {"growth": g, "obs_A": obs_w["A"].sum() / 1e6, "obs_B": obs_w["B"].sum() / 1e6,
            "nice_A": win["A"].sum() / 1e6, "nice_B": win["B"].sum() / 1e6}


def interrupted_time_series(p):
    """Monthly tablets on a trend, level and slope changes at Sep 2025 and Feb 2026, month effects."""
    import statsmodels.api as sm
    q = p["TOTAL_QUANTITY"].sum(axis=1).loc["2023-09-01":LAST_OBS] / 1e6
    t = np.arange(len(q), dtype=float)
    t1, t2 = list(q.index).index(BREAK), list(q.index).index(NICE_GUIDANCE)
    X = pd.DataFrame({"trend": t, "break_level": (t >= t1) * 1.0, "break_slope": np.clip(t - t1, 0, None),
                      "nice_level": (t >= t2) * 1.0, "nice_slope": np.clip(t - t2, 0, None)}, index=q.index)
    for m in range(2, 13):
        X[f"m{m}"] = (q.index.month == m) * 1.0
    res = sm.OLS(q.values, sm.add_constant(X)).fit(cov_type="HAC", cov_kwds={"maxlags": 3})
    g10 = (p["NIC"]["Generic 10mg"] / p["TOTAL_QUANTITY"]["Generic 10mg"]).loc[BREAK:LAST_OBS]
    price = sm.OLS(np.log(g10.values), sm.add_constant(np.arange(len(g10), dtype=float))).fit(
        cov_type="HAC", cov_kwds={"maxlags": 3})
    return res, price, len(q)


def switching(cls):
    """Compare each series with its own pre-break trend: dapagliflozin, other SGLT2s, whole class."""
    cls = cls.assign(month=pd.to_datetime(cls["month"] + "-01"))
    q = cls.pivot(index="month", columns="chemical", values="TOTAL_QUANTITY")
    nic = cls.pivot(index="month", columns="chemical", values="NIC")
    q["Other SGLT2"] = q.drop(columns="Dapagliflozin").sum(axis=1)
    q["Class"] = q["Dapagliflozin"] + q["Other SGLT2"]
    gaps = pd.DataFrame({c: q[c] - trend_line(q[c]) for c in ["Dapagliflozin", "Other SGLT2", "Class"]}).loc[BREAK:LAST_OBS]
    aug25 = BREAK - pd.DateOffset(months=1)
    pre_price = nic.loc[aug25].sum() / q.loc[aug25, ["Dapagliflozin", "Other SGLT2"]].sum()
    class_B = (trend_line(q["Class"]).loc[BREAK:LAST_OBS] * pre_price
               - nic.loc[BREAK:LAST_OBS].sum(axis=1)).sum() / 1e6
    share = q["Dapagliflozin"] / q["Class"] * 100
    fig10_switching(gaps)
    return {"gaps": gaps, "class_B": class_B, "share_aug25": share[aug25], "share_last": share[LAST_OBS],
            "empa_aug25": q.loc[aug25, "Empagliflozin"], "empa_last": q.loc[LAST_OBS, "Empagliflozin"]}


def fig9_range(tab):
    fig, ax = plt.subplots(figsize=(9, 5))
    y = np.arange(len(tab))[::-1]
    for yi, (_, r) in zip(y, tab.iterrows()):
        ax.plot([r.nice_B, r.nice_A], [yi, yi], color=GREY_LIGHT, lw=3, solid_capstyle="round", zorder=1)
        ax.scatter(r.nice_B, yi, s=46, color=GREY, zorder=2, edgecolor="white", linewidth=1.5)
        ax.scatter(r.nice_A, yi, s=46, color=BLUE, zorder=3, edgecolor="white", linewidth=1.5)
        hi, lo = max(r.nice_A, r.nice_B), min(r.nice_A, r.nice_B)
        a_high = r.nice_A >= r.nice_B
        ax.text(hi + 8, yi, f"£{hi:.0f}m", va="center", fontsize=8.5, color=INK if a_high else INK_2)
        ax.text(lo - 8, yi, f"£{lo:.0f}m", va="center", ha="right", fontsize=8.5, color=INK_2 if a_high else INK)
    ax.axvline(NHSE_ESTIMATE_M, color=INK_2, lw=1, ls=(0, (2, 2)))
    ax.text(NHSE_ESTIMATE_M, len(tab) - 0.35, f" NHS England £{NHSE_ESTIMATE_M:.0f}m", fontsize=9, color=INK_2, va="bottom")
    ax.set_yticks(y)
    ax.set_yticklabels(tab["case"], fontsize=9)
    ax.tick_params(length=0)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID)
    ax.set_xlim(min(tab.nice_B.min(), NHSE_ESTIMATE_M) - 40, tab.nice_A.max() + 45)
    ax.set_ylim(-0.7, len(tab) - 0.1)
    ax.xaxis.set_major_formatter(lambda v, _: f"£{v:.0f}m")
    ax.set_xlabel("Saving, Apr 2025 to Mar 2027 (Sep 2026 onward projected)")
    vals = tab[["nice_A", "nice_B"]]
    titles(fig, f"The saving stays between £{vals.min().min():.0f}m and £{vals.max().max():.0f}m across every case tested",
           f"Blue = baseline A (actual volume), grey = baseline B (trend volume). "
           f"{int((vals < NHSE_ESTIMATE_M).sum().sum())} of {vals.size} results fall below £{NHSE_ESTIMATE_M:.0f}m.")
    source(fig, "NHS England letter, 6 Oct 2025. Oct 2026 concession price from Community Pharmacy England.", y=-0.06)
    save(fig, "fig9_sensitivity_range.png")


def fig10_switching(g):
    fig, ax = plt.subplots(figsize=(9, 4.4))
    off = pd.Timedelta(days=5)
    h1 = ax.bar(g.index - off, g["Dapagliflozin"] / 1e6, width=9, color=BLUE)
    h2 = ax.bar(g.index + off, g["Other SGLT2"] / 1e6, width=9, color=GREY)
    h3, = ax.plot(g.index, g["Class"] / 1e6, color=INK, lw=1.8, marker="o", ms=4)
    ax.axhline(0, color=GREY, lw=1)
    ax.axvline(NICE_GUIDANCE - pd.Timedelta(days=15), color=GREY_LIGHT, lw=1, ls="--")
    ax.text(NICE_GUIDANCE - pd.Timedelta(days=12), 0.97, " NICE guidance", transform=ax.get_xaxis_transform(),
            color=INK_2, fontsize=9, va="top")
    ax.legend([h1, h2, h3], ["Dapagliflozin", "Other SGLT2 inhibitors", "Whole class (net)"], loc="lower left",
              frameon=False, fontsize=9)
    ax.set_axisbelow(True)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:+.0f}m" if v else "0")
    ax.set_ylabel("Tablets vs pre-break trend, per month")
    month_axis(ax, "%b %y")
    d, o, c = (g[k].sum() / 1e6 for k in ["Dapagliflozin", "Other SGLT2", "Class"])
    titles(fig, f"Dapagliflozin's extra {d:.0f}m tablets were matched by a fall in other SGLT2 inhibitors",
       f"Monthly tablets above or below each series' pre-break trend, Sep 2025 to Aug 2026: "
       f"dapagliflozin {d:+.1f}m, others {o:+.1f}m, class {c:+.1f}m.")
    source(fig, "Trend: linear time trend plus month-of-year effects, fitted Sep 2023 to Aug 2025, per series.",
           base=SOURCE.replace("BNF 0601023AG", "BNF 0601023AG, AN, AM, AX (single-agent SGLT2 inhibitors)"))
    save(fig, "fig10_sglt2_switching.png")


def sensitivity(p, cls, cf):
    tab = pd.DataFrame([{"case": name, **run_case(p, **kw)} for name, kw in CASES])
    base_ref = cf["tot"].iloc[-1]
    assert abs(tab.nice_A[0] - base_ref.saving_A_m) < 0.1 and abs(tab.nice_B[0] - base_ref.saving_B_m) < 0.1, \
        "base case does not reproduce the counterfactual"
    tab.round(2).to_csv(DATA / "phase5_sensitivity.csv", index=False)
    fig9_range(tab)
    its, price, n = interrupted_time_series(p)
    sw = switching(cls)
    return {"tab": tab, "its": its, "price": price, "n": n, "sw": sw}


# %% 6. Run everything ----------------------------------------------------------

def write_results(pull, desc, cf, rec, sens):
    f = lambda v: f"−£{-v:,.0f}m" if v < 0 else f"£{v:,.0f}m"
    tot, tab, sw, its = cf["tot"], sens["tab"], sens["sw"], sens["its"]
    L = ["# Results", "", "Generated by `dapa_analysis.py`. List-price (NIC) basis unless stated.", "",
         "## Checks", ""] + [f"- {'PASS' if ok else 'FAIL'}: {name}" for name, ok in GATES.items()] + [
        "", "## 1. Data", "",
        f"- {pull['df']['YEAR_MONTH'].nunique()} months ({FIRST_MONTH} to {LAST_MONTH}), {len(pull['df'])} rows "
        f"(month x presentation x SNOMED code). Missing months: {pull['missing'] or 'none'}.",
        "", "## 2. Descriptives", "",
        f"- Generic 10mg list price per tablet: £{desc['g10'].iloc[0]:.3f} until Aug 2025, £{desc['g10'][BREAK]:.3f} "
        f"in Sep 2025, £{desc['g10'][OCT25]:.3f} in Oct 2025, £{desc['g10'].iloc[-1]:.3f} in {LAST_OBS:%b %Y}.",
        f"- Sep 2025 to Aug 2026 vs the 12 months before: tablets {desc['vol_g']:+.1f}%, NIC spend {desc['sp_g']:+.1f}%.",
        f"- Forxiga share of items: {desc['share'][0]:.2f}% low before the break, {desc['share'][1]:.2f}% peak after, "
        f"{desc['share'][2]:.2f}% in {LAST_OBS:%b %Y}.",
        f"- Generic 10mg price concession months: {', '.join(desc['concessions'])}.",
        "", "## 3. Counterfactual savings", "",
        "| Window | Observed months | Projected months | A: actual volume | B: trend volume | Volume effect |",
        "| --- | --- | --- | --- | --- | --- |"]
    L += [f"| {r.window} | {r.months_observed} | {r.months_projected} | {f(r.saving_A_m)} | {f(r.saving_B_m)} | "
          f"{f(r.volume_effect_m)} |" for _, r in tot.iterrows()]
    L += ["", f"- Volume ran {cf['above']:.1f}% above the pre-break trend, Sep 2025 to Aug 2026.",
          "- Trend backtest, 12 months ahead: " + ", ".join(f"{a} {b:+.1f}%" for a, b in cf["backtest"]) + ".",
          f"- Projection growth: {cf['g'] * 100:.1f}% a year (Mar to Aug 2026 vs a year earlier).",
          "", "## 4. Plan vs actual (£560m, NHS England, 6 Oct 2025)", "",
          "| Assumption set, Apr 2025 to Mar 2027 | Saving | vs £560m |", "| --- | --- | --- |"]
    for name, key in [("Oct 2025 prices, trend volume", "known_trend"), ("Oct 2025 prices, actual volume", "known_actual"),
                      ("Actual prices, trend volume", "trend_actual_price"), ("Actual prices, actual volume (A)", "A")]:
        L.append(f"| {name} | {f(rec[key])} | {rec[key] / NHSE_ESTIMATE_M * 100:.0f}% |")
    b = rec["bridge"].value_m
    L += ["", f"- £560m implies a generic price of £{rec['implied']:.3f} a tablet from Oct 2025 at trend volume; "
              f"the actual average was £{rec['avg_actual']:.3f}.",
          f"- Bridge: £560m {b[1]:+.0f}m (prices) {b[2]:+.0f}m (volume) = {f(b[3])} "
          f"(observed {f(rec['obs_A'])}, projected {f(b[3] - rec['obs_A'])}).",
          "", "## 5. Sensitivity", "",
          "| Case | Observed A | Observed B | Window A | Window B |", "| --- | --- | --- | --- | --- |"]
    L += [f"| {r.case} | {f(r.obs_A)} | {f(r.obs_B)} | {f(r.nice_A)} | {f(r.nice_B)} |" for _, r in tab.iterrows()]
    co, pv = its.params, its.pvalues
    L += ["", "Interrupted time series, monthly tablets (millions), Sep 2023 to Aug 2026, Newey-West SEs:", ""]
    for k, lab in [("trend", "Pre-break slope per month"), ("break_level", "Level change, Sep 2025"),
                   ("break_slope", "Slope change from Sep 2025"), ("nice_level", "Level change, Feb 2026"),
                   ("nice_slope", "Slope change from Feb 2026")]:
        L.append(f"- {lab}: {co[k]:+.2f} (p = {pv[k]:.3f})")
    g = sw["gaps"]
    L += ["", "Switching within the SGLT2 class, tablets vs each series' own trend, Sep 2025 to Aug 2026:", "",
          f"- Dapagliflozin {g['Dapagliflozin'].sum() / 1e6:+.1f}m, other SGLT2 inhibitors {g['Other SGLT2'].sum() / 1e6:+.1f}m, "
          f"class {g['Class'].sum() / 1e6:+.1f}m.",
          f"- Dapagliflozin share of class tablets {sw['share_aug25']:.1f}% (Aug 2025) to {sw['share_last']:.1f}% "
          f"({LAST_OBS:%b %Y}); empagliflozin {sw['empa_aug25'] / 1e6:.1f}m to {sw['empa_last'] / 1e6:.1f}m tablets a month.",
          f"- Class-level saving, observed year: {f(sw['class_B'])} (dapagliflozin baseline A {f(tab.obs_A[0])}).", ""]
    (DATA / "results.md").write_text("\n".join(L))


def main():
    print("1. Pulling data from the NHSBSA API (cached after the first run) ...")
    tables = table_names()
    df, missing = pull_dapa(tables)
    df.to_csv(DATA / "dapa_monthly_by_presentation.csv", index=False)
    check_pull(df, missing).to_csv(DATA / "code_map.csv", index=False)
    cls = pull_class(tables)
    cls.to_csv(DATA / "sglt2_class_monthly.csv", index=False)
    p = presentations(df)

    print("2. Descriptives ...")
    desc = descriptives(df, p)
    print("3. Counterfactual ...")
    cf = counterfactual(p)
    print("4. Plan vs actual ...")
    rec = reconcile(cf, p)
    print("5. Sensitivity ...")
    sens = sensitivity(p, cls, cf)

    write_results({"df": df, "missing": missing}, desc, cf, rec, sens)
    print("\nChecks:")
    for name, ok in GATES.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\nFirst-year saving (A): £{cf['tot'].saving_A_m[0]:.0f}m. "
          f"£560m window: £{cf['tot'].saving_A_m.iloc[-1]:.0f}m (A), £{cf['tot'].saving_B_m.iloc[-1]:.0f}m (B).")
    print("Full results in data/results.md, figures in figs/.")
    return 0 if all(GATES.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
