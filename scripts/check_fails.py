import json

try:
    with open("reports/raw_batch.json") as f:
        data = json.load(f)
    
    print("\n--- Summary ---")
    for k, v in data.get("summary", {}).items():
        print(f"{k}: {v}")
    
    print("\n--- Failed Cases ---")
    for r in data.get("results", []):
        diag = r.get("diagnosed_cause")
        gt = r.get("ground_truth_cause")
        err = r.get("error")
        if err or (diag and diag != gt):
            print(f"Case {r.get('case_id')}: GT={gt}, Diag={diag}, Err={err}, Tier={r.get('tier')}, Context={r.get('additional_context')}")
except Exception as e:
    print(f"Error reading file: {e}")
