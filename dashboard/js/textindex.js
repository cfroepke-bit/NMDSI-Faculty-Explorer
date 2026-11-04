// Text engine shared by smart search, "Find an Expert", and the collaboration map.
// - Tokenizes text into stemmed words plus two-word phrases ("supply chain").
// - Ranks faculty for a query with BM25, weighting tags above long prose.
// - Expands queries with related terms from SYNONYM_GROUPS.
// - Builds TF-IDF vectors so faculty can be compared to each other.
(function () {
  const STOP = new Set(`a an and or the of in on for to with by from at as is are was were be been being this that these those
    it its into over under between within across about through via than then also such other their his her they them we our
    i my me he she you your can may might will would should could not no nor but if so do does did has have had having
    which who whom whose what when where how why all any both each few more most some many much very own same just
    including include includes included especially particularly various several new current recent ongoing
    research researcher researchers interest interests area areas focus focuses focused work works working study studies
    studied project projects professor dr phd department college university school faculty member members use using used
    based approach approaches application applications well related role topics topic field fields efforts primarily
    student students course courses teaching taught class classes program programs one two three
    want wants need needs looking look seek seeking find help someone anyone expert experts us like get make team
    improve improving better best way ways`.split(/\s+/).filter(Boolean));

  function stem(w) {
    if (w.length <= 3 || /\d/.test(w)) return w;
    if (w.endsWith("ies") && w.length > 4) return w.slice(0, -3) + "y";
    if (w.endsWith("sses")) w = w.slice(0, -2);
    else if (w.endsWith("s") && !/(ss|us|is|ics)$/.test(w)) w = w.slice(0, -1);
    if (w.endsWith("ing") && w.length > 6) w = w.slice(0, -3);
    else if (w.endsWith("ed") && w.length > 5 && !w.endsWith("eed")) w = w.slice(0, -2);
    return w;
  }

  // Returns [{term, surface}] where term is a stemmed word or "word word" phrase.
  function terms(text, { bigrams = true } = {}) {
    const out = [];
    const segments = String(text || "").toLowerCase().replace(/[’']/g, "").split(/[,;.:()\[\]\n\/|•–—]+|\s-\s|\band\b|\bor\b/);
    for (const seg of segments) {
      const words = seg.replace(/[^a-z0-9+#&\- ]/g, " ").split(/[\s\-]+/).filter(Boolean);
      let prev = null;
      for (const raw of words) {
        if (STOP.has(raw) || raw.length < 2 || /^\d+$/.test(raw)) { prev = null; continue; }
        const t = stem(raw);
        out.push({ term: t, surface: raw });
        if (bigrams && prev) out.push({ term: prev.t + " " + t, surface: prev.raw + " " + raw });
        prev = { t, raw };
      }
    }
    return out;
  }
  const termKeys = text => terms(text).map(x => x.term);

  // Field weights: tags are the most deliberate signal; long summaries are noisy.
  const FIELDS = [
    [p => p.research_tags.join(" ; "), 3],
    [p => p.directory_research, 2],
    [p => (p.research_summary || "").slice(0, 3000), 1],
    [p => p.classes.map(c => c.title).join(" ; "), 1.5],
    [p => p.department, 1],
  ];

  class TextIndex {
    constructor(people) {
      this.people = people;
      this.surface = new Map();          // term -> {form: count}
      this.docs = people.map(p => {
        const tf = new Map();
        let len = 0;
        for (const [get, w] of FIELDS) {
          for (const { term, surface } of terms(get(p))) {
            tf.set(term, (tf.get(term) || 0) + w); len += w;
            const forms = this.surface.get(term) || {}; forms[surface] = (forms[surface] || 0) + 1; this.surface.set(term, forms);
          }
        }
        return { p, tf, len };
      });
      this.N = this.docs.length;
      this.avgLen = this.docs.reduce((s, d) => s + d.len, 0) / this.N;
      this.df = new Map();
      for (const d of this.docs) for (const t of d.tf.keys()) this.df.set(t, (this.df.get(t) || 0) + 1);
      this.groups = SYNONYM_GROUPS.map(g => g.map(ph => ({ phrase: ph, keys: phraseKeys(ph) })));
    }
    idf(t) { const df = this.df.get(t) || 0; return Math.log(1 + (this.N - df + 0.5) / (df + 0.5)); }
    display(t) {
      const forms = this.surface.get(t); if (!forms) return t;
      return Object.entries(forms).sort((a, b) => b[1] - a[1])[0][0];
    }

    // Query terms with weights, plus the related phrases that were added.
    // Each original query word is a "concept"; related terms count toward the concept that triggered them.
    expand(query) {
      const q = new Map(), concept = new Map();
      for (const t of termKeys(query)) {
        q.set(t, Math.max(q.get(t) || 0, t.includes(" ") ? 1.5 : 1));
        concept.set(t, t.split(" "));
      }
      const original = new Set(q.keys());
      const has = keys => keys.length > 0 && keys.every(k => original.has(k));
      const added = [];
      for (const g of this.groups) {
        const trig = g.filter(m => has(m.keys));
        if (!trig.length) continue;
        const cs = [...new Set(trig.flatMap(m => m.keys.flatMap(k => k.split(" "))))];
        for (const m of g) {
          if (has(m.keys)) continue;
          let any = false;
          for (const k of m.keys) if (this.df.has(k) && !q.has(k)) { q.set(k, k.includes(" ") ? 0.5 : 0.3); concept.set(k, cs); any = true; }
          if (any && !added.includes(m.phrase)) added.push(m.phrase);
        }
      }
      const concepts = [...new Set([...original].filter(t => !t.includes(" ")))];
      return { weights: q, added, concept, concepts };
    }

    // BM25 ranking. Returns [{p, score, hits:[{term, w}]}] sorted best first.
    search(query, { limit = Infinity, expand = true } = {}) {
      const ex = this.expand(query);
      const weights = expand ? ex.weights : new Map([...ex.weights].filter(([t]) => !ex.concept.get(t) || termKeys(query).includes(t)));
      const cWeight = new Map(ex.concepts.map(c => [c, this.idf(c)]));
      const cTotal = [...cWeight.values()].reduce((a, b) => a + b, 0) || 1;
      const k1 = 1.2, b = 0.6, res = [];
      for (const d of this.docs) {
        let score = 0; const hits = [], covered = new Set();
        for (const [t, qw] of weights) {
          const tf = d.tf.get(t); if (!tf) continue;
          const s = qw * this.idf(t) * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * d.len / this.avgLen));
          score += s; hits.push({ term: t, w: s });
          (ex.concept.get(t) || []).forEach(c => covered.add(c));
        }
        if (score <= 0) continue;
        // Reward covering more of the query's distinct ideas (rare ideas count more).
        const coverage = [...covered].reduce((a, c) => a + (cWeight.get(c) || 0), 0) / cTotal;
        res.push({ p: d.p, score: score * (0.3 + 0.7 * coverage), raw: score, coverage, covered: [...covered], hits: hits.sort((a, b) => b.w - a.w) });
      }
      const added = expand ? ex.added : [];
      res.sort((a, b) => b.score - a.score);
      return { results: res.slice(0, limit), added, weights, concepts: ex.concepts, conceptWeight: cWeight };
    }

    // Human-readable reasons a person matched: tags and classes containing matched terms, then other key words.
    explain(p, hits) {
      const top = hits.slice(0, 8).map(h => h.term);
      const covered = new Set();
      const tagHits = p.research_tags.filter(tag => {
        const keys = new Set(termKeys(tag));
        const m = top.filter(t => keys.has(t));
        m.forEach(t => covered.add(t));
        return m.length > 0;
      }).slice(0, 4);
      const classHits = p.classes.filter(c => {
        const keys = new Set(termKeys(c.title));
        const m = top.filter(t => keys.has(t));
        m.forEach(t => covered.add(t));
        return m.length > 0;
      }).slice(0, 2);
      const words = [];
      for (const t of top) {
        if (covered.has(t)) continue;
        if (!t.includes(" ") && top.some(o => o.includes(" ") && o.split(" ").includes(t))) continue;
        const d = this.display(t);
        if (!words.includes(d)) words.push(d);
      }
      return { tags: tagHits, classes: classHits, words: words.slice(0, 4) };
    }

    // Unit-length TF-IDF vectors for comparing faculty with each other.
    vectors() {
      if (this._vecs) return this._vecs;
      this._vecs = this.docs.map(d => {
        const v = new Map(); let norm = 0;
        for (const [t, tf] of d.tf) {
          const df = this.df.get(t);
          if (df < 2 || df > this.N * 0.25) continue;   // ignore one-offs and near-universal terms
          const w = (1 + Math.log(tf)) * Math.log(this.N / df) * (t.includes(" ") ? 1.4 : 1);
          v.set(t, w); norm += w * w;
        }
        norm = Math.sqrt(norm) || 1;
        for (const [t, w] of v) v.set(t, w / norm);
        return v;
      });
      return this._vecs;
    }
    similarity(i, j) {
      const V = this.vectors(); let a = V[i], b = V[j]; if (a.size > b.size) [a, b] = [b, a];
      let s = 0, shared = [];
      for (const [t, w] of a) { const w2 = b.get(t); if (w2) { s += w * w2; shared.push([t, w * w2]); } }
      return { score: s, shared };
    }
    // Readable shared topics for an edge: prefer phrases, drop words already inside a chosen phrase.
    sharedTopics(shared, n = 4) {
      const sorted = [...shared].sort((a, b) => b[1] - a[1]).map(x => x[0]);
      const out = [];
      for (const t of sorted) {
        if (out.length >= n) break;
        if (!t.includes(" ") && out.some(o => o.split(" ").includes(this.display(t)))) continue;
        if (t.includes(" ")) {
          const ws = t.split(" ").map(w => this.display(w));
          const i = out.findIndex(o => o.endsWith(" " + ws[0]) || o.startsWith(ws[1] + " "));
          if (i >= 0) { const o = out[i]; out[i] = o.endsWith(" " + ws[0]) ? o + " " + ws[1] : ws[0] + " " + o; continue; }
          const d = ws.join(" ");
          if (!out.includes(d)) out.push(d);
        } else { const d = this.display(t); if (!out.includes(d)) out.push(d); }
      }
      return out;
    }
  }

  function phraseKeys(ph) {
    const ws = termKeys(ph).filter(t => !t.includes(" "));
    if (ws.length <= 1) return ws;
    const keys = [];
    for (let i = 0; i + 1 < ws.length; i++) keys.push(ws[i] + " " + ws[i + 1]);
    return keys;
  }

  window.TextIndex = TextIndex;
  window.textTerms = termKeys;
})();
