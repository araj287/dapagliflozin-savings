import warnings; warnings.filterwarnings("ignore")
exec(open("baseline_c.py").read().split("def calc")[0])
d="dapagliflozin"; oth=[x for x in mono if x!=d]
cls_tr=trend[mono].sum(axis=1)
obs=[x for x in months if "2025-09"<=x<="2026-08"]
C_obs=((trend.loc[obs,mono]*P0[mono]).sum(axis=1)-N.loc[obs,mono].sum(axis=1)).sum()/1e6
share_aug=Q.loc["2026-08",d]/Q.loc["2026-08",mono].sum()
# share trend Mar-Aug 2026 (linear), capped at 95%
sh=Q.loc[ma,d]/Q.loc[ma,mono].sum(axis=1); slope=np.polyfit(range(6),sh.values,1)[0]
pd_=p_aug26[d]
def window(shares, label):
    Cp=0; Ap=0
    for i,x in enumerate(proj):
        s=shares(i); qd=s*cls_tr[x]; qo=(1-s)*cls_tr[x]
        cf=(trend.loc[x,mono]*P0[mono]).sum(); act=qd*pd_+qo*P0["empagliflozin"]
        Cp+=cf-act; Ap+=qd*(P0[d]-pd_)
    print(f"{label:45s} proj-months C £{Cp/1e6:6.1f}m | NICE window C £{(C_obs*1e6+Cp)/1e6+0:6.1f}m (A-style £{(385.4e6+Ap)/1e6:.1f}m)")
print(f"Aug 2026 dapa share of SGLT2 mono tablets: {share_aug:.1%}; Mar-Aug 2026 share slope {slope*100:+.2f}pp/month")
print(f"C observed Sep25-Aug26: £{C_obs:.1f}m")
window(lambda i: share_aug, "Class at trend, share held at Aug 2026")
window(lambda i: min(0.95, share_aug+slope*(i+1)), "Class at trend, share keeps rising (cap 95%)")
# original rule, for reference
Cp=sum(((trend.loc[x,mono]*P0[mono]).sum()-Np.loc[x,mono].sum()) for x in proj)
print(f"{'Original x1.404 rule (as in results table)':45s} proj-months C £{Cp/1e6:6.1f}m | NICE window C £{C_obs+Cp/1e6:6.1f}m")
print("Projected class vs trend under original rule (m tablets/month):",((Qp.loc[proj,mono].sum(axis=1)-cls_tr[proj])/1e6).round(1).tolist())
