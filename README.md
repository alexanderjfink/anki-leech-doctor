# Leech Doctor

> Diagnose and repair the Anki cards you keep forgetting — with an LLM.

**AnkiWeb install code: [`2142317474`](https://ankiweb.net/shared/info/2142317474)**

**Leech Doctor** finds the cards you fail most often, explains *why* they keep failing, asks a language model for a concrete rewrite, and lets you edit and apply those changes safely — per card, per deck, or across your whole collection.

---

## Why

Spaced repetition works — until a card is badly written. A card you've forgotten 30 times is usually not a memory problem; it's a **card** problem: it lacks a discriminating cue, buries the answer in a wall of text, tests an arbitrary label, or asks several things at once.

Anki already tracks the evidence: **lapses** (how many times you answered *Again* after learning), **ease** (how aggressively Anki has shortened the interval), and **fail rate**. Leech Doctor turns that evidence into a ranked worklist, and an LLM into a repair tool.

---

## Features

- **Struggle ranking** — sorts cards by lapses (times forgotten after learning), tie-broken by fail rate and ease.
- **Deck grouping & filters** — browse grouped by deck or flat, filtered by minimum lapses, leeches only, and an optional ease ceiling.
- **Clear stat chips** — big, legible **lapses / reps / fail % / ease / interval**, each with a tooltip explaining it.
- **Heuristic diagnosis** — flags *wordy front*, *wall of text on the answer side*, *image prompt with no anchor*, *empty support field*, and *possible multi-response* cards.
- **LLM repair proposals** — sends the note, its fields, which fields render on the question, and the card's performance to your chosen model, and receives **strict JSON**: a failure mode, a one-line rationale, and concrete field edits.
- **Edit every field** — raw HTML or rich text; **B / I / U** buttons and **⌘B / ⌘I / ⌘U**; a **cloze** button (**⌘⇧C**) on cloze notes; and **inline image previews** that resolve Anki media (`<img src="...">`).
- **Safe apply** — per card, per deck, or all; a confirmation threshold for large batches; and a persistent **revert log** with *Revert last* / *Revert all*.
- **Provider router** — OpenAI, Anthropic Claude, Ollama, vLLM, OpenCode, or any OpenAI-compatible endpoint, with automatic **local vs. cloud** selection based on power source.

---

## How it works

1. **Pick a scope** — all decks, or one deck. Leech Doctor ranks your most-struggled notes.
2. **Select a note** — you get its metrics, a heuristic diagnosis, and every field, editable.
3. **Generate a proposal** — the model proposes edits, which you can freely change (or write your own).
4. **Apply** — only the fields you actually changed are written back, and only field *text* is touched.

---

## Safety model

Leech Doctor is deliberately conservative with a collection you care about:

- **Field text only.** It never changes a note's type/model, and never touches `interval`, `ease`, `due` or `queue`. **Scheduling is always preserved.**
- **Only edited fields are written.** In rich mode each editor tracks whether you modified it; untouched fields stay byte-for-byte identical.
- **Revert log.** Every applied change is recorded (note id, field, old value, new value, timestamp) in `revert_log.json`, and can be undone with *Revert last* / *Revert all*.
- **Confirmation for batches.** Applying to more than a configurable number of notes asks first.

---

## Privacy

Card text is sent **only** to the LLM provider you configure — nothing else leaves your machine. API keys are stored locally in Anki's add-on config and are **never** committed to this repository (`meta.json` and `revert_log.json` are git-ignored). To keep everything offline, point the *local* slot at Ollama or vLLM and use **Local** mode.

---

## Requirements

- **Anki 2.1.50+** (Qt6). Developed and tested on **Anki 26.9**.
- **No third-party Python packages** — standard library only.
- For **local** models: [Ollama](https://ollama.com) (`http://localhost:11434/v1`) or [vLLM](https://docs.vllm.ai) (`http://localhost:8000/v1`).
- For **cloud**: an API key for OpenAI / Anthropic / OpenCode, or any OpenAI-compatible gateway.

---

## Install

### From AnkiWeb — install code `2142317474`

1. In Anki: **Tools → Add-ons → Get Add-ons…**
2. Enter **`2142317474`** and click **OK**.
3. Restart Anki.

Add-on page: <https://ankiweb.net/shared/info/2142317474>

### From a `.ankiaddon` file

1. Download `leech_doctor-<version>.ankiaddon` from **Releases** (or build it: `python3 build.py`).
2. In Anki: **Tools → Add-ons → Install from file…** and choose the file.
3. Restart Anki.

### Manual (from source)

Copy this folder into your Anki `addons21` directory:

| OS | Path |
|----|------|
| macOS | `~/Library/Application Support/Anki2/addons21/leech_doctor` |
| Windows | `%APPDATA%\Anki2\addons21\leech_doctor` |
| Linux | `~/.local/share/Anki2/addons21/leech_doctor` |

Then restart Anki.

> The add-on is published on AnkiWeb with install code **`2142317474`**. See [Publishing](#publishing-to-ankiweb) for how updates are released.

---

## Configuration

Open **Tools → Leech Doctor: Preferences…**

### Providers

Each provider has a **base URL**, **model**, and **API key**. Enter the URL and key, then click **Load models** to populate the dropdown — or type a model name if the endpoint can't list them.

| Provider | Kind | Default endpoint |
|----------|------|------------------|
| Ollama | OpenAI-compatible | `http://localhost:11434/v1` |
| vLLM | OpenAI-compatible | `http://localhost:8000/v1` |
| OpenCode | OpenAI-compatible | *configure your gateway* |
| OpenAI | OpenAI-compatible | `https://api.openai.com/v1` |
| Claude | Anthropic native | `https://api.anthropic.com` |

Requests use `{base_url}/chat/completions` and `{base_url}/models` (Anthropic uses `/v1/messages` and `/v1/models`). A full endpoint pasted into the base URL is accepted and normalised.

### Routing

Two **slots** — **local** and **cloud** — each pointing at a provider. In **Auto** mode the slot is chosen by situation:

| Situation | Default slot |
|-----------|--------------|
| On AC power | local |
| On battery | cloud |
| Desktop (no battery) | local |
| Offline | local |
| Chosen provider unreachable | fallback slot |

Local inference is power-hungry, so Auto offloads to the cloud on battery and uses local when plugged in. A **manual Auto / Local / Cloud** toggle sits in the editor toolbar, and the live choice is always shown in the status line. An unconfigured provider is never selected silently.

---

## Usage

### The Leech Doctor window

- **Left:** your struggled notes — grouped by deck, or flat when a single deck is selected.
- **Toolbar:** deck, sort, minimum lapses, leeches-only, previews, rich edit, field height, provider, rebuild.
- **Right:** stat chips, a highlighted diagnosis banner, and **every field** with formatting controls.
- **Bottom:** *Generate proposal*, *Generate for deck*, *Reload fields*, *Apply card*, *Apply deck*, *Apply all*, *Revert last*, *Revert all*.

### Editing fields

- **Raw mode** (default) — you edit the field's HTML directly, with B/I/U wrapping the selection in `<b>`/`<i>`/`<u>`.
- **Rich mode** (`rich edit`) — WYSIWYG editing; only fields you modify are written back, and Qt's markup is normalised to Anki-style HTML.
- **Previews** — any field containing HTML is rendered below the editor, with `<img>` resolved against Anki's media folder.
- **Field height** — drag the toolbar spinner to fit more or less text; set it high to always fit everything.

### Keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| ⌘B / Ctrl+B | Bold |
| ⌘I / Ctrl+I | Italic |
| ⌘U / Ctrl+U | Underline |
| ⌘⇧C / Ctrl+Shift+C | Cloze deletion (cloze notes only) |

Shortcuts are scoped to the focused field.

---

## Troubleshooting

- **`HTTP 403 … error code 1010`** — your gateway sits behind Cloudflare, which blocks known-bot user agents. Leech Doctor sends a self-identifying `User-Agent` that passes it; if a provider still blocks you, set a browser-style `user_agent` for that provider in the config.
- **`HTTP 400 … MissingSessionID` / `x-opencode-session`** — OpenCode Go requires a stable session id on **inference** requests. Leech Doctor sends one automatically for any `opencode.ai` endpoint (their `GET /models` deliberately omits it, which is why *Load models* works without it). If you override that provider's `headers`, don't drop it — or set your own `x-opencode-session` value.
- **`The 'cloud' slot points to '…', which is not ready`** — the slot references a provider with no base URL (or, for Anthropic, no API key). Fix it in **Preferences → Routing**.
- **Settings don't seem to apply** — Anki stores live add-on config in `meta.json`, not `config.json`. Always change settings through **Preferences**.
- **Boxes too tall or too short** — adjust **field height** in the toolbar.

---

## Development

- Pure logic lives in `engine/` and is unit-testable without Anki: card ranking (`query.py`), failure-mode diagnosis (`diagnose.py`), safe apply + revert (`apply.py`), and field-text helpers (`text.py`).
- Provider clients live in `providers/` (two shapes cover every target: OpenAI-compatible and Anthropic native).
- Build a package:

  ```bash
  python3 build.py        # → leech_doctor-<version>.ankiaddon
  ```

### Publishing to AnkiWeb

1. Build the package (this excludes `__pycache__`, which AnkiWeb rejects).
2. Go to **https://ankiweb.net/shared/addons** and use the **Upload** button.
3. AnkiWeb assigns the add-on a **numeric ID** — that number is the install code.
4. Optionally add `"ankiweb_id": "<number>"` to `manifest.json`.

---

## Theming

Leech Doctor follows the app's colours instead of hard-coding its own.

- **With Onigiri installed**, it reads Onigiri's **live palette** (its `colors.light` / `colors.dark` tokens) and adopts the same background, surface, text, and **accent** colours — including Onigiri's own light/dark choice. Catppuccin, Dracula, Rosé Pine, Nord, Solarized and custom Onigiri themes all work, because the palette is read from Onigiri rather than reimplemented.
- **Otherwise** it uses Anki's Qt palette, so it tracks Anki's light/dark mode.
- **Or** set explicit colours under **Preferences → Theme → custom**.

The whole window palette is applied through Qt's palette (not a stylesheet), so buttons, trees, text fields and scrollbars inherit it and nothing fights Anki's or Onigiri's own styling. Accent-derived tints are used for the diagnosis banner, the lapses chip, and LLM-proposal labels.

**Preferences → Theme → Show resolved theme** reports exactly which source was used and the resolved colours.

## Roadmap

- Rendered card preview (question/answer with the note's CSS)
- CSV / Markdown export of proposals
- Dry-run mode (write a plan without applying)

---

## License

Licensed under the **Peer Production License** — a *copyfarleft* license created by John Magyar and Dmytri Kleiner, derived from Creative Commons BY-NC-SA 3.0. See [LICENSE](LICENSE) for the full text.

In short: you may use, share and adapt this work freely for **non-commercial** purposes, provided you **attribute** it and **share alike**. Commercial use is permitted **only** by worker-owned businesses or worker-owned collectives that distribute all financial gain among their worker-owners. Commercial use by privately owned, profit-seeking businesses is **not** permitted.

> The Peer Production License is not currently registered with SPDX.
