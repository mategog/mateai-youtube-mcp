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

const stub = (on: any, files: Record<string, string>) => {
  on('command.register', () => ({ value: { command: 'yt-setup' } }))
  on('session.start', (_: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  on('env.get', (_: unknown, e: { name: string }) => ({
    value: e.name === 'HOME' ? '/home/u' : undefined,
  }))
  on('fs.exists', (_: unknown, e: { path: string }) => ({ value: e.path in files }))
  on('fs.read', (_: unknown, e: { path: string }) => ({ value: files[e.path] }))
  on('fs.list', () => ({ value: [{ name: '1.0.5', kind: 'dir', size: 0, mtimeMs: 0, isLink: false }] }))
  on('ui.status', () => ({ value: undefined }))
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
