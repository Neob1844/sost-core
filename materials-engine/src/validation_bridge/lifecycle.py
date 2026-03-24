"""Candidate lifecycle states and transitions.

Each candidate progresses through a clear lifecycle:
  rejected → (terminal)
  watchlist → manual_review | validation_candidate
  manual_review → validation_candidate | watchlist | rejected
  validation_candidate → priority_validation | DFT_handoff_ready
  priority_validation → DFT_handoff_ready
  DFT_handoff_ready → handed_off
  handed_off → validation_pending
  validation_pending → result_received
  result_received → confirmed_partial | disagrees | inconclusive
"""

LIFECYCLE_STATES = {
    "rejected":                {"terminal": True,  "tier": 0},
    "watchlist":               {"terminal": False, "tier": 1},
    "known_reference":         {"terminal": True,  "tier": 0},
    "manual_review":           {"terminal": False, "tier": 2},
    "validation_candidate":    {"terminal": False, "tier": 3},
    "priority_validation":     {"terminal": False, "tier": 4},
    "DFT_handoff_ready":       {"terminal": False, "tier": 5},
    "handed_off":              {"terminal": False, "tier": 6},
    "validation_pending":      {"terminal": False, "tier": 7},
    "result_received":         {"terminal": False, "tier": 8},
    "confirmed_partial":       {"terminal": True,  "tier": 9},
    "disagrees_with_model":    {"terminal": True,  "tier": 9},
    "inconclusive":            {"terminal": True,  "tier": 9},
}

VALID_TRANSITIONS = {
    "watchlist": {"manual_review", "validation_candidate", "rejected"},
    "manual_review": {"validation_candidate", "watchlist", "rejected"},
    "validation_candidate": {"priority_validation", "DFT_handoff_ready", "watchlist"},
    "priority_validation": {"DFT_handoff_ready", "validation_candidate"},
    "DFT_handoff_ready": {"handed_off"},
    "handed_off": {"validation_pending"},
    "validation_pending": {"result_received"},
    "result_received": {"confirmed_partial", "disagrees_with_model", "inconclusive"},
}


def can_transition(current_state, target_state):
    """Check if a state transition is valid."""
    if current_state not in VALID_TRANSITIONS:
        return False
    return target_state in VALID_TRANSITIONS[current_state]


def get_tier(state):
    """Get numeric tier for a lifecycle state."""
    return LIFECYCLE_STATES.get(state, {}).get("tier", -1)
