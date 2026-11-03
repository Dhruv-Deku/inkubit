// Mirrors the backend's JSON shapes (backend/inkubit/**). Keep in sync by hand.

export type Bbox = [number, number, number, number]

export interface SourceRef {
  bbox: Bbox
  confidence: number
  segment_id?: string | null
}

export type Gate =
  | 'H' | 'X' | 'Y' | 'Z' | 'S' | 'T' | 'SDG' | 'TDG' | 'SX' | 'RX' | 'RY' | 'RZ'
  | 'CX' | 'CZ' | 'CP' | 'SWAP' | 'CCX' | 'MEASURE' | 'BARRIER'

export const GATES: Gate[] = ['H', 'X', 'Y', 'Z', 'S', 'T', 'SDG', 'TDG', 'SX', 'RX', 'RY', 'RZ', 'CX', 'CZ', 'CP', 'SWAP', 'CCX', 'MEASURE', 'BARRIER']

/** How a gate is written on screen (S† rather than SDG). */
export const GATE_LABEL: Partial<Record<Gate, string>> = { SDG: 'S†', TDG: 'T†', SX: '√X', CCX: 'CCX (Toffoli)', CP: 'CP (phase)', MEASURE: 'Measure (mid-circuit)' }

export interface Operation {
  gate: Gate
  targets: number[]
  controls?: number[]
  params?: number[]
  clbits?: number[]
  /** Feed-forward: run only when the classical bit (written by an earlier MEASURE) reads this value. */
  conditional?: { classical_register: number; value: 0 | 1 } | null
  source?: SourceRef | null
}

export interface Metadata {
  title?: string | null
  notes?: string | null
  origin?: 'image' | 'text' | 'manual'
}

export interface CircuitSpec {
  kind: 'circuit'
  version: string
  num_qubits: number
  num_clbits: number
  operations: Operation[]
  measurements: { qubit: number; clbit: number }[]
  metadata?: Metadata
}

export interface NetNode {
  id: string
  type: 'ground_station' | 'satellite' | 'repeater'
  label?: string | null
  position?: { x: number; y: number } | null
  memory_t2_ms?: number | null
  source?: SourceRef | null
}

export interface NetLink {
  from: string
  to: string
  medium: 'fiber' | 'free_space'
  length_km: number
  loss_db?: number | null
  depolarizing?: number | null
  source?: SourceRef | null
}

export interface NetworkSpec {
  kind: 'network'
  version: string
  nodes: NetNode[]
  links: NetLink[]
  source: string
  destination: string
  purification_rounds?: number
  metadata?: Metadata
}

export type Spec = CircuitSpec | NetworkSpec

export interface SpecIssue {
  path: string
  message: string
}

export interface ModelCall {
  provider: 'meta' | 'mock' | 'mock-fallback'
  model: string
  role: string
  cached: boolean
  latency_s: number
  error?: string | null
}

export interface Segment {
  id: string
  concept: string
  bbox: Bbox
  confidence: number
}

export interface OverlayBox {
  segment_id: string
  concept: string
  bbox: Bbox
  confidence: number
  linked_to: string | null
  label: string
}

export interface SketchAnalysis {
  image_sha256: string
  mime: string
  width: number
  height: number
  kind: 'circuit' | 'network'
  concepts: string[]
  segments: Segment[]
  spec: Spec
  valid: boolean
  issues: string[]
  notes: string
  overlay: OverlayBox[]
  calls: ModelCall[]
}

export type Status = 'info' | 'running' | 'ok' | 'fail' | 'warn'

export interface AgentEvent {
  seq: number
  timestamp: string
  step: string
  status: Status
  message: string
  attempt: number | null
  details: Record<string, unknown>
}

export type Distribution = Record<string, number>

export interface Verdict {
  passed: boolean
  noise: string
  metrics: {
    shots: number
    tvd: number
    fidelity: number
    tvd_threshold: number
    fidelity_threshold: number
    tvd_vs_ideal: number
    fidelity_vs_ideal: number
  }
  expected: Distribution
  ideal: Distribution
  measured: Distribution
  deviations: { outcome: string; expected: number; measured: number; delta: number }[]
  reason: string
}

export interface RunResult {
  ok: boolean
  counts: Record<string, number> | null
  duration_s: number
  error_type: string | null
  error_message: string | null
  stderr: string
}

export interface Attempt {
  attempt: number
  code: string
  diff_from_previous: string
  run: RunResult
  verdict: Verdict | null
  diagnosis: { category: string; summary: string; hint: string } | null
  fix_summary: string | null
  repair_call: ModelCall | null
  passed: boolean
}

export interface ImageOut {
  image_b64: string
  mime: string
  caption: string
  call?: ModelCall
}

export interface Explanation {
  text: string
  call: ModelCall
  language?: string
  note?: string
}

export interface CircuitResult {
  status: 'verified' | 'failed'
  verified: boolean
  summary: string
  attempts: Attempt[]
  final_code: string
  counts: Record<string, number> | null
  verdict: Verdict | null
  fault: { name: string; label: string; description: string } | null
  calls: ModelCall[]
  exact_diagram?: ImageOut
  diagram?: ImageOut
  explanation?: Explanation
  insights?: CircuitInsights
}

export interface QaoaSplit {
  teams: number[]
  cut: number
  prob: number
  optimal: boolean
}

export interface QaoaDepth {
  p: number
  gammas: number[]
  betas: number[]
  expected: number
  ratio: number
  p_best: number
  p_best_noisy: number | null
  ratio_noisy: number | null
  top: QaoaSplit[]
  evals: number
  cx: number
  gates: number
  spec: CircuitSpec
}

export interface QaoaLab {
  n: number
  edges: [number, number][]
  max_cut: number
  optimal_count: number
  splits: number
  random_ratio: number
  gammas: number[]
  betas: number[]
  landscape: number[][]
  path: [number, number][]
  depths: QaoaDepth[]
  noise: string
  noise_label: string
  summary: string
}

export interface DiracForm { text: string; latex: string; terms: number; groups: number[][]; product: boolean; expanded: string | null }
export interface RosettaStep { label: string; meaning: string; effect: string; dirac: string }
export interface RosettaLang { id: string; name: string; code: string; checked: boolean; note: string }
export interface RosettaResult {
  source: { kind: string; label: string; exact: boolean; normalized_from: number | null; note: string }
  spec: Spec
  target: DiracForm | null
  state: DiracForm
  preparation: { method: string; fidelity: number; gates: number; two_qubit: number } | null
  steps: RosettaStep[]
  languages: RosettaLang[]
  calls: ModelCall[]
}
export interface RosettaEntry { term: string; plain: string; example: string; dirac: string; entangled: boolean; see: string | null }
export interface NotationRead { kind: string; text: string; notes: string; call: ModelCall }

export interface CopilotTool { name: string; args: Record<string, unknown>; facts: Record<string, unknown>; card: Record<string, unknown> | null; error: string | null; seconds: number }

export interface CopilotReply {
  answer: string
  tools: CopilotTool[]
  trace: { checked: number; traced: number; given: number; untraced: string[] }
  calls: ModelCall[]
  router: 'muse' | 'offline'
}

export interface ChemPoint { r: number; hf: number; exact: number; vqe: number; vqe_err: number; mitigated: number; mitigated_err: number; weight_u: number }

export interface ChemLab {
  r: number
  hamiltonian: { a: number; b: number; c: number }
  hf: number
  exact: number
  vqe: number
  vqe_err: number
  mitigated: number
  mitigated_err: number
  theta: number
  weight_u: number
  correlation: number
  curve: ChemPoint[]
  scan: { theta: number; exact: number; noisy: number; shots: number | null; err: number | null }[]
  atoms: number
  noise: string
  noise_label: string
  shots: number
  spec: CircuitSpec
  summary: string
}

export interface QkdPhoton { bit: number; basis: string; eve: string | null; eve_bit: number | null; bob_basis: string; bob_bit: number; kept: boolean; error: boolean }

export interface QkdLab {
  photons: number
  eve: number
  noise: number
  seed: number
  shown: QkdPhoton[]
  sifted: number
  checked: number
  errors_seen: number
  qber: number
  qber_err: number
  expected_qber: number
  caught: boolean
  key_bits: number
  eve_knows: number
  curve: [number, number][]
  spec: CircuitSpec
  summary: string
}

export interface ArenaComparison {
  truth: Distribution
  guess: Record<string, number>
  guess_sum: number
  tvd: number
  verdict: 'matched' | 'close' | 'wrong'
  impossible: string[]
  missed: string[]
}

export interface ArenaResult { comparison: ArenaComparison; reasoning: string; call: ModelCall }

export interface ArenaRow { id: string; set: 'textbook' | 'new' | 'bigger'; title: string; qubits: number; gates: number; tvd: number | null; verdict: string; impossible: number; missed: number; seconds: number }

export interface ArenaSet { count: number; matched: number; close: number; wrong: number; no_answer: number; mean_tvd: number }

export interface ArenaBenchmark {
  available?: string[]
  model: string
  date: string
  rows: ArenaRow[]
  textbook: ArenaSet
  new: ArenaSet
  bigger: ArenaSet
  verifier: string
}

export interface BugRound {
  id: string
  level: number
  level_label: string
  seed: number
  title: string
  spec: CircuitSpec
  intended: Distribution
  observed: Record<string, number>
  shots: number
  gates: number
}

export interface BugFix { index: number; edit: string }

export interface BugVerdict {
  correct: boolean
  index: number
  planted: number
  label: string
  detail: string
  fixed: CircuitSpec
  machine: { checked: number; seconds: number; fixes: BugFix[]; culprits: number[] }
}

export interface BugGuess {
  index: number
  fix: string
  reason: string
  call: ModelCall
}

export interface Transcript {
  text: string
  duration_ms: number
  call: ModelCall
}

export interface TextDraft {
  kind: 'circuit' | 'network'
  spec: Spec
  valid: boolean
  issues: string[]
  notes: string
  call: ModelCall
}

export interface Amplitude { basis: string; probability: number; phase: number }
export interface StepState {
  step: number
  op_index: number | null
  label: string
  amplitudes: Amplitude[]
  hidden_probability: number
  bloch: [number, number, number][]
  entangled: boolean[]
  entropy?: number[]
  links?: [number, number, number][]  // [a, b, concurrence]
  dirac?: string  // the state in Dirac notation
}
export interface PairEntanglement { a: number; b: number; ideal: number; noisy: number | null }
export interface Entanglement { pairs: PairEntanglement[]; qubit_entropy: number[]; summary: string }
export interface BudgetItem { source: string; label: string; fidelity_loss: number }
export interface ErrorBudget { total_loss: number; items: BudgetItem[]; summary: string }
export interface SweepPoint { scale: number; fidelity: number; success: number | null }
export interface NoiseSweep { baseline: string; points: SweepPoint[]; target: number; scale_for_target: number | null; summary: string }
export interface Mitigation { corrected: Distribution; fidelity_raw: number; fidelity_corrected: number; summary: string }
export interface ZeroNoise {
  scales: number[]
  coefficients: number[]
  fidelity_at: number[]
  mitigated: Distribution
  fidelity_raw: number
  fidelity_readout: number
  fidelity_mitigated: number
  fidelity_shots: number
  fidelity_readout_shots: number
  shots: number
  shot_overhead: number
  outcome: string
  outcome_ideal: number
  outcome_at: number[]
  outcome_zero: number
  summary: string
}
export interface LayoutCost {
  layout: string
  description: string
  depth: number
  two_qubit_gates: number
  swaps_added: number
  estimated_success: number
}
export interface CircuitInsights {
  steps: StepState[]
  entanglement: Entanglement | null
  budget: ErrorBudget | null
  sweep: NoiseSweep | null
  mitigation: Mitigation | null
  zne?: ZeroNoise | null
  bell?: BellTest | null
  tomography?: Tomography | null
  factoring?: ShorLab | null
  layouts: LayoutCost[]
  layout_summary: string
  exports: { qasm2: string; qasm3: string }
  notes: string[]
}

export interface LinkMetrics {
  from: string
  to: string
  medium: string
  length_km: number
  loss_db: number
  transmissivity: number
  success_prob: number
  pair_rate_hz: number
  fidelity: number
}

export interface NetworkMetrics {
  path: string[]
  links: LinkMetrics[]
  end_to_end: {
    pair_rate_hz: number
    fidelity: number
    qber: number
    key_rate_bps: number
    swaps: number
    segments: number
  }
  weakest_link: { from: string; to: string; reason: string } | null
}

export interface FixCandidate {
  kind: string
  description: string
  round: number
  applied: boolean
  pair_rate_hz: number
  fidelity: number
  key_rate_bps: number
  score: number
}

export interface NetworkResult {
  status: string
  summary: string
  path: string[]
  before: NetworkMetrics
  after: NetworkMetrics | null
  fix: FixCandidate | null
  fixes: FixCandidate[]
  candidates: FixCandidate[]
  spec_after: NetworkSpec | null
  checks: { name: string; passed: boolean; detail: string }[]
  diagram?: ImageOut
  explanation?: Explanation
}

export interface JobSummary {
  id: string
  kind: 'circuit' | 'network'
  status: 'queued' | 'running' | 'done' | 'failed'
  error: string | null
  result: CircuitResult | NetworkResult | null
  spec: Spec
}

export interface RecentRun {
  id: string
  title: string
  kind: 'circuit' | 'network'
  started: string
  outcome: string | null
}

export interface Health {
  status: string
  mode: 'meta' | 'mock'
  mode_label: string
  provider: 'meta' | 'mock'
  has_key: boolean
  allow_fallback: boolean
  models: Record<string, string>
}

export interface Examples {
  specs: { id: string; title: string; kind: string; notes: string; valid: boolean; group: string; spec: Spec }[]
  images: { id: string; title: string; kind: string; url: string }[]
  noise_presets: { name: string; label: string }[]
  faults: { name: string; label: string; description: string }[]
  languages: string[]
}

export interface RunOptions {
  noise: string
  shots: number
  demo_mode: boolean
  demo_fault: string
  explain: boolean
  diagram: boolean
  language: string
}

export interface LiveState {
  steps: StepState[]
  ideal: Record<string, number> | null
  noisy: { scale: number; baseline: string; distribution: Record<string, number>; fidelity: number; success: number | null } | null
}

export interface BellResult {
  kind: 'CHSH' | 'Mermin'
  qubits: number[]
  classical_bound: number
  quantum_bound: number
  ideal: number
  noisy: number | null
  shots_value: number | null
  shots_error: number | null
  shots: number
  sigmas: number | null
  settings: number[][][]
  violates: boolean
  verdict: string
}
export interface BellTest { tests: BellResult[]; summary: string }
export interface Tomography {
  n: number
  settings: number
  shots_per_setting: number
  ideal_re: number[][]
  ideal_im: number[][]
  recon_re: number[][]
  recon_im: number[][]
  fidelity_ideal: number
  fidelity_noisy: number
  noisy_fidelity_ideal: number
  purity: number
  summary: string
}
export interface LabCurves { perfect: number[]; realistic: number[]; break_even: number | null }
export interface RepetitionLab {
  scale: number
  p: number[]
  bare: number[]
  bit: LabCurves
  phase: LabCurves
  gate_error_2q: number
  summary: string
}

export interface ShorOutcome {
  bits: string
  y: number
  phase: string
  fraction: string
  cf: number[]
  r: number | null
  ok: boolean
  factors: number[] | null
  steps: string[]
  ideal: number
  noisy: number
  measured: number | null
}
export interface ShorLab {
  N: number
  a: number
  coprime: boolean
  shortcut: number | null
  period: number | null
  outcomes: ShorOutcome[]
  success_ideal: number
  success_noisy: number
  success_measured: number | null
  shots: number | null
  noise: string
  noise_label: string
  spec: CircuitSpec | null
  summary: string
}

export interface OptimizeCost { gates: number; two_qubit: number; depth: number; fidelity: number | null }
export interface OptimizeCandidate {
  source: 'rules' | 'qiskit' | 'combined' | 'muse'
  label: string
  spec: CircuitSpec | null
  cost: OptimizeCost | null
  proof: { level: 'unitary' | 'state' | 'outcomes' | 'none'; process_fidelity: number | null; state_fidelity: number; outcome_tvd: number; detail: string } | null
  accepted: boolean
  better: boolean
  note: string
  rewrites: { rule: string; level: string; text: string }[]
  call: ModelCall | null
  attempts: number
}
export interface OptimizeResult {
  original: OptimizeCost
  candidates: OptimizeCandidate[]
  best: number | null
  summary: string
  ai_note: string
}

export interface ChallengeInfo {
  id: string
  level: number
  level_name: string
  title: string
  goal: string
  kind: 'state' | 'gate'
  num_qubits: number
  par: number
  allowed: Gate[] | null
  hint_count: number
  target_text: string
  target: Amplitude[] | null
  target_bloch: [number, number, number][] | null
  table: { input: string; output: string }[] | null
  starter: CircuitSpec
}

export interface ChallengeCheck {
  solved: boolean
  fidelity: number
  gates: number
  par: number
  stars: number
  message: string
  illegal: string[]
  state: Amplitude[] | null
  bloch: [number, number, number][] | null
  rows_right: number | null
  noisy_fidelity: number | null
  lesson: string | null
}

export interface ObsSeries { id: string; label: string; points: [number, number | null][] }
export interface ObsReference { value: number; label: string; axis: 'x' | 'y' }
export interface ObsChart {
  id: string
  title: string
  finding: string
  x_label: string
  y_label: string
  x_log: boolean
  y_log: boolean
  series: ObsSeries[]
  references: ObsReference[]
  method: string
}
export interface ObsWalkFrames { positions: number[]; steps: number[]; quantum: number[][]; classical: number[][] }
export interface ObsGrover { qubits: number; marked: string; best_k: number; cx_per_query: number; chart: ObsChart }
export interface Observatory {
  satellite: ObsChart
  walk: ObsChart
  walk_frames: ObsWalkFrames
  grover: ObsGrover[]
  entanglement: ObsChart
  wall: ObsChart
}

export interface MissionCheck { name: string; ok: boolean; detail: string; affects: boolean }
export interface MissionNode {
  id: string
  lane: 'perceive' | 'plan' | 'step' | 'report'
  label: string
  tool: string | null
  purpose: string
  after: string[]
  status: 'waiting' | 'running' | 'verifying' | 'done' | 'repaired' | 'flagged' | 'failed' | 'skipped'
  detail: string
  seconds: number
  model: string | null
  args: Record<string, unknown>
  facts: Record<string, unknown>
  card: Record<string, unknown> | null
  checks: MissionCheck[]
}
export interface MissionReport {
  headline: string
  findings: string[]
  next: string
  trace: { checked: number; traced: number; given: number; untraced: string[] }
  router: 'muse' | 'offline'
  calls: ModelCall[]
  seconds: number
  verified: number
  flagged: number
}

export interface MlReport {
  metrics: Record<string, number | string>
  q90: number
  features: string[]
  scatter: [number, number, number][]
  gallery: { circuit: string; scale: number; exact: number; ml: number; half_width: number; baseline: number; depolarizing: number }[]
}

export interface DiscoveryGoal { id: string; title: string; blurb: string; num_qubits: number; chip: boolean }
export interface DiscoveryEntry {
  label: string; source: string; cx: number; one_qubit: number; depth: number; proof: number
  noisy_fidelity: number; outcome_fidelity: number; ml_fidelity: number | null; why: string; spec: Record<string, unknown>
}
export interface DiscoveryResult {
  goal: DiscoveryGoal; target: string; num_qubits: number; complex: boolean; entries: DiscoveryEntry[]; tried: number
  fewest_cnots: number | null; baseline_cnots: number; lower_bound: number; ml_agrees: boolean | null
  ml_rank_correlation: number | null; ml_milliseconds: number; finding: string; calls: ModelCall[]; seconds: number
}

export interface DistLink { label: string; medium: string; distance_km: number; pair_rate_hz: number; fidelity: number; latency_us: number }
export interface DistOption { link: DistLink; fidelity: number | null; fidelity_memory: number | null; seconds_per_run: number | null; note: string }
export interface DistSplit { chip_a: number[]; chip_b: number[]; remote: number; remote_ops: number[] }
export interface DistributedResult {
  title: string; num_qubits: number; capacity: number; compiled_ops: Record<string, unknown>[]; local_cx: number
  best: DistSplit; naive: DistSplit; monolithic_fidelity: number; floor: number; options: DistOption[]
  sweep: [number, number | null, number | null][]; finding: string
}

export interface EstimateQuantum {
  code_distance: number; logical_qubits: number; patches: number; physical_qubits: number; data_qubits: number
  factory_qubits: number; factories: number; t_count: number; runtime_s: number; feasible: boolean; note: string
}
export interface EstimateResult {
  family: string; title: string; hardware: { id: string; label: string; p: number; cycle_s: number }; verdict: string
  headline: string; quantum: EstimateQuantum | null; classical_s: number | null; classical_note: string
  details: Record<string, unknown>; curve: { x: number; quantum_s: number | null; classical_s: number | null; physical_qubits: number | null }[]
  curve_x: string; check: string; assumptions: string[]; sources: string[]; read_by: string; call: ModelCall | null
  mapped: Record<string, unknown>
}

export interface LiveRead {
  analysis: {
    width: number; height: number; kind: string; valid: boolean; issues: string[]; spec: Record<string, unknown>
    overlay: { segment_id: string; concept: string; bbox: [number, number, number, number]; confidence: number; linked_to: string | null; label: string }[]
    calls: ModelCall[]
  }
  result: {
    kind: string; wires: { qubit: number; y: number; x_end: number; x_right: number }[]; error?: string
    ideal?: Record<string, number>; noisy?: Record<string, number> | null
    p1_ideal?: Record<number, number>; p1_noisy?: Record<number, number> | null; gates?: number; qubits?: number
    network?: { pairs_per_second: number; fidelity: number; key_bits_per_second: number }
  }
  read_seconds: number
  total_seconds: number
}

export interface OrbitCity { id: string; name: string; lat: number; lon: number }
export interface OrbitPass {
  start_utc: string; minutes: number; max_el_a: number; max_el_b: number | null; pairs: number | null; key_bits: number; kind: string
  cloud_a: number | null; cloud_b: number | null; expected_key_bits: number | null
}
export interface OrbitSatellite {
  id: string; name: string; norad: number; real: boolean; aperture_mm: number; dual: boolean; status: string; launched: string; note: string
  elements?: { source: string; epoch_utc: string; fetched_utc: string; age_hours: number; line1: string; line2: string }
  height_km?: [number, number]; speed_kms?: number; period_min?: number; inclination_deg?: number
}
export interface OrbitDay {
  from_utc: string; passes_a: number; passes_b: number; key_a: number; key_b: number; trusted: number; expected_trusted: number | null
  cloud_a: number | null; cloud_b: number | null
}
export interface OrbitPlan {
  city_a: OrbitCity; city_b: OrbitCity; distance_km: number; start_utc: string; step_s: number
  track: [number, number][]; sun: [number, number][]; el_a: number[]; el_b: number[]; night_a: boolean[]; night_b: boolean[]
  passes: OrbitPass[]; shared_key_bits_per_day: number; entangled_pairs_per_day: number; trusted_key_bits_per_day: number; finding: string
  satellite: OrbitSatellite; alt_km: number[]; now_index: number | null; expected_trusted_key_bits: number | null; clouds: string | null
  outlook: OrbitDay[]
}
export interface OrbitMeta {
  cities: { id: string; name: string }[]; pairs: { a: string; b: string; label: string; sat: string | null }[]
  satellites: { id: string; name: string; norad: number; real: boolean; status: string }[]
}

export interface ReproClaim { outcome: string; ours: string; claimed: number; ideal: number; noisy: number | null; tolerance: number; verdict: string; ok: boolean }
export interface Reproduction {
  verdict: string; headline: string; read_from: string; bit_order: string; bit_order_inferred: boolean; shots: number
  hardware: string; spec: Record<string, unknown>; ideal: Record<string, number>; noisy: Record<string, number> | null
  claims: ReproClaim[]; tvd_to_ideal: number | null; notes: string; calls: ModelCall[]
}

export interface DecoderPoint { p: number; unprotected: number; mwpm: number; mwpm_ci: number; neural: number; neural_ci: number; shots: number }
export interface DecoderD5Point {
  p: number; shots: number; d3: number; d3_ci: number; d5: number; d5_ci: number; neural: number; neural_ci: number
  per_round_d3: number; per_round_d5: number; per_round_neural: number; lam: number | null
  fixes: number; breaks: number; paired_z: number
}
export interface DecoderReport {
  curve: DecoderPoint[]; train_shots: number; train_p: number[]; rounds: number
  d5: { curve: DecoderD5Point[]; train_shots: number; train_p: number[] } | null
  example: {
    p: number; d: number; x_checks: number[][]; z_checks: number[][]; errors: number[][]; final_flips: number[]
    dz: number[][]; dx: number[][]; flip: number; mwpm: number; neural: number
  }
}
export interface PulseReport {
  run: { duration_ns: number; drag: boolean; beta: number; times: number[]; omega_x_mhz: number[]; omega_y_mhz: number[]
    populations: [number, number, number][]; fidelity: number; leakage: number; fidelity_no_decoherence: number }
  sweep: { durations: number[]; gaussian_error: number[]; drag_error: number[]; gaussian_leak: number[]; drag_leak: number[]
    decoherence_only: number[]; best_gaussian: [number, number]; best_drag: [number, number] }
}

export interface HardwareRun { circuit: string; id: string; two_qubit_gates: number; depth: number; tvd_ideal: number; tvd_generic: number; tvd_twin: number
  tvd_calibrated?: number; shot_noise_tvd?: number }
export interface HardwareRuns { device: string; rehearsal: boolean; job_id: string; shots: number; date_utc: string; runs: HardwareRun[]
  calibration?: { device: string; taken_utc: string; calibrated_utc: string | null; two_qubit_error: number; readout_p01: number; readout_p10: number } }
export interface GhzEstimate { populations: number; coherence: number; fidelity: number; se?: number }
export interface DiscoveryHardwareVariant { label: string; source: string; cx_logical: number; two_qubit_gates: number; depth: number
  predicted_state_fidelity: number; predicted_outcome_fidelity: number; outcome_fidelity: number; outcome_se?: number; twin_outcome_fidelity: number; tvd: number
  ghz?: GhzEstimate; twin_ghz?: GhzEstimate }
export interface DiscoveryHardwareGoal { id: string; title: string; target: string; finding: string; num_qubits: number; patch?: number[]; variants: DiscoveryHardwareVariant[]
  comparison?: { metric: string; discovered: number; baseline: number; baseline_label: string; margin: number; z: number } }
export interface DiscoveryHardware { device: string; rehearsal: boolean; job_id: string; shots: number; date_utc: string; circuits: number; goals: DiscoveryHardwareGoal[] }

export interface ProofCheck { id: string; category: string; title: string; guards: string; status: 'pass' | 'fail' | 'skipped' | 'note'; detail: string; ms: number }
export interface ProofSheet { title: string; num_qubits: number; gates: number; noise: string; checks: ProofCheck[]
  passed: number; failed: number; skipped: number; notes: number; seconds: number; summary: string }
export interface ProofBench { date_utc: string; circuits: number; categories: number; checks_per_circuit: number; kinds: number
  totals: { passed?: number; failed?: number; skipped?: number; notes?: number }
  rows: { id: string; title: string; category: string; qubits: number; gates: number; passed: number; failed: number; skipped: number; notes: number; seconds: number }[]
  per_check: Record<string, { category: string; title: string; guards: string; pass?: number; fail?: number; skipped?: number; note?: number }> }

export interface IbmDevice { device: string; processor: { family?: string; revision?: string }; num_qubits: number; couplers: number
  taken_utc: string; calibrated_utc: string | null; pending_jobs: number; dynamic_circuits: boolean
  two_qubit_error: number | null; sx_error: number | null; readout_error: number | null; t1_us: number; t2_us: number; unusable_couplers: number }
export interface IbmStatus { can_run: boolean; reason: string; runs_today: number; devices: IbmDevice[]
  live: null | { error?: string; devices?: { device: string; operational: boolean; pending_jobs: number }[]; usage?: { used_s: number; limit_s: number; left_s: number } | null; checked_utc?: string } }
export interface IbmQubit { t1_us: number | null; t2_us: number | null; p01: number | null; p10: number | null; sx_error: number | null }
export interface IbmSnapshot { device: string; num_qubits: number; two_qubit_gate: string; taken_utc: string; calibrated_utc: string | null
  qubits: IbmQubit[]; edges: Record<string, number>; coords: [number, number][]; summary: IbmDevice }
export interface IbmPatch { qubits: number[]; success: number }
export interface IbmAdvice { device: string; ok: boolean; note: string; candidates: number; best: IbmPatch | null; median: IbmPatch | null; worst: IbmPatch | null; seconds: number }
export interface IbmRun { job_id: string; device: string; shots: number; placement: number[] | null; how: string; two_qubit_gates: number; title: string
  submitted_utc: string; status: string
  result: null | { error?: string; measured?: Record<string, number>; ideal?: Record<string, number>; tvd_ideal?: number; tvd_calibrated?: number | null; shot_noise?: number; finished_utc?: string } }
export interface IbmExperiments { device: string; job_id: string; date_utc: string; snapshot_utc: string; circuits: number
  ghz: { n: number; shots: number; candidates: number; rows: { placement: string; qubits: number[]; advisor_score: number; fidelity: number; se: number; populations: number; coherence: number; twin_fidelity: number }[] }
  teleport: { qubits: number[]; shots: number; classical_limit: number
    feed_forward: { average: number; se: number; twin_average: number; rows: { state: string; fidelity: number; se: number; twin_fidelity: number }[] }
    no_corrections: { average: number; se: number; twin_average: number; rows: { state: string; fidelity: number; se: number; twin_fidelity: number }[] } } }

export interface HeadlineStat { value: string; label: string; note: string; source: string }
export interface HeadlineScene {
  image: string
  width: number
  height: number
  segments: { concept: string; bbox: [number, number, number, number]; confidence: number }[]
  operations: { gate: string; targets: number[]; controls?: number[] }[]
  num_qubits: number
  outcomes: { key: string; measured: number; predicted: number }[]
  shots: number
  preset: string
  verified: boolean
  fidelity: number
  tvd: number
}
export interface Headline { stats: HeadlineStat[]; scene: HeadlineScene }
