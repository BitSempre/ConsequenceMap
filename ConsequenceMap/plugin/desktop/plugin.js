// ConsequenceMap — desktop half (runtime-loaded Hermes plugin).
//
// Contract: HermesPlugin default export — see
// apps/desktop/src/contrib/plugin.ts (HermesPlugin / PluginContext) and
// apps/desktop/src/contrib/runtime-loader.ts (validation + register call).
//
// This file ships as the unified agent-plugin desktop half
// (<plugin root>/desktop/plugin.js) and is loaded through the runtime
// pipeline: source -> import allowlist (@hermes/plugin-sdk, react*) ->
// specifier rewrite -> blob import -> validate default HermesPlugin ->
// register(ctx) called exactly once at load.

import { host } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'consequence-map'

// Disk plugins are not scanned by Tailwind, so layout lives here.
const CSS = `
.cm-panel{display:flex;flex-direction:column;gap:8px;padding:12px;font-family:var(--font-sans,system-ui,sans-serif)}
.cm-panel-title{margin:0;font-size:0.875rem;font-weight:600;color:var(--ui-text-primary)}
.cm-panel-sub{margin:0;font-size:0.75rem;color:var(--ui-text-tertiary)}
`

function ConsequenceMapPanel() {
  return jsxs('div', {
    className: 'cm-panel',
    children: [
      jsx('style', { children: CSS }),
      jsx('h3', { className: 'cm-panel-title', children: 'ConsequenceMap' }),
      jsx('p', { className: 'cm-panel-sub', children: 'See what happens before it happens.' })
    ]
  })
}

export default {
  id: ID,
  name: 'ConsequenceMap',
  description: 'Compact desktop panel with the ConsequenceMap forecast and comparison surfaces',
  register(ctx) {
    // Workspace registration through the supported mechanism:
    // host.openWorkspace(id, { title, minWidth, render, onClose }) -> disposer.
    // Feature-detect per the SDK doc comment (sdk/index.ts, openWorkspace):
    // older desktops without the door get a graceful skip, never a crash,
    // and no interval polling.
    if (typeof host?.openWorkspace !== 'function') {
      console.warn('[consequence-map] host.openWorkspace unavailable — workspace not docked')
      return
    }

    // Guard the cleanup channel FIRST: if ctx.onDispose is unavailable,
    // the pane can never be disposed on unload, so refuse to register it.
    if (typeof ctx?.onDispose !== 'function') {
      const error = new Error('consequence-map: ctx.onDispose is unavailable — refusing to register an undisposable workspace')
      console.error('[consequence-map] invalid PluginContext', error)
      throw error
    }

    let close
    let closed = false
    try {
      close = host.openWorkspace(ID, {
        title: 'ConsequenceMap',
        minWidth: '22rem',
        render: () => jsx(ConsequenceMapPanel, {})
      })
    } catch (error) {
      // Propagate so the runtime loader's failRegistration() records the
      // failure on this plugin's own inventory row (diagnostics). Nothing
      // has been registered yet, so nothing can leak on this path.
      console.error('[consequence-map] workspace registration failed', error)
      throw error
    }

    // A non-function disposer means the pane is registered but can never
    // be disposed on unload — refuse instead of registering an
    // undisposable workspace (failRegistration() rolls this back).
    if (typeof close !== 'function') {
      const error = new Error('consequence-map: host.openWorkspace did not return a disposer — refusing to register an undisposable workspace')
      console.error('[consequence-map] invalid openWorkspace result', error)
      throw error
    }

    // Cleanup: on plugin unload/reload/disable the loader runs every
    // disposer registered via ctx — this closes the docked pane so it
    // can never outlive the plugin. The tab's own Close (Cmd+W / strip
    // ✕) already routes through the same disposer in the SDK.
    // No bare globals, no timers.
    //
    // Idempotent: the SDK may fire both the pane-closer and the ctx
    // disposer for the same workspace; guard so the disposer runs once.
    ctx.onDispose(() => {
      if (closed) return
      closed = true
      close()
    })
  }
}
