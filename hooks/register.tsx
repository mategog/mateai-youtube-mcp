import type { Hook, Register } from 'claude-code'

type Api = Parameters<Hook<'session.start'>>[0]

// yt-studio keeps its login files in its plugin data folder (override: MATEAI_YT_HOME).
const DATA_NAME = 'yt-studio-mateai-youtube-mcp'
const NEEDED_SCOPES = [
  'https://www.googleapis.com/auth/youtube.readonly',
  'https://www.googleapis.com/auth/yt-analytics.readonly',
  'https://www.googleapis.com/auth/youtube.upload',
  'https://www.googleapis.com/auth/youtube',
  'https://www.googleapis.com/auth/youtube.force-ssl',
]
const CONSOLE_PAGES = [
  'https://console.cloud.google.com/auth/clients/create',
  'https://console.cloud.google.com/auth/audience',
]

type Paths = { home: string; data: string; secret: string; token: string; venvPython: string }

const paths = async ($: Api): Promise<Paths> => {
  const home = (await $.env.get('HOME')) ?? ''
  const data = (await $.env.get('MATEAI_YT_HOME')) ?? `${home}/.claude/plugins/data/${DATA_NAME}`

  return {
    home,
    data,
    secret: `${data}/google_auth_secret/client_secret.json`,
    token: `${data}/.tokens/token.json`,
    venvPython: `${data}/.venv/bin/python`,
  }
}

// 'ok' = logged in with every scope the plugin needs; 'scopes' = logged in, too few scopes.
const loginState = async ($: Api, p: Paths): Promise<'ok' | 'scopes' | 'none'> => {
  if (!(await $.fs.exists(p.token))) return 'none'
  try {
    const token = JSON.parse(await $.fs.read(p.token)) as { scopes?: string[] }
    const have = token.scopes ?? []

    return NEEDED_SCOPES.every(s => have.includes(s)) ? 'ok' : 'scopes'
  } catch {
    return 'none'
  }
}

const pluginRoot = async ($: Api, p: Paths): Promise<string | undefined> => {
  const base = `${p.home}/.claude/plugins/cache/mateai-youtube-mcp/yt-studio`
  if (!(await $.fs.exists(base))) return undefined
  const versions = (await $.fs.list(base)).filter(e => e.kind === 'dir').map(e => e.name)
  const num = (v: string) => v.split('.').map(Number)
  versions.sort((a, b) => {
    const [x, y] = [num(a), num(b)]

    return (x[0] - y[0]) || (x[1] - y[1]) || (x[2] - y[2])
  })
  const newest = versions[versions.length - 1]

  return newest === undefined ? undefined : `${base}/${newest}`
}

// Looks for a Desktop-app client_secret*.json in the data folder, this project and Downloads.
const findSecret = async ($: Api, p: Paths, cwd: string): Promise<string | undefined> => {
  if (await $.fs.exists(p.secret)) return p.secret
  const found = await $.process.run(
    [
      'find', cwd, `${p.home}/Downloads`, '-maxdepth', '5',
      '-name', 'client_secret*.json',
      '-not', '-path', '*/node_modules/*', '-not', '-path', '*/.venv/*',
    ],
    { timeoutMs: 20000 },
  ).catch(() => undefined)
  const lines = (found?.stdout ?? '').split('\n').map(s => s.trim()).filter(Boolean)

  return lines[0]
}

const LOGIN_CODE = [
  'import yt_studio as y, sys',
  'y.get_oauth_credentials(upload_scope=True, force_reauth=sys.argv[1] == "1")',
  'print("LOGIN_OK")',
].join('\n')

const connect = async ($: Api, p: Paths, root: string, state: 'none' | 'scopes') => {
  const env = { MATEAI_YT_HOME: p.data }
  if (!(await $.fs.exists(p.venvPython))) {
    $.ui.toast('yt-setup: installing Google libraries (about a minute)…')
    const venv = await $.process.run(['python3', '-m', 'venv', `${p.data}/.venv`], { timeoutMs: 120000 })
    const pip = venv.exitCode === 0
      ? await $.process.run(
          [p.venvPython, '-m', 'pip', 'install', '-q', '-r', `${root}/requirements.txt`],
          { timeoutMs: 300000 },
        )
      : venv
    if (pip.exitCode !== 0) {
      $.ui.toast(`yt-setup: could not install the Google libraries: ${pip.stderr.trim().slice(-200)}`)

      return
    }
  }
  $.ui.toast('yt-setup: your browser is opening. Sign in and click Allow.')
  const login = await $.process.run(
    [p.venvPython, '-c', LOGIN_CODE, state === 'scopes' ? '1' : '0'],
    { cwd: root, env, timeoutMs: 600000 },
  ).catch((err: unknown) => ({ exitCode: 1, stdout: '', stderr: String(err) }))
  const isOk = login.exitCode === 0 && (await loginState($, p)) === 'ok'
  $.ui.status(isOk ? undefined : 'YouTube: not connected, run /yt-setup')
  $.ui.toast(
    isOk
      ? 'yt-setup: connected! YouTube tools are ready.'
      : `yt-setup: login did not finish. ${login.stderr.trim().slice(-200)}`,
  )
}

export const register: Register = on => {
  let projectDir = '.'

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'yt-setup',
      description: 'Connect the yt-studio plugin to your YouTube account (one-time)',
    })
    projectDir = e.cwd
    const p = await paths($)
    if ((await loginState($, p)) !== 'ok') $.ui.status('YouTube: not connected, run /yt-setup')

    return next(e)
  })

  on('command.run', { command: 'yt-setup' }, async $ => {
    const p = await paths($)
    const state = await loginState($, p)
    if (state === 'ok') {
      $.ui.status(undefined)

      return { text: 'Already connected. Nothing to do. (To log in again, delete the .tokens folder in the yt-studio data folder and rerun /yt-setup.)' }
    }

    const root = await pluginRoot($, p)
    if (root === undefined) {
      return { text: 'The yt-studio plugin is not installed. Install it first with: /plugin install yt-studio@mateai-youtube-mcp' }
    }

    const secret = await findSecret($, p, projectDir)
    if (secret === undefined) {
      for (const url of CONSOLE_PAGES) await $.process.run(['open', url]).catch(() => undefined)

      return {
        text: [
          'One manual step first (Google requires it, nothing can automate it).',
          'I opened two Google pages. In them:',
          '  1. "Audience": add your YouTube email under Test users.',
          '  2. "Create client": choose Application type = Desktop app, click Create, then Download JSON.',
          'Leave the file in Downloads, then run /yt-setup again.',
        ].join('\n'),
      }
    }

    if (secret !== p.secret) {
      let kind = ''
      try {
        kind = Object.keys(JSON.parse(await $.fs.read(secret)) as object)[0] ?? ''
      } catch {
        return { text: `Found ${secret} but it is not valid JSON. Download the client file again.` }
      }
      if (kind !== 'installed') {
        return { text: `Found ${secret} but it is a "${kind}" client. Create a Desktop app client instead.` }
      }
      await $.fs.write(p.secret, await $.fs.read(secret))
      await $.process.run(['chmod', '600', p.secret])
    }

    // The login waits for the person in the browser, so it runs on after this answer.
    void connect($, p, root, state)

    return { text: `Found your Google client file. Opening your browser: sign in with the YouTube account, click Allow, and wait for the "connected" message.${secret === p.secret ? '' : `\n(Copied ${secret} into the plugin folder, permissions 600.)`}` }
  })
}
