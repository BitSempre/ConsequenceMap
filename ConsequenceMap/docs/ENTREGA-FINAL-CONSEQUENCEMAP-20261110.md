# ConsequenceMap — Entrega Final

**Data:** 10 de novembro de 2026
**Commit:** `01a3b85904c7a635229d40dac037a2b802703de2`
**Mensagem:** `feat(security): strengthen Quality Guardian and fail-closed policy`
**Branch:** `feature/platform-v1` · **Commits:** 59 · **Árvore:** limpa

> **Classificação de prontidão: `NOT READY FOR PRODUCTION`.**
> O trabalho de estabilização está concluído e verificado. A instalação em
> produção não está — ver a secção 8.

---

## 1. Objectivo do trabalho

Concluir o trabalho de estabilização autorizado do Quality Guardian e do
controlo de reparação automática, e entregar uma versão consolidada,
verificável e pronta para validação futura — sem tocar nos bloqueios de
produção.

## 2. As cinco intervenções realizadas

### Proposta 1 — cobertura do Quality Guardian
`MODULE_TO_TESTS` 13 → **37** chaves e `FULL_TEST_SET` 13 → **45** entradas.
**As duas constantes têm de mudar em conjunto**: `select_tests()` filtra o
resultado por `FULL_TEST_SET`, pelo que uma edição só do mapa é um *no-op*
verificado empiricamente. As 13 entradas Phase 2A originais estão preservadas
**verbatim** (comparadas por `ast.literal_eval` contra o HEAD).

### Proposta 2 — G06 (variante pass-through)
`repair.write_file_text(path, content, root=None)` consulta a política da
raiz que lhe é passada; `guardian._attempt_repairs` transmite `root=root` nos
dois call sites. O gate e o choke point passam a consultar **a mesma raiz**.
O G06 deixou de dar ERROR.

### Proposta 3 — `consequence_guard` visível
`config.module_for_path()` reconhece o pacote `consequence_guard`;
`runner._module_address()` resolve o módulo de teste no pacote que
effectivamente o contém (os dois pacotes têm sobreposição zero);
`run_full_suite()` descobre **ambos**; `_parse_counts()` soma todos os
resumos, para uma falha no segundo pacote ser contada em vez de mascarada.

### Correcção A — política de reparação fail-closed
`DEFAULT_AUTO_REPAIR = False`. Uma política ausente, ilegível, malformada ou
com `auto_repair` não booleano resolve para **reparação suspensa**; só um
`"auto_repair": true` explícito num ficheiro legível a habilita.
`make_isolated_project()` escreve uma política explícita **dentro da raiz
temporária descartável**, para os testes do caminho de reparação continuarem
a exercê-lo. **A política de produção não foi tocada.**

### Correcção B — contador de falhas do audit sink visível
`on_command("status")` reporta `"Audit sink failures this session: N"`. O
contador é lido, **nunca reiniciado, nunca ocultado**. Um sink que não o
mantenha reporta `0` em vez de partir o comando. Nada foi alterado no caminho
de autorização nem na semântica de escrita do sink.

## 3. Ficheiros incluídos no commit (20)

| Ficheiro | Papel |
|---|---|
| `consequence_map/hooks.py` | Correcção B — contador visível |
| `consequence_map/tests/test_audit_sink_failures.py` | **NOVO** — 7 testes comportamentais |
| `quality_guardian/config.py` | Propostas 1 + 3, Correcção A |
| `quality_guardian/guardian.py` | Proposta 2 — transmite `root=root` |
| `quality_guardian/repair.py` | Proposta 2 — choke point pass-through |
| `quality_guardian/runner.py` | Proposta 3 — endereço, ciclo duplo, contagem |
| `quality_guardian/tests/isolated.py` | Correcção A — política explícita na raiz isolada |
| `quality_guardian/tests/test_repair_policy.py` | **NOVO** — 11 testes comportamentais |
| `quality_guardian/state/last-seen.json` | Estado — baseline de hashes do Guardian |
| `quality_guardian/reports/20261110T{214825,222235}Z-manual.{json,md}` | Evidência — relatórios dos ciclos |
| `docs/PROPOSTAS-AUTORIZACAO-20261110.md` | Evidência — as três propostas |
| `docs/PROPOSTAS-EXECUCAO-20261110.md` | Evidência — relatório de execução |
| `docs/PROPOSTAS-EXECUCAO-DIFFS-20261110.diff` | Evidência — diffs |
| `docs/CORRECCOES-SEGURANCA-RELATORIO-20261110.md` | Evidência — relatório das correcções |
| `docs/CORRECCOES-SEGURANCA-DIFFS-20261110.diff` | Evidência — diffs |
| `docs/BACKUP-MANIFEST-20261110.json` | Evidência — manifesto de backup |
| `docs/BACKUP-MANIFEST-CORRECCOES-20261110.json` | Evidência — manifesto de backup |

**Não incluídos, por não pertencerem ao âmbito:** `quality_guardian/state/repair-policy.json`
(a política real), qualquer componente de criptografia, autorização, executor,
nonce, replay ou revogação, o ZIP de entrega e o `SHA256SUMS.txt`.

## 4. Hash e mensagem do commit

```
01a3b85904c7a635229d40dac037a2b802703de2
feat(security): strengthen Quality Guardian and fail-closed policy
```

## 5. Resultados reais dos testes (execução desta entrega)

| Suite | Testes | Resultado | rc | Duração |
|---|---|---|---|---|
| `consequence_map` | 556 | **OK** | 0 | 69,4 s |
| `consequence_guard` | 134 | **OK** | 0 | 86,9 s |
| `host_tests` | 2 | **OK** | 0 | 0,4 s |
| `quality_guardian` | 41 | **OK** | 0 | 6,7 s |
| Protótipo móvel | 12 | **OK** | 0 | 0,3 s |
| Demonstração móvel | — | exit 0 | 0 | 0,1 s |
| **Total** | **745** | **PASS, 0 erros** | | ~164 s |
| **Ciclo completo do Guardian** | **690** | **PASS, 0 falhas** | 0 | 110,9 s |

**Os 18 testes novos têm dentes** — verificado por injecção de defeito em
cópias isoladas: `DEFAULT_AUTO_REPAIR=True` → 8 falhas · branch permissiva →
5 falhas · linha do status removida → 4 falhas · contador reiniciado → 2
falhas · `+= 1` removido → 3 falhas.

**As quatro regressões antes demonstradas continuam detectadas:** Ed25519
removido → 4 falhas · EC-7 no `hooks.py` → 7 erros · EC-7 removido do
correlator → 3 falhas · Ed25519 pelo ciclo completo → 7 falhas.

## 6. Verificações de integridade e segurança

| Verificação | Resultado |
|---|---|
| `auto_repair` na política real | **`false`**, sha256 `52f60c0afb16746a54c32a31b96c53f64eaa48ff074641966ec610f5c6c3b129` — **inalterado** |
| `DEFAULT_AUTO_REPAIR` | **`False`** |
| Fallbacks permissivos na política | **nenhum** — as 5 branches usam `DEFAULT_AUTO_REPAIR` |
| Política do G06 | explícita `auto_repair: true`, **só na raiz temporária** |
| Contador no status | apresentado, lido sem reiniciar |
| Superfícies protegidas | **byte-idênticas ao HEAD** — nenhuma divergência |
| Regressões injectadas no código real | **nenhuma** (`DEFECT INJECTED` ausente de toda a árvore) |
| Criptografia, autorização, executor, nonce, replay, revogação | **não alterados** — `git diff --name-only` sobre esses caminhos devolve vazio |
| Credenciais / tokens / chaves nos ficheiros | **nenhum** encontrado |
| Ficheiros temporários, caches | **nenhum** |

## 7. Evidência da preservação do backup

`C:/Users/Utente/AppData/Local/hermes/cache/scratch/cm-backup-pre-fix-20261110_231519/`
— os 6 ficheiros verificados um a um contra o manifesto
(`BACKUP-MANIFEST.json`, sha256 `b6ac8c6a07e04ec27fdf01e35af9f0e4a31aaf3b8d68317617495fb7c6a62f77`):
**todos coincidem**. O manifesto está também copiado para
`docs/BACKUP-MANIFEST-CORRECOES-20261110.json`.

Backups adicionais preservados: `scratch/cm-backup-pre-20261110_222200/`
(antes das Propostas 1–3) e `scratch/cm-independent-audit-TRANSCRIPT-20261110.log`
(transcript da auditoria que mediu).

## 8. Limitações e riscos ainda existentes

**Bloqueios de produção — não resolvidos nesta missão:**

1. **Propagação da revogação Ed25519.** `KeyRegistry.revoke()` não afecta um
   `Ed25519Verifier` já construído; `consequence_guard/service.py:455` passa
   `revoked_key_ids=()`. A revogação só tem efeito sobre verificadores novos.
2. **Ausência de API de verificação integral da cadeia de auditoria.**
   `GuardStore.audit_head()` devolve o hash **armazenado**; o checkpoint
   detecta apenas a adulteração do `record_hash` da última linha. O recálculo
   detectaria todas, mas não está exposto.
3. **Serviço Windows ainda não instalado.** `sc query ConsequenceMapGuard` →
   1060; a identidade `ConsequenceMapGuardSvc` não existe. O procedimento e o
   rollback estão no ADR-002.
4. **Plugin Hermes ainda não instalado.** `AppData/Local/hermes/plugins`
   existe, o `consequence-map` não está dentro dele.
5. **DEC-16 ainda sem decisão explícita.** O grace period é 30 s, valor de
   referência analítica, não uma decisão do proprietário.
6. **`SHA256SUMS.txt` desactualizado.** Declara o ZIP `4e62e418…` e o
   manifesto `510f415…`; os reais são `5ae7a35b…` e `b8cc268…`. O conteúdo
   do ZIP verifica 246/246 — a âncora é que está errada. Corrigir exige
   re-empacotar e altera hashes de entrega.

**Riscos menores:** o ciclo completo do Guardian passou de ~125 s para ~190 s
(timeout de 600 s **por pacote**; o pior caso é 1200 s). A selecção por
grafo de imports sobre-selecciona para módulos de fundação como
`core/canonical.py` — inerente ao método, mitigável com
`HIGH_IMPACT_MODULES` se o custo incomodar.

## 9. Estado Git final

```
HEAD    01a3b85904c7a635229d40dac037a2b802703de2
commits 59 (o anterior 5920406 é ancestral)
branch  feature/platform-v1
upstream: nenhum — nada foi enviado
status  ÁRVORE LIMPA: 0 staged, 0 unstaged, 0 untracked
```

O commit é **local**. Não houve `push`, publicação, distribuição de release,
instalação de serviço ou plugin, alteração do DEC-16, alteração do ZIP ou
regeneração do `SHA256SUMS.txt`.

## 10. Classificação de prontidão

> ### `NOT READY FOR PRODUCTION`
>
> `READY FOR DEVELOPMENT` — sim, o desenvolvimento continua.
> `READY FOR CONTROLLED TESTING` — sim, em ambiente isolado.
> `READY FOR PRODUCTION` — **não**. Os seis bloqueios da secção 8 têm de ser
> fechados, e a decisão sobre eles é do proprietário.

**Nota sobre o caminho indicado na instrução.** A instrução indicava
`C:\Users\Utente\Desktop\ConsequenceMap`. Esse directório existe mas
**não é um repositório Git** — é a árvore da Phase 2A, com o mapa de 13 chaves,
`DEFAULT_AUTO_REPAIR = True` e sem qualquer módulo de `consequence_guard`.
O trabalho autorizado está no repositório
`Desktop/Projects/ConsequenceMap/ConsequenceMap-Platform`, que é onde o commit
foi feito. As duas árvores divergem e não devem ser confundidas.
