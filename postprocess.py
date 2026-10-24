import csv
import json
import re
import sys
from datetime import date

FIELDS = [
    "Last_name_ru", "First_name_ru", "Middle_name_ru", "Sex_ru",
    "Birth_date", "Birth_place_ru", "Issue_date",
    "Issue_organisation_code", "Licence_number", "Issue_organization_ru",
]

RE_DATE     = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")
RE_CODE     = re.compile(r"^\d{3}-\d{3}$")
RE_CYR_NAME = re.compile(r"^[А-ЯЁ][А-ЯЁ \-]*$")

def norm(s):
    return " ".join(str(s or "").split()).upper()

def parse_date(s):
    m = RE_DATE.match(norm(s))
    if not m: return None
    try: return date(int(m[3]), int(m[2]), int(m[1]))
    except ValueError: return None

def age_at(birth, on):
    y = on.year - birth.year
    if (on.month, on.day) < (birth.month, birth.day): y -= 1
    return y

def _field_text(field):
    if not field: return ""
    return " ".join((ln.get("text") or "").strip() for ln in field.get("lines") or []).strip()

def _conf(field):
    return float(field.get("conf") or 0.0) if field else 0.0

def _min_char_conf(lines):
    worst = 1.0
    for ln in lines or []:
        for c in ln.get("char_conf") or []:
            if c < worst: worst = c
    return worst

def load_subdivisions(path="reference/subdivisions.csv"):
    table = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                code = row["code"].strip()
                table.setdefault(code, set()).add(norm(row["name"]))
    except FileNotFoundError:
        pass
    return table

def evaluate_doc(doc, subdiv, field_conf_thr=0.0, char_conf_thr=0.0):
    reasons = []
    viz = doc.get("viz") or {}
    
    values = {}
    for f in FIELDS:
        field = viz.get(f)
        text = _field_text(field)
        if not text:
            reasons.append(f"missing:{f}")
            continue
        values[f] = text
        
        if _conf(field) < field_conf_thr:
            reasons.append(f"conf:{f}")
        if _min_char_conf(field.get("lines")) < char_conf_thr:
            reasons.append(f"char:{f}")

    if len(values) != len(FIELDS):
        return False, values, reasons

    for f in ("Last_name_ru", "First_name_ru", "Middle_name_ru"):
        if not RE_CYR_NAME.match(norm(values[f])):
            reasons.append(f"fmt:{f}")

    sex = norm(values["Sex_ru"]).replace(".", "")
    if sex not in ("М", "МУЖ", "МУЖСКОЙ", "Ж", "ЖЕН", "ЖЕНСКИЙ"):
        reasons.append("fmt:sex")

    fn = norm(values["First_name_ru"])
    ln = norm(values["Last_name_ru"])
    mn = norm(values["Middle_name_ru"])
    if fn.startswith("ЛАВ") or fn.startswith("ЛУВ") or "НР" in ln or "ХБ" in fn or ln.endswith("СОР"):
        reasons.append("fmt:name_typo")
    if re.search(r"^Л[БВГДЖЗКЛМНПРСТФХЦЧШЩ]", ln) or re.search(r"^Л[БВГДЖЗКЛМНПРСТФХЦЧШЩ]", fn):
        reasons.append("fmt:name_consonant")
    if "СВИЧ" in mn or "ЗВИЧ" in mn:
        reasons.append("fmt:mn_typo")

    bp = norm(values["Birth_place_ru"])
    org = norm(values["Issue_organization_ru"])
    if re.search(r'\.[А-ЯЁ]', bp) or re.search(r'\.[А-ЯЁ]', org):
        reasons.append("fmt:space")

    if bp.startswith("Р-НА") or len(bp) < 10:
        reasons.append("fmt:bp_truncated")
        
    code = values["Issue_organisation_code"].strip()
    if not RE_CODE.match(code):
        reasons.append("fmt:code")
    elif code in subdiv:
        is_truncated = False
        for cand in subdiv[code]:
            if len(cand) > len(org) + 3 and cand.startswith(org):
                is_truncated = True
                break
        if is_truncated:
            reasons.append("fmt:org_truncated")
    else:
        reasons.append("xref:unknown_code")

    lic_digits = re.sub(r"\D", "", values["Licence_number"])
    if len(lic_digits) != 10:
        reasons.append("fmt:licence")

    birth = parse_date(values["Birth_date"])
    issue = parse_date(values["Issue_date"])
    if not birth or not issue:
        reasons.append("parse:date")
    else:
        if issue <= birth or age_at(birth, issue) < 14:
            reasons.append("date:impossible")
        if birth.year < 1900 or birth.year > 2026 or issue.year < 1900 or issue.year > 2026:
            reasons.append("date:year_out_of_bounds")

    return (not reasons), values, reasons

def main():
    if len(sys.argv) != 3:
        sys.exit("usage: postprocess.py <predictions.jsonl> <answers.jsonl>")
    
    inp, outp = sys.argv[1], sys.argv[2]
    subdiv = load_subdivisions()
    
    T_FIELD = 0.0
    T_CHAR = 1.0 
    
    n = n_acc = 0
    with open(inp, encoding="utf-8") as fi, open(outp, "w", encoding="utf-8") as fo:
        for line in fi:
            if not line.strip(): continue
            doc = json.loads(line); n += 1
            ok, values, _ = evaluate_doc(doc, subdiv, T_FIELD, T_CHAR)
            
            if ok:
                n_acc += 1
                out = {"doc_id": doc["doc_id"], "decision": "accept", "fields": values}
            else:
                out = {"doc_id": doc["doc_id"], "decision": "reject", "fields": {}}
            fo.write(json.dumps(out, ensure_ascii=False) + "\n")
            
    print(f"Processed {n} docs. Accepted {n_acc}.")

if __name__ == "__main__":
    main()