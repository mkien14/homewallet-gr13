"""Keep historical one-shot pilot identities consumed across fresh checkouts."""

import json
from pathlib import Path


HISTORY = Path(__file__).with_name("d3_run_history.json")


def require_unconsumed_run(run_id):
    history = json.loads(HISTORY.read_text(encoding="utf-8"))
    run = history.get("runs", {}).get(run_id)
    if not run or run.get("consumed") is not False:
        raise RuntimeError("Historical/unapproved pilot cannot run; preserve its evidence and use a separately approved new run identity.")
