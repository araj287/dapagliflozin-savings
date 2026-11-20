import pandas as pd, numpy as np, statsmodels.api as sm
m=pd.read_csv("sglt2_class_monthly_by_drug.csv")
Q=m.pivot(index="month",columns="drug",values="q").fillna(0)
N=m.pivot(index="month",columns="drug",values="nic").fillna(0)
A_C=m.pivot(index="month",columns="drug",values="ac").fillna(0)
months=pd.period_range("2022-09","2027-03",freq="M").astype(str)
def X(idx):
    p=pd.PeriodIndex(idx,freq="M"); t=np.array([(x.year-2023)*12+x.month for x in p],float)
    D=pd.get_dummies(pd.Series([x.month for x in p]),prefix="m",dtype=float).reindex(columns=[f"m_{i}" for i in range(1,13)],fill_value=0)
    D.index=idx; D.insert(0,"t",t); return D
fit=[x for x in Q.index if "2023-09"<=x<="2025-08"]
trend=pd.DataFrame(index=months)
for d in Q.columns:
    mod=sm.OLS(Q.loc[fit,d].values,X(fit).values).fit()
    trend[d]=X(list(months)).values@mod.params
P0=(N.loc["2025-08"]/Q.loc["2025-08"])          # pre-entry NIC per tablet by drug
mono=["dapagliflozin","empagliflozin","canagliflozin","ertugliflozin"]
allc=list(Q.columns)

# projection Sep26-Mar27 (same rule as phase 3: same month last yr x YoY growth Mar-Aug 2026; Aug 2026 prices)
proj=[x for x in months if x>="2026-09"]
ma=[f"2026-0{i}" for i in range(3,9)]; mb=[f"2025-0{i}" for i in range(3,9)]
g=Q.loc[ma].sum()/Q.loc[mb].sum()
Qp=Q.reindex(months).copy(); Np=N.reindex(months).copy(); ACp=A_C.reindex(months).copy()
p_aug26=N.loc["2026-08"]/Q.loc["2026-08"]; ac_aug26=A_C.loc["2026-08"]/Q.loc["2026-08"]
for x in proj:
    ly=str(pd.Period(x)-12); Qp.loc[x]=Q.loc[ly]*g; Np.loc[x]=Qp.loc[x]*p_aug26; ACp.loc[x]=Qp.loc[x]*ac_aug26
print("YoY growth Mar-Aug 2026:",g[mono].round(3).to_dict())

def calc(drugs, start, end):
    w=[x for x in months if start<=x<=end and x>="2025-09"]   # zero saving before price break by construction
    q,n,t=Qp.loc[w,drugs],Np.loc[w,drugs],trend.loc[w,drugs]
    d="dapagliflozin"
    A=(q[d]*P0[d]-n[d]).sum()
    B=(t[d]*P0[d]-n[d]).sum()
    C=((t*P0[drugs]).sum(axis=1)-n.sum(axis=1)).sum()
    C_classvol=(q.sum(axis=1)-t.sum(axis=1)).sum()
    dapa_ex=(q[d]-t[d]).sum(); oth=(q.drop(columns=d).sum(axis=1)-t.drop(columns=d).sum(axis=1)).sum()
    return dict(A=A/1e6,B=B/1e6,C=C/1e6,dapa_vs_trend_m=dapa_ex/1e6,others_vs_trend_m=oth/1e6,class_vs_trend_m=C_classvol/1e6)
out=[]
for lab,(s,e) in {"Observed Sep25-Aug26":("2025-09","2026-08"),"FY25/26":("2025-04","2026-03"),
                  "FY26/27 (7m projected)":("2026-04","2027-03"),"NICE window Apr25-Mar27":("2025-04","2027-03")}.items():
    for cl,dr in {"mono":mono,"incl combos":allc}.items():
        r=calc(dr,s,e); r.update(window=lab,classdef=cl); out.append(r)
res=pd.DataFrame(out).set_index(["window","classdef"]).round(1)
print(res.to_string())
res.to_csv("baseline_c_results.csv")
# monthly table (mono)
d="dapagliflozin"; mt=pd.DataFrame({"status":["projected" if x>="2026-09" else "observed" for x in months]},index=months)
mt["dapa_m"]=Qp[d]/1e6; mt["dapa_trend_m"]=trend[d]/1e6
mt["others_m"]=Qp[mono].drop(columns=d).sum(axis=1)/1e6; mt["others_trend_m"]=trend[mono].drop(columns=d).sum(axis=1)/1e6
mt["A"]=(Qp[d]*P0[d]-Np[d])/1e6; mt["B"]=(trend[d]*P0[d]-Np[d])/1e6
mt["C"]=((trend[mono]*P0[mono]).sum(axis=1)-Np[mono].sum(axis=1))/1e6
mt.loc[mt.index<"2025-09",["A","B","C"]]=0
mt=mt.loc["2025-09":].round(2); mt.to_csv("baseline_c_monthly.csv"); print(mt.to_string())
# backtest of class trend: fit Sep22-Aug24 window? (only have from Sep22) -> fit Sep22-Aug24, predict Sep24-Aug25
f2=[x for x in Q.index if "2022-09"<=x<="2024-08"]; p2=[x for x in Q.index if "2024-09"<=x<="2025-08"]
for d in mono:
    mod=sm.OLS(Q.loc[f2,d].values,X(f2).values).fit(); pr=X(p2).values@mod.params
    print("backtest",d, f"{(Q.loc[p2,d].sum()-pr.sum())/pr.sum()*100:+.1f}%")
cls=Q[mono].sum(axis=1); mod=sm.OLS(cls.loc[f2].values,X(f2).values).fit(); pr=X(p2).values@mod.params
print("backtest class", f"{(cls.loc[p2].sum()-pr.sum())/pr.sum()*100:+.1f}%")
