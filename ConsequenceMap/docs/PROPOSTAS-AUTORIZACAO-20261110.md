# PROPOSTAS DE ALTERAÇÃO — Aguardam autorização explícita

**Projecto:** ConsequenceMap · **Branch:** `feature/platform-v1` · **HEAD:** `5920406`
**Data:** 10 de novembro de 2026
**Estado:** nada disto foi aplicado. As duas alterações abaixo estão **verificadas em
cópias isoladas** e à espera de decisão.

---

## PROPOSTA 1 — Alargar o mapa módulo→teste do Quality Guardian

### Problema

`quality_guardian/config.py` mapeia 13 dos 33 módulos de teste. Os módulos da
Phase 2B (`test_phase2b`, `test_independent_review`) e mais 18 **nunca são
seleccionados** por uma alteração nos ficheiros que os exercitam.

### Impacto medido (não é teórico)

Injectei a regressão real do `hooks.py` numa cópia isolada e comparei:

| Mapa | Módulos seleccionados para `consequence_map/hooks.py` | O defeito é detectado? |
|---|---|---|
| Actual (13/33) | `test_import_audit`, `test_plugin_integration`, `test_static_audits` | **Não** — os 3 passam |
| Proposto (33/33) | + `test_phase2b`, `test_independent_review` | **Sim** — 5 erros + 2 falhas |

Este é o ponto cego real que a missão descreve: uma mudança que partia cinco
testes do produto passava o Guardian sem o notar.

### Ficheiros afectados

- `quality_guardian/config.py` — `MODULE_TO_TESTS` e `FULL_TEST_SET`

### ⚠️ Correcção crítica: `MODULE_TO_TESTS` sozinho é um NO-OP

`runner.select_tests()` termina com:

```python
ordered = [m for m in config.FULL_TEST_SET if m in modules]
```

**O resultado é filtrado por `FULL_TEST_SET`.** Um teste acrescentado ao mapa mas
ausente do conjunto é silenciosamente descartado. Confirmei-o empiricamente: com
`consequence_map.hooks -> [test_phase2b, ...]` no mapa e o `FULL_TEST_SET`
intacto, a selecção para `hooks.py` continuava a devolver apenas
`['test_static_audits', 'test_import_audit']`.

**As duas constantes têm de mudar em conjunto.** É o mesmo ficheiro, o mesmo
diff, mas a omissão de uma delas anula inteiramente a outra.

### Mapa proposto

O grafo real de imports foi derivado por **dois métodos combinados**: (a) carregamento
de cada um dos 33 módulos de teste em processo isolado, observando `sys.modules`
— captura imports transitivos e efeitos de `__init__`; (b) caminhada AST de
todos os ficheiros de teste, incluindo corpos de funções — captura imports
dentro de métodos. **Nenhum dos dois é suficiente sozinho**: a análise empírica
perde 10 arestas que só a estática vê; a estática perde 100 que só a empírica
vê. A união fecha as 28. Não há imports dinâmicos (`importlib`, `__import__`)
nos ficheiros de teste ou do pacote, pelo que a cobertura é completa.

Cobertura resultante: **28/28 módulos de pacote cobertos, 0 módulos sem teste.**

```
MODULE_TO_TESTS:  13 -> 28 chaves   (as 13 Phase 2A mantêm-se inalteradas)
FULL_TEST_SET:    13 -> 33 entradas  (a suite inteira)
```

Selecção resultante, verificada em cópia de scratch:

| Ficheiro alterado | Antes | Depois |
|---|---|---|
| `consequence_map/hooks.py` | 2 | **5** |
| `consequence_map/lifecycle.py` | 2 | **4** |
| `consequence_map/paths.py` | 2 | **3** |
| `consequence_map/core/canonical.py` | 2 | **15** |
| `consequence_map/domain/enums.py` | 33 (high-impact) | 33 (inalterado) |

### Custo real (falsos positivos)

Os módulos de fundação puxam suites amplas: `core/canonical.py` é importado por
13 testes e uma alteração de uma linha seleccionaria 233 testes. É
**inerente** à derivação por grafo de imports — o grafo regista *usos*, não
*testes-de*. Não é uma regressão: o mapa actual nunca corre esses testes.
Se o custo se tornar um problema, a correcção é adicionar
`consequence_map.core.canonical` e `consequence_map.core.timeutil` a
`HIGH_IMPACT_MODULES` (que força a suite completa) — **decisão separada, não
incluída aqui para manter a alteração mínima.**

### Nota sobre um falso alarme

Uma auditoria independente reportou que `test_independent_review` (2 erros) e
`test_plugin_integration` (6 erros) estavam **vermelhos** e que o mapa
proposto os exporia. **Verifiquei e é falso.** A partir da raiz do projecto
ambos passam (15 e 14 testes, `OK`). Os erros apareciam porque o teste foi
executado a partir de um directório de scratch sem os módulos `agent` e
`fastapi` no caminho — `No module named 'agent'`, `No module named 'fastapi'`.
É um artefacto do *cwd* da auditoria, não um estado do projecto. A linha
`consequence_map/` na tabela de selecção do relatório do auditor reflecte este
engano e **não foi adoptada**.

### Riscos

- **Falsos positivos:** um módulo que importe outro passa a ser seleccionado
  quando esse outro muda. É o comportamento pretendido, mas aumenta o número
  de testes executados num ciclo. Medido: o ciclo completo passa de 3 a 5
  módulos em `hooks.py`.
- **Falsos negativos:** o grafo é **estático**. Um import dinâmico (`importlib`,
  `__import__`) não aparece. Verifiquei que `consequence_map` **não** usa
  imports dinâmicos para os seus módulos de teste — o grafo é completo para
  o que existe hoje.
- **Custo:** mais testes por ciclo. Aceitável — são testes stdlib, sem rede.

### Reversão

```bash
git checkout -- quality_guardian/config.py
```

Uma linha, sem dependências, sem estado externo.

---

## PROPOSTA 2 — Corrigir o erro G06

### Causa raiz (verificada)

A política de reparação é consultada contra **duas raízes diferentes**:

| Sítio | Consulta | Resultado |
|---|---|---|
| `guardian.py::_attempt_repairs` (o gate) | `config.auto_repair_enabled(root)` — a raiz **do ciclo** | `True` — a raiz isolada do teste não tem política, aplica o *default* |
| `repair.py::write_file_text` (o choke point) | `config.auto_repair_enabled()` — sem argumento, logo `PROJECT_ROOT` | `False` — a política real diz `auto_repair: false` |

O gate passa, a escrita levanta `RepairSuspended`, e `_attempt_repairs` **não
apanha a excepção** — ela escapa do `run_cycle` e o teste regista `ERROR`.

**Não é uma regressão desta missão.** Reproduzi o erro no commit de referência
`c1f4e2c`, extraído para um directório limpo: o mesmo `RepairSuspended`. O
problema existe desde 8 de novembro de 2026.

### Resposta às quatro hipóteses

- **(A) O teste exige uma capacidade desactivada?** Não. O teste quer exercitar
  o caminho de reparação; num projecto isolado, sem política, a reparação está
  habilitada por *default*. O teste está correcto no que pretende verificar.
- **(B) A implementação reporta mal?** Sim, parcialmente. Duas leituras de
  política para raízes diferentes é um defeito de desenho: o gate e o choke
  point **deviam consultar o mesmo sítio**.
- **(C) A classificação do resultado é inadequada?** Sim. `RepairSuspended` é
  uma **decisão de política**, não um erro. Deveria ser registado como
  `repair-capability: NOT_VERIFIED` com a razão — que é exactamente o que
  acontece no projecto real.
- **(D) Regressão efectiva?** Não.

### Solução mínima proposta (F1 — variante *pass-through*)

**Ficheiros:** `quality_guardian/repair.py` + `quality_guardian/guardian.py`
· **4 linhas, 2 ficheiros**

O choke point passa a consultar a política **da raiz que o ciclo já tem** — o
mesmo valor que o gate consultou. Sem derivação de caminho, sem heurísticas,
sem marcadores a escolher.

```diff
--- a/quality_guardian/repair.py
+++ b/quality_guardian/repair.py
-def write_file_text(path: Path, content: str) -> bool:
+def write_file_text(path: Path, content: str, root: Path = None) -> bool:
     """Write the file atomically. Returns True on success.
 
     This is the ONLY function in the Guardian that writes to a project
     source file, so it is the single choke point for the automatic-repair
     capability. When the repair policy suspends automatic repair, every
     write is refused here — whichever path reached it.
+
+    The policy is consulted for the project ROOT the file belongs to. The
+    caller passes the cycle root; when it is omitted the global
+    PROJECT_ROOT is used, which is the owner-controlled policy for the
+    production project.
     """
-    if not config.auto_repair_enabled():
+    if not config.auto_repair_enabled(root):
```

```diff
--- a/quality_guardian/guardian.py
+++ b/quality_guardian/guardian.py
@@ _attempt_repairs
-        if not repair.write_file_text(path, fixed):
+        if not repair.write_file_text(path, fixed, root=root):
@@ _attempt_repairs
-            repair.write_file_text(path, original)
+            repair.write_file_text(path, original, root=root)
```

### Porque esta variante e não a derivação de caminho

Considerei primeiro derivar a raiz a partir do caminho do ficheiro. **A revisão
independente mostrou que essa variante é mais frágil**, e concordo: obriga a
escolher um "marcador" de projecto, e qualquer escolha tem uma armadilha.

Usar `consequence_map/` como marcador abre um buraco: um caminho **dentro** de
`consequence_map/` auto-identificar-se-ia como raiz sem política → *default*
`True` → escrita no pacote real. Usar "contém o ficheiro de política" como
marcador faz o teste isolado falhar (o projecto isolado não tem política →
fallback para `PROJECT_ROOT` → `False` → o teste volta a dar erro).

A variante *pass-through* entrega ao choke point a raiz **que o ciclo já
tem**. Sem marcador, sem fallback, sem ambiguidade. Verifiquei que a propriedade
crítica se mantém nas duas variantes — e que a variante *pass-through* é
estritamente mais simples.

### Porque F1 e não as alternativas

- **F2** (apanhar `RepairSuspended` no `_attempt_repairs`) esconderia a
  divergência entre as duas raízes em vez de a eliminar. Um projecto isolado
  ficaria com a política do projecto real — errado.
- **F3** (pôr `auto_repair: true` na política do projecto isolado do teste)
  testa o caminho de reparação, mas deixa o defeito de desenho intacto: duas
  raízes, duas respostas.
- **F1** elimina a divergência na origem e **não toca no teste**.

### Efeitos no comportamento

| Cenário | Antes | Com F1 |
|---|---|---|
| Ciclo no projecto real (`auto_repair: false`) | reparo recusado | reparo recusado — **inalterado** |
| Ciclo num clone sem política | reparo aplicado | reparo aplicado — **inalterado** |
| Suite do Guardian (30 testes) | 29 PASS + 1 ERROR | **30 PASS** |
| `auto_repair` global | `false` | `false` — **inalterado** |
| Veredito registado no projecto real | WARNING | WARNING — **inalterado** |

Medido nas três variantes (original, A e B), em cópias de scratch:
`original → 29 PASS + 1 ERROR`, `A → 30 PASS`, `B → 30 PASS`; e o `verify` no
projecto real devolve `WARNING` com as mesmas quatro verificações em todas.

### Propriedade crítica de segurança

Verifiquei explicitamente, em cópia isolada, com `auto_repair: false`:

```
auto_repair_enabled(None)                      -> False  (None = PROJECT_ROOT)
ESCRITA NO PROJECTO REAL:                      recusada
ESCRITA NUM SUBDIR DO PROJECTO REAL:           recusada
ESCRITA DENTRO DE consequence_map/:             recusada
ESCRITA NUM DIRECTORIO SEM POLITICA:           recusada (a politica real governa)
CICLO NUMA COPIA COM A POLITICA REAL:          0 propostas aplicadas, registado como
                                              repair-capability: NOT_VERIFIED
```

**Com F1, não existe nenhuma escrita no projecto real com `auto_repair: false`.**
A suspensão continua a ser fail-closed.

### Reversão

```bash
git checkout -- quality_guardian/repair.py quality_guardian/guardian.py
```

4 linhas, 2 ficheiros. Sem estado externo, sem dependências. Expectativa após
reversão: **29 PASS + 1 ERROR** (o G06 volta ao estado pré-fix).

---

## PROPOSTA 3 — Tornar o `consequence_guard` visível ao Guardian

> **Descoberta da auditoria de segurança. É o achado mais grave desta missão e
> não estava na lista original de decisões.**

### O problema

O Guardian não consegue ver **nada** do pacote `consequence_guard/`. Medido:

```
module_for_path('consequence_guard/crypto.py')  -> ''      (string vazia)
module_for_path('consequence_guard/store.py')   -> ''
module_for_path('consequence_guard/service.py') -> ''
```

E, mesmo que o mapa os nomeasse, **o runner não os conseguiria executar**:

```python
# runner.py:84
[sys.executable, "-m", "unittest", f"consequence_map.tests.{module}", "-v"]
```

Os 12 módulos de teste do guard (`test_crypto`, `test_store`, `test_service`,
`test_binding`, `test_ipc`, `test_nonce`, `test_recovery`, …) vivem em
`consequence_guard/tests/` — **não** em `consequence_map/tests/`. A sobreposição
entre os dois pacotes é **zero**. O endereçamento `consequence_map.tests.X`
apontaria para um módulo inexistente.

O ciclo `--full` tem o mesmo problema: faz `unittest discover -s
consequence_map/tests` — **um** pacote.

### Consequência medida

**Os 134 testes do `consequence_guard` — a suite de segurança — nunca são
executados pelo Guardian.** Nem selectivamente, nem no ciclo completo.

Prova por injecção de defeito: substituí a verificação da assinatura Ed25519
em `consequence_guard/crypto.py` por `return True` — o Guard passaria a aceitar
**qualquer** assinatura forjada.

| | Selecção | Resultado |
|---|---|---|
| **Mapa actual** | `['test_static_audits', 'test_import_audit']` | **passa despercebida** — 0 falhas detectadas |
| **Com a Proposta 3** | 5 módulos, incl. `test_crypto` | **4 falhas detectadas** |

Isto é a mesma classe de ponto cego que a Proposta 1 corrige para a Phase 2B,
mas num pacote onde o stakes é o do lado errado: **a suite de segurança não é
verificada pelo verificador**.

### Ficheiros afectados

- `quality_guardian/config.py` — `module_for_path()` aceita `consequence_guard/`;
  `MODULE_TO_TESTS` ganha as 7 chaves do guard; `FULL_TEST_SET` inclui os 12
  módulos de teste do guard.
- `quality_guardian/runner.py` — `_module_address()` escolhe o pacote que
  contém_effectivamente o ficheiro; o ciclo completo corre `discover` nos
  **dois** pacotes.

### Diff (essência)

```diff
--- a/quality_guardian/config.py
+++ b/quality_guardian/config.py
@@ def module_for_path(path) -> str:
     parts = list(rel.parts)
-    if not parts or parts[0] != "consequence_map":
+    if not parts or parts[0] not in ("consequence_map", "consequence_guard"):
         return ""

@@ MODULE_TO_TESTS
+    "consequence_guard.crypto":  ["test_crypto", "test_binding", "test_rfc8032_vectors"],
+    "consequence_guard.store":   ["test_store", "test_recovery", "test_recovery_after_crash"],
+    "consequence_guard.service": ["test_service", "test_binding", "test_ipc"],
+    "consequence_guard.protocol":["test_ipc", "test_binding"],
+    "consequence_guard.policy":  ["test_binding"],
+    "consequence_guard.ipc":     ["test_ipc", "test_instance_id"],
+    "consequence_guard.recovery":["test_recovery", "test_recovery_after_crash",
+                                  "test_review_findings", "test_review_round12"],

@@ FULL_TEST_SET
+    # the 12 modules of consequence_guard/tests
```

```diff
--- a/quality_guardian/runner.py
+++ b/quality_guardian/runner.py
+def _module_address(module: str) -> str:
+    """The dotted address of a test module.
+
+    The project has TWO test packages: ``consequence_map.tests`` and
+    ``consequence_guard.tests``. A module name is not enough to say
+    which one holds it, so the package that actually contains the file
+    wins. The name alone would address the wrong package - or no
+    package at all.
+    """
+    base = config.PROJECT_ROOT
+    for package in ("consequence_map", "consequence_guard"):
+        if (base / package / "tests" / (module + ".py")).exists():
+            return f"{package}.tests.{module}"
+    return f"consequence_map.tests.{module}"

@@ run_test_module
-            [sys.executable, "-m", "unittest", f"consequence_map.tests.{module}", "-v"],
+            [sys.executable, "-m", "unittest", _module_address(module), "-v"],

@@ run_full_suite
+        # The guard's own tests live in a SECOND package. A discover on
+        # consequence_map/tests cannot see them, so the full run has to
+        # cover both or the security suite is simply never executed.
+        proc2 = subprocess.run(
+            [sys.executable, "-m", "unittest", "discover",
+             "-s", str(base / "consequence_guard" / "tests"), "-t", str(base), "-v"],
+            capture_output=True, text=True, timeout=limit, cwd=str(base), env=env,
+        )
```

### Verificado em cópia de scratch

| Verificação | Resultado |
|---|---|
| `module_for_path` para os 3 ficheiros do guard | `consequence_guard.crypto` / `.store` / `.service` |
| Selecção para `consequence_guard/crypto.py` | 5 módulos (incl. `test_crypto`) |
| `test_crypto` pelo runner | 25 PASS · `test_store` 16 · `test_service` 18 |
| Suite do Guardian | 30 testes, **o único erro continua a ser o G06** — esta alteração não o afecta |
| Regressão injectada (assinatura removida) | **4 falhas detectadas** (antes: 0) |

### Impacto e riscos

- **Custo:** o ciclo completo passa a correr 134 testes a mais (~90 s). O ciclo
  selectivo ganha 5-15 módulos nos ficheiros do guard.
- **Risco:** a junção das contagens dos dois `discover` tem de ser feita
  correctamente (o `stderr` dos dois é concatenado e o parser de contagens lê
  o total). **Validei** — os totais batem certo nos testes que corri.
- **Nenhum risco de segurança:** a alteração só faz o Guardian *executar mais
  testes*. Não toca em autenticação, autorização, validação criptográfica nem
  em `auto_repair`.

### Reversão

```bash
git checkout -- quality_guardian/config.py quality_guardian/runner.py
```

---

## O que NÃO está incluído

- Nenhuma alteração a `auto_repair: false`.
- Nenhuma alteração a superfícies protegidas.
- Nenhuma alteração a mecanismos de segurança — a Proposta 3 só faz o Guardian
  correr *mais* testes; não toca em criptografia, autorização nem execução.
- Nenhuma alteração a autenticação, autorização, validação criptográfica ou
  mecanismos fail-closed.
- Nenhuma alteração a testes (nem para os fazer passar).
- Nenhuma instalação de certificados, identidades de serviço ou permissões
  Windows.
- Nenhuma alteração a outros projectos ou à configuração global do Hermes.

## Decisão pedida

1. **Aplicar a PROPOSTA 1** (alargar o mapa do Guardian à Phase 2B)? SIM / NÃO
2. **Aplicar a PROPOSTA 2 / F1** (corrigir o G06)? SIM / NÃO
3. **Aplicar a PROPOSTA 3** (tornar o `consequence_guard` visível ao Guardian)? SIM / NÃO

> **Nota sobre a dependência:** as Propostas 1 e 3 tocam ambas em
> `quality_guardian/config.py` (`MODULE_TO_TESTS` e `FULL_TEST_SET`). Se
> autorizar as duas, aplico-as num único diff coerente — o mapa final fica com
> 35 chaves e 45 entradas no `FULL_TEST_SET`. A Proposta 2 é independente
> (`repair.py` + `guardian.py`) e não colide com nenhuma.

> **A PROPOSTA 3 é a mais urgente das três.** Sem ela, a suite de segurança do
> projecto — 134 testes — nunca é executada pelo verificador, e uma
> regressão que remova a verificação de uma assinatura Ed25519 passa
> despercebida. Foi isso que a auditoria injectou e mediu.
