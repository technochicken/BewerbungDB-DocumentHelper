"use strict";

const $ = (sel) => document.querySelector(sel);
const view = $("#view");
let status = null;
let currentView = "new";
let newState = { jobId: "", job: null, result: null };
let pendingJob = null;   // Job-ID aus einem bewerbungdb://create-application/<id>-Link, wird beim Öffnen geladen

// Aufruf per Link: nur die ID übernehmen (streng geprüft) – erstellt wird erst nach Klick des Nutzers.
(function readJobFromAddress() {
  const id = new URLSearchParams(location.search).get("job");
  if (id && /^[A-Za-z0-9_-]{1,64}$/.test(id)) { pendingJob = id; newState = { jobId: id, job: null, result: null }; }
  if (location.search) history.replaceState(null, "", "/");
})();

// ── Helfer ────────────────────────────────────────────────────────────────────
// Erzeugt DOM-Elemente; Text wird immer als Text gesetzt (nie als HTML).
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, "");
    else if (v !== false && v != null) el.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return el;
}

async function api(path, options = {}) {
  const opts = { ...options };
  if (opts.body && typeof opts.body !== "string") {
    opts.body = JSON.stringify(opts.body);
    opts.headers = { "Content-Type": "application/json" };
  }
  let resp;
  try { resp = await fetch("/api" + path, opts); }
  catch { throw new Error("Die App antwortet nicht. Bitte neu starten."); }
  if (!resp.ok) {
    let msg = `Fehler (${resp.status})`;
    try { msg = (await resp.json()).detail || msg; } catch {}
    const err = new Error(msg);
    err.status = resp.status;
    throw err;
  }
  return resp.json();
}

// Bestätigungsdialog (eigenes <dialog> statt window.confirm: lesbar, gestaltbar, mit Warnfarbe).
function confirmDialog({ title, body, confirmLabel = "OK", cancelLabel = "Abbrechen", danger = false }) {
  return new Promise((resolve) => {
    const dlg = h("dialog", { class: "modal" },
      h("h2", {}, title),
      h("div", { class: "modal-body" }, body),
      h("div", { class: "row modal-actions" },
        h("button", { class: "btn", onclick: () => dlg.close("cancel") }, cancelLabel),
        h("button", { class: "btn " + (danger ? "danger" : "primary"), onclick: () => dlg.close("ok") }, confirmLabel)));
    dlg.addEventListener("close", () => { resolve(dlg.returnValue === "ok"); dlg.remove(); });
    document.body.append(dlg);
    dlg.showModal();
  });
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), 2800);
}

const fmtDate = (iso) => new Date(iso).toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" });
const fmtSize = (b) => (b > 1048576 ? (b / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(b / 1024)) + " KB");
const fileUrl = (folder, name, download = false) =>
  `/api/applications/${encodeURIComponent(folder)}/files/${encodeURIComponent(name)}${download ? "?download=true" : ""}`;

// ── Status / Hinweisleiste ────────────────────────────────────────────────────
async function refreshStatus() {
  status = await api("/status");
  $("#version").textContent = "Version " + status.version;
  const problems = [];
  if (!status.libreoffice) problems.push("LibreOffice wurde nicht gefunden (nötig für PDFs).");
  if (!status.api_key_set) problems.push("Es ist noch kein API-Schlüssel eingetragen.");
  if (!status.profil_complete) problems.push("Dein Profil ist noch unvollständig.");
  const missingTpl = Object.entries(status.templates).filter(([, ok]) => !ok).map(([t]) => t);
  if (missingTpl.length) problems.push("Vorlagen fehlen: " + missingTpl.join(", "));
  const banner = $("#banner");
  banner.hidden = problems.length === 0;
  banner.replaceChildren(
    h("strong", {}, "Einrichtung unvollständig: "), problems.join(" "), " ",
    h("a", { onclick: () => show("settings") }, "Zu den Einstellungen"),
  );
}

// ── Navigation ────────────────────────────────────────────────────────────────
const views = { new: viewNew, library: viewLibrary, profile: viewProfile, settings: viewSettings };

async function show(name, arg) {
  currentView = name;
  document.querySelectorAll("#nav button").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  try { await refreshStatus(); } catch (e) { toast(e.message); }
  view.replaceChildren();
  await views[name](arg);
}
$("#nav").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) show(b.dataset.view); });

// ── Ansicht: Neue Bewerbung ───────────────────────────────────────────────────
function viewNew() {
  const input = h("input", { type: "text", class: "grow", placeholder: "Job-ID, z. B. c876474e3c", autocomplete: "off", spellcheck: "false", value: newState.jobId });
  const loadBtn = h("button", { class: "btn primary" }, "Stelle laden");
  const out = h("div");

  async function load() {
    newState.jobId = input.value.trim();
    newState.result = null;
    if (!newState.jobId) return;
    loadBtn.disabled = true; loadBtn.replaceChildren(h("span", { class: "spinner" }), "Lade …");
    try { newState.job = await api("/jobs/" + encodeURIComponent(newState.jobId)); }
    catch (e) { newState.job = null; out.replaceChildren(h("div", { class: "notice err" }, e.message)); return; }
    finally { loadBtn.disabled = false; loadBtn.textContent = "Stelle laden"; }
    renderJob();
  }

  function renderJob() {
    const j = newState.job;
    const missing = Object.entries(j.missing);
    const exists = j.existing;
    const genBtn = h("button", { class: exists ? "btn danger" : "btn primary", onclick: () => generate(genBtn) },
      exists ? "Neu erstellen und überschreiben …" : "Bewerbung erstellen");
    out.replaceChildren(h("div", { class: "card" },
      h("h2", {}, "Stelle gefunden"),
      exists && h("div", { class: "notice warn" },
        h("strong", {}, "Für diese Stelle gibt es bereits eine Bewerbung "),
        `(zuletzt geändert ${fmtDate(exists.modified)}). Wenn du neu erstellst, werden die vorhandenen Word-Dateien überschrieben – auch deine Änderungen darin.`,
        h("div", { style: "margin-top:10px" },
          h("button", { class: "btn small", onclick: () => show("library", exists.folder) }, "Bestehende Bewerbung ansehen"))),
      h("dl", { class: "meta" },
        h("dt", {}, "Stelle"), h("dd", {}, j.title || "–"),
        h("dt", {}, "Firma"), h("dd", {}, j.company || "–"),
        h("dt", {}, "Ort"), h("dd", {}, j.location || "–"),
        h("dt", {}, "Kontakt"), h("dd", {}, j.contact || "–")),
      !j.has_text && h("div", { class: "notice warn" }, "Für diese Stelle gibt es noch keinen Bewerbungstext in der BewerbungDB."),
      missing.length > 0 && h("div", { class: "notice warn" },
        "Diese Platzhalter der Vorlagen bleiben leer:",
        h("ul", {}, missing.map(([t, vars]) => h("li", {}, h("strong", {}, t + ": "), vars.map((v) => h("code", {}, v + " ")))))),
      h("div", { class: "row", style: "margin-top:16px" }, genBtn),
      h("div", { id: "result" })));
    if (newState.result) renderResult(newState.result);
  }

  const confirmOverwrite = () => confirmDialog({
    title: "Bestehende Bewerbung überschreiben?",
    body: h("div", {},
      h("p", {}, "Für diese Stelle wurde bereits eine Bewerbung erstellt. Beim Überschreiben werden Deckblatt, Anschreiben und Lebenslauf neu aus den Daten der BewerbungDB erzeugt."),
      h("p", {}, h("strong", {}, "Änderungen, die du in den Word-Dateien gemacht hast, gehen dabei verloren."))),
    confirmLabel: "Ja, überschreiben", danger: true,
  });

  async function generate(btn) {
    const label = btn.textContent;
    let overwrite = false;
    if (newState.job && newState.job.existing) {
      if (!(await confirmOverwrite())) return;
      overwrite = true;
    }
    btn.disabled = true; btn.replaceChildren(h("span", { class: "spinner" }), "Erstelle Dokumente …");
    try {
      let r;
      try {
        r = await api("/applications", { method: "POST", body: { job_id: newState.jobId, overwrite } });
      } catch (e) {
        // Zwischenzeitlich wurde die Bewerbung angelegt (z. B. in einem zweiten Fenster): nachfragen.
        if (e.status !== 409 || !(await confirmOverwrite())) throw e;
        r = await api("/applications", { method: "POST", body: { job_id: newState.jobId, overwrite: true } });
      }
      newState.result = r;
      if (r.errors.length === 0) { newState.job = null; return show("library", r.folder); }  // gleich anzeigen
      renderResult(r);   // bei Problemen bleiben, damit die Meldungen lesbar sind
    } catch (e) {
      if (e.status !== 409) $("#result").replaceChildren(h("div", { class: "notice err" }, e.message));
    } finally { btn.disabled = false; btn.textContent = label; }
  }

  function renderResult(r) {
    const box = $("#result");
    box.replaceChildren(
      r.errors.length > 0 && h("div", { class: "notice err" }, "Nicht alles hat geklappt:", h("ul", {}, r.errors.map((e) => h("li", {}, e)))),
      Object.keys(r.files).length > 0 && h("div", { class: "notice ok" }, `${Object.keys(r.files).length} Dateien erstellt.`),
      h("div", { class: "row", style: "margin-top:12px" },
        h("button", { class: "btn", onclick: () => show("library", r.folder) }, "Dokumente ansehen"),
        h("button", { class: "btn", onclick: () => api(`/applications/${encodeURIComponent(r.folder)}/open`, { method: "POST" }) }, "Ordner öffnen")));
  }

  input.addEventListener("keydown", (e) => e.key === "Enter" && load());
  loadBtn.addEventListener("click", load);
  view.append(
    h("h1", {}, "Neue Bewerbung"),
    h("p", { class: "sub" }, "Gib die Job-ID aus der BewerbungDB ein. Die Unterlagen werden automatisch erstellt."),
    h("div", { class: "card" }, h("div", { class: "row" }, input, loadBtn)),
    out);
  if (newState.job) renderJob();
  input.focus();
  if (pendingJob) { pendingJob = null; load(); }
}

// ── Ansicht: Bewerbungen / Dokumente ──────────────────────────────────────────
let libraryFilter = { q: "", sort: "modified", dir: "desc" };

async function viewLibrary(openFolder) {
  const items = await api("/applications");
  if (openFolder) {
    const item = items.find((i) => i.folder === openFolder);
    if (item) return renderDetail(item);
  }
  view.append(h("h1", {}, "Bewerbungen"));
  if (!items.length) {
    view.append(h("p", { class: "sub" }, "Noch keine Bewerbungen."),
      h("div", { class: "empty" }, "Lege mit „Neue Bewerbung“ los."));
    return;
  }

  const count = h("p", { class: "sub" });
  const search = h("input", {
    type: "search", class: "grow", placeholder: "Suchen nach Stelle oder Firma …", autocomplete: "off", spellcheck: "false",
    value: libraryFilter.q,
  });
  const body = h("tbody");
  const columns = [
    ["title", "Stelle"], ["company", "Firma"], ["location", "Ort"], ["modified", "Zuletzt geändert"], ["files", "Dateien"],
  ];
  const headRow = h("tr");
  const kinds = { pdf: "PDF", word: "Word", mail: "E-Mail" };

  function paintHeader() {
    headRow.replaceChildren(...columns.map(([key, label]) => {
      const active = libraryFilter.sort === key;
      return h("th", {
        class: "sortable" + (active ? " active" : ""),
        "aria-sort": active ? (libraryFilter.dir === "asc" ? "ascending" : "descending") : "none",
        onclick: () => {
          libraryFilter.dir = active && libraryFilter.dir === "asc" ? "desc" : "asc";
          libraryFilter.sort = key; paintHeader(); paintRows();
        },
      }, label, active ? (libraryFilter.dir === "asc" ? " ▲" : " ▼") : "");
    }));
  }

  function paintRows() {
    libraryFilter.q = search.value;
    const words = search.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const matches = items.filter((i) => {
      const hay = `${i.title} ${i.company}`.toLowerCase();
      return words.every((w) => hay.includes(w));   // alle Suchwörter müssen vorkommen
    });
    const val = (i) => (libraryFilter.sort === "files" ? i.files.length : String(i[libraryFilter.sort] || "").toLowerCase());
    matches.sort((a, b) => (val(a) < val(b) ? -1 : val(a) > val(b) ? 1 : 0) * (libraryFilter.dir === "asc" ? 1 : -1));

    count.textContent = words.length ? `${matches.length} von ${items.length} Bewerbungen` : `${items.length} Bewerbungen`;
    if (!matches.length) {
      body.replaceChildren(h("tr", {}, h("td", { colspan: columns.length, class: "empty" }, "Keine Bewerbung gefunden.")));
      return;
    }
    body.replaceChildren(...matches.map((i) => {
      const present = [...new Set(i.files.map((f) => f.kind))].filter((k) => kinds[k]);
      return h("tr", { class: "clickable", tabindex: "0", onclick: () => renderDetail(i),
                       onkeydown: (e) => e.key === "Enter" && renderDetail(i) },
        h("td", { class: "cell-title" }, h("div", {}, i.title), h("div", { class: "hint" }, "Job " + i.job_id)),
        h("td", {}, i.company || "–"), h("td", {}, i.location || "–"),
        h("td", { class: "nowrap" }, fmtDate(i.modified)),
        h("td", {}, h("div", { class: "chips inline" }, present.map((k) => h("span", { class: "chip" }, kinds[k])))));
    }));
  }

  search.addEventListener("input", paintRows);
  paintHeader(); paintRows();
  view.append(count,
    h("div", { class: "card toolbar" }, h("div", { class: "row" }, search)),
    h("div", { class: "card table-card" }, h("table", { class: "table" }, h("thead", {}, headRow), body)));
  search.focus();
}

function renderDetail(item) {
  view.replaceChildren();
  const preview = h("div");
  const enc = encodeURIComponent(item.folder);
  const openFile = (name) => api(`/applications/${enc}/open?name=${encodeURIComponent(name)}`, { method: "POST" })
    .catch((e) => toast(e.message));
  const wordFiles = item.files.filter((f) => f.type);   // einzelne Word-Dokumente (Deckblatt, Anschreiben, Lebenslauf)

  async function run(btn, busyText, body, doneText) {
    const label = btn.textContent;
    btn.disabled = true; btn.replaceChildren(h("span", { class: "spinner" }), busyText);
    try {
      const r = await api("/applications", { method: "POST", body: { job_id: item.job_id, ...body } });
      toast(r.errors.length ? r.errors[0] : doneText);
      show("library", item.folder);   // Ansicht mit den neuen Dateien neu laden
    } catch (e) { toast(e.message); btn.disabled = false; btn.textContent = label; }
  }

  // Word-Dateien aus den aktuellen Daten der BewerbungDB neu erzeugen (eigene Änderungen gehen verloren)
  async function regenerate(btn, types, what) {
    const ok = await confirmDialog({
      title: `${what} neu erstellen?`,
      body: h("div", {},
        h("p", {}, `${what} wird mit den aktuellen Daten aus der BewerbungDB neu erzeugt (z. B. nach einer Änderung des Bewerbungstextes). Die PDFs und der E-Mail-Entwurf werden ebenfalls aktualisiert.`),
        h("p", {}, h("strong", {}, "Änderungen, die du in Word gemacht hast, gehen dabei verloren."))),
      confirmLabel: "Ja, neu erstellen", danger: true,
    });
    if (ok) run(btn, "Erstelle …", { types, overwrite: true }, `${what} neu erstellt`);
  }

  const pdfBtn = h("button", { class: "btn", onclick: () => run(pdfBtn, "Erstelle PDFs …", { pdf_only: true }, "PDFs aktualisiert") },
    "PDFs aus Word-Dateien neu erstellen");
  const allBtn = h("button", { class: "btn", onclick: () => regenerate(allBtn, null, "Alle Word-Dokumente") },
    "Alle Word-Dokumente aus Datenbank neu erstellen");

  view.append(
    h("button", { class: "back", onclick: () => show("library") }, "← Alle Bewerbungen"),
    h("h1", {}, item.title), h("p", { class: "sub" }, `${item.company || "–"} · Job ${item.job_id}`),
    h("div", { class: "card" }, h("div", { class: "files" }, item.files.map((f) => {
      const regenBtn = f.type && h("button", { class: "btn small", title: "Mit den aktuellen Daten der BewerbungDB neu erstellen",
        onclick: () => regenerate(regenBtn, [f.type], f.label) }, "Neu aus Datenbank");
      return h("div", { class: "file" },
        h("div", { class: "ficon " + f.kind }, { pdf: "PDF", word: "DOC", mail: "MAIL" }[f.kind] || "…"),
        h("div", { class: "name" }, h("div", {}, f.label), h("div", {}, f.name + " · " + fmtSize(f.size))),
        f.kind === "pdf" && h("button", { class: "btn small", onclick: () => { preview.replaceChildren(h("iframe", { class: "preview", src: fileUrl(item.folder, f.name) })); preview.scrollIntoView({ behavior: "smooth" }); } }, "Vorschau"),
        (f.kind === "word" || f.kind === "mail") && h("button", { class: "btn small", onclick: () => openFile(f.name) }, f.kind === "word" ? "Bearbeiten" : "Öffnen"),
        regenBtn,
        h("a", { class: "btn small", style: "text-decoration:none", href: fileUrl(item.folder, f.name, true) }, "Speichern"));
    }))),
    h("div", { class: "card" },
      h("h2", {}, "Aktionen"),
      h("div", { class: "row" }, pdfBtn, wordFiles.length > 0 && allBtn,
        h("button", { class: "btn", onclick: () => api(`/applications/${enc}/open`, { method: "POST" }) }, "Ordner öffnen")),
      h("p", { class: "hint" }, "Tipp: Word-Datei bearbeiten, speichern und danach „PDFs neu erstellen“ – deine Änderungen bleiben erhalten. „Neu aus Datenbank“ ersetzt die Word-Datei dagegen durch eine frische Version.")),
    preview);
}

// ── Ansicht: Profil ───────────────────────────────────────────────────────────
const PROFILE_FIELDS = [
  ["titel", "Titel (optional)"], ["vorname", "Vorname"], ["nachname", "Nachname"], ["email", "E-Mail"],
  ["telefon", "Telefon"], ["mobil", "Mobil (optional)"], ["strasse", "Straße"], ["hausnummer", "Hausnummer"],
  ["plz", "PLZ"], ["ort", "Ort"],
];

async function viewProfile() {
  const data = await api("/profil");
  const inputs = {};
  const form = h("div", { class: "form-grid" }, PROFILE_FIELDS.map(([key, label]) => {
    inputs[key] = h("input", { type: "text", value: data[key] || "" });
    return h("div", { class: "field" }, h("label", {}, label), inputs[key]);
  }));
  const save = async () => {
    const values = Object.fromEntries(Object.entries(inputs).map(([k, el]) => [k, el.value]));
    try { await api("/profil", { method: "PUT", body: { values } }); toast("Profil gespeichert"); await refreshStatus(); }
    catch (e) { toast(e.message); }
  };
  view.append(h("h1", {}, "Mein Profil"), h("p", { class: "sub" }, "Diese Angaben erscheinen in deinen Bewerbungsunterlagen."),
    h("div", { class: "card" }, form, h("div", { class: "row", style: "margin-top:18px" }, h("button", { class: "btn primary", onclick: save }, "Speichern"))));
}

// ── Ansicht: Einstellungen ────────────────────────────────────────────────────
async function viewSettings() {
  const cfg = await api("/config");
  const f = {
    api_base_url: h("input", { type: "text", value: cfg.api_base_url }),
    api_key: h("input", { type: "password", placeholder: cfg.api_key_set ? "•••••••• (gespeichert – leer lassen zum Behalten)" : "API-Schlüssel einfügen" }),
    libreoffice_path: h("input", { type: "text", value: cfg.libreoffice_path }),
    arbeitsordner: h("input", { type: "text", value: cfg.arbeitsordner }),
    vorlagen_pfad: h("input", { type: "text", value: cfg.vorlagen_pfad }),
  };
  const field = (label, key, hint) => h("div", { class: "field" }, h("label", {}, label), f[key], hint && h("span", { class: "hint" }, hint));
  const save = async () => {
    try {
      await api("/config", { method: "PUT", body: Object.fromEntries(Object.entries(f).map(([k, el]) => [k, el.value])) });
      toast("Einstellungen gespeichert"); show("settings");
    } catch (e) { toast(e.message); }
  };
  const check = (ok, text) => h("li", { class: ok ? "" : "bad" }, text);
  view.append(
    h("h1", {}, "Einstellungen"), h("p", { class: "sub" }, "Verbindung, Ordner und Programme."),
    h("div", { class: "card" }, h("h2", {}, "Zustand"), h("ul", { class: "checks" },
      check(status.libreoffice, status.libreoffice ? "LibreOffice gefunden" : "LibreOffice nicht gefunden"),
      check(status.api_key_set, status.api_key_set ? "API-Schlüssel hinterlegt" : "API-Schlüssel fehlt"),
      check(status.profil_complete, status.profil_complete ? "Profil vollständig" : "Profil unvollständig"),
      ...Object.entries(status.templates).map(([t, ok]) => check(ok, ok ? `Vorlage ${t} gefunden` : `Vorlage ${t} fehlt`)))),
    h("div", { class: "card" }, h("h2", {}, "BewerbungDB"), h("div", { class: "form-grid" },
      field("Adresse der BewerbungDB", "api_base_url"), field("API-Schlüssel", "api_key"))),
    h("div", { class: "card" }, h("h2", {}, "Ordner & Programme"), h("div", { class: "form-grid" },
      field("Bewerbungen speichern in", "arbeitsordner", "Relative Pfade gelten ab dem Programmordner."),
      field("Vorlagen-Ordner", "vorlagen_pfad"), field("LibreOffice (soffice.exe)", "libreoffice_path")),
      h("div", { class: "row", style: "margin-top:14px" },
        h("button", { class: "btn", onclick: () => api("/open-templates", { method: "POST" }).catch((e) => toast(e.message)) }, "Vorlagen-Ordner öffnen"))),
    h("div", { class: "row" }, h("button", { class: "btn primary", onclick: save }, "Speichern")));
}

// ── Erststart-Assistent ───────────────────────────────────────────────────────
function skippedWizard() { try { return sessionStorage.getItem("skipWizard") === "1"; } catch { return false; } }

async function wizard() {
  document.body.classList.add("wizard");
  const cfg = await api("/config");
  const profil = await api("/profil");
  const errBox = h("div");
  const inputs = {};
  const input = (key, label, opts = {}) => {
    inputs[key] = h("input", { type: opts.type || "text", value: opts.value ?? profil[key] ?? "", placeholder: opts.placeholder || "" });
    return h("div", { class: "field" }, h("label", {}, label), inputs[key]);
  };
  const shell = (step, title, sub, ...body) => {
    view.replaceChildren(h("div", { class: "wizard-card" },
      h("div", { class: "steps" }, [1, 2].map((n) => h("span", { class: n <= step ? "on" : "" }))),
      h("h1", {}, title), h("p", { class: "sub" }, sub), ...body));
  };
  const skip = h("a", { class: "skip", onclick: () => { try { sessionStorage.setItem("skipWizard", "1"); } catch {} finish(); } }, "Später einrichten");

  function step1() {
    shell(1, "Willkommen bei BewerbungDB", "Ein paar Angaben für deine Unterlagen – das dauert eine Minute.",
      h("div", { class: "form-grid" },
        input("vorname", "Vorname"), input("nachname", "Nachname"),
        input("email", "E-Mail", { type: "email" }), input("telefon", "Telefon (optional)"),
        input("strasse", "Straße"), input("hausnummer", "Hausnummer"),
        input("plz", "PLZ"), input("ort", "Ort")),
      errBox,
      h("div", { class: "row", style: "margin-top:20px" },
        h("button", { class: "btn primary", onclick: next }, "Weiter"), skip));
  }
  function next() {
    const missing = ["vorname", "nachname", "email"].filter((k) => !inputs[k].value.trim());
    if (missing.length) { errBox.replaceChildren(h("div", { class: "notice err" }, "Bitte Vorname, Nachname und E-Mail ausfüllen.")); return; }
    Object.keys(inputs).forEach((k) => (profil[k] = inputs[k].value.trim()));
    step2();
  }

  function step2() {
    const result = h("div");
    const back = h("a", { class: "skip", onclick: step1 }, "← Zurück");
    let tested = false;
    const doTest = async (btn) => {
      btn.disabled = true; btn.replaceChildren(h("span", { class: "spinner" }), "Teste …");
      try {
        const r = await api("/test-connection", { method: "POST", body: { api_base_url: inputs.api_base_url.value, api_key: inputs.api_key.value } });
        tested = r.ok;
        result.replaceChildren(h("div", { class: "notice " + (r.ok ? "ok" : "err") }, r.message));
      } catch (e) { result.replaceChildren(h("div", { class: "notice err" }, e.message)); }
      btn.disabled = false; btn.textContent = "Verbindung testen";
    };
    const testBtn = h("button", { class: "btn", onclick: () => doTest(testBtn) }, "Verbindung testen");
    const doneBtn = h("button", { class: "btn primary", onclick: () => save(doneBtn) }, "Fertig");
    const save = async (btn) => {
      if (!inputs.api_key.value.trim() && !cfg.api_key_set) { result.replaceChildren(h("div", { class: "notice err" }, "Bitte den API-Schlüssel eintragen.")); return; }
      btn.disabled = true;
      try {
        await api("/profil", { method: "PUT", body: { values: profil } });
        await api("/config", { method: "PUT", body: { api_base_url: inputs.api_base_url.value, api_key: inputs.api_key.value } });
        finish();
      } catch (e) { result.replaceChildren(h("div", { class: "notice err" }, e.message)); btn.disabled = false; }
    };
    const lo = status.libreoffice
      ? h("div", { class: "notice ok" }, "LibreOffice gefunden – PDFs können erstellt werden.")
      : h("div", { class: "notice warn" }, "LibreOffice wurde nicht gefunden. Ohne LibreOffice entstehen keine PDFs – bitte installieren (libreoffice.org) und die App neu starten.");
    shell(2, "Verbindung zur BewerbungDB", "Adresse und persönlicher API-Schlüssel deiner BewerbungDB.",
      h("div", { class: "form-grid" },
        input("api_base_url", "Adresse", { value: cfg.api_base_url }),
        input("api_key", "API-Schlüssel", { type: "password", value: "", placeholder: cfg.api_key_set ? "•••••••• (bereits gespeichert)" : "Schlüssel einfügen" })),
      h("div", { class: "row", style: "margin-top:14px" }, testBtn), result, lo,
      h("div", { class: "row", style: "margin-top:20px" }, doneBtn, back, skip));
  }

  async function finish() {
    document.body.classList.remove("wizard");
    show("new");
  }
  step1();
}

async function start() {
  try { await refreshStatus(); } catch (e) { toast(e.message); }
  if (status && status.first_run && !skippedWizard()) return wizard();
  show("new");
}

// Meldet dem Programm, dass das Fenster noch offen ist (sonst beendet es sich selbst).
const ping = () => fetch("/api/ping", { method: "POST" }).catch(() => {});
ping(); setInterval(ping, 5000);
window.addEventListener("pagehide", () => navigator.sendBeacon("/api/bye"));

start();
