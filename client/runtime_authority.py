#!/usr/bin/env python3
"""Shared adapter authority composition (architecture R4, checklist R4a).

runtime_authority_context composes a runtime adapter's already-read policy
document with the manifest-delivered reminder context returned by a concierge
/inject call, so remote adapters (e.g. asrock) receive the same operator
authority as the local hook without duplicating delivery logic.

Fail-closed by contract: a missing, partial or malformed authority response is
a ValueError naming the offending field — never a fabricated success and never
a silently filtered composition. The returned text carries no credentials;
only the caller-supplied policy provenance and the authority fields the
concierge itself published.
"""
from __future__ import annotations

import json


def _require_text(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _validate_rules(rules) -> list:
    if not isinstance(rules, list) or not rules:
        raise ValueError("inject response authority_rules must be a nonempty list")
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("authority rule descriptor must be an object")
        for key in ("id", "path", "sha256"):
            _require_text(rule.get(key), f"authority rule {key}")
    return rules


def runtime_authority_context(
    client, prompt: str, policy_text: str, policy_path: str
) -> str:
    """Combine exact-read policy text with injected manifest authority.

    client is any object exposing inject(prompt)->dict per the R1
    InjectResponse contract: nonempty string `context`, nonempty string
    `authority_revision`, and nonempty `authority_rules` list of objects with
    nonempty string id/path/sha256. The prompt is always delivered verbatim —
    an unrelated prompt still triggers the inject call. Policy and reminder
    text are embedded unmodified and labelled with their provenance.
    """
    _require_text(policy_text, "policy_text")
    _require_text(policy_path, "policy_path")
    result = client.inject(prompt)
    if not isinstance(result, dict):
        raise ValueError("inject response must be an object")
    context = _require_text(result.get("context"), "inject response context")
    revision = _require_text(
        result.get("authority_revision"), "inject response authority_revision"
    )
    rules = _validate_rules(result.get("authority_rules"))
    try:
        descriptors = json.dumps(rules, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"authority rule descriptors are not representable: {type(error).__name__}"
        ) from error
    return (
        "KStore shared runtime authority. Current explicit operator "
        "instructions take precedence over supplied policy text.\n\n"
        f"Operator policy document ({policy_path}):\n"
        f"{policy_text}\n\n"
        f"Injected manifest authority (revision {revision}):\n"
        f"Rule descriptors: {descriptors}\n"
        f"{context}"
    )
