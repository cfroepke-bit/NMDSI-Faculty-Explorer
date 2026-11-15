// "Funded projects like this": live keyword search of NSF and NIH awards from the last five years,
// in Wisconsin or nationwide. Shows that an idea is fundable, which programs fund it, and who else holds
// those grants (NMDSI faculty are linked to their profiles).
// NSF is queried from the browser; NIH goes through /api/nih-search (RePORTER refuses browser requests).
const GrantSearch = (() => {
  const NSF = "https://api.nsf.gov/services/v1/awards.json";
  const NSF_FIELDS = "id,title,piFirstName,piLastName,awardeeName,awardeeCity,awardeeStateCode,startDate,expDate,estimatedTotalAmt,fundProgramName";
  let scope = "WI", lastTerms = null, el = null, seq = 0;
  const cache = new Map();

  const fold = s => String(s || "").normalize("NFKD").replace(/[^\p{L}]/gu, "").toLowerCase();
  // NMDSI person with this first + last name (first name may be shortened on the award).
  function person(first, last) {
    const f = fold(String(first).split(/\s+/)[0]), l = fold(last);
    if (!l) return null;
    const hits = people.filter(p => {
      const w = p.name.replace(/\([^)]*\)/g, " ").replace(/[.,]/g, " ").split(/\s+/).filter(x => x.length > 1);
      const pf = fold(w[0]), pl = fold(w.at(-1));
      return pl === l && f && (pf === f || (Math.min(pf.length, f.length) >= 3 && (pf.startsWith(f) || f.startsWith(pf))));
    });
    return hits.length === 1 ? hits[0] : null;
  }

  const quote = t => t.includes(" ") ? `"${t}"` : t;
  function fiveYearsAgo() {
    const d = new Date(); d.setFullYear(d.getFullYear() - 5);
    return `${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")}/${d.getFullYear()}`;
  }

  // All terms with AND, then fewer, until at least 3 awards come back.
  async function nsf(terms) {
    let last = null;
    for (let k = terms.length; k >= 1; k--) {
      const q = terms.slice(0, k).map(quote).join(" AND ");
      const params = new URLSearchParams({ keyword: q, printFields: NSF_FIELDS, rpp: "8", startDateStart: fiveYearsAgo() });
      if (scope === "WI") params.set("awardeeStateCode", "WI");
      const r = await fetch(`${NSF}?${params}`);
      if (!r.ok) throw new Error(`NSF ${r.status}`);
      const d = (await r.json()).response || {};
      last = {
        query: q, total: d.metadata?.totalCount ?? (d.award || []).length,
        items: (d.award || []).map(a => ({
          id: a.id, title: a.title, pi_first: a.piFirstName, pi_last: a.piLastName,
          pi: [a.piFirstName, a.piLastName].filter(Boolean).join(" "),
          org: a.awardeeName, city: a.awardeeCity, state: a.awardeeStateCode,
          years: [a.startDate, a.expDate].map(x => (x || "").slice(-4)).filter(Boolean),
          amount: +a.estimatedTotalAmt || null, program: a.fundProgramName,
          url: `https://www.nsf.gov/awardsearch/showAward?AWD_ID=${a.id}`,
        })),
      };
      if (last.items.length >= 3) break;
    }
    return last;
  }
  async function nih(terms) {
    const r = await fetch(`/api/nih-search?${new URLSearchParams({ terms: JSON.stringify(terms), scope })}`);
    if (!r.ok) throw new Error(r.status === 404 ? "local" : `NIH ${r.status}`);
    return r.json();
  }

  function row(a, agency) {
    const p = person(a.pi_first, a.pi_last);
    const where = [a.org, scope === "US" && a.state ? a.state : null].filter(Boolean).join(", ");
    const years = [...new Set(a.years || [])].join("–");
    return `<li class="award">
      <span class="ag ${agency.toLowerCase()}">${agency}</span>
      <span class="aw-main"><a href="${esc(safeUrl(a.url) || "#")}" target="_blank" rel="noopener noreferrer">${esc(a.title)}</a>
        <span class="small muted">${p ? `<button class="linkish nmdsi-pi" data-open="${esc(p.id)}">${esc(p.name)}</button> ${uniBadge(p.university)}` : esc(a.pi || "")}
          ${where ? ` · ${esc(where)}` : ""}${years ? ` · ${esc(years)}` : ""}${a.amount ? ` · ${esc(money(a.amount))}` : ""}${a.program || a.ic ? ` · ${esc(a.program || a.ic)}` : ""}</span></span>
    </li>`;
  }
  function column(agency, res, err) {
    if (err === "local") return `<div><h4>NIH</h4><p class="small muted">The NIH search runs on the published site (it needs the site's /api function).</p></div>`;
    if (err) return `<div><h4>${agency}</h4><p class="small muted">${agency} search is unavailable right now (${esc(err)}).</p></div>`;
    if (!res.items.length) return `<div><h4>${agency}</h4><p class="small muted">No ${agency} awards in the last five years match ${esc(res.query)}.</p></div>`;
    return `<div><h4>${agency} <span class="muted small">${res.total} match${res.total === 1 ? "" : "es"} · ${esc(res.query)}</span></h4>
      <ul class="awards">${res.items.slice(0, 6).map(a => row(a, agency)).join("")}</ul></div>`;
  }

  async function draw() {
    if (!el || !lastTerms?.length) return;
    const my = ++seq, key = scope + "|" + lastTerms.join("|");
    el.querySelector(".gs-body").innerHTML = `<p class="small muted">Searching NSF and NIH…</p>`;
    if (!cache.has(key)) {
      const settle = p => p.then(v => ({ v }), e => ({ e: e.message || String(e) }));
      cache.set(key, Promise.all([settle(nsf(lastTerms)), settle(nih(lastTerms))]));
    }
    const [n, h] = await cache.get(key);
    if (my !== seq || !el.isConnected) return;   // a newer search replaced this one
    el.querySelector(".gs-body").innerHTML = `<div class="gs-grid">${column("NSF", n.v, n.e)}${column("NIH", h.v, h.e)}</div>`;
  }

  // terms: the request's most distinctive ideas, most distinctive first (at most 3 are used).
  function render(target, terms) {
    el = target; lastTerms = terms.slice(0, 3);
    if (!el) return;
    if (!lastTerms.length) { el.innerHTML = ""; return; }
    el.innerHTML = `<section class="gsearch">
      <div class="team-head"><div><h3>Funded projects like this</h3>
        <p class="muted small">NSF and NIH awards from the last five years that mention ${lastTerms.map(t => `<span class="cpt">${esc(t)}</span>`).join(" ")}.
          A sign the idea is fundable, which programs fund it, and who already holds those grants.</p></div>
        <div class="gs-scope" role="group" aria-label="Where">
          <button class="chip${scope === "WI" ? " primary" : ""}" data-scope="WI">Wisconsin</button>
          <button class="chip${scope === "US" ? " primary" : ""}" data-scope="US">Nationwide</button></div></div>
      <div class="gs-body"></div></section>`;
    el.querySelectorAll("[data-scope]").forEach(b => b.onclick = () => {
      scope = b.dataset.scope;
      el.querySelectorAll("[data-scope]").forEach(x => x.classList.toggle("primary", x.dataset.scope === scope));
      draw();
    });
    draw();
  }

  return { render, person };
})();
