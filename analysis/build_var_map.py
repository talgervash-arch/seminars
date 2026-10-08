"""
בונה את analysis/var_map.csv מתוך מילוני ה-PUF (Codebook.xlsx) של סקר ביטחון אישי, 2015–2025.

לכל שנה: משקל, דתיות, ולכל עבירה כלפי הפרט — היפגעות, דיווח למשטרה, סיבה עיקרית לאי-דיווח
ופנייה לגורמים נוספים. הקודים והתוויות נלקחים מהמילון של אותה שנה, ומותאמים לקטגוריה אחידה
(`harmonized`) לפי נוסח התווית — כי מספור הקטגוריות משתנה בין שנים (למשל סיבות אי-דיווח:
7 קטגוריות ב-2015, 9 ב-2016–2019, 10 מ-2020).

תווית שאינה מתאימה לאף כלל — עוצרת את הסקריפט (לא מנחשים).
המילונים עצמם ב-data/puf/ (מחוץ ל-git); var_map.csv הוא תוצר שנכנס ל-git.

שימוש:
    python analysis/build_var_map.py [--puf data/puf] [--out analysis/var_map.csv]
"""
import argparse
import glob
import os
import re
import sys

import pandas as pd

YEARS = range(2015, 2026)  # ב-2014 לא נשאלה דתיות

CRIMES = {  # crime_type: (משתנה היפגעות, דיווח למשטרה, סיבה עיקרית לאי-דיווח, תחילית "גורמים נוספים" או None)
    "theft": ("GnevaPrat", "HitlonenGnevaPrat", "SibaLoHitlonenGnevaPrat", None),
    "violence_threat": ("AlimutPrat", "HitlonenAlimutPrat", "SibaLoHitlonenAlimutPrat", "DivuahAlimutPrat"),
    "sexual_harassment": ("HatradaMinitPrat", "HitlonenHatradaMinitPrat", "LoHitlonenHatradaMinitPrat", "DivuahHatradaMinitPrat"),
    "cyber": ("CyberPrat", "HitlonenCyberPrat", "LoHitlonenCyberPrat", "DivuahCyberPrat"),
}

# כללי התאמה לפי נוסח התווית — הסדר קובע (הראשון שמתאים)
RULES = {
    "religiosity": [
        (r"חרדי", "haredi"), (r"מסורתי-דתי", "traditional_religious"), (r"מסורתי", "traditional"),
        (r"חילוני", "secular"), (r"דתי", "religious"),
    ],
    "yes_no": [(r"אין מענה", "no_answer"), (r"^כן", "yes"), (r"^לא", "no")],
    "reason_not_reported": [
        (r"אין מענה", "no_answer"),
        (r"להטריח", "not_worth_bothering"),
        (r"אינה מסוגלת", "police_unable"),
        (r"אינה מעוניינת", "police_unwilling"),
        (r"מניסיון קודם", "police_ineffective_past"),
        (r"סיבות אישיות", "personal_time"),
        (r"לא ידעתי שהמשטרה מטפלת", "didnt_know_police_handles"),  # עבירה מקוונת, מ-2022
        (r"פני(ת|תם) ל(גורם אחר|גורמים אחרים)", "turned_elsewhere"),
        (r"התבייש", "ashamed"),
        (r"פחד", "fear_revenge"),
        (r"טיפל(ת|תם) ב", "handled_self"),
        (r"סיבה אחרת", "other"),
    ],
    "other_body": [
        (r"לא פני(ת|תי|תם)", "none"),
        (r"רווחה", "welfare"), (r"רי?פואי", "medical"), (r"נפשי", "mental_health"),
        (r"עמותה", "ngo"), (r"משפטי", "legal"),
        (r"מכר|^לחבר$", "acquaintance"),  # 2015, עבירה מקוונת: "לחבר"; מ-2016: "למכר שאינו קרוב משפחה"
        (r"קרוב משפחה", "family"), (r"מקום העבודה", "workplace"),
        # עבירה מקוונת בלבד
        (r"ספק שירות אינטרנט", "isp"), (r"לאתר אינטרנט", "website"), (r"חברת האשראי|בנק", "bank"),
        (r"איש מקצוע", "professional"), (r"גורם ממשלתי", "government"),
        (r"(גורם אחר|גורמים אחרים)", "other"),
    ],
}


def harmonize(kind, label):
    for pat, key in RULES[kind]:
        if re.search(pat, label):
            return key
    sys.exit(f"no harmonization rule for {kind} label: {label!r}")


def norm_code(c):
    s = str(c).strip()
    return s[:-2] if s.endswith(".0") else s


def read_codebook(path):
    cb = pd.read_excel(path, header=None).iloc[:, :5]
    cb.columns = ["question", "var", "code", "label", "note"]
    cb["question"] = cb["question"].ffill()
    cb["var"] = cb["var"].str.strip().ffill()  # במילונים יש שמות עם רווח/שורה חדשה בסוף
    return cb.dropna(subset=["code"])


def entries(cb, var):
    s = cb[cb["var"].str.lower() == var.lower()]  # במילון לעיתים באותיות קטנות (divuahhatradaminitprat1)
    if s.empty:
        return None
    return [(norm_code(r.code), " ".join(str(r.label).split())) for r in s.itertuples() if pd.notna(r.label)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--puf", default="data/puf")
    ap.add_argument("--out", default="analysis/var_map.csv")
    a = ap.parse_args()
    rows = []

    def add(year, concept, crime, var, code, label, harm):
        rows.append(dict(year=year, concept=concept, crime_type=crime, puf_variable=var,
                         code=code, label=label, harmonized=harm))

    for year in YEARS:
        cb = read_codebook(glob.glob(os.path.join(a.puf, str(year), "*Codebook.xlsx"))[0])
        add(year, "weight", "", "GN_Prat", "", "מקדם ניפוח פרט", "weight")
        for code, label in entries(cb, "Datiut"):
            if code.isdigit():
                add(year, "religiosity", "", "Datiut", code, label, harmonize("religiosity", label))
        for crime, (victim, reported, reason, other_prefix) in CRIMES.items():
            for concept, var in (("victim", victim), ("reported", reported)):
                for code, label in entries(cb, var):
                    add(year, concept, crime, var, code, label, harmonize("yes_no", label))
            for code, label in entries(cb, reason):
                if code.isdigit():
                    add(year, "reason_not_reported", crime, reason, code, label, harmonize("reason_not_reported", label))
            if other_prefix:
                k = 1
                while (e := entries(cb, f"{other_prefix}{k}")) is not None:
                    for code, label in e:
                        if code == "1":  # כל אפשרות היא משתנה נפרד; 1 = סומן
                            add(year, "other_body", crime, f"{other_prefix}{k}", code, label, harmonize("other_body", label))
                    k += 1

    vm = pd.DataFrame(rows)
    vm.to_csv(a.out, index=False, encoding="utf-8")
    print(f"wrote {a.out}: {len(vm)} rows")
    for concept in ("reason_not_reported", "other_body"):
        t = vm[vm.concept == concept].pivot_table(index=["crime_type", "harmonized"], columns="year",
                                                   values="code", aggfunc="first")
        print(f"\n{concept} — code per year:")
        print(t.fillna("·").to_string())


if __name__ == "__main__":
    main()
