// "Fund it": federal opportunities (Grants.gov) that fit a team's request, and a timeline that works backward
// from the chosen deadline, with NMDSI's Paving ROADS seed fund as a pilot step when there is time for one.
const Plan = (() => {
  const ROADS = {
    name: "Paving ROADS Seed Fund",
    url: "https://www.nmdsi.org/center-of-excellence/paving-roads-seed-fund",
    // 2027 round: proposals due Sunday, October 18, 2026; awards by early December; projects up to 18 months.
    // Later rounds are assumed to follow the same pattern (third Sunday of October). Check the page each year.
    months: 18,
    amount: "up to $50,000 per project (joint Marquette–UWM proposals up to $100,000)",
  };
  const DAY = 864e5;
  let opps = [], oix = null, meta = null, loaded = null, current = null;

  function load() {
    loaded ??= fetch("../data/opportunities.json").then(r => r.ok ? r.json() : null).then(d => {
      if (!d) return;
      meta = d.meta; opps = d.opportunities;
      // Title and description only: the search keywords each opportunity was found with would give every one
      // a free match on words like "machine learning".
      oix = new TextIndex(opps, [[o => o.title, 3], [o => o.description, 1]]);
    }).catch(() => {});
    return loaded;
  }

  const today = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };
  const parse = s => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
  const addDays = (d, n) => new Date(d.getTime() + n * DAY);
  const addMonths = (d, n) => { const x = new Date(d); x.setMonth(x.getMonth() + n); return x; };
  const fmt = d => d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  const fmtMonth = d => d.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  const daysUntil = d => Math.round((d - today()) / DAY);

  function thirdSundayOfOctober(year) {
    const d = new Date(year, 9, 1);
    d.setDate(1 + (7 - d.getDay()) % 7 + 14);
    return d;
  }
  // Next ROADS deadline with at least 6 weeks left to write the proposal.
  function nextRoads(from = today()) {
    let d = thirdSundayOfOctober(from.getFullYear());
    if ((d - from) / DAY < 42) d = thirdSundayOfOctober(from.getFullYear() + 1);
    return d;
  }

  const deadlineOf = o => o.close_date ? { date: parse(o.close_date), kind: "due" }
    : o.estimated_close_date ? { date: parse(o.estimated_close_date), kind: "estimated" } : null;

  // Opportunities that fit the request: they must cover at least half of its ideas (rare ideas count more),
  // best text match first, dropping ones closing within 3 weeks. Better none than a list of near-misses.
  const MIN_COVERAGE = 0.5;
  function fit(text, n = 5) {
    if (!oix) return [];
    const { results } = oix.search(text);
    const good = results.filter(r => r.coverage >= MIN_COVERAGE);
    const top = good[0]?.score || 1;
    return good.filter(r => r.score >= top * 0.25)
      .filter(r => { const d = deadlineOf(r.p); return !d || daysUntil(d.date) >= 21; })
      .slice(0, n).map(r => ({ o: r.p, rel: r.score / top, why: oix.explain({ research_tags: [], classes: [] }, r.hits).words }));
  }

  // The next ROADS cycle: proposal, award, an 18-month pilot with a midpoint report.
  function seedCycle(t = today()) {
    const R = nextRoads(t), award = new Date(R.getFullYear(), 11, 5), start = new Date(R.getFullYear() + 1, 0, 1);
    const midpoint = addMonths(start, 9), end = addMonths(start, ROADS.months);
    const steps = [
      { date: t, label: "Form the team", detail: "Agree on the pilot question and who leads at each institution.", kind: "now" },
      { date: addDays(R, -42), label: "Start the Paving ROADS proposal", detail: `${ROADS.name}: ${ROADS.amount}.`, kind: "seed" },
      { date: R, label: "Submit the Paving ROADS proposal", detail: "Expected mid-October (the 2027 round closed Oct 18, 2026). Late or incomplete applications are not accepted.", kind: "seed" },
      { date: award, label: "ROADS award notice", detail: "Expected by early December.", kind: "seed" },
      { date: start, label: "Pilot project starts", detail: `Up to ${ROADS.months} months of seed-funded work.`, kind: "seed" },
      { date: midpoint, label: "Pilot midpoint report", detail: "Preliminary results become the evidence for a federal proposal.", kind: "seed" },
    ];
    return { R, start, midpoint, end, steps };
  }

  function eligibilityNotes(team) {
    const unis = new Set(team.map(m => m.p.university)), notes = [];
    if (unis.has("Marquette University") && unis.has("UW-Milwaukee")) notes.push("This team includes Marquette and UWM faculty, so it fits the joint ROADS track (up to $100,000).");
    else if (!unis.has("Marquette University") && !unis.has("UW-Milwaukee")) notes.push("The ROADS page describes awards at Marquette and UWM. Add a Marquette or UWM lead, or check with NMDSI about eligibility.");
    if ([...unis].some(u => !["Marquette University", "UW-Milwaukee"].includes(u))) notes.push("Ask NMDSI how MCW, MSOE or WCTC members can take part in a ROADS project.");
    return notes;
  }

  // No federal opportunity fits: the ROADS pilot on its own, ending with a pointer to the federal step.
  function seedOnly(team) {
    const c = seedCycle();
    const steps = [...c.steps,
      { date: addMonths(c.midpoint, 1), label: "Pick the federal program", detail: "Search Grants.gov again with the pilot's results; NSF and NIH post most data-science calls.", kind: "fed" },
      { date: c.end, label: "Pilot ends; final ROADS report", detail: "", kind: "seed" }];
    return { steps, notes: eligibilityNotes(team), seed: true };
  }

  // Backward plan. Returns {steps:[{date, label, detail, kind}], notes:[...], seed: bool, target}.
  function build(o, team) {
    const t = today(), d = deadlineOf(o), notes = [];
    const { R, midpoint, end, steps: seedSteps } = seedCycle(t);
    let target = d?.date, guessed = false;
    if (!target) { target = addMonths(midpoint, 4); guessed = true; }
    const agency = o.agency || "the agency";
    const fed = [
      { date: addDays(target, -120), label: `Contact the ${agency} program officer`, detail: "Send a one-page summary to confirm fit, then start writing.", kind: "fed" },
      { date: addDays(target, -42), label: "Full draft for team review", detail: "Request budgets and letters of support from each institution.", kind: "fed" },
      { date: addDays(target, -7), label: "Final package to your research office", detail: "Most sponsored-programs offices ask for about 5 business days to route a proposal.", kind: "fed" },
      { date: target, label: guessed ? `Suggested target: submit to ${agency}` : `${d.kind === "estimated" ? "Expected deadline" : "Deadline"}: submit to ${agency}`,
        detail: o.title, kind: "deadline" },
    ];
    const seed = target >= addDays(midpoint, 60);
    let steps;
    if (seed) {
      steps = [...seedSteps, ...fed];
      if (end > target) steps.push({ date: end, label: "Pilot ends; final ROADS report", detail: "", kind: "seed" });
    } else {
      steps = [{ date: t, label: "Form the team", detail: "Agree on the aims and who leads at each institution.", kind: "now" }, ...fed];
      if (daysUntil(target) < 120) notes.push(`Only ${daysUntil(target)} days until this deadline: the steps above are compressed. Start now, or plan for the next cycle.`);
      notes.push(`Not enough time for a seed pilot before this deadline (pilot results would arrive around ${fmtMonth(midpoint)}). `
        + `Apply directly, or use the ${R.getFullYear()} ROADS round (due mid-October) to build pilot data for the next cycle.`);
    }
    steps = steps.filter(s => s.kind === "now" || s.date >= t).sort((a, b) => a.date - b.date);
    if (guessed) notes.unshift("No fixed deadline is listed (rolling or not yet posted), so the target date is a suggestion that leaves time for pilot results.");
    if (seed) notes.push(...eligibilityNotes(team));
    return { steps, notes, seed, target, guessed };
  }

  function oppCard(f, i) {
    const o = f.o, d = deadlineOf(o);
    const when = d ? `${d.kind === "estimated" ? "Expected " : "Due "}${fmt(d.date)} · ${daysUntil(d.date)} days` : "No fixed deadline listed";
    return `<label class="opp${i === 0 ? " on" : ""}">
      <input type="radio" name="opp" value="${esc(o.id)}" ${i === 0 ? "checked" : ""}>
      <span class="opp-main">
        <span class="opp-title">${esc(o.title)}</span>
        <span class="small muted">${esc(o.agency || "")} ${o.number ? "· " + esc(o.number) : ""} · ${o.status === "forecasted" ? "Forecast" : "Open"}
          ${o.award_ceiling ? ` · up to ${money(o.award_ceiling)}` : ""}</span>
        ${f.why.length ? `<span class="small">Fits: ${f.why.slice(0, 4).map(esc).join(", ")}</span>` : ""}
      </span>
      <span class="opp-when ${d && daysUntil(d.date) < 120 ? "soon" : ""}">${esc(when)}</span>
    </label>`;
  }

  function timeline(plan, o) {
    return `<ol class="tl">${plan.steps.map(s => `<li class="tl-step ${s.kind}">
        <span class="tl-date">${s.kind === "now" ? "Now" : esc(fmt(s.date))}</span>
        <span class="tl-body"><strong>${esc(s.label)}</strong>${s.detail ? `<span class="small muted">${esc(s.detail)}</span>` : ""}</span>
      </li>`).join("")}</ol>
      ${plan.notes.map(n => `<p class="tl-note small">${esc(n)}</p>`).join("")}
      <div class="tl-links small">
        ${o ? `<a href="${esc(safeUrl(o.url) || "#")}" target="_blank" rel="noopener noreferrer">Opportunity on Grants.gov ↗</a>` : ""}
        ${plan.seed ? `<a href="${ROADS.url}" target="_blank" rel="noopener noreferrer">Paving ROADS Seed Fund ↗</a>` : ""}
        <button class="linkish" id="planCopy">Copy plan as text</button>
      </div>`;
  }

  function asText(plan, o, team) {
    return [o ? `Funding plan: ${o.title} (${o.agency}${o.number ? " " + o.number : ""})` : `Funding plan: ${ROADS.name} pilot`,
      `Team: ${team.map(m => `${m.p.name} (${UNI_SHORT[m.p.university] || m.p.university})`).join(", ")}`, "",
      ...plan.steps.map(s => `${s.kind === "now" ? "Now" : fmt(s.date)}  ${s.label}${s.detail ? " — " + s.detail : ""}`),
      ...(plan.notes.length ? ["", ...plan.notes] : []), "", o ? o.url : "", plan.seed ? ROADS.url : ""].join("\n").trim();
  }
  function wireCopy(root, plan, o, team) {
    root.querySelector("#planCopy").onclick = async () => {
      const txt = asText(plan, o, team);
      try { await navigator.clipboard.writeText(txt); toast("Plan copied to clipboard"); } catch { window.prompt("Copy this plan:", txt); }
    };
  }

  // Render into el for a request text and a suggested team ([{p, ...}]).
  async function render(el, text, team) {
    await load();
    if (!el) return;
    if (!oix) { el.innerHTML = ""; return; }
    const fits = fit(text);
    current = { fits, team };
    if (!fits.length) {
      // No federal call fits closely: a ROADS pilot is still a concrete first step.
      const plan = seedOnly(team);
      el.innerHTML = `<section class="fund"><h3>Fund it</h3>
        <p class="muted small">No open or forecast federal opportunity on Grants.gov fits this request closely right now
          (checked ${esc(meta?.retrieved || "")}). Start with a pilot, then aim for the next federal call.</p>
        <div class="plan"><h4>Plan with a ROADS pilot</h4>${timeline(plan, null)}</div></section>`;
      wireCopy(el, plan, null, team);
      return;
    }
    el.innerHTML = `<section class="fund">
      <div class="team-head"><div><h3>Fund it</h3>
        <p class="muted small">Open and upcoming federal opportunities that fit this request (from Grants.gov, ${esc(meta?.retrieved || "")}).
          Pick one to see a plan that works backward from its deadline.</p></div></div>
      <div class="fund-grid">
        <div class="opps" role="radiogroup" aria-label="Funding opportunities">${fits.map(oppCard).join("")}</div>
        <div class="plan" id="planBox" aria-live="polite"></div>
      </div>
    </section>`;
    const show = id => {
      const f = fits.find(x => String(x.o.id) === String(id)) || fits[0];
      el.querySelectorAll(".opp").forEach(l => l.classList.toggle("on", l.querySelector("input").value === String(f.o.id)));
      const plan = build(f.o, team);
      const box = el.querySelector("#planBox");
      box.innerHTML = `<h4>${plan.seed ? "Plan with a ROADS pilot" : "Plan"}</h4>${timeline(plan, f.o)}`;
      wireCopy(box, plan, f.o, team);
    };
    el.querySelectorAll('input[name="opp"]').forEach(r => r.onchange = () => show(r.value));
    show(fits[0].o.id);
  }

  return { load, render, build, nextRoads, fit };
})();
