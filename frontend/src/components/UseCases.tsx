import type { Examples, Spec } from '../types'

type Action = { kind: 'panel'; title: string } | { kind: 'sample'; match: string } | { kind: 'spec'; id: string }

const CASES: { who: string; title: string; text: string; action: Action; cta: string }[] = [
  { who: 'Teacher', title: 'Board photo to a verified result', text: 'Draw on the board, take a photo: the class sees the code, the run and the check in seconds.', action: { kind: 'sample', match: 'ghz' }, cta: 'Read a sample sketch' },
  { who: 'Student', title: 'Learn by debugging', text: 'Find the one wrong gate from the histogram, against the clock and against Muse Spark.', action: { kind: 'panel', title: 'Bug hunt' }, cta: 'Play bug hunt' },
  { who: 'Chemist', title: 'The energy of a molecule', text: 'H₂ from first principles: where the classical shortcut fails and VQE does not.', action: { kind: 'panel', title: 'Molecule lab' }, cta: 'Open the molecule lab' },
  { who: 'Security', title: 'Keys a spy cannot copy', text: 'BB84: slide an eavesdropper in and watch the error rate give her away.', action: { kind: 'panel', title: 'Catch the spy' }, cta: 'Catch the spy' },
  { who: 'Logistics', title: 'Seat, schedule, route', text: 'Max-Cut with QAOA: the shape of scheduling and routing problems, on a graph you draw.', action: { kind: 'panel', title: 'Split the party' }, cta: 'Split the party' },
  { who: 'Network planner', title: 'A satellite link, fixed', text: 'Ground stations and a satellite: find the weakest link and the fix that helps most.', action: { kind: 'spec', id: 'network_satellite' }, cta: 'Plan the link' },
  { who: 'Cryptography', title: 'How Shor breaks RSA', text: 'Factor 15 from a measured period, and see why noise makes it hard today.', action: { kind: 'panel', title: "Shor's algorithm lab" }, cta: 'Factor 15' },
  { who: 'Researcher', title: 'Will it run on real hardware?', text: 'Phase estimation under realistic noise: error budget, chip layouts, a shorter proven-equal circuit.', action: { kind: 'spec', id: 'phase_estimation' }, cta: 'Open it in the editor' },
  { who: 'Skeptic', title: 'Can the AI be trusted?', text: 'We measured where the model alone goes wrong. Here, nothing reaches you unchecked.', action: { kind: 'panel', title: 'AI alone vs Q-Canvas' }, cta: 'See the evidence' },
]

function scrollToPanel(title: string) {
  const h = [...document.querySelectorAll('.panel h2')].find((el) => el.textContent?.startsWith(title))
  const panel = h?.closest('.panel') as HTMLElement | null
  if (!panel) return
  panel.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' })
  panel.classList.remove('flash')
  void panel.offsetWidth
  panel.classList.add('flash')
}

/** Who Q-Canvas is for, each with one click into the part of the app that does it. */
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
      <div className="panel-head"><h2>Who it is for</h2><span className="sub">one click into each use</span><span className="spacer" />
        <span className="sub">photos: Muse Image 1.0</span></div>
      <div className="uc-grid">
        {CASES.map((c) => (
          <button key={c.who} className="uc-card" onClick={() => { void run(c.action) }} disabled={busy && c.action.kind !== 'panel'}>
            <img className="uc-img" src={`/usecases/${c.who.split(' ')[0].toLowerCase()}.webp`} alt="" loading="lazy" width={720} height={405}
              onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }} />
            <span className="uc-who">{c.who}</span>
            <span className="uc-title">{c.title}</span>
            <span className="uc-text">{c.text}</span>
            <span className="uc-cta">{c.cta} →</span>
          </button>
        ))}
      </div>
    </div>
  )
}
