import json
import postprocess as pp

def load(path):
    with open(path, encoding="utf-8") as fh:
        return {d["doc_id"]: d for d in map(json.loads, fh)}

def main():
    subdiv = pp.load_subdivisions()
    pred = load("train_predictions.jsonl")
    gt   = load("train_labels.jsonl")

    bad_docs = []
    for doc_id, d in pred.items():
        if doc_id not in gt: continue
        
        ok, vals, _ = pp.evaluate_doc(d, subdiv, field_conf_thr=0.0, char_conf_thr=0.99)
        correct = all(pp.norm(vals.get(f, "")) == pp.norm(gt[doc_id]["fields"].get(f)) for f in pp.FIELDS)
        
        if ok and not correct:
            viz = d.get("viz") or {}
            c_conf = 1.0
            for f in pp.FIELDS:
                field = viz.get(f)
                if field:
                    c = pp._min_char_conf(field.get("lines"))
                    if c < c_conf: c_conf = c
            bad_docs.append((doc_id, c_conf, vals, gt[doc_id]["fields"]))

    print(f"Found {len(bad_docs)} errors at char_conf=0.8.\n")
    for doc_id, c_conf, v, g in bad_docs:
        print(f"--- {doc_id} (Min Char Conf: {c_conf:.3f}) ---")
        for f in pp.FIELDS:
            val = pp.norm(v.get(f, ""))
            gt_val = pp.norm(g.get(f, ""))
            if val != gt_val:
                print(f"  {f}: Pred='{val}' | GT='{gt_val}'")
        print()

if __name__ == "__main__":
    main()