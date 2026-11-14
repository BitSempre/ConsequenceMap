/**
 * ConsequenceMap Desktop Plugin — Contract Test Suite (Vitest).
 *
 * Validates the Phase 11 implementation against the Hermes Desktop SDK
 * contract. Mocking follows the repository's established pattern
 * (hermes-bots/bot-delete.test.ts): vi.mock('@hermes/plugin-sdk',
 * async importOriginal => ...) with a Proxy over the real SDK so only
 * the host.openWorkspace seam is replaced — everything else resolves
 * through the actual SDK module.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { openWorkspaceSpy, overrides } = vi.hoisted(() => ({
  openWorkspaceSpy: vi.fn(),
  overrides: {}
}))

vi.mock('@hermes/plugin-sdk', async importOriginal => {
  const sdk = await importOriginal()

  return {
    ...sdk,
    host: new Proxy(sdk.host, {
      get: (target, prop) => (prop in overrides ? overrides[prop] : Reflect.get(target, prop))
    })
  }
})

import plugin from './plugin.js'

/** A PluginContext stub shaped to the contract (contrib/plugin.ts:115+). */
function makeCtx(extra = {}) {
  return {
    source: 'plugin:consequence-map',
    onDispose: vi.fn(),
    ...extra
  }
}

describe('A. Module and loader contract', () => {
  it('imports the module successfully', () => {
    expect(plugin).toBeDefined()
  })

  it('default export is an object', () => {
    expect(typeof plugin).toBe('object')
  })

  it('plugin id is exactly consequence-map', () => {
    expect(plugin.id).toBe('consequence-map')
  })

  it('register is a function', () => {
    expect(typeof plugin.register).toBe('function')
  })

  it('satisfies the actual loader validation contract', () => {
    // Verbatim check from contrib/runtime-loader.ts:
    //   if (!plugin?.id || typeof plugin.register !== 'function') throw
    expect(plugin?.id).toBeTruthy()
    expect(typeof plugin.register).toBe('function')
  })

  it('metadata fields are well-typed strings', () => {
    expect(typeof plugin.name).toBe('string')
    expect(plugin.name).toBe('ConsequenceMap')
    expect(typeof plugin.description).toBe('string')
    expect(plugin.description.length).toBeGreaterThan(0)
  })
})

describe('B. Workspace registration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    openWorkspaceSpy.mockReset()
    // The openWorkspace implementation returns a disposer; record calls.
    openWorkspaceSpy.mockImplementation(() => vi.fn())
    overrides.openWorkspace = openWorkspaceSpy
  })

  afterEach(() => {
    delete overrides.openWorkspace
  })

  it('calls host.openWorkspace exactly once', () => {
    plugin.register(makeCtx())

    expect(openWorkspaceSpy).toHaveBeenCalledTimes(1)
  })

  it('uses the correct workspace id', () => {
    plugin.register(makeCtx())

    expect(openWorkspaceSpy.mock.calls[0][0]).toBe('consequence-map')
  })

  it('passes title and minimum width', () => {
    plugin.register(makeCtx())

    const options = openWorkspaceSpy.mock.calls[0][1]
    expect(options.title).toBe('ConsequenceMap')
    expect(options.minWidth).toBe('22rem')
  })

  it('render callback returns a valid ReactNode', () => {
    plugin.register(makeCtx())

    const options = openWorkspaceSpy.mock.calls[0][1]
    const node = options.render()
    expect(node).not.toBeNull()
    // react/jsx-runtime elements carry $$typeof (react.element symbol)
    expect(node.$$typeof).toBeDefined()
  })

  it('uses only the supported SDK option keys', () => {
    plugin.register(makeCtx())

    const options = openWorkspaceSpy.mock.calls[0][1]
    // Every key handed to openWorkspace must exist in the contract:
    // id, dock, headerVeto, minWidth, onClose, render, title, uncloseable
    for (const key of Object.keys(options)) {
      expect(['dock', 'headerVeto', 'minWidth', 'onClose', 'render', 'title', 'uncloseable']).toContain(key)
    }
  })
})

describe('C. Lifecycle and disposal', () => {
  let disposer

  beforeEach(() => {
    vi.clearAllMocks()
    openWorkspaceSpy.mockReset()
    disposer = vi.fn()
    openWorkspaceSpy.mockImplementation(() => disposer)
    overrides.openWorkspace = openWorkspaceSpy
  })

  afterEach(() => {
    delete overrides.openWorkspace
  })

  it('captures the workspace disposer through ctx.onDispose', () => {
    const ctx = makeCtx()

    plugin.register(ctx)

    expect(ctx.onDispose).toHaveBeenCalledTimes(1)
    expect(typeof ctx.onDispose.mock.calls[0][0]).toBe('function')
  })

  it('executes the workspace disposer exactly once when cleanup runs', () => {
    const ctx = makeCtx()

    plugin.register(ctx)
    const cleanup = ctx.onDispose.mock.calls[0][0]

    cleanup()

    expect(disposer).toHaveBeenCalledTimes(1)
  })

  it('the plugin registers exactly one cleanup and owns no state between cleanups', () => {
    const ctx = makeCtx()

    plugin.register(ctx)
    const cleanup = ctx.onDispose.mock.calls[0][0]

    // The plugin registers exactly one cleanup — the forwarded SDK
    // disposer — and keeps no timers or plugin-side accumulators.
    expect(ctx.onDispose).toHaveBeenCalledTimes(1)

    cleanup()
    expect(disposer).toHaveBeenCalledTimes(1)
  })

  it('two consecutive registrations each hold an independent disposer chain', () => {
    // The loader owns replacement order (runtime-loader.ts disposes the
    // previous incarnation on reload); what the plugin must guarantee is
    // that each register() call hands the loader its own cleanup that
    // closes only its own workspace.
    const ctx1 = makeCtx()
    const ctx2 = makeCtx()
    const d1 = vi.fn()
    const d2 = vi.fn()
    let call = 0

    openWorkspaceSpy.mockImplementation(() => {
      call += 1
      return call === 1 ? d1 : d2
    })

    plugin.register(ctx1)
    plugin.register(ctx2)

    expect(openWorkspaceSpy).toHaveBeenCalledTimes(2)

    ctx1.onDispose.mock.calls[0][0]()
    expect(d1).toHaveBeenCalledTimes(1)
    expect(d2).not.toHaveBeenCalled()

    ctx2.onDispose.mock.calls[0][0]()
    expect(d1).toHaveBeenCalledTimes(1)
    expect(d2).toHaveBeenCalledTimes(1)
  })
})

describe('D. Failure handling', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    openWorkspaceSpy.mockReset()
  })

  afterEach(() => {
    delete overrides.openWorkspace
  })

  it('propagates when host.openWorkspace throws', () => {
    openWorkspaceSpy.mockImplementation(() => {
      throw new Error('boom')
    })
    overrides.openWorkspace = openWorkspaceSpy

    const ctx = makeCtx()

    expect(() => plugin.register(ctx)).toThrow('boom')
    expect(ctx.onDispose).not.toHaveBeenCalled()
  })

  it('refuses to register when host.openWorkspace returns a non-function disposer', () => {
    openWorkspaceSpy.mockReturnValue('not-a-disposer')
    overrides.openWorkspace = openWorkspaceSpy

    const ctx = makeCtx()

    expect(() => plugin.register(ctx)).toThrow(/did not return a disposer/)
    expect(ctx.onDispose).not.toHaveBeenCalled()
  })

  it('gracefully skips when the host capability is unavailable', () => {
    overrides.openWorkspace = undefined
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})

    try {
      const ctx = makeCtx()

      expect(() => plugin.register(ctx)).not.toThrow()
      expect(ctx.onDispose).not.toHaveBeenCalled()
      expect(warn).toHaveBeenCalled()
    } finally {
      warn.mockRestore()
    }
  })

  it('refuses registration when ctx is missing', () => {
    openWorkspaceSpy.mockImplementation(() => vi.fn())
    overrides.openWorkspace = openWorkspaceSpy

    expect(() => plugin.register(undefined)).toThrow(/onDispose is unavailable/)
    expect(openWorkspaceSpy).not.toHaveBeenCalled()
  })

  it('refuses registration when ctx.onDispose is missing', () => {
    openWorkspaceSpy.mockImplementation(() => vi.fn())
    overrides.openWorkspace = openWorkspaceSpy

    expect(() => plugin.register({})).toThrow(/onDispose is unavailable/)
    expect(openWorkspaceSpy).not.toHaveBeenCalled()
  })

  it('failed registration leaves no registered workspace or leaked resource', () => {
    openWorkspaceSpy.mockImplementation(() => {
      throw new Error('nope')
    })
    overrides.openWorkspace = openWorkspaceSpy

    const ctx = makeCtx()
    const beforeKeys = Object.keys(globalThis)

    expect(() => plugin.register(ctx)).toThrow()
    expect(ctx.onDispose).not.toHaveBeenCalled()
    expect(Object.keys(globalThis)).toEqual(beforeKeys)
  })
})

describe('E. Duplicate registration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    openWorkspaceSpy.mockReset()
    openWorkspaceSpy.mockImplementation(() => vi.fn())
    overrides.openWorkspace = openWorkspaceSpy
  })

  afterEach(() => {
    delete overrides.openWorkspace
  })

  it('performs two independent registrations', () => {
    const ctx1 = makeCtx()
    const ctx2 = makeCtx()

    plugin.register(ctx1)
    plugin.register(ctx2)

    expect(openWorkspaceSpy).toHaveBeenCalledTimes(2)
    expect(ctx1.onDispose).toHaveBeenCalledTimes(1)
    expect(ctx2.onDispose).toHaveBeenCalledTimes(1)
  })

  it('each registration cleans up independently', () => {
    const ctx1 = makeCtx()
    const ctx2 = makeCtx()
    const disposers = []

    openWorkspaceSpy.mockImplementation(() => {
      const d = vi.fn()
      disposers.push(d)
      return d
    })

    plugin.register(ctx1)
    plugin.register(ctx2)

    ctx1.onDispose.mock.calls[0][0]()

    expect(disposers[0]).toHaveBeenCalledTimes(1)
    expect(disposers[1]).not.toHaveBeenCalled()

    ctx2.onDispose.mock.calls[0][0]()

    expect(disposers[0]).toHaveBeenCalledTimes(1)
    expect(disposers[1]).toHaveBeenCalledTimes(1)
  })

  it('each registration captures the workspace disposer returned for it', () => {
    const d1 = vi.fn()
    const d2 = vi.fn()
    let call = 0

    openWorkspaceSpy.mockImplementation(() => {
      call += 1
      return call === 1 ? d1 : d2
    })

    const onDispose = vi.fn()

    plugin.register({ onDispose })
    plugin.register({ onDispose })

    const c1 = onDispose.mock.calls[0][0]
    const c2 = onDispose.mock.calls[1][0]

    expect(c1).not.toBe(c2)

    c1()
    c2()

    // Each cleanup closes exactly the workspace its registration opened.
    expect(d1).toHaveBeenCalledTimes(1)
    expect(d2).toHaveBeenCalledTimes(1)
  })
})

describe('F. Regression', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    openWorkspaceSpy.mockReset()
    openWorkspaceSpy.mockImplementation(() => vi.fn())
    overrides.openWorkspace = openWorkspaceSpy
  })

  afterEach(() => {
    delete overrides.openWorkspace
  })

  it('plugin remains importable after registrations', () => {
    plugin.register(makeCtx())
    expect(() => plugin.id).not.toThrow()
    expect(plugin.id).toBe('consequence-map')
  })

  it('does not use a deprecated global registration mechanism', async () => {
    const { readFileSync } = await import('node:fs')
    const { fileURLToPath } = await import('node:url')
    const { dirname, join } = await import('node:path')

    // Read the ACTUAL imported plugin.js source, not a cwd-relative path
    const source = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'plugin.js'), 'utf8')

    expect(source).not.toContain('__HERMES_PLUGIN_SDK__')
    expect(source).not.toContain('window.')
  })

  it('introduces no unsafe dynamic imports', async () => {
    const { readFileSync } = await import('node:fs')
    const { fileURLToPath } = await import('node:url')
    const { dirname, join } = await import('node:path')

    // Read the ACTUAL imported plugin.js source, not a cwd-relative path
    const source = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'plugin.js'), 'utf8')

    expect(source).not.toMatch(/import\(\s*['"]/)
    expect(source).not.toContain('fetch(')
  })

  it('does not mutate unrelated global state', () => {
    const before = JSON.stringify(Object.keys(globalThis).sort())

    plugin.register(makeCtx())

    const after = JSON.stringify(Object.keys(globalThis).sort())
    expect(after).toBe(before)
  })
})
