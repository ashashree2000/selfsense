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
      if (!silent) toast("Sample data reset", "ok");
    } catch (e) {
      console.warn("demo data load failed", e);
      if (!silent) toast("Could not load sample data", "err");
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
    let s = `<svg viewBox="0 0 ${width} ${height}" width="100%" style="display:block;min-width:600px;height:auto;" role="img" aria-label="forecast chart">`;
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
    s += `<polygon points="${band}" fill="#c9971c" fill-opacity="0.22" stroke="none"><title>likely range</title></polygon>`;
    s += `<line x1="${xOf(off - 0.5)}" y1="${padT}" x2="${xOf(off - 0.5)}" y2="${padT + innerH}" stroke="#6b615c" stroke-dasharray="4 4"/>`;
    s += `<polyline points="${hVals.map((v, i) => `${xOf(i)},${yOf(v)}`).join(" ")}" fill="none" stroke="#7b1e3a" stroke-width="2.2"/>`;
    s += `<polyline points="${yhat.map((v, j) => `${xOf(off + j)},${yOf(v)}`).join(" ")}" fill="none" stroke="#b9770e" stroke-width="2.4" stroke-dasharray="6 3"/>`;
    yhat.forEach((v, j) => {
      s += `<circle cx="${xOf(off + j)}" cy="${yOf(v)}" r="3" fill="#b9770e"><title>${fDates[j]}: expected ${v.toFixed(1)} (likely ${lo[j].toFixed(1)}–${hi[j].toFixed(1)})</title></circle>`;
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
      title = `${esc(c.category)}`;
    } else {
      const p = INS.products.find((x) => String(x.productId) === String(selKey)) || INS.products[0];
      h = p.history; f = p.forecast;
      title = `${esc(p.name)}`;
    }
    return `<div class="table-wrap" style="padding:8px;">${svgForecastChart(h.dates, h.units, f.dates, f.yhat, f.lo, f.hi, 760, 260)}</div>` +
      `<p class="help"><span style="color:#7b1e3a;">━ sold</span> &nbsp; <span style="color:#b9770e;">╍ expected</span> &nbsp; <span style="background:#f3e3bd;padding:0 6px;">likely range</span></p>`;
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
    if (!mapped.length) { toast("Reset the sample data first", "err"); return; }
    purchaseRows = mapped.concat([blankPurchaseRow()]);
    showScreen("purchase");
    const sel = $("purchaseSupplier");
    if (sel) sel.value = String(supplierId);
    renderPurchaseGrid();
    toast(`Added ${mapped.length} items to the purchase order`, "ok");
  }
  window.selfsensePrefill = prefillPurchase;

  // Plain-language labels for the rule-based checks shown to the shop user.
  // (The statistical spike/drop flags are kept for analysis in reports/, not shown here.)
  const CHECKS = {
    duplicate_sale: "Sales entered twice",
    credit_sale_no_name: "Credit sales without a customer name",
    sale_at_zero_stock: "Sales recorded when stock was 0",
    ledger_balance_mismatch: "Stock register entries that don't add up",
    shrinkage: "Shelf count differs from records",
  };

  function render() {
    const root = $("insightsRoot");
    if (!INS) { root.innerHTML = '<p class="help">Insights not available.</p>'; return; }
    const q = INS.quality;
    const supName = (id) => { const s = (DB.suppliers || []).find((x) => String(x.id) === String(id)); return s ? s.name : "Supplier " + id; };
    const need = INS.reorder_suggestions.filter((s) => s.suggested_qty > 0);
    const bySup = {};
    need.forEach((s) => { (bySup[s.supplierId] = bySup[s.supplierId] || []).push(s); });
    const week = Math.round(INS.category_forecast.reduce((a, c) => a + c.yhat.slice(0, 7).reduce((x, y) => x + y, 0), 0));
    const issues = Object.keys(CHECKS).filter((k) => q.counts[k] > 0);
    const issueTotal = issues.reduce((a, k) => a + q.counts[k], 0);
    const fmtDay = (d) => new Date(d + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

    let h = `<h1>🔮 Insights</h1>
    <p class="help">Updated ${esc(fmtDay(INS.meta.as_of))} · <a href="#" onclick="selfsenseLoadDemoData();return false;">Reset sample data</a></p>
    <div class="cards">
      <div class="card"><div class="label">Expected sales, next 7 days</div><div class="value">${week.toLocaleString("en-IN")}</div><div class="sub">bottles</div></div>
      <div class="card ${need.length ? "bad" : "good"}"><div class="label">Items to reorder</div><div class="value">${need.length}</div><div class="sub">from ${Object.keys(bySup).length} ${Object.keys(bySup).length === 1 ? "supplier" : "suppliers"}</div></div>
      <div class="card ${issueTotal ? "bad" : "good"}"><div class="label">Records to check</div><div class="value">${issueTotal}</div><div class="sub">see below</div></div>
    </div>

    <div class="section-title"><h2>📈 Next 14 days</h2></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px;">
      <select id="insKind" style="padding:8px;border-radius:8px;"><option value="category">By category</option><option value="product">By product</option></select>
      <select id="insKey" style="padding:8px;border-radius:8px;min-width:220px;"></select>
    </div>
    <div id="insChart">${chartBlock()}</div>

    <div class="section-title"><h2>🛒 Reorder now</h2></div>`;
    if (!need.length) h += `<p class="help">Nothing to reorder today.</p>`;
    Object.keys(bySup).forEach((sid) => {
      h += `<h3 style="margin:14px 0 6px;">${esc(supName(sid))}</h3>
      <div class="table-wrap"><table><thead><tr><th>Product</th><th>In stock</th><th>Days left</th><th>Order</th></tr></thead><tbody>` +
        bySup[sid].map((s) => `<tr><td>${esc(s.productName)}</td><td>${s.current_stock}</td><td>${s.days_of_cover ?? "—"}</td><td><b>${s.suggested_qty}</b></td></tr>`).join("") +
        `</tbody></table></div><button class="btn btn-gold btn-sm" style="margin-top:6px;" onclick="selfsensePrefill('${esc(sid)}')">Fill purchase order</button>`;
    });

    h += `<div class="section-title"><h2>🧾 Records to check</h2></div>`;
    if (!issues.length) h += `<p class="help">No problems found in the records.</p>`;
    else h += `<div class="table-wrap"><table><thead><tr><th>Problem</th><th>Count</th><th>Latest example</th></tr></thead><tbody>` +
      issues.map((k) => { const ex = (q.alerts[k] || []).slice(-1)[0] || ""; return `<tr><td>${esc(CHECKS[k])}</td><td><b>${q.counts[k]}</b></td><td style="font-size:0.85rem;color:var(--muted);">${esc(ex)}</td></tr>`; }).join("") +
      `</tbody></table></div>`;
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
