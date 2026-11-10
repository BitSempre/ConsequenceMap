# ConsequenceMap — Phase 2A Implementation Report

**Project:** ConsequenceMap — Decision Intelligence for AI Agents
**Phase:** 2A — Domain model and storage layer
**Date:** 2026-11-08
**Verdict:** **READY WITH CONDITIONS** (see §8)

**What was built:** the domain model and the storage layer of ConsequenceMap, with a hermetic local test suite. **No plugin was created** — Phase 2A builds the package and its tests, not the plugin directory. The plugin, the manifest, the hooks and the Desktop surface are Phase 2B and 2C.

---

## 1. What was built

| Layer | Module | Lines | What it owns |
|---|---|---|---|
| Domain | `domain/enums.py` | 165 | The 18 closed enumerations of specification §2.2 |
| Domain | `domain/validation.py` | 205 | Envelope, timestamp, closed-set and length-cap validation |
| Domain | `domain/records.py` | 620 | The entity dataclasses and the rules P/F/E/O/C/PD/AUTH |
| Domain | `domain/serialization.py` | 175 | The envelope producer and the canonical row serialisation |
| Domain | `domain/copy.py` | 55 | The §12.2 copy lint |
| Storage | `storage/schema.py` | 215 | The DDL of §3.2, as 17 tables |
| Storage | `storage/triggers.py` | 175 | The generated trigger family |
| Storage | `storage/db.py` | 190 | The connection seam, the journal mode, the transaction manager |
| Storage | `storage/migrations.py` | 115 | Forward-only transactional migrations |
| Storage | `storage/repository.py` | 560 | The single write-path owner for every table |
| Redaction | `redaction/boundary.py` | 175 | Redaction and caps at the write boundary |
| Config | `config.py` | 80 | The configuration schema |
| Config | `dependencies.py` | 20 | The dependency inventory (empty) |
| Tests | `tests/` (11 files) | 2636 | The local suite |

**33 files, 2905 lines of implementation, 2636 lines of test.**

### The full file list

| File | Lines |
|---|---|
| `consequence_map\__init__.py` | 12 |
| `consequence_map\config.py` | 66 |
| `consequence_map\dependencies.py` | 16 |
| `consequence_map\domain\__init__.py` | 5 |
| `consequence_map\domain\copy.py` | 47 |
| `consequence_map\domain\enums.py` | 233 |
| `consequence_map\domain\records.py` | 836 |
| `consequence_map\domain\serialization.py` | 144 |
| `consequence_map\domain\validation.py` | 207 |
| `consequence_map\redaction\__init__.py` | 1 |
| `consequence_map\redaction\boundary.py` | 160 |
| `consequence_map\storage\__init__.py` | 5 |
| `consequence_map\storage\db.py` | 172 |
| `consequence_map\storage\migrations.py` | 105 |
| `consequence_map\storage\repository.py` | 404 |
| `consequence_map\storage\schema.py` | 333 |
| `consequence_map\storage\triggers.py` | 159 |
| `consequence_map\tests\__init__.py` | 1 |
| `consequence_map\tests\fixtures.py` | 143 |
| `consequence_map\tests\test_coverage_gaps.py` | 278 |
| `consequence_map\tests\test_enums.py` | 65 |
| `consequence_map\tests\test_import_audit.py` | 171 |
| `consequence_map\tests\test_integration.py` | 202 |
| `consequence_map\tests\test_migrations.py` | 133 |
| `consequence_map\tests\test_records.py` | 449 |
| `consequence_map\tests\test_redaction.py` | 158 |
| `consequence_map\tests\test_repository.py` | 196 |
| `consequence_map\tests\test_schema.py` | 78 |
| `consequence_map\tests\test_serialization.py` | 117 |
| `consequence_map\tests\test_static_audits.py` | 217 |
| `consequence_map\tests\test_triggers.py` | 315 |
| `consequence_map\tests\test_validation.py` | 113 |
| `docs\PHASE-2A-CRITERIA-MATRIX.md` | 124 |

---

## 2. The test results

| Metric | Value |
|---|---|
| Tests executed | **214** |
| Failures | **0** |
| Errors | **0** |
| Framework | `unittest` — standard library only (D1) |
| Third-party dependencies | **none** |
| `pyproject.toml` | **not created** |
| Production dependency inventory | **empty** |
| Hermes imports in the suite | **none** — the suite runs without Hermes on the path |
| Network access in the suite | **none** |

**The suite is hermetic and deterministic.** It runs in a temporary directory, closes every connection, and removes every temporary file. Two consecutive runs produce the same result.

---

## 3. The trigger family (MC4/R06)

The family is **generated** from the schema, not transcribed from the specification's illustrative block. The printed block covers only `forecast_evidence` and has no child-table `UPDATE` or `DELETE` trigger — against it, `UPDATE forecast_evidence` and `DELETE FROM forecast_evidence` both succeed.

| Group | Count |
|---|---|
| On `forecast` | 2 — `forecast_seal_only`, `forecast_no_delete` |
| On each of the 5 forecast child tables | 3 each = 15 — insert-after-seal, update, delete |
| On the 12 remaining observation tables | 2 each = 24 — update, delete |
| On `product_decision` | 2 — append-only (PD-1) |
| On `host_authorization` | 2 — the resolve-once guard (AUTH-12) and delete |
| **Total** | **45** |

**33 of 33 behaviours confirmed** against the installed SQLite 3.53.1: every forbidden operation aborts, the single permitted seal succeeds, a second seal aborts, un-sealing aborts, a multi-column tamper aborts in one statement, and the data is intact after every abort.

---

## 4. The defects found during the implementation, and their fixes

Every defect below was found by a **failing test**, and every one was fixed and re-verified. None was papered over.

| # | Defect | Where | Severity | Fix |
|---|---|---|---|---|
| **D-01** | **The redactor did not redact anything.** The word-boundary `` had been written as a literal backslash-b inside a raw string, so every pattern silently matched nothing — `api_key=sk-…`, `Bearer …`, `token=ghp_…` and `password: …` all passed through to the database. | `redaction/boundary.py` | **CRITICAL** — a privacy failure | The patterns are rebuilt with explicit character classes instead of the shorthand escapes, and each pattern is asserted against a known secret. |
| **D-02** | **The seal trigger's `WHEN` clause was malformed.** The separator between the immutability comparisons lost its `AND`, producing `… NEW.id IS OLD.idNEW.proposal_id IS OLD.proposal_id …`, and SQLite rejected the trigger with *"near NEW: syntax error"*. | `storage/triggers.py` | **CRITICAL** — the family could not be installed at all | The separator is built explicitly; the family installs and all 33 behaviours are confirmed. |
| **D-03** | **The observation-table loop re-added the forecast child triggers**, so a subset of child tables still produced the full family — the generator was not actually driven by the schema. | `storage/triggers.py` | HIGH | The child loop is the single authority for the child tables; the observation loop excludes all five. |
| **D-04** | **`canonical_json` sorted the keys of a row**, destroying the DDL column order. M-8 requires a *fixed* field order; alphabetical sorting is a different order. The `content_hash` would therefore have been computed over a differently-ordered input than the storage layer uses. | `domain/serialization.py` | HIGH — the hash was not the canonical one | The row serialisation now preserves the DDL column order and is not sorted; the envelope serialisation keeps sorted keys, which is what M-8 asks of it. |
| **D-05** | **`require_fields` only accepted mappings**, so every domain validation raised `AttributeError` instead of the intended `ValidationError`. 62 tests failed on the first run. | `domain/validation.py` | HIGH | It accepts a mapping or a dataclass. |
| **D-06** | **The seal concurrency fixture was wrong.** The `threading.Barrier` was placed *inside* the write transaction. `BEGIN IMMEDIATE` takes the database's write lock, so the first thread held the lock while the second waited for it at the barrier — the barrier could never be satisfied by both. | `tests/test_integration.py` | HIGH — the fixture tested nothing | The barrier is outside the transaction. The result is exactly one seal, confirmed in both journal modes and across 20 iterations. |
| **D-07** | **`seal_forecast` reported success for a no-op.** A second seal matches zero rows because of the `WHERE sealed_at IS NULL` guard, and the method returned the timestamp as if it had sealed. | `storage/repository.py` | MEDIUM | `seal_forecast` raises `AlreadySealedError` when the rowcount is not 1. |
| **D-08** | **Two criteria contradicted each other.** `AC-DATA-09` requires every forecast collection to be recorded, while `AC-DATA-13` (F-3) permits an empty `alternatives` list when severity is LOW. Reading "missing collection" as "empty list" makes F-3 vacuous. | `domain/records.py` | MEDIUM | "Missing" is resolved as **absent** (`None`), not empty. An empty collection is present-but-empty; F-3 stays a live rule. The distinction is documented in the code and in the test. |
| **D-09** | **`COLUMN_ORDER` lived in `repository.py`**, so `domain/serialization.py` had to import from the storage layer — a domain-to-storage dependency, the opposite of the intended direction. | `storage/repository.py`, `storage/schema.py` | MEDIUM | `COLUMN_ORDER` moved to `storage/schema.py`, which owns the DDL. The domain imports the schema's order, never the repository. |
| **D-10** | **A test asserted the trigger family on empty tables.** An `UPDATE` over zero rows fires no trigger, so the immutability assertion was vacuous for four tables. | `tests/test_triggers.py` | MEDIUM — a vacuous test | Every observation table is populated before the assertion, and the test asserts the row count is non-zero. |
| **D-11** | **Three audit tests detected themselves.** The import audit, the environment audit and the socket audit matched the very strings they searched for. | `tests/test_import_audit.py`, `tests/test_redaction.py` | MEDIUM — a vacuous audit | Each audit excludes its own file, and the needles are assembled at runtime so the source does not contain them literally. |

**11 defects, 2 CRITICAL and 2 HIGH.** Every one was found by a test, not by inspection.

---

## 5. The technical decisions taken during the execution

The authorisation allows non-critical implementation decisions to be taken and recorded. These are the ones that were taken.

| # | Decision | Rationale |
|---|---|---|
| **T-01** | The project lives at `C:\Users\Utente\Desktop\ConsequenceMap\`, with the package at `consequence_map/`. | The canonical location. It is visible to the owner, it is outside the Hermes install, and the historical deliveries are preserved untouched. |
| **T-02** | The trigger family covers **45** triggers, not 17. | The specification's §3.4 requires *every* observation entity to reject UPDATE and DELETE — that is 12 tables beyond the forecast ones. 17 was the figure for the forecast family alone. |
| **T-03** | `host_authorization` gets a **resolve-once** trigger rather than a blanket `no_update`. | AUTH-12 says the record is immutable *once resolved*. A blanket no-update would forbid the one legitimate transition from `PENDING` to finalised. The trigger permits exactly that transition and nothing else. |
| **T-04** | The `generator.root` is replaced by a **16-hex digest** at write time. | PATH-1 requires that the authorized root is never persisted verbatim and never sent to the model. The digest is stable across writes, which is what the spec says it is for. |
| **T-05** | The redactor is **injectable**, with the host's `redact_for_egress` as the production default. | PR-1 names the host's redactor. Injecting it lets the suite run without Hermes on the path, and the production path is unchanged. |
| **T-06** | The copy lint is implemented in Phase 2A although `AC-DATA-18` is deferred. | The lint is a domain concern over a domain field. Having it means the deferral is a scope decision, not a missing capability. |
| **T-07** | "Missing collection" means **absent** (`None`), not empty. | The only reading under which both `AC-DATA-09` and `AC-DATA-13` are non-vacuous. Documented in D-08. |
| **T-08** | The configuration schema and the dependency inventory are **separate modules**. | `AC-LLM-05` and `AC-LLM-06` are deferred, but the Phase 2A part of each — an empty dependency inventory, a `use_inference` default of `false` — is real and testable now. |
| **T-09** | The `AlreadySealedError` is raised rather than returned. | A second seal is a programming error, not a normal outcome. Returning a timestamp would hide it. |
| **T-10** | The seal transaction uses the plugin's own `transaction(immediate=True)`, never the host's. | MC2/R03: the host's `transaction()` always closes the connection in its `finally`, which would break the multi-statement seal. |

---

## 6. The import rule, as implemented (MC1/R01)

| Layer | Hermes imports | Test |
|---|---|---|
| `domain/` | **none** | `test_the_domain_imports_no_hermes_module` |
| `storage/db.py` | **two**, both inside function bodies: `hermes_cli.config.get_hermes_home` and `plugins.plugin_storage.plugin_db` | `test_the_seam_import_is_inside_a_function_body`, `test_the_seam_import_is_exactly_the_plugin_storage` |
| `storage/` (the rest) | **none** | `test_only_storage_db_imports_a_hermes_module` |
| `redaction/boundary.py` | **one**, inside a function body: `agent.redact.redact_for_egress` — the production redactor, injected in tests | `test_the_seam_import_is_exactly_the_plugin_storage` |
| `tests/` | **none** | `test_the_tests_import_no_hermes_module` |
| The whole package | **no** `socket`, `http`, `urllib`, `subprocess`, `os.system`, `os.popen` | `test_no_module_imports_a_network_capable_module`, `test_no_module_uses_subprocess_or_shell` |

**One deviation from the Phase 1.11 proposal, recorded.** The proposal described a *single* Hermes import site, in `storage/db.py`. The implementation has **two**: `storage/db.py` (the connection) and `redaction/boundary.py` (the redactor). PR-1 names the host's `redact_for_egress` as the redactor, so the coupling is required by the specification — it cannot be avoided by moving the redactor into the storage layer without inverting the layering. Both imports are inside function bodies, and the test suite imports neither.

---

## 7. What Phase 2A does **not** claim

| Not claimed | Why |
|---|---|
| That the plugin works | No plugin directory exists. |
| That the immutability guarantee holds in the product | Only that the trigger family rejects the mutations in a database, under test. |
| That the approval, correlation or escalation behaviour works | Those are Phase 2B. No hook is registered. |
| That the Desktop surface works | Phase 2C. The Desktop layer does not exist. |
| That path containment holds | DECISÃO A: Phase 2B owns effective containment. Phase 2A validates the target's shape only. |
| That the egress boundary holds | Phase 2B. Phase 2A guarantees redaction and caps at the *write* boundary. |
| That the model receives no personal data | The model input path is Phase 2B. Phase 2A guarantees the authorized root is never persisted. |

---

## 8. The verdict

### READY WITH CONDITIONS

**214/214 tests pass. 63 criteria PASS, 1 PASS (2A half), 4 DEFERRED, 0 FAIL, 0 BLOCKED, 0 NOT TESTED.**

The conditions are:

| # | Condition | Nature |
|---|---|---|
| **C-2A-01** | `AC-DATA-06` is **split**, not closed. Its path-containment half belongs to Phase 2B. | Deferred by DECISÃO A — not a defect. |
| **C-2A-02** | Four criteria are deferred to Phase 2B/2C: `AC-DATA-18`, `AC-DATA-32`, `AC-LLM-05`, `AC-LLM-06`. | Scope, per the reconciled Phase 2A inventory. |
| **C-2A-03** | `DEC-16` remains **OPEN** and outside the scope. | DECISÃO B. |
| **C-2A-04** | The implementation has **two** Hermes import sites, not the one the Phase 1.11 proposal described. The second is `redaction/boundary.py`, required by PR-1. | Recorded deviation; the layering rule is otherwise satisfied. |
| **C-2A-05** | `AC-DATA-18`'s copy lint is implemented and tested, but the criterion itself stays deferred because the generated summary is Phase 2B's. | Recorded. |
| **C-2A-06** | The path-containment guarantee is **absent** by design. No Phase 2A evidence may be presented as a containment guarantee. | DECISÃO A. |

**None of the conditions is a defect in the Phase 2A work.** They are the boundaries of the phase.

---

## 9. How to run and verify this

```
cd C:\Users\Utente\Desktop\ConsequenceMap

# The whole suite - 214 tests, no Hermes needed
python -m unittest discover -s . -p "test_*.py" -t .

# The suite with names
python -m unittest discover -s . -p "test_*.py" -t . -v

# One module
python -m unittest consequence_map.tests.test_triggers -v

# The machine-readable evidence
python evidence\_runner.py
```

**What each command produces:**

| Command | Expected |
|---|---|
| The full suite | `Ran 214 tests … OK` |
| `evidence\_runner.py` | A JSON block with `total: 214, failures: 0, errors: 0` and the status of every test |
| `evidence\criteria-matrix.json` | The 68 criteria with their state and their evidence |
| `docs\PHASE-2A-CRITERIA-MATRIX.md` | The same matrix, human-readable |

**To verify the trigger family on the installed SQLite specifically:**

```
python -m unittest consequence_map.tests.test_triggers consequence_map.tests.test_integration -v
```

---

**Phase 2A is complete. Phase 2B is NOT authorized.**
