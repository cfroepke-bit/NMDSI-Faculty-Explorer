// Collaboration map: faculty linked by shared research topics (TF-IDF similarity of tags, blurbs, summaries).
// Gold links connect UWM and Marquette faculty: the cross-campus collaborations NMDSI exists to create.
const Network = (() => {
  const K = 3, MIN_SIM = 0.12, STRONG_SIM = 0.3;
  let built = false, nodes = [], links = [], svg, gAll, zoom, selected = null;
  const opts = { color: "theme", crossOnly: false };
  const UNI_STROKE = { "UW-Milwaukee": "#ffbd00", "Marquette University": "#003366" };

  function build() {
    const n = people.length, best = people.map(() => []);
    const pairs = new Map();
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      const s = ix.similarity(i, j);
      if (s.score < MIN_SIM) continue;
      best[i].push([s.score, j, s.shared]); best[j].push([s.score, i, s.shared]);
    }
    for (let i = 0; i < n; i++) {
      best[i].sort((a, b) => b[0] - a[0]);
      best[i].forEach(([s, j, shared], rank) => {
        if (rank >= K && s < STRONG_SIM) return;
        const key = i < j ? `${i}-${j}` : `${j}-${i}`;
        if (!pairs.has(key)) pairs.set(key, { source: Math.min(i, j), target: Math.max(i, j), sim: s, shared });
      });
    }
    links = [...pairs.values()].map(l => ({ ...l, cross: people[l.source].university !== people[l.target].university,
                                             topics: ix.sharedTopics(l.shared, 3) }));
    const deg = new Array(n).fill(0); links.forEach(l => { deg[l.source]++; deg[l.target]++; });
    nodes = people.map((p, i) => ({ i, p, deg: deg[i] })).filter(d => d.deg > 0);
    const keep = new Map(nodes.map((d, k) => [d.i, d]));
    links = links.map(l => ({ ...l, source: keep.get(l.source), target: keep.get(l.target) }));

    built = true;
  }
  const W = 1100, H = 760;
  const radius = d => 4 + Math.sqrt(d.deg) * 1.3;
  const fill = d => opts.color === "theme" ? themeColor(d.p.theme) : (UNI_STROKE[d.p.university] || "#999");

  // Live force layout. Each research theme has a home region on a ring so clusters stay readable;
  // links pull related people toward each other across regions. Nodes can be dragged.
  function startSim() {
    const themes = THEMES.filter(t => nodes.some(d => d.p.theme === t));
    const anchor = Object.fromEntries(themes.map((t, k) => {
      const a = -Math.PI / 2 + 2 * Math.PI * k / themes.length;
      return [t, { x: W / 2 + Math.cos(a) * W * 0.38, y: H / 2 + Math.sin(a) * H * 0.37, a }];
    }));
    // Start everyone near their region so the map "blooms" outward instead of exploding from the center.
    nodes.forEach(d => { if (d.x == null) { const a = anchor[d.p.theme] || { x: W / 2, y: H / 2 };
      d.x = a.x + (Math.random() - 0.5) * 60; d.y = a.y + (Math.random() - 0.5) * 60; } });
    sim = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links).distance(l => 85 - 35 * l.sim).strength(l => 0.02 + l.sim * 0.18))
      .force("charge", d3.forceManyBody().strength(-75).distanceMax(260))
      .force("x", d3.forceX(d => anchor[d.p.theme]?.x ?? W / 2).strength(0.09))
      .force("y", d3.forceY(d => anchor[d.p.theme]?.y ?? H / 2).strength(0.09))
      .force("collide", d3.forceCollide(d => radius(d) + 5).strength(0.9))
      .alphaDecay(0.018).velocityDecay(0.32)
      .on("tick", tick);
    regionAnchor = anchor;
  }
  let sim, regionAnchor = {}, frame = 0;

  function tick() {
    svg.selectAll(".link").attr("x1", l => l.source.x).attr("y1", l => l.source.y)
      .attr("x2", l => l.target.x).attr("y2", l => l.target.y);
    svg.selectAll(".node").attr("transform", d => `translate(${d.x},${d.y})`);
    if (frame++ % 6 === 0) placeRegionLabels();
  }
  // Label each region just outside its cluster, kept inside the frame.
  function placeRegionLabels() {
    svg.selectAll(".region").each(function ([t]) {
      const pts = nodes.filter(d => d.p.theme === t); if (!pts.length) return;
      const cx = d3.mean(pts, d => d.x), cy = d3.mean(pts, d => d.y), a = regionAnchor[t]?.a ?? 0;
      const r = d3.quantile(pts.map(d => Math.hypot(d.x - cx, d.y - cy)).sort(d3.ascending), 0.9) + 26;
      d3.select(this).attr("x", Math.max(95, Math.min(W - 95, cx + Math.cos(a) * r)))
                     .attr("y", Math.max(16, Math.min(H - 8, cy + Math.sin(a) * r + 4)));
    });
  }

  function draw() {
    const wrap = document.getElementById("netCanvas");
    wrap.innerHTML = "";
    svg = d3.select(wrap).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("role", "img")
      .attr("aria-label", "Network of faculty connected by shared research topics");
    gAll = svg.append("g");
    zoom = d3.zoom().scaleExtent([0.5, 6]).on("zoom", e => gAll.attr("transform", e.transform));
    svg.call(zoom).on("dblclick.zoom", null);
    svg.on("click", e => { if (e.target === svg.node()) select(null); });

    const themes = THEMES.filter(t => nodes.some(d => d.p.theme === t));
    gAll.append("g").attr("class", "region-labels").selectAll("text").data(themes.map(t => [t])).join("text")
      .attr("class", "region").text(([t]) => t).style("fill", ([t]) => themeColor(t));
    gAll.append("g").attr("class", "links").selectAll("line").data(links).join("line")
      .attr("class", l => l.cross ? "link cross" : "link").attr("stroke-width", l => 0.6 + l.sim * 1.6);
    const node = gAll.append("g").attr("class", "nodes").selectAll("g").data(nodes).join("g")
      .attr("class", "node").attr("tabindex", 0)
      .attr("role", "button").attr("aria-label", d => `${d.p.name}, ${d.p.university}, ${d.deg} connections`);
    node.append("circle").attr("r", radius).attr("stroke", d => UNI_STROKE[d.p.university] || "#999");
    node.append("text").attr("class", "lbl").attr("dy", d => -radius(d) - 4).text(d => d.p.name.split(" ").at(-1));
    node.on("mouseenter", (e, d) => tip(e, d)).on("mousemove", (e, d) => tip(e, d)).on("mouseleave", () => tip())
        .on("click", (e, d) => { if (e.defaultPrevented) return; e.stopPropagation(); select(d); })
        .on("keydown", (e, d) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(d); } });
    // Drag a person to pull their neighbors along; they drift back when released.
    node.call(d3.drag()
      .on("start", (e, d) => { if (!e.active) sim.alphaTarget(0.25).restart(); d.fx = d.x; d.fy = d.y; tip(); })
      .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on("end", (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = d.fy = null; }));
    startSim();
    restyle();
  }

  function restyle() {
    if (!svg) return;
    const nb = selected ? new Set(links.filter(l => l.source === selected || l.target === selected).flatMap(l => [l.source, l.target])) : null;
    svg.selectAll(".node circle").attr("fill", fill);
    svg.selectAll(".region").style("display", opts.color === "theme" ? null : "none");
    svg.selectAll(".node").classed("dim", d => nb ? !nb.has(d) : false).classed("sel", d => d === selected)
      .classed("show-lbl", d => (nb && nb.has(d)) || (!nb && d.deg >= 7));
    svg.selectAll(".link")
      .classed("hidden", l => opts.crossOnly && !l.cross)
      .classed("dim", l => nb ? !(l.source === selected || l.target === selected) : false)
      .classed("hot", l => nb ? (l.source === selected || l.target === selected) : false);
    legend();
  }

  function tip(e, d) {
    const t = document.getElementById("netTip");
    if (!d) { t.hidden = true; return; }
    const box = document.getElementById("netCanvas").getBoundingClientRect();
    t.hidden = false;
    t.innerHTML = `${d.p.photo_url ? `<img class="tip-photo" src="${esc(d.p.photo_url)}" alt="" referrerpolicy="no-referrer" onerror="this.remove()">` : ""}<strong>${esc(d.p.name)}</strong><br><span>${esc(UNI_SHORT[d.p.university] || d.p.university)} · ${esc(d.p.department || d.p.theme)}</span>
      <br><span class="muted">${d.deg} connection${d.deg === 1 ? "" : "s"} · click for details</span>`;
    t.style.left = Math.min(e.clientX - box.left + 14, box.width - 240) + "px";
    t.style.top = (e.clientY - box.top + 14) + "px";
  }

  function select(d) {
    selected = d; restyle(); side();
  }

  function pairRow(l, focus) {
    const a = focus ? (l.source === focus ? l.target : l.source) : l.source, b = focus ? null : l.target;
    return `<li class="pair${l.cross ? " cross" : ""}">
      <div class="pair-names">
        <button class="linkish" data-net="${a.i}">${esc(a.p.name)}</button> ${uniBadge(a.p.university)}
        ${b ? `<span class="muted">↔</span> <button class="linkish" data-net="${b.i}">${esc(b.p.name)}</button> ${uniBadge(b.p.university)}` : ""}
      </div>
      <div class="small muted">Shared: ${esc(l.topics.join(", ") || "related research")}</div>
    </li>`;
  }

  function side() {
    const el = document.getElementById("netSide");
    if (selected) {
      const mine = links.filter(l => l.source === selected || l.target === selected).sort((a, b) => b.sim - a.sim);
      const cross = mine.filter(l => l.cross).length;
      el.innerHTML = `<div class="ns-person" style="--tc:${themeColor(selected.p.theme)}">
          ${avatar(selected.p)}
          <div><strong>${esc(selected.p.name)}</strong><div class="small muted">${uniBadge(selected.p.university)}${esc(selected.p.department || "")}</div></div>
        </div>
        <div class="ns-actions"><button class="chip" data-open="${esc(selected.p.id)}">View profile</button>${starBtn(selected.p)}
          <button class="chip" id="netBack">← All</button></div>
        <h4>${mine.length} research connection${mine.length === 1 ? "" : "s"}${cross ? ` · <span class="gold-txt">${cross} cross-campus</span>` : ""}</h4>
        <ul class="pairs">${mine.map(l => pairRow(l, selected)).join("")}</ul>`;
      document.getElementById("netBack").onclick = () => select(null);
    } else {
      const cross = links.filter(l => l.cross).sort((a, b) => b.sim - a.sim);
      const bridged = new Set(cross.flatMap(l => [l.source.i, l.target.i]));
      el.innerHTML = `<div class="stats">
          <div><strong>${nodes.length}</strong><span>faculty mapped</span></div>
          <div><strong>${links.length}</strong><span>research links</span></div>
          <div class="gold"><strong>${cross.length}</strong><span>cross-campus links</span></div>
        </div>
        <p class="small muted">${bridged.size} faculty (${Math.round(100 * bridged.size / nodes.length)}%) share research with someone at the other university.
          Click anyone on the map to see their connections.</p>
        <h4>Top cross-campus opportunities</h4>
        <ul class="pairs">${cross.slice(0, 10).map(l => pairRow(l)).join("")}</ul>
        ${people.length - nodes.length ? `<p class="small muted">${people.length - nodes.length} faculty aren't shown because their profiles don't list enough research detail to connect.</p>` : ""}`;
    }
    el.querySelectorAll("[data-net]").forEach(b => b.onclick = () => focusNode(nodes.find(d => d.i === +b.dataset.net)));
  }

  function focusNode(d) {
    if (!d) return;
    select(d);
    const box = svg.node().viewBox.baseVal;
    svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity.translate(box.width / 2, box.height / 2).scale(2).translate(-d.x, -d.y));
  }

  function legend() {
    const el = document.getElementById("netLegend");
    const items = opts.color === "theme"
      ? THEMES.filter(t => nodes.some(d => d.p.theme === t)).map(t => `<span><i style="background:${themeColor(t)}"></i>${esc(t)}</span>`)
      : Object.entries(UNI_STROKE).map(([u, c]) => `<span><i style="background:${c}"></i>${esc(u)}</span>`);
    el.innerHTML = items.join("") + `<span class="sep"></span><span><b class="ln cross"></b>Cross-campus link</span><span><b class="ln"></b>Same-campus link</span>
      <span class="muted">Grouped by research theme · ring = university · size = connections · drag to rearrange</span>`;
  }

  function show() {
    if (typeof d3 === "undefined") {
      document.getElementById("netCanvas").innerHTML = `<div class="empty-state"><p>The map needs an internet connection to load its drawing library.</p></div>`;
      return;
    }
    if (!built) {
      build(); draw(); side();
      document.getElementById("netColor").onchange = e => { opts.color = e.target.value; restyle(); };
      document.getElementById("netCross").onchange = e => { opts.crossOnly = e.target.checked; restyle(); };
      document.getElementById("netReset").onclick = () => { select(null); svg.transition().duration(400).call(zoom.transform, d3.zoomIdentity); sim.alpha(0.6).restart(); };
      const find = document.getElementById("netFind");
      document.getElementById("netNames").innerHTML = nodes.map(d => `<option value="${esc(d.p.name)}">`).join("");
      find.onchange = () => { const d = nodes.find(n => n.p.name.toLowerCase() === find.value.trim().toLowerCase()); if (d) focusNode(d); };
    } else { restyle(); sim.alpha(0.15).restart(); }
  }

  return { show, energy: () => sim ? sim.alpha() : 0 };   // energy: how much the layout is still moving (for tests)
})();
