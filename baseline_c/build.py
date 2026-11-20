import json, glob, pandas as pd, numpy as np, statsmodels.api as sm
rows=[]
for f in sorted(glob.glob("raw/*.json")):
    ym=f[-11:-5]; ym=f"{ym[:4]}-{ym[4:]}"
    for r in json.load(open(f)):
        rows.append(dict(month=ym,chem=r["CHEM"],code=r["CODE"],name=r["NAME"],
            q=float(r["TOTAL_QUANTITY"] or 0),nic=float(r["NIC"] or 0),ac=float(r["ACTUAL_COST"] or 0)))
df=pd.DataFrame(rows)
MONO={"0601023AG":"dapagliflozin","0601023AN":"empagliflozin","0601023AM":"canagliflozin","0601023AX":"ertugliflozin"}
COMBO={"0601023AL":"dapa/metformin","0601023AR":"empa/metformin","0601023AP":"cana/metformin","0601023AV":"saxa/dapa","0601023AY":"empa/lina"}
df=df[df.chem.isin({**MONO,**COMBO})].copy()
df["drug"]=df.chem.map({**MONO,**COMBO}); df["mono"]=df.chem.isin(MONO)
df.to_csv("sglt2_class_monthly_by_presentation.csv",index=False)
m=df.groupby(["month","drug","mono"])[["q","nic","ac"]].sum().reset_index()
m.to_csv("sglt2_class_monthly_by_drug.csv",index=False)
print(m.pivot(index="month",columns="drug",values="q").div(1e6).round(2).loc["2025-06":].to_string())
print((m.assign(p=m.nic/m.q).pivot(index="month",columns="drug",values="p")).round(3).loc[["2023-09","2024-09","2025-03","2025-08","2025-10","2026-02","2026-08"]].to_string())
