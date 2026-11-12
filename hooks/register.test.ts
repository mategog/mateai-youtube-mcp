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

const stub = (on: any, files: Record<string, string>, hints?: Array<string | undefined>) => {
  on('command.register', (_: unknown, e: { name: string }) => {
    registered.push(e.name)

    return { value: { command: e.name } }
  })
  on('session.start', (_: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  on('env.get', (_: unknown, e: { name: string }) => ({
    value: e.name === 'HOME' ? '/home/u' : undefined,
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

test('one session.start registers both /yt-setup and /yt-dashboard', async ($, on) => {
  registered.length = 0
  stub(on, {})
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })

  expect([...registered].sort()).toEqual(['yt-dashboard', 'yt-setup'])
})

// MateAI Studio's login: /usr/bin/security exists and finds the app's Keychain item.
const appLogin = (on: any, hints?: Array<string | undefined>) => {
  stub(on, { [PLUGIN]: '', [`${PLUGIN}/1.0.5/oauth_client.json`]: '{"installed":{}}', '/usr/bin/security': '' }, hints)
  const argvs: string[][] = []
  on('process.run', (_: unknown, e: { argv: string[] }) => {
    argvs.push(e.argv)

    return { value: { exitCode: e.argv[0] === '/usr/bin/security' ? 0 : 1, stdout: '', stderr: '' } }
  })

  return argvs
}

test('with a MateAI Studio login, /yt-setup says connected and starts no second sign-in', async ($, on) => {
  const argvs = appLogin(on)
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })

  const out = await $.command.run({ command: 'yt-setup', args: '' })
  await new Promise(r => setTimeout(r, 50))

  expect(out.text).toMatch(/MateAI Studio/)
  expect(argvs.every(a => a[0] === '/usr/bin/security')).toBe(true)
  expect(argvs.some(a => a.includes('-w'))).toBe(false)
})

test('with a MateAI Studio login, no "not connected" hint at start', async ($, on) => {
  const hints: Array<string | undefined> = []
  appLogin(on, hints)
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })

  expect(hints.some(h => /not connected/.test(h ?? ''))).toBe(false)
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
const loginArgs = async ($: any, on: any, files: Record<string, string>) => {
  stub(on, {
    ...files,
    [`${DATA}/.venv/bin/python`]: '',
    [`${DATA}/google_auth_secret/client_secret.json`]: '{"installed":{}}',
    [PLUGIN]: '',
  })
  const logins: string[][] = []
  on('process.run', (_: unknown, e: { argv: string[] }) => {
    if (e.argv.includes('-c')) logins.push(e.argv)

    return { value: { exitCode: 1, stdout: '', stderr: '' } }
  })
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })
  await $.command.run({ command: 'yt-setup', args: '' })
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
