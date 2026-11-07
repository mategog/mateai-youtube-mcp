import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import { dashboardSvg } from './svg'
import type { Snapshot } from './svg'

const PANE = 'yt-dashboard'
const SNAPSHOT_TOOL = 'mcp__plugin_yt-studio_mateai-youtube__yt_channel_snapshot'
const DATA_NAME = 'yt-studio-mateai-youtube-mcp'

// Bumped when the snapshot tool finishes, so the pane redraws with the new file.
const refreshed = atom({ plugin: 'yt-studio', key: 'refreshed' } as const, 0)
// Whether the compact band above the prompt is shown; /yt-dashboard toggles it.
const bandOn = atom({ plugin: 'yt-studio', key: 'bandOn' } as const, false)

const bar = (pct: number, width: number) => {
  const filled = Math.round((Math.min(100, Math.max(0, pct)) / 100) * width)

  return '█'.repeat(filled) + '░'.repeat(width - filled)
}
const clip = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s)
const num = (n: number | null, suffix = '') => (n === null ? '–' : `${n}${suffix}`)

const BAND_VIDEOS = 5

// The plugin data folder (override: MATEAI_YT_HOME). Windows has USERPROFILE (and OS=Windows_NT) instead of HOME.
const dataDir = async ($: { env: { get: (name: string) => Promise<string | undefined> } }) => {
  const isWindows = (await $.env.get('OS')) === 'Windows_NT'
  const home = (isWindows ? (await $.env.get('USERPROFILE')) ?? (await $.env.get('HOME')) : await $.env.get('HOME')) ?? ''

  return (await $.env.get('MATEAI_YT_HOME')) ?? `${home}/.claude/plugins/data/${DATA_NAME}`
}

// register.tsx registers this command in its session.start hook: one module can't hold two unmatched ones.
export const dashboardCommand = { name: 'yt-dashboard', description: 'Open the YouTube channel dashboard pane' }

export const register: Register = on => {
  on('command.run', { command: 'yt-dashboard' }, async $ => {
    const isOn = !(await read($, bandOn))
    await update($, bandOn, () => isOn)
    if (isOn) await $.ui.open({ id: PANE, title: 'YouTube', columns: 48 })

    return {
      text: isOn
        ? 'YouTube dashboard shown above the prompt. Run /yt-dashboard again to hide it. To refresh, ask Claude to run yt_channel_snapshot.'
        : 'YouTube dashboard hidden.',
    }
  })

  on('tool.call', { tool: SNAPSHOT_TOOL }, async ($, e, next) => {
    const ran = await next(e)
    await update($, refreshed, n => n + 1)

    return ran
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey || !(await read($, bandOn))) return next(e)

    const dir = await dataDir($)

    let snap: Snapshot
    try {
      snap = JSON.parse(await $.fs.read(`${dir}/channel_snapshot.json`)) as Snapshot
    } catch {
      const { Text } = $.ui.resolve(e)

      return <Text dimColor>YouTube: no snapshot yet. Ask Claude to run yt_channel_snapshot.</Text>
    }

    // Desktop, VS Code and mobile draw a vector card; the terminal has no Svg and keeps the text band.
    if (e.surface !== 'terminal') {
      const { Svg } = $.ui.resolve(e)

      return <Svg source={dashboardSvg(snap, BAND_VIDEOS)} alt={`YouTube dashboard for ${snap.channel.title}`} />
    }

    const { Box, Text } = $.ui.resolve(e)

    const latest = [...snap.videos].sort((a, b) => b.publishDate.localeCompare(a.publishDate)).slice(0, BAND_VIDEOS)
    const tone = (pct: number) => (pct >= 60 ? 'success' : pct >= 30 ? 'warning' : 'error')

    return (
      <Box flexDirection="column" borderStyle="round" borderColor="subtle" paddingX={1}>
        <Text>
          <Text weight="bold">{snap.channel.title}</Text>
          <Text dimColor> · {snap.channel.subscribersText} · {snap.totals.totalViews} views · {snap.generatedAt}</Text>
        </Text>
        {latest.map(v => (
          <Box gap={1}>
            <Text dimColor>{v.format === 'short' ? 'S' : 'L'}</Text>
            <Text tabular>{String(v.views).padStart(5)}</Text>
            {v.viewedVsSwipedPct === null ? (
              <Text dimColor>{'no data'.padEnd(16)}</Text>
            ) : (
              <Box gap={1}>
                <Text color={tone(v.viewedVsSwipedPct)}>{bar(v.viewedVsSwipedPct, 10)}</Text>
                <Text tabular>{`${v.viewedVsSwipedPct}%`.padStart(5)}</Text>
              </Box>
            )}
            <Text>{clip(v.title, 44)}</Text>
          </Box>
        ))}
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    await read($, refreshed)

    const dir = await dataDir($)
    const file = `${dir}/channel_snapshot.json`

    let snap: Snapshot
    try {
      snap = JSON.parse(await $.fs.read(file)) as Snapshot
    } catch {
      return <Text dimColor>No snapshot yet. Ask Claude to run yt_channel_snapshot (or run /yt-setup first).</Text>
    }

    const width = Math.max(24, e.props.bodyColumns ?? 44)
    const barWidth = Math.min(14, Math.max(6, width - 24))
    const videos = [...snap.videos].sort((a, b) => b.publishDate.localeCompare(a.publishDate))

    // Every colored bar also prints its number, so color is never the only signal.
    const tone = (pct: number) => (pct >= 60 ? 'success' : pct >= 30 ? 'warning' : 'error')

    return (
      <Box flexDirection="column" gap={1}>
        <Box flexDirection="column">
          <Text weight="bold">{snap.channel.title}</Text>
          <Text dimColor>{clip(`${snap.channel.handle} · ${snap.channel.subscribersText}`, width)}</Text>
        </Box>

        <Box gap={3}>
          <Box flexDirection="column">
            <Text dimColor>Views</Text>
            <Text weight="bold" tabular>{snap.totals.totalViews}</Text>
          </Box>
          <Box flexDirection="column">
            <Text dimColor>Shorts</Text>
            <Text weight="bold" tabular>{snap.totals.shortsCount}</Text>
          </Box>
          <Box flexDirection="column">
            <Text dimColor>Long</Text>
            <Text weight="bold" tabular>{snap.totals.longCount}</Text>
          </Box>
        </Box>

        <Text dimColor>Viewed vs swiped away, newest first</Text>

        {videos.map(v => (
          <Box flexDirection="column">
            <Text>{clip(v.title, width)}</Text>
            <Box gap={1}>
              <Text dimColor tabular>
                {v.format === 'short' ? 'Short' : 'Long'} · {v.publishDate.slice(5)} · {v.views} views
              </Text>
            </Box>
            {v.viewedVsSwipedPct === null ? (
              <Text dimColor>no analytics yet</Text>
            ) : (
              <Box gap={1}>
                <Text color={tone(v.viewedVsSwipedPct)}>{bar(v.viewedVsSwipedPct, barWidth)}</Text>
                <Text tabular>{num(v.viewedVsSwipedPct, '%')}</Text>
              </Box>
            )}
          </Box>
        ))}

        <Text dimColor>Snapshot {snap.generatedAt}</Text>
        <Text dimColor>Green 60%+, yellow 30%+, red below.</Text>
      </Box>
    )
  })
}
