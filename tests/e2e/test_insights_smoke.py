"""Playwright smoke tests of the demo app + Insights tab.

Run with:  RUN_E2E=1 pytest tests/e2e -q
Needs:     python -m playwright install chromium
If the SheetJS CDN is unreachable (sandboxed env), set XLSX_LOCAL=/path/to/xlsx.full.min.js.
"""
import functools
import http.server
import json
import os
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"
pytestmark = pytest.mark.skipif(os.environ.get("RUN_E2E") != "1", reason="set RUN_E2E=1 to run browser tests")
BLOCKED_HOSTS = ("googleapis.com", "accounts.google.com", "gstatic.com", "firebase", "telegram.org")


@pytest.fixture(scope="module")
def server():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(APP))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture()
def page(server):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 900}, service_workers="block")
        pg = ctx.new_page()
        pg.external_requests = []
        local = os.environ.get("XLSX_LOCAL")
        if local:
            pg.route("**/xlsx.full.min.js", lambda r: r.fulfill(path=local, content_type="application/javascript"))

        def on_request(req):
            if any(h in req.url for h in BLOCKED_HOSTS):
                pg.external_requests.append(req.url)
        pg.on("request", on_request)
        pg.errors = []
        pg.on("pageerror", lambda e: pg.errors.append(str(e)))
        pg.goto(server + "/index.html")
        pg.wait_for_function("DB && DB.products && DB.products.length === 16", timeout=15000)
        yield pg
        browser.close()


def test_demo_loads_synthetic_data_and_integrations_are_off(page):
    assert "SYNTHETIC" in page.inner_text("#demoBanner")
    assert page.evaluate("DEMO_MODE") is True
    assert page.evaluate("sendTelegramMessage('x')") is False
    assert page.evaluate("initFirebaseIfNeeded()") is False
    assert page.evaluate("DB.settings.telegramBotToken + DB.settings.firebaseConfigJson + DB.settings.gdriveClientId") == ""
    page.wait_for_timeout(1500)
    assert page.external_requests == []
    assert page.errors == []


def test_insights_tab_renders(page):
    page.click('.navbtn[data-screen="insights"]')
    page.wait_for_selector("#insChart svg")
    txt = page.inner_text("#insightsRoot")
    assert "Model version" in txt and "SYNTHETIC" in txt
    page.select_option("#insKind", "product")
    page.wait_for_selector("#insChart svg")
    assert page.external_requests == []


def test_reorder_prefills_purchase_grid(page):
    page.click('.navbtn[data-screen="insights"]')
    page.wait_for_selector("#insChart svg")
    btns = page.locator("text=Pre-fill purchase grid")
    if btns.count() == 0:
        pytest.skip("no reorder needed in the published snapshot")
    btns.first.click()
    assert page.evaluate("document.getElementById('screen-purchase').classList.contains('active')")
    assert page.evaluate("purchaseRows.filter(r=>r.productId).length") >= 1


def test_existing_excel_import_reads_generated_workbook(page):
    xlsx = APP / "data" / "demo_db.xlsx"
    expected = json.loads((APP / "data" / "demo_db.json").read_text())
    page.evaluate("DB.sales = []; DB.products = DB.products.slice(0,1)")
    page.set_input_files("#fileInput", str(xlsx))
    page.wait_for_function(f"DB.sales.length === {len(expected['sales'])}", timeout=20000)
    assert page.evaluate("DB.products.length") == len(expected["products"])
    assert page.evaluate("DB.stockLedger.length") == len(expected["stockLedger"])
    assert page.errors == []
