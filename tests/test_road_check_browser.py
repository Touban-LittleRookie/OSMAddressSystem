"""The road check in a browser: list in the Edit streets tab, zoom to a problem, mark it OK as is."""

import json
import os
import urllib.request

import pytest
from shapely.geometry import Point

import app_helpers as H
from test_app_frontend import live_app, playwright_sync_api, wait_for  # noqa: F401  (pytest fixture)


def _post(url, path, body):
    req = urllib.request.Request(url + "/api" + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))


def test_the_road_check_lists_zooms_and_marks_ok_in_a_browser(live_app):  # noqa: F811
    url, _root = live_app
    lon, lat = H.lonlat(H.X0 + 120, H.Y0 + 120)
    _post(url, "/reference", {"lat": lat, "lon": lon})
    _post(url, "/roads/draw", {"coords": [list(H.lonlat(H.X0 + 60, H.Y0 + 30)), list(H.lonlat(H.X0 + 60, H.Y0 + 116))],
                               "start": {"type": "none"}, "end": {"type": "none"}})          # stops 4 m from a street: a gap
    try:
        pw = playwright_sync_api.sync_playwright().start()
        browser = H.launch_browser(pw)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"no Chromium available: {exc}")
    try:
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.goto(url)
        page.wait_for_selector("#ref-confirm")
        page.click("#ref-confirm")
        page.click("#tabs button[data-tab=roads]")
        page.click("[data-act=check-run]")
        wait_for(page, "S.check && S.check.counts.gap === 1")
        assert "Gaps" in page.locator("details[data-sec=check]").inner_text()
        assert page.evaluate("G.check.getLayers().length") > 0                                  # markers on the map
        # the panel is drawn again when the map layers finish loading: click until the click lands on the current list
        wait_for(page, "(() => { const row = document.querySelector('details[data-sec=check] tr[data-act=check-zoom]'); if (row) row.click(); return S.checkFocus; })()")
        wait_for(page, "map.getZoom() >= 17 && G.hl.getLayers().length > 0")
        if os.environ.get("ROAD_CHECK_SHOT"):
            page.screenshot(path=os.environ["ROAD_CHECK_SHOT"])
        page.evaluate("document.querySelector('details[data-sec=check] button[data-act=check-ok]').click()")
        wait_for(page, "S.check && S.check.ok === 1")
    finally:
        browser.close()
        pw.stop()
