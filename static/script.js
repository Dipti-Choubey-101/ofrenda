// Ofrenda front-end: record or add a story, write it down, make the card, save it.
const $ = (id) => document.getElementById(id);
const post = (url, body) => fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
let clip = null, ext = "webm", audioId = null, recorder = null;

// Small helper: make an element with a class and text (textContent keeps it safe).
function h(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text) e.textContent = text;
  return e;
}
const say = (t) => ($("msg").textContent = t);

// Asks the server if Ollama is running and the model is downloaded.
async function checkStatus() {
  const s = await (await fetch("/api/status")).json();
  $("model").textContent = s.model;
  $("dot").className = "dot " + (s.state === "ready" ? "ready" : "bad");
  $("notice").style.display = s.message ? "block" : "none";
  $("notice").textContent = s.message || "";
}

// Remembers the recording (or voice memo) so it can be played back and written down.
function setClip(blob, extension) {
  clip = blob;
  ext = extension.toLowerCase();
  $("player").src = URL.createObjectURL(blob);
  $("player").hidden = false;
  $("write").disabled = false;
  say("Play it back if you like, then press Write it down.");
}

$("file").onchange = (e) => { const f = e.target.files[0]; if (f) setClip(f, f.name.split(".").pop()); };

$("rec").onclick = async () => {
  if (recorder) { recorder.stop(); return; }          // second click = stop
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    $("notice").style.display = "block";
    $("notice").textContent = "The microphone is blocked. Click the lock icon next to the address bar and allow it.";
    return;
  }
  const chunks = [], started = Date.now();
  recorder = new MediaRecorder(stream);
  recorder.ondataavailable = (e) => chunks.push(e.data);
  const timer = setInterval(() => {
    const s = Math.floor((Date.now() - started) / 1000);
    $("rec").textContent = `Stop (${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")})`;
  }, 500);
  recorder.onstop = () => {
    clearInterval(timer);
    stream.getTracks().forEach((t) => t.stop());      // turn the mic off
    const blob = new Blob(chunks, { type: recorder.mimeType });
    recorder = null;
    $("rec").classList.remove("on");
    $("rec").textContent = "Record a story";
    setClip(blob, blob.type.includes("ogg") ? "ogg" : blob.type.includes("mp4") ? "mp4" : "webm");
  };
  recorder.start();
  $("rec").classList.add("on");
  $("rec").textContent = "Stop (0:00)";
};

// Step 1: the recording becomes text (Whisper, on this laptop).
$("write").onclick = async () => {
  $("write").disabled = true;
  say("Listening to the recording. A long story can take a few minutes. Leave this page open.");
  try {
    const res = await fetch(`/api/transcribe?ext=${ext}&lang=${$("lang").value}`, { method: "POST", body: clip });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    audioId = data.audio_id;
    $("transcript").value = data.text;
    $("transcriptBox").hidden = false;
    say(data.text ? "" : "Nothing was heard. Try a clearer recording.");
  } catch (err) {
    say(err.message);
  }
  $("write").disabled = false;
};

// Step 2: the text becomes a remembrance card (the open-weight model, on this laptop).
$("make").onclick = async () => {
  $("make").disabled = true;
  $("make").textContent = "Writing…";
  try {
    const res = await post("/api/card", { name: $("who").value, transcript: $("transcript").value });
    const c = await res.json();
    if (!res.ok) throw new Error(c.error);
    $("c-title").value = c.title;
    $("c-text").value = c.remembrance;
    $("c-loved").value = c.loved.join(", ");
    $("c-quote").textContent = c.quote;
    $("cardBox").hidden = false;
    say(c.truncated ? "This was a long story, so the card is based on the first part of it." : "");
  } catch (err) {
    say(err.message);
    checkStatus();
  }
  $("make").disabled = false;
  $("make").textContent = "Make the remembrance";
};

// Step 3: save everything as plain files in the memories folder.
$("save").onclick = async () => {
  const card = {
    title: $("c-title").value,
    remembrance: $("c-text").value,
    loved: $("c-loved").value.split(",").map((s) => s.trim()).filter(Boolean),
    quote: $("c-quote").textContent,
  };
  await post("/api/save", { name: $("who").value, transcript: $("transcript").value, audio_id: audioId, card });
  reset();
  say("Saved. It is now a plain folder inside the memories folder of this project.");
  loadShelf();
};

function reset() {
  clip = audioId = null;
  $("player").hidden = $("transcriptBox").hidden = $("cardBox").hidden = true;
  $("write").disabled = true;
  $("transcript").value = "";
}
$("again").onclick = () => { reset(); say(""); };

// Draws one saved story on the shelf.
function shelfCard(m) {
  const el = h("article", "memory");
  el.append(h("p", "who", m.name), h("h3", "", m.card.title || "Untitled"), h("p", "text", m.card.remembrance));
  if (m.card.loved && m.card.loved.length) {
    const chips = h("div", "chips");
    m.card.loved.forEach((t) => chips.appendChild(h("span", "chip", t)));
    el.appendChild(chips);
  }
  if (m.card.quote) el.appendChild(h("blockquote", "", m.card.quote));
  if (m.has_audio) {
    const a = h("audio");
    a.controls = true;
    a.preload = "none";
    a.src = `/api/audio/${m.folder}`;
    el.appendChild(a);
  }
  el.appendChild(h("p", "date", m.saved));
  return el;
}

async function loadShelf() {
  const items = await (await fetch("/api/memories")).json();
  $("shelf").replaceChildren(...(items.length ? items.map(shelfCard) : [h("p", "sub", "Nothing here yet. The first story you save will appear as a candle on this shelf.")]));
}

checkStatus();
loadShelf();
