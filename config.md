# Leech Doctor — Settings

Edit via **Tools → Leech Doctor: Preferences…**, or directly in the add-on's `config.json`.

## `providers.catalog`
One entry per provider. Supported `kind`s: `openai_compat` (OpenAI, Ollama, vLLM, OpenCode, LM Studio…)
and `anthropic` (Claude native Messages API). Each entry has `label`, `base_url`, `model`, `api_key`.

Optional per-provider keys:
- `headers` — a dict of extra request headers (editable in Preferences → Providers). Useful for
  gateways that need a routing/session header.
- `user_agent` — override the default self-identifying User-Agent.
- `chat_path` / `models_path` — override the endpoint paths (default `/chat/completions`, `/models`).

For any `opencode.ai` endpoint, an `x-opencode-session` header is added automatically on inference
requests (OpenCode Go requires it); a value you set in `headers` takes precedence.

## `providers.slots`
Two slots a card is sent through: `local` and `cloud`. Point each at a catalog key.
Default: `local → ollama`, `cloud → claude`.

## `routing`
- `mode`: `auto` | `local` | `cloud` (manual override wins).
- `on_ac` / `on_battery` / `on_desktop` / `offline`: which slot to use in each situation.
  Default: AC→local, battery→cloud, desktop→local, offline→local.
- `fallback`: slot to use when the chosen one is unreachable.
- `probe_timeout_s`: how long to wait when checking a provider is up.

## `generation`
`temperature`, `max_tokens`, `timeout_s`, `max_cards_per_batch` (cap on a batch), `concurrency`.

## `filters`
`min_lapses`, `include_suspended`, `include_leeches`, `ease_ceiling` (null = off).

## `diagnosis`
Heuristic thresholds that seed the LLM (`wordy_front_threshold`, `wall_of_text_threshold`) and the
`support_fields` list used to spot an empty field that could carry a discriminating cue.

## `ui`
`field_max_height` — how tall a field box may grow (px) before it starts scrolling internally.
Boxes auto-size to their content, so short/empty fields take a single line (default 260).
Also adjustable live from the **field height** spinner in the toolbar; set it high (e.g. 2000) to
always fit the whole text.

`preview_max_height` — max height (px) of the inline image preview shown under a field that
contains an `<img>` tag (default 220). Previews resolve filenames against Anki's media folder.

`rich_edit` — start with the rich-text editor enabled (default false). In rich mode fields render
as formatted text; only fields you actually modify are written back, and Qt's markup is normalised
to Anki-style HTML. Prefer raw mode for cloze/image-heavy fields.

## `ui.theme`

Controls how Leech Doctor colours itself.

- `mode` — `auto` (default) | `onigiri` | `anki` | `custom`.
  - `auto` / `onigiri` read **Onigiri's live palette** from its config on disk, honouring Onigiri's
    own light/dark choice (falling back to Anki's). This makes the window match the rest of your theme.
  - `anki` uses Anki's Qt palette (tracks light/dark).
  - `custom` uses the explicit colours below.
- `dark` — `null` (auto) | `true` | `false`. Only used by `custom`.
- `accent`, `bg`, `panel`, `fg`, `fg_dim`, `border` — `#rrggbb` overrides, used by `custom`.

Use **Preferences → Theme → Show resolved theme** to see exactly which palette was picked and from where.

## `apply`
`confirm_apply_over` (ask before batch-applying more than this), `keep_revert_log`.
