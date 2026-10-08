"""
סדרה 2 — דיווח למשטרה, סיבות לאי-דיווח ופנייה לגורמים נוספים, בקרב נפגעים חרדים מול יהודים לא-חרדים
(סקר ביטחון אישי, PUF, 2015–2025).

קלט:  data/puf/<שנה>/*data.csv (מחוץ ל-git) + analysis/var_map.csv (נבנה ב-build_var_map.py).
פלט:  output/tables/ — אגרגטים בלבד (מותר לפי רישיון ה-PUF; CLAUDE.md §9.8).

1. pss_puf_blocks.csv — "אבני בניין" לכל שנה × קבוצה × עבירה × מדד × קטגוריה:
   n_unweighted, n_base, sum_w, sum_w_base, sum_w2_base. כל הרכיבים חיבוריים, ולכן אפשר לחשב מהם
   כל איחוד שנים/עבירות בלי קובצי ה-PUF (שאינם נשמרים בין סשנים).
2. pss_puf_validation.csv — שיעור הדיווח לכלל בני 20+ לעומת הערכים שפרסמה הלמ"ס (לוח 1.4/1.5).
3. pss_reporting_haredi_by_year.csv / _by_period.csv — שיעורי דיווח עם כלל ההצגה ורווח סמך.
4. pss_reasons_by_period.csv, pss_other_bodies_by_period.csv — סיבות אי-דיווח ופנייה לגורמים נוספים.

הגדרות:
    נפגע       = משתנה ההיפגעות == "כן" (12 החודשים שקדמו לסקר).
    דיווח      = "האם דיווחת למשטרה על הפגיעה/הגניבה האחרונה" — מכנה: מי שענה כן/לא (כמו בפרסומי הלמ"ס).
    סיבה        = הסיבה העיקרית (תשובה אחת) — מכנה: מי שלא דיווח וענה על השאלה.
    גורם נוסף   = רב-בחירה, לכל נפגע (גם למי שדיווח) — מכנה: מי שסימן לפחות אפשרות אחת.
    קבוצות     = Datiut (נשאל יהודים בלבד): haredi = חרדי; nonharedi_jew = דתי/מסורתי/חילוני;
                 all_20plus = כל המשיבים.
כלל הצגה (DECISIONS #8, הצעה): n לא-משוקלל < 30 — לא מוצג; 30–49 — מסומן. רווח סמך 95% — Wilson עם
n אפקטיבי של Kish (אין משתני תכנון מדגם ב-PUF). נפגע של כמה עבירות נספר פעם לכל עבירה.

שימוש:
    python analysis/pss_puf_reporting.py [--puf data/puf] [--var-map analysis/var_map.csv] [--out output/tables]
"""
import argparse
import glob
import math
import os

import pandas as pd

PERIODS = {  # איחוד שנים — DECISIONS #7 (הצעה, ממתין לאישור)
    "2015-2019": range(2015, 2020),
    "2020-2022": range(2020, 2023),
    "2023-2025": range(2023, 2026),
    "2015-2025": range(2015, 2026),
    "2020-2025": range(2020, 2026),  # סיבות אי-דיווח: אותה רשימת קטגוריות בכל השנים (מ-2020 נוספה "טיפלת בעצמך")
}
MIN_N, WARN_N = 30, 50
GROUPS = ("haredi", "nonharedi_jew", "all_20plus")
PUBLISHED = "data/cbs_pss_reporting_by_crime.csv"


def year_records(df, vm):
    """רשומה לכל נפגע × עבירה: קבוצה, משקל, דיווח, סיבה, גורמים נוספים."""
    rel = vm[vm.concept == "religiosity"]
    code2grp = {float(c): ("haredi" if h == "haredi" else "nonharedi_jew") for c, h in zip(rel.code, rel.harmonized)}
    group = df["Datiut"].map(code2grp)
    w = df[vm[vm.concept == "weight"].puf_variable.iloc[0]].astype(float)
    out = []
    for crime, c in vm[vm.crime_type.notna() & (vm.crime_type != "")].groupby("crime_type"):
        def code(concept, harm):
            r = c[(c.concept == concept) & (c.harmonized == harm)]
            return float(r.code.iloc[0])
        victim_var = c[c.concept == "victim"].puf_variable.iloc[0]
        rep_var = c[c.concept == "reported"].puf_variable.iloc[0]
        is_victim = df[victim_var] == code("victim", "yes")
        rep = df[rep_var].map({code("reported", "yes"): 1, code("reported", "no"): 0})
        rec = pd.DataFrame({"crime_type": crime, "group": group, "w": w, "reported": rep, "respondent": df.index,
                            "Min": df["Min"], "agegroup": df["agegroup"]})[is_victim]  # שני האחרונים — לרגרסיה
        rs = c[c.concept == "reason_not_reported"]
        if not rs.empty:
            m = {float(k): h for k, h in zip(rs.code, rs.harmonized) if h != "no_answer"}
            rec["reason"] = df.loc[is_victim, rs.puf_variable.iloc[0]].map(m)
            rec.loc[rec["reported"] != 0, "reason"] = pd.NA
        ob = c[c.concept == "other_body"]
        for var, h in zip(ob.puf_variable, ob.harmonized):
            rec["ob_" + h] = (df.loc[is_victim, var] == 1).astype(int)
        out.append(rec)
    return pd.concat(out, ignore_index=True)


def blocks_for(rec, year, cats, offered):
    """אבני בניין לשנה אחת. לכל קטגוריה (מאיחוד כל השנים) נכתבת שורה גם כשאין בה מקרים, כדי שבאיחוד
    שנים המכנה יכלול את כל השנים; offered=False — הקטגוריה לא הופיעה בשאלון של אותה שנה."""
    rows = []
    false = pd.Series(False, index=rec.index)
    for grp in GROUPS:
        g = rec if grp == "all_20plus" else rec[rec.group == grp]
        for crime, d in g.groupby("crime_type"):
            def add(measure, category, base_mask, cat_mask, is_offered=True):
                b = d[base_mask]
                rows.append(dict(year=year, group=grp, crime_type=crime, measure=measure, category=category,
                                 offered=is_offered, n_unweighted=int(cat_mask[base_mask].sum()), n_base=len(b),
                                 sum_w=b.w[cat_mask[base_mask]].sum(), sum_w_base=b.w.sum(),
                                 sum_w2_base=(b.w ** 2).sum()))
            answered = d.reported.notna()
            add("reported", "yes", answered, d.reported == 1)
            if cats[crime]["reason"]:
                base = (d.reported == 0) & d.reason.notna()
                for cat in cats[crime]["reason"]:
                    add("reason_not_reported", cat, base, d.reason == cat,
                        ("reason_not_reported", cat) in offered[crime])
            if cats[crime]["other_body"]:
                obs = [x for x in d.columns if x.startswith("ob_")]
                base = d[obs].sum(axis=1) > 0
                for status, b2 in (("other_body", base), ("other_body_reporters", base & (d.reported == 1)),
                                   ("other_body_nonreporters", base & (d.reported == 0))):
                    for cat in cats[crime]["other_body"]:
                        col = "ob_" + cat
                        add(status, cat, b2, (d[col] == 1) if col in d else false[d.index],
                            ("other_body", cat) in offered[crime])
    return rows


def estimate(sum_w, sum_w_base, sum_w2_base, n_unweighted, n_base):
    p = sum_w / sum_w_base if sum_w_base else float("nan")
    n_eff = sum_w_base ** 2 / sum_w2_base if sum_w2_base else 0
    show = n_base >= MIN_N
    z = 1.96
    if n_eff > 0 and show:
        denom = 1 + z ** 2 / n_eff
        centre = (p + z ** 2 / (2 * n_eff)) / denom
        half = z * math.sqrt(p * (1 - p) / n_eff + z ** 2 / (4 * n_eff ** 2)) / denom
        lo, hi = max(0.0, 100 * (centre - half)), min(100.0, 100 * (centre + half))
    else:
        lo = hi = None
    return dict(n_base=n_base, n_cases=n_unweighted, n_eff_kish=round(n_eff, 1),
                pct=round(100 * p, 1) if show else None,
                ci95_low=round(lo, 1) if lo is not None else None,
                ci95_high=round(hi, 1) if hi is not None else None,
                flag="suppressed_n_lt_30" if not show else ("warn_n_30_49" if n_base < WARN_N else ""))


def pool(blocks, keys, label_col, label_of):
    b = blocks.assign(**{label_col: blocks.year.map(label_of)}).dropna(subset=[label_col])
    agg = b.groupby([label_col] + keys, as_index=False).agg(
        n_unweighted=("n_unweighted", "sum"), n_base=("n_base", "sum"), sum_w=("sum_w", "sum"),
        sum_w_base=("sum_w_base", "sum"), sum_w2_base=("sum_w2_base", "sum"),
        years=("year", "nunique"), years_offered=("offered", "sum"))
    est = agg.apply(lambda r: pd.Series(estimate(r.sum_w, r.sum_w_base, r.sum_w2_base, r.n_unweighted, r.n_base)), axis=1)
    return pd.concat([agg[[label_col] + keys + ["years", "years_offered"]], est], axis=1)


REASON_BROAD = {  # קיבוץ סיבות אי-דיווח (DECISIONS #18, הצעה) — לבחינת H3
    "police_unable": "police_wont_help", "police_unwilling": "police_wont_help",
    "police_ineffective_past": "police_wont_help", "didnt_know_police_handles": "police_wont_help",
    "turned_elsewhere": "handled_otherwise", "handled_self": "handled_otherwise",
    "not_worth_bothering": "not_worth_it", "personal_time": "not_worth_it",
    "ashamed": "shame_fear", "fear_revenge": "shame_fear",
    "other": "other",
}
COMBINED = {"all_personal": None, "all_personal_excl_cyber": ["theft", "violence_threat", "sexual_harassment"]}
NUM = ["n_unweighted", "sum_w"]
BASE = ["n_base", "sum_w_base", "sum_w2_base"]


def regroup(blocks, measure, new_measure, cat_map):
    """קיבוץ קטגוריות באותו מדד: מונים מתחברים, המכנה זהה."""
    b = blocks[blocks.measure == measure].assign(category=lambda x: x.category.map(cat_map), measure=new_measure)
    keys = ["year", "group", "crime_type", "measure", "category"]
    num = b.groupby(keys, as_index=False).agg(n_unweighted=("n_unweighted", "sum"), sum_w=("sum_w", "sum"),
                                              offered=("offered", "any"))
    base = b.groupby(["year", "group", "crime_type"], as_index=False)[BASE].first()
    return num.merge(base, on=["year", "group", "crime_type"])


def combine_crimes(blocks, measure):
    """'כל עבירות הפרט' (עם ובלי עבירה מקוונת): המכנה — סכום המכנים של העבירות; המונה — סכום המונים
    (קטגוריה שאינה קיימת בעבירה מסוימת נספרת 0 שם)."""
    b = blocks[blocks.measure == measure]
    out = []
    for name, crimes in COMBINED.items():
        x = b if crimes is None else b[b.crime_type.isin(crimes)]
        base = (x.groupby(["year", "group", "crime_type"], as_index=False)[BASE].first()
                 .groupby(["year", "group"], as_index=False)[BASE].sum())
        num = x.groupby(["year", "group", "category"], as_index=False).agg(
            n_unweighted=("n_unweighted", "sum"), sum_w=("sum_w", "sum"), offered=("offered", "any"))
        out.append(num.merge(base, on=["year", "group"]).assign(crime_type=name, measure=measure))
    return pd.concat(out, ignore_index=True)


def add_derived(blocks):
    blocks = pd.concat([blocks, regroup(blocks, "reason_not_reported", "reason_broad", REASON_BROAD)], ignore_index=True)
    derived = [combine_crimes(blocks, m) for m in ("reported", "reason_not_reported", "reason_broad")]
    return pd.concat([blocks] + derived, ignore_index=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--puf", default="data/puf")
    ap.add_argument("--var-map", default="analysis/var_map.csv")
    ap.add_argument("--out", default="output/tables")
    a = ap.parse_args()
    var_map = pd.read_csv(a.var_map, dtype={"code": str})
    os.makedirs(a.out, exist_ok=True)

    crimes = var_map[var_map.crime_type.notna()]
    cats = {c: {k: sorted(set(v[(v.concept == k) & (v.harmonized != "no_answer")].harmonized))
                for k in ("reason", "other_body")}
            for c, v in crimes.assign(concept=crimes.concept.replace({"reason_not_reported": "reason"})).groupby("crime_type")}
    rows = []
    for year, vm in var_map.groupby("year"):
        df = pd.read_csv(glob.glob(os.path.join(a.puf, str(year), "*data.csv"))[0], low_memory=False, encoding="utf-8-sig")
        v = vm[vm.crime_type.notna()]
        offered = {c: set(zip(x.concept, x.harmonized)) for c, x in v.groupby("crime_type")}
        rows += blocks_for(year_records(df, vm), year, cats, offered)
    blocks = add_derived(pd.DataFrame(rows))
    blocks.to_csv(os.path.join(a.out, "pss_puf_blocks.csv"), index=False)

    # אימות מול הפרסום: כלל בני 20+, % דיווח לפי עבירה ושנה
    est_year = pool(blocks[blocks.measure == "reported"], ["group", "crime_type"], "period", lambda y: str(y))
    pub = pd.read_csv(PUBLISHED)
    pub = pub[(pub.population == "all_20plus") & pub.reported_pct.notna()]
    val = est_year[est_year.group == "all_20plus"].merge(
        pub.assign(period=pub.year.astype(str))[["period", "crime_type", "reported_pct", "reported_reliability", "source"]],
        on=["period", "crime_type"], how="inner")
    val["diff"] = (val.pct - val.reported_pct).round(1)
    val[["period", "crime_type", "n_base", "pct", "reported_pct", "diff", "reported_reliability", "source"]].to_csv(
        os.path.join(a.out, "pss_puf_validation.csv"), index=False)

    by_period = []
    for p, ys in PERIODS.items():
        by_period.append(pool(blocks, ["group", "crime_type", "measure", "category"], "period",
                              lambda y, ys=ys, p=p: p if y in ys else None))
    by_period = pd.concat(by_period, ignore_index=True)
    rep_cols = ["period", "group", "crime_type", "n_base", "n_cases", "n_eff_kish", "pct", "ci95_low", "ci95_high", "flag"]
    is_rep = by_period.measure == "reported"
    by_period[is_rep][rep_cols].to_csv(os.path.join(a.out, "pss_reporting_haredi_by_period.csv"), index=False)
    est_year[rep_cols].to_csv(os.path.join(a.out, "pss_reporting_haredi_by_year.csv"), index=False)
    by_period[by_period.measure.isin(["reason_not_reported", "reason_broad"])].to_csv(
        os.path.join(a.out, "pss_reasons_by_period.csv"), index=False)
    by_period[by_period.measure.str.startswith("other_body")].to_csv(
        os.path.join(a.out, "pss_other_bodies_by_period.csv"), index=False)

    print("validation vs published (all 20+), |diff| > 0.5:")
    print(val[val["diff"].abs() > 0.5][["period", "crime_type", "pct", "reported_pct", "diff"]].to_string(index=False) or "  none")
    print(f"  {len(val)} year×crime cells compared; max |diff| = {val['diff'].abs().max()}")
    show = by_period[is_rep & by_period.group.isin(["haredi", "nonharedi_jew"])][rep_cols]
    print(show.sort_values(["crime_type", "period", "group"]).to_string(index=False))


if __name__ == "__main__":
    main()
