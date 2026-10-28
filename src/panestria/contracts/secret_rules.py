"""Secret-material rules shared by the repository scan and runtime ingestion checks.

Callers report rule names only, never the matched text.
"""

from __future__ import annotations

import math
import re
from collections import Counter

# Split literals keep this file from matching its own rules.
RULES = (
    ("private-key", re.compile("-----BEGIN " + r"(?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----")),
    ("aws-access-key-id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("anthropic-api-key", re.compile("sk-" + r"ant-[A-Za-z0-9_-]{20,}")),
    ("openai-api-key", re.compile(r"\bsk-(?:proj|svcacct|admin)-[A-Za-z0-9_-]{20,}|\bsk-[A-Za-z0-9]{48}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{22,}")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
)
# NAME_KEY = "value" style assignments are reported only when the value looks random.
ASSIGNMENT = re.compile(r"(?i)\b[A-Z0-9_]*(?:API_?KEY|SECRET|TOKEN|PASSWORD)\b\s*[:=]\s*[\"']?([A-Za-z0-9/+_-]{24,})")
MIN_ENTROPY = 4.0


def entropy(value: str) -> float:
    """Return the Shannon entropy of ``value`` in bits per character."""
    counts = Counter(value)
    return -sum(n / len(value) * math.log2(n / len(value)) for n in counts.values())


def rules_matching(text: str) -> list[str]:
    """Return the names of every rule that matches ``text``."""
    found = [name for name, pattern in RULES if pattern.search(text)]
    if any(entropy(match.group(1)) >= MIN_ENTROPY for match in ASSIGNMENT.finditer(text)):
        found.append("high-entropy-assignment")
    return found
