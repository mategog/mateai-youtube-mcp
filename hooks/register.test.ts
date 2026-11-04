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

const stub = (on: any, files: Record<string, string>, hints?: Array<string | undefined>) => {
  on('command.register', () => ({ value: { command: 'yt-setup' } }))
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

test('refuses a client file of the wrong type without copying it', async ($, on) => {
  stub(on, { [PLUGIN]: '', '/proj/client_secret_x.json': '{"web":{}}' })
  on('process.run', () => ({
    value: { exitCode: 0, stdout: '/proj/client_secret_x.json\n', stderr: '' },
  }))
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })

  const out = await $.command.run({ command: 'yt-setup', args: '' })

  expect(out.text).toMatch(/"web" client/)
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
