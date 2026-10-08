"""
בדיקת תקינות לקובץ PUF של סקר ביטחון אישי (שנה אחת), לפני שמכניסים אותו לניתוח.

1. משווה N וממוצע של כל משתנה לקובץ הממוצעים של הלמ"ס (averages) — זהות = הקובץ נקרא נכון.
2. מדפיס: מספר משיבים, התפלגות Datiut, סכום GN_Prat.
3. מונה (לא משוקלל) נפגעים חרדים ודיווח למשטרה לכל עבירה כלפי הפרט שיש לה משתנה Hitlonen*Prat.
   המטרה — להעריך גודל מדגם, לא אומדנים. אין להציג את הספירות האלה כממצאים.

שימוש:
    python analysis/check_puf.py data/puf/2024
"""
import glob
import os
import sys

import pandas as pd


def find(folder, pattern):
    hits = [p for p in glob.glob(os.path.join(folder, "*")) if pattern in os.path.basename(p).lower()]
    return hits[0] if hits else None


def read_averages(path):
    """קובץ הממוצעים של הלמ"ס: שורת כותרת (Variable/Label/)N/Mean/...; העמודה הראשונה — שם המשתנה.
    בשנים מסוימות כל עמודה היא תא אחד עם ערכים מופרדים בשורות, ובאחרות שורה לכל משתנה."""
    raw = pd.read_excel(path, header=None).dropna(how="all").dropna(axis=1, how="all")
    is_hdr = raw.apply(lambda r: {"N", "Mean"} <= {str(c).strip() for c in r}, axis=1)
    hdr = raw.index[is_hdr][0]
    cols = [str(c).strip() for c in raw.loc[hdr]]
    cols[0] = "Variable"  # ב-2020 הכותרת קטועה ("iable")
    body = raw.loc[raw.index > hdr]
    out = {}
    for c, name in enumerate(cols):
        vals = []
        for cell in body.iloc[:, c].dropna():
            vals += str(cell).split("\n")
        out[name] = vals
    n = min(len(v) for v in out.values())
    return pd.DataFrame({k: v[:n] for k, v in out.items()})


def main(folder):
    data_path = find(folder, "data.csv")
    avg_path = find(folder, "averages")
    d = pd.read_csv(data_path, low_memory=False, encoding="utf-8-sig")
    print(f"{os.path.basename(data_path)}: {d.shape[0]} rows, {d.shape[1]} columns")

    if avg_path:
        a = read_averages(avg_path)
        bad, missing = [], []
        for _, r in a.iterrows():
            v = r["Variable"].strip()
            if v not in d.columns:
                missing.append(v)
                continue
            x = pd.to_numeric(d[v], errors="coerce")
            mean = r["Mean"].strip()
            if mean == ".":  # משתנה ריק (N=0) — בודקים רק N
                if int(x.notna().sum()) != int(float(r["N"])):
                    bad.append((v, r["N"], int(x.notna().sum()), mean, None))
                continue
            if int(x.notna().sum()) != int(float(r["N"])) or abs(x.mean() - float(mean)) > 1e-4 * max(1, abs(float(mean))):
                bad.append((v, r["N"], int(x.notna().sum()), r["Mean"], x.mean()))
        print(f"averages check: {len(a)} variables, {len(bad)} mismatches, {len(missing)} not in data")
        for b in bad[:20]:
            print("  MISMATCH", b)
        if missing:
            print("  not in data:", missing[:20])
    else:
        print("averages file not found — skipped")

    weight = "GN_Prat" if "GN_Prat" in d.columns else None
    print("weight GN_Prat:", f"sum={d[weight].sum():,.0f}" if weight else "NOT FOUND")
    if "Datiut" not in d.columns:
        print("Datiut NOT FOUND — check codebook")
        return
    print("Datiut:", d["Datiut"].value_counts(dropna=False).sort_index().to_dict())

    h = d[d["Datiut"] == 1]
    print("Haredi victims (unweighted counts; 1=reported, 2=not reported):")
    for rep in [c for c in d.columns if c.startswith("Hitlonen") and c.endswith("Prat")]:
        crime = rep[len("Hitlonen"):]
        if crime not in d.columns:
            print(f"  {rep}: victimization variable {crime} not found")
            continue
        v = h[h[crime] == 1]
        print(f"  {crime:<20} n={len(v):>3}  {v[rep].value_counts().sort_index().to_dict()}")


if __name__ == "__main__":
    main(sys.argv[1])
