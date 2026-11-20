"""Pull all BNF 0601023 (SGLT2 + others in para) by month x presentation, Sep 2022-Aug 2026."""
import json, sys, time, re
from pathlib import Path
import requests
API="https://opendata.nhsbsa.net/api/3/action"
RAW=Path(__file__).parent/"raw"
SCH={"new":dict(chem="BNF_CHEMICAL_SUBSTANCE_CODE",code="BNF_PRESENTATION_CODE",name="BNF_PRESENTATION_NAME"),
     "old":dict(chem="BNF_CHEMICAL_SUBSTANCE",code="BNF_CODE",name="BNF_DESCRIPTION")}
def sql(t,s):
    c=SCH[s]; n=lambda x:f"SUM(SAFE_CAST({x} AS NUMERIC)) AS {x}"
    return (f"SELECT SAFE_CAST(YEAR_MONTH AS STRING) AS YEAR_MONTH, {c['chem']} AS CHEM, {c['code']} AS CODE, {c['name']} AS NAME, "
            f"{n('ITEMS')}, {n('TOTAL_QUANTITY')}, {n('NIC')}, {n('ACTUAL_COST')} FROM `{t}` "
            f"WHERE STARTS_WITH({c['code']}, '0601023') GROUP BY 1,2,3,4")
def months(a,b):
    y,m=map(int,a.split("-")); out=[]
    while (y,m)<=tuple(map(int,b.split("-"))):
        out.append(f"{y}{m:02d}"); y,m=(y+1,1) if m==12 else (y,m+1)
    return out
for ym in months(sys.argv[1],sys.argv[2]):
    f=RAW/f"{ym}.json"
    if f.exists(): continue
    t=f"EPD_SNOMED_{ym}"; first="old" if ym<"202503" else "new"
    for s in (first,"new" if first=="old" else "old"):
        for k in range(4):
            try:
                r=requests.get(f"{API}/datastore_search_sql",params={"resource_id":t,"sql":sql(t,s)},timeout=600)
                js=r.json()
                break
            except Exception as e:
                print(ym,"retry",e); time.sleep(10*(k+1))
        if js.get("success"): break
        if "Unrecognized name" not in json.dumps(js.get("error")): print(ym, js.get("error")); break
    if js.get("success"):
        rec=js["result"]["result"]["records"] if "result" in js["result"] else js["result"]["records"]
        f.write_text(json.dumps(rec)); print(ym,len(rec),flush=True)
