# Ofrenda

Keep a family story before it fades. Record someone telling it (or add a voice memo), and
Ofrenda writes it down, then turns it into a short remembrance card using only what was said.
Everything runs on your laptop: Whisper (speech to text) and an open-weight model through
Ollama. No account, no API key, no cloud. Stories are saved as plain files (text, JSON and the
original audio) in a `memories/` folder, so they never depend on a service that might disappear.

## Run (Windows)
1. Install [Python 3.11+](https://python.org) (tick **Add python.exe to PATH**).
2. Install [Ollama](https://ollama.com/download), then in PowerShell: `ollama pull gemma3:4b`
3. Double-click `run.bat`. Your browser opens at http://localhost:5003.
   The first start downloads the voice model (a few hundred MB, needs internet once).

## Good to know
- Ask permission before recording someone.
- The card may only use words from the story. A quoted line is checked against the transcript,
  and you can edit everything before saving.
- Saved stories are in `memories/`, which is excluded from git. Delete a folder there to remove a story.
- Change `MODEL` and `WHISPER_MODEL` at the top of `app.py`. The model's instructions are in `card()`.
