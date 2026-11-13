import type { Hook, Register } from 'claude-code'

import { dashboardCommand, register as registerDashboard } from './dashboard'

type Api = Parameters<Hook<'session.start'>>[0]

// yt-studio keeps its login files in its plugin data folder (override: MATEAI_YT_HOME).
const DATA_NAME = 'yt-studio-mateai-youtube-mcp'
const NEEDED_SCOPES = [
  'https://www.googleapis.com/auth/youtube.readonly',
  'https://www.googleapis.com/auth/yt-analytics.readonly',
  'https://www.googleapis.com/auth/youtube.force-ssl',
]
const CONSOLE_PAGES = [
  'https://console.cloud.google.com/auth/clients/create',
  'https://console.cloud.google.com/auth/audience',
]

type Paths = {
  isWindows: boolean
  home: string
  data: string
  secret: string
  token: string
  expired: string
  venvPython: string
}

// Windows sets OS=Windows_NT for every process, and has USERPROFILE where macOS/Linux have HOME.
const isWindowsEnv = async ($: Api): Promise<boolean> => (await $.env.get('OS')) === 'Windows_NT'

const paths = async ($: Api): Promise<Paths> => {
  const isWindows = await isWindowsEnv($)
  const home = (isWindows ? (await $.env.get('USERPROFILE')) ?? (await $.env.get('HOME')) : await $.env.get('HOME')) ?? ''
  const data = (await $.env.get('MATEAI_YT_HOME')) ?? `${home}/.claude/plugins/data/${DATA_NAME}`

  return {
    isWindows,
    home,
    data,
    secret: `${data}/google_auth_secret/client_secret.json`,
    token: `${data}/.tokens/token.json`,
    expired: `${data}/.tokens/expired`,
    // A Windows venv keeps its interpreter in Scripts\python.exe, not bin/python.
    venvPython: isWindows ? `${data}/.venv/Scripts/python.exe` : `${data}/.venv/bin/python`,
  }
}

// 'ok' = logged in with every scope the plugin needs; 'scopes' = logged in, too few scopes;
// 'expired' = the Python side marked the saved login dead (Google refused to renew it).
const loginState = async ($: Api, p: Paths): Promise<'ok' | 'scopes' | 'expired' | 'none'> => {
  if (!(await $.fs.exists(p.token))) return 'none'
  try {
    const token = JSON.parse(await $.fs.read(p.token)) as { scopes?: string[] }
    const have = token.scopes ?? []

    if (!NEEDED_SCOPES.every(s => have.includes(s))) return 'scopes'

    return (await $.fs.exists(p.expired)) ? 'expired' : 'ok'
  } catch {
    return 'none'
  }
}

// MateAI Studio's YouTube login (macOS Keychain). The Python side falls back to it when the plugin has no
// login of its own, so one Connect covers both; /yt-setup still signs the plugin in to any account.
// No -w: this only asks whether the item exists, never reads the token, so macOS shows no prompt. MATEAI_DESKTOP_LOGIN=off and MATEAI_TOKEN_BACKEND=keyring turn it off, as in yt_auth.py.
const usesKeyring = async ($: Api) => ((await $.env.get('MATEAI_TOKEN_BACKEND')) ?? '').trim().toLowerCase() === 'keyring'

const hasAppLogin = async ($: Api): Promise<boolean> => {
  const off = ['off', '0', 'false'].includes(((await $.env.get('MATEAI_DESKTOP_LOGIN')) ?? '').trim().toLowerCase())
  if (off || (await usesKeyring($)) || !(await $.fs.exists('/usr/bin/security'))) return false
  const found = await $.process.run(
    ['/usr/bin/security', 'find-generic-password', '-s', 'dev.mateai.desktop', '-a', 'google-oauth-token'],
    { timeoutMs: 10000 },
  ).catch(() => undefined)

  return found?.exitCode === 0
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

const SKIP_DIRS = new Set(['node_modules', '.venv'])
const isSecretName = (name: string) => /^client_secret.*\.json$/.test(name)

// Windows has no POSIX `find` (its find.exe searches text), so walk the folders with $.fs.list,
// to the same depth as `find -maxdepth 5`.
const walkForSecret = async ($: Api, dir: string, depth: number): Promise<string | undefined> => {
  const entries = await $.fs.list(dir).catch(() => [])
  const file = entries.find(e => e.kind === 'file' && isSecretName(e.name))
  if (file !== undefined) return `${dir}/${file.name}`
  if (depth <= 1) return undefined
  for (const e of entries) {
    if (e.kind !== 'dir' || SKIP_DIRS.has(e.name)) continue
    const found = await walkForSecret($, `${dir}/${e.name}`, depth - 1)
    if (found !== undefined) return found
  }

  return undefined
}

// Looks for a Desktop-app client_secret*.json in the data folder, this project and Downloads.
const findSecret = async ($: Api, p: Paths, cwd: string): Promise<string | undefined> => {
  if (await $.fs.exists(p.secret)) return p.secret
  if (p.isWindows) {
    for (const root of [cwd, `${p.home}/Downloads`]) {
      const found = await walkForSecret($, root, 5)
      if (found !== undefined) return found
    }

    return undefined
  }
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

const DISCONNECT_CODE = [
  'import yt_auth, json, sys',
  'print(json.dumps(yt_auth.disconnect(revoke=sys.argv[1] == "1")))',
].join('\n')

const NOT_CONNECTED = 'YouTube is not connected. Nothing to do.'
const STUDIO_LOGIN = 'This plugin uses your MateAI Studio login. To use another account in the plugin, run /yt-setup and pick it in Google\'s account chooser. To disconnect Studio\'s login, open MateAI Studio and disconnect YouTube there.'
const PERMISSIONS = 'https://myaccount.google.com/permissions'

// Revokes the plugin's own login at Google (best effort) and deletes it; yt_auth.disconnect() does both.
// With a MateAI Studio login it only deletes: the built-in client is Studio's, and Google revokes the
// whole user+client grant, so a revoke here would sign Studio out too.
const disconnect = async ($: Api) => {
  const p = await paths($)
  const appLogin = await hasAppLogin($)
  if (!(await usesKeyring($)) && !(await $.fs.exists(p.token))) return { text: appLogin ? STUDIO_LOGIN : NOT_CONNECTED }

  const root = await pluginRoot($, p)
  if (root === undefined) {
    return { text: 'The yt-studio plugin is not installed. Install it first with: /plugin install yt-studio@mateai-youtube-mcp' }
  }
  const python = (await $.fs.exists(p.venvPython)) ? p.venvPython : 'python3'
  const run = await $.process.run(
    [python, '-c', DISCONNECT_CODE, appLogin ? '0' : '1'],
    { cwd: root, env: { MATEAI_YT_HOME: p.data }, timeoutMs: 60000 },
  ).catch((err: unknown) => ({ exitCode: 1, stdout: '', stderr: String(err) }))
  let result: { had_login?: boolean; revoked?: boolean } | undefined
  try {
    result = JSON.parse(run.stdout.trim().split('\n').pop() ?? '')
  } catch {}
  if (run.exitCode !== 0 || result === undefined) {
    return {
      text: `Could not disconnect: ${run.stderr.trim().slice(-200)}\nTo do it by hand, delete ${p.token} and remove access at ${PERMISSIONS}.`,
    }
  }
  if (!result.had_login) return { text: appLogin ? STUDIO_LOGIN : NOT_CONNECTED }

  if (appLogin) {
    return {
      text: `Removed the plugin's own YouTube login from this computer. Google access was not revoked, because MateAI Studio uses the same Google sign-in and a revoke would sign Studio out too. The plugin now falls back to your MateAI Studio login. To use another account in the plugin, run /yt-setup and pick it in Google's account chooser. To cut Google access fully, disconnect YouTube in MateAI Studio (that revokes it) or remove access at ${PERMISSIONS}.`,
    }
  }
  $.ui.status('YouTube: not connected, run /yt-setup')

  return {
    text: [
      result.revoked
        ? 'Disconnected. Google revoked access and the saved login was removed from this computer.'
        : `The saved login was removed from this computer, but Google did not confirm the revoke (offline, or the login was already invalid). To be sure, remove access at ${PERMISSIONS}.`,
      'To connect another account or channel, run /yt-setup and pick it in Google\'s account chooser.',
    ].join('\n'),
  }
}

const connect = async ($: Api, p: Paths, root: string, state: 'none' | 'scopes' | 'expired', force = false) => {
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
    [p.venvPython, '-c', LOGIN_CODE, force || state === 'scopes' || state === 'expired' ? '1' : '0'],
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

const registerSetup: Register = on => {
  let projectDir = '.'

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'yt-setup',
      description: 'Connect the yt-studio plugin to your YouTube account (one-time)',
    })
    await $.command.register({
      name: 'yt-disconnect',
      description: 'Sign the yt-studio plugin out of YouTube and revoke its access at Google',
    })
    await $.command.register(dashboardCommand)
    projectDir = e.cwd
    const p = await paths($)
    // The plugin's own login wins over Studio's, so only a missing one falls back to Studio's.
    const state = await loginState($, p)
    if (state !== 'ok' && (state !== 'none' || !(await hasAppLogin($)))) $.ui.status('YouTube: not connected, run /yt-setup')

    return next(e)
  })

  on('command.run', { command: 'yt-disconnect' }, async $ => disconnect($))

  on('command.run', { command: 'yt-setup' }, async $ => {
    const p = await paths($)
    const state = await loginState($, p)
    if (state === 'ok') {
      $.ui.status(undefined)

      return { text: 'Already connected. To sign out or switch to another channel, run /yt-disconnect, then /yt-setup.' }
    }

    const root = await pluginRoot($, p)
    if (root === undefined) {
      return { text: 'The yt-studio plugin is not installed. Install it first with: /plugin install yt-studio@mateai-youtube-mcp' }
    }

    // The plugin ships a verified Google client (oauth_client.json), so sign-in needs no Google Cloud
    // steps. A client file of the user's own in the data folder still wins (yt_auth.py picks it).
    if (!(await $.fs.exists(p.secret)) && (await $.fs.exists(`${root}/oauth_client.json`))) {
      // force: yt_auth.py starts a built-in-client sign-in only for setup, never from a tool call.
      void connect($, p, root, state, true)

      return { text: 'Opening your browser: sign in with the YouTube account, click Allow, and wait for the "connected" message.' }
    }

    const secret = await findSecret($, p, projectDir)
    if (secret === undefined) {
      // `open` is macOS; on Windows, url.dll opens the default browser without a shell to quote for.
      const opener = p.isWindows ? ['rundll32', 'url.dll,FileProtocolHandler'] : ['open']
      for (const url of CONSOLE_PAGES) await $.process.run([...opener, url]).catch(() => undefined)

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
      // Windows has no chmod; the data folder in the user's profile is already private to that user.
      if (!p.isWindows) await $.process.run(['chmod', '600', p.secret])
    }

    // The login waits for the person in the browser, so it runs on after this answer. Force it over a
    // MateAI Studio login, or yt_auth.py would just return Studio's login and open no browser.
    void connect($, p, root, state, await hasAppLogin($))

    return { text: `Found your Google client file. Opening your browser: sign in with the YouTube account, click Allow, and wait for the "connected" message.${secret === p.secret ? '' : `\n(Copied ${secret} into the plugin folder, ${p.isWindows ? 'private to your Windows user' : 'permissions 600'}.)`}` }
  })
}

// A plugin names exactly one hooks module in hooks.json, so this entry point registers both parts:
// /yt-setup and /yt-disconnect (above) and /yt-dashboard (dashboard.tsx).
export const register: Register = (on, options) => {
  registerSetup(on, options)
  registerDashboard(on, options)
}
