"""
Deterministic (non-LLM) generators for poisoned datasets. Keeping these as
plain code - not model output - means the unit_tests baked into the case
template (expected_cleaned_count, expected_answer) always stay in sync with
what's actually in the dataset.
"""
from __future__ import annotations

import random
from typing import Any


def generate_poisoned_transactions(
    seed: str,
    clean_count: int = 8214,
    poison_count: int = 786,
) -> list[dict[str, Any]]:
    """Builds a shuffled list of `clean_count` valid transactions plus
    `poison_count` poisoned ones (negative timestamps, non-numeric amounts,
    duplicate record_ids). Total record count is intentionally NOT a round
    number so players can't shortcut cleaning by just guessing a count.

    NOTE: the CodingChallenge.unit_tests expected_cleaned_count must match
    `clean_count` exactly - this function is the single source of truth for
    that number, so the daily generator should always derive both from here
    rather than hardcoding them separately in real usage.
    """
    rng = random.Random(seed)
    records: list[dict[str, Any]] = []

    base_ts = 1_700_000_000
    for i in range(clean_count):
        records.append(
            {
                "record_id": f"TXN-{10000 + i}",
                "timestamp": base_ts + i * 37,
                "amount": round(rng.uniform(5, 5000), 2),
            }
        )
    # Plant the record the algorithm test expects to find.
    target = next(r for r in records if r["timestamp"] == base_ts + 500 * 37)
    target["record_id"] = "TXN-55291"

    for i in range(poison_count):
        kind = rng.choice(["negative_ts", "bad_amount", "dup_id"])
        if kind == "negative_ts":
            records.append({"record_id": f"TXN-P{i}", "timestamp": -abs(base_ts), "amount": rng.uniform(5, 100)})
        elif kind == "bad_amount":
            records.append({"record_id": f"TXN-P{i}", "timestamp": base_ts + i, "amount": "NaN"})
        else:
            dup = rng.choice(records[:clean_count])
            records.append(dict(dup))  # duplicate record_id, valid otherwise

    rng.shuffle(records)
    return records


def generate_poisoned_cell_pings(
    seed: str,
    num_devices: int = 40,
    pings_per_device: int = 60,
    poison_count: int = 640,
) -> list[dict[str, Any]]:
    """Builds cell-tower ping records for `num_devices` phones. Exactly one
    device ("the suspect's burner") pings the crime-scene tower twice within
    a suspiciously short window - everyone else's pings are spread out
    normally. Poisoned records have a null device_id, a negative
    signal_strength, or a malformed (non-string) tower_id.

    NOTE: like generate_poisoned_transactions, the CodingChallenge's
    unit_tests (expected_cleaned_count, expected_answer) must be derived
    from this function's actual output, not hardcoded separately.
    """
    rng = random.Random(seed)
    records: list[dict[str, Any]] = []
    base_ts = 1_700_000_000
    crime_scene_tower = "TWR-CS-07"

    suspect_device = f"DEV-{rng.randint(1000, 9999)}"
    clean_count = 0

    for d in range(num_devices):
        device_id = f"DEV-{1000 + d}" if d > 0 else suspect_device
        for p in range(pings_per_device):
            ts = base_ts + p * rng.randint(200, 900) + d * 31
            tower = crime_scene_tower if (device_id == suspect_device and p in (12, 13)) else f"TWR-{rng.randint(1, 40):02d}"
            records.append(
                {
                    "device_id": device_id,
                    "timestamp": ts,
                    "tower_id": tower,
                    "signal_strength": round(rng.uniform(-110, -60), 1),
                }
            )
            clean_count += 1

    for i in range(poison_count):
        kind = rng.choice(["null_device", "bad_signal", "bad_tower"])
        base = dict(rng.choice(records[:clean_count]))
        if kind == "null_device":
            base["device_id"] = None
        elif kind == "bad_signal":
            base["signal_strength"] = -abs(base["signal_strength"]) - 1000  # out-of-range placeholder value
            base["signal_strength"] = "N/A"
        else:
            base["tower_id"] = 404  # non-string tower id
        records.append(base)

    rng.shuffle(records)
    return records
