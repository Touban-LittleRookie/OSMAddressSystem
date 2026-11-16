"""Who lives in each surveyed building: the name printed on the plaque, and the private contact used to inform a family.

Read from the EFYL admin export (``efyl_admin_export_*.csv``) and kept in ``input/households.csv`` of the project, never in
the database or in git. A survey row is the building whose id ends with ``<address_id>|<created_at>`` (the app's building id
is ``<device>|<address_id>|<created_at>``).

The plaque shows the family name; a building without one (a shop, a school, a house nobody answered at) shows the name of the
business or public place when the survey has it, otherwise nothing (``name_missing``). Phone numbers and contact names are
private: only administrators see them, and they are never printed or put in the QR code.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

KEEP = ["address_id", "created_at", "family_name", "contact_name", "contact_phone", "commerce_name", "commerce_phone", "public_name",
        "public_phone", "heritage_name", "survey_type", "persons_count"]
PRIVATE = {"contact_name", "contact_phone", "commerce_phone", "public_phone"}
FILE = "households.csv"


def _clean(v) -> str:
    return " ".join(str(v or "").split())


def import_export(source: Path, project_root: Path) -> dict:
    """Copy the columns the app needs from a survey export into ``input/households.csv``.

    Args:
        source: The EFYL admin export (CSV, UTF-8).
        project_root: Project folder.

    Returns:
        ``{"rows": n, "family_names": n}``.
    """
    text = Path(source).read_text(encoding="utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    missing = [c for c in ("address_id", "created_at", "family_name") if rows and c not in rows[0]]
    if missing:
        raise ValueError(f"{source} has no column {', '.join(missing)}: is it an EFYL admin export?")
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=KEEP)
    w.writeheader()
    for r in rows:
        w.writerow({k: _clean(r.get(k)) for k in KEEP})
    dest = Path(project_root) / "input" / FILE
    dest.write_text(out.getvalue(), encoding="utf-8")
    return {"rows": len(rows), "family_names": sum(1 for r in rows if _clean(r.get("family_name")))}


def load(project_root: Path) -> dict:
    """``{"<address_id>|<created_at>": row}`` from ``input/households.csv`` (empty when the project has none)."""
    path = Path(project_root) / "input" / FILE
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    table = {f"{r['address_id']}|{r['created_at']}": r for r in rows}
    once = {}
    for r in rows:                                           # a building id that is just the address id (other projects)
        once.setdefault(r["address_id"], []).append(r)
    table.update({f"#{k}": v[0] for k, v in once.items() if len(v) == 1})
    return table


def for_building(table: dict, building_id) -> dict | None:
    """The survey row of an app building id (``dev01|TCH-A001-X001|2026-08-17T09:00:00+00:00``, or just an address id)."""
    parts = str(building_id).split("|", 1)
    return table.get(parts[1]) if len(parts) == 2 else table.get(f"#{building_id}")


def plaque_name(row: dict | None, place_name=None) -> str | None:
    """The name printed on the plaque: the family name, else the business or public place name, else None."""
    for v in ([row.get("family_name"), row.get("commerce_name"), row.get("public_name"), row.get("heritage_name")] if row else []) + [place_name]:
        v = _clean(v) if isinstance(v, str) else ""
        if re.search(r"[^\W\d_]{2}", v):                            # survey fillers such as "0", "O" or "000" are not names
            return v
    return None


def public_view(row: dict | None) -> dict:
    """The fields every member may see (no phone, no contact name)."""
    return {k: v for k, v in (row or {}).items() if k not in PRIVATE}
