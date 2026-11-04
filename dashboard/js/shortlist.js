// Shortlist: star faculty anywhere, add notes, then export CSV, print a one-pager, or share a link.
// Saved in this browser (localStorage).
const Shortlist = (() => {
  const KEY = "nmdsi-shortlist", NOTES = "nmdsi-shortlist-notes";
  let ids = [], notes = {};

  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(ids)); localStorage.setItem(NOTES, JSON.stringify(notes)); } catch {}
  }
  function init(shared) {
    try { ids = JSON.parse(localStorage.getItem(KEY) || "[]").filter(id => byId[id]); notes = JSON.parse(localStorage.getItem(NOTES) || "{}"); } catch {}
    if (shared) {
      const incoming = shared.split(",").map(decodeURIComponent).filter(id => byId[id] && !ids.includes(id));
      if (incoming.length) { ids.push(...incoming); save(); toast(`Added ${incoming.length} shared ${incoming.length === 1 ? "person" : "people"} to your shortlist`); }
    }
    badge();
  }
  const has = id => ids.includes(id);
  function toggle(id) {
    const p = byId[id]; if (!p) return;
    if (has(id)) { ids = ids.filter(x => x !== id); toast(`Removed ${p.name} from shortlist`); }
    else { ids.push(id); toast(`Added ${p.name} to shortlist`, { action: "View", onAction: () => setTab("shortlist") }); }
    save(); badge(); refreshStars();
    if (state.tab === "shortlist") render();
  }
  function addMany(list) {
    const fresh = list.filter(id => !has(id));
    ids.push(...fresh); save(); badge(); refreshStars();
    toast(fresh.length ? `Added ${fresh.length} to shortlist` : "Already on your shortlist", { action: "View", onAction: () => setTab("shortlist") });
  }
  function badge() {
    const b = document.getElementById("shortCount");
    b.textContent = ids.length; b.hidden = !ids.length;
  }

  function render() {
    const el = document.getElementById("shortList");
    const list = ids.map(id => byId[id]);
    document.getElementById("shortTitle").textContent = list.length
      ? `${list.length} ${list.length === 1 ? "person" : "people"} on your shortlist` : "Your shortlist is empty";
    document.querySelectorAll(".short-actions button").forEach(b => b.disabled = !list.length);
    const unis = new Set(list.map(p => p.university));
    document.getElementById("shortMeta").textContent = list.length
      ? `${[...unis].map(u => UNI_SHORT[u] || u).join(" + ")} · ${new Set(list.map(p => p.theme)).size} research themes` : "";
    if (!list.length) {
      el.innerHTML = `<div class="empty-state">
        <div class="big">☆</div>
        <p>Click the star on any faculty card or profile to save them here.<br>Then export a spreadsheet, print a one-page summary, or share a link.</p>
        <div class="chips center"><button class="chip primary" data-tab-go="match">Find an expert</button><button class="chip" data-tab-go="search">Browse faculty</button></div>
      </div>`;
      el.querySelectorAll("[data-tab-go]").forEach(b => b.onclick = () => setTab(b.dataset.tabGo));
      return;
    }
    el.innerHTML = list.map((p, i) => {
      const url = safeUrl(p.profile_url);
      return `<article class="s-row" style="--tc:${themeColor(p.theme)}">
        <div class="s-num">${i + 1}</div>
        <div class="avatar" aria-hidden="true">${esc(initials(p))}</div>
        <div class="s-main">
          <div class="s-head">
            <button class="linkish" data-open="${esc(p.id)}"><strong>${esc(p.name)}</strong></button>
            ${p.credentials ? `<span class="cred">${esc(p.credentials)}</span>` : ""}
            ${uniBadge(p.university)}
          </div>
          <div class="muted small">${esc(p.title || "")}${p.title ? " · " : ""}${esc(orgLine(p))}</div>
          <div class="theme" style="color:${themeColor(p.theme)}"><span class="dot"></span>${esc(p.theme)}</div>
          <div class="tags">${p.research_tags.slice(0, 6).map(t => `<span class="tag">${esc(t)}</span>`).join("")}</div>
          <textarea class="note" data-note="${esc(p.id)}" rows="1" placeholder="Add a note (why this person, next step…)">${esc(notes[p.id] || "")}</textarea>
        </div>
        <div class="s-side">
          ${url ? `<a class="small" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Profile ↗</a>` : ""}
          <button class="icon-x" data-star="${esc(p.id)}" title="Remove" aria-label="Remove ${esc(p.name)}">Remove</button>
        </div>
      </article>`;
    }).join("");
    el.querySelectorAll("[data-note]").forEach(t => {
      const grow = () => { t.style.height = "auto"; t.style.height = t.scrollHeight + "px"; };
      grow();
      t.oninput = () => { notes[t.dataset.note] = t.value; save(); grow(); };
    });
  }

  function csv() {
    const cols = ["Name", "Credentials", "Title", "University", "College", "Department", "Theme", "Research tags",
                  "Classes", "Funding", "Profile URL", "Note"];
    const cell = v => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const rows = ids.map(id => byId[id]).map(p => [p.name, p.credentials, p.title, p.university, p.college, p.department, p.theme,
      p.research_tags.join("; "), p.classes.map(c => [c.code, c.title].filter(Boolean).join(" ")).join("; "),
      p.funding.map(f => f.name).join("; "), p.profile_url, notes[p.id]]);
    const text = "﻿" + [cols, ...rows].map(r => r.map(cell).join(",")).join("\r\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
    a.download = `nmdsi-shortlist-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  // A clean printable page (also "Save as PDF" from the print dialog).
  function print() {
    const date = new Date().toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
    document.getElementById("printSheet").innerHTML = `
      <div class="p-head"><img src="assets/nmdsi-mark.svg" alt=""><div><h1>NMDSI Faculty Shortlist</h1>
        <p>${ids.length} faculty · prepared ${esc(date)}</p></div></div>
      ${ids.map(id => byId[id]).map(p => {
        const summary = (p.research_summary || p.directory_research || "").slice(0, 520).replace(/\s+\S*$/, "");
        return `<section class="p-person">
          <h2>${esc(p.name)}${p.credentials ? ` <small>${esc(p.credentials)}</small>` : ""}</h2>
          <div class="p-org">${esc(p.title || "")}${p.title ? " · " : ""}${esc(orgLine(p))} · <strong>${esc(p.university)}</strong></div>
          <div class="p-theme">${esc(p.theme)}${p.research_tags.length ? " — " + esc(p.research_tags.slice(0, 6).join(", ")) : ""}</div>
          ${summary ? `<p>${esc(summary)}${summary.length >= 500 ? "…" : ""}</p>` : ""}
          ${p.classes.length ? `<div class="p-small"><strong>Teaches:</strong> ${esc(p.classes.slice(0, 4).map(c => c.title).join("; "))}</div>` : ""}
          ${notes[p.id] ? `<div class="p-note"><strong>Note:</strong> ${esc(notes[p.id])}</div>` : ""}
          ${safeUrl(p.profile_url) ? `<div class="p-small">${esc(p.profile_url)}</div>` : ""}
        </section>`;
      }).join("")}`;
    window.print();
  }

  async function share() {
    const url = `${location.origin}${location.pathname}?tab=shortlist&ids=${ids.map(encodeURIComponent).join(",")}`;
    try { await navigator.clipboard.writeText(url); toast("Share link copied to clipboard"); }
    catch { window.prompt("Copy this link:", url); }
  }
  function clear() {
    if (!confirm("Remove everyone from your shortlist?")) return;
    ids = []; save(); badge(); refreshStars(); render();
  }

  document.getElementById("shortCsv").onclick = csv;
  document.getElementById("shortPrint").onclick = print;
  document.getElementById("shortShare").onclick = share;
  document.getElementById("shortClear").onclick = clear;
  return { init, has, toggle, addMany, render, ids: () => ids.slice() };
})();

function toast(msg, { action, onAction } = {}) {
  const t = document.getElementById("toast");
  t.innerHTML = `<span>${esc(msg)}</span>${action ? `<button>${esc(action)}</button>` : ""}`;
  if (action) t.querySelector("button").onclick = () => { t.classList.remove("show"); onAction(); };
  t.classList.add("show");
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("show"), 3200);
}
