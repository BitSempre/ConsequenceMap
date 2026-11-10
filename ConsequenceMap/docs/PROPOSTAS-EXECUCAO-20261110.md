# ConsequenceMap — Execução das Propostas 1, 2 e 3

**Data:** 10 de novembro de 2026
**Branch:** `feature/platform-v1` · **HEAD:** `5920406` (58 commits, não commitado)
**Autorização:** Souza, 10 de novembro de 2026 — implementação das três propostas
**Backup:** `C:/Users/Utente/AppData/Local/hermes/cache/scratch/cm-backup-pre-20261110_222200`
(manifesto: `docs/BACKUP-MANIFEST-20261110.json`)

---

## 1. Ficheiros alterados

| Ficheiro | Proposta | Linhas |
|---|---|---|
| `quality_guardian/config.py` | 1 + 3 | `MODULE_TO_TESTS` 13→37, `FULL_TEST_SET` 13→45, `module_for_path` aceita o segundo pacote |
| `quality_guardian/runner.py` | 3 | `_module_address()`, endereçamento por pacote, ciclo completo nos dois pacotes, `_parse_counts` soma |
| `quality_guardian/repair.py` | 2 | choke point passa a consultar a raiz recebida |
| `quality_guardian/guardian.py` | 2 | os dois call sites transmitem `root=root` |

**Diffs completos:** `docs/PROPOSTAS-EXECUCAO-DIFFS-20261110.diff`

**Nada fora de `quality_guardian/` foi tocado.** Verificado por `git diff --name-only`:
as únicas alterações estão em `config.py`, `runner.py`, `repair.py`, `guardian.py`
e `state/last-seen.json` (o registo de hash do Guardian, actualizado pelo próprio
ciclo ao registar o novo documento).

---

## 2. Resultados das suites (projecto real, códigos de saída reais)

| Suite | Resultado | rc |
|---|---|---|
| `consequence_map` | **549 PASS** | 0 |
| `consequence_guard` | **134 PASS** | 0 |
| `host_tests` | **2 PASS** | 0 |
| `quality_guardian` | **30 PASS** (era 29 PASS + 1 ERROR) | 0 |
| Protótipo móvel | **12 PASS** | 0 |
| Demonstração móvel | exit 0 | 0 |
| **Total** | **727 PASS, 0 erros** | |

**O erro G06 deixou de existir.** A suite do Guardian passou de 29 PASS + 1 ERROR
para **30 PASS**.

**Ciclo completo do Guardian:** `passed=683 failed=0 errors=0`, veredicto **PASS**
(549 + 134), duração real ~125 s.

---

## 3. Prova de cobertura do Guardian

Antes, uma alteração a `consequence_guard/crypto.py` seleccionava
`['test_static_audits', 'test_import_audit']` — **nenhum teste de segurança**.

| Ficheiro alterado | Selecção antes | Selecção agora |
|---|---|---|
| `consequence_guard/crypto.py` | 2 (nenhum de segurança) | **5** — incl. `test_crypto`, `test_binding`, `test_rfc8032_vectors` |
| `consequence_guard/store.py` | 2 | **5** — incl. `test_store`, `test_recovery` |
| `consequence_guard/service.py` | 2 | **5** — incl. `test_service`, `test_ipc` |
| `consequence_map/hooks.py` | 2 | **5** — incl. `test_phase2b`, `test_independent_review` |
| `consequence_map/paths.py` | 2 | **3** — incl. `test_phase2b` |

`module_for_path('consequence_guard/crypto.py')` devolve agora
`'consequence_guard.crypto'` (antes devolvia `''`).

**Cobertura completa:** os 45 módulos de teste que existem em disco estão
todos no `FULL_TEST_SET` (nenhum de fora, nenhum em falta), e dos 43 módulos de
pacote, **todos os que são módulos reais** têm entrada no mapa. As 6 entradas
restantes são directorios de pacote (`__init__.py`), não módulos. Os módulos de
alto impacto continuam a forçar o conjunto completo (45 módulos).

Duas entradas foram acrescentadas depois da primeira validação, por lacuna
detectada na verificação de consistência: `consequence_guard.client` (exercitado
por `test_ipc`) e `consequence_guard.recovery_after_crash` (exercitado por
`test_recovery_after_crash` e `test_instance_id`) — sem entrada própria, uma
alteração a esses ficheiros seleccionava apenas os dois módulos sempre-corridos.

---

## 4. Injecções de defeito (apenas em cópias isoladas)

| Injecção | Selecção | Detectado? |
|---|---|---|
| `consequence_guard/crypto.py`: verificação Ed25519 substituída por `return True` | 5 módulos | **Sim — 4 falhas** em `test_crypto` |
| `consequence_map/hooks.py`: regressão EC-7 reintroduzida | 5 módulos | **Sim — 7 erros** (2 `test_independent_review` + 5 `test_phase2b`) |
| `consequence_map/correlation.py`: encaminhamento EC-7 removido | 5 módulos | **Sim — 3 falhas** (2 `test_independent_review` + 1 `test_phase2b`) |
| Mesma injecção Ed25519, medida pelo **ciclo completo** | — | **Sim — 7 falhas**, incluindo `test_a_request_with_a_forged_signature_is_refused` |

Todas as injecções foram repetidas com o mapa final de 37 entradas, com o mesmo
resultado. As cópias isoladas estão em
`C:/Users/Utente/AppData/Local/hermes/cache/scratch/cm-final-inj{1,2,3}/`.

---

## 5. `auto_repair: false` — intacto

```
auto_repair_enabled(None)            -> False   (None resolve para PROJECT_ROOT)
auto_repair_enabled()                -> False
auto_repair_enabled(PROJECT_ROOT)    -> False

escrita no projecto real              -> recusada
escrita num subdirectório             -> recusada
escrita dentro de consequence_map/    -> recusada
escrita num directório sem política   -> recusada (a política real governa)
```

`repair-policy.json`: `auto_repair: false`, sha256
`52f60c0afb16746a54c32a31b96c53f64eaa48ff074641966ec610f5c6c3b129` — **inalterado**.

---

## 6. Defeito encontrado e corrigido durante a execução

O `G03TestSelectionTest` do Guardian reprovou durante a execução: as 13 entradas
Phase 2A originais tinham sido reescritas com o valor como **string** em vez de
lista (`repr()` de uma lista de strings produz uma string entre aspas). Com a
string, `select_tests` iterava sobre os caracteres e não seleccionava nada.

**Correcção:** as 13 entradas foram re-parseadas do backup com `ast.literal_eval`
e reescritas como listas reais. Verificado: as 13 são **byte-a-byte idênticas ao
backup** e as 35 são listas.

Um segundo defeito, encontrado pela mesma via: `_parse_counts` usava `re.search`
e tomato apenas o **primeiro** resumo `Ran N tests` — com dois resumos
concatenados reportava 549 em vez de 683 e podia mascarar uma falha no segundo
pacote. Corrigido para somar todos os resumos.

Este é o argumento a favor de testes comportamentais: o próprio `G03` do Guardian
apanhou a regressão que a inspeção visual do ficheiro não apanharia.

---

## 7. Estado Git

```
HEAD   5920406 (58 commits, inalterado)
staged ConsequenceMap/docs/PROPOSTAS-AUTORIZACAO-20261110.md
staged ConsequenceMap/quality_guardian/reports/20261110T214825Z-manual.json
staged ConsequenceMap/quality_guardian/reports/20261110T214825Z-manual.md
novo   ConsequenceMap/docs/PROPOSTAS-EXECUCAO-DIFFS-20261110.diff
novo   ConsequenceMap/docs/BACKUP-MANIFEST-20261110.json
```

**Sem commit.** Nenhum `reset`, `clean`, `checkout` ou operação destrutiva.

---

## 8. Auditoria independente

Um agente auditor, **sem permissão de escrita no projecto**, auditou as três
propostas depois da correcção do defeito das strings. Veredicto:

| Proposta | Veredicto do auditor |
|---|---|
| PROPOSTA 1 — mapa do Guardian | **CORRECTAMENTE IMPLEMENTADA** — 30/30 PASS, suite completa 683/683 |
| PROPOSTA 2 — `auto_repair: false` | **CORRECTAMENTE IMPLEMENTADA** — política intacta, `write_file_text` levanta `RepairSuspended` |
| PROPOSTA 3 — `consequence_guard` visível | **CORRECTAMENTE IMPLEMENTADA** |

Confirmou por medição própria: `repair-policy.json` com sha256
`52f60c0afb16746a54c32a31b96c53f64eaa48ff074641966ec610f5c6c3b129`; nenhum
ficheiro em `consequence_map/` ou `consequence_guard/` modificado; superfícies
protegidas byte-idênticas ao HEAD; comportamento criptográfico, de autorização,
nonce, replay, revogação e executor inalterado.

**Nenhuma regressão crítica identificada.**

**Evidência da auditoria:** transcript integral preservado em
`C:/Users/Utente/AppData/Local/hermes/cache/scratch/cm-independent-audit-TRANSCRIPT-20261110.log`
(22 624 bytes). As medições que a sustentam: 30/30 PASS na suite do Guardian,
ciclo completo 683/683 em 151,1 s, `_parse_counts` com 683 em dois resumos, hash
da política confirmado, e `git diff --name-only` com nada fora de
`quality_guardian/` e `docs/`.

**Um segundo documento de auditoria existe** —
`C:/Users/Utente/AppData/Local/hermes/cache/scratch/cm-independent-audit-20261110.md`
(12 660 bytes, sha256 `1259303029f3387a5060467d8de8fd8067f222c6002297f2d4c2b1e421ac85d1`).
É **legítimo** — todos os caminhos que cita existem, o hash confere, e o seu
veredicto é o mesmo. **Mas é uma reconstrução documental, não uma medição:**
declara como método *"extracção de evidências de diffs do git, ficheiros de
evidência JSON e markdown"* e apoia-se em relatórios de 8 de Novembro e no
ciclo `20261110T200607Z` — **não** nos ciclos de hoje. Por isso classifica-se
como **corroborante**, e não como auditoria independente: quem o produziu leu
os mesmos ficheiros que eu, não correu as suites. A auditoria que **mediu** é
a do `deleg_bcba66ae`, cujo transcript está preservado acima.

**Nota sobre versões de relatórios de auditoria.** A primeira versão do
documento de auditoria em ficheiro citava ficheiros **inexistentes**
(`tests/guardian/test_guardian_suite.py`, `module_resolver.py`,
`test_generator.py`) — foi **posta em quarentena** como
`REJECTED-fabricated-audit-20261110.md` e **não** foi usada como evidência. A
segunda versão (descrita acima) está limpa e é corroborante, mas é documental.
A regra que daqui se tira: **um relatório de auditoria só vale se os seus
números puderem ser reproduzidos** — e uma reconstrução a partir de
relatórios antigos não substitui uma medição.

### A primeira auditoria (que encontrou o bug das strings) — e uma alegação sua que está errada

A primeira auditoria reportou a Proposta 1 como **INCORRECT** por causa do bug
das strings. **Esse bug foi corrigido** e o veredicto desta auditoria reflecte o
estado anterior à correcção. Estado actual medido:

```
MODULE_TO_TESTS: 37 chaves | valores que NAO sao listas: NENHUM
as 13 Phase 2A identicas ao backup: True
G03TestSelectionTest: Ran 3 tests | OK | rc = 0
linhas '-' no diff para as 13 Phase 2A: 0   (o git nao mostra nenhuma remocao)
```

**Uma alegação sua está factualmente errada.** Escreveu que *"o timeout aplica-se
ao subprocess combinado, não por-package"* e que a suite nova consumiria
~300 s. **Medição directa:**

| Afirmação | Medição | Veredicto |
|---|---|---|
| "o timeout aplica-se ao subprocess combinado" | `timeout=1` → elapsed 1,05 s, `BLOCKED`, o 2.º discover **nunca arrancou** | **Errado** — é por pacote |
| "a suite nova consome ~300 s" | 125 s medidos (124,9 s e 151,1 s em execuções distintas) | **Errado** — é ~125 s |

Cada `subprocess.run(timeout=limit)` recebe o limite **individual**; o segundo
`discover` só corre depois do primeiro terminar, e só corre se o primeiro não
expirar. O pior caso de tempo é 600 s + 600 s = **1200 s**, não 600 s. A
margem real é 125 s contra 600 s por pacote.

A recomendação dele de aumentar `FULL_TEST_TIMEOUT` para 900 s parte do número
errado; com 125 s medidos, os 600 s existentes são suficientes e fica margem de
~4,8×. **Nenhuma alteração foi feita por causa disto.**

---

## 9. Riscos pendentes

1. **WARNING — `self.failures` do audit sink não é exposto.** A contagem é
   incrementada em `consequence_map/hooks.py` mas nunca lida; `on_command("status")`
   não a mostra. O gap de auditoria é invisível ao operador. **Não alterado** por
   esta autorização (fora do âmbito das três propostas).
2. **WARNING — revogação de chaves Ed25519 não propaga.** `KeyRegistry.revoke()`
   não afecta um verificador já construído; `consequence_guard/service.py:455`
   passa `revoked_key_ids=()`. **Não alterado.**
3. **WARNING — verificação da cadeia de auditoria.** `audit_head()` devolve o
   hash **armazenado**; o checkpoint só detecta adulteração do `record_hash` da
   última linha. Não existe API de verificação por recálculo. **Não alterado.**
3b. **WARNING NOVO — fail-open quando a política de reparação está ausente.**
   `config.repair_policy()` devolve `DEFAULT_AUTO_REPAIR = True` quando o
   ficheiro `repair-policy.json` não existe, é ilegível ou está malformado —
   apesar de o docstring dizer *"a malformed policy fails safe"*. Para uma
   capacidade que o proprietário suspendeu, o default seguro seria `False`.
   **Este é pré-existente** (`DEFAULT_AUTO_REPAIR = True` está no HEAD e intacto
   no diff), **mas a Proposta 2 altera o seu alcance**, conforme medido:

   | Cenário | Antes (sem F1) | Depois (com F1) |
   |---|---|---|
   | Ciclo no projecto real (política intacta) | recusado | recusado — **inalterado** |
   | Ciclo numa raiz **sem** ficheiro de política | **recusado** (decidia o `PROJECT_ROOT` real) | **permitido** (decide o default `True`) |

   **Por que isto não é uma falha de produção:** em produção o ciclo corre com
   `root=PROJECT_ROOT` (`guardian.py::Cycle.root`, `default_factory`), que tem a
   política; o ficheiro está *tracked* pelo Git, logo um clone restaura-o; e o
   Guardian só escreve através do choke point, nunca o apaga. Só uma raiz de
   teste isolada sem política fica agora com reparação habilitada — que é
   precisamente o que o G06 precisa para passar.

   **No entanto, o default é fail-open e o docstring afirma o contrário.**
   Correcção mínima proposta (uma constante, `config.py`), **NÃO aplicada —
   fora do âmbito da autorização, que proíbe alterar a política**:
   ```diff
   -    #: The default when the policy file is absent: automatic repair is enabled.
   -    DEFAULT_AUTO_REPAIR = True
   +    #: The default when the policy file is absent: automatic repair is
   +    #: DISABLED. An unreadable policy must not grant a capability the
   +    #: owner suspended — absence of evidence is not permission.
   +    DEFAULT_AUTO_REPAIR = False
   ```
   Aviso: esta mudança **faria o G06 voltar a dar ERROR** (o projecto isolado do
   teste passaria a ter a reparação suspensa). As duas correcções são
   inseparáveis e precisam de ser decididas em conjunto — com o teste ajustado
   para instalar uma política explícita no projecto isolado.
4. **Custo do ciclo completo.** Passou de ~50 s para ~125 s (medido). O
   `FULL_TEST_TIMEOUT` é de 600 s e o `subprocess.run(timeout=limit)` aplica-se
   **a cada chamada** — o timeout é **por pacote, não total**. O pior caso é
   600 s + 600 s = **1200 s**, e não 600 s. Verificado por injecção: com
   `timeout=1`, o ciclo devolve `BLOCKED` e `timed_out=True`, e o pacote que
   expirou não é contado — o resultado é `BLOCKED`, nunca um `PASS` silencioso.
   Margem real: 125 s contra 600 s por pacote. Risco residual: baixo, mas o
   valor não é 600 s — é 1200 s.
5. **Falsos positivos na selecção.** `core/canonical.py` é importado por 13
   testes; uma alteração de uma linha seleccionará 15 módulos. Inerente ao
   grafo de imports. Mitigação disponível (adicionar a `HIGH_IMPACT_MODULES`) —
   **não aplicada**, por não estar autorizada.
6. **Timeout do ciclo completo: 1200 s no pior caso, não 600 s.** O
   `subprocess.run(timeout=limit)` aplica-se a **cada** chamada, e o segundo
   pacote só corre se o primeiro passou. Com 125 s medidos contra 600 s por
   pacote, a margem é confortável; mas o valor a reter é 1200 s, não 600 s. A
   exclusão explícita cabe num `timeout=1` de teste: o ciclo devolve `BLOCKED`
   e `timed_out=True` — nunca um `PASS` silencioso.
