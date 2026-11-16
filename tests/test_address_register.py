"""Tests of the address rules of 13 and 15 November: paths that give no addresses (230A, 230B), the register (a validated
address changes only through a validated change), the "plaque d'immatriculation" address (TCK (447D)KUET 0230), the plaque,
the address card and the survey households."""

import time

import geopandas as gpd
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Point

import app_helpers as H
from test_accounts import login, member, root, secured  # noqa: F401 - fixtures
from osmaddresssystem.app import engine, plaque
from osmaddresssystem.app.server import create_app
from osmaddresssystem.app.store import Store, address_code


def _wait(client, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get("/api/job").json()
        if j["state"] in ("done", "error"):
            return j
        time.sleep(0.1)
    raise AssertionError("job did not finish")


@pytest.fixture()
def client(tmp_path):
    """The synthetic grid plus two houses beside the second vertical street, 25 m and 50 m north of the first row."""
    root = H.make_project(tmp_path / "proj")
    b = gpd.read_file(root / "input" / "buildings.gpkg").to_crs(H.CRS)
    extra = gpd.GeoDataFrame({"building_id": ["P0", "P1"]}, geometry=[Point(H.X0 + 130, H.Y0 + 25), Point(H.X0 + 130, H.Y0 + 50)], crs=H.CRS)
    allb = pd.concat([b, extra], ignore_index=True).pipe(gpd.GeoDataFrame, crs=H.CRS)
    allb["district"] = "Tchikwong"                                    # a survey variant of Tchikong: trigram TCK
    allb.to_crs(4326).to_file(root / "input" / "buildings.gpkg")
    c = TestClient(create_app(root, auth_enabled=False, auto_compute=False))
    lon, lat = H.lonlat(H.X0 + 120, H.Y0 + 120)
    c.post("/api/reference", json={"lat": lat, "lon": lon})
    assert c.post("/api/compute").json()["started"] and _wait(c)["state"] == "done"
    h = _houses(c)                                                    # name the two streets: only complete addresses can be approved
    orig = {f["properties"]["id"]: f["properties"]["original"] for f in c.get("/api/network").json()["streets"]["features"]}
    for b, name in (("H0", "Rue A"), ("P0", "Rue B")):
        c.post("/api/names", json={"street_id": orig[h[b]["street_id"]], "name": name})
    assert c.post("/api/compute").json()["started"] and _wait(c)["state"] == "done"
    return c


def _houses(c):
    assert c.post("/api/addresses/compute").json()["started"] and _wait(c)["state"] == "done"
    return {f["properties"]["building_id"]: f["properties"] for f in c.get("/api/addresses").json()["houses"]["features"]}


def _path_street(c):
    lon, lat = H.lonlat(H.X0 + 120, H.Y0 + 30)
    sid = c.post("/api/access/snap", json={"lat": lat, "lon": lon}).json()["street_id"]
    f = next(f for f in c.get("/api/network").json()["streets"]["features"] if f["properties"]["id"] == sid)
    return sid, f["properties"]


def test_houses_on_a_path_that_gives_no_addresses_take_the_number_where_it_leaves_the_street(client):
    """Marked "gives no addresses", the path's houses take the number of its junction with a letter in walking order."""
    before = _houses(client)
    sid, props = _path_street(client)
    assert before["P0"]["street_id"] == sid and props["addresses"] is True
    client.post("/api/streets/attrs", json={"original": props["original"], **({"part": props["part"]} if props.get("part") else {}), "addresses": False})
    p = client.get("/api/project").json()
    assert p["stale"] is False and p["addresses_stale"] is True               # only the addresses depend on it
    assert next(f for f in client.get("/api/network").json()["streets"]["features"] if f["properties"]["id"] == sid)["properties"]["addresses"] is False
    h = _houses(client)
    p0, p1 = h["P0"], h["P1"]
    assert p0["via_path"] == sid and p1["via_path"] == sid and p0["side_source"] == "path"
    assert p0["street_id"] == p1["street_id"] != sid
    assert p0["number"][-1] == "A" and p1["number"][-1] == "B" and p0["number"][:-1] == p1["number"][:-1]   # A is nearer the street
    assert h["H0"]["address"] == before["H0"]["address"]                       # nobody else moves


def test_approved_addresses_are_frozen_and_changes_are_only_listed(client):
    """Approving freezes an address: a later change of the map is listed, not applied; codes are permanent and never reused."""
    before = _houses(client)
    r = client.post("/api/register/approve", json={"ids": ["P0", "P1", "FAR0"]}).json()
    assert r["approved"] == 2 and r["skipped"] == 1                             # FAR0 has no road: it cannot be approved
    reg = {x["building_id"]: x for x in client.get("/api/register").json()["rows"]}
    assert reg["P0"]["code"] != reg["P1"]["code"] and reg["P0"]["code"].startswith("FTN-") and reg["P0"]["address"] == before["P0"]["address"]
    sid, props = _path_street(client)
    client.post("/api/streets/attrs", json={"original": props["original"], **({"part": props["part"]} if props.get("part") else {}), "addresses": False})
    h = _houses(client)
    assert h["P0"]["address"] == before["P0"]["address"] and h["P0"]["register_status"] == "approved"
    assert h["P0"]["changed"] is True and h["P0"]["computed_address"] != before["P0"]["address"]
    assert {x["building_id"] for x in client.get("/api/register").json()["changed"]} == {"P0", "P1"}
    ch = client.get("/api/register/changes").json()
    assert ch["to_validate"] == 2 and all(r["before_plate"] and r["after_plate"] and r["before_plate"] != r["after_plate"] for r in ch["rows"])
    assert "contact_phone" not in ch["rows"][0]
    again = client.post("/api/register/approve", json={"ids": ["P0"]}).json()
    assert again["unchanged"] == 1                                              # approving again never changes it
    bad = client.post("/api/register/approve", json={"ids": ["P0"], "correct": True})
    assert bad.status_code == 400                                               # a correction needs a reason
    fixed = client.post("/api/register/approve", json={"ids": ["P0"], "correct": True, "reason": "path redrawn on the ground"}).json()
    assert fixed["corrected"] == 1
    reg2 = {x["building_id"]: x for x in client.get("/api/register").json()["rows"]}
    assert reg2["P0"]["code"] == reg["P0"]["code"] and [s_["action"] for s_ in reg2["P0"]["history"]] == ["approved", "corrected"]
    done = {(r["building_id"], r["state"]): r for r in client.get("/api/register/changes").json()["rows"]}
    assert done[("P0", "validated")]["reason"] == "path redrawn on the ground" and ("P1", "to_validate") in done
    assert client.post("/api/register/approve", json={"changed": True, "correct": True, "reason": "same path"}).json()["corrected"] == 1
    assert "before_plate" in client.get("/api/register/changes.csv").text.splitlines()[0]
    assert client.post("/api/register/retire", json={"ids": ["P1"]}).status_code == 400
    assert client.post("/api/register/retire", json={"ids": ["P1"], "reason": "demolished"}).json()["retired"] == 1
    assert client.get("/api/register.csv").text.count("FTN-") == 2


def test_the_plaque_has_the_quartier_the_family_name_and_the_address_and_a_draft_mark_until_validated(client):
    """Plaque (15 November): FOTOUNI · TCK, the family name, the address TCK ... ; no phone anywhere; a draft until validated."""
    root = client.app.state.ctx.store.project().root
    (root / "input" / "households.csv").write_text(
        "address_id,created_at,family_name,contact_name,contact_phone\nH0,x,Famille Test,Jean Test,699000000\n", encoding="utf-8")
    h = _houses(client)
    assert h["H0"]["plate"].startswith("TCK ") and h["H0"]["quartier_code"] == "TCK"
    draft = client.get("/api/plaque/H0.svg")
    assert draft.status_code == 200 and "BROUILLON" in draft.text
    client.post("/api/register/approve", json={"ids": ["H0"]})
    svg = client.get("/api/plaque/H0.svg").text
    assert "BROUILLON" not in svg and h["H0"]["plate"] in svg and "FOTOUNI · TCK" in svg and "FAMILLE TEST" in svg
    assert h["H0"]["plaque_name"] == "Famille Test"
    card = client.get("/api/card/H0.svg").text
    assert h["H0"]["plate"] in card and "CARTE" in card
    assert "699000000" not in svg + card and "Jean" not in svg + card


def test_a_corrected_quartier_changes_the_trigram_and_can_be_undone(client):
    """A house whose survey quartier is wrong gets the corrected trigram; only the addresses go stale; undo goes back."""
    before = _houses(client)
    assert client.post("/api/houses/quartier", json={"ids": ["H0"], "quartier": "Pas un quartier"}).status_code == 400
    assert client.post("/api/houses/quartier", json={"ids": ["H0"], "quartier": "Mving"}).status_code == 200
    p = client.get("/api/project").json()
    assert p["stale"] is False and p["addresses_stale"] is True
    h = _houses(client)
    assert h["H0"]["quartier_code"] == "MVI" and h["H0"]["plate"] == "MVI" + before["H0"]["plate"][3:] and h["H0"]["survey_district"] == "Tchikwong"
    assert h["H1"]["plate"] == before["H1"]["plate"]
    client.post("/api/undo", json={})
    assert _houses(client)["H0"]["plate"] == before["H0"]["plate"]


def test_household_names_join_the_survey_rows_and_contacts_stay_private(tmp_path):
    """The EFYL export joins on address id + time; the plaque name falls back to the business name; no phone in the public view."""
    from osmaddresssystem.app import households

    src = tmp_path / "export.csv"
    src.write_text("address_id,created_at,owner_id,family_name,contact_name,contact_phone,commerce_name\n"
                   "TCK-A001-X001,2026-08-17T09:00:00+00:00,guest,  Famille   Kamga ,Paul,690,\n"
                   "TCK-A001-X002,2026-08-17T09:05:00+00:00,guest,,Ana,691,Boutique Ana\n", encoding="utf-8")
    (tmp_path / "input").mkdir()
    assert households.import_export(src, tmp_path) == {"rows": 2, "family_names": 1}
    t = households.load(tmp_path)
    r1 = households.for_building(t, "dev01|TCK-A001-X001|2026-08-17T09:00:00+00:00")
    r2 = households.for_building(t, "dev02|TCK-A001-X002|2026-08-17T09:05:00+00:00")
    assert households.plaque_name(r1) == "Famille Kamga" and households.plaque_name(r2) == "Boutique Ana"
    assert "contact_phone" not in households.public_view(r1) and households.for_building(t, "nothing") is None


def test_only_administrators_see_the_contacts(secured):
    """Contacts (phones) and the list of families to inform are for administrators only."""
    login(secured)
    mapper, _ = member(secured, "mapper", "mapper")
    assert mapper.get("/api/households/dev01|X|Y").status_code == 403
    assert mapper.get("/api/register/changes.csv").status_code == 403
    assert secured.get("/api/households/dev01|X|Y").status_code == 404           # allowed, just no such record


def test_street_codes_quadrigrams_and_ruelle_positions():
    """Named street -> its four letters; unnamed -> its number on 4 digits; a ruelle -> (position/10 + D/G) then its main street."""
    from osmaddresssystem.app import plate

    nan = float("nan")
    streets = pd.DataFrame({
        "street_id": [575, 12, 20, 21, 22, 30, 40, 41],
        "street_name": ["Boulevard Fo KUETCHONG", None, None, None, None, None, "Rue Fo KUETCHONG", "Boulevard Fo KUETCHONG (B)"],
        "to_be_named": [False, True, False, False, False, False, False, False],
        "branch_parent_id": [nan, nan, 575, 575, 575, 20, nan, nan],
        "branch_distance_m": [nan, nan, 4470.0, 4472.0, 4468.0, 121.0, nan, nan],
        "branch_side": [None, None, "right", "right", "left", "left", None, None]})
    codes, warnings = plate.street_codes(streets)
    assert codes[575] == "KUET" and codes[12] == "0012"
    assert codes[20] == "(447D)KUET" and codes[21] == "(448D)KUET" and codes[22] == "(447G)KUET"   # same slot: the next free number
    assert codes[30] == "(447D-012G)KUET" and codes[41] == "KUET"                                 # a ruelle of a ruelle; a part keeps the code
    assert [w["code"] for w in warnings] == ["KUET"] and set(warnings[0]["street_ids"]) == {575, 40}  # two different streets share KUET
    assert plate.quadrigram("Fo FONDJO (2)") == "FON2" and plate.quadrigram("Rue du Marché Tchisso") == "TCHI"
    assert plate.quadrigram("Boulevard Fo FONDJO II D. - FON2") == "FON2" and plate.quadrigram("Boulevard Fo FONDJO - FON1 (B)") == "FON1"
    assert plate.plate_address("TCK", "(447D)KUET", "230A") == "TCK (447D)KUET 0230A" and plate.plate_address(None, "KUET", "2") is None
    assert plate.with_number("TCK 0575 0230", "230B") == "TCK 0575 0230B"
    assert plate.quartier_trigram("Tchikwong") == "TCK" and plate.quartier_trigram("Demkwo") == "DMK" and plate.quartier_trigram("Baving") == "MVI"


def test_a_number_taken_by_an_approved_address_is_never_given_again():
    """A new house that would get an approved (or retired) number on the same street takes the next free letter."""
    houses = gpd.GeoDataFrame({"building_id": ["a", "new"], "address": ["230, X", "230, X"], "number": ["230", "230"], "street_id": [7, 7],
                               "street": ["X", "X"]}, geometry=[Point(0, 0), Point(1, 1)], crs=4326)
    reg = {"a": {"status": "approved", "address": "230, X", "number": "230", "street_id": 7, "street": "X", "code": "FTN-000001-8"},
           "old": {"status": "retired", "address": "230A, X", "number": "230A", "street_id": 7, "street": "X", "code": "FTN-000002-6"}}
    out = engine.apply_register(houses, reg).set_index("building_id")
    assert out.loc["a", "address"] == "230, X" and out.loc["new", "number"] == "230B" and out.loc["new", "address"] == "230B, X"


def test_codes_have_a_check_digit_and_restoring_a_checkpoint_keeps_the_register(tmp_path):
    """Codes carry a Luhn digit; a checkpoint restore never takes back approvals; undo of the approval is possible."""
    assert address_code(1) == "FTN-000001-8" and address_code(1) != address_code(2)
    st = Store(tmp_path, "t")
    cp = st.save("before")
    st.approve_addresses({"b1": {"address": "2, X", "number": "2", "street": "X", "street_id": 1}}, "me")
    st.restore(cp, "me", reason="test restore")
    assert st.register()["b1"]["status"] == "approved"
    st.undo("me")                                                               # the restore
    st.undo("me")                                                               # the approval
    assert "b1" not in st.register()
    st.approve_addresses({"b1": {"address": "2, X", "number": "2", "street": "X", "street_id": 1}}, "me")
    assert st.register()["b1"]["code"] == address_code(2)                       # code 1 is never given again


def _read_qr(text):
    """Read a QR code back: unmask, walk the modules, split the blocks, check every block's error correction, decode the bytes."""
    m, fn, v = plaque._build(text)
    n = len(m)
    bits = []
    right = n - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(n):
            for j in range(2):
                x = right - j
                y = n - 1 - vert if ((right + 1) & 2) == 0 else vert
                if not fn[y][x]:
                    bits.append(int(m[y][x] != ((x + y) % 2 == 0)))
        right -= 2
    ec, groups = plaque._BLOCKS[v]
    sizes = [k for c, k in groups for _ in range(c)]
    total = sum(sizes) + ec * len(sizes)
    cw = [int("".join(map(str, bits[i * 8:i * 8 + 8])), 2) for i in range(total)]
    data = [[] for _ in sizes]
    it = iter(cw)
    for i in range(max(sizes)):
        for b, k in enumerate(sizes):
            if i < k:
                data[b].append(next(it))
    eccs = [[] for _ in sizes]
    for _ in range(ec):
        for b in range(len(sizes)):
            eccs[b].append(next(it))
    assert all(plaque._rs_ecc(d, ec) == e for d, e in zip(data, eccs))
    flat = [x for d in data for x in d]
    s = "".join(f"{x:08b}" for x in flat)
    assert s[:4] == "0100"
    length = int(s[4:12], 2)
    return v, bytes(int(s[12 + 8 * i:20 + 8 * i], 2) for i in range(length)).decode("utf-8")


def test_qr_codes_read_back_for_every_version_and_refuse_long_text():
    """Short and long texts (versions 1 to 9, one to five blocks) read back exactly; finders are in place; too long is refused."""
    full = plaque.qr_text("TCK (447D-012G)KUET 0230A", "FAMILLE NGUETCHUENG KAMGA TCHOUANGUEP", 5.27123, 10.22456, quartier="TCK")
    assert full.splitlines()[0] == "FOTOUNI · TCK" and "Famille : " in full and "GPS : 5.27123, 10.22456" in full
    for text in ["TCK 0575 0230", "x" * 40, "é" * 30, full, "y" * 150, "z" * 180]:
        v, back = _read_qr(text)
        assert back == text
    assert _read_qr("z" * 180)[0] == 9 and _read_qr(full)[0] >= 5
    m = plaque.qr_matrix(full)
    assert all(m[0][:7]) and all(m[0][-7:]) and all(m[-1][:7]) and not m[0][7]
    with pytest.raises(ValueError):
        plaque.qr_matrix("x" * 181)
    long_name = plaque.qr_text("TCK 0575 0230", "N" * 300, 5.0, 10.0, quartier="TCK")
    assert len(long_name.encode()) <= plaque.QR_MAX_BYTES and long_name.endswith("Adresse : TCK 0575 0230")
