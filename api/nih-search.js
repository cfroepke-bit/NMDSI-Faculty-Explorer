// Vercel serverless function: keyword search of NIH RePORTER for the dashboard's "Funded projects like this".
// The browser can't call RePORTER directly (its API refuses cross-site requests), so this relays the search.
//
// GET /api/nih-search?terms=["machine learning","fraud"]&scope=WI|US
// Tries all terms together (AND), then fewer, until at least 3 projects are found.
// Returns {query, total, items: [{id, title, pi, org, city, state, years, amount, ic, activity, url}]}.

const URL = "https://api.reporter.nih.gov/v2/projects/search";
const FIELDS = ["ApplId", "CoreProjectNum", "ProjectTitle", "PrincipalInvestigators", "Organization", "FiscalYear",
                "AwardAmount", "AgencyIcAdmin", "ActivityCode"];

function cleanTerms(raw) {
  let terms = [];
  try { terms = JSON.parse(raw || "[]"); } catch { return []; }
  return (Array.isArray(terms) ? terms : [])
    .filter(t => typeof t === "string")
    .map(t => t.replace(/[^\p{L}\p{N}' -]/gu, " ").replace(/\s+/g, " ").trim())
    .filter(t => t.length >= 2 && t.length <= 60)
    .slice(0, 3);
}

async function search(terms, scope) {
  const year = new Date().getFullYear();
  const text = terms.map(t => (t.includes(" ") ? `"${t}"` : t)).join(" ");
  const criteria = {
    advanced_text_search: { operator: "and", search_field: "projecttitle,terms,abstracttext", search_text: text },
    fiscal_years: [year - 4, year - 3, year - 2, year - 1, year, year + 1],
  };
  if (scope === "WI") criteria.org_states = ["WI"];
  const r = await fetch(URL, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json",
               "User-Agent": "NMDSI-Faculty-Explorer (https://github.com/cfroepke-bit/NMDSI-Faculty-Explorer)" },
    body: JSON.stringify({ criteria, include_fields: FIELDS, limit: 50, sort_field: "fiscal_year", sort_order: "desc" }),
  });
  if (!r.ok) throw new Error(`RePORTER HTTP ${r.status}`);
  const data = await r.json();
  // One entry per project (RePORTER returns a record per fiscal year).
  const byCore = new Map();
  for (const p of data.results || []) {
    const key = p.core_project_num || p.appl_id;
    const e = byCore.get(key);
    if (!e) byCore.set(key, { p, years: [p.fiscal_year], amount: p.award_amount || 0 });
    else { e.years.push(p.fiscal_year); e.amount += p.award_amount || 0; }
  }
  const items = [...byCore.values()].slice(0, 8).map(({ p, years, amount }) => {
    const pi = (p.principal_investigators || []).find(x => x.is_contact_pi) || (p.principal_investigators || [])[0] || {};
    return {
      id: p.core_project_num || String(p.appl_id), title: p.project_title,
      pi: [pi.first_name, pi.last_name].filter(Boolean).join(" "), pi_first: pi.first_name || "", pi_last: pi.last_name || "",
      org: p.organization?.org_name, city: p.organization?.org_city, state: p.organization?.org_state,
      years: [Math.min(...years), Math.max(...years)], amount: amount || null,
      ic: p.agency_ic_admin?.abbreviation, activity: p.activity_code,
      url: `https://reporter.nih.gov/project-details/${p.appl_id}`,
    };
  });
  return { query: text, total: data.meta?.total ?? items.length, items };
}

module.exports = async (req, res) => {
  const terms = cleanTerms(req.query.terms);
  const scope = req.query.scope === "US" ? "US" : "WI";
  if (!terms.length) { res.status(400).json({ error: "terms required" }); return; }
  try {
    let result = null;
    for (let k = terms.length; k >= 1; k--) {
      result = await search(terms.slice(0, k), scope);
      if (result.items.length >= 3) break;
    }
    res.setHeader("Cache-Control", "public, s-maxage=86400, stale-while-revalidate=604800");
    res.status(200).json(result);
  } catch (e) {
    res.status(502).json({ error: String(e.message || e) });
  }
};

module.exports.cleanTerms = cleanTerms;
module.exports.search = search;
