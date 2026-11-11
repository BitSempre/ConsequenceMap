# ConsequenceMap

**Decision intelligence for AI agents** — forecasts the consequence of an action
before it happens, preserves the decision and its evidence, and compares the
forecast with what actually occurred.

> **Status: NOT READY FOR PRODUCTION.** The library and the plugin are
> implemented and tested; the Security Guard is not installed on any host, so
> the authorization boundary is not active yet.

The project lives in the [`ConsequenceMap/`](ConsequenceMap/) subdirectory,
which is the installable Hermes plugin and also contains the product library,
the Security Guard and the quality layer.

**→ [Read the full README](ConsequenceMap/README.md)**

## Layout

| Path | Contents |
|---|---|
| [`ConsequenceMap/`](ConsequenceMap/) | The plugin, the product library, the Security Guard, the quality layer, the tests and the delivery evidence |
| [`design/`](design/) | The mobile authorization prototype |
| [`security-decisions/`](security-decisions/) | Architecture decision records, including the Windows service identity |

## Install

```bash
hermes plugins validate ConsequenceMap/plugin
hermes plugins install https://github.com/BitSempre/ConsequenceMap --ref <40-char-sha>
```
