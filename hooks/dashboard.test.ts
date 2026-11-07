import { expect, test } from 'claude-code/testing'

const PANE_PROPS = {
  title: 'YouTube',
  isFocused: false,
  bodyColumns: 44,
  placement: 'dock',
  scroll: { offset: 0, bodyRows: 20 },
  view: {},
} as const

const DATA = '/home/u/.claude/plugins/data/yt-studio-mateai-youtube-mcp'

const snapshot = JSON.stringify({
  generatedAt: '2026-11-03 12:16 UTC',
  mode: 'studio_oauth',
  channel: { handle: '@mateai-c6m', title: 'MateAI', subscribersText: '11 subscribers' },
  totals: { videoCount: 1, shortsCount: 1, longCount: 0, totalViews: 51 },
  videos: [
    { videoId: 'a', title: 'Google Built a World', format: 'short', publishDate: '2026-10-28', views: 51, likes: 0, viewedVsSwipedPct: 66.7, avgViewPct: 90.5, subsGained: 0 },
  ],
})

const stub = (on: any, files: Record<string, string>, env: Record<string, string> = { HOME: '/home/u' }) => {
  on('env.get', (_: unknown, e: { name: string }) => ({ value: env[e.name] }))
  on('fs.read', (_: unknown, e: { path: string }) => {
    if (!(e.path in files)) throw new Error('missing')

    return { value: files[e.path] }
  })
}

test('pane shows channel totals and the viewed-vs-swiped number', async ($, on) => {
  stub(on, { [`${DATA}/channel_snapshot.json`]: snapshot })

  const ui = await $.ui.mount({ plugin: 'yt-studio', surface: 'terminal', component: 'Pane', requestId: 'yt-dashboard', props: PANE_PROPS })

  expect(await ui.find({ type: 'Text', text: '11 subscribers' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: '66.7%' })).toBeDefined()
})

test('pane explains how to get a first snapshot when none exists', async ($, on) => {
  stub(on, {})

  const ui = await $.ui.mount({ plugin: 'yt-studio', surface: 'terminal', component: 'Pane', requestId: 'yt-dashboard', props: PANE_PROPS })

  expect(await ui.find({ type: 'Text', text: 'No snapshot yet' })).toBeDefined()
})

import { dashboardSvg } from './svg'

test('svg card escapes titles and shows the percentage as text', () => {
  const snap = JSON.parse(snapshot)
  snap.videos[0].title = 'A & B <C>'
  const svg = dashboardSvg(snap)

  expect(svg).toContain('A &amp; B &lt;C&gt;')
  expect(svg).toContain('66.7%')
})

test('Windows: reads the snapshot from the USERPROFILE data folder', async ($, on) => {
  // The test host resolves paths POSIX-style, so the Windows profile is written as /win/u.
  stub(on, { '/win/u/.claude/plugins/data/yt-studio-mateai-youtube-mcp/channel_snapshot.json': snapshot }, {
    OS: 'Windows_NT', USERPROFILE: '/win/u',
  })

  const ui = await $.ui.mount({ plugin: 'yt-studio', surface: 'terminal', component: 'Pane', requestId: 'yt-dashboard', props: PANE_PROPS })

  expect(await ui.find({ type: 'Text', text: '11 subscribers' })).toBeDefined()
})
