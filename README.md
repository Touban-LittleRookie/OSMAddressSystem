# Community Addressing Cameroon

Give every house in a Cameroonian community a clear, printable address, starting from a field survey and the
OpenStreetMap road network. First pilot: **Fotouni** (West region), 2,127 surveyed houses, 58 work areas.

The project has two parts:

- **`osmaddresssystem`**, a Python package that turns a road network into an address system: street identities,
  street direction, house numbering, sub-street names, geocoding, sign maps.
- **The community address app**, a web app (FastAPI + Leaflet) in which a small trusted team reviews the roads, names
  the streets, checks every house and validates the addresses, with accounts, roles and a full undo history.

An address looks like a licence plate: **`TCK 0575 0230`**, meaning quartier `TCK`, street `0575` (or its 4-letter
code once named), house `0230`. Odd numbers are on the left of the street, even numbers on the right.

---

## Contents

1. [What the app does](#what-the-app-does)
2. [How it works](#how-it-works)
3. [Quick start](#quick-start)
4. [The review workflow](#the-review-workflow)
5. [Address and plaque format](#address-and-plaque-format)
6. [Repository layout](#repository-layout)
7. [Data and privacy](#data-and-privacy)
8. [Accounts and security](#accounts-and-security)
9. [Deployment](#deployment)
10. [Tests](#tests)
11. [Documentation](#documentation)
12. [Credits](#credits)
13. [Licence](#licence)

---

## What the app does

| Step in the app | What the team does there |
|---|---|
| **1 Edit streets** | Check every road on the satellite image, reshape it, draw missing paths, join and cut roads. |
| **2 Street types and IDs** | Set road rank, drivable and surface; see the street each road belongs to. |
| **3 Street names** | Enter names the community already uses. Unnamed streets keep their 4-digit number. |
| **4 Addresses** | See every house, its address and its road point; fix the quartier or the road point; validate addresses into the register; print plaques and cards. |

Around these steps:

- **Work areas**: the map is cut into 950 m squares (`R01C08`…), each with five review stages (roads, attributes,
  names, buildings, addresses), so progress can be tracked area by area.
- **History**: every change is one event with its author; undo / redo and named checkpoints.
- **Address register**: a validated address changes only through a validated correction, which records before and
  after. The list of changed addresses (with contacts, for administrators only) is what the team uses to inform
  families.
- **Search**: by address (`TCK 0575`), family name or survey id; a **Go to** box takes coordinates.
- **Exports**: streets (GeoPackage, CSV, KML), houses and addresses, reference points.

## How it works

```text
Browser  (static/index.html, app.js, i18n.js: Leaflet map, French / English)
   │  JSON over HTTP, session cookie + CSRF token
   ▼
FastAPI server  (osmaddresssystem/app/server.py, auth.py)
   │
   ├── Store  (store.py)  event log in SQLite or PostgreSQL: every edit is an event,
   │                      the project state is the replay of the events (undo = drop the last one)
   │
   └── Engine (engine.py) recomputes from base data + events:
         roads   → network (nodes, edges)   → streets (street_ids.py, branches.py)
         streets → numbering (path_numbering.py, numbering.py)
         houses  → nearest street or hand-chosen road point → number, side, address (plate.py)
         address → plaque / card SVG with QR code (plaque.py)
```

Base data of a project (folder `projects/<name>/input/`): the area boundary, `streets.osm` (OpenStreetMap roads),
`buildings.gpkg` (surveyed houses), `points.gpkg` (reference points), and the private `households.csv` (family names
and contacts, never in git). Everything the team changes lives in the project database, never in those files.

## Quick start

Requirements: Python 3.11+ and [uv](https://docs.astral.sh/uv/) (or pip).

```bash
cd code/OSMAddressSystem
uv sync --extra app --extra planning                           # install (the app and its planning tools)
uv run python -m osmaddresssystem.app setup --project projects/fotouni    # build the road network from input/
uv run python -m osmaddresssystem.app account --project projects/fotouni --username admin --name "Administrator"
uv run python -m osmaddresssystem.app serve --project projects/fotouni --port 8003
```

Open <http://127.0.0.1:8003>, sign in, then invite the team from **Team** (one-use invitations, roles Viewer,
Contributor, Mapper, Administrator). Other commands: `init` (new project folder), `backup` (copy the SQLite database), `import-households` (load family
names and contacts from the survey export into the private `households.csv`).

## The review workflow

The order matters: changing a road changes street ids, street names to choose, numbering and house-road links, so
names and addresses come after geometry.

1. **Roads** — every road on its visible track on Esri imagery, nothing across a roof, junctions where roads meet.
2. **Names** — only names the community already uses; check duplicates and 4-letter codes.
3. **Buildings and addresses** — verify houses, fix road points, review odd/even exceptions, validate into the register.
4. **Final recompute** — warnings, exports, acceptance review, plaques.

Work goes in batches of 7 work areas; an area is complete when its five stages are reviewed.

## Address and plaque format

- **Address**: quartier trigram + street (4-digit number, or the street's 4-letter code once it has a name) +
  4-digit house number: `TCK 0575 0230`, `TCK KUET 0230`.
- **Alleys** off a numbered or named street carry their distance along it (÷ 10 m) and the side they leave on
  (`D` right, `G` left): `TCK (447D)KUET 0230`.
- **Plaque**, top to bottom: `FOTOUNI · TCK`; the family name (one or two lines); a QR code (black on white) with town
  and quartier, family name, GPS position and address; the address. **No phone number** on the plaque or in the QR.
- Only streets with a real name are uploaded to OpenStreetMap; numbers are internal.

## Repository layout

| Path | What is there |
|---|---|
| `osmaddresssystem/` | The package: `street_ids.py`, `branches.py`, `numbering.py`, `path_numbering.py`, `naming_plan.py`, `street_direction.py`, `geocode_map.py`, `street_editor.py`, `street_signs.py`, `poi_signs.py`, `routing.py`, `pipeline.py`, `default_values.py`. |
| `osmaddresssystem/app/` | The web app: `server.py` (API), `auth.py` (accounts), `store.py` (event store), `engine.py` (recompute), `plate.py`, `plaque.py`, `work_areas.py`, `households.py`, `roads.py`, `exports.py`; `static/` (front end). |
| `projects/fotouni/` | The Fotouni project: `input/` (base data), `network/` (built by `setup`). |
| `tests/` | pytest suite: synthetic networks, real-data regressions and browser tests (Playwright). |
| `deploy/` | Docker, docker-compose (SQLite or PostgreSQL, Caddy HTTPS), systemd unit, backup script. |
| `docs/` | Project status, specification, system design, accounts, deployment (see below). |
| `examples/`, `experiments/` | Tutorial notebooks and earlier full runs (Bandja, Douala, Fotouni). |

## Data and privacy

- **Family names and phone numbers never go into git.** They live only in `input/households.csv` (ignored by
  `.gitignore`) and in the project database. A clone of this repository contains no personal data.
- Phone numbers are internal: shown to administrators in the list of address changes, never on a plaque, card or QR.
- A project folder with its database **does** contain personal data: share it privately, never commit it.
- Imagery: Esri World Imagery (and its sharper Wayback release) for tracing and display; Google imagery is not used.
  Roads drawn in Google Earth (`input/missing_roads.kml`) may not go to OpenStreetMap unless retraced on Esri.

## Accounts and security

- Individual accounts, invited by an administrator; four roles enforced on the server.
- Passwords of 15–128 characters, stored as scrypt hashes; session tokens stored only as hashes.
- Session cookie `httpOnly`, `SameSite=strict`, `Secure` off localhost; CSRF token on every change.
- 8 hours per session, 30 minutes idle timeout; sign-in locked for 15 minutes after 8 failed attempts.
- The first administrator can only be created on the server itself (`account` command or localhost).

Details: `docs/accounts-and-history.md`.

## Deployment

The app is one Python process plus a database and a project folder; it needs a persistent disk. See
`deploy/README.md` (Docker, Caddy HTTPS, backups). Serverless hosts such as Vercel do not fit (no persistent disk,
long recomputations).

## Tests

```bash
uv run pytest -p no:cacheprovider
```

Browser tests need Playwright and Chrome; they skip when unavailable.

## Documentation

| Document | What it is for |
|---|---|
| `docs/project-status.md` | **Start here**: where the project stands, the agreed rules, the remaining work. |
| `docs/requirements.md` | Dated record of every requirement and change. |
| `docs/srs.md` | Software requirements specification. |
| `docs/system-design.md` | Architecture and target boundary. |
| `docs/accounts-and-history.md` | Accounts, roles, audit history. |
| `docs/deployment-requirements.md` | What a deployment must provide. |
| `deploy/README.md` | How to host it. |

## Credits

- `osmaddresssystem` package and the original app: **Miguel Ureña Pliego**.
- Fotouni pilot, community app work and field review: **Loryan Mbassi** and the Community Addressing
  Cameroon team.
- Map data © OpenStreetMap contributors (ODbL). Imagery © Esri, Maxar, Earthstar Geographics.

## Licence

Open source under the [MIT licence](LICENSE). The street network and naming code was co-developed with a university;
keeping it open is a requirement.
