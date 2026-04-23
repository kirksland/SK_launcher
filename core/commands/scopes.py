from __future__ import annotations


GLOBAL_SCOPE = "global"

KNOWN_COMMAND_SCOPES = frozenset(
    {
        GLOBAL_SCOPE,
        "projects",
        "asset_manager",
        "board",
        "board.focus",
        "board.edit",
        "board.timeline",
        "board.tool",
        "client",
        "settings",
        "dev",
    }
)


def normalize_scope(scope: object) -> str:
    return str(scope or "").strip().lower()


def is_known_scope(scope: object) -> bool:
    return normalize_scope(scope) in KNOWN_COMMAND_SCOPES


def scopes_overlap(left: object, right: object) -> bool:
    left_scope = normalize_scope(left)
    right_scope = normalize_scope(right)
    if not left_scope or not right_scope:
        return False
    if left_scope == right_scope:
        return True
    if left_scope == GLOBAL_SCOPE or right_scope == GLOBAL_SCOPE:
        return True
    return left_scope.startswith(f"{right_scope}.") or right_scope.startswith(f"{left_scope}.")
