/* CounterSign - client. Contract text is untrusted: everything rendered goes through h(). */
"use strict";

const S = { user: "Karandeep", meta: null, sort: { key: "deadline", dir: 1 }, tab: "findings", openReason: null };
try { S.user = localStorage.getItem("cs.user") || "Karandeep"; } catch (e) { /* storage unavailable */ }

const $ = (sel, root = document) => root.querySelector(sel);
const app = () => $("#app");
const h = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const qt = (s) => h(String(s ?? "").replace(/\*\*/g, ""));
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const fmtDate = (iso) => { if (!iso) return "-"; const [y, m, d] = iso.slice(0, 10).split("-"); return `${+d} ${MON[+m - 1]} ${y}`; };
const fmtMoney = (v, cur = "USD") => {
  if (v === null || v === undefined || v === "") return "-";
  if (cur === "INR") { const n = Math.round(v).toString(); const last = n.slice(-3), rest = n.slice(0, -3); return "₹" + (rest ? rest.replace(/\B(?=(\d{2})+(?!\d))/g, ",") + "," : "") + last; }
  return ({ USD: "$", EUR: "€" }[cur] || cur + " ") + Math.round(v).toLocaleString("en-US");
};
const daysUntil = (iso) => iso ? Math.round((new Date(iso) - new Date(S.meta.today)) / 864e5) : null;
const SIDE = { supplier: "AtliQ = supplier", buyer: "AtliQ = buyer (own paper)", partner: "AtliQ = partner", nda: "NDA party" };

async function api(path, opts = {}) {
  const res = await fetch(path, { ...opts, headers: { "Content-Type": "application/json", "X-User": S.user, ...(opts.headers || {}) } });
  const ct = res.headers.get("content-type") || "";
  const body = ct.includes("json") ? await res.json() : await res.text();
  if (!res.ok) throw new Error(body.error || res.statusText);
  return body;
}
const post = (path, data) => api(path, { method: "POST", body: JSON.stringify(data) });

function toast(msg, err = false) {
  const t = $("#toast"); t.textContent = msg; t.className = "show" + (err ? " err" : "");
  clearTimeout(t._t); t._t = setTimeout(() => (t.className = ""), err ? 6000 : 3000);
}
const role = () => S.meta.users[S.user].role;

/* ------------------------------------------------------------------ boot */
async function boot() {
  S.meta = await api("/api/meta");
  const sel = $("#userSel");
  sel.innerHTML = Object.entries(S.meta.users).map(([n, u]) => `<option value="${h(n)}" title="${h(u.title)}">${h(n)} (${h(u.title.split(" - ")[0])})</option>`).join("");
  sel.value = S.user in S.meta.users ? S.user : "Karandeep";
  sel.onchange = () => { S.user = sel.value; try { localStorage.setItem("cs.user", S.user); } catch (e) { } route(); };
  $("#todayNote").textContent = `Dataset "today": ${fmtDate(S.meta.today)} · Principles: ${S.meta.principles_version}`;
  $("#footMeta").textContent = S.meta.ai_available ? `AI second pass available (${S.meta.ai_model})` : "Rules-first review · AI second pass off (optional)";
  window.addEventListener("hashchange", route);
  route();
}

function route() {
  const [, page = "queue", arg, tab] = location.hash.split("/");
  if (page === "review" && tab) S.tab = tab;   // deep link, e.g. #/review/<id>/conflicts
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("on", a.dataset.nav === page || (page === "review" && a.dataset.nav === "queue")));
  const views = { queue: viewQueue, review: () => viewReview(decodeURIComponent(arg || "")), register: viewRegister, intake: viewIntake, audit: viewAudit, evals: viewEvals };
  (views[page] || viewQueue)().catch((e) => { app().innerHTML = `<div class="notice act"><b>Something went wrong.</b> ${h(e.message)}</div>`; });
  app().focus({ preventScroll: true });
}

/* ------------------------------------------------------------------ queue (FR-41, seller status cards FR-37) */
async function viewQueue() {
  const data = await api("/api/queue");
  const cards = data.cards;
  const due7 = cards.filter((c) => { const d = daysUntil(c.deadline); return d !== null && d <= 7; });
  const openSerious = cards.reduce((a, c) => a + c.open_serious, 0);
  const value = cards.reduce((a, c) => a + (c.currency === "USD" ? (c.value || 0) : c.currency === "EUR" ? (c.value || 0) * 1.09 : 0), 0);
  const acts = cards.filter((c, i, all) => c.actions_now && all.findIndex((x) => x.actions_now && x.counterparty === c.counterparty) === i);
  const isSeller = role() === "seller";
  app().innerHTML = `
    <div class="spread"><div><h1>${isSeller ? "My contracts" : "Contract queue"}</h1>
      <p class="muted" style="margin:0">${isSeller ? "Status, deadline and what is blocking each of your contracts. Karandeep reviews and signs." : "Every draft waiting for a decision, with a complete cited review ready. Deadlines order the queue; they never change a finding."}</p></div>
      <a class="btn primary" href="#/intake">+ New contract</a></div>
    <div class="stats">
      <div class="stat"><b>${cards.length}</b><span>contracts waiting</span></div>
      <div class="stat"><b class="${due7.length ? "due-soon" : ""}">${due7.length}</b><span>due within 7 days</span></div>
      <div class="stat"><b>${openSerious}</b><span>Serious items without a disposition</span></div>
      <div class="stat"><b>${fmtMoney(value)}</b><span>approx. value in queue (USD)</span></div>
    </div>
    ${acts.length && !isSeller ? `<div class="notice act" style="margin-bottom:14px"><b>Act now (outside CounterSign):</b> ${acts.map((c) => `<a href="#/review/${encodeURIComponent(c.id)}">${h(c.counterparty)}</a>`).join(", ")} - open the review for details.</div>` : ""}
    <div class="cov" style="margin-bottom:14px">Promise Register coverage: ${h(data.coverage.line)}. <a href="#/register">See what is missing</a></div>
    ${isSeller ? sellerCards(cards) : queueTable(cards)}`;
  document.querySelectorAll("th.sort").forEach((th) => th.onclick = () => {
    S.sort = { key: th.dataset.k, dir: S.sort.key === th.dataset.k ? -S.sort.dir : 1 }; viewQueue();
  });
  document.querySelectorAll("tr.click, .card.click").forEach((el) => el.onclick = () => {
    if (el.dataset.open === "true") location.hash = "#/review/" + encodeURIComponent(el.dataset.id); else toast("You can see the status card; the full review is Karandeep's.");
  });
}

function counts(c) {
  return `<span class="counts">${c.serious ? `<span class="pill Serious">${c.serious} Serious</span>` : ""}${c.review ? `<span class="pill Review">${c.review} Review</span>` : ""}${!c.serious && !c.review ? `<span class="pill ok">No Serious</span>` : ""}</span>`;
}

function sortCards(cards) {
  const { key, dir } = S.sort;
  const v = (c) => key === "deadline" ? (c.deadline || "9999") : key === "value" ? -(c.value || 0) : key === "waiting" ? -(c.days_waiting || 0) : key === "serious" ? -c.open_serious : c.counterparty;
  return [...cards].sort((a, b) => (v(a) > v(b) ? 1 : v(a) < v(b) ? -1 : 0) * dir);
}

function queueTable(cards) {
  const arrow = (k) => S.sort.key === k ? (S.sort.dir > 0 ? " ↑" : " ↓") : "";
  return `<div class="card tablewrap" style="padding:4px 6px"><table>
    <thead><tr><th class="sort" data-k="name">Contract${arrow("name")}</th><th class="hide-sm">Side · entity</th><th class="sort" data-k="deadline">Deadline${arrow("deadline")}</th>
    <th class="sort" data-k="value">Value${arrow("value")}</th><th class="sort hide-sm" data-k="waiting">Waiting${arrow("waiting")}</th><th>Review</th><th class="sort" data-k="serious">Open${arrow("serious")}</th><th class="hide-sm">Stage</th></tr></thead>
    <tbody>${sortCards(cards).map((c) => {
      const d = daysUntil(c.deadline);
      return `<tr class="click" data-id="${h(c.id)}" data-open="${c.can_open}">
        <td><b>${h(c.counterparty)}</b><div class="muted" style="font-size:13px">${h(c.doc_type)} · ${h(c.seller)}${c.kind === "upload" ? " · uploaded" : ""}</div></td>
        <td class="hide-sm" style="font-size:13px">${h(SIDE[c.side] || c.side)}<div class="muted">${h(c.entity ? "AtliQ " + c.entity : "-")}</div></td>
        <td>${c.deadline ? `<span class="${d <= 3 ? "due-soon" : ""}">${fmtDate(c.deadline)}</span><div class="muted" style="font-size:12px">${d < 0 ? `${-d}d overdue` : `in ${d}d`}</div>` : `<span class="muted">none set</span>`}</td>
        <td style="font-variant-numeric:tabular-nums">${fmtMoney(c.value, c.currency)}</td>
        <td class="hide-sm">${c.days_waiting ?? "-"}d</td>
        <td>${counts(c)}${c.conflicts ? `<div style="margin-top:3px"><span class="pill possible">${c.conflicts} past-promise match${c.conflicts > 1 ? "es" : ""}</span></div>` : ""}${c.actions_now ? `<div style="margin-top:3px"><span class="pill Serious">Act now</span></div>` : ""}</td>
        <td><b style="font-variant-numeric:tabular-nums">${c.open_serious}</b></td>
        <td class="hide-sm" style="font-size:13px">${h(c.stage)}</td></tr>`;
    }).join("")}</tbody></table></div>`;
}

function sellerCards(cards) {
  if (!cards.length) return `<div class="card"><p class="muted">No contracts brought in by ${h(S.user)} are waiting.</p></div>`;
  return `<div class="cards">${sortCards(cards).map((c) => `
    <div class="card click" data-id="${h(c.id)}" data-open="${c.can_open}" style="cursor:pointer">
      <div class="spread"><h3>${h(c.counterparty)}</h3>${counts(c)}</div>
      <div class="muted" style="font-size:13px;margin-bottom:8px">${h(c.doc_type)} · ${fmtMoney(c.value, c.currency)}</div>
      <dl class="kv"><dt>Stage</dt><dd>${h(c.stage)}</dd><dt>Deadline</dt><dd>${fmtDate(c.deadline)}</dd><dt>Waiting</dt><dd>${c.days_waiting ?? "-"} days</dd>
      <dt>Open Serious</dt><dd><b>${c.open_serious}</b></dd><dt>Documents missing</dt><dd>${c.documents_missing.length ? h(c.documents_missing.join(", ")) : "none"}</dd></dl>
    </div>`).join("")}</div>`;
}

/* ------------------------------------------------------------------ review */
async function viewReview(id, useAi = false) {
  if (!id) return viewQueue();
  app().innerHTML = `<p class="muted pad">Running the review…</p>`;
  const data = await api(`/api/review/${encodeURIComponent(id)}${useAi ? "?ai=1" : ""}`);
  S.cur = data;
  renderReview();
}

function renderReview() {
  const { review: r, decisions, gate, status, card, can_decide } = S.cur;
  const d = r.doc;
  const rl = r.review_line;
  const tabs = [
    ["findings", "Findings", r.findings.length],
    ["conflicts", "Past promises", r.conflicts.length],
    ["fairness", "Fairness", r.fairness.filter((x) => x.asymmetric).length],
    ["entity", "Entity & bundle", (r.bundle ? r.bundle.issues.length : 0) + r.entity.filter((e) => e.status !== "ok").length],
    ["cnc", "Could not check", r.could_not_check.length],
    ["checks", "Checks run", r.checks_run.length],
    ["doc", "Document", rl.clauses_total],
  ];
  const dd = daysUntil(d.deadline);
  app().innerHTML = `
    <p style="margin:0 0 8px"><a href="#/queue">← Queue</a></p>
    <div class="rev-head">
      <div class="spread"><div><h1>${h(d.counterparty)} <span class="muted" style="font-weight:400">· ${h(d.doc_type)}</span></h1>
        <div class="meta-line"><span>${h(SIDE[d.side] || d.side)}</span><span>Entity named: <b>${h(d.entity_named ? "AtliQ " + d.entity_named : "not found")}</b></span>
        <span>Value: <b>${fmtMoney(d.value, d.currency)}</b></span><span>Deadline: <b>${fmtDate(d.deadline)}</b>${dd !== null ? ` (${dd < 0 ? -dd + "d overdue" : "in " + dd + "d"}) - shown, never changes a severity` : ""}</span>
        <span>Brought by: <b>${h(d.seller || "-")}</b></span>${d.tracker_id ? `<span>Tracker ${h(d.tracker_id)}</span>` : ""}</div></div>
        <div class="row">${S.meta.ai_available ? `<button class="btn sm" id="aiBtn">Run AI second pass</button>` : ""}</div></div>
      <div class="meta-line"><span><b>${rl.clauses_reviewed} of ${rl.clauses_total}</b> clauses reviewed</span><span>${rl.definitions} definitions attached to the clauses that use them</span>
        <span>Review ready in ${rl.elapsed_seconds}s</span><span>${r.sources_consulted.length} files consulted</span><span>Stage: <b>${h(status.stage || card.stage)}</b></span></div>
      <div class="cov"><b>Coverage:</b> ${h(r.coverage.line)}. Matches below are only as complete as the register - this is not a clearance.</div>
      <div class="row" style="margin-top:4px">
        <span class="pill Serious">${r.summary.serious} Serious</span><span class="pill Review">${r.summary.review} Review</span><span class="pill Minor">${r.summary.minor} Minor</span>
        ${r.summary.conflicts ? `<span class="pill possible">${r.summary.conflicts} past-promise match${r.summary.conflicts > 1 ? "es" : ""}</span>` : ""}
        ${r.summary.ld_exposure ? `<span class="pill ghost">Delay damages: ${h(r.summary.ld_exposure.per_period || r.summary.ld_exposure.rate)} · ${h(r.summary.ld_exposure.cap_status)}</span>` : ""}
        ${r.summary.liability ? `<span class="pill ghost">Liability: ${h(r.summary.liability)}</span>` : ""}
      </div>
      ${r.ai_note ? `<div class="notice">${h(r.ai_note)}</div>` : ""}
      ${r.actions_now.map((e) => `<div class="notice act"><b>${h(e.title)}.</b> ${h(e.detail)}${e.sources.map((s) => `<blockquote class="q">${qt(s.quote)}</blockquote><div class="qmeta"><span>${h(s.file)}</span>${verif(s.verified)}</div>`).join("")}</div>`).join("")}
      ${r.clean_message ? `<div class="notice calm"><b>${h(r.clean_message)}</b></div>` : ""}
      ${d.informal === "yes" ? `<div class="notice"><b>Agreed outside the document (from intake):</b> ${h(d.informal_note)} - reviewed below alongside the clauses; it never overrides the contract.</div>` : ""}
    </div>
    <div class="layout">
      <section>
        <div class="tabs" role="tablist">${tabs.map(([k, l, n]) => `<button role="tab" data-tab="${k}" class="${S.tab === k ? "on" : ""}">${l}<span class="n">${n}</span></button>`).join("")}</div>
        <div id="tabBody"></div>
      </section>
      <aside class="side">${decisionPanel(r, decisions, gate, status, can_decide)}</aside>
    </div>`;
  document.querySelectorAll(".tabs button").forEach((b) => b.onclick = () => { S.tab = b.dataset.tab; renderReview(); });
  if ($("#aiBtn")) $("#aiBtn").onclick = () => viewReview(d.id, true);
  renderTab();
  wireDecisionPanel();
}

const verif = (ok) => ok ? `<span class="v-ok" title="String-matched against the source file">✓ verbatim in source</span>` : `<span class="v-no">Not sure - please cross-check</span>`;
const principleChip = (p) => { const k = (p || "").split(" ")[0]; const pr = S.meta.principles[k]; return `<span class="chip" title="${h(pr ? pr.text + " (checklist: " + pr.checklist + ")" : p)}">${h(p)}${pr ? " · " + h(pr.name) : ""}</span>`; };

function dispositionBar(item) {
  const { decisions, can_decide } = S.cur;
  const dec = decisions[item.id];
  if (dec) {
    return `<div class="disp"><span class="pill ${dec.disposition === "accept" ? "Review" : "ok"}">${h(dec.disposition)}</span>
      <span class="done-note">${h(dec.by)}, ${h(dec.at.replace("T", " "))}${dec.reason ? ` - "${h(dec.reason)}"` : ""}${dec.exception ? " · logged as a deliberate exception (not a new standard)" : ""}</span>
      ${can_decide ? `<button class="btn sm" data-undo="${h(item.id)}">Change</button>` : ""}</div>`;
  }
  if (!can_decide) return `<div class="disp"><span class="done-note muted">Awaiting Karandeep's disposition</span></div>`;
  const open = S.openReason === item.id;
  return `<div class="disp">${["accept", "negotiate", "needs counsel", "reject"].map((x) => `<button class="btn sm" data-disp="${x}" data-item="${h(item.id)}">${x[0].toUpperCase() + x.slice(1)}</button>`).join("")}
    ${open ? `<div style="flex-basis:100%"><label class="f" for="rs-${h(item.id)}">Reason ${item.severity === "Serious" ? "(required to accept a Serious item - logged with your name)" : "(optional)"}</label>
      <textarea id="rs-${h(item.id)}" placeholder="Why is this acceptable for this deal?"></textarea>
      <div class="row" style="margin-top:6px"><button class="btn sm primary" data-confirm="${h(item.id)}">Accept as a deliberate exception</button><button class="btn sm" data-cancel="1">Cancel</button></div></div>` : ""}</div>`;
}

function findingCard(f) {
  const done = S.cur.decisions[f.id];
  const ex = f.exposure ? Object.entries(f.exposure).filter(([k, v]) => v !== null && v !== "" && k !== "cap_status").map(([k, v]) => `<span>${h(k.replace(/_/g, " "))}: <b>${h(v)}</b></span>`).join("") : "";
  return `<article class="card finding ${h(f.severity)} ${done ? "done" : ""}" id="i-${h(f.id)}">
    <div class="spread"><div class="row"><span class="pill ${h(f.severity)}">${h(f.severity)}</span><h3 style="margin:0">${h(f.title)}</h3></div>
      <div class="row"><span class="mono">${h(f.clause_ref)}</span>${principleChip(f.principle)}</div></div>
    <p class="reason">${h(f.reason)}</p>
    ${ex ? `<div class="expo">${ex}</div>` : ""}
    <blockquote class="q">${qt(f.quote)}</blockquote>
    <div class="qmeta"><span>${h(f.source_title ? f.source_title + " · " : "")}${h(f.clause_ref)}${f.clause_title && f.clause_title !== f.clause_ref ? " " + h(f.clause_title) : ""}</span>${verif(f.verified)}<span>${f.origin === "ai" ? "AI-proposed" : "rule"} · ${h(f.category)}</span></div>
    ${f.definitions && f.definitions.length ? `<div class="qmeta" style="margin-top:4px">Definitions used: ${f.definitions.map((x) => `${h(x.term)} (${h(x.ref)})`).join(", ")}</div>` : ""}
    ${f.precedents && f.precedents.length ? `<details><summary>${f.precedents.length} precedent${f.precedents.length > 1 ? "s" : ""} from AtliQ's history (unreviewed)</summary><ul class="prec">${f.precedents.map((p) => `<li><b>${h(p.counterparty)}</b>: ${h(p.outcome)} - <i>"${h(p.quote)}"</i></li>`).join("")}</ul></details>` : ""}
    ${dispositionBar(f)}</article>`;
}

function conflictCard(c) {
  const poss = c.certainty.startsWith("Possible");
  return `<article class="card finding ${h(c.severity)}" id="i-${h(c.id)}">
    <div class="spread"><div class="row"><span class="pill ${poss ? "possible" : "Serious"}">${h(c.certainty)}</span><h3 style="margin:0">${h(c.entry_type)} - ${h(c.counterparty)}</h3></div>
      <div class="row">${principleChip("P9")}</div></div>
    <p class="reason">${h(c.why)}</p>
    ${c.question ? `<div class="notice" style="margin:6px 0"><b>Question that settles it:</b> ${h(c.question)}</div>` : ""}
    ${c.ai_explanation ? `<div class="notice" style="margin:6px 0"><b>AI explanation (from the two cited clauses):</b> ${h(c.ai_explanation)}</div>` : ""}
    <div class="two">
      <div><h4>Already signed - ${h(c.counterparty)} ${h(c.register_clauses)}</h4>
        ${(c.register_quotes.length ? c.register_quotes : [{ quote: c.register_quote, verified: c.register_verified }]).map((q) => `<blockquote class="q">${qt(q.quote)}</blockquote><div class="qmeta">${verif(q.verified)}</div>`).join("")}
        <div class="qmeta">${h(c.register_file || "tracker + signed files")}</div></div>
      <div><h4>This draft - ${h(c.draft_ref || "")}</h4><blockquote class="q">${qt(c.draft_quote || "")}</blockquote><div class="qmeta">${verif(c.draft_verified)}</div></div>
    </div>
    <dl class="kv" style="margin-top:8px"><dt>Who is bound</dt><dd>${h(c.entity_bound)}${c.affiliates ? " · " + h(c.affiliates) : ""}</dd>
      ${c.end ? `<dt>Runs until</dt><dd><b>${fmtDate(c.end)}</b> (${h(c.end_note)}) · ${h(c.status)}</dd>` : ""}
      ${c.label && c.label !== "standard" ? `<dt>Label</dt><dd>${h(c.label)}</dd>` : ""}
      ${c.extra && c.extra.rate_table ? `<dt>Rates</dt><dd>${c.extra.rate_table.map((x) => `${h(x.role)}: $${x.draft} vs $${x.register} (gap $${x.gap})`).join("<br>")}</dd>` : ""}
      ${c.extra && c.extra.informal_note ? `<dt>Agreed on a call</dt><dd>${h(c.extra.informal_note)}</dd>` : ""}
      ${c.extra && c.extra.termination ? `<dt>Note</dt><dd>${h(c.extra.termination)}</dd>` : ""}</dl>
    ${c.waivers.map((w) => `<div class="notice" style="margin-top:8px"><b>Waiver on file (${h(w.status)}):</b> ${w.covers_this_deal ? "covers this deal" : "<b>does not cover this deal</b>"} - ${h(w.limits)}<blockquote class="q">${qt(w.quote)}</blockquote><div class="qmeta">${h(w.file)} ${verif(w.verified)}</div></div>`).join("")}
    ${dispositionBar(c)}</article>`;
}

function renderTab() {
  const r = S.cur.review;
  const el = $("#tabBody");
  if (S.tab === "findings") {
    el.innerHTML = r.findings.length ? `<div class="grid">${r.findings.map(findingCard).join("")}</div>`
      : `<div class="card"><p><b>No findings from the checks we ran.</b> This is not a clearance - see "Checks run" for what was covered and "Could not check" for what was not.</p></div>`;
  } else if (S.tab === "conflicts") {
    el.innerHTML = `<div class="cov" style="margin-bottom:12px">${h(r.coverage.line)}. Matched on industry, geography, entity (incl. Affiliates), services, rates and assets, with definitions carried from the signed contracts.</div>` +
      (r.conflicts.length ? `<div class="grid">${r.conflicts.map(conflictCard).join("")}</div>` : `<div class="card"><p>No match against the ${h(r.coverage.covered)} signed records on file. Coverage is partial: ${h(r.coverage.total - r.coverage.covered)} signed records have no file yet.</p></div>`) +
      (r.history.length ? `<h2 style="margin-top:18px">Expired entries (history)</h2>${r.history.map((x) => `<div class="card" style="margin-top:8px"><b>${h(x.counterparty)} - ${h(x.type)}</b><p class="muted" style="margin:4px 0 0">${h(x.note)}</p></div>`).join("")}` : "");
  } else if (S.tab === "fairness") {
    el.innerHTML = `<p class="muted" style="margin-top:0">Each party's obligations side by side, whatever the title says. AtliQ's own paper is judged against the terms AtliQ asks for as a supplier.</p>
      <div class="card tablewrap" style="padding:4px 6px"><table class="fair"><thead><tr><th>Clause type</th><th>AtliQ</th><th>Both / mutual</th><th>${h(r.doc.counterparty)}</th></tr></thead><tbody>
      ${r.fairness.map((g) => `<tr class="${g.asymmetric ? "asym" : ""}"><td><b>${h(g.type)}</b></td>${["atliq", "both", "other"].map((k) => `<td>${g[k].length ? `<ul>${g[k].map((x) => `<li><span class="mono">${h(x.ref)}</span> ${h(x.text)}</li>`).join("")}</ul>` : `<span class="muted">-</span>`}</td>`).join("")}</tr>`).join("") || `<tr><td colspan="4" class="muted">No obligation clauses of these types found.</td></tr>`}
      </tbody></table></div>`;
  } else if (S.tab === "entity") {
    const b = r.bundle;
    el.innerHTML = `<div class="card"><h2>Entity, law and invoicing <span class="muted" style="font-weight:400;font-size:13px">rule table from finance's entity sheet - no AI</span></h2>
      <div class="tablewrap"><table><thead><tr><th>Check</th><th>Expected</th><th>Found</th><th>Status</th><th>Clause</th></tr></thead><tbody>
      ${r.entity.map((e) => `<tr><td>${h(e.check)}</td><td>${h(e.expected)}</td><td>${h(e.found)}</td><td class="${e.status === "ok" ? "st-ok" : e.status === "mismatch" ? "st-bad" : "st-rev"}">${e.status === "ok" ? "matches" : e.status === "mismatch" ? "mismatch" : "review"}</td><td class="mono">${h(e.ref)}</td></tr>`).join("")}
      </tbody></table></div></div>
      ${b ? `<div class="card" style="margin-top:14px"><h2>Deal bundle - ${h(b.name)}</h2>
        ${b.data_types.length ? `<p class="muted" style="margin-top:0">Data: ${h(b.data_types.join(", "))}. Rule: ${h(b.flowdown_rule.join("; "))}.</p>` : ""}
        <table><thead><tr><th>Document</th><th>Status</th></tr></thead><tbody>${b.documents.map((x) => `<tr><td>${h(x.doc)}${x.file ? `<div class="muted mono">${h(x.file)}</div>` : ""}</td><td class="${/Missing|only/.test(x.status) ? "st-bad" : /Signed/.test(x.status) ? "st-ok" : "st-rev"}">${h(x.status)}</td></tr>`).join("")}</tbody></table>
        ${!b.counts_toward_summary && b.issues.length ? `<p class="muted">Bundle issues are counted on the client contract and the subcontractor agreements, not on this NDA:</p>` : ""}
        ${b.issues.length ? `<div class="grid" style="margin-top:10px">${b.issues.map((i) => `<div class="card finding ${h(i.severity)}"><div class="row"><span class="pill ${h(i.severity)}">${h(i.severity)}</span><b>${h(i.title)}</b>${principleChip(i.principle)}</div><p class="reason">${h(i.reason)}</p><blockquote class="q">${qt(i.quote)}</blockquote><div class="qmeta"><span>${h(i.source_title || "")} ${h(i.clause_ref)}</span>${verif(i.verified)}</div></div>`).join("")}</div>` : ""}
      </div>` : `<p class="muted" style="margin-top:14px">This contract is not linked to a deal bundle.</p>`}`;
  } else if (S.tab === "cnc") {
    el.innerHTML = `<div class="card">${r.could_not_check.length ? `<ul>${r.could_not_check.map((x) => `<li>${h(x)}</li>`).join("")}</ul>` : `<p>Nothing flagged as unreadable, missing or in another prevailing language.</p>`}
      <p class="muted" style="margin-bottom:0">Clauses no principle covers are still read and shown in the Document tab.</p></div>`;
  } else if (S.tab === "checks") {
    el.innerHTML = `<div class="card"><h2>Checks run</h2><ul>${r.checks_run.map((x) => `<li>${h(x)}</li>`).join("")}</ul>
      ${r.checks_passed.length ? `<h2>Within AtliQ's positions</h2><ul>${r.checks_passed.map((x) => `<li>${h(x)}</li>`).join("")}</ul>` : ""}
      <h2>Files consulted (${r.sources_consulted.length})</h2><ul class="mono">${r.sources_consulted.map((x) => `<li>${h(x)}</li>`).join("")}</ul>
      <p class="muted">${h(r.principles_version)}</p></div>`;
  } else if (S.tab === "doc") {
    el.innerHTML = `<p class="muted">Loading document…</p>`;
    api(`/api/doc/${encodeURIComponent(r.doc.id)}`).then((doc) => {
      el.innerHTML = `<div class="card">${r.doc.provenance ? `<p class="muted" style="margin-top:0">${h(r.doc.provenance)}</p>` : ""}${doc.clauses.map((c) => `<div class="clause"><span class="ref">${h(c.ref)}</span>${h(c.text.replace(/\*\*/g, ""))}</div>`).join("")}</div>`;
    });
  }
  wireDispositions();
}

function decisionPanel(r, decisions, gate, status, canDecide) {
  const fb = S.cur.feedback;
  const decided = status.decision;
  return `<div class="card gate"><h2>Decision</h2>
    <p style="margin-top:0"><b>${gate.open.length}</b> Serious finding${gate.open.length === 1 ? "" : "s"} / past-promise match${gate.open.length === 1 ? "" : "es"} still need a disposition.</p>
    ${gate.open.length ? `<ul>${gate.open.slice(0, 6).map((o) => `<li><a href="#" data-jump="${h(o.id)}">${h(o.title)}</a></li>`).join("")}${gate.open.length > 6 ? `<li>…and ${gate.open.length - 6} more</li>` : ""}</ul>` : ""}
    ${canDecide ? `
      <button class="btn primary" id="readyBtn" ${gate.ready_enabled && !decided ? "" : "disabled"} style="width:100%;justify-content:center">Mark ready for my signature</button>
      <p class="muted" style="font-size:12.5px">Enabled only when every Serious item and past-promise match has a disposition. You sign by hand; CounterSign signs nothing.</p>
      <div class="row"><a class="btn" id="packBtn" href="#">Prepare counsel pack</a></div>
      <div class="row" style="margin-top:8px"><button class="btn sm" id="signedBtn" ${gate.ready_enabled && !decided ? "" : "disabled"}>Record: I signed it</button><button class="btn sm danger" id="rejBtn" ${decided ? "disabled" : ""}>Record: rejected</button></div>
      ${decided ? `<p class="notice" style="margin-top:8px">Decision recorded: <b>${h(decided)}</b> on ${h(status.decided.replace("T", " "))}${decided === "signed" ? ". New promises were extracted and wait for the register custodian's confirmation." : ""}</p>` : ""}`
      : `<p class="muted">Only Karandeep records dispositions and decisions. You can read this review and add context through the seller.</p>`}
  </div>
  <div class="card"><h3>Did the review miss anything important?</h3>
    ${fb ? `<p class="muted" style="margin:0">Answered: <b>${h(fb.missed)}</b>${fb.reason ? ` - ${h(fb.reason)}` : ""} (${h(fb.by)})</p>` : `
    <div class="row"><button class="btn sm" data-fb="no">No</button><button class="btn sm" data-fb="yes">Yes</button></div>
    <textarea id="fbReason" placeholder="Optional: what was missed?" style="margin-top:6px;min-height:50px"></textarea>
    <p class="muted" style="font-size:12px;margin:4px 0 0">Optional. Unanswered counts as unconfirmed.</p>`}</div>
  <div class="card"><h3>Ask about this contract</h3>
    <div class="row" style="flex-wrap:nowrap"><input type="text" id="askQ" placeholder="e.g. Is this enforceable? / hotels GCC"><button class="btn sm" id="askBtn">Ask</button></div>
    <div id="askA" class="answer"></div></div>`;
}

function wireDecisionPanel() {
  const id = S.cur.review.doc.id;
  document.querySelectorAll("[data-jump]").forEach((a) => a.onclick = (e) => {
    e.preventDefault();
    const isConflict = S.cur.review.conflicts.some((c) => c.id === a.dataset.jump);
    S.tab = isConflict ? "conflicts" : "findings"; renderReview();
    const t = document.getElementById("i-" + a.dataset.jump); if (t) t.scrollIntoView({ behavior: "smooth", block: "center" });
  });
  const ready = $("#readyBtn");
  if (ready) ready.onclick = async () => { try { await post("/api/ready", { doc_id: id }); toast("Marked ready for your signature - sign by hand."); viewReview(id); } catch (e) { toast(e.message, true); } };
  const pack = $("#packBtn");
  if (pack) pack.onclick = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch(`/api/counsel-pack/${encodeURIComponent(id)}`, { headers: { "X-User": S.user } });
      if (!res.ok) throw new Error((await res.json()).error);
      const blob = new Blob([await res.text()], { type: "text/html" });
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `counsel-pack-${id}.html`; a.click();
      toast("Counsel pack prepared. CounterSign sends nothing - attach it to your email to counsel.");
    } catch (err) { toast(err.message, true); }
  };
  const dec = (decision) => async () => {
    if (!confirm(decision === "signed" ? "Record that you signed this contract by hand?" : "Record that this contract was rejected?")) return;
    try { const r = await post("/api/decide", { doc_id: id, decision }); toast(decision === "signed" ? `Recorded. ${r.extracted} promise(s) extracted for confirmation.` : "Recorded as rejected."); viewReview(id); } catch (e) { toast(e.message, true); }
  };
  if ($("#signedBtn")) $("#signedBtn").onclick = dec("signed");
  if ($("#rejBtn")) $("#rejBtn").onclick = dec("rejected");
  document.querySelectorAll("[data-fb]").forEach((b) => b.onclick = async () => {
    await post("/api/feedback", { doc_id: id, missed: b.dataset.fb, reason: $("#fbReason").value }); toast("Thanks - recorded."); viewReview(id);
  });
  const ask = async () => {
    const q = $("#askQ").value.trim(); if (!q) return;
    const res = await post("/api/ask", { question: q, doc_id: id });
    $("#askA").innerHTML = `<p style="margin:0">${h(res.answer)}</p>` + (res.refused ? `<button class="btn sm" style="margin-top:6px" id="askPack">Prepare counsel pack</button>` : "") +
      (res.results || []).map((x) => `<div style="margin-top:8px"><span class="pill ghost">${h(x.kind)}</span> <b>${h(x.title)}</b> <span class="mono">${h(x.ref)}</span><blockquote class="q">${qt(x.quote)}</blockquote></div>`).join("");
    if ($("#askPack")) $("#askPack").onclick = () => $("#packBtn") ? $("#packBtn").click() : toast("Only Karandeep prepares counsel packs.");
  };
  $("#askBtn").onclick = ask;
  $("#askQ").onkeydown = (e) => { if (e.key === "Enter") ask(); };
}

function wireDispositions() {
  const id = S.cur.review.doc.id;
  const send = async (itemId, disposition, reason = "") => {
    try {
      const res = await post("/api/decision", { doc_id: id, item_id: itemId, disposition, reason });
      S.cur.decisions = res.decisions; S.cur.gate = res.gate; S.openReason = null; renderReview();
    } catch (e) { toast(e.message, true); }
  };
  document.querySelectorAll("[data-disp]").forEach((b) => b.onclick = () => {
    const item = [...S.cur.review.findings, ...S.cur.review.conflicts].find((x) => x.id === b.dataset.item);
    if (b.dataset.disp === "accept") { S.openReason = item.id; renderTab(); const t = document.getElementById("rs-" + item.id); if (t) t.focus(); return; }
    send(item.id, b.dataset.disp);
  });
  document.querySelectorAll("[data-confirm]").forEach((b) => b.onclick = () => send(b.dataset.confirm, "accept", $("#rs-" + CSS.escape(b.dataset.confirm)).value));
  document.querySelectorAll("[data-cancel]").forEach((b) => b.onclick = () => { S.openReason = null; renderTab(); });
  document.querySelectorAll("[data-undo]").forEach((b) => b.onclick = () => send(b.dataset.undo, null));
}

/* ------------------------------------------------------------------ register (FR-21 - FR-32) */
async function viewRegister() {
  const data = await api("/api/register");
  const cov = data.coverage;
  const pending = data.entries.filter((e) => !e.confirmed);
  const canConfirm = S.meta.users[S.user].custodian || role() === "reviewer";
  const geos = [...new Set(data.entries.flatMap((e) => e.geographies || []).filter((g) => g !== "*"))].sort();
  app().innerHTML = `
    <h1>Promise Register</h1>
    <p class="muted" style="margin-top:0">What AtliQ has already promised - non-competes, exclusivity, pricing promises, IP handed over, data-location duties, waivers and logged exceptions - each beside its source clause and confirmed by a person before conflict checks use it.</p>
    <div class="stats">
      <div class="stat"><b>${cov.covered} / ${cov.total}</b><span>signed records on file</span></div>
      <div class="stat"><b class="${cov.missing.length ? "due-soon" : ""}">${cov.missing.length}</b><span>signed records with no file</span></div>
      <div class="stat"><b>${data.entries.filter((e) => e.confirmed && e.status === "active").length}</b><span>active confirmed promises</span></div>
      <div class="stat"><b>${pending.length}</b><span>awaiting confirmation</span></div>
      <div class="stat"><b>${cov.restrictive_column_filled} / ${cov.tracker_rows}</b><span>tracker rows with restrictions noted (before)</span></div>
    </div>
    <div class="card"><h2>Search before you promise <span class="muted" style="font-weight:400;font-size:13px">e.g. "hotel analytics in Saudi?"</span></h2>
      <div class="row">
        <div style="flex:1;min-width:150px"><label class="f" for="sInd">Industry</label><select id="sInd"><option value="">Any</option>${["hospitality", "financial services", "retail", "cloud data platform", "healthcare", "online travel agency"].map((x) => `<option>${x}</option>`).join("")}</select></div>
        <div style="flex:1;min-width:150px"><label class="f" for="sCty">Country</label><select id="sCty"><option value="">Any</option>${geos.map((g) => `<option>${h(g)}</option>`).join("")}</select></div>
        <div style="flex:1;min-width:150px"><label class="f" for="sSvc">Service</label><input type="text" id="sSvc" placeholder="analytics, pricing, PipeKit…"></div>
        <button class="btn primary" id="sGo" style="align-self:flex-end">Search</button>
      </div><div id="sRes" style="margin-top:12px"></div></div>
    ${pending.length ? `<div class="card" style="margin-top:14px"><h2>Confirmation queue (${pending.length})</h2><p class="muted" style="margin-top:0">Low-confidence reads first. An entry joins conflict checks only after the custodian confirms it beside its clause.</p>
      <div class="grid">${pending.sort((a, b) => (b.low_confidence ? 1 : 0) - (a.low_confidence ? 1 : 0)).map((e) => `<div class="card">
        <div class="spread"><b>${h(e.counterparty)} - ${h(e.type)} <span class="mono">${h(e.clauses)}</span></b>${e.low_confidence ? `<span class="pill Review">Low-confidence scan</span>` : ""}</div>
        <p style="margin:4px 0">${h(e.activity)}</p>
        ${e.anchor_checks.map((a) => `<blockquote class="q">${qt(a.quote)}</blockquote><div class="qmeta">${h(e.file)} ${verif(a.verified)}</div>`).join("")}
        <dl class="kv" style="margin-top:6px"><dt>End</dt><dd>${e.end ? fmtDate(e.end) : "-"} (${h(e.end_note)})</dd><dt>Status</dt><dd>${h(e.status)}</dd></dl>
        ${canConfirm ? `<div class="row" style="margin-top:8px"><label class="f" for="end-${h(e.id)}" style="margin:0">End date</label><input type="date" id="end-${h(e.id)}" value="${h(e.end || "")}" style="max-width:170px"><button class="btn sm primary" data-confirm-entry="${h(e.id)}">Confirm beside clause</button></div>` : `<p class="muted">Waiting for the register custodian (Jay).</p>`}
      </div>`).join("")}</div></div>` : ""}
    <div class="card tablewrap" style="margin-top:14px;padding:4px 6px"><table><thead><tr><th>Counterparty</th><th>Type</th><th>Who is bound</th><th>What it restricts or promises</th><th>Runs until</th><th>Status</th></tr></thead><tbody>
      ${data.entries.filter((e) => e.confirmed).map((e) => `<tr class="reg-entry"><td>${h(e.counterparty)}<div class="mono muted">${h(e.clauses)}</div></td><td>${h(e.type)}${e.label && e.label !== "standard" ? `<div><span class="pill ghost">${h(e.label)}</span></div>` : ""}</td>
        <td style="font-size:13px">${h(e.entity)}${e.affiliates ? "<br><b>+ Affiliates</b>" : ""}</td>
        <td style="font-size:13px">${h(e.activity)}${e.geographies && e.geographies[0] !== "*" && e.geographies.length ? `<div class="muted">Geography: ${h(e.geographies.join(", "))}</div>` : ""}
          <details><summary>Source text (${e.anchor_checks.filter((a) => a.verified).length}/${e.anchor_checks.length} verified)</summary>${e.anchor_checks.map((a) => `<blockquote class="q">${qt(a.quote)}</blockquote>`).join("")}<div class="qmeta">${h(e.file)} · confirmed by ${h(e.confirmed_by || "-")} on ${h((e.confirmed_on || "").slice(0, 10))}</div></details></td>
        <td style="white-space:nowrap">${e.end ? fmtDate(e.end) : "permanent"}<div class="muted" style="font-size:12px;white-space:normal">${h(e.end_note)}</div></td>
        <td class="status-${h(e.status)}">${h(e.status)}</td></tr>`).join("")}
    </tbody></table></div>
    <div class="card" style="margin-top:14px"><h2>Signed records with no file (${cov.missing.length})</h2>
      <p class="muted" style="margin-top:0">Every conflict check states this gap. Back-fill as files are found.${cov.duplicates.length ? ` Duplicate tracker rows ignored: ${h(cov.duplicates.join(", "))}.` : ""}</p>
      <div class="tablewrap"><table><thead><tr><th>Tracker</th><th>Counterparty</th><th>Document</th><th>Signed</th></tr></thead><tbody>${cov.missing.map((m) => `<tr><td class="mono">${h(m.id)}</td><td>${h(m.counterparty)}</td><td>${h(m.doc_type)}</td><td>${fmtDate(m.signed)}</td></tr>`).join("")}</tbody></table></div></div>`;
  const search = async () => {
    const q = new URLSearchParams({ industry: $("#sInd").value, country: $("#sCty").value, service: $("#sSvc").value });
    const res = await api("/api/register-search?" + q);
    $("#sRes").innerHTML = `<div class="cov">${h(res.coverage.line)}. Results cover confirmed entries only.</div>` + (res.results.length ? res.results.map((e) => `<div class="card" style="margin-top:8px">
      <div class="spread"><b>${h(e.counterparty)} - ${h(e.type)} <span class="mono">${h(e.clauses)}</span></b><span class="status-${h(e.status)}">${h(e.status)}${e.end ? " until " + fmtDate(e.end) : ""}</span></div>
      <p style="margin:4px 0">${h(e.activity)}</p><div class="muted" style="font-size:13px">${h(e.entity)}${e.affiliates ? " + Affiliates" : ""}${e.industry_definition ? " · " + h(e.industry_definition) : ""}</div>
      ${data.entries.filter((w) => w.parent === e.id).map((w) => `<div class="notice" style="margin-top:6px"><b>Waiver (${h(w.status)}):</b> ${h(w.activity)}</div>`).join("")}</div>`).join("") : `<p>No confirmed entry matched. Coverage is partial (${h(res.coverage.total - res.coverage.covered)} signed records have no file), so check with Karandeep before promising.</p>`);
  };
  $("#sGo").onclick = search;
  document.querySelectorAll("[data-confirm-entry]").forEach((b) => b.onclick = async () => {
    const id = b.dataset.confirmEntry; const end = $("#end-" + CSS.escape(id)).value;
    try { await post("/api/register-confirm", { entry_id: id, edits: end ? { end } : {} }); toast("Confirmed - now used in conflict checks."); viewRegister(); } catch (e) { toast(e.message, true); }
  });
}

/* ------------------------------------------------------------------ intake (FR-01 - FR-05) */
async function viewIntake() {
  app().innerHTML = `<h1>New contract</h1>
    <p class="muted" style="margin-top:0">Upload a draft (PDF, Word, Markdown or text) as a new contract or a new version. Every version is reviewed in full. Deal context is pre-filled from the document - please confirm it.</p>
    <form class="card" id="upForm" style="max-width:820px">
      <div class="grid" style="grid-template-columns:1fr 1fr">
        <div style="grid-column:1/-1"><label class="f" for="uFile">Contract file</label><input type="file" id="uFile" accept=".pdf,.docx,.md,.txt" required></div>
        <div><label class="f" for="uCp">Counterparty</label><input type="text" id="uCp" required></div>
        <div><label class="f" for="uType">Document type</label><input type="text" id="uType" placeholder="MSA, SOW, NDA, BAA…"></div>
        <div><label class="f" for="uSide">AtliQ's side of the table</label><select id="uSide"><option value="supplier">Supplier (client paper)</option><option value="buyer">Buyer (AtliQ's paper to a vendor / freelancer)</option><option value="partner">Partner</option><option value="nda">NDA party</option></select></div>
        <div><label class="f" for="uReg">Client / service region</label><input type="text" id="uReg" placeholder="USA, India, United Arab Emirates…"></div>
        <div><label class="f" for="uVal">Value</label><input type="number" id="uVal" min="0" step="any"></div>
        <div><label class="f" for="uCur">Currency</label><select id="uCur"><option>USD</option><option>INR</option><option>EUR</option></select></div>
        <div><label class="f" for="uDl">Client deadline</label><input type="date" id="uDl"></div>
        <div><label class="f" for="uDeal">Related deal (bundle)</label><select id="uDeal"><option value="">None</option>${Object.entries(S.meta.deals).map(([k, v]) => `<option value="${h(k)}">${h(v)}</option>`).join("")}</select></div>
        <fieldset style="grid-column:1/-1;border:1px solid var(--line);border-radius:8px;padding:10px 12px">
          <legend class="f" style="padding:0 4px">Required: was anything agreed outside this document (rate, scope, region, dates)?</legend>
          <label><input type="radio" name="inf" value="no"> No</label> &nbsp; <label><input type="radio" name="inf" value="yes"> Yes</label>
          <textarea id="uInfNote" placeholder="What was agreed, by whom, and when (e.g. 'Jay offered $72/hr on a call, Dhaval ok'd')" style="margin-top:8px;display:none"></textarea>
        </fieldset>
      </div>
      <div class="row" style="margin-top:14px"><button class="btn primary" type="submit">Upload and review</button><span id="upNote" class="muted" style="font-size:13px"></span></div>
      <p class="muted" style="font-size:12.5px;margin-bottom:0">Files that look like patient or bulk personal data are blocked: CounterSign reads contracts, not datasets. Scanned pages without a text layer are flagged as unreadable, never guessed.</p>
    </form>`;
  let payload = null;
  document.querySelectorAll("input[name=inf]").forEach((r) => r.onchange = () => { $("#uInfNote").style.display = r.value === "yes" && r.checked ? "block" : "none"; });
  $("#uFile").onchange = async () => {
    const f = $("#uFile").files[0]; if (!f) return;
    const buf = await f.arrayBuffer();
    let bin = ""; new Uint8Array(buf).forEach((b) => (bin += String.fromCharCode(b)));
    payload = { filename: f.name, data: btoa(bin) };
    try {
      const p = await post("/api/prefill", payload);
      $("#uCp").value = p.counterparty || ""; $("#uType").value = p.doc_type || ""; $("#uSide").value = p.side;
      if (p.value) $("#uVal").value = p.value;
      $("#uReg").value = p.entity_named === "Inc" ? "USA" : "";
      $("#upNote").textContent = `Pre-filled from ${p.clauses} clauses${p.entity_named ? " · entity named: AtliQ " + p.entity_named : ""}. Please confirm.` + (p.notes.length ? " " + p.notes.join("; ") : "");
    } catch (e) { toast(e.message, true); }
  };
  $("#upForm").onsubmit = async (e) => {
    e.preventDefault();
    if (!payload) return toast("Choose a file first", true);
    const inf = (document.querySelector("input[name=inf]:checked") || {}).value;
    const meta = { counterparty: $("#uCp").value, doc_type: $("#uType").value, side: $("#uSide").value, service_region: $("#uReg").value,
      value: $("#uVal").value, currency: $("#uCur").value, deadline: $("#uDl").value || null, deal: $("#uDeal").value || null, informal: inf, informal_note: $("#uInfNote").value };
    try {
      const r = await post("/api/upload", { ...payload, meta });
      if (r.phi_warning) toast("Warning: possible personal data detected - check the upload.", true);
      location.hash = "#/review/" + encodeURIComponent(r.id);
    } catch (err) { toast(err.message, true); }
  };
}

/* ------------------------------------------------------------------ audit log (FR-38) */
async function viewAudit() {
  const data = await api("/api/audit");
  app().innerHTML = `<h1>Audit log</h1><p class="muted" style="margin-top:0">Append-only: every review shown, quote verification, disposition, override reason, register confirmation, counsel pack and question - with who and when.</p>
    <div class="card tablewrap" style="padding:4px 6px"><table><thead><tr><th>When</th><th>Who</th><th>Event</th><th>Details</th></tr></thead><tbody>
    ${data.events.map((e) => { const { at, user, event, ...rest } = e; return `<tr><td class="mono" style="white-space:nowrap">${h(at.replace("T", " "))}</td><td>${h(user)}</td><td><b>${h(event.replace(/_/g, " "))}</b></td><td class="mono" style="font-size:12px">${h(JSON.stringify(rest))}</td></tr>`; }).join("") || `<tr><td colspan="4" class="muted">Nothing logged yet.</td></tr>`}
    </tbody></table></div>`;
}

/* ------------------------------------------------------------------ evals (PRD 11) and North Star */
async function viewEvals() {
  const m = await api("/api/metrics");
  app().innerHTML = `<div class="spread"><div><h1>Evals and metrics</h1><p class="muted" style="margin-top:0">The golden set from PRD section 11: must-catch recall, clean controls, groundedness, guardrails. Re-run before any change to a rule, prompt, model or principle.</p></div>
    <button class="btn primary" id="runEv">Run golden set</button></div>
    <div class="stats">
      <div class="stat"><b>${m.idr === null ? "-" : Math.round(m.idr * 100) + "%"}</b><span>Informed Decision Rate (${m.informed}/${m.decisions} decisions)</span></div>
      <div class="stat"><b>${m.dispositions}</b><span>dispositions recorded</span></div>
      <div class="stat"><b>${m.serious_accepted_as_exception}</b><span>Serious items accepted as logged exceptions</span></div>
      <div class="stat"><b>${m.feedback_answered}</b><span>"missed anything?" answered (${m.feedback_missed} yes)</span></div>
    </div>
    <div id="evOut" class="card"><p class="muted" style="margin:0">Press "Run golden set" to evaluate all 15 drafts, the register and the guardrails.</p></div>
    ${role() === "reviewer" ? `<p style="margin-top:18px"><button class="btn sm danger" id="resetBtn">Reset demo state</button> <span class="muted" style="font-size:12.5px">Clears dispositions and confirmations; the audit log is kept.</span></p>` : ""}`;
  $("#runEv").onclick = async () => {
    $("#evOut").innerHTML = `<p class="muted">Running…</p>`;
    const res = await api("/api/evals");
    const pass = res.results.filter((r) => r.passed).length;
    $("#evOut").innerHTML = `<h2>${pass} / ${res.results.length} passed</h2><div class="tablewrap"><table><thead><tr><th></th><th>ID</th><th>Scenario</th><th>Detail</th></tr></thead><tbody>
      ${res.results.map((r) => `<tr><td class="${r.passed ? "st-ok" : "st-bad"}">${r.passed ? "PASS" : "FAIL"}</td><td class="mono">${h(r.id)}</td><td>${h(r.scenario)}</td><td class="mono" style="font-size:12px">${h(r.detail)}</td></tr>`).join("")}</tbody></table></div>`;
  };
  if ($("#resetBtn")) $("#resetBtn").onclick = async () => { if (!confirm("Reset all dispositions, decisions and confirmations?")) return; await post("/api/reset", {}); toast("Demo state reset."); viewEvals(); };
}

boot();
