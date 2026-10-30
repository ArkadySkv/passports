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

VALID_ON = date(2026, 10, 1)

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

def add_years(d, n):
    try: return d.replace(year=d.year + n)
    except ValueError: return d.replace(year=d.year + n, day=28)

def is_passport_valid(birth, issue):
    if not birth or not issue or issue <= birth: return False
    a = age_at(birth, issue)
    if a < 14: return False
    if a < 20:
        return add_years(birth, 20) >= VALID_ON
    if a < 45:
        return add_years(birth, 45) >= VALID_ON
    return True # Бессрочный (выдан в 45+)

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
    source = doc.get("source", "")
    
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
            
        # Дополнительная проверка для mobile_v2 (модель завышает уверенность)
        if source == "mobile_v2" and _conf(field) < 0.99:
            reasons.append("mobile_v2:low_field_conf")

    if len(values) != len(FIELDS):
        return False, values, reasons

    # 1. Format checks
    for f in ("Last_name_ru", "First_name_ru", "Middle_name_ru"):
        if not RE_CYR_NAME.match(norm(values[f])):
            reasons.append(f"fmt:{f}")

    sex = norm(values["Sex_ru"]).replace(".", "")
    if sex not in ("М", "МУЖ", "МУЖСКОЙ", "Ж", "ЖЕН", "ЖЕНСКИЙ"):
        reasons.append("fmt:sex")

    # 2. Dates & Validity
    birth = parse_date(values["Birth_date"])
    issue = parse_date(values["Issue_date"])
    if not birth or not issue:
        reasons.append("parse:date")
    else:
        if not is_passport_valid(birth, issue):
            reasons.append("date:expired")

    # 3. Birth Place Checks (Missing line logic)
    bp = norm(values["Birth_place_ru"])
    bp_field = viz.get("Birth_place_ru") or {}
    lines_count = len(bp_field.get("lines") or [])
    
    # Если адрес слишком короткий или нет ключевых слов региона/района, вероятно, потеряна строка
    if len(bp) < 20 or ("ОБЛ" not in bp and "КРАЙ" not in bp and "Р-Н" not in bp and "РАЙОН" not in bp and "РЕСП" not in bp):
        if lines_count <= 1:
            reasons.append("bp:truncated_or_missing_line")

    # 4. Issue Organization Checks
    code = values["Issue_organisation_code"].strip()
    org = norm(values["Issue_organization_ru"])
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

    # 5. Licence
    lic_digits = re.sub(r"\D", "", values["Licence_number"])
    if len(lic_digits) != 10:
        reasons.append("fmt:licence")

    return (not reasons), values, reasons

def main():
    if len(sys.argv) != 3:
        sys.exit("usage: postprocess.py <predictions.jsonl> <answers.jsonl>")
    
    inp, outp = sys.argv[1], sys.argv[2]
    subdiv = load_subdivisions()
    
    T_FIELD = 0.0
    T_CHAR = 1.0  # Самый безопасный порог
    
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