export type Video = {
  videoId: string
  title: string
  format: 'short' | 'long'
  publishDate: string
  views: number
  likes: number
  viewedVsSwipedPct: number | null
  avgViewPct: number | null
  subsGained: number | null
}
export type Snapshot = {
  generatedAt: string
  mode: string
  channel: { handle: string; title: string; subscribersText: string }
  totals: { videoCount: number; shortsCount: number; longCount: number; totalViews: number }
  videos: Video[]
}

const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
const clip = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s)
const tone = (pct: number) => (pct >= 60 ? 'good' : pct >= 30 ? 'ok' : 'bad')

const W = 720
const ROW = 34
const TABLE_Y = 150

// Light and dark palettes follow the system; the card has its own background, so it reads on either.
const STYLE = `
:root{--bg:#1b1e27;--card:#242936;--line:#323949;--text:#eceff4;--mut:#9aa3b5;--good:#3ecf8e;--ok:#f5b84b;--bad:#f2677a;--track:#323949}
@media (prefers-color-scheme: light){:root{--bg:#f6f7fa;--card:#ffffff;--line:#dfe3ea;--text:#1a1d26;--mut:#5b6475;--good:#12805a;--ok:#9a6200;--bad:#c2334d;--track:#e6e9ef}}
text{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif}
.bg{fill:var(--bg)}.card{fill:var(--card);stroke:var(--line)}.line{stroke:var(--line)}.track{fill:var(--track)}
.t{fill:var(--text)}.m{fill:var(--mut)}
.good{fill:var(--good)}.ok{fill:var(--ok)}.bad{fill:var(--bad)}
.chip{fill:var(--track)}
`

export function dashboardSvg(snap: Snapshot, rowCount = 5): string {
  const videos = [...snap.videos].sort((a, b) => b.publishDate.localeCompare(a.publishDate)).slice(0, rowCount)
  const footerY = TABLE_Y + 10 + videos.length * ROW + 24
  const height = footerY + 22
  const subs = snap.channel.subscribersText.replace(/\s*subscribers?/i, '')
  const stale = snap.mode === 'studio_oauth' ? '' : ` · ${snap.mode}`

  const card = (x: number, label: string, value: string) =>
    `<rect class="card" x="${x}" y="72" width="220" height="56" rx="10"/>` +
    `<text class="m" x="${x + 14}" y="93" font-size="12">${esc(label)}</text>` +
    `<text class="t" x="${x + 14}" y="118" font-size="22" font-weight="700">${esc(value)}</text>`

  const rows = videos
    .map((v, i) => {
      const y = TABLE_Y + 10 + i * ROW
      const isShort = v.format === 'short'
      const pct = v.viewedVsSwipedPct
      const meter =
        pct === null
          ? `<text class="m" x="450" y="${y + 22}" font-size="13">no analytics yet</text>`
          : `<rect class="track" x="450" y="${y + 13}" width="180" height="8" rx="4"/>` +
            `<rect class="${tone(pct)}" x="450" y="${y + 13}" width="${Math.max(4, Math.round(pct * 1.8))}" height="8" rx="4"/>` +
            `<text class="${tone(pct)}" x="700" y="${y + 22}" font-size="13" font-weight="600" text-anchor="end">${pct}%</text>`

      return (
        `<line class="line" x1="20" y1="${y}" x2="700" y2="${y}"/>` +
        `<rect class="chip" x="20" y="${y + 8}" width="46" height="18" rx="5"/>` +
        `<text class="m" x="43" y="${y + 21}" font-size="11" font-weight="600" text-anchor="middle">${isShort ? 'SHORT' : 'LONG'}</text>` +
        `<text class="t" x="76" y="${y + 22}" font-size="13.5">${esc(clip(v.title, 38))}</text>` +
        `<text class="t" x="430" y="${y + 22}" font-size="13.5" text-anchor="end">${v.views}</text>` +
        meter
      )
    })
    .join('')

  const legend = (x: number, cls: string, label: string) =>
    `<circle class="${cls}" cx="${x}" cy="${footerY - 4}" r="4"/><text class="m" x="${x + 10}" y="${footerY}" font-size="12">${label}</text>`

  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${height}" width="${W}" height="${height}" role="img">` +
    `<style>${STYLE}</style>` +
    `<rect class="bg" width="${W}" height="${height}" rx="14"/>` +
    `<text class="t" x="20" y="36" font-size="18" font-weight="700">${esc(snap.channel.title)}</text>` +
    `<text class="m" x="20" y="56" font-size="12.5">${esc(snap.channel.handle)}</text>` +
    `<text class="m" x="700" y="36" font-size="12" text-anchor="end">Snapshot ${esc(snap.generatedAt)}${esc(stale)}</text>` +
    card(20, 'Total views', String(snap.totals.totalViews)) +
    card(250, 'Subscribers', subs) +
    card(480, `Videos · ${snap.totals.shortsCount} Shorts, ${snap.totals.longCount} long`, String(snap.totals.videoCount)) +
    `<text class="m" x="20" y="${TABLE_Y - 2}" font-size="11" font-weight="600" letter-spacing="0.6">LATEST VIDEOS</text>` +
    `<text class="m" x="430" y="${TABLE_Y - 2}" font-size="11" font-weight="600" text-anchor="end" letter-spacing="0.6">VIEWS</text>` +
    `<text class="m" x="450" y="${TABLE_Y - 2}" font-size="11" font-weight="600" letter-spacing="0.6">VIEWED VS SWIPED AWAY</text>` +
    rows +
    legend(20, 'good', '60% or more: strong') +
    legend(190, 'ok', '30–59%: mixed') +
    legend(330, 'bad', 'under 30%: weak') +
    `</svg>`
  )
}
