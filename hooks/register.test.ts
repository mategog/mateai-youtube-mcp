import { expect, test } from 'claude-code/testing'

const TOKEN = JSON.stringify({
  scopes: [
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/yt-analytics.readonly',
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube',
    'https://www.googleapis.com/auth/youtube.force-ssl',
  ],
})

const registered: string[] = []

const stub = (on: any, files: Record<string, string>, hints?: Array<string | undefined>, env: Record<string, string> = {}) => {
  on('command.register', (_: unknown, e: { name: string }) => {
    registered.push(e.name)

    return { value: { command: e.name } }
  })
  on('session.start', (_: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  on('env.get', (_: unknown, e: { name: string }) => ({
    value: e.name === 'HOME' ? '/home/u' : env[e.name],
  }))
  on('fs.exists', (_: unknown, e: { path: string }) => ({ value: e.path in files }))
  on('fs.read', (_: unknown, e: { path: string }) => ({ value: files[e.path] }))
  on('fs.list', () => ({ value: [{ name: '1.0.5', kind: 'dir', size: 0, mtimeMs: 0, isLink: false }] }))
  on('ui.status', (_: unknown, e: { text?: string }) => {
    hints?.push(e.text)

    return { value: undefined }
  })
  on('ui.toast', () => ({ value: undefined }))
}

const DATA = '/home/u/.claude/plugins/data/yt-studio-mateai-youtube-mcp'
const PLUGIN = '/home/u/.claude/plugins/cache/mateai-youtube-mcp/yt-studio'
// Left by /yt-disconnect: the plugin stays signed out (no fallback to MateAI Studio's login) until /yt-setup.
const SIGNED_OUT = `${DATA}/.tokens/signed_out`

test('says it is already connected when the token has every scope', async ($, on) => {
  stub(on, { [`${DATA}/.tokens/token.json`]: TOKEN })
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })

  const out = await $.command.run({ command: 'yt-setup', args: '' })

  expect(out.text).toMatch(/Already connected/)
})

test('explains the one manual Google step when no client file exists', async ($, on) => {
  stub(on, { [PLUGIN]: '' })
  on('process.run', () => ({ value: { exitCode: 0, stdout: '', stderr: '' } }))
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })

  const out = await $.command.run({ command: 'yt-setup', args: '' })

  expect(out.text).toMatch(/Desktop app/)
  expect(out.text).toMatch(/Download JSON/)
})

test('with the bundled Google client it goes straight to the sign-in, no Google Cloud pages', async ($, on) => {
  stub(on, { [PLUGIN]: '', [`${PLUGIN}/1.0.5/oauth_client.json`]: '{"installed":{}}', [`${DATA}/.venv/bin/python`]: '' })
  const argvs: string[][] = []
  on('process.run', (_: unknown, e: { argv: string[] }) => {
    argvs.push(e.argv)

    return { value: { exitCode: 1, stdout: '', stderr: '' } }
  })
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })

  const out = await $.command.run({ command: 'yt-setup', args: '' })
  for (let i = 0; i < 50 && argvs.length === 0; i++) await new Promise(r => setTimeout(r, 10))

  expect(out.text).toMatch(/Opening your browser/)
  expect(out.text).not.toMatch(/Download JSON/)
  expect(argvs.length).toBe(1)
  expect(argvs[0][0]).toBe(`${DATA}/.venv/bin/python`)
  expect(argvs[0][argvs[0].length - 1]).toBe('1')
})

test('refuses a client file of the wrong type without copying it', async ($, on) => {
  stub(on, { [PLUGIN]: '', '/proj/client_secret_x.json': '{"web":{}}' })
  on('process.run', () => ({
    value: { exitCode: 0, stdout: '/proj/client_secret_x.json\n', stderr: '' },
  }))
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })

  const out = await $.command.run({ command: 'yt-setup', args: '' })

  expect(out.text).toMatch(/"web" client/)
})

test('one session.start registers /yt-setup, /yt-disconnect and /yt-dashboard', async ($, on) => {
  registered.length = 0
  stub(on, {})
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })

  expect([...registered].sort()).toEqual(['yt-dashboard', 'yt-disconnect', 'yt-setup'])
})

test('/yt-setup when connected points to /yt-disconnect, not the manual delete', async ($, on) => {
  stub(on, { [`${DATA}/.tokens/token.json`]: TOKEN })
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })

  const out = await $.command.run({ command: 'yt-setup', args: '' })

  expect(out.text).toMatch(/\/yt-disconnect/)
  expect(out.text).toMatch(/\/yt-setup switch/)
  expect(out.text).not.toMatch(/delete the \.tokens/)
})

test('/yt-setup switch when connected opens a forced sign-in (built-in client) and keeps the current login meanwhile', async ($, on) => {
  stub(on, {
    [`${DATA}/.tokens/token.json`]: TOKEN,
    [PLUGIN]: '',
    [`${PLUGIN}/1.0.5/oauth_client.json`]: '{"installed":{}}',
    [`${DATA}/.venv/bin/python`]: '',
  })
  const logins: string[][] = []
  on('process.run', (_: unknown, e: { argv: string[] }) => {
    if (e.argv.includes('-c')) logins.push(e.argv)

    return { value: { exitCode: 1, stdout: '', stderr: '' } }
  })
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })

  const out = await $.command.run({ command: 'yt-setup', args: 'switch' })
  for (let i = 0; i < 50 && logins.length === 0; i++) await new Promise(r => setTimeout(r, 10))

  expect(out.text).not.toMatch(/Already connected/)
  expect(out.text).toMatch(/Opening your browser/)
  expect(out.text).toMatch(/current login keeps working/)
  expect(logins.length).toBe(1)
  expect(logins[0][logins[0].length - 1]).toBe('1')
})

test('a failed first /yt-setup still shows the "not connected" hint', async ($, on) => {
  const hints: Array<string | undefined> = []
  stub(on, { [PLUGIN]: '', [`${PLUGIN}/1.0.5/oauth_client.json`]: '{"installed":{}}', [`${DATA}/.venv/bin/python`]: '' }, hints)
  const logins: string[][] = []
  on('process.run', (_: unknown, e: { argv: string[] }) => {
    if (e.argv.includes('-c')) logins.push(e.argv)

    return { value: { exitCode: 1, stdout: '', stderr: 'closed the tab' } }
  })
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })
  hints.length = 0

  await $.command.run({ command: 'yt-setup', args: '' })
  for (let i = 0; i < 50 && hints.length === 0; i++) await new Promise(r => setTimeout(r, 10))

  expect(logins.length).toBe(1)
  expect(hints).toContain('YouTube: not connected, run /yt-setup')
})

test('a cancelled /yt-setup switch leaves the previous login connected: no "not connected" hint', async ($, on) => {
  const hints: Array<string | undefined> = []
  stub(on, {
    [`${DATA}/.tokens/token.json`]: TOKEN,
    [PLUGIN]: '',
    [`${PLUGIN}/1.0.5/oauth_client.json`]: '{"installed":{}}',
    [`${DATA}/.venv/bin/python`]: '',
  }, hints)
  const logins: string[][] = []
  on('process.run', (_: unknown, e: { argv: string[] }) => {
    if (e.argv.includes('-c')) logins.push(e.argv)

    return { value: { exitCode: 1, stdout: '', stderr: 'closed the tab' } }
  })
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })
  hints.length = 0

  await $.command.run({ command: 'yt-setup', args: 'switch' })
  for (let i = 0; i < 50 && hints.length === 0; i++) await new Promise(r => setTimeout(r, 10))

  expect(logins.length).toBe(1) // the sign-in ran
  expect(hints.length).toBe(1) // and finished
  expect(hints.some(h => /not connected/.test(h ?? ''))).toBe(false)
})

// Runs /yt-disconnect; the Python helper (yt_auth.disconnect) answers with `reply` on stdout.
// A '/usr/bin/security' entry in `files` means MateAI Studio's Keychain login exists.
const runDisconnect = async ($: any, on: any, files: Record<string, string>, reply: string, env: Record<string, string> = {}) => {
  const hints: Array<string | undefined> = []
  stub(on, { ...files, [PLUGIN]: '', [`${DATA}/.venv/bin/python`]: '' }, hints, env)
  const runs: Array<{ argv: string[]; env?: Record<string, string> }> = []
  on('process.run', (_: unknown, e: { argv: string[]; init?: { env?: Record<string, string> } }) => {
    runs.push({ argv: e.argv, env: e.init?.env })

    return { value: { exitCode: 0, stdout: reply, stderr: '' } }
  })
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })
  hints.length = 0
  const out = await $.command.run({ command: 'yt-disconnect', args: '' })

  return { out, runs, hints }
}

test('/yt-disconnect with nothing connected says so and runs nothing', async ($, on) => {
  const { out, runs } = await runDisconnect($, on, {}, '')

  expect(out.text).toMatch(/not connected/)
  expect(runs.length).toBe(0)
})

test('/yt-disconnect revokes and deletes through yt_auth.disconnect, then shows "not connected"', async ($, on) => {
  const { out, runs, hints } = await runDisconnect(
    $, on, { [`${DATA}/.tokens/token.json`]: TOKEN }, '{"had_login": true, "revoked": true}\n',
  )

  expect(runs.length).toBe(1)
  expect(runs[0].argv[0]).toBe(`${DATA}/.venv/bin/python`)
  expect(runs[0].argv.join(' ')).toMatch(/yt_auth\.disconnect\(revoke=/)
  expect(runs[0].env?.MATEAI_YT_HOME).toBe(DATA)
  expect(runs[0].argv[runs[0].argv.length - 1]).toBe('1') // revoke at Google
  expect(out.text).toMatch(/Google revoked access/)
  expect(out.text).toMatch(/\/yt-setup/)
  expect(out.text).toMatch(/account chooser/)
  expect(out.text).not.toMatch(/pre-select/)
  expect(hints).toContain('YouTube: not connected, run /yt-setup')
})

test('/yt-disconnect when Google does not confirm: login still removed, honest message', async ($, on) => {
  const { out, hints } = await runDisconnect(
    $, on, { [`${DATA}/.tokens/token.json`]: TOKEN }, '{"had_login": true, "revoked": false}\n',
  )

  expect(out.text).toMatch(/removed from this computer/)
  expect(out.text).toMatch(/did not confirm/)
  expect(out.text).toMatch(/myaccount\.google\.com\/permissions/)
  expect(out.text).not.toMatch(/Google revoked access/)
  expect(hints).toContain('YouTube: not connected, run /yt-setup')
})

test('/yt-disconnect with a MateAI Studio login deletes the plugin token, never revokes, and signs the plugin out', async ($, on) => {
  const { out, runs, hints } = await runDisconnect(
    $, on, { [`${DATA}/.tokens/token.json`]: TOKEN, '/usr/bin/security': '' }, '{"had_login": true, "revoked": false}\n',
  )
  const helper = runs.filter(r => r.argv[0] !== '/usr/bin/security')

  expect(helper.length).toBe(1)
  expect(helper[0].argv[helper[0].argv.length - 1]).toBe('0') // no revoke: it would sign Studio out too
  expect(out.text).toMatch(/^Disconnected\./)
  expect(out.text).toMatch(/not revoked/)
  expect(out.text).toMatch(/disconnect YouTube in MateAI Studio/)
  expect(out.text).toMatch(/myaccount\.google\.com\/permissions/)
  expect(out.text).toMatch(/does not use your MateAI Studio login/)
  expect(out.text).not.toMatch(/falls back/)
  expect(out.text).toMatch(/run \/yt-setup and pick it in Google's account chooser/)
  expect(hints).toContain('YouTube: not connected, run /yt-setup')
})

test('/yt-disconnect with only a MateAI Studio login still signs the plugin out', async ($, on) => {
  const { out, runs, hints } = await runDisconnect($, on, { '/usr/bin/security': '' }, '{"had_login": false, "revoked": false}\n')
  const helper = runs.filter(r => r.argv[0] !== '/usr/bin/security')

  expect(helper.length).toBe(1)
  expect(helper[0].argv[helper[0].argv.length - 1]).toBe('0') // Studio keeps its Google access
  expect(out.text).toMatch(/^Disconnected\./)
  expect(out.text).toMatch(/does not use your MateAI Studio login/)
  expect(hints).toContain('YouTube: not connected, run /yt-setup')
})

test('/yt-disconnect when the helper fails, with a MateAI Studio login: the by-hand steps include the signed-out file', async ($, on) => {
  stub(on, { [`${DATA}/.tokens/token.json`]: TOKEN, [PLUGIN]: '', '/usr/bin/security': '' })
  on('process.run', (_: unknown, e: { argv: string[] }) => ({
    value: { exitCode: e.argv[0] === '/usr/bin/security' ? 0 : 1, stdout: '', stderr: 'boom' },
  }))
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })

  const out = await $.command.run({ command: 'yt-disconnect', args: '' })

  expect(out.text).toMatch(/Could not disconnect/)
  expect(out.text).toMatch(/\.tokens\/signed_out/) // deleting the token alone would fall back to Studio's login
})

test('/yt-disconnect a second time, with a MateAI Studio login, says not connected and runs nothing', async ($, on) => {
  const { out, runs } = await runDisconnect($, on, { '/usr/bin/security': '', [SIGNED_OUT]: '' }, '')

  expect(out.text).toMatch(/not connected/)
  expect(runs.filter(r => r.argv[0] !== '/usr/bin/security').length).toBe(0)
})

test('keyring mode ignores the Studio Keychain item, as yt_auth.py does: revoke, "not connected"', async ($, on) => {
  const { out, runs, hints } = await runDisconnect(
    $, on, { '/usr/bin/security': '' }, '{"had_login": true, "revoked": true}\n', { MATEAI_TOKEN_BACKEND: 'keyring' },
  )

  expect(runs.some(r => r.argv[0] === '/usr/bin/security')).toBe(false)
  expect(runs.length).toBe(1)
  expect(runs[0].argv[runs[0].argv.length - 1]).toBe('1')
  expect(out.text).not.toMatch(/MateAI Studio/)
  expect(hints).toContain('YouTube: not connected, run /yt-setup')
})

test('/yt-disconnect when the helper fails does not claim success', async ($, on) => {
  const hints: Array<string | undefined> = []
  stub(on, { [`${DATA}/.tokens/token.json`]: TOKEN, [PLUGIN]: '' }, hints)
  on('process.run', () => ({ value: { exitCode: 1, stdout: '', stderr: 'boom' } }))
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })
  hints.length = 0

  const out = await $.command.run({ command: 'yt-disconnect', args: '' })

  expect(out.text).toMatch(/Could not disconnect/)
  expect(out.text).toMatch(/\.tokens\/token\.json/)
  expect(out.text).toMatch(/myaccount\.google\.com\/permissions/)
  expect(hints.length).toBe(0)
})

// MateAI Studio's login: /usr/bin/security exists and finds the app's Keychain item.
const appLogin = (on: any, hints?: Array<string | undefined>, files: Record<string, string> = {}) => {
  stub(on, { ...files, [PLUGIN]: '', [`${PLUGIN}/1.0.5/oauth_client.json`]: '{"installed":{}}', '/usr/bin/security': '' }, hints)
  const argvs: string[][] = []
  on('process.run', (_: unknown, e: { argv: string[] }) => {
    argvs.push(e.argv)

    return { value: { exitCode: e.argv[0] === '/usr/bin/security' ? 0 : 1, stdout: '', stderr: '' } }
  })

  return argvs
}

test('with a MateAI Studio login, /yt-setup still opens the sign-in (built-in client, force "1")', async ($, on) => {
  const argvs = appLogin(on, undefined, { [`${DATA}/.venv/bin/python`]: '' })
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })

  const out = await $.command.run({ command: 'yt-setup', args: '' })
  const logins = () => argvs.filter(a => a.includes('-c'))
  for (let i = 0; i < 50 && logins().length === 0; i++) await new Promise(r => setTimeout(r, 10))

  expect(out.text).toMatch(/Opening your browser/)
  expect(out.text).not.toMatch(/Already connected/)
  expect(logins().length).toBe(1)
  expect(logins()[0][logins()[0].length - 1]).toBe('1')
  expect(argvs.some(a => a.includes('-w'))).toBe(false) // never reads Studio's token
})

test('with a MateAI Studio login, /yt-setup with your own client file also forces the sign-in', async ($, on) => {
  const logins = await loginArgs($, on, { '/usr/bin/security': '' })

  expect(logins.length).toBe(1)
  expect(logins[0][logins[0].length - 1]).toBe('1')
})

test('with a MateAI Studio login and the plugin login fine, /yt-setup says already connected', async ($, on) => {
  appLogin(on, undefined, { [`${DATA}/.tokens/token.json`]: TOKEN })
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })

  const out = await $.command.run({ command: 'yt-setup', args: '' })

  expect(out.text).toMatch(/Already connected/)
})

test('with a MateAI Studio login, an expired plugin login still shows the hint (it wins over Studio)', async ($, on) => {
  const hints: Array<string | undefined> = []
  appLogin(on, hints, { [`${DATA}/.tokens/token.json`]: TOKEN, [`${DATA}/.tokens/expired`]: '' })
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })

  expect(hints.some(h => /not connected/.test(h ?? ''))).toBe(true)
})

test('with a MateAI Studio login, no "not connected" hint at start', async ($, on) => {
  const hints: Array<string | undefined> = []
  appLogin(on, hints)
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })

  expect(hints.some(h => /not connected/.test(h ?? ''))).toBe(false)
})

test('after /yt-disconnect, a MateAI Studio login no longer hides the "not connected" hint at start', async ($, on) => {
  const hints: Array<string | undefined> = []
  appLogin(on, hints, { [SIGNED_OUT]: '' })
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })

  expect(hints.some(h => /not connected/.test(h ?? ''))).toBe(true)
})

const MARKER = `${DATA}/.tokens/expired`

test('starts the sign-in, not "Already connected", when the login is marked expired', async ($, on) => {
  stub(on, { [`${DATA}/.tokens/token.json`]: TOKEN, [MARKER]: '' })
  on('process.run', () => ({ value: { exitCode: 0, stdout: '', stderr: '' } }))
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })

  const out = await $.command.run({ command: 'yt-setup', args: '' })

  expect(out.text).not.toMatch(/Already connected/)
})

test('shows the "not connected" hint at start when the login is marked expired', async ($, on) => {
  const hints: Array<string | undefined> = []
  stub(on, { [`${DATA}/.tokens/token.json`]: TOKEN, [MARKER]: '' }, hints)
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })

  expect(hints.some(h => /not connected/.test(h ?? ''))).toBe(true)
})

// Runs /yt-setup with the Google libraries "installed" and a client file in place, and returns
// the argv of the login process (the force_reauth flag is its last argument).
const loginArgs = async ($: any, on: any, files: Record<string, string>, args = '') => {
  stub(on, {
    ...files,
    [`${DATA}/.venv/bin/python`]: '',
    [`${DATA}/google_auth_secret/client_secret.json`]: '{"installed":{}}',
    [PLUGIN]: '',
  })
  const logins: string[][] = []
  on('process.run', (_: unknown, e: { argv: string[] }) => {
    if (e.argv.includes('-c')) logins.push(e.argv)

    // A '/usr/bin/security' entry in `files` plus exit 0 here means a MateAI Studio login exists.
    return { value: { exitCode: e.argv[0] === '/usr/bin/security' ? 0 : 1, stdout: '', stderr: '' } }
  })
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })
  await $.command.run({ command: 'yt-setup', args })
  // The login runs on after the command's answer, so give it a moment to start.
  for (let i = 0; i < 50 && logins.length === 0; i++) await new Promise(r => setTimeout(r, 10))

  return logins
}

test('forces a fresh sign-in (force_reauth "1") when the login is marked expired', async ($, on) => {
  const logins = await loginArgs($, on, { [`${DATA}/.tokens/token.json`]: TOKEN, [MARKER]: '' })

  expect(logins.length).toBe(1)
  expect(logins[0][logins[0].length - 1]).toBe('1')
})

test('keeps the plain refresh (force_reauth "0") when the login is fine but not yet connected', async ($, on) => {
  const logins = await loginArgs($, on, {})

  expect(logins.length).toBe(1)
  expect(logins[0][logins[0].length - 1]).toBe('0')
})

test('after /yt-disconnect, /yt-setup with your own client file forces the sign-in (yt_auth.py refuses a plain one)', async ($, on) => {
  const logins = await loginArgs($, on, { [SIGNED_OUT]: '' })

  expect(logins.length).toBe(1)
  expect(logins[0][logins[0].length - 1]).toBe('1')
})

test('/yt-setup switch with your own client file forces the sign-in over a working login', async ($, on) => {
  const logins = await loginArgs($, on, { [`${DATA}/.tokens/token.json`]: TOKEN }, 'switch')

  expect(logins.length).toBe(1)
  expect(logins[0][logins[0].length - 1]).toBe('1')
})

test('a stale marker without a token folder does not trap the user', async ($, on) => {
  const logins = await loginArgs($, on, { [MARKER]: '' })

  expect(logins.length).toBe(1)
})

// Windows: USERPROFILE instead of HOME, no `find`/`open`/`chmod`, and the venv interpreter is
// Scripts\python.exe. The test host resolves paths POSIX-style, so the profile is written as /win/u.
const WIN_HOME = '/win/u'
const WIN_DATA = `${WIN_HOME}/.claude/plugins/data/yt-studio-mateai-youtube-mcp`
const WIN_PLUGIN = `${WIN_HOME}/.claude/plugins/cache/mateai-youtube-mcp/yt-studio`

const stubWindows = (on: any, files: Record<string, string>, dirs: Record<string, Array<{ name: string; kind: string }>>) => {
  on('command.register', (_: unknown, e: { name: string }) => ({ value: { command: e.name } }))
  on('session.start', (_: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  on('env.get', (_: unknown, e: { name: string }) => ({
    value: ({ OS: 'Windows_NT', USERPROFILE: WIN_HOME, HOME: '/wrong/home' } as Record<string, string>)[e.name],
  }))
  on('fs.exists', (_: unknown, e: { path: string }) => ({ value: e.path in files || e.path in dirs }))
  on('fs.read', (_: unknown, e: { path: string }) => ({ value: files[e.path] }))
  on('fs.write', (_: unknown, e: { path: string; text: string }) => {
    files[e.path] = e.text

    return { value: undefined }
  })
  on('fs.list', (_: unknown, e: { path: string }) => ({
    value: (dirs[e.path] ?? []).map(d => ({ ...d, size: 0, mtimeMs: 0, isLink: false })),
  }))
  on('ui.status', () => ({ value: undefined }))
  on('ui.toast', () => ({ value: undefined }))
}

test('Windows: opens the Google pages with url.dll, never find or open', async ($, on) => {
  stubWindows(on, {}, { [WIN_PLUGIN]: [{ name: '1.0.5', kind: 'dir' }] })
  const argvs: string[][] = []
  on('process.run', (_: unknown, e: { argv: string[] }) => {
    argvs.push(e.argv)

    return { value: { exitCode: 0, stdout: '', stderr: '' } }
  })
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })

  const out = await $.command.run({ command: 'yt-setup', args: '' })

  expect(out.text).toMatch(/Download JSON/)
  expect(argvs.map(a => a[0])).toEqual(['rundll32', 'rundll32'])
  expect(argvs[0][1]).toBe('url.dll,FileProtocolHandler')
})

test('Windows: finds the client file in Downloads, copies it without chmod, signs in with Scripts\\python.exe', async ($, on) => {
  const files: Record<string, string> = {
    [`${WIN_HOME}/Downloads/client_secret_123.json`]: '{"installed":{}}',
    [`${WIN_DATA}/.venv/Scripts/python.exe`]: '',
  }
  stubWindows(on, files, {
    [WIN_PLUGIN]: [{ name: '1.0.5', kind: 'dir' }],
    '/proj': [{ name: 'node_modules', kind: 'dir' }],
    [`${WIN_HOME}/Downloads`]: [{ name: 'client_secret_123.json', kind: 'file' }],
  })
  const argvs: string[][] = []
  on('process.run', (_: unknown, e: { argv: string[] }) => {
    argvs.push(e.argv)

    return { value: { exitCode: 1, stdout: '', stderr: '' } }
  })
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })

  const out = await $.command.run({ command: 'yt-setup', args: '' })
  for (let i = 0; i < 50 && argvs.length === 0; i++) await new Promise(r => setTimeout(r, 10))

  expect(out.text).toMatch(/private to your Windows user/)
  expect(files[`${WIN_DATA}/google_auth_secret/client_secret.json`]).toBe('{"installed":{}}')
  expect(argvs.some(a => a[0] === 'chmod' || a[0] === 'find')).toBe(false)
  expect(argvs[0][0]).toBe(`${WIN_DATA}/.venv/Scripts/python.exe`)
})
