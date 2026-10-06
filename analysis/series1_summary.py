"""
סדרה 1 — אמון במשטרה (הסקר החברתי, הלמ"ס): פער חרדים מול כלל בני 20+, ומתאם עם מדד "תפקוד המשטרה".
קורא מ-data/ וכותב ל-output/tables/. ללא חישובים ידניים.

    python analysis/series1_summary.py
"""
import os

import pandas as pd

trust = pd.read_csv("data/cbs_trust_police.csv")
func = pd.read_csv("data/cbs_police_functioning_haredim.csv")

t = trust[trust["comparable"] == 1].copy()  # 2014 לא בר-השוואה (סולם כן/לא)
t["gap_haredim_vs_all"] = (t["haredim_pct"] - t["all_20plus_pct"]).round(1)

m = t.merge(func, on="year").dropna(subset=["haredim_pct", "haredim_good_or_very_good_pct"])
r = m["haredim_pct"].corr(m["haredim_good_or_very_good_pct"])

os.makedirs("output/tables", exist_ok=True)
t[["year", "haredim_pct", "all_20plus_pct", "gap_haredim_vs_all", "source"]].to_csv(
    "output/tables/series1_trust_gap.csv", index=False)
pd.DataFrame([{"years": ",".join(map(str, m["year"])), "n_years": len(m), "pearson_r": round(r, 3)}]).to_csv(
    "output/tables/series1_trust_vs_functioning_r.csv", index=False)

print(t[["year", "haredim_pct", "all_20plus_pct", "gap_haredim_vs_all"]].to_string(index=False))
print(f"\nr(trust, functioning) = {r:.3f}  (n={len(m)} years: {list(m['year'])})")
