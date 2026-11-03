import type { Examples, Spec } from '../types'

type Action = { kind: 'panel'; title: string } | { kind: 'sample'; match: string } | { kind: 'spec'; id: string }

const CASES: { id: string; tag: string; title: string; text: string; action: Action; cta: string }[] = [
  { id: 'sketch', tag: 'Sketch to code', title: 'A photo becomes a verified result', text: 'Draw a circuit on paper or a board and take a photo: code, a noisy run and an independent check in seconds.', action: { kind: 'sample', match: 'ghz' }, cta: 'Read a sample sketch' },
  { id: 'hardware', tag: 'Real hardware', title: 'Will it run on a real chip?', text: 'Phase estimation under realistic noise: error budget, chip layouts, a shorter proven-equal circuit.', action: { kind: 'spec', id: 'phase_estimation' }, cta: 'Open it in the editor' },
  { id: 'evidence', tag: 'Trust', title: 'Can the AI be trusted?', text: 'We measured where the model alone goes wrong. Here, nothing reaches you unchecked.', action: { kind: 'panel', title: 'AI alone vs Inkubit' }, cta: 'See the evidence' },
  { id: 'network', tag: 'Satellite networks', title: 'A satellite link, fixed', text: 'Ground stations and a satellite: find the weakest link and the fix that helps most.', action: { kind: 'spec', id: 'network_satellite' }, cta: 'Plan the link' },
  { id: 'shor', tag: 'Cryptography', title: 'How Shor breaks RSA', text: 'Factor 15 from a measured period, and see why noise makes it hard today.', action: { kind: 'panel', title: "Shor's algorithm lab" }, cta: 'Factor 15' },
  { id: 'molecule', tag: 'Chemistry', title: 'The energy of a molecule', text: 'H₂ from first principles: where the classical shortcut fails and VQE does not.', action: { kind: 'panel', title: 'Molecule lab' }, cta: 'Open the molecule lab' },
  { id: 'qkd', tag: 'Quantum security', title: 'Keys a spy cannot copy', text: 'BB84: slide an eavesdropper in and watch the error rate give her away.', action: { kind: 'panel', title: 'Catch the spy' }, cta: 'Catch the spy' },
  { id: 'qaoa', tag: 'Optimization', title: 'Seat, schedule, route', text: 'Max-Cut with QAOA: the shape of scheduling and routing problems, on a graph you draw.', action: { kind: 'panel', title: 'Split the party' }, cta: 'Split the party' },
  { id: 'bughunt', tag: 'Debugging', title: 'Find the one wrong gate', text: 'Spot the planted bug from the histogram alone, against the clock and against Muse Spark.', action: { kind: 'panel', title: 'Bug hunt' }, cta: 'Play bug hunt' },
]

export function scrollToPanel(title: string, retried = false) {
  const h = [...document.querySelectorAll<HTMLElement>('.panel h2')].find((el) => el.offsetParent !== null && el.textContent?.startsWith(title))
  const panel = h?.closest('.panel') as HTMLElement | null
  if (!panel) {  // in another section: ask the page to open it, then come back here
    if (!retried) window.dispatchEvent(new CustomEvent('inkubit:goto', { detail: title }))
    return
  }
  panel.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' })
  panel.classList.remove('flash')
  void panel.offsetWidth
  panel.classList.add('flash')
  holdInView(panel)
}

let releaseHold: (() => void) | null = null

/** Keep a panel at the top while the panels above it finish loading (they grow and would push it down), for up to
 *  15 s or until the visitor scrolls, clicks or types themselves. */
function holdInView(panel: HTMLElement, ms = 15000) {
  releaseHold?.()
  const margin = parseFloat(getComputedStyle(panel).scrollMarginTop) || 0
  const ro = new ResizeObserver(() => {
    if (panel.offsetParent === null) return release()  // its section was closed
    const top = panel.getBoundingClientRect().top
    if (Math.abs(top - margin) > 12) window.scrollBy({ top: top - margin, behavior: 'auto' })
  })
  const stop = ['wheel', 'touchstart', 'keydown', 'pointerdown'] as const
  const timer = window.setTimeout(() => release(), ms)
  function release() {
    ro.disconnect()
    window.clearTimeout(timer)
    stop.forEach((ev) => window.removeEventListener(ev, release, true))
    if (releaseHold === release) releaseHold = null
  }
  ro.observe(document.body)
  stop.forEach((ev) => window.addEventListener(ev, release, true))
  releaseHold = release
}

/** What Inkubit does, each with one click into the part of the app that does it. */
export function UseCases({ examples, onImage, onSpec, busy }: {
  examples: Examples | null; onImage: (b: Blob, name: string) => void; onSpec: (s: Spec) => void; busy?: boolean
}) {
  const run = async (a: Action) => {
    if (a.kind === 'panel') return scrollToPanel(a.title)
    if (a.kind === 'spec') {
      const ex = examples?.specs.find((s) => s.id === a.id)
      if (ex) onSpec(JSON.parse(JSON.stringify(ex.spec)))
      return
    }
    const img = examples?.images.find((i) => i.id.includes(a.match)) ?? examples?.images[0]
    if (img) onImage(await (await fetch(img.url)).blob(), `${img.id}.png`)
  }
  return (
    <div className="panel">
      <div className="panel-head"><h2>What it can do</h2><span className="spacer" />
        <span className="sub">drawn by Muse Image</span></div>
      <div className="uc-grid">
        {CASES.map((c) => (
          <button key={c.id} className="uc-card" onClick={() => { void run(c.action) }} disabled={busy && c.action.kind !== 'panel'}>
            <img className="uc-img" src={`/usecases/${c.id}.webp`} alt="" loading="lazy" width={720} height={405}
              onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }} />
            <span className="uc-who">{c.tag}</span>
            <span className="uc-title">{c.title}</span>
            <span className="uc-text">{c.text}</span>
            <span className="uc-cta">{c.cta}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
