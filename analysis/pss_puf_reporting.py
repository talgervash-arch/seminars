"""
סדרה 2 — שיעור דיווח למשטרה בקרב נפגעים חרדים מול יהודים לא-חרדים (סקר ביטחון אישי, PUF).

הסקריפט לא מכיל שמות משתנים: כל המיפוי נמצא ב-analysis/var_map.csv
(להעתיק מ-var_map_template.csv ולמלא מתוך מילון ה-PUF של כל שנה).
קובצי ה-PUF עצמם נשארים ב-data/puf/ (מחוץ ל-git). הפלט — אגרגטים בלבד.

שימוש:
    python analysis/pss_puf_reporting.py [--var-map analysis/var_map.csv] [--out output/tables]

כללי דיווח (CLAUDE.md §5.5, DECISIONS.md):
    n לא-משוקלל < 30  -> האומדן לא מוצג
    30 <= n < 50      -> מסומן ⚠️
    רווח סמך 95% — Wilson עם n אפקטיבי של Kish (אין משתני תכנון ב-PUF)
"""
import argparse
import math
import os
import sys

import pandas as pd

PERIODS = {  # איחוד שנים — ראו DECISIONS.md
    "2015-2019": range(2015, 2020),
    "2020-2022": range(2020, 2023),
    "2023-2025": range(2023, 2026),
}
MIN_N, WARN_N = 30, 50


def read_puf(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return pd.read_csv(path, low_memory=False)
    if ext == ".sav":
        return pd.read_spss(path, convert_categoricals=False)  # דורש pyreadstat
    if ext == ".dta":
        return pd.read_stata(path, convert_categoricals=False)
    raise ValueError(f"unsupported PUF format: {path}")


def codes(cell):
    if pd.isna(cell) or str(cell).strip() == "":
        return set()
    return {float(c) for c in str(cell).split(";")}


def build_long(var_map):
    """מחזיר טבלה ארוכה: שנה × נפגע × סוג עבירה, עם דיווח (0/1), חרדי (0/1) ומשקל."""
    frames = []
    for year, vm in var_map.groupby("year"):
        if (vm["puf_variable"] == "TO_FILL").any():
            sys.exit(f"var_map: year {year} still has TO_FILL entries — fill from the PUF dictionary first")
        cache = {}

        def col(row):
            f = row["puf_file"]
            if f not in cache:
                cache[f] = read_puf(f)
            return cache[f][row["puf_variable"]]

        w_row = vm[vm.concept == "weight"].iloc[0]
        r_row = vm[vm.concept == "religiosity"].iloc[0]
        weight, relig = col(w_row), col(r_row)
        haredi_codes, other_jew_codes = codes(r_row["code_yes"]), codes(r_row["code_no"])
        group = pd.Series(pd.NA, index=relig.index, dtype="object")
        group[relig.isin(haredi_codes)] = "haredi"
        group[relig.isin(other_jew_codes)] = "nonharedi_jew"

        for _, row in vm[vm.concept == "reported"].iterrows():
            rep = col(row)
            yes, no = codes(row["code_yes"]), codes(row["code_no"])
            answered = rep.isin(yes | no) & group.notna()
            frames.append(pd.DataFrame({
                "year": year,
                "crime_type": row["crime_type"],
                "group": group[answered],
                "reported": rep[answered].isin(yes).astype(int),
                "weight": weight[answered].astype(float),
            }))
    return pd.concat(frames, ignore_index=True)


def summarize(df):
    rows = []
    for (period, crime, grp), d in df.groupby(["period", "crime_type", "group"]):
        n = len(d)
        w = d["weight"]
        p = (w * d["reported"]).sum() / w.sum()
        n_eff = w.sum() ** 2 / (w ** 2).sum()  # Kish
        z = 1.96
        denom = 1 + z ** 2 / n_eff
        centre = (p + z ** 2 / (2 * n_eff)) / denom
        half = z * math.sqrt(p * (1 - p) / n_eff + z ** 2 / (4 * n_eff ** 2)) / denom
        rows.append({
            "period": period, "crime_type": crime, "group": grp,
            "n_unweighted": n, "n_eff_kish": round(n_eff, 1),
            "reported_pct": round(100 * p, 1) if n >= MIN_N else None,
            "ci95_low": round(100 * (centre - half), 1) if n >= MIN_N else None,
            "ci95_high": round(100 * (centre + half), 1) if n >= MIN_N else None,
            "flag": "suppressed_n_lt_30" if n < MIN_N else ("warn_n_30_49" if n < WARN_N else ""),
        })
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--var-map", default="analysis/var_map.csv")
    ap.add_argument("--out", default="output/tables")
    a = ap.parse_args()
    var_map = pd.read_csv(a.var_map, dtype={"code_yes": str, "code_no": str})
    df = build_long(var_map)
    year_to_period = {y: p for p, ys in PERIODS.items() for y in ys}
    df["period"] = df["year"].map(year_to_period)
    by_period = summarize(df.dropna(subset=["period"]))
    by_year = summarize(df.assign(period=df["year"].astype(str)))
    os.makedirs(a.out, exist_ok=True)
    by_period.to_csv(os.path.join(a.out, "pss_reporting_haredi_by_period.csv"), index=False)
    by_year.to_csv(os.path.join(a.out, "pss_reporting_haredi_by_year.csv"), index=False)
    print(by_period.to_string(index=False))


if __name__ == "__main__":
    main()
