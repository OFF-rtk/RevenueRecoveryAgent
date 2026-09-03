import json

with open("reports/live_persona_report.json", "r") as f:
    report = json.load(f)

with open("reports/conversations_dump.json", "r") as f:
    dump = json.load(f)

phone_map = {}
for case in report.get("cases_data", []):
    phone = case.get("phone")
    phone_map[phone] = {
        "persona": case.get("persona"),
        "harness_outcome": case.get("outcome")
    }

for d in dump:
    phone = d.get("customer_phone")
    if phone in phone_map:
        d["persona"] = phone_map[phone]["persona"]
        d["harness_outcome"] = phone_map[phone]["harness_outcome"]

with open("reports/conversations_dump.json", "w") as f:
    json.dump(dump, f, indent=2)

print("Updated conversations_dump.json with persona and harness_outcome")
