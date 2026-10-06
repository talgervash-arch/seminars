"""
בונה את נתוני סקר ביטחון אישי שפורסמו (הלמ"ס) לקובצי data/:

    data/cbs_pss_victimization_by_religiosity.csv  — לוח 1.2: יהודים בני 20+ שנפגעו, לפי דתיות (2015–2025)
    data/cbs_pss_reporting_by_crime.csv            — לוח 1.5 (2014: 1.4): % שדיווחו למשטרה, לפי סוג עבירה (2014–2025)
    data/cbs_pss_reporting_overall.csv             — שיעור דיווח כולל (הודעות לתקשורת)

מקורות:
    data/sources/cbs_pss/y*_t1_*.xls(x)   — קובצי האקסל של הלמ"ס (2014–2018, 2023–2025)
    data/sources/cbs_pss/manual_*.csv     — תעתיק ידני מ-PDF (2019–2022; אין קובצי אקסל), נבדק מול עמודים מרונדרים
    PDF_FLAGS (להלן)                      — סימוני מהימנות מה-PDF ל-2023–2025 (קובצי האקסל של שנים אלה לא מסמנים אותם)

סימונים: ok | low_rse_15_30 ("( )") | suppressed_rse_gt30 ("..") | no_cases ("-") | not_asked (תא ריק)
ב-2014 ההגדרות שונות: "( )" = 25%–40%, ".." = 40% ומעלה.

    python analysis/build_pss_published.py
"""
import csv
import os
import re
import warnings

import pandas as pd

warnings.filterwarnings("ignore")
SRC = "data/sources/cbs_pss"
BASE = "https://www.cbs.gov.il/he/publications/DocLib/"
PUB = {  # survey year: (pub. no., PDF path under BASE, printed page of t1.2, printed page of t1.5)
    2014: ("1614", "2015/victim14_1614/pdf/h_print.pdf", "", "80"),
    2015: ("1653", "2016/1653_bitachon_ishi_2015/h_print.pdf", "74", "77"),
    2016: ("1702", "2018/victim16_1702/h_print.pdf", "74", "77"),
    2017: ("1731", "2018/victim17_1731/h_print.pdf", "76", "79"),
    2018: ("1767", "2019/1767_bitachon_ishi_2018/h_print.pdf", "100", "103"),
    2023: ("1948", "2025/1948/h_print.pdf", "105", "109"),
    2024: ("1974", "2025/victim24_1974/h_print.pdf", "77", "81"),
    2025: ("1992", "2026/1992/h_print.pdf", "77", "81"),
}
CRIMES_12 = ["theft", "violence_threat", "sexual_harassment", "sexual_offences", "cyber", "cyberbullying_shaming"]
CRIMES_15 = ["theft", "violence_threat", "sexual_harassment", "sexual_offences", "cyber"]

# Table 1.2 rows as printed in the PDF (English layout = reversed column order):
# cyberbullying, cyber, sexual offences, sexual harassment, violence, theft, total, population
PDF_FLAGS = {
    2023: {"total_jews": ("132.2 515.7 (18.5) 177.7 257.9 145.8 906.3 4,567.1", "2.9 (11.3) (0.4) 3.9 5.6 3.2 19.8"),
           "haredi": (".. (36.1) .. .. (35.2) (17.2) 79.6 515.0", ".. (7.0) .. .. (6.8) (3.3) 15.5"),
           "dati": ("(16.6) 56.6 .. (27.1) (30.4) (17.7) 108.2 512.1", "(3.2) 11.0 .. (5.3) (5.9) (3.5) 21.1"),
           "masorti_dati": ("(16.4) 57.9 .. (15.7) (29.0) (23.0) 102.2 536.3", "(3.1) 10.8 .. (2.9) (5.4) (4.3) 19.1"),
           "masorti_lo_dati": ("(24.8) 95.0 .. (34.5) (50.2) (27.1) 170.3 824.0", "(3.0) 11.5 .. (4.2) (6.1) (3.3) 20.7"),
           "hiloni": ("65.3 270.1 .. 91.5 113.2 60.8 446.0 2,179.7", "3.0 12.4 .. 4.2 5.2 2.8 20.5")},
    2024: {"total_jews": ("143.3 483.0 .. 138.2 213.4 119.9 822.4 4,729.6", "3.0 10.2 .. 2.9 4.5 2.5 17.4"),
           "haredi": (".. (29.2) .. .. (30.9) (17.2) 72.8 573.3", ".. (5.1) .. .. (5.4) (3.0) 12.7"),
           "dati": ("(24.2) 71.7 .. .. (20.5) .. 109.5 594.5", "(4.1) 12.1 .. .. (3.4) .. 18.4"),
           "masorti_dati": (".. (46.5) - .. (14.2) .. 71.5 563.7", ".. (8.3) - .. (2.5) .. 12.7"),
           "masorti_lo_dati": ("(29.0) 96.6 .. (29.6) (37.0) (21.5) 153.8 874.8", "(3.3) 11.1 .. (3.4) (4.2) (2.5) 17.6"),
           "hiloni": ("73.5 239.0 .. 75.7 110.8 (55.2) 414.7 2,123.4", "3.5 11.3 .. 3.6 5.2 (2.6) 19.5")},
    2025: {"total_jews": ("137.5 453.8 .. 132.4 175.2 144.3 794.0 4,750.5", "2.9 9.6 .. 2.8 3.7 3.0 16.7"),
           "haredi": (".. (34.6) .. .. (15.2) (19.4) 66.8 607.1", ".. (5.7) .. .. (2.5) (3.2) 11.0"),
           "dati": (".. (36.0) .. .. (16.9) (21.1) 73.6 541.1", ".. (6.7) .. .. (3.1) (3.9) 13.6"),
           "masorti_dati": ("(17.9) (52.1) - (24.0) (36.4) .. 105.0 696.9", "(2.6) (7.5) - (3.4) (5.2) .. 15.1"),
           "masorti_lo_dati": ("(35.1) 92.1 .. (28.9) (33.3) (33.5) 167.4 824", "(4.3) 11.2 .. (3.5) (4.0) (4.1) 20.3"),
           "hiloni": ("65.9 239.2 .. 62.0 73.4 (56.1) 381.3 2,081.4", "3.2 11.5 .. 3.0 3.5 (2.7) 18.3")},
}
# Table 1.5, "reported to the police" % row as printed in the PDF (reversed: cyber, sex. offences, harassment, violence, theft)
PDF_FLAGS_15 = {2023: "(7.6) .. .. 32.6 32.8", 2024: "(6.7) .. .. 32.1 39.1", 2025: "(9.6) .. .. 35.0 31.7"}


def flag(tok, year=None):
    tok = "" if tok is None or str(tok) == "nan" else str(tok).strip()
    if tok == "..":
        return "", ("suppressed_rse_ge40" if year == 2014 else "suppressed_rse_gt30")
    if tok == "-":
        return "", "no_cases"
    if tok == "":
        return "", "not_asked"
    if tok.startswith("(") or tok.startswith(")"):
        return f"{float(tok.strip('()').replace(',', '')):.1f}", ("low_rse_25_40" if year == 2014 else "low_rse_15_30")
    return f"{float(tok.replace(',', '')):.1f}", "ok"


def group_of(label):
    s = str(label)
    if "סך כולל" in s:
        return "total_jews"
    if "חרד" in s:
        return "haredi"
    if "מסורתי" in s:
        return "masorti_lo_dati" if "לא" in s else "masorti_dati"
    if "חילונ" in s:
        return "hiloni"
    if re.fullmatch(r"\s*דתי(ים)?\s*", s):
        return "dati"
    return None


def read_t12(year):
    path = [f for f in os.listdir(SRC) if f.startswith(f"y{year}_t") and ("t1_2" in f or "t01_02" in f)][0]
    df = pd.read_excel(os.path.join(SRC, path), header=None, dtype=str)
    seen, out = {}, {}
    for _, row in df.iterrows():
        cells = list(row)
        for j, c in enumerate(cells):
            g = group_of(c) if str(c) != "nan" else None
            if g:
                n = 8 if year >= 2023 else 7  # pop, total, theft, violence, harassment, sex.off, cyber[, cyberbullying]
                vals = cells[j + 1:j + 1 + n]
                section = "thousands" if seen.get(g, 0) == 0 else "pct"
                seen[g] = seen.get(g, 0) + 1
                out.setdefault(g, {})[section] = vals
                break
    return out


def victimization_rows():
    rows = list(csv.DictReader(open(f"{SRC}/manual_t1_2_2019_2022.csv", encoding="utf-8")))
    for year in (2015, 2016, 2017, 2018, 2023, 2024, 2025):
        pub, pdf, page, _ = PUB[year]
        data = read_t12(year)
        for g, d in data.items():
            th, pc = d["thousands"], d.get("pct")  # 2023+ xlsx: total_jews % row has no label
            pop = flag(th[0])[0]
            if year >= 2023:  # numbers from xlsx; flags from PDF (reversed order)
                pdf_t, pdf_p = (s.split() for s in PDF_FLAGS[year][g])
                pdf_t = list(reversed(pdf_t[:-1]))  # total..cyberbullying
                pdf_p = list(reversed(pdf_p))
            cols = ["total"] + CRIMES_12[: (6 if year >= 2023 else 5)]
            for k, crime in enumerate(cols):
                if year >= 2023:
                    tv, tf = flag(pdf_t[k]); pv, pf = flag(pdf_p[k])
                    # cross-check printed PDF value against the unrounded xlsx value
                    for printed, raw in ((tv, th[1 + k]), (pv, pc[1 + k] if pc else None)):
                        if printed and raw is not None:
                            assert abs(float(printed) - float(raw)) < 0.051, (year, g, crime, printed, raw)
                else:
                    tv, tf = flag(th[1 + k]); pv, pf = flag(pc[1 + k])
                rows.append(dict(year=year, religiosity=g, crime_type=crime, population_20plus_thousands=pop,
                                 victims_thousands=tv, victims_pct=pv, reliability=pf, reliability_thousands=tf,
                                 source=f"CBS pub. {pub}, table 1.2", page=page, url=BASE + pdf,
                                 note=("2023+: excludes respondents who did not state religiosity" if year >= 2023 else "")))
    rows.sort(key=lambda r: (int(r["year"]), r["religiosity"], r["crime_type"]))
    return rows


def reporting_rows():
    rows = list(csv.DictReader(open(f"{SRC}/manual_t1_5_2019_2022.csv", encoding="utf-8")))
    for year in (2014, 2015, 2016, 2017, 2018, 2023, 2024, 2025):
        pub, pdf, _, page = PUB[year]
        name = [f for f in os.listdir(SRC) if f.startswith(f"y{year}_t") and ("t1_5" in f or "t01_05" in f or (year == 2014 and "t1_4" in f))][0]
        df = pd.read_excel(os.path.join(SRC, name), header=None, dtype=str)
        rep = [list(r) for _, r in df.iterrows() if any("דיווחו למשטרה" in str(c) and "לא" not in str(c) for c in r)]
        notrep = [list(r) for _, r in df.iterrows() if any("לא דיווחו למשטרה" in str(c) for c in r)]
        def vals(r):
            j = next(i for i, c in enumerate(r) if "דיווחו" in str(c))
            return r[j + 1:j + 6]
        rep_pct, notrep_pct = vals(rep[1]), vals(notrep[1])  # [0] = thousands, [1] = percentages
        if year >= 2023:
            printed = list(reversed(PDF_FLAGS_15[year].split()))
        for k, crime in enumerate(CRIMES_15):
            if year >= 2023:
                av, af = flag(printed[k])
                if av:
                    assert abs(float(av) - float(rep_pct[k])) < 0.051, (year, crime, av, rep_pct[k])
            else:
                av, af = flag(rep_pct[k], year)
            bv, bf = flag(notrep_pct[k], year)
            rows.append(dict(year=year, population="all_20plus", crime_type=crime, reported_pct=av, reported_reliability=af,
                             not_reported_pct=bv, not_reported_reliability=bf,
                             source=f"CBS pub. {pub}, table {'1.4' if year == 2014 else '1.5'}", page=page, url=BASE + pdf,
                             note="most recent incident; % of victims who answered the reporting question"))
    rows.sort(key=lambda r: (int(r["year"]), r["crime_type"]))
    return rows


def overall_rows():
    df = pd.read_excel(f"{SRC}/mr275_t12.xlsx", header=None)
    url = "https://www.cbs.gov.il/he/mediarelease/DocLib/2024/275/18_24_275t12.xlsx"
    rows = []
    for _, r in df.iterrows():
        if str(r[1]).isdigit():
            rows.append(dict(year=int(r[1]), measure="reported_pct_personal_crimes_excl_cyber", value=round(float(r[2]), 1),
                             source="CBS media release 275/2024, chart 12 data", url=url,
                             note=f"victimization rate (personal crimes excl. cyber) = {round(float(r[4]), 1)}%"))
    rows += [
        dict(year=2022, measure="victims_reported_at_least_once_pct", value=21.0, source="CBS media release 353/2024",
             url="https://www.cbs.gov.il/he/mediarelease/DocLib/2024/353/18_24_353b.pdf", note="186.1k of 887.6k victims"),
        dict(year=2023, measure="victims_reported_at_least_once_pct", value=18.1, source="CBS media release 353/2024",
             url="https://www.cbs.gov.il/he/mediarelease/DocLib/2024/353/18_24_353b.pdf", note="194.8k of 1.075m victims"),
        dict(year=2025, measure="victims_reported_at_least_once_pct", value=20.1, source="CBS media release 084/2026; pub. 1992 p.11",
             url="https://www.cbs.gov.il/he/mediarelease/DocLib/2026/084/18_26_084b.pdf",
             note="'reported victimization from one of the personal crimes'"),
    ]
    return rows


def write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"{path}: {len(rows)} rows")


if __name__ == "__main__":
    v = victimization_rows()
    for r in v:  # internal consistency: thousands / population ≈ %
        if r["victims_thousands"] and r["victims_pct"] and r["population_20plus_thousands"]:
            calc = 100 * float(r["victims_thousands"]) / float(r["population_20plus_thousands"])
            if abs(calc - float(r["victims_pct"])) > 0.11:
                print("  note: % != thousands/pop", r["year"], r["religiosity"], r["crime_type"], r["victims_pct"], round(calc, 2))
    write("data/cbs_pss_victimization_by_religiosity.csv", v)
    rep = reporting_rows()
    for r in rep:
        if r["reported_pct"] and r["not_reported_pct"]:
            assert abs(float(r["reported_pct"]) + float(r["not_reported_pct"]) - 100) < 0.15, r
    write("data/cbs_pss_reporting_by_crime.csv", rep)
    write("data/cbs_pss_reporting_overall.csv", overall_rows())
