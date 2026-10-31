"""Ofrenda: keeps a family story. Record someone telling it (or add a voice memo).
Everything runs on this laptop: Whisper writes down what was said, and an open-weight
model (through Ollama) turns it into a short remembrance card using ONLY the words in
the story. Saved stories are plain files in the memories/ folder, so they never depend
on a service that might disappear."""
import glob
import io
import json
import os
import re
import shutil
import threading
import time
import uuid
import webbrowser

import requests
from flask import Flask, jsonify, request, send_from_directory

BASE = os.path.dirname(os.path.abspath(__file__))
MEMORIES = os.path.join(BASE, "memories")   # saved stories live here (never uploaded to GitHub)
PENDING = os.path.join(MEMORIES, "_pending")  # recordings waiting to be saved
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 300 * 1024 * 1024  # allow long recordings

MODEL = "gemma3:4b"                # change to any model you have pulled with Ollama
OLLAMA = "http://localhost:11434"  # where Ollama listens on this laptop
WHISPER_MODEL = "small"            # "base" is faster, "small" understands more languages better
MAX_CHARS = 7000                   # how much of a long story the model reads

# The exact shape we force the model to answer in
CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "remembrance": {"type": "string"},
        "loved": {"type": "array", "items": {"type": "string"}},
        "quote": {"type": "string"},
    },
    "required": ["title", "remembrance", "loved", "quote"],
}

# ---- Whisper (speech to text), loaded once ----
WHISPER, LOCK = None, threading.Lock()


def get_whisper():
    """Loads Whisper once. The very first time, it downloads the model (needs internet once)."""
    global WHISPER
    with LOCK:
        if WHISPER is None:
            from faster_whisper import WhisperModel
            WHISPER = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    return WHISPER


def norm(s):
    """Lowercase text with punctuation and extra spaces removed, so quotes can be compared."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", s.lower())).strip()


@app.get("/")
def home():
    return send_from_directory(os.path.join(BASE, "static"), "index.html")


@app.get("/api/status")
def status():
    """Tells the page if Ollama is running and the model is downloaded."""
    try:
        tags = requests.get(f"{OLLAMA}/api/tags", timeout=3).json()
    except requests.exceptions.RequestException:
        return jsonify(model=MODEL, state="offline", message="Ollama isn't running. Open the Ollama app from the Start menu, then reload this page.")
    names = [m["name"] for m in tags.get("models", [])]
    if (MODEL if ":" in MODEL else MODEL + ":latest") not in names:
        return jsonify(model=MODEL, state="missing", message=f"Model not downloaded yet. In PowerShell run: ollama pull {MODEL}")
    return jsonify(model=MODEL, state="ready")


@app.post("/api/transcribe")
def transcribe():
    """Writes down what was said in a recording. The audio is kept aside until you save."""
    ext = re.sub(r"[^a-z0-9]", "", request.args.get("ext", "webm").lower())[:5] or "webm"
    data, audio_id = request.get_data(), uuid.uuid4().hex
    os.makedirs(PENDING, exist_ok=True)
    with open(os.path.join(PENDING, f"{audio_id}.{ext}"), "wb") as f:
        f.write(data)
    try:
        segments, info = get_whisper().transcribe(io.BytesIO(data), language=request.args.get("lang") or None, beam_size=1)
        text = " ".join(s.text.strip() for s in segments).strip()
    except Exception as e:
        return jsonify(error=f"Couldn't read the recording ({e}). On the first run, wait for the voice model to finish downloading."), 500
    return jsonify(text=text, audio_id=audio_id)


@app.post("/api/card")
def card():
    """Turns the story into a remembrance card, using only what was said."""
    d = request.get_json()
    name = (d.get("name") or "this person").strip()
    transcript = (d.get("transcript") or "").strip()
    if not transcript:
        return jsonify(error="There's no story to work from yet."), 400
    used = transcript[:MAX_CHARS]
    prompt = f"""Someone is keeping a family story about {name}. Below is a transcript of the story being told. It may contain speech-recognition mistakes.

Transcript:
{used}

Write a remembrance card using ONLY what is in the transcript. Never invent names, dates, places, relatives or feelings that are not there. If the transcript doesn't say it, leave it out.
- title: 3 to 7 plain, warm words.
- remembrance: 3 to 5 sentences in English, about {name}, in the third person.
- loved: up to 6 short items (foods, songs, places, objects, habits) clearly mentioned in the transcript. An empty list if none.
- quote: one short phrase (under 25 words) copied EXACTLY from the transcript, in its original language. An empty string if nothing fits."""
    try:
        r = requests.post(
            f"{OLLAMA}/api/chat",
            json={"model": MODEL, "messages": [{"role": "user", "content": prompt}], "stream": False,
                  "format": CARD_SCHEMA, "options": {"temperature": 0.3, "num_ctx": 8192}},
            timeout=300,
        )
        r.raise_for_status()
        result = json.loads(r.json()["message"]["content"])
        result["loved"] = [str(x) for x in result["loved"]][:6]
        if norm(result["quote"]) not in norm(used):  # a quote must be real words from the story
            result["quote"] = ""
    except requests.exceptions.RequestException:
        return jsonify(error="Can't reach the model. Check that Ollama is running and the model is downloaded."), 502
    except (ValueError, KeyError):
        return jsonify(error="The model gave a muddled answer. Press the button to try again."), 502
    result["truncated"] = len(transcript) > MAX_CHARS
    return jsonify(result)


@app.post("/api/save")
def save():
    """Saves the story, the card and the recording as plain files in memories/."""
    d = request.get_json()
    slug = re.sub(r"[^a-z0-9]+", "-", (d.get("name") or "").lower()).strip("-")[:30] or "story"
    folder = f"{time.strftime('%Y%m%d-%H%M%S')}-{slug}"
    path = os.path.join(MEMORIES, folder)
    os.makedirs(path)
    audio_id = d.get("audio_id", "")
    if re.fullmatch(r"[0-9a-f]{32}", audio_id):  # only our own generated ids
        for f in glob.glob(os.path.join(PENDING, audio_id + ".*")):
            shutil.move(f, os.path.join(path, "audio" + os.path.splitext(f)[1]))
    story = {"name": d.get("name", ""), "saved": time.strftime("%d %B %Y"), "transcript": d.get("transcript", ""), "card": d.get("card", {})}
    with open(os.path.join(path, "story.json"), "w", encoding="utf-8") as f:
        json.dump(story, f, ensure_ascii=False, indent=2)
    return jsonify(folder=folder)


@app.get("/api/memories")
def memories():
    """Lists every saved story, newest first."""
    items = []
    for folder in sorted(os.listdir(MEMORIES), reverse=True) if os.path.isdir(MEMORIES) else []:
        p = os.path.join(MEMORIES, folder, "story.json")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                s = json.load(f)
            has_audio = bool(glob.glob(os.path.join(MEMORIES, folder, "audio.*")))
            items.append({"folder": folder, "name": s.get("name"), "saved": s.get("saved"), "card": s.get("card"), "has_audio": has_audio})
    return jsonify(items)


@app.get("/api/audio/<folder>")
def audio(folder):
    """Plays a saved recording."""
    files = glob.glob(os.path.join(MEMORIES, folder, "audio.*")) if re.fullmatch(r"\d{8}-\d{6}-[a-z0-9-]+", folder) else []
    if not files:
        return "", 404
    return send_from_directory(os.path.join(MEMORIES, folder), os.path.basename(files[0]))


def preload_whisper():
    """Runs in the background at startup so the voice model is ready when you need it."""
    print("Loading the voice model (the first time it downloads a few hundred MB)...")
    try:
        get_whisper()
        print("Voice model ready.")
    except Exception as e:
        print("Voice model not ready:", e)


if __name__ == "__main__":
    os.makedirs(MEMORIES, exist_ok=True)
    threading.Thread(target=preload_whisper, daemon=True).start()
    threading.Timer(1.2, lambda: webbrowser.open("http://localhost:5003")).start()
    app.run(port=5003)
