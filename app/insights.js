/* SelfSense — Insights tab (forecasting & analytics layer).
 * Reads the static forecasts.json published by the ML pipeline (no backend needed).
 * The FastAPI service in /api serves the same results; this page does not depend on it.
 * Uses globals from index.html: DB, purchaseRows, renderPurchaseGrid, renderAll,
 * showScreen, saveToLocalStorage, toast, escapeHtml, fmtMoney, getProduct.
 * All data is SYNTHETIC.
 */
(function () {
  "use strict";
  let INS = null;
  let selKind = "category", selKey = null;
  const $ = (id) => document.getElementById(id);
  const esc = (s) => (typeof escapeHtml === "function" ? escapeHtml(String(s)) : String(s));
  const pct = (x) => (x == null || isNaN(x) ? "—" : (x * 100).toFixed(1) + "%");

  async function loadDemoData(silent) {
    try {
      const r = await fetch("data/demo_db.json", { cache: "no-store" });
      if (!r.ok) throw new Error(r.status);
      DB = await r.json();
      saveToLocalStorage();
      localStorage.setItem("selfsenseDemoLoaded", "1");
      renderAll();
      if (!silent) toast("Synthetic demo data loaded", "ok");
    } catch (e) {
      console.warn("demo data load failed", e);
      if (!silent) toast("Could not load demo data", "err");
    }
  }
  window.selfsenseLoadDemoData = loadDemoData;

  async function loadInsights() {
    const r = await fetch("forecasts.json", { cache: "no-store" });
    if (!r.ok) throw new Error("forecasts.json " + r.status);
    INS = await r.json();
    if (!selKey) selKey = INS.category_forecast[0].category;
  }

  // SVG chart in the app's existing style: history line, forecast line, shaded 80% interval
  function svgForecastChart(hDates, hVals, fDates, yhat, lo, hi, width, height) {
    const padL = 44, padR = 14, padT = 14, padB = 32;
    const labels = hDates.concat(fDates), n = labels.length;
    const innerW = width - padL - padR, innerH = height - padT - padB;
    const maxV = Math.max(1, ...hVals, ...hi, ...yhat);
    const xOf = (i) => padL + (n > 1 ? (i * innerW) / (n - 1) : 0);
    const yOf = (v) => padT + innerH - (v / maxV) * innerH;
    let s = `<svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img" aria-label="forecast chart">`;
    for (let g = 0; g <= 4; g++) {
      const v = (maxV * g) / 4, y = yOf(v);
      s += `<line x1="${padL}" y1="${y}" x2="${width - padR}" y2="${y}" stroke="#e6dcd0"/>`;
      s += `<text x="${padL - 6}" y="${y + 4}" text-anchor="end" font-size="10" fill="#6b615c">${Math.round(v)}</text>`;
    }
    const every = Math.ceil(n / 8);
    labels.forEach((d, i) => {
      if (i % every === 0 || i === n - 1)
        s += `<text x="${xOf(i)}" y="${height - 10}" text-anchor="middle" font-size="10" fill="#6b615c">${d.slice(5)}</text>`;
    });
    const off = hDates.length;
    const band = fDates.map((_, j) => `${xOf(off + j)},${yOf(hi[j])}`).join(" ") + " " +
      fDates.map((_, j) => `${xOf(off + fDates.length - 1 - j)},${yOf(lo[fDates.length - 1 - j])}`).join(" ");
    s += `<polygon points="${band}" fill="#c9971c" fill-opacity="0.22" stroke="none"><title>80% interval</title></polygon>`;
    s += `<line x1="${xOf(off - 0.5)}" y1="${padT}" x2="${xOf(off - 0.5)}" y2="${padT + innerH}" stroke="#6b615c" stroke-dasharray="4 4"/>`;
    s += `<polyline points="${hVals.map((v, i) => `${xOf(i)},${yOf(v)}`).join(" ")}" fill="none" stroke="#7b1e3a" stroke-width="2.2"/>`;
    s += `<polyline points="${yhat.map((v, j) => `${xOf(off + j)},${yOf(v)}`).join(" ")}" fill="none" stroke="#b9770e" stroke-width="2.4" stroke-dasharray="6 3"/>`;
    yhat.forEach((v, j) => {
      s += `<circle cx="${xOf(off + j)}" cy="${yOf(v)}" r="3" fill="#b9770e"><title>${fDates[j]}: forecast ${v.toFixed(1)} (80%: ${lo[j].toFixed(1)}–${hi[j].toFixed(1)})</title></circle>`;
    });
    hVals.forEach((v, i) => {
      s += `<circle cx="${xOf(i)}" cy="${yOf(v)}" r="2.4" fill="#7b1e3a"><title>${hDates[i]}: sold ${v}</title></circle>`;
    });
    return s + "</svg>";
  }

  function chartBlock() {
    let h, f, title;
    if (selKind === "category") {
      const c = INS.category_forecast.find((x) => x.category === selKey) || INS.category_forecast[0];
      h = c.history; f = { dates: c.dates, yhat: c.yhat, lo: c.lo_sum, hi: c.hi_sum };
      title = `Category ${esc(c.category)} · model: ${esc(c.model)} · band = sum of product intervals (conservative)`;
    } else {
      const p = INS.products.find((x) => String(x.productId) === String(selKey)) || INS.products[0];
      h = p.history; f = p.forecast;
      title = `${esc(p.name)} · model: ${esc(p.model)} · 80% interval`;
    }
    return `<p class="help">${title}</p>` +
      `<div class="table-wrap" style="padding:8px;">${svgForecastChart(h.dates, h.units, f.dates, f.yhat, f.lo, f.hi, 760, 260)}</div>` +
      `<p class="help"><span style="color:#7b1e3a;">━ units sold (last 6 weeks)</span> &nbsp; <span style="color:#b9770e;">╍ forecast next ${INS.meta.horizon_days} days</span> &nbsp; <span style="background:#f3e3bd;padding:0 6px;">80% interval</span></p>`;
  }

  function prefillPurchase(supplierId) {
    const rows = INS.reorder_suggestions.filter((s) => s.suggested_qty > 0 && String(s.supplierId) === String(supplierId));
    const mapped = [];
    rows.forEach((s) => {
      const p = getProduct(s.productId) || DB.products.find((x) => x.name === s.productName);
      if (!p) return;
      mapped.push({ productId: p.id, productName: p.name, category: p.category, barcode: p.barcode || "",
        qty: String(s.suggested_qty), rate: String(p.costPrice), amount: (s.suggested_qty * p.costPrice).toFixed(2) });
    });
    if (!mapped.length) { toast("These products aren't in the loaded data — load the synthetic demo data first", "err"); return; }
    purchaseRows = mapped.concat([blankPurchaseRow()]);
    showScreen("purchase");
    const sel = $("purchaseSupplier");
    if (sel) sel.value = String(supplierId);
    renderPurchaseGrid();
    toast(`Pre-filled ${mapped.length} rows — review and save the voucher yourself`, "ok");
  }
  window.selfsensePrefill = prefillPurchase;

  function render() {
    const root = $("insightsRoot");
    if (!INS) { root.innerHTML = '<p class="help">Insights not available.</p>'; return; }
    const m = INS.model_info, mon = INS.monitoring, q = INS.quality;
    const imp = 1 - m.holdout_wape_selected / m.holdout_wape_seasonal_naive;
    const supName = (id) => { const s = (DB.suppliers || []).find((x) => String(x.id) === String(id)); return s ? s.name : "Supplier " + id; };
    const need = INS.reorder_suggestions.filter((s) => s.suggested_qty > 0);
    const bySup = {};
    need.forEach((s) => { (bySup[s.supplierId] = bySup[s.supplierId] || []).push(s); });

    let h = `<h1>🔮 Insights <span class="tag tag-med" style="vertical-align:middle;">SYNTHETIC DATA</span></h1>
    <div class="banner info"><div style="flex:1;">Forecasts and checks below come from the offline ML pipeline (published as <code>forecasts.json</code>, data as of <b>${esc(INS.meta.as_of)}</b>). They describe the synthetic demo dataset — reload it if you changed the data.</div>
      <button class="btn btn-flat btn-sm" onclick="selfsenseLoadDemoData()">↺ Reload synthetic demo data</button></div>
    <div class="cards">
      <div class="card"><div class="label">Model version</div><div class="value" style="font-size:1.05rem;">${esc(m.version)}</div><div class="sub">trained through ${esc(m.trained_through)} · ${m.registry_versions} versions in registry</div></div>
      <div class="card good"><div class="label">Holdout WAPE (selected)</div><div class="value">${pct(m.holdout_wape_selected)}</div><div class="sub">seasonal-naive baseline ${pct(m.holdout_wape_seasonal_naive)} · ${(imp * 100).toFixed(0)}% lower error</div></div>
      <div class="card"><div class="label">80% interval coverage</div><div class="value">${pct(m.holdout_coverage_80)}</div><div class="sub">share of holdout days inside the band</div></div>
      <div class="card ${mon.drift.alert ? "bad" : "good"}"><div class="label">Drift check</div><div class="value" style="font-size:1.2rem;">${mon.drift.alert ? "⚠️ Alert" : "✓ OK"}</div><div class="sub">mean shift ${pct(mon.drift.mean_shift)} · KS p=${mon.drift.ks_pvalue}</div></div>
    </div>
    <div class="section-title"><h2>📝 Owner's weekly brief</h2></div>
    <div class="banner ok">${esc(INS.brief.text)}<div class="help" style="margin-top:6px;">source: ${esc(INS.brief.source)}${INS.brief.llm && INS.brief.llm.used ? ` · ${INS.brief.llm.latency_ms} ms` : " (template — no LLM call)"}</div></div>

    <div class="section-title"><h2>📈 Demand forecast</h2></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px;">
      <select id="insKind" style="padding:8px;border-radius:8px;"><option value="category">By category</option><option value="product">By product</option></select>
      <select id="insKey" style="padding:8px;border-radius:8px;min-width:220px;"></select>
    </div>
    <div id="insChart">${chartBlock()}</div>

    <div class="section-title"><h2>🛒 Reorder suggestions</h2></div>
    <p class="help">Reorder point = forecast demand over lead time + 1 day, plus safety stock from forecast error (95% service level); order up to 7 more days of forecast demand. "Fixed rule" = the app's current reorderLevel check.</p>`;
    if (!need.length) h += `<p class="help">No product is at or below its reorder point today.</p>`;
    Object.keys(bySup).forEach((sid) => {
      h += `<h3 style="margin:14px 0 6px;">${esc(supName(sid))}</h3>
      <div class="table-wrap"><table><thead><tr><th>Product</th><th>Stock</th><th>Days of cover</th><th>Reorder point</th><th>Suggested qty</th><th>Fixed rule would order?</th></tr></thead><tbody>` +
        bySup[sid].map((s) => `<tr><td>${esc(s.productName)}</td><td>${s.current_stock}</td><td>${s.days_of_cover ?? "—"}</td><td>${s.reorder_point}</td><td><b>${s.suggested_qty}</b></td><td>${s.fixed_rule_would_order ? '<span class="tag tag-ok">yes</span>' : '<span class="tag tag-low">no</span>'}</td></tr>`).join("") +
        `</tbody></table></div><button class="btn btn-gold btn-sm" style="margin-top:6px;" onclick="selfsensePrefill('${esc(sid)}')">📋 Pre-fill purchase grid for this supplier</button>`;
    });

    h += `<div class="section-title"><h2>🧪 Data-quality alerts</h2></div><div class="stat-strip">` +
      Object.entries(q.counts).map(([k, v]) => `<div class="stat-chip ${v ? "bad" : ""}"><div class="l">${esc(k.replace(/_/g, " "))}</div><div class="v">${v}</div></div>`).join("") + `</div>`;
    const alertList = Object.entries(q.alerts).flatMap(([k, arr]) => arr.slice(-3).map((a) => `<li><span class="tag tag-cat">${esc(k.replace(/_/g, " "))}</span> ${esc(a)}</li>`));
    h += `<ul style="font-size:0.9rem;line-height:1.6;">${alertList.join("")}</ul>
    <details><summary class="help">Check accuracy vs planted anomalies (precision / recall)</summary><div class="table-wrap"><table><thead><tr><th>Check</th><th>Planted</th><th>Flagged</th><th>Precision</th><th>Recall</th></tr></thead><tbody>` +
      q.scores.map((s) => `<tr><td>${esc(s.check)}</td><td>${s.planted}</td><td>${s.flagged}</td><td>${pct(s.precision)}</td><td>${pct(s.recall)}</td></tr>`).join("") + `</tbody></table></div></details>`;

    h += `<div class="section-title"><h2>📡 Model monitoring</h2></div>
    <p class="help">Each weekly retrain scores the previously published forecast against the days that have since arrived.</p>
    <div class="table-wrap"><table><thead><tr><th>Forecast made</th><th>Scored through</th><th>Model</th><th>Live WAPE</th><th>Holdout WAPE at training</th></tr></thead><tbody>` +
      (mon.history.length ? mon.history.map((x) => `<tr><td>${esc(x.forecast_made_at)}</td><td>${esc(x.scored_through)}</td><td>${esc(x.model_version)}</td><td>${pct(x.live_wape)}</td><td>${pct(x.holdout_wape_of_model)}</td></tr>`).join("")
        : `<tr><td colspan="5">No live scores yet.</td></tr>`) + `</tbody></table></div>
    <p class="help">Drift rule: ${esc(mon.drift.rule)}. Recent ${mon.drift.recent_window_days}-day mean ${mon.drift.recent_mean_daily_units} units/day vs training ${mon.drift.training_mean_daily_units}.</p>
    <details><summary class="help">All models on the holdout</summary><div class="table-wrap"><table><thead><tr><th>Model</th><th>WAPE</th><th>MASE</th><th>Bias</th><th>80% coverage</th></tr></thead><tbody>` +
      m.holdout_overall.map((r) => `<tr><td>${esc(r.model)}</td><td>${pct(r.wape)}</td><td>${r.mase.toFixed(3)}</td><td>${pct(r.bias)}</td><td>${pct(r.coverage_80)}</td></tr>`).join("") +
      `</tbody></table></div></details>`;
    root.innerHTML = h;

    const kind = $("insKind"), key = $("insKey");
    kind.value = selKind;
    const fillKeys = () => {
      key.innerHTML = selKind === "category"
        ? INS.category_forecast.map((c) => `<option value="${esc(c.category)}">${esc(c.category)}</option>`).join("")
        : INS.products.map((p) => `<option value="${p.productId}">${esc(p.name)}</option>`).join("");
      key.value = selKey;
      if (key.selectedIndex < 0) { key.selectedIndex = 0; selKey = key.value; }
    };
    fillKeys();
    kind.onchange = () => { selKind = kind.value; selKey = null; fillKeys(); selKey = key.value; $("insChart").innerHTML = chartBlock(); };
    key.onchange = () => { selKey = key.value; $("insChart").innerHTML = chartBlock(); };
  }

  async function renderInsights() {
    try { if (!INS) await loadInsights(); render(); }
    catch (e) { console.warn(e); $("insightsRoot").innerHTML = '<p class="help">Could not load forecasts.json.</p>'; }
  }
  window.renderInsights = renderInsights;

  document.querySelectorAll('.navbtn[data-screen="insights"]').forEach((b) => b.addEventListener("click", renderInsights));
  // First visit: replace the app's 4-product sample with the synthetic demo dataset
  if (!localStorage.getItem("selfsenseDemoLoaded")) loadDemoData(true);
})();
