"""Addresses in the "plaque d'immatriculation" format decided on 15 November 2026 (``docs/requirements.md``).

``TCK 0575 0230`` reads: quartier trigram ``TCK``, street ``0575`` (its number on four digits, or its four-letter code once
the street has an official name: ``KUET``), house ``0230`` (metres along the street on four digits, even on the right and odd
on the left, with a letter when two houses share a number: ``0230A``).

A *ruelle* (a street with a derived name, ``Voie 447 du Boulevard Fo KUETCHONG``) has no street number of its own: it is
written as the street it leaves, preceded in brackets by where it leaves it, the distance from the start of that street
divided by 10 and ``D`` or ``G`` for the side it leaves on (``(447D)KUET``: 4,470 m along KUET, to the right). A ruelle of a
ruelle adds its own position after a dash: ``(447D-012G)KUET``. The houses of a ruelle are numbered along the ruelle.
Two ruelles that would get the same position on the same side of the same street take the next free number (``448D``).
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

from . import work_areas

# Official four-letter codes of the streets named after the chiefs (``Overview Abbreviations.xlsx``, sheet "Chiefs").
CHIEF_QUADRIGRAMS = [
    ("KUETCHONG", "KUET"), ("KEKUEKA", "KEKU"), ("KEPANTANG", "KEPA"), ("NADOMDONG", "NADO"), ("NGOUENETH", "NGOU"),
    ("FOYET", "FOYE"), ("NGANKAM", "NGAN"), ("NGOMSEU", "NGOM"), ("KAMGANG", "KAMG"), ("FONDJO (2)", "FON2"),
    ("FONDJO", "FON1"), ("TEMDEMNOU", "TEMD"),
]
_GENERIC = {"BOULEVARD", "AVENUE", "RUE", "ROUTE", "PLACE", "PISTE", "VOIE", "RUELLE", "CHEMIN", "ALLEE", "IMPASSE", "CARREFOUR",
            "DE", "DU", "DES", "LA", "LE", "LES", "L", "D", "ET", "FO", "CHEFFERIE", "MARCHE", "QUARTIER"}


def _plain(text: str) -> str:
    """Upper case without accents, letters, digits, brackets and spaces only."""
    t = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9() ]+", " ", t)


def quadrigram(name: str) -> str | None:
    """The four-letter code of a named street: the code written at the end of the name (``... - FON2``), else the official chief
    code when the name holds a chief's name, otherwise the first four letters of the first word that is not generic
    (``Rue du Marché Tchisso`` -> ``TCHI``).

    Args:
        name: Street name.

    Returns:
        The code, or None for a name with no usable word.
    """
    base = re.sub(r"\s*\(([B-Z])\)\s*$", "", str(name)).strip()   # "(B)", "(C)": parts of a cut street keep the street's code
    given = re.search(r"\s-\s*([A-Z0-9]{4})$", base)             # the name already ends with its code: "Boulevard Fo FONDJO II D. - FON2"
    if given:
        return given.group(1)
    base = _plain(base)
    for chief, code in CHIEF_QUADRIGRAMS:
        if re.search(rf"\b{re.escape(chief)}(?=\W|$)", base):
            return code
    for word in re.findall(r"[A-Z]+", base):
        if word not in _GENERIC and len(word) >= 2:
            return (word + "XXXX")[:4]
    return None


# Settlements of Overview Abbreviations marked "not Fotouni": they are not Fotouni work areas, but a surveyed house there still
# gets the official trigram in its address.
OTHER_SETTLEMENTS = {"Balem": "BLE", "Baleng": "BLN", "Bamekoup": "BMK", "Bandum": "BDM", "Bangam": "BGM", "Demkwouo": "DMK", "Demkwo": "DMK",
                     "Kagme": "KGM", "Kamgang": "KMG", "Mboua": "MBU", "Mfeu": "MFE", "Ndoghem": "NDG", "Pouomgne": "PMG", "Saa": "SAA",
                     "Tchidje": "TCJ", "Tchitchap": "TCP", "Tse'e": "TSE", "Tse'e (Tchue)": "TSE", "Tchue": "TSE"}


def quartier_trigram(district) -> str | None:
    """Trigram of a surveyed quartier name (``Tchikwong`` -> ``TCK``, ``Demkwouo`` -> ``DMK``), None when not in the list."""
    if not isinstance(district, str) or not district.strip():
        return None
    entry = work_areas.fotouni_catalog()["lookup"].get(work_areas._name_key(district))
    if entry:
        return entry["code"]
    other = {work_areas._name_key(k): v for k, v in OTHER_SETTLEMENTS.items()}
    return other.get(work_areas._name_key(district))


def house_token(number) -> str | None:
    """``230A`` -> ``0230A`` (four digits, then the letter)."""
    if number is None or (isinstance(number, float) and number != number):
        return None
    m = re.match(r"^(\d+)([A-Z]*)$", str(number).strip())
    return f"{int(m.group(1)):04d}{m.group(2)}" if m else None


def _known(v) -> bool:
    return v is not None and not (isinstance(v, float) and v != v)


def street_codes(streets: pd.DataFrame, step_m: float = 10.0) -> tuple[dict, list[dict]]:
    """The street part of the address for every street of the network.

    Args:
        streets: ``NetworkState.streets`` (``street_id``, ``street_name``, ``to_be_named`` and the ``branch_*`` columns).
        step_m: Metres per unit of a ruelle position (10: ``447`` is 4,470 m).

    Returns:
        ``(codes, warnings)``: ``{street_id: "KUET" | "0575" | "(447D)KUET"}`` for the streets that can carry addresses, and
        the problems found (two named streets with the same code).
    """
    s = streets.set_index("street_id")
    own: dict[int, str] = {}
    named_by_code: dict[str, list[int]] = {}
    for sid, r in s.iterrows():
        if _known(r.get("branch_parent_id")):
            continue
        name = r.get("street_name")
        if isinstance(name, str) and name.strip() and not name.strip().isdigit():
            q = quadrigram(name)
            if q:
                own[int(sid)] = q
                base = re.sub(r"\s*\([B-Z]\)\s*$", "", name.strip())
                named_by_code.setdefault(q, [])
                if base not in [n for n, _ in named_by_code[q]]:
                    named_by_code[q].append((base, int(sid)))
                continue
        own[int(sid)] = f"{int(sid):04d}"                     # no official name: the street's number (never an invented name)
    # ruelle positions: per parent and side, in order along the parent; a taken position moves to the next free number
    pos: dict[int, str] = {}
    groups: dict[tuple, list] = {}
    for sid, r in s.iterrows():
        if _known(r.get("branch_parent_id")) and _known(r.get("branch_distance_m")):
            side = "G" if str(r.get("branch_side")) == "left" else "D"
            groups.setdefault((int(r["branch_parent_id"]), side), []).append((float(r["branch_distance_m"]), int(sid)))
    for (_p, side), items in groups.items():
        used: set[int] = set()
        for dist, sid in sorted(items):
            k = int(round(dist / step_m))
            while k in used:
                k += 1
            used.add(k)
            pos[sid] = f"{k:03d}{side}"
    codes = dict(own)
    for sid in pos:
        chain, cur, seen = [], sid, set()
        while cur in pos and cur not in seen:
            seen.add(cur)
            chain.append(pos[cur])
            cur = int(s.at[cur, "branch_parent_id"])
        if cur in own:
            codes[sid] = f"({'-'.join(reversed(chain))}){own[cur]}"
    warnings = [{"code": q, "streets": [n for n, _ in v], "street_ids": [i for _, i in v]} for q, v in named_by_code.items() if len(v) > 1]
    return codes, warnings


def plate_address(trigram: str | None, street_code: str | None, number) -> str | None:
    """``TCK (447D)KUET 0230``; None when a part is missing."""
    h = house_token(number)
    if not (trigram and street_code and h):
        return None
    return f"{trigram} {street_code} {h}"


def with_number(plate: str | None, number) -> str | None:
    """The same address with another house number (after a letter was added)."""
    h = house_token(number)
    if not plate or not h:
        return plate
    return plate.rsplit(" ", 1)[0] + " " + h


def add_plates(houses, streets: pd.DataFrame, step_m: float = 10.0) -> tuple[object, dict]:
    """Add ``quartier_code``, ``street_code`` and ``plate`` to computed houses.

    Args:
        houses: ``AddressState.houses`` (``district``, ``street_id``, ``number``).
        streets: ``NetworkState.streets``.
        step_m: See :func:`street_codes`.

    Returns:
        ``(houses copy, stats)`` with the counts of complete addresses, houses whose quartier is not in the catalogue, the same
        address given twice and named streets sharing a code.
    """
    h = houses.copy()
    codes, warnings = street_codes(streets, step_m)
    tri = [quartier_trigram(d) for d in (h["district"] if "district" in h.columns else [None] * len(h))]
    sc = [codes.get(int(s)) if _known(s) else None for s in h["street_id"]]
    h["quartier_code"], h["street_code"] = tri, sc
    h["plate"] = [plate_address(t, c, n) for t, c, n in zip(tri, sc, h["number"])]
    plates = [p for p in h["plate"] if p]
    dup = pd.Series(plates).value_counts()
    unknown = sorted({str(d) for d, t, n in zip(h.get("district", []), tri, h["number"]) if t is None and _known(n)})
    stats = {"plates": len(plates), "plates_missing_quartier": int(sum(1 for t, n in zip(tri, h["number"]) if t is None and _known(n))),
             "unknown_quartiers": unknown, "plates_twice": int((dup > 1).sum()), "street_code_conflicts": warnings}
    return h, stats
