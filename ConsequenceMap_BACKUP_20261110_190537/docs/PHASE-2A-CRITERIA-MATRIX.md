# ConsequenceMap — Phase 2A Acceptance Criteria Matrix

**Project:** ConsequenceMap — Decision Intelligence for AI Agents
**Phase:** 2A — Domain model and storage layer (executed 2026-11-08)
**Date:** 2026-11-08
**Suite:** 214 tests, 0 failures, 0 errors

**The 68 criteria of the Phase 2A scope, each with its state and its evidence.**

Every state below is backed by an **executed** test. The evidence column names the file, the line and the test method; the machine-readable form is `evidence/criteria-matrix.json`.

## Summary

| State | Count | Criteria |
|---|---|---|
| **PASS** | **63** | every closable criterion, with an executed test |
| **PASS (2A half)** | **1** | `AC-DATA-06` - the target-validation half is executed; the path-containment half belongs to Phase 2B (DECISÃO A) |
| **DEFERRED** | **4** | `AC-DATA-18` → 2B, `AC-DATA-32` → 2C, `AC-LLM-05` → 2C, `AC-LLM-06` → 2B |
| **FAIL** | **0** | — |
| **BLOCKED** | **0** | — |
| **NOT TESTED** | **0** | — |
| **Total** | **68** | |

**Test-layer distribution, as scoped:** **{'unit': 55, 'integration': 3, 'static': 10}** — the split of 55 unit / 10 static / 3 integration is unchanged.

## The matrix

| Criterion | Layer | Rule | State | Evidence (file:line test) |
|---|---|---|---|---|
| `AC-DATA-01` | unit | `§2.1` | **PASS** | test_validation.py:10 test_AC_DATA_01_a_valid_envelope_is_accepted [ok]; test_validation.py:15 test_AC_DATA_01_an_unknown_major_version_is_rejected [ok]; test_validation.py:19 test_AC_DATA_01_a_missing_schema_version_is_rejected [ok]; test_validation.py:23 test_AC_DATA_01_a_non_integer_schema_version_is_rejected [ok]; test_validation.py:27 test_AC_DATA_01_a_boolean_schema_version_is_rejected [ok]; test_validation.py:32 test_AC_DATA_01_unknown_minor_fields_are_ignored [ok]; test_validation.py:36 test_AC_DATA_01_a_non_mapping_is_rejected [ok] |
| `AC-DATA-02` | unit | `§2.1` | **PASS** | test_validation.py:42 test_AC_DATA_02_a_valid_timestamp_is_accepted [ok]; test_validation.py:47 test_AC_DATA_02_a_timestamp_without_milliseconds_is_rejected [ok]; test_validation.py:51 test_AC_DATA_02_a_timestamp_with_an_offset_is_rejected [ok]; test_validation.py:55 test_AC_DATA_02_a_non_utc_timestamp_is_rejected [ok]; test_validation.py:59 test_AC_DATA_02_an_impossible_calendar_date_is_rejected [ok]; test_validation.py:63 test_AC_DATA_02_a_lowercase_z_is_rejected [ok]; test_validation.py:67 test_AC_DATA_02_a_non_string_is_rejected [ok] |
| `AC-DATA-03` | unit | `§2.1,§2.2` | **PASS** | test_enums.py:28 test_AC_DATA_03_a_member_validates [ok]; test_enums.py:33 test_AC_DATA_03_an_unknown_value_is_an_error_not_a_default [ok] |
| `AC-DATA-04` | unit | `§2.1,§8.3,§8.5` | **PASS** | test_coverage_gaps.py:28 test_AC_DATA_04_every_free_text_field_has_a_documented_cap [ok]; test_coverage_gaps.py:45 test_AC_DATA_04_the_caps_match_the_specification [ok] |
| `AC-DATA-05` | unit | `P-1` | **PASS** | test_records.py:19 test_AC_DATA_05_P1_scope_excluded_must_be_present [ok]; test_records.py:25 test_AC_DATA_05_P1_scope_excluded_must_be_non_empty [ok] |
| `AC-DATA-06` | unit | `P-2,§7.2` | **PASS (2A half)** | the 2A half is executed; the path-containment half -> Phase 2B (target validation -> 2A; path containment -> 2B) |
| `AC-DATA-07` | unit | `P-3` | **PASS** | test_records.py:43 test_AC_DATA_07_P3_a_non_filesystem_target_is_not_rejected [ok] |
| `AC-DATA-08` | unit | `P-4,§9` | **PASS** | test_records.py:48 test_AC_DATA_08_P4_an_undeterminable_target_kind_is_unknown [ok] |
| `AC-DATA-09` | unit | `§2.4` | **PASS** | test_records.py:66 test_AC_DATA_09_an_absent_collection_is_an_error [ok]; test_records.py:78 test_AC_DATA_09_an_empty_collection_is_present_not_missing [ok]; test_records.py:84 test_AC_DATA_09_a_missing_risk_is_an_error [ok] |
| `AC-DATA-10` | unit | `§2.4,§9` | **PASS** | test_records.py:179 test_AC_DATA_10_evidence_needs_a_classification_and_source_ref [ok] |
| `AC-DATA-11` | unit | `F-1` | **PASS** | test_records.py:90 test_AC_DATA_11_F1_an_unknown_relation_edge_requires_unknown_evidence [ok]; test_records.py:97 test_AC_DATA_11_F1_with_unknown_evidence_is_accepted [ok] |
| `AC-DATA-12` | unit | `F-2` | **PASS** | test_records.py:104 test_AC_DATA_12_F2_an_inferred_edge_must_be_an_inference [ok]; test_records.py:111 test_AC_DATA_12_F2_with_the_right_classification_is_accepted [ok] |
| `AC-DATA-13` | unit | `F-3` | **PASS** | test_records.py:117 test_AC_DATA_13_F3_severity_moderate_requires_an_alternative [ok]; test_records.py:125 test_AC_DATA_13_F3_severity_high_requires_an_alternative [ok]; test_records.py:133 test_AC_DATA_13_F3_severity_low_does_not_require_an_alternative [ok] |
| `AC-DATA-14` | unit | `F-4` | **PASS** | test_records.py:138 test_AC_DATA_14_F4_an_unobservable_edge_must_be_unknown_and_low [ok]; test_records.py:145 test_AC_DATA_14_F4_with_low_confidence_is_accepted [ok] |
| `AC-DATA-15` | unit | `F-5` | **PASS** | test_records.py:153 test_AC_DATA_15_F5_an_unobservable_edge_requires_dimension_caveats [ok] |
| `AC-DATA-16` | integration | `F-6` | **PASS** | test_integration.py:43 test_AC_DATA_16_a_sealed_forecast_is_returned_by_the_read_path [ok]; test_repository.py:142 test_AC_DATA_16_a_forecast_returned_by_a_read_path_is_sealed [ok] |
| `AC-DATA-17` | unit | `§2.4` | **PASS** | test_records.py:163 test_AC_DATA_17_overall_confidence_is_the_lowest_of_the_material_claims [ok]; test_records.py:170 test_AC_DATA_17_an_overstated_overall_confidence_is_rejected [ok] |
| `AC-DATA-18` | unit | `§12.2` | **DEFERRED** | deferred to Phase 2B - owner's decision, 2026-11-08 |
| `AC-DATA-19` | unit | `E-1` | **PASS** | test_records.py:196 test_AC_DATA_19_E1_an_unknown_status_is_accepted [ok]; test_records.py:200 test_AC_DATA_19_E1_an_issued_command_is_never_completed [ok] |
| `AC-DATA-20` | unit | `E-2` | **PASS** | test_records.py:207 test_AC_DATA_20_E2_a_blocked_execution_records_the_error_type [ok]; test_records.py:212 test_AC_DATA_20_E2_distinguishes_plugin_block_from_tool_error [ok]; test_records.py:220 test_AC_DATA_20_E2_an_unknown_error_type_is_rejected [ok] |
| `AC-DATA-21` | unit | `§8.1,§8.2` | **PASS** | test_repository.py:60 test_AC_DATA_21_tool_arguments_are_stored_only_as_digests [ok] |
| `AC-DATA-22` | unit | `O-2` | **PASS** | test_records.py:252 test_AC_DATA_22_O2_an_observed_observation_requires_an_evidence_ref [ok] |
| `AC-DATA-23` | unit | `O-1` | **PASS** | test_records.py:259 test_AC_DATA_23_O1_unverified_forces_not_verifiable_or_not_applicable [ok]; test_records.py:265 test_AC_DATA_23_O1_unverified_accepts_not_verifiable [ok] |
| `AC-DATA-24` | integration | `C-1` | **PASS** | test_integration.py:71 test_AC_DATA_24_the_forecast_is_unchanged_after_the_outcome [ok]; test_repository.py:166 test_AC_DATA_24_a_comparison_references_the_forecast_that_existed [ok] |
| `AC-DATA-25` | unit | `C-2` | **PASS** | test_records.py:288 test_AC_DATA_25_C2_counts_must_equal_the_item_counts [ok]; test_records.py:296 test_AC_DATA_25_C2_the_sum_of_counts_must_equal_the_item_count [ok] |
| `AC-DATA-26` | unit | `C-3` | **PASS** | test_records.py:304 test_AC_DATA_26_C3_an_unexpected_item_has_a_null_forecast_ref [ok]; test_records.py:312 test_AC_DATA_26_C3_an_unexpected_item_needs_a_non_null_observed_ref [ok] |
| `AC-DATA-27` | unit | `C-4` | **PASS** | test_records.py:319 test_AC_DATA_27_C4_forecast_ref_kind_alternative_is_rejected [ok] |
| `AC-DATA-28` | unit | `C-5` | **PASS** | test_records.py:327 test_AC_DATA_28_C5_no_unexpected_item_requires_the_note_to_say_so [ok]; test_records.py:338 test_AC_DATA_28_C5_is_accepted_with_the_note [ok] |
| `AC-DATA-29` | unit | `C-6` | **PASS** | test_coverage_gaps.py:93 test_AC_DATA_29_a_comparison_records_whether_each_unknown_dimension_was_resolved [ok]; test_coverage_gaps.py:114 test_AC_DATA_29_an_unresolved_dimension_is_recorded_as_unresolved [ok] |
| `AC-DATA-30` | unit | `§10 (M-6,M-7)` | **PASS** | test_serialization.py:23 test_AC_DATA_30_every_envelope_path_maps_to_exactly_one_storage_location [ok]; test_serialization.py:30 test_AC_DATA_30_the_mapping_covers_the_specification_table [ok]; test_serialization.py:41 test_AC_DATA_30_there_is_no_reverse_converter [ok]; test_serialization.py:52 test_AC_DATA_30_every_mapped_table_exists_in_the_schema [ok] |
| `AC-DATA-31` | unit | `§10 (M-8)` | **PASS** | test_serialization.py:60 test_AC_DATA_31_the_json_is_sorted_and_compact [ok]; test_serialization.py:64 test_AC_DATA_31_the_same_input_produces_the_same_output [ok]; test_serialization.py:69 test_AC_DATA_31_the_row_serialisation_uses_the_ddl_column_order [ok]; test_serialization.py:75 test_AC_DATA_31_an_envelope_serialises_deterministically [ok] |
| `AC-DATA-32` | static | `§10 (M-9)` | **DEFERRED** | deferred to Phase 2C - owner's decision, 2026-11-08 |
| `AC-DATA-33` | unit | `§10 (M-10)` | **PASS** | test_serialization.py:90 test_AC_DATA_33_the_hash_is_computed_over_the_rows_not_the_envelope [ok] |
| `AC-LLM-05` | static | `LLM-4` | **DEFERRED** | deferred to Phase 2C - owner's decision, 2026-11-08 |
| `AC-LLM-06` | static | `LLM-6` | **DEFERRED** | deferred to Phase 2B - owner's decision, 2026-11-08 |
| `AC-PATH-20` | unit | `PATH-1,PATH-4,M-3` | **PASS** | test_repository.py:101 test_AC_PATH_20_the_authorized_root_is_never_persisted_verbatim [ok] |
| `AC-PATH-22` | unit | `PATH-3` | **PASS** | test_repository.py:117 test_AC_PATH_22_the_digest_is_stable_across_writes [ok] |
| `AC-PRIV-01` | unit | `PR-1` | **PASS** | test_redaction.py:58 test_AC_PRIV_01_a_secret_in_a_free_text_field_never_reaches_the_database [ok] |
| `AC-PRIV-02` | unit | `PR-1` | **PASS** | test_redaction.py:78 test_AC_PRIV_02_a_raising_redactor_prevents_the_write [ok] |
| `AC-PRIV-03` | static | `PR-2` | **PASS** | test_coverage_gaps.py:245 test_AC_PRIV_03_the_repository_is_the_only_write_path [ok]; test_coverage_gaps.py:253 test_AC_PRIV_03_no_other_module_writes_to_the_database [ok] |
| `AC-PRIV-05` | unit | `§8.2` | **PASS** | test_redaction.py:65 test_AC_PRIV_05_no_credential_is_persisted_in_any_field [ok] |
| `AC-PRIV-19` | unit | `§8.5` | **PASS** | test_redaction.py:47 test_AC_PRIV_19_the_cap_is_applied_after_redaction [ok]; test_redaction.py:91 test_AC_PRIV_19_an_over_long_field_is_truncated_with_the_marker [ok]; test_redaction.py:98 test_AC_PRIV_19_the_cap_matrix_is_applied_per_field [ok] |
| `AC-PRIV-22` | static | `§8.2 (M-4)` | **PASS** | test_redaction.py:112 test_AC_PRIV_22_the_package_never_reads_a_credential_file [ok]; test_redaction.py:134 test_AC_PRIV_22_the_environment_is_never_read [ok] |
| `AC-SEPR-01` | static | `§2.5,§2.6,PD-6` | **PASS** | test_schema.py:29 test_AC_SEPR_01_the_two_records_are_separate_tables_with_separate_prefixes [ok] |
| `AC-SEPR-02` | static | `§2.7` | **PASS** | test_schema.py:39 test_AC_SEPR_02_there_is_no_foreign_key_between_the_two_records [ok] |
| `AC-SEPR-03` | static | `§2.7` | **PASS** | test_coverage_gaps.py:208 test_AC_SEPR_03_there_is_no_merge_operation [ok]; test_coverage_gaps.py:226 test_AC_SEPR_03_the_two_records_have_distinct_identifier_prefixes [ok] |
| `AC-SEPR-11` | unit | `PD-1` | **PASS** | test_repository.py:23 test_AC_SEPR_11_a_supersedes_chain_appends_and_preserves_the_prior_row [ok] |
| `AC-SEPR-12` | unit | `§2.7` | **PASS** | test_repository.py:46 test_AC_SEPR_12_a_rejected_decision_needs_no_authorization_row [ok] |
| `AC-STORE-01` | unit | `§3.3` | **PASS** | test_triggers.py:67 test_AC_STORE_01_the_first_seal_succeeds [ok]; test_triggers.py:74 test_AC_STORE_01_a_second_seal_is_rejected [ok] |
| `AC-STORE-02` | unit | `§3.3` | **PASS** | test_triggers.py:79 test_AC_STORE_02_the_only_permitted_update_is_the_seal [ok]; test_triggers.py:83 test_AC_STORE_02_a_content_hash_change_is_rejected [ok] |
| `AC-STORE-03` | unit | `§3.3` | **PASS** | test_triggers.py:87 test_AC_STORE_03_unsealing_is_rejected [ok] |
| `AC-STORE-04` | unit | `§3.3` | **PASS** | test_triggers.py:92 test_AC_STORE_04_a_multi_column_tamper_is_rejected_in_one_statement [ok] |
| `AC-STORE-05` | unit | `§3.3` | **PASS** | test_triggers.py:98 test_AC_STORE_05_delete_is_always_rejected [ok] |
| `AC-STORE-06` | unit | `§3.3` | **PASS** | test_triggers.py:101 test_AC_STORE_06_an_insert_after_the_seal_is_rejected [ok] |
| `AC-STORE-07` | unit | `§3.3` | **PASS** | test_triggers.py:111 test_AC_STORE_07_a_child_update_is_rejected [ok]; test_triggers.py:120 test_AC_STORE_07_a_child_delete_is_rejected [ok] |
| `AC-STORE-08` | unit | `§3.3,§11` | **PASS** | test_coverage_gaps.py:133 test_AC_STORE_08_the_family_uses_raise_abort [ok]; test_coverage_gaps.py:139 test_AC_STORE_08_the_family_uses_scalar_subqueries_in_when_clauses [ok]; test_coverage_gaps.py:148 test_AC_STORE_08_the_family_executes_on_the_installed_sqlite [ok] |
| `AC-STORE-09` | unit | `§3.3` | **PASS** | test_repository.py:148 test_AC_STORE_09_the_content_hash_is_computed_before_the_header_insert [ok] |
| `AC-STORE-10` | integration | `§3.3` | **PASS** | test_integration.py:58 test_AC_STORE_10_an_unsealed_forecast_is_invisible [ok]; test_repository.py:134 test_AC_STORE_10_an_unsealed_forecast_is_invisible_to_every_read_path [ok] |
| `AC-STORE-11` | static | `§3.4` | **PASS** | test_repository.py:75 test_AC_STORE_11_there_is_no_write_path_from_the_outcome_side_to_a_forecast [ok]; test_static_audits.py:44 test_AC_STORE_11_no_outcome_side_write_reaches_a_forecast_table [ok]; test_static_audits.py:65 test_AC_STORE_11_the_repository_has_no_forecast_write_on_the_outcome_side [ok] |
| `AC-STORE-12` | unit | `§3.4` | **PASS** | test_triggers.py:172 test_AC_STORE_12_every_observation_table_rejects_update_and_delete [ok] |
| `AC-STORE-13` | unit | `AUTH-12,§3.4` | **PASS** | test_triggers.py:265 test_AC_STORE_13_a_resolved_authorization_is_immutable [ok] |
| `AC-STORE-14` | unit | `PD-1,§3.4` | **PASS** | test_triggers.py:290 test_AC_STORE_14_a_product_decision_is_append_only [ok] |
| `AC-STORE-15` | static | `§3.5` | **PASS** | test_repository.py:88 test_AC_STORE_15_exactly_one_write_method_per_table [ok]; test_static_audits.py:82 test_AC_STORE_15_every_table_has_exactly_one_write_method [ok] |
| `AC-STORE-16` | unit | `§3.1` | **PASS** | test_migrations.py:110 test_AC_STORE_16_the_path_is_resolved_from_the_hermes_home_on_every_call [ok] |
| `AC-STORE-17` | unit | `§3.1` | **PASS** | test_coverage_gaps.py:169 test_AC_STORE_17_the_plugin_requests_wal_and_records_the_observed_mode [ok]; test_coverage_gaps.py:186 test_AC_STORE_17_a_delete_mode_is_not_an_error [ok]; test_coverage_gaps.py:202 test_AC_STORE_17_the_observed_mode_is_recorded [ok] |
| `AC-STORE-18` | unit | `§3.7` | **PASS** | test_migrations.py:36 test_AC_STORE_18_a_newer_database_requires_read_only [ok]; test_migrations.py:46 test_AC_STORE_18_applying_to_a_newer_database_raises [ok] |
| `AC-STORE-19` | unit | `§3.7` | **PASS** | test_migrations.py:23 test_AC_STORE_19_the_schema_version_is_recorded [ok]; test_migrations.py:26 test_AC_STORE_19_applying_twice_is_idempotent [ok]; test_migrations.py:56 test_AC_STORE_19_a_failing_migration_rolls_back [ok] |
| `AC-STORE-20` | unit | `§3.6` | **PASS** | test_migrations.py:79 test_AC_STORE_20_no_automatic_deletion_occurs [ok]; test_migrations.py:94 test_AC_STORE_20_the_store_grows_with_record_count_not_field_size [ok] |

## The deferred criteria

| Criterion | Destination | Why |
|---|---|---|
| `AC-DATA-18` | **Phase 2B** | The copy lint on a generated summary. The lint is implemented (`consequence_map/domain/copy.py`) and tested, but the criterion's own subject — a summary the plugin actually generates — is Phase 2B's work. |
| `AC-DATA-32` | **Phase 2C** | "The Desktop layer never references a table name" is a grep of the Desktop source. There is no Desktop half until Phase 2C. The Phase 2A audit that stands in for it is in `tests/test_static_audits.py`. |
| `AC-LLM-05` | **Phase 2C** | The manifest is a Phase 2C packaging artefact. The Phase 2A part — an empty production dependency inventory — is implemented and tested. |
| `AC-LLM-06` | **Phase 2B** | The config schema is implemented and tested (`use_inference` defaults to `false`), but the setting is only exercised when the plugin's inference path exists, which is Phase 2B. |

## The split criterion

| Criterion | 2A half | 2B half |
|---|---|---|
| `AC-DATA-06` | **PASS** — a `FILESYSTEM` target must carry a non-empty `paths` list (P-2); a non-`FILESYSTEM` target is never rejected for lacking a path (P-3). | Effective path containment, path-traversal protection, and the guarantee that access does not exceed the authorized roots, with dedicated security tests. |

**DECISÃO A (owner, 2026-11-08) settles this split.** Phase 2A validates the *shape and semantics* of a target. It does **not** claim that validation guarantees effective path containment, and no Phase 2A evidence may be presented as a containment guarantee.

## What a PASS means here, and what it does not

| A PASS asserts | A PASS does **not** assert |
|---|---|
| The behaviour was **executed** against a real SQLite database in a temporary directory, and the assertion held. | That the plugin works. No plugin was created. |
| The test suite is hermetic: no network, no Hermes import, deterministic. | That the guarantee holds in the product. It holds in a database, under test. |
| The static audits are mechanical scans of the source, executed. | That the Desktop, the approval hooks or the escalation protocol work. Those are 2B and 2C. |
| The privacy guarantees hold at the **write boundary** — redaction, caps, digest-only tool arguments. | That they hold end-to-end, including the model input. The egress boundary is 2B. |
| The path rule holds — the authorized root is never persisted verbatim, only a digest. | That path containment holds. That is 2B (DECISÃO A). |
