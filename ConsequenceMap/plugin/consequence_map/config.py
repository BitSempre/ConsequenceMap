"""The plugin's configuration schema (LLM-6, section 13).

Every setting has a default, so the plugin runs with no configuration at
all. No setting requires a credential (LLM-4): the plugin declares no
python dependency on a paid service and reads no API key.
"""
from __future__ import annotations

from typing import Any, Dict

#: The configuration schema. `use_inference` is the only setting that
#: controls whether the plugin may consult a model; it defaults to
#: FALSE, so the plugin never calls a provider unless the user asks.
CONFIG_SCHEMA: Dict[str, Dict[str, Any]] = {
    "use_inference": {
        "type": "bool",
        "default": False,
        "description": (
            "When true, the plugin may consult an inference provider to "
            "draft a forecast. Defaults to false: no provider is contacted "
            "and no credential is read."
        ),
    },
    "inference_provider": {
        "type": "str",
        "default": "",
        "description": (
            "Optional provider name. Empty means no provider is configured. "
            "The plugin never reads an API key; the host's secret scope is "
            "the only source of a credential."
        ),
    },
    "inference_model": {
        "type": "str",
        "default": "",
        "description": "Optional model name used when use_inference is true.",
    },
}


def default_config() -> Dict[str, Any]:
    """The configuration the plugin runs with when nothing is set."""
    return {name: spec["default"] for name, spec in CONFIG_SCHEMA.items()}


def validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a configuration against the schema.

    An unknown key is rejected: a typo must not silently disable the
    inference switch.
    """
    unknown = sorted(set(config) - set(CONFIG_SCHEMA))
    if unknown:
        raise ValueError(f"unknown configuration key(s): {', '.join(unknown)}")
    merged = default_config()
    for name, value in config.items():
        spec = CONFIG_SCHEMA[name]
        expected = spec["type"]
        if expected == "bool":
            if not isinstance(value, bool):
                raise ValueError(f"{name} must be a boolean, got {value!r}")
        elif expected == "str":
            if not isinstance(value, str):
                raise ValueError(f"{name} must be a string, got {value!r}")
        merged[name] = value
    return merged
