# Decisions

Each entry: what was decided, and why. Newest last.

## D1. Project location and identity (2026-10-28)
No `q-canvas` folder, `.env` or `docs/meta-api/` existed. Created the project at
`C:\Users\DHRUV\Projects\q-canvas` with its own git repo (branch `main`). Commits
use repo-local identity `DHRUV <alwaysworking.7077@gmail.com>`; change with
`git config user.email` if you prefer another address. No AI attribution lines.

## D2. Meta API docs were fetched, not invented
`docs/meta-api/` was empty, so the official Markdown docs were downloaded from
`https://dev.meta.ai/docs/*.md` (see `docs/meta-api/SOURCES.md`). All adapter code
cites those files. The docs call the key `MODEL_API_KEY`; we read `META_API_KEY`
first (the mission's name, also what Muse Code reads) and fall back to
`MODEL_API_KEY`.

## D3. Which Meta model does which job
| Job | Model ID | Endpoint |
| --- | --- | --- |
| Find drawn parts (boxes, circles, dots, dishes) | `sam-3.1` | `POST /v1/responses` |
| Read the sketch into a spec; explain results | `muse-spark-1.3` | `POST /v1/chat/completions` with `response_format` json_schema |
| Write and repair Qiskit code | `muse-spark-1.3` by default (`QCANVAS_CODE_MODEL`, e.g. `muse-wonder-1.0`) | `POST /v1/chat/completions` |
| Optional: repair through the Muse Code agent itself | `muse exec` headless CLI | local binary, opt in with `QCANVAS_CODE_BACKEND=muse-cli` |
| Clean annotated diagram | `muse-image-1.0` | `POST /v1/images/generations` |

"Muse Code" in the mission is Meta's coding agent product, which is built on
Muse Spark. Inside our app the repair agent is our own loop calling Muse Spark,
which the docs describe as the model "for agentic and coding work". Standard
mode IDs are used (not `-contributor`) so judges' and users' content is not used
for training.

## D4. Spec design
- Discriminated by `kind` (`circuit` | `network`), version `1.0`, pydantic v2,
  `extra="forbid"` so typos are reported, not silently ignored.
- Single-qubit gates may list several targets (broadcast, e.g. H on 0 and 1).
- Terminal measurements only (no gate after a qubit is measured). This keeps the
  independent expected distribution exact (statevector / density matrix).
- A circuit with no measurement is invalid: nothing to verify.
- Common aliases (`CNOT`, lower case) are normalised, because hand labels and
  model output use them.
- Validation collects every issue with a path like `operations[2] (RX)`.
- Network links use `from`/`to` in JSON (`from_node`/`to_node` in Python).
- `kind_schema()` inlines `$ref`s so structured output gets a plain-object root.

## D5. Python 3.13 venv
System Python is 3.10 (too old for the mission's 3.11+). The `py` launcher has
3.13, which Qiskit 2.6.1 and qiskit-aer 0.18.2 ship wheels for.
