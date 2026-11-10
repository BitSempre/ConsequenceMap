# ConsequenceMap — Phase 2A Manifest

**Project:** ConsequenceMap — Decision Intelligence for AI Agents
**Phase:** 2A — Domain model and storage layer
**Date:** 2026-11-08
**Project root:** `C:\Users\Utente\Desktop\ConsequenceMap\`

**Verdict: READY WITH CONDITIONS.** 214 tests, 0 failures, 0 errors. 63 criteria PASS, 1 PASS (2A half), 4 DEFERRED, 0 FAIL.

---

## 1. The delivery

| File | Bytes | SHA-256 |
|---|---|---|
| `consequence_map/__init__.py` | 354 | `c5b92176fa8b70da9ad48ecca5d84cac5425effb71dd6e63aeae02c2f234b68d` |
| `consequence_map/config.py` | 2,408 | `aa4766508174f71023cd8d6a54d5b7dcf4c45ca07c786b299ff815320f5eb52f` |
| `consequence_map/dependencies.py` | 514 | `3fc11317a64113776e916aaec38d30b6bfbaaa177da5a687b834efcc3720ba11` |
| `consequence_map/domain/__init__.py` | 155 | `8d9cfc8d331a2718f8b2e3f655c4276411ad9478a42bf0018d0b91888675c5a9` |
| `consequence_map/domain/copy.py` | 1,624 | `bd09d066c036e43a974555ad6624026e96410d359b10f00b35a7350b20f9ba5a` |
| `consequence_map/domain/enums.py` | 6,815 | `8c94af37f3434514175c13c2c709508f11dc9e405e3228f2304199b46d3594ae` |
| `consequence_map/domain/records.py` | 31,915 | `414579aabe042fac85a1a149e6606753648178eb04c1f9dc104a0ae8190c5aa9` |
| `consequence_map/domain/serialization.py` | 5,813 | `13f86d77215162a3eb910b513b100aee3322931401fc2cd666abefec5389295e` |
| `consequence_map/domain/validation.py` | 8,037 | `b32de602aa5fd6c320c9ef02c24c742c67a23a129d4c4533ed7697527d10e3bd` |
| `consequence_map/redaction/__init__.py` | 76 | `97b7c152fe11326d6cb9ff56bf904d2102fac9495b8c73ca6a2717bcdef079ee` |
| `consequence_map/redaction/boundary.py` | 5,998 | `2c31f9a3ecc508dc8a2c3086d43fccbd1a4f38a98293092d4150a27675ffed1d` |
| `consequence_map/storage/__init__.py` | 145 | `2631b1f54f763dc4da16afd9395ab7cde4ee61c952568d0b1f8e0a30d5188fb7` |
| `consequence_map/storage/db.py` | 6,311 | `38df9a61bfba2c8df77de7078942c8a4a8e52f094123a3a39f1b085fdb2daf3a` |
| `consequence_map/storage/migrations.py` | 3,616 | `f2c3a01debeebb144e3dc9ca286967333d1c4a1d2e0ae88a14191017022af141` |
| `consequence_map/storage/repository.py` | 19,202 | `99747f7b3eae15e7070b85d3a7dd324d2112a283195f7e7122f569ccdefc438a` |
| `consequence_map/storage/schema.py` | 10,964 | `d4b1ab95e078cf13f9a2fee1b6793259b2338d0c46e893c345186b55bad22962` |
| `consequence_map/storage/triggers.py` | 5,980 | `8e3d389470b0ff887a2aa055f7adfaf210fd058f04c626e2cc05a23c6fd88b87` |
| `consequence_map/tests/__init__.py` | 74 | `64a2edfd852e861547c3a3b3434f02bc9a83027fed53924c4c9cb668551869d6` |
| `consequence_map/tests/fixtures.py` | 5,469 | `65c6ec2ebd6401316903fc3494cf68142f64a79cbc4db337a54594fc2c71598d` |
| `consequence_map/tests/test_coverage_gaps.py` | 12,540 | `1cbd85e6f7b88423a4f8c7a2eda024207dfeeb98fed6386621dda1c2335aca8f` |
| `consequence_map/tests/test_enums.py` | 2,496 | `05e44c0001895109aa4921e17010cd9b6196fd8d07780317fd87f995b0caab22` |
| `consequence_map/tests/test_import_audit.py` | 7,207 | `5fae8e8a9eb5295ab7b125481e9a189d616f611dbfe921d5091a32ae60333f8e` |
| `consequence_map/tests/test_integration.py` | 8,113 | `57222fcb239818b014a73ec4ae5f6915c36fb95f316041f9c71a5c927efcdfc0` |
| `consequence_map/tests/test_migrations.py` | 5,268 | `efafa09cbdf822988cb670a6d00ddb6c1876f030b0f67027ad4f04a4bef0a8ff` |
| `consequence_map/tests/test_records.py` | 21,145 | `6aa583dd3321467794408494161f525e3663a031a2edf9cb71c4c56c022b9988` |
| `consequence_map/tests/test_redaction.py` | 7,095 | `a83e265340bfe998deb03e8bc38b614fab2ac8be4200e4ae0af1afc03041f5e3` |
| `consequence_map/tests/test_repository.py` | 9,386 | `04e8784c7c3e6faf1b32b6fe33263228ea8e4e4c0167428d1c01cf8207876265` |
| `consequence_map/tests/test_schema.py` | 3,603 | `9e9dd0b4eee9f496efa40076eb7c46900be4ba25d0267c14e8bf0686c1364c77` |
| `consequence_map/tests/test_serialization.py` | 5,042 | `6a68169b80e21d5a493173751f8b5b7343cc203ced13625ffdb47de9fa0d2c87` |
| `consequence_map/tests/test_static_audits.py` | 10,228 | `011998b96b73d9b5a3778327ddbdc19107d5b8bf305ad42022b361bb191d450d` |
| `consequence_map/tests/test_triggers.py` | 14,617 | `4ddaef60b9d0283c01a8d6c33aabe54063b3621a199e7d7e53552962cc142794` |
| `consequence_map/tests/test_validation.py` | 4,537 | `210510be1b617dc7611fbae5364ff9d3abd077c0d0e3ffe7191bc9591928122c` |
| `docs/PHASE-2A-CRITERIA-MATRIX.md` | 17,755 | `e93bc75c6f6553f4c2fae5df295432f28282d0e0aad9488b91f42c9d82a4b10e` |
| `docs/PHASE-2A-IMPLEMENTATION-REPORT.md` | 17,220 | `09345dad876630b47ec1887a7a22c25b41a40b96f686ef766942abdbbe2e1287` |
| `evidence/_runner.py` | 809 | `c012049121a1974bb8eb0adc7ce42f46742aa04306bfb392de2de67b2531905a` |
| `evidence/criteria-matrix.json` | 37,700 | `ed8cf3bef3578413f1a4c1482250b050533c75ba282a3bc783b57c0cce1874d6` |
| `evidence/criterion-test-map.json` | 18,950 | `d54cb955a8489e36174159cebc38807e6dd904a4ec003c2ba51f611e1986d352` |
| `evidence/determinism-check.json` | 52,512 | `22a1cfe096e7a25568da7b95b09e9fe924c16c1d7d626e9bf1ac22d75a100d54` |
| `evidence/test-status.json` | 25,789 | `fc15b759d67e45e7ee967a7ce77c8addae82a01a81b439693f56b8b2d32136b8` |

**39 files.** Every SHA-256 was computed from the file on disk at manifest generation time.

---

## 2. The test evidence

| File | What it holds |
|---|---|
| `evidence/test-status.json` | The status of every one of the 214 tests. |
| `evidence/criteria-matrix.json` | The 68 criteria with their state, their layer and their evidence. |
| `evidence/criterion-test-map.json` | The criterion-to-test map, with file and line. |
| `evidence/determinism-check.json` | Two consecutive runs of the suite, compared test by test. |
| `evidence/_runner.py` | The runner that produces the machine-readable evidence. |

**Determinism, measured:** two consecutive executions produced **identical** results for all 214 tests — `True`.

---

## 3. The documentation

| File | Purpose |
|---|---|
| `docs/PHASE-2A-IMPLEMENTATION-REPORT.md` | What was built, the defects found and fixed, the technical decisions, the verdict. |
| `docs/PHASE-2A-CRITERIA-MATRIX.md` | The 68 criteria with state and evidence. |

---

## 4. The historical deliveries, preserved

**Every historical artefact was opened read-only and is preserved byte-for-byte.** The three ZIPs carry their declared SHA-256 values, recomputed and confirmed.

| File | Bytes | SHA-256 | Status |
|---|---|---|---|
| `ConsequenceMap-Phase-1.6-Documents.zip` | 124,466 | `d55863b071677f8cb27809fc4a6e703a3579bc3891a5d175626e1d3a2a464d03` | unchanged |
| `ConsequenceMap-Phase-1.8-Corrections.zip` | 139,590 | `50ecbae74ddfae773d61270cdb62e834384685b0f65709cc25c26a253d80a5ec` | unchanged |
| `ConsequenceMap-Phase-1.9-Triage-and-Phase-2A-Proposal.zip` | 21,529 | `a735d83cda2436f54818f3a183c30d67638fa5008aa26d6f986d147e00ff94fc` | unchanged |
| `PHASE-1.10-INDEPENDENT-TECHNICAL-REVIEW.md` | 36,471 | `c58d79c610686da29ecfbae1ad6f8bce8214c4280faf1f35706b74794b3e64cd` | present |
| `PHASE-1.10-CRITERIA-REVIEW.md` | 22,621 | `3a3c1e93da0b80931d8b35d3ffffef0f72672fba64cb2e5129b2d9e20a940bb9` | present |
| `PHASE-1.10-DECISIONS-RECOMMENDATION.md` | 25,592 | `aff46c98a8ff83c4cc7b5afeef119fea3d56552a139ff2403e489a3bcff07d74` | present |
| `PHASE-1.10-REVIEW-MANIFEST.md` | 3,999 | `9a6b9a1234b043ed371009b1e7265ce778c18b61a92eaa4e132e1d82e28e5a35` | present |
| `PHASE-1.11-PHASE-2A-PROPOSAL-v1.1.md` | 68,629 | `b9feb5a3ecc372b4e5c88c6238b5aeca7a47c88db22964da1533e720199c6205` | present |
| `PHASE-1.11-CORRECTIONS-REPORT.md` | 23,383 | `0c8d40956b4ee3f271cf4c7e9d0aa55739edfd0797dbdd84be3f0644823173c9` | present |
| `PHASE-1.11-DECISIONS-REGISTER.md` | 15,161 | `f8a93d58d7d9eedf1b0ce1576252612bf74950b34db8ca4738577d60235dfb7e` | present |
| `PHASE-1.11-VALIDATION-REPORT.md` | 16,250 | `7c0a66b8907c6ac41bc75062419467aed4250f670969b57e2ed3a4c030e4aaa5` | present |
| `PHASE-1.11-DIFF-REPORT.md` | 5,690 | `fb1859342b5403f4a4c7767cb1a0575100449e1880520ac7e57c24d42ca2e977` | present |
| `PHASE-1.11-MANIFEST.md` | 6,862 | `339f3441037f0a2e9b64c4315cfb8fb350aa86414507a463e718509cc42c18aa` | present |

---

## 5. Scope compliance

| The authorisation did **not** permit | Status |
|---|---|
| Creating or publishing Pull Requests | **Not done.** |
| Git commits or pushes | **Not done.** No Git operation was performed on any file. |
| Publishing versions or releases | **Not done.** |
| Publishing the plugin in the Hermes catalogue | **Not done.** No plugin directory was created. |
| Hackathon submissions | **Not done.** |
| Publishing on social networks | **Not done.** |
| Changing global Hermes configuration | **Not done.** |
| Changing ACLs, system permissions or global hooks | **Not done.** |
| Exposing tokens, credentials or private data | **Not done.** The suite reads no environment variable, opens no credential file and contacts no network. |
| Modifying the Phase 1.6, 1.8, 1.9, 1.10 or 1.11 deliveries | **Not done.** The Phase 1.11 proposal and decisions register were updated **as the owner instructed** — to record DECISÃO A and DECISÃO B — and nothing else in them was touched. |

---

## 6. Reproducing every result in this manifest

```
cd C:\Users\Utente\Desktop\ConsequenceMap
python -m unittest discover -s . -p "test_*.py" -t .
```

Expected: `Ran 214 tests` and `OK`.

```
python evidence\_runner.py
```

Expected: a JSON block with `total: 214, failures: 0, errors: 0`.

---

**Phase 2A is complete and ready for review. Phase 2B is NOT authorized.**
