const THEMES = ["AI/ML & NLP", "Health Informatics", "Statistics & Mathematics", "Operations & Supply Chain",
  "Finance & Economics", "Climate & Environment", "Security & Systems", "Social Science & Policy",
  "Biology & Biomedical", "Humanities & Communication"];
const themeColor = t => `var(--t${THEMES.indexOf(t) + 1})`;
const UNI_SHORT = { "UW-Milwaukee": "UWM", "Marquette University": "Marquette" };
const UNI_CLASS = { "UW-Milwaukee": "uwm", "Marquette University": "mu" };
const UNI_LOGO = { "UW-Milwaukee": "assets/uwm-logo.svg", "Marquette University": "assets/marquette-logo.png" };
const uniBadge = u => `<span class="uni ${UNI_CLASS[u] || "other"}">${esc(UNI_SHORT[u] || u)}</span>`;
const initials = p => p.name.replace(/\b(Dr|Jr|Sr|II|III)\b\.?/g, "").split(/\s+/).filter(Boolean)
  .filter((w, i, a) => i === 0 || i === a.length - 1).map(w => w[0]).join("").toUpperCase();
// Headshot from the university's own site (loaded only when visible); initials show if it's missing or fails.
const avatar = (p, tag = "div") => p.photo_url
  ? `<${tag} class="avatar has-photo" aria-hidden="true">${esc(initials(p))}<img src="${esc(p.photo_url)}" alt="" loading="lazy"
      decoding="async" referrerpolicy="no-referrer" onerror="this.parentNode.classList.remove('has-photo');this.remove()"></${tag}>`
  : `<${tag} class="avatar" aria-hidden="true">${esc(initials(p))}</${tag}>`;
const FUNDING_LABEL = { unknown: "Not stated", internal: "Internal / university", "industry partner": "Industry partner" };
const STATUS_LABEL = { ok: "Profile read", http_error: "Profile link broken", no_url: "No profile link",
                       parsed_empty: "Profile had no details", redirected_away: "Profile link redirects elsewhere" };

const FACETS = [
  { key: "university", title: "University", values: p => [p.university], label: v => v },
  { key: "theme", title: "Research theme", values: p => [p.theme], label: v => v, dot: true },
  { key: "industry", title: "Industry", values: p => p.industries.map(i => i.name), label: v => v },
  { key: "funding", title: "Funding", values: p => p.funding.length ? p.funding.map(f => f.name) : ["unknown"],
    label: v => FUNDING_LABEL[v] || v },
];

const state = { q: "", sel: Object.fromEntries(FACETS.map(f => [f.key, new Set()])),
                preset: false, hasClasses: false, group: null, showAll: false, sort: "last", openId: null,
                tab: "search", related: [], exact: false, why: new Map() };
let people = [], byId = {}, groups = {}, fuse, ix, presetName = null, presetIds = new Set();
const TABS = ["search", "match", "network", "shortlist"];

const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeUrl = u => /^https?:\/\//i.test(u || "") ? u : null;
const lastName = p => p.name.split(" ").at(-1);

async function load() {
  try {
    const [f, g] = await Promise.all([fetch("../faculty.json"), fetch("../data/groupings.json")]);
    if (!f.ok || !g.ok) throw new Error(`HTTP ${f.status}/${g.status}`);
    people = await f.json(); groups = await g.json();
  } catch (e) {
    document.getElementById("cards").innerHTML = `<div class="empty">Could not load data (${esc(e.message)}).<br>
      Start the server from the project folder with <code>python -m http.server 8000</code>, then open
      <code>http://localhost:8000/dashboard/</code>.</div>`;
    return;
  }
  people.forEach(p => byId[p.id] = p);
  presetName = Object.keys(groups.presets || {})[0] || null;
  if (presetName) presetIds = new Set(groups.presets[presetName].ids);
  const unis = Object.keys(groups.by_university).map(u => UNI_SHORT[u] || u).join(" & ");
  document.getElementById("subtitle").textContent = `${people.length} affiliated faculty · ${unis}`;
  document.getElementById("heroSub").textContent =
    `Search ${people.length} affiliated faculty at ${Object.keys(groups.by_university).join(" and ")} by name, research topic, class, or department.`;
  ix = new TextIndex(people);
  // Fuzzy matching only on short fields (names, tags, class codes) so typos still work; topic relevance comes from ix.
  fuse = new Fuse(people, {
    keys: [{ name: "name", weight: 3 }, { name: "research_tags", weight: 1.5 }, "classes.code", "classes.title", "department"],
    threshold: 0.3, ignoreLocation: true, minMatchCharLength: 2, includeScore: true,
  });
  const params = new URLSearchParams(location.search);
  const q0 = params.get("q");
  if (q0) { state.q = q0; document.getElementById("q").value = q0; }
  Shortlist.init(params.get("ids"));
  Match.init();
  setTab(TABS.includes(params.get("tab")) ? params.get("tab") : "search", { push: false });
  const h = decodeURIComponent(location.hash.slice(1));
  if (byId[h]) openDrawer(h);
}

/* ---------- filtering ---------- */
function passes(p, skip) {
  for (const f of FACETS) {
    if (f.key === skip) continue;
    const s = state.sel[f.key];
    if (s.size && !f.values(p).some(v => s.has(v))) return false;
  }
  if (skip !== "views") {
    if (state.preset && !presetIds.has(p.id)) return false;
    if (state.hasClasses && !p.classes.length) return false;
  }
  if (skip !== "group" && state.group && !state.group.ids.has(p.id)) return false;
  return true;
}
// Smart search: topic relevance (with related terms) blended with fuzzy name/tag matching for typos.
function searchBase() {
  const q = state.q.trim();
  state.why = new Map(); state.related = [];
  if (q.length < 2) return people;
  const { results, added } = ix.search(q, { expand: !state.exact });
  state.related = added;
  const score = new Map(), top = results[0]?.score || 1;
  for (const r of results) {
    if (r.score < top * 0.08) continue;
    score.set(r.p.id, r.score / top);
    state.why.set(r.p.id, ix.explain(r.p, r.hits));
  }
  for (const r of fuse.search(q)) {
    const f = (1 - r.score) * (r.score < 0.05 ? 1.2 : 0.8);
    score.set(r.item.id, Math.max(score.get(r.item.id) || 0, f) + (score.has(r.item.id) ? 0.1 : 0));
  }
  return [...score].sort((a, b) => b[1] - a[1]).map(([id]) => byId[id]);
}

/* ---------- sidebar ---------- */
function optionRow({ checked, label, count, dot, onChange }) {
  const row = document.createElement("label");
  row.className = "opt" + (count === 0 && !checked ? " zero" : "");
  row.innerHTML = `<input type="checkbox" ${checked ? "checked" : ""}>
    ${dot ? `<span class="dot" style="color:${dot}"></span>` : ""}
    <span class="lbl">${esc(label)}</span><span class="n">${count}</span>`;
  row.querySelector("input").onchange = onChange;
  return row;
}
function section(title, open, key) {
  const d = document.createElement("details"); d.className = "fsec";
  d.open = sectionOpen[key] ?? open;
  d.ontoggle = () => { sectionOpen[key] = d.open; };
  d.innerHTML = `<summary>${esc(title)}</summary>`;
  return d;
}
const sectionOpen = {};

function buildSidebar(base) {
  const el = document.getElementById("sidebar");
  const scroll = el.scrollTop; el.innerHTML = "";

  // Quick views
  const views = section("Quick views", true, "views");
  const vBase = base.filter(p => passes(p, "views"));
  if (presetName) views.append(optionRow({ checked: state.preset, label: presetName,
    count: vBase.filter(p => presetIds.has(p.id)).length, onChange: () => { state.preset = !state.preset; render(); } }));
  views.append(optionRow({ checked: state.hasClasses, label: "Has classes listed",
    count: vBase.filter(p => p.classes.length).length, onChange: () => { state.hasClasses = !state.hasClasses; render(); } }));
  el.append(views);

  // Facets: counts show what you'd get if you added that option
  for (const f of FACETS) {
    const sec = section(f.title, f.key !== "funding", f.key);
    const fBase = base.filter(p => passes(p, f.key));
    const all = new Map();
    people.forEach(p => f.values(p).forEach(v => all.set(v, 0)));
    fBase.forEach(p => f.values(p).forEach(v => all.set(v, all.get(v) + 1)));
    const order = Object.keys(groups[`by_${f.key}`] || {});
    [...all.keys()].filter(v => !v.startsWith("("))
      .sort((a, b) => (order.indexOf(a) - order.indexOf(b)) || a.localeCompare(b))
      .forEach(v => sec.append(optionRow({ checked: state.sel[f.key].has(v), label: f.label(v), count: all.get(v),
        dot: f.dot ? themeColor(v) : null,
        onChange: () => { const s = state.sel[f.key]; s.has(v) ? s.delete(v) : s.add(v); render(); } })));
    el.append(sec);
  }

  // College / department tree (single-select)
  const org = section("College & department", false, "org");
  const tree = document.createElement("div"); tree.className = "tree";
  const pick = (path, label, ids) => () => {
    state.group = state.group?.path === path ? null : { path, label, ids: new Set(ids) }; render();
  };
  const node = (label, n, path, cls = "") => {
    const b = document.createElement("button");
    b.className = "opt " + cls; b.setAttribute("aria-pressed", state.group?.path === path);
    b.innerHTML = `<span class="lbl">${esc(label)}</span><span class="n">${n.count}</span>`;
    b.onclick = e => { e.preventDefault(); pick(path, label, n.ids)(); };
    return b;
  };
  for (const [uni, u] of Object.entries(groups.by_university)) {
    const d1 = document.createElement("details");
    d1.open = !!state.group?.path.includes(`${uni}/`) || sectionOpen[`u:${uni}`];
    d1.ontoggle = () => { sectionOpen[`u:${uni}`] = d1.open; };
    const s1 = document.createElement("summary"); s1.append(node(uni, u, `u:${uni}/`)); d1.append(s1);
    for (const [col, c] of Object.entries(u.colleges).sort((a, b) => b[1].count - a[1].count)) {
      const deps = Object.entries(c.departments).sort((a, b) => b[1].count - a[1].count);
      const path = `c:${uni}/${col}`;
      if (deps.length <= 1) { d1.append(node(col, c, path, "leaf")); continue; }
      const d2 = document.createElement("details");
      d2.open = !!state.group?.path.startsWith(`d:${uni}/${col}/`) || sectionOpen[path];
      d2.ontoggle = () => { sectionOpen[path] = d2.open; };
      const s2 = document.createElement("summary"); s2.append(node(col, c, path)); d2.append(s2);
      deps.forEach(([dep, d]) => d2.append(node(dep, d, `d:${uni}/${col}/${dep}`, "leaf")));
      d1.append(d2);
    }
    tree.append(d1);
  }
  org.append(tree); el.append(org);

  // Data quality (for maintainers)
  const dq = section("Profile data status", false, "status");
  for (const [name, n] of Object.entries(groups.by_scrape_status || {}))
    dq.append(node(STATUS_LABEL[name] || name, n, `s:${name}`));
  el.append(dq);

  el.scrollTop = scroll;
}

/* ---------- cards ---------- */
function orgLine(p) {
  const parts = [p.department, p.college].filter(Boolean);
  // Avoid "Physics · Physics" style repeats
  const uniq = parts.filter((x, i) => parts.indexOf(x) === i);
  return uniq.join(" · ");
}
function whyLine(w) {
  if (!w) return "";
  const bits = [...w.tags, ...w.classes.map(c => c.title), ...w.words].slice(0, 3);
  return bits.length ? `<div class="why"><span>Matched:</span> ${bits.map(esc).join(" · ")}</div>` : "";
}
function starBtn(p) {
  const on = Shortlist.has(p.id);
  return `<button class="star${on ? " on" : ""}" data-star="${esc(p.id)}" aria-pressed="${on}"
    title="${on ? "Remove from" : "Add to"} shortlist" aria-label="${on ? "Remove" : "Add"} ${esc(p.name)} ${on ? "from" : "to"} shortlist">${on ? "★" : "☆"}</button>`;
}
function card(p, { why } = {}) {
  const tags = p.research_tags;
  const shown = tags.slice(0, 3);
  return `<div class="card" data-id="${esc(p.id)}" style="--tc:${themeColor(p.theme)}">
    <button class="card-open" data-open="${esc(p.id)}" aria-haspopup="dialog" aria-label="Open profile: ${esc(p.name)}"></button>
    ${starBtn(p)}
    <div class="top">
      ${avatar(p)}
      <div>
        <div class="name">${esc(p.name)}${p.credentials ? ` <span class="cred">${esc(p.credentials)}</span>` : ""}</div>
        <div class="role">${esc(p.title || "Title not listed")}</div>
      </div>
    </div>
    <div class="org">${uniBadge(p.university)}${esc(orgLine(p) || "Department not listed")}</div>
    <div class="theme" style="color:${themeColor(p.theme)}"><span class="dot"></span>${esc(p.theme)}</div>
    <div class="tags">${shown.map(t => `<span class="tag" title="${esc(t)}">${esc(t)}</span>`).join("")}${
      tags.length > 3 ? `<span class="tag more">+${tags.length - 3} more</span>` : ""}</div>
    ${whyLine(why)}
  </div>`;
}

function sorted(list) {
  const by = {
    last: (a, b) => lastName(a).localeCompare(lastName(b)),
    theme: (a, b) => a.theme.localeCompare(b.theme) || lastName(a).localeCompare(lastName(b)),
    dept: (a, b) => (a.department || "~").localeCompare(b.department || "~") || lastName(a).localeCompare(lastName(b)),
  }[state.sort];
  // Keep relevance order while searching unless the user picked a sort
  return state.q.trim().length >= 2 && state.sort === "last" ? list : [...list].sort(by);
}

function isActive() {
  return state.showAll || state.q.trim().length >= 2 || state.preset || state.hasClasses || !!state.group
    || Object.values(state.sel).some(s => s.size);
}
function placeSearch(home) {
  const box = document.getElementById("searchBox"), input = document.getElementById("q");
  const slot = document.getElementById(home ? "heroSlot" : "searchSlot");
  if (box.parentElement === slot) return;
  const focused = document.activeElement === input, pos = input.selectionStart;
  slot.append(box);
  if (focused) { input.focus(); input.setSelectionRange(pos, pos); }
}
function buildHome() {
  const go = fn => () => { fn(); render(); window.scrollTo(0, 0); };
  const unisEl = document.getElementById("uniCards"); unisEl.innerHTML = "";
  Object.entries(groups.by_university).forEach(([u, n]) => {
    const b = document.createElement("button"); b.className = "uni-card";
    b.setAttribute("aria-label", `Show ${n.count} faculty at ${u}`);
    b.innerHTML = (UNI_LOGO[u] ? `<img src="${UNI_LOGO[u]}" alt="${esc(u)}">` : `<strong>${esc(u)}</strong>`)
      + `<span class="n"><strong>${n.count}</strong> affiliated faculty</span>`;
    b.onclick = go(() => state.sel.university.add(u));
    unisEl.append(b);
  });
  const tiles = document.getElementById("themeChips"); tiles.innerHTML = "";
  const counts = {}; people.forEach(p => counts[p.theme] = (counts[p.theme] || 0) + 1);
  Object.keys(groups.by_theme).forEach(t => {
    const b = document.createElement("button"); b.className = "tile"; b.style.setProperty("--tc", themeColor(t));
    b.innerHTML = `<span class="t">${esc(t)}</span><span class="n">${counts[t] || 0} faculty</span>`;
    b.onclick = go(() => state.sel.theme.add(t));
    tiles.append(b);
  });
  const views = document.getElementById("viewChips"); views.innerHTML = "";
  const add = (label, n, fn, cls = "") => {
    const b = document.createElement("button"); b.className = "chip " + cls;
    b.innerHTML = `${esc(label)}${n != null ? ` <span class="n">${n}</span>` : ""}`; b.onclick = go(fn);
    views.append(b);
  };
  if (presetName) add(`★ ${presetName}`, presetIds.size, () => { state.preset = true; });
  add("Has classes listed", people.filter(p => p.classes.length).length, () => { state.hasClasses = true; });
  add("See all faculty →", people.length, () => { state.showAll = true; }, "primary");
}

function render() {
  if (state.tab !== "search") return;
  const home = !isActive();
  document.body.classList.toggle("home", home);
  placeSearch(home);
  if (home) { buildHome(); return; }
  const base = searchBase();
  const list = sorted(base.filter(p => passes(p)));
  document.getElementById("count").innerHTML = list.length === people.length
    ? `${people.length} <span>faculty</span>` : `${list.length} <span>of ${people.length} faculty</span>`;
  const rel = document.getElementById("related");
  rel.innerHTML = state.q.trim().length >= 2 && (state.related.length || state.exact)
    ? `<label class="exact"><input type="checkbox" id="exactBox" ${state.exact ? "" : "checked"}> Include related terms</label>
       ${state.exact ? "" : `<span class="muted">Also matching: ${state.related.slice(0, 6).map(esc).join(", ")}${state.related.length > 6 ? "…" : ""}</span>`}`
    : "";
  document.getElementById("exactBox")?.addEventListener("change", e => { state.exact = !e.target.checked; render(); });
  document.getElementById("cards").innerHTML = list.length ? list.map(p => card(p, { why: state.why.get(p.id) })).join("")
    : `<div class="empty">No faculty match these filters.<br><button class="pill clear" id="emptyClear">Clear all filters</button></div>`;
  document.getElementById("emptyClear")?.addEventListener("click", clearAll);
  buildSidebar(base);
  buildPills();
}

function buildPills() {
  const el = document.getElementById("pills"); el.innerHTML = "";
  const pill = (label, onClick, cls = "") => {
    const b = document.createElement("button"); b.className = "pill " + cls;
    b.innerHTML = cls ? esc(label) : `${esc(label)} <span aria-hidden="true">×</span>`;
    b.setAttribute("aria-label", cls ? label : `Remove filter ${label}`); b.onclick = onClick; el.append(b);
  };
  let any = false;
  if (state.q.trim()) { any = true; pill(`“${state.q.trim()}”`, () => { state.q = ""; document.getElementById("q").value = ""; render(); }); }
  if (state.preset) { any = true; pill(presetName, () => { state.preset = false; render(); }); }
  if (state.hasClasses) { any = true; pill("Has classes", () => { state.hasClasses = false; render(); }); }
  for (const f of FACETS) for (const v of state.sel[f.key]) { any = true; pill(f.label(v), () => { state.sel[f.key].delete(v); render(); }); }
  if (state.group) { any = true; pill(state.group.label, () => { state.group = null; render(); }); }
  if (any) pill("Clear all", clearAll, "clear");
}
function clearAll() {
  state.q = ""; document.getElementById("q").value = "";
  state.preset = state.hasClasses = state.showAll = false; state.group = null;
  Object.values(state.sel).forEach(s => s.clear()); render();
}

/* ---------- detail drawer ---------- */
const sourceNote = src => src === "profile" ? "" : src === "directory" ? " (from NMDSI directory)" : " (auto-generated)";
function openDrawer(id) {
  const p = byId[id]; if (!p) return;
  state.openId = id;
  history.replaceState(null, "", "#" + encodeURIComponent(id));
  const url = safeUrl(p.profile_url);
  const summary = p.research_summary || "";
  const long = summary.length > 700;
  const classes = p.classes.length
    ? `<ul>${p.classes.map(c => `<li>${c.code ? `<span class="code">${esc(c.code)}</span>` : ""}${esc(c.title || "")}</li>`).join("")}</ul>`
    : `<p class="muted">None listed on profile</p>`;
  const funding = p.funding.length
    ? `<ul>${p.funding.map(f => `<li title="${esc(f.evidence)}">${esc(FUNDING_LABEL[f.name] || f.name)}</li>`).join("")}</ul>`
    : `<p class="muted">No sponsor named on profile</p>`;
  const industries = p.industries.length
    ? `<div class="tags">${p.industries.map(i => `<span class="tag" title="Matched: ${esc(i.evidence.join(", "))}">${esc(i.name)}</span>`).join("")}</div>`
    : `<p class="muted">None matched</p>`;
  const showDirectory = p.directory_research && p.research_summary !== p.directory_research;

  const d = document.getElementById("drawer");
  d.innerHTML = `
    <div class="d-head" style="--tc:${themeColor(p.theme)}">
      ${avatar(p)}
      <div class="who">
        <h2 id="d-name">${esc(p.name)}${p.credentials ? ` <span class="cred">${esc(p.credentials)}</span>` : ""}</h2>
        <div class="role">${esc(p.title || "Title not listed")}</div>
        <div class="org">${esc(orgLine(p))}</div>
        <div class="theme"><span class="dot" style="color:${themeColor(p.theme)}"></span>${esc(p.theme)}</div>
      </div>
      <button class="x" id="closeDrawer" aria-label="Close">×</button>
    </div>
    <div class="d-logo">
      ${UNI_LOGO[p.university] ? `<img src="${UNI_LOGO[p.university]}" alt="${esc(p.university)}">` : `<strong>${esc(p.university)}</strong>`}
      <div class="d-actions">
        <button class="short-btn${Shortlist.has(p.id) ? " on" : ""}" data-star="${esc(p.id)}">${Shortlist.has(p.id) ? "★ On shortlist" : "☆ Add to shortlist"}</button>
        ${url ? `<a class="profile-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer">View university profile ↗</a>` : ""}
      </div>
    </div>
    <div class="d-body">
      <section class="d-sec"><h3>Research${esc(sourceNote(p.research_summary_source))}</h3>
        <p id="summary">${esc(long ? summary.slice(0, 700).replace(/\s+\S*$/, "") + "…" : summary || "—")}</p>
        ${long ? `<button class="readmore" id="readmore">Read more</button>` : ""}</section>
      <section class="d-sec"><h3>Research tags${esc(sourceNote(p.research_tags_source))}</h3>
        <div class="tags">${p.research_tags.map(t => `<span class="tag">${esc(t)}</span>`).join("") || `<span class="muted">—</span>`}</div></section>
      ${showDirectory ? `<section class="d-sec"><h3>NMDSI directory blurb</h3><p>${esc(p.directory_research)}</p></section>` : ""}
      <section class="d-sec"><h3>Classes</h3>${classes}</section>
      <section class="d-sec two">
        <div><h3>Industries (auto-generated)</h3>${industries}</div>
        <div><h3>Funding</h3>${funding}</div>
      </section>
      ${p.bio ? `<section class="d-sec"><h3>Bio</h3><p>${esc(p.bio)}</p></section>` : ""}
      <section class="d-sec small muted">
        ${esc(STATUS_LABEL[p.scrape_status] || p.scrape_status)}${p.last_scraped ? ` on ${esc(p.last_scraped.slice(0, 10))}` : ""}.
        ${p.theme_evidence?.length ? `Theme based on: ${esc(p.theme_evidence.join(", "))}.` : ""}
        ${!url ? "No profile link in the NMDSI directory." : ""}
      </section>
    </div>`;
  document.getElementById("readmore")?.addEventListener("click", e => {
    document.getElementById("summary").textContent = summary; e.target.remove();
  });
  document.getElementById("closeDrawer").onclick = closeDrawer;
  d.classList.add("show"); d.setAttribute("aria-hidden", "false");
  document.getElementById("scrim").classList.add("show");
  document.body.style.overflow = "hidden";
  document.getElementById("closeDrawer").focus();
}
function closeDrawer() {
  const d = document.getElementById("drawer");
  if (!d.classList.contains("show")) return;
  d.classList.remove("show"); d.setAttribute("aria-hidden", "true");
  document.getElementById("scrim").classList.remove("show");
  document.body.style.overflow = "";
  document.querySelector(`[data-open="${CSS.escape(state.openId || "")}"]`)?.focus();
  state.openId = null;
  history.replaceState(null, "", location.pathname + location.search);
}

/* ---------- events ---------- */
document.addEventListener("click", e => {
  const star = e.target.closest("[data-star]");
  if (star) { e.preventDefault(); Shortlist.toggle(star.dataset.star); return; }
  const open = e.target.closest("[data-open]");
  if (open) { e.preventDefault(); openDrawer(open.dataset.open); }
});
document.getElementById("scrim").onclick = closeDrawer;
document.addEventListener("keydown", e => {
  if (e.key === "Escape") closeDrawer();
  if (e.key === "/" && !/INPUT|TEXTAREA/.test(document.activeElement.tagName) && state.tab === "search") { e.preventDefault(); document.getElementById("q").focus(); }
});
let timer;
document.getElementById("q").addEventListener("input", e => {
  clearTimeout(timer); timer = setTimeout(() => { state.q = e.target.value; render(); }, 120);
});
document.getElementById("brand").onclick = () => { setTab("search"); clearAll(); document.getElementById("q").focus(); };
document.querySelectorAll("button[data-tab]").forEach(b => b.onclick = () => setTab(b.dataset.tab));

/* ---------- tabs ---------- */
function setTab(tab, { push = true } = {}) {
  state.tab = tab;
  document.body.dataset.tab = tab;
  document.querySelectorAll("button[data-tab]").forEach(b => b.setAttribute("aria-selected", b.dataset.tab === tab));
  if (tab !== "search") document.body.classList.remove("home");
  const params = new URLSearchParams(location.search);
  if (tab === "search") params.delete("tab"); else params.set("tab", tab);
  if (tab !== "shortlist") params.delete("ids");
  if (push) history.replaceState(null, "", location.pathname + (params.toString() ? "?" + params : "") + location.hash);
  if (tab === "search") render();
  if (tab === "network") Network.show();
  if (tab === "shortlist") Shortlist.render();
  if (tab === "match") Match.focus();
  window.scrollTo(0, 0);
}
// Re-render whatever is visible after the shortlist changes.
function refreshStars() {
  document.querySelectorAll("[data-star]").forEach(b => {
    const on = Shortlist.has(b.dataset.star);
    b.classList.toggle("on", on); b.setAttribute("aria-pressed", on);
    if (b.classList.contains("star")) b.textContent = on ? "★" : "☆";
    else b.textContent = on ? "★ On shortlist" : "☆ Add to shortlist";
  });
}
document.querySelectorAll("[data-try]").forEach(b => b.onclick = () => {
  const q = document.getElementById("q"); q.value = state.q = b.dataset.try; render(); q.focus();
});
document.getElementById("sort").onchange = e => { state.sort = e.target.value; render(); };
document.getElementById("filtersBtn").onclick = e => {
  const s = document.getElementById("sidebar"); s.classList.toggle("show");
  e.target.setAttribute("aria-expanded", s.classList.contains("show"));
};

const modes = ["auto", "light", "dark"];
function applyTheme(mode) {
  if (mode === "auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.dataset.theme = mode;
  document.getElementById("themeBtn").textContent = `Theme: ${mode}`;
}
let mode = "auto";
try { mode = localStorage.getItem("nmdsi-theme") || "auto"; } catch {}
applyTheme(mode);
document.getElementById("themeBtn").onclick = () => {
  mode = modes[(modes.indexOf(mode) + 1) % 3]; applyTheme(mode);
  try { localStorage.setItem("nmdsi-theme", mode); } catch {}
};
window.addEventListener("DOMContentLoaded", load);
