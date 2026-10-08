"""
H2 — רגרסיה לוגיסטית משוקללת: האם נפגעים חרדים מדווחים למשטרה פחות מיהודים לא-חרדים,
בשליטה על סוג עבירה, מגדר, גיל ותקופה (סקר ביטחון אישי, PUF, 2015–2025).

יחידת ניתוח: נפגע × עבירה (הפגיעה האחרונה), יהודים שענו על שאלת הדיווח.
משקל: GN_Prat, מנורמל לממוצע 1. שגיאות תקן: sandwich מקובץ לפי משיב (נפגע של כמה עבירות
מופיע כמה פעמים). אין משתני תכנון מדגם (שכבות) ב-PUF — שגיאות התקן הן קירוב; נבדקו מול
bootstrap מקובץ לפי משיב בתוך שנה (300 חזרות, 8.10.2026): M1 haredi 0.126 מול 0.124; M2 0.186 מול 0.178.

מודלים:
    M0  reported ~ haredi
    M1  reported ~ haredi + crime_type + female + age + period
    M1x כמו M1, בלי עבירה מקוונת
    M2  M1 + haredi × period (האם פער הדיווח השתנה בין התקופות)

פלט: output/tables/pss_reporting_logit.csv (יחסי סיכויים, רווח סמך 95%, p).

שימוש:
    python analysis/pss_puf_regression.py [--puf data/puf] [--var-map analysis/var_map.csv] [--out output/tables]
"""
import argparse
import glob
import os
import sys
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pss_puf_reporting import PERIODS, year_records  # noqa: E402

MAIN_PERIODS = {y: p for p in ("2015-2019", "2020-2022", "2023-2025") for y in PERIODS[p]}
AGE = {1: "20-29", 2: "30-39", 3: "40-49", 4: "50-59", 5: "60+", 6: "60+", 7: "60+"}


def load(puf, var_map):
    frames = []
    for year, vm in var_map.groupby("year"):
        df = pd.read_csv(glob.glob(os.path.join(puf, str(year), "*data.csv"))[0], low_memory=False, encoding="utf-8-sig")
        frames.append(year_records(df, vm).assign(year=year))
    return pd.concat(frames, ignore_index=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--puf", default="data/puf")
    ap.add_argument("--var-map", default="analysis/var_map.csv")
    ap.add_argument("--out", default="output/tables")
    a = ap.parse_args()
    var_map = pd.read_csv(a.var_map, dtype={"code": str})
    d = load(a.puf, var_map)
    d = d[d.group.isin(["haredi", "nonharedi_jew"]) & d.reported.notna()].copy()
    d["haredi"] = (d.group == "haredi").astype(int)
    d["female"] = (d.Min == 2).astype(int)
    d["age"] = d.agegroup.map(AGE)
    d["period"] = d.year.map(MAIN_PERIODS)
    d["pid"] = d.year.astype(str) + "_" + d.respondent.astype(str)
    d = d.dropna(subset=["age", "period"])
    d["wn"] = d.w / d.w.mean()

    models = {
        "M0": ("reported ~ haredi", d),
        "M1": ("reported ~ haredi + C(crime_type, Treatment('violence_threat')) + female + C(age) + C(period)", d),
        "M1x": ("reported ~ haredi + C(crime_type, Treatment('violence_threat')) + female + C(age) + C(period)",
                d[d.crime_type != "cyber"]),
        "M2": ("reported ~ haredi * C(period) + C(crime_type, Treatment('violence_threat')) + female + C(age)", d),
    }
    warnings.filterwarnings("ignore", message="cov_type not fully supported")  # נבדק מול bootstrap (ראו למעלה)
    rows = []
    for name, (formula, x) in models.items():
        fit = smf.glm(formula, data=x, family=sm.families.Binomial(), var_weights=x.wn).fit(
            cov_type="cluster", cov_kwds={"groups": pd.factorize(x.pid)[0]})
        ci = fit.conf_int()
        for term in fit.params.index:
            rows.append(dict(model=name, term=term, odds_ratio=round(np.exp(fit.params[term]), 3),
                             ci95_low=round(np.exp(ci.loc[term, 0]), 3), ci95_high=round(np.exp(ci.loc[term, 1]), 3),
                             p_value=round(fit.pvalues[term], 4), n_records=len(x),
                             n_haredi_records=int(x.haredi.sum()), formula=formula))
        if name == "M2":  # יחס הסיכויים חרדי/לא-חרדי בכל תקופה = haredi + haredi:period
            for per in sorted(x.period.unique()):
                inter = f"haredi:C(period)[T.{per}]"
                L = np.array([[1.0 if t == "haredi" or t == inter else 0.0 for t in fit.params.index]])
                tt = fit.t_test(L)
                lo, hi = tt.conf_int()[0]
                rows.append(dict(model="M2", term=f"haredi_in_{per}", odds_ratio=round(np.exp(tt.effect[0]), 3),
                                 ci95_low=round(np.exp(lo), 3), ci95_high=round(np.exp(hi), 3),
                                 p_value=round(float(tt.pvalue), 4), n_records=len(x),
                                 n_haredi_records=int(x[x.period == per].haredi.sum()), formula=formula))
    out = pd.DataFrame(rows)
    os.makedirs(a.out, exist_ok=True)
    out.to_csv(os.path.join(a.out, "pss_reporting_logit.csv"), index=False)
    print(out[out.term.str.contains("haredi")][["model", "term", "odds_ratio", "ci95_low", "ci95_high", "p_value",
                                                  "n_records", "n_haredi_records"]].to_string(index=False))


if __name__ == "__main__":
    main()
