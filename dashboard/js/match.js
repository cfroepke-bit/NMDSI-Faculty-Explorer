// "Find an Expert": describe a project in plain language, get ranked faculty with reasons,
// plus a suggested team that together covers the most of the request.
const Match = (() => {
  const EXAMPLES = [
    "Detect fraud in insurance claims using machine learning",
    "Forecast product demand across our supply chain",
    "Use natural language processing on clinical notes to improve patient care",
    "Measure climate and environmental risk in investment portfolios",
    "Protect customer data and improve cybersecurity for connected devices",
    "Understand public opinion and misinformation on social media",
  ];
  let last = null;

  function init() {
    const ex = document.getElementById("matchExamples");
    ex.innerHTML = EXAMPLES.map(e => `<button class="ex">${esc(e)}</button>`).join("");
    ex.querySelectorAll(".ex").forEach(b => b.onclick = () => { input().value = b.textContent; run(); });
    document.getElementById("matchForm").onsubmit = e => { e.preventDefault(); run(); };
    input().addEventListener("keydown", e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) run(); });
    document.getElementById("matchUni").onchange = () => last && run();
    const mq = new URLSearchParams(location.search).get("mq");
    if (mq) { input().value = mq; run(); }
  }
  const input = () => document.getElementById("matchText");
  function focus() { if (!last) setTimeout(() => input().focus(), 50); }

  function run() {
    const text = input().value.trim();
    const out = document.getElementById("matchResults");
    if (text.length < 3) { out.innerHTML = `<p class="muted">Describe what you're working on in a sentence or two.</p>`; return; }
    const uni = document.getElementById("matchUni").value;
    const { results, added, concepts, conceptWeight } = ix.search(text);
    const pool = results.filter(r => !uni || r.p.university === uni);
    last = text;
    if (!pool.length) {
      out.innerHTML = `<div class="empty-state"><p>No faculty matched those words. Try naming a method or topic, like
        “machine learning”, “forecasting”, or “public health”.</p></div>`;
      return;
    }
    const top = pool[0].score;
    const list = pool.slice(0, 10);
    const team = suggestTeam(pool.slice(0, 15), concepts, conceptWeight);
    const conceptLabel = c => ix.display(c);

    out.innerHTML = `
      <div class="m-understood">
        <span class="muted">Looking for</span>
        ${lookingFor(text, concepts).map(c => `<span class="cpt">${esc(c)}</span>`).join("")}
        ${added.length ? `<span class="muted">plus related:</span> ${added.slice(0, 6).map(a => `<span class="cpt rel">${esc(a)}</span>`).join("")}` : ""}
      </div>
      ${team.length > 1 ? `<section class="team">
        <div class="team-head">
          <div><h3>Suggested team</h3><p class="muted small">Together they cover ${esc(team.coveredLabel)}${team.crossCampus ? " · spans both universities" : ""}.</p></div>
          <button class="chip primary" id="teamAdd">☆ Add team to shortlist</button>
        </div>
        <div class="team-row">${team.map(r => `
          <button class="team-card" data-open="${esc(r.p.id)}" style="--tc:${themeColor(r.p.theme)}">
            <span class="avatar" aria-hidden="true">${esc(initials(r.p))}</span>
            <span class="tc-body"><strong>${esc(r.p.name)}</strong>
              <span class="small muted">${uniBadge(r.p.university)}${esc(r.p.department || r.p.college || "")}</span>
              <span class="small">Brings: ${esc(lookingFor(text, r.brings).join(", ") || "related expertise")}</span></span>
          </button>`).join("")}</div>
      </section>` : ""}
      <h3 class="m-list-title">Top matches</h3>
      <ol class="m-list">${list.map((r, i) => matchRow(r, i, top)).join("")}</ol>`;
    document.getElementById("teamAdd")?.addEventListener("click", () => Shortlist.addMany(team.map(r => r.p.id)));
  }

  // Show known phrases ("machine learning") instead of their separate words.
  function lookingFor(text, concepts) {
    const keys = textTerms(text), out = [], used = new Set();
    let lastWord = null;
    for (const k of keys) {
      if (!k.includes(" ")) continue;
      const [w1, w2] = k.split(" ");
      if (!(ix.df.get(k) >= 2) || !concepts.includes(w1) || !concepts.includes(w2)) { lastWord = null; continue; }
      // "natural language" + "language processing" -> "natural language processing"
      if (lastWord === w1 && out.length) out[out.length - 1] += " " + ix.display(w2);
      else out.push(ix.display(w1) + " " + ix.display(w2));
      used.add(w1); used.add(w2); lastWord = w2;
    }
    for (const c of concepts) if (!used.has(c)) out.push(ix.display(c));
    return [...new Set(out)];
  }
  function strength(rel) {
    return rel >= 0.75 ? ["Strong match", "strong"] : rel >= 0.45 ? ["Good match", "good"] : ["Possible match", "possible"];
  }
  function matchRow(r, i, top) {
    const p = r.p, rel = r.score / top, [label, cls] = strength(rel);
    const w = ix.explain(p, r.hits);
    const reasons = [
      ...w.tags.map(t => `<span class="reason tag-r">${esc(t)}</span>`),
      ...w.classes.map(c => `<span class="reason class-r">Teaches ${esc(c.code ? c.code + " " : "")}${esc(c.title)}</span>`),
      ...w.words.map(x => `<span class="reason word-r">mentions “${esc(x)}”</span>`),
    ];
    return `<li class="m-row" style="--tc:${themeColor(p.theme)}">
      <div class="rank">${i + 1}</div>
      <div class="avatar" aria-hidden="true">${esc(initials(p))}</div>
      <div class="m-main">
        <div class="s-head"><button class="linkish" data-open="${esc(p.id)}"><strong>${esc(p.name)}</strong></button>
          ${p.credentials ? `<span class="cred">${esc(p.credentials)}</span>` : ""}${uniBadge(p.university)}</div>
        <div class="muted small">${esc(p.title || "")}${p.title ? " · " : ""}${esc(orgLine(p))}</div>
        <div class="reasons"><span class="why-label">Why:</span>${reasons.join("") || `<span class="muted small">Related research text</span>`}</div>
      </div>
      <div class="m-side">
        <div class="meter ${cls}" title="${Math.round(rel * 100)}% of the top score"><span style="width:${Math.max(8, Math.round(rel * 100))}%"></span></div>
        <div class="m-label ${cls}">${label}</div>
        ${starBtn(p)}
      </div>
    </li>`;
  }

  // Greedy pick of up to 3 people that cover the most (rarity-weighted) request concepts,
  // with a small bonus for adding the other university.
  function suggestTeam(cands, concepts, cWeight) {
    if (concepts.length < 2 || cands.length < 2) return [];
    const top = cands[0].score, chosen = [], covered = new Set(), unis = new Set();
    for (let k = 0; k < 3; k++) {
      let best = null, bestVal = 0;
      for (const r of cands) {
        if (chosen.includes(r) || r.score < top * 0.4) continue;   // team members must be solid matches themselves
        const gain = r.covered.filter(c => !covered.has(c)).reduce((a, c) => a + (cWeight.get(c) || 0), 0);
        const val = gain + 0.35 * (r.score / top) + (unis.size && !unis.has(r.p.university) ? 0.4 : 0);
        if (gain > 0 || k === 0) if (val > bestVal) { best = r; bestVal = val; }
      }
      if (!best) break;
      best.brings = best.covered.filter(c => !covered.has(c) && concepts.includes(c));
      if (!best.brings.length && k > 0) break;
      chosen.push(best); best.covered.forEach(c => covered.add(c)); unis.add(best.p.university);
    }
    const got = concepts.filter(c => covered.has(c));
    chosen.coveredLabel = got.length === concepts.length ? "every part of the request"
      : lookingFor(last, got).join(", ");
    chosen.crossCampus = unis.size > 1;
    return chosen;
  }

  return { init, focus, run };
})();
