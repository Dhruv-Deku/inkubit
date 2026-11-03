# Meta Model API docs used by Inkubit

No human-provided docs were present when work started, so these pages were
downloaded on 2026-10-28 from Meta's official Markdown docs
(`https://dev.meta.ai/docs/<page>.md`; index in `_index_llms.txt`). File names
map `/` to `_`, for example `sam_reading-segmentation.md` is
`https://dev.meta.ai/docs/sam/reading-segmentation.md`.

Every endpoint, model ID and request field in `backend/inkubit/adapters/meta*.py`
comes from these files:

| What we use | Where it is documented |
| --- | --- |
| Base URL `https://api.meta.ai/v1`, `Authorization: Bearer <key>` | `api-reference.md`, `authentication.md` |
| `POST /v1/chat/completions`, model `muse-spark-1.3` | `protocols_chat-completions.md`, `models.md` |
| Image input as `{"type":"image_url","image_url":{"url":"data:image/png;base64,..."}}` | `image-understanding.md` |
| `response_format: {"type":"json_schema","json_schema":{"name","schema"}}` | `structured-output.md` |
| `reasoning_effort` (top level on Chat Completions) | `reasoning.md` |
| `POST /v1/responses`, model `sam-3.1`, `input_text` + `input_image`, `metadata.include_confidence: "true"` | `media-segmentation.md`, `sam_segmenting.md` |
| SAM output grammar `<0f>id<|box;x1=..;...;c=..|><|mask;...|>` | `sam_reading-segmentation.md` |
| `POST /v1/images/generations`, model `muse-image-1.0`, `response_format: "b64_json"`, `output_format: "png"` | `image-generation.md`, `api-reference_images_schemas.md` |
| `POST /v1/asr/transcribe`, model `muse-voice-transcribe-1.0`, multipart `request` (`audioEncoding: "WAV"`, `mode: "PUSH_TO_TALK"`, `keywords`) + `audio` (mono 16-bit PCM WAV, 16 or 24 kHz); response `transcript`, `audioDurationMs` | `speech-to-text.md`, `api-reference_voice_transcribe.md`, `api-reference_voice_schemas.md` (downloaded 2026-10-30) |
| Muse Wonder (`muse-wonder-1.0`) on Chat Completions with tools and `reasoning_effort`; Standard mode only, $4 / $20 per 1M input / output tokens | `models.md`, `reasoning.md`, `pricing-rate-limits.md`, `tool-calling.md` |
| Error envelope and retry guidance | `error-handling.md` |

The docs name the env var `MODEL_API_KEY`; Inkubit reads `META_API_KEY` first
and falls back to `MODEL_API_KEY`.
