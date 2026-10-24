import json
import itertools
import sys
import postprocess as pp

def load(path):
    with open(path, encoding="utf-8") as fh:
        return {d["doc_id"]: d for d in map(json.loads, fh)}

def main(pred_path, gt_path):
    print("Loading data...", flush=True)
    subdiv = pp.load_subdivisions()
    pred = load(pred_path)
    gt   = load(gt_path)

    docs = []
    print("Extracting features...", flush=True)
    for doc_id, d in pred.items():
        if doc_id not in gt: continue
        
        ok, vals, reasons = pp.evaluate_doc(d, subdiv, 0.0, 0.0)
        correct = all(pp.norm(vals.get(f, "")) == pp.norm(gt[doc_id]["fields"].get(f)) for f in pp.FIELDS)
        
        q = d.get("quality") or {}
        viz = d.get("viz") or {}
        
        min_f_conf = min([pp._conf(viz.get(f)) for f in pp.FIELDS] or [1.0])
        min_c_conf = 1.0
        for f in pp.FIELDS:
            field = viz.get(f)
            if field:
                c = pp._min_char_conf(field.get("lines"))
                if c < min_c_conf: min_c_conf = c

        static_errors = [r for r in reasons if not r.startswith(("conf:", "char:"))]

        docs.append({
            "doc_id": doc_id,
            "correct": correct,
            "static_errors": static_errors,
            "min_f_conf": min_f_conf,
            "min_c_conf": min_c_conf,
            "doc_px": q.get("doc_px", 0),
            "sharpness": q.get("sharpness", 0),
            "glare": q.get("glare", 0),
            "vals": vals,
            "gt": gt[doc_id]["fields"]
        })

    correct_errs = {}
    for d in docs:
        if d["correct"]:
            for e in d["static_errors"]:
                correct_errs[e] = correct_errs.get(e, 0) + 1
    print(f"\nStatic errors on CORRECT docs: {correct_errs}", flush=True)

    grid = {
        "field_conf": [0.0, 0.8, 0.9, 0.95, 0.98, 0.99, 0.995],
        "char_conf":  [0.0, 0.6, 0.8, 0.9, 0.95, 0.98, 0.99, 1.0],
        "doc_px":     [0, 500, 700],
        "sharpness":  [0, 20, 50],
        "glare":      [1.0, 0.5, 0.3, 0.1],
    }
    
    print("Running grid search...", flush=True)
    best = None
    for combo in itertools.product(*grid.values()):
        thr = dict(zip(grid.keys(), combo))
        good = bad = 0
        bad_docs_list = []
        
        for d in docs:
            if d["static_errors"]: continue
            if d["min_f_conf"] < thr["field_conf"]: continue
            if d["min_c_conf"] < thr["char_conf"]: continue
            if d["doc_px"] < thr["doc_px"]: continue
            if d["sharpness"] < thr["sharpness"]: continue
            if d["glare"] > thr["glare"]: continue
                
            if d["correct"]: 
                good += 1
            else: 
                bad += 1
                bad_docs_list.append(d)
                
        if best is None or (bad < best[1]) or (bad == best[1] and good > best[0]):
            best = (good, bad, thr, bad_docs_list)
            
    if best:
        good, bad, thr, bad_docs = best
        print(f"\nBEST COMBO FOUND:")
        print(f"Accepted correctly:   {good}")
        print(f"Accepted incorrectly: {bad}")
        print("Thresholds:", thr)
        
        if bad > 0:
            print("\n--- EXACT ERRORS IN THE INCORRECT DOCS ---")
            for d in bad_docs:
                print(f"\nDoc ID: {d['doc_id']}")
                print(f"  Conf: F={d['min_f_conf']:.3f}, C={d['min_c_conf']:.3f}")
                print(f"  Quality: px={d['doc_px']}, sharp={d['sharpness']}, glare={d['glare']}")
                for f in pp.FIELDS:
                    v = pp.norm(d['vals'].get(f, ""))
                    g = pp.norm(d['gt'].get(f, ""))
                    if v != g:
                        print(f"  {f}:\n    Pred: '{v}'\n    GT:   '{g}'")
    else:
        print("No combo found.")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])