"""Configuration, policy and the module-to-test map.

Every limit the owner set is expressed here as a named constant, so the
policy is readable in one place and testable.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

#: The project root. The Guardian never writes outside it.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: The package under test.
PACKAGE_DIR = PROJECT_ROOT / "consequence_map"

#: Where persistent verification reports are written.
REPORTS_DIR = PROJECT_ROOT / "quality_guardian" / "reports"

#: Where the Guardian keeps its state (last-seen hashes, etc.).
STATE_DIR = PROJECT_ROOT / "quality_guardian" / "state"

#: The Guardian's own source. Excluded from "changed project files" so the
#: Guardian never reacts to its own writes.
GUARDIAN_DIR = PROJECT_ROOT / "quality_guardian"

#: Directories that are never considered project sources.
EXCLUDED_DIRS = frozenset({
    "__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", ".venv", "venv",
})

#: File suffixes the Guardian tracks for change detection.
TRACKED_SUFFIXES = frozenset({".py", ".md", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".txt"})

#: Maximum repair attempts inside one Guardian cycle. The owner's hard limit.
MAX_REPAIR_ATTEMPTS = 3

#: Maximum consecutive pre_verify "continue" directives the Guardian emits
#: per turn. The runtime separately bounds this with agent.max_verify_nudges.
MAX_CONTINUE_NUDGES = 2

#: Seconds a single selective test run may take before it is abandoned.
SELECTIVE_TEST_TIMEOUT = 120

#: Seconds the full regression may take.
FULL_TEST_TIMEOUT = 600

#: Modules whose change forces a full regression, not just a selective run.
HIGH_IMPACT_MODULES = frozenset({
    "consequence_map.storage.schema",
    "consequence_map.storage.triggers",
    "consequence_map.storage.migrations",
    "consequence_map.storage.db",
    "consequence_map.domain.enums",
    "consequence_map.domain.validation",
})

#: Changed source module -> the test modules that must run.
#: Derived from the real import graph of the Phase 2A package (verified
#: against the installed tree), not guessed.
MODULE_TO_TESTS = {
    "consequence_map.domain.enums": ["test_enums"],
    "consequence_map.domain.validation": ["test_validation"],
    "consequence_map.domain.records": ["test_records"],
    "consequence_map.domain.serialization": ["test_serialization"],
    "consequence_map.domain.copy": ["test_coverage_gaps"],
    "consequence_map.storage.schema": ["test_schema", "test_serialization"],
    "consequence_map.storage.triggers": ["test_triggers"],
    "consequence_map.storage.repository": ["test_repository"],
    "consequence_map.storage.migrations": ["test_migrations"],
    "consequence_map.storage.db": ["test_integration"],
    "consequence_map.redaction.boundary": ["test_redaction"],
    "consequence_map.config": ["test_static_audits"],
    "consequence_map.dependencies": ["test_static_audits"],
    "consequence_guard.crypto": ['test_crypto', 'test_binding', 'test_rfc8032_vectors'],
    "consequence_guard.ipc": ['test_ipc', 'test_instance_id'],
    "consequence_guard.policy": ['test_binding'],
    "consequence_guard.protocol": ['test_ipc', 'test_binding'],
    "consequence_guard.recovery": ['test_recovery', 'test_recovery_after_crash', 'test_review_findings', 'test_review_round12'],
    "consequence_guard.client": ["test_ipc"],
    "consequence_guard.recovery_after_crash": ["test_recovery_after_crash", "test_instance_id"],
    "consequence_guard.service": ['test_service', 'test_binding', 'test_ipc'],
    "consequence_guard.store": ['test_store', 'test_recovery', 'test_recovery_after_crash'],
    "consequence_map.authorization": ['test_independent_review', 'test_phase2b', 'test_plugin_integration'],
    "consequence_map.core.agent": ['test_agent', 'test_regressions', 'test_regressions_round2'],
    "consequence_map.core.analysis": ['test_analysis', 'test_regressions_round2', 'test_regressions_round3', 'test_regressions_round6'],
    "consequence_map.core.audit": ['test_agent', 'test_audit', 'test_deployment', 'test_execution', 'test_guard', 'test_regressions', 'test_regressions_round2', 'test_regressions_round4', 'test_regressions_round5', 'test_regressions_round6', 'test_regressions_round7'],
    "consequence_map.core.authorization": ['test_agent', 'test_authorization', 'test_deployment', 'test_execution', 'test_guard', 'test_regressions', 'test_regressions_round2', 'test_regressions_round4', 'test_regressions_round5', 'test_regressions_round7'],
    "consequence_map.core.canonical": ['test_agent', 'test_audit', 'test_authorization', 'test_deployment', 'test_execution', 'test_guard', 'test_regressions', 'test_regressions_round2', 'test_regressions_round3', 'test_regressions_round4', 'test_regressions_round5', 'test_regressions_round6', 'test_regressions_round7'],
    "consequence_map.core.deployment": ['test_deployment', 'test_regressions_round2', 'test_regressions_round5'],
    "consequence_map.core.execution": ['test_agent', 'test_deployment', 'test_execution', 'test_guard', 'test_regressions', 'test_regressions_round2', 'test_regressions_round4', 'test_regressions_round5', 'test_regressions_round7'],
    "consequence_map.core.guard": ['test_agent', 'test_deployment', 'test_guard', 'test_regressions', 'test_regressions_round2', 'test_regressions_round5'],
    "consequence_map.core.timeutil": ['test_agent', 'test_audit', 'test_authorization', 'test_deployment', 'test_execution', 'test_guard', 'test_regressions', 'test_regressions_round2', 'test_regressions_round4', 'test_regressions_round5', 'test_regressions_round6', 'test_regressions_round7'],
    "consequence_map.correlation": ['test_independent_review', 'test_phase2b', 'test_plugin_integration'],
    "consequence_map.hooks": ['test_independent_review', 'test_phase2b', 'test_plugin_integration'],
    "consequence_map.lifecycle": ['test_independent_review', 'test_lifecycle'],
    "consequence_map.paths": ['test_phase2b'],
    "consequence_map.self_exclusion": ['test_independent_review', 'test_phase2b', 'test_plugin_integration'],
}

#: Extra test modules that must run whenever ANY package module changed,
#: because they assert cross-cutting invariants over the whole package.
ALWAYS_RUN_TESTS = ["test_import_audit", "test_static_audits"]

#: The full regression set.
FULL_TEST_SET = [
    "test_agent",
    "test_analysis",
    "test_audit",
    "test_authorization",
    "test_binding",
    "test_coverage_gaps",
    "test_crypto",
    "test_deployment",
    "test_enums",
    "test_execution",
    "test_guard",
    "test_host_load",
    "test_import_audit",
    "test_independent_review",
    "test_instance_id",
    "test_integration",
    "test_integrity_regressions",
    "test_ipc",
    "test_lifecycle",
    "test_migrations",
    "test_nonce",
    "test_phase2b",
    "test_plugin_integration",
    "test_records",
    "test_recovery",
    "test_recovery_after_crash",
    "test_redaction",
    "test_regressions",
    "test_regressions_round2",
    "test_regressions_round3",
    "test_regressions_round4",
    "test_regressions_round5",
    "test_regressions_round6",
    "test_regressions_round7",
    "test_repository",
    "test_review_findings",
    "test_review_round12",
    "test_rfc8032_vectors",
    "test_schema",
    "test_serialization",
    "test_service",
    "test_static_audits",
    "test_store",
    "test_triggers",
    "test_validation",
]

#: The minimum Hermes runtime the project declares.
REQUIRED_HERMES_VERSION = ">=0.22.5"

#: Paths, relative to the project root, the Guardian must never modify.
#: These are the product's security, approval and privacy surfaces.
PROTECTED_PATH_PATTERNS = (
    "consequence_map/storage/schema.py",
    "consequence_map/storage/triggers.py",
    "consequence_map/storage/migrations.py",
    "consequence_map/storage/db.py",
    "consequence_map/redaction/boundary.py",
    "consequence_map/domain/validation.py",
    "consequence_map/domain/enums.py",
    "consequence_map/dependencies.py",
)

#: Directories the Guardian must never modify.
PROTECTED_DIRS = ("consequence_map/tests",)

#: The minimum Hermes runtime floor, as a comparable tuple.
MIN_HERMES = (0, 22, 5)


def module_for_path(path) -> str:
    """Map a changed file path to its dotted module name, or ""."""
    p = Path(path)
    try:
        rel = p.resolve().relative_to(PROJECT_ROOT)
    except (ValueError, OSError):
        return ""
    parts = list(rel.parts)
    if not parts or parts[0] not in ("consequence_map", "consequence_guard"):
        return ""
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def is_protected(path) -> bool:
    """True when the path is a protected product surface."""
    p = Path(path)
    try:
        rel = p.resolve().relative_to(PROJECT_ROOT)
    except (ValueError, OSError):
        return True  # outside the project: treat as protected
    rel_s = rel.as_posix()
    if rel_s in PROTECTED_PATH_PATTERNS:
        return True
    return any(rel_s.startswith(d + "/") for d in PROTECTED_DIRS)


def ensure_dirs() -> None:
    """Create the Guardian's own state and report directories."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

#: Files covered by the Phase 2A manifest. The Guardian must not rewrite
#: them: a change would invalidate the manifest's hash and break the
#: audit trail of the delivered phase. Such files are reported, never
#: repaired automatically.
MANIFEST_PROTECTED_PREFIXES = (
    "consequence_map/",
    "docs/PHASE-2A-",
    "evidence/",
)


def is_manifest_protected(rel_path: str) -> bool:
    """True when the project-relative path is covered by the Phase 2A manifest."""
    rel = str(rel_path).replace("\\", "/")
    return any(rel.startswith(prefix) for prefix in MANIFEST_PROTECTED_PREFIXES)


#: A repair that would shrink a file below this fraction of its current
#: size is refused. A mechanical formatting fix never removes a large part
#: of a file; a repair that would is a sign of corruption, not of a
#: formatting defect, and is escalated instead.
MIN_REPAIR_SIZE_RATIO = 0.5

#: The repair policy file. It controls ONLY the automatic-repair capability.
#: Detection, test execution, reporting and baseline recording are unaffected.
REPAIR_POLICY_FILE = PROJECT_ROOT / "quality_guardian" / "state" / "repair-policy.json"

#: The default when the policy file is absent, unreadable or malformed:
#: automatic repair is DISABLED.
#:
#: An unreadable policy must never GRANT a capability the owner suspended.
#: Absence of evidence is not permission. A policy that explicitly says
#: ``auto_repair: true`` is the only thing that enables the capability.
DEFAULT_AUTO_REPAIR = False


def repair_policy(root: Path = None) -> dict:
    """Read the repair policy. Never raises; a malformed policy fails safe.

    "Fails safe" means the capability is **suspended**: an absent,
    unreadable, malformed or non-boolean policy resolves to
    ``DEFAULT_AUTO_REPAIR``, which is ``False``. Only an explicit
    ``"auto_repair": true`` in a readable policy file enables automatic
    repair.
    """
    base = Path(root) if root else PROJECT_ROOT
    path = base / "quality_guardian" / "state" / "repair-policy.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"auto_repair": DEFAULT_AUTO_REPAIR, "source": "default"}
    if not isinstance(data, dict):
        return {"auto_repair": DEFAULT_AUTO_REPAIR, "source": "default"}
    enabled = data.get("auto_repair", DEFAULT_AUTO_REPAIR)
    if not isinstance(enabled, bool):
        enabled = DEFAULT_AUTO_REPAIR
    result = dict(data)
    result["auto_repair"] = enabled
    result["source"] = str(path)
    return result


def auto_repair_enabled(root: Path = None) -> bool:
    """True when automatic repair is permitted. The single choke point."""
    return bool(repair_policy(root).get("auto_repair", DEFAULT_AUTO_REPAIR))
