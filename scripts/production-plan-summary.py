"""Export resource actions only. Never publish a binary plan or complete plan JSON."""
import json
import sys

plan = json.load(sys.stdin)
changes = [
    {"address": item["address"], "actions": item["change"]["actions"]}
    for item in plan.get("resource_changes", [])
    if item["change"]["actions"] != ["no-op"]
]
print(json.dumps({"changes": changes}, indent=2))
