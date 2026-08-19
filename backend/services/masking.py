"""Deterministic PII masking shared across cloud, database and local (agent-go) remediation.

Mirrors `stableDeletionToken` in agent-go/cmd/agent/delete_mask.go so the same identifier
always masks to the same token regardless of which surface (local agent, cloud, database)
performed the deletion.
"""
from __future__ import annotations

import base64
import hashlib
import os

DELETION_TOKEN_SALT = os.environ.get("DELETION_TOKEN", "abcde12345fghij67890")


def mask_value(original: str) -> str:
    """Return a_manage_sqlite stable, irreversible masked token for `original`.

    Short values (<=4 chars) become an 8-char masked token.
    Longer values keep their first/last 2 characters and mask the middle,
    preserving the original length.
    """
    if not original or not original.strip():
        return original

    digest = hashlib.sha256(f"{DELETION_TOKEN_SALT}|{original}".encode("utf-8")).digest()
    encoded = base64.b32encode(digest).decode("ascii").rstrip("=").lower()

    if len(original) <= 4:
        return encoded[:8]

    middle_len = len(original) - 4
    if middle_len > len(encoded):
        repeated = encoded
        while len(repeated) < middle_len:
            repeated += encoded
        encoded = repeated

    return original[:2] + encoded[:middle_len] + original[-2:]
