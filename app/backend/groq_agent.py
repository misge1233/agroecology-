"""Backward-compatibility shim — the canonical agent moved to ``advisor_agent.py``.

Kept so older imports/scripts keep working. New code should import from
``advisor_agent`` directly.
"""
from advisor_agent import (  # noqa: F401
    INDICATOR_PHRASING,
    INDICATORS,
    PRACTICE_FAMILIES,
    SYSTEM_PROMPT,
    TOOLS,
    AgroAdvisor,
    CSAAdvisor,
    run_tool,
    _is_social_ack,
)
