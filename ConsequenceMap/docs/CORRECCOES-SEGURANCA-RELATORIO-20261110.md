# ConsequenceMap — Duas correcções de segurança antes do commit

**Data:** 10 de novembro de 2026
**Branch:** `feature/platform-v1` · **HEAD:** `5920406` (58 commits, **sem commit**)
**Autorização:** Souza — exclusivamente (A) fail-closed da política e (B) exposição do contador de falhas
**Backup:** `C:/Users/Utente/AppData/Local/hermes/cache/scratch/cm-backup-pre-fix-20261110_231519`
(manifesto: `docs/BACKUP-MANIFEST-CORRECOES-20261110.json`)
**Diffs:** `docs/CORRECCOES-SEGURANCA-DIFFS-20261110.diff`

---

## 1. Correcção A — a política de reparação é fail-closed

### O que mudou

| Ficheiro | Mudança |
|---|---|
| `quality_guardian/config.py` | `DEFAULT_AUTO_REPAIR = True` → **`False`**; docstring de `repair_policy()` reescrito para dizer que *"fails safe"* significa **capacidade suspensa** |
| `quality_guardian/tests/isolated.py` | `make_isolated_project()` escreve uma **política explícita** `{"auto_repair": true}` dentro da raiz temporária descartável |
| `quality_guardian/tests/test_repair_policy.py` | **NOVO** — 11 testes comportamentais |

**Nenhum fallback permissivo sobrevive.** Todas as branches de `repair_policy()`
resolvem para `DEFAULT_AUTO_REPAIR`, que é agora `False`:

| Branch | Antes | Agora |
|---|---|---|
| ficheiro ausente (`OSError`) | `True` (permite) | **`False`** (recusa) |
| JSON inválido (`ValueError`) | `True` (permite) | **`False`** (recusa) |
| política não é um objecto | `True` (permite) | **`False`** (recusa) |
| chave `auto_repair` ausente | `True` (permite) | **`False`** (recusa) |
| `auto_repair` não booleano | `True` (permite) | **`False`** (recusa) |
| `auto_repair: false` explícito | recusa | recusa |
| `auto_repair: true` explícito | permite | **permite — só na sua própria raiz** |

### Matriz medida

```
1. politica AUSENTE                        -> recusada
2. politica MALFORMADA (json invalido)     -> recusada
3. politica MALFORMADA (nao e objecto)     -> recusada
4. auto_repair NAO-BOOLEAN (string)        -> recusada
5. politica EXPLICITA false                -> recusada
6. politica EXPLICITA true (raiz isolada)  -> PERMITIDA
   projecto real                           -> recusada
```

### A política real não foi tocada

`quality_guardian/state/repair-policy.json`: `auto_repair: false`, sha256
`52f60c0afb16746a54c32a31b96c53f64eaa48ff074641966ec610f5c6c3b129` — **idêntico
antes e depois**.

### O teste G06 continua a ser significativo

`G06ReRunTest` continua a afirmar, com comportamento:
`applied` é verdade · houve re-execução de testes · houve **mais de uma** ·
o ficheiro **já não tem** os espaços a mais. Com a política explícita na raiz
isolada, o ciclo aplica a reparação, re-executa e verifica o ficheiro — a
afirmação continua a ser real, não um tautologia.

---

## 2. Correcção B — o contador de falhas do audit sink é visível

| Ficheiro | Mudança |
|---|---|
| `consequence_map/hooks.py` | `AuthorizationSink.__init__` define `self.failures = 0`; novo `_sink_failures()` lê o contador de forma tolerante; `on_command("status")` emite `"Audit sink failures this session: %d"` |
| `consequence_map/tests/test_audit_sink_failures.py` | **NOVO** — 7 testes comportamentais |

O contador é **lido, nunca reiniciado, nunca ocultado**. Um sink que não o
mantenha reporta `0` em vez de partir o comando de status.

**Nada mais foi tocado:** nem a cadeia de auditoria, nem o mecanismo de
autorização, nem a semântica de escrita do sink. O diff de `hooks.py` é de
**+33 linhas**, todas de exposição.

---

## 3. Resultados dos testes (projecto real, códigos de saída reais)

| Suite | Antes desta missão | Agora |
|---|---|---|
| `consequence_map` | 549 PASS (rc=0) | **556 PASS** (rc=0) — +7 novos |
| `consequence_guard` | 134 PASS (rc=0) | **134 PASS** (rc=0) |
| `host_tests` | 2 PASS (rc=0) | **2 PASS** (rc=0) |
| `quality_guardian` | 30 PASS (rc=0) | **41 PASS** (rc=0) — +11 novos |
| Protótipo móvel | 12 PASS (rc=0) | **12 PASS** (rc=0) |
| Demonstração | exit 0 | exit 0 |
| **Total** | 727 PASS | **745 PASS, 0 erros** |

**Ciclo completo do Guardian:** `passed=690 failed=0 errors=0 skipped=0`,
veredicto **PASS** (556 + 134).

### Os testes novos têm dentes (injeccões em cópias isoladas)

| Injecção | Resultado |
|---|---|
| `DEFAULT_AUTO_REPAIR` de volta a `True` | **8 falhas** |
| branch `OSError` devolve `{"auto_repair": True}` | **5 falhas** |
| linha do status removida | **4 falhas** |
| contador reiniciado na leitura | **2 falhas** |
| `self.failures += 1` removido | **3 falhas** |

---

## 4. As quatro regressões continuam a ser detectadas

| Injecção | Selecção | Detectado? |
|---|---|---|
| `consequence_guard/crypto.py`: verificação Ed25519 → `return True` | 5 módulos | **Sim — 4 falhas** |
| `consequence_map/hooks.py`: regressão EC-7 | 5 módulos | **Sim — 7 erros** |
| `consequence_map/correlation.py`: EC-7 removido | 5 módulos | **Sim — 3 falhas** |
| a primeira, medida pelo **ciclo completo** | — | **Sim — 7 falhas**, veredicto FAIL |

---

## 5. Auditoria independente

Um agente **read-only** (sem permissão de escrita) auditou as duas correcções:

| Correcção | Veredicto |
|---|---|
| **A — política fail-closed** | **CORRECTAMENTE IMPLEMENTADA** |
| **B — contador visível** | **CORRECTAMENTE IMPLEMENTADA** |

Mediu por conta própria: `quality_guardian` **41/41 PASS** (7,84 s),
`consequence_map` **556/556 PASS** (76,5 s), política real byte-idêntica ao HEAD
com o sha256 esperado, e as injecções de defeito em cópias isoladas.
**Nenhum defeito remanescente identificado.**

### Uma secção do relatório do auditor está invertida

O auditor concludes que *"as duas correcções estão completas e verificadas"* —
correcto — mas, na secção 3 e nas "Immediate Action Required", escreve que é
necessário **injectar** as regressões em `consequence_guard/crypto.py` e
`consequence_map/correlation.py`, e apresenta-as como "❌ NOT regressed".

**Está invertido.** As regressões são injectadas **em cópias isoladas, para
medir se o Guardian as detecta** — nunca no projecto real. Ojectivo da
medição é *provocar* a falha, não corrigi-la. O auditor não conseguiu
executar a injecção (o seu próprio `execute_code` terminou com `ERROR`) e
interpretou a ausência da injecção como um estado do projecto.

Estado real do projecto de produção, verificado por mim depois da auditoria:

```
consequence_guard/crypto.py    contem 'public_key.verify(raw_signature, payload)': True
                               contem 'DEFECT INJECTED': False
consequence_map/correlation.py contem 'pending_forecasts=tuple(self._pending)': True
                               contem 'DEFECT INJECTED': False
consequence_map/hooks.py       a chamada correcta esta presente; a linha nao tem 'pending_forecasts'
git diff HEAD -- crypto.py correlation.py  ->  NAENHUM (byte-identicos ao HEAD)
```

**As três regressões são detectadas**, com evidência ANTES/DEPOIS em cópias
isoladas:

| Injecção | Presente antes | Injectada no scratch | Seleccionados | Detectado |
|---|---|---|---|---|
| Ed25519 removido | sim | sim | 5 | **Sim — 4 falhas** |
| EC-7 no `hooks.py` | sim | sim | 5 | **Sim — 7 erros** |
| EC-7 removido do correlator | sim | sim | 5 | **Sim — 3 falhas** |

Nada foi injectado no projecto real. O veredicto final do auditor mantém-se —
as duas correcções estão completas — mas a sua lista de "acções imediatas" não
deve ser executada: seria injectar, de propósito, uma verificação de assinatura
falsa no código de produção.

---

## 6. Integridade

- `auto_repair: false` — sha256 `52f60c0afb16746a54c32a31b96c53f64eaa48ff074641966ec610f5c6c3b129`, **inalterado**.
- Superfícies protegidas (`core/authorization.py`, `paths.py`, `correlation.py`,
  `lifecycle.py`, `self_exclusion.py`, `consequence_guard/crypto.py`, `store.py`,
  `service.py`, `protocol.py`, `policy.py`, `ipc.py`, `recovery.py`, `client.py`,
  `recovery_after_crash.py`): **byte-idênticas ao HEAD**, nenhuma divergência.
- `consequence_map/hooks.py` difere **apenas** pela exposição do contador.
- Nenhuma alteração em criptografia, autorização, executor, nonce, replay ou revogação.
- Nenhum serviço ou plugin instalado; DEC-16 intocado; ZIP e `SHA256SUMS` intocados.
- Nenhum `reset`, `clean`, `checkout`, commit ou push.

---

## 7. Estado Git

```
HEAD 5920406 (58 commits, intocado)        sem commit
M consequence_map/hooks.py
M quality_guardian/{config,guardian,repair,runner}.py
M quality_guardian/tests/isolated.py
M quality_guardian/state/last-seen.json
A consequence_map/tests/test_audit_sink_failures.py
A quality_guardian/tests/test_repair_policy.py
A docs/{CORRECCOES-SEGURANCA-DIFFS,BACKUP-MANIFEST-CORRECOES,PROPOSTAS-*}.*
A quality_guardian/reports/20261110T{214825,222235}Z-manual.{json,md}
untracked: 0
```

---

## 8. Riscos ainda pendentes

1. **A revogação de chaves Ed25519 não propaga** a um verificador já
   construído; `consequence_guard/service.py:455` passa `revoked_key_ids=()`.
   **Não tocada** — fora do âmbito desta autorização.
2. **A cadeia de auditoria não tem API de verificação por recálculo**;
   `audit_head()` devolve o hash armazenado. **Não tocada.**
3. **Custo do ciclo completo:** ~125 s → ~190 s com o dobro de módulos de
   teste. `FULL_TEST_TIMEOUT` = 600 s **por pacote**; margem de ~3×.
4. **Bloqueios de produção** (serviço Windows, plugin, DEC-16,
   `SHA256SUMS.txt`): inalterados, para decisão separada.
