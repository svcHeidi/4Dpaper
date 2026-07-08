from __future__ import annotations
import sys
import re
from pathlib import Path
import time

def _expand_timeseries_steps(ts: dict, n_steps: int) -> list[int]:
    """Expand `steps` or `times` into step indices."""
    if ts["times"]:
        result = []
        for tok in ts["times"].split(","):
            tok = tok.strip()
            if tok == "first":
                result.append(0)
            elif tok == "last":
                result.append(max(0, n_steps - 1))
            else:
                try:
                    result.append(max(0, min(int(tok), n_steps - 1)))
                except ValueError:
                    pass
        if result:
            return result
    if n_steps <= 1:
        print(
            f"WARNING: timeseries '{ts['id']}' source has only {n_steps} step(s) "
            "— generating single frame.", file=sys.stderr
        )
        return [0]
    N = max(2, int(ts.get("steps", "4")))
    return [round(i * (n_steps - 1) / (N - 1)) for i in range(N)]

def _nearest_time_idx(sim, target_time: float) -> int:
    """Return the index in sim.time_steps closest to target_time."""
    times = sim.time_steps
    if not times:
        return 0
    return min(range(len(times)), key=lambda i: abs(times[i] - target_time))

