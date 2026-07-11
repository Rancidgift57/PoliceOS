"""
Indian-themed flavor text: operation codenames for daily cases and Hindi/
Sanskrit-derived labels for the fixed pieces of UI (the tutorial, the
challenge slots). Purely cosmetic - none of this touches the deterministic
cleaning/algorithm specs or unit tests, same "narrative wrapper only"
principle as the rest of backend/generation/.
"""
from __future__ import annotations

import random

# "Operation <Codename>" - real Indian police/investigative operations are
# often named this way (e.g. Operation Kaali, Operation Trinetra). Mix of
# Hindi/Sanskrit words meaning things like "eagle-eye", "thunderbolt",
# "shadow", "truth" etc, kept in Roman script so they render everywhere.
OPERATION_CODENAMES = [
    "Cheel Nazar",     # Eagle Eye
    "Bijli",           # Lightning
    "Kaali Chhaya",    # Dark Shadow
    "Trinetra",        # Third Eye
    "Chakravyuh",      # The Maze / Trap
    "Satyanveshi",     # Truth-Seeker
    "Garud Drishti",   # Falcon Vision
    "Raat Ka Saya",    # Shadow of the Night
    "Agnipath",        # Path of Fire
    "Khoji",           # The Tracker
    "Andhera",         # Darkness
    "Sher Ki Maand",   # Lion's Den
    "Nishaan",         # The Mark / Sign
    "Vajra",           # Thunderbolt
    "Bhram",           # Illusion
    "Kohinoor",        # after the diamond - "the prized find"
    "Zanjeer",         # The Chain
    "Rakshak",         # Guardian
    "Anveshan",        # Investigation
    "Parchhai",        # The Shadow/Reflection
]

# Player-facing labels for the challenge slots inside a case, in place of
# the generic "Coding Challenge #1". "Chunauti" = challenge/dare in Hindi.
CHALLENGE_LABEL_PREFIXES = ["Chunauti", "Pehchaan", "Sabut"]  # Challenge / Identification / Proof

TUTORIAL_CODENAME = "Prashikshan"  # Training
TUTORIAL_TITLE = "Operation Prashikshan: The Rookie's First File"


def pick_codename(seed: str) -> str:
    rng = random.Random(seed)
    return rng.choice(OPERATION_CODENAMES)


def challenge_label(seed: str, index: int) -> str:
    rng = random.Random(f"{seed}:{index}")
    prefix = rng.choice(CHALLENGE_LABEL_PREFIXES)
    return f"{prefix} {index + 1}"
