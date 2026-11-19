# Community Addressing Cameroon: Software Requirements Specification

Version 0.1, 15 November 2026. Draft for the project team.

This document says what the addressing application must do, now for Fotouni and later for other communities, and how it
should be built. It complements, and does not replace:

- `docs/project-status.md`: where the project stands, the agreed rules and the remaining work;
- `docs/system-design.md`: the architecture boundary;
- `docs/deployment-requirements.md`: the hosting brief.

Each requirement has an identifier (`FR-…` for functional, `NFR-…` for non-functional) and a status:

- **Done**: implemented and tested.
- **Partial**: started, or done for the pilot only.
- **Planned**: not started.
- **Decision**: waiting for a decision by the project lead.

---

## 1. Purpose and scope

### 1.1 The problem

Most houses in Fotouni (Bandja commune, West Region) have no address that a visitor, a delivery driver, an ambulance or a
public service could use. Streets exist but have no names. Houses exist but have no numbers. Directions are given by
landmarks.

### 1.2 What the product does

The application turns the road network of a community into a **stable, human-readable address for every house**, for
example `230A, Voie 447 du Boulevard Fo KUETCHONG`. It does this in five steps:

1. Start from the roads already in OpenStreetMap (OSM) and let local editors correct them against satellite imagery and
   their own knowledge.
2. Group road pieces into **streets** with stable identifiers, ranks and a numbering direction.
3. Give every street a **name**: a few are named by the community and the others get derived names
   ("Voie 447 du Boulevard X").
4. Give every surveyed building a **number**: the metres along its street from the street's start, even on the right and
   odd on the left, with letters when houses share a number or are reached by a small path.
5. **Approve** addresses into a permanent register, print **plaques** and street signs, and later publish the approved
   addresses to other services, such as ride-pooling, a marketplace or public lookup.

### 1.3 Out of scope

- An official cadastre or land titles.
- Legal ownership.
- Postal delivery operations.
- Payments.

---

## 2. Background: where the project and its data come from

This section is for anyone joining the project. Everything below is taken from the repository, its READMEs and its git
history.

### 2.1 The research project

The workspace `addressing-cameroon` is a research project on street addressing and census data, piloted in **Fotouni**
and in **Bonamoussadi (Douala)**. It has three strands (`README.md`):

| Strand | What was done | Data |
|---|---|---|
| Pilot building survey | Surveyors walked with RTK GNSS receivers and phones running SW Maps, in Douala and Fotouni. | `data/*/pilot_survey` |
| Road-quality tests | A phone's IMU and GPS were recorded in a car to classify road roughness, 21–26 March 2026. | `data/imu`, `code/IMURoadQuality` |
| Fotouni town survey | The complete town was surveyed with phones only, using the **EFYL** survey app, in August 2026. | `data/fotouni/town_survey` |

The project website (`reports/project_web`, page *addressing-system*) explains the method and its references, including
the World Bank guide *Street Addressing and the Management of Cities* (2005) and the UPU white paper
*Addressing the World* (2012).

### 2.2 The input data of the Fotouni app

| Input file (`projects/<name>/input/`) | Origin |
|---|---|
| `streets.osm` | The roads in **OpenStreetMap**, mapped over the years by OSM volunteers. The Bandja commune (OSM relation 3837548) was downloaded through the Overpass API on 18 October 2026 (`data/fotouni/town_survey/osm`), and the project copy was cut with osmium. OSM had almost no street names there: 16 of about 3,100 ways. |
| `buildings.gpkg` | The **2,127 usable buildings of the EFYL town survey** (August 2026). They are survey points, not roofs detected from imagery. The survey also holds personal data, which is not in git and must not be published. |
| `area.gpkg` | The Fotouni extent, chosen from the candidates in `fotouni_area_candidates.gpkg` (`code/fotouni_town_qc`). |
| `points.gpkg` | Important places (squares, facilities), drawn in Google Earth (`Fotouni_Sept. 2026.kml`) and listed in `Squares- Intersections - Facilities.xlsx`. |
| `street_edits.csv`, `edge_edits.csv` | Street names, ranks and geometry corrections made with the earlier street-editor maps, as of 15 September 2026 (`streets_places/`). |
| `missing_roads.kml` | Roads missing from OSM, drawn in Google Earth. |
| `default_reference.json` | The reference point that numbering starts from (the centre of the radial numbering). |

### 2.3 Code history

| Date (2026) | Who | What |
|---|---|---|
| 20 Jul – 11 Aug | Miguel Ureña Pliego | `OSMAddressSystem` package: street identity from OSM (`street_ids.py`), radial and grid numbering direction, house numbering, geocoding, sign maps. Pipeline runs for Bandja and Douala. |
| 1 Sep | Miguel | Offline street editor (folium maps) and major street-identity changes. |
| 25–26 Oct | Miguel | **Major refactor into the community app** (`osmaddresssystem/app`): FastAPI backend, Leaflet front end, project database, path numbering from a reference point, naming plan. Fotouni project inputs imported on 26 October. |
| 27–29 Oct | Loryan Mbassi | Invited accounts and roles, audit history, design system and logo, English/French interface, road editing tools, street-ID validation, work areas. Pull request #1. |
| 29 Oct – 13 Nov | Loryan Mbassi | Naming rules R1–R3, quartier work areas with five-stage progress, drivable/paved per edge, ordered road edits and fast recompute, derived names in walking order, paths that give no addresses, the address register with permanent codes, plaques. |

Branches:

- `main` is Miguel's last published state.
- `naming-rules` holds the work since 29 October, not committed yet.

### 2.4 OpenStreetMap: what the app does and does not do

- Editing roads in the app **does not change OSM**. The app keeps its own copy and a history of edits. Adding, moving
  or deleting a road therefore causes no problem for OSM volunteers.
- Sending corrections back to OSM is a separate, deliberate step: the export `osm_changes.osm` and the documented upload
  workflow. It must follow the OSM rules (section 7.4). In particular, **geometry traced on Google imagery may not be
  uploaded to OSM**.

---

## 3. Users and roles

| Role | Who | Main tasks |
|---|---|---|
| Administrator | Project lead, technical owner | Accounts, project settings, approving addresses, checkpoints, exports |
| Editor | Trained local team | Correct roads, set street attributes, propose names, place access points, in assigned work areas |
| Reviewer | Project lead or delegated quartier representatives | Check a work area, accept or return it, validate names |
| Field surveyor | Local team with phones | Add missing buildings, photos and plaque installation status (planned) |
| Resident / public | Anyone | Look up an address, find the way to a house (planned, read-only) |
| Downstream service | Ride-pooling, marketplace, emergency services | Read **approved** addresses only, through a versioned API (planned) |

---

## 4. Operating environment and constraints

- **Connectivity:** mobile data in Fotouni is slow and expensive. Pages must work on 3G, and satellite tiles are the
  largest cost.
- **Devices:** low-end Android phones for field work, and laptops for editing.
- **Languages:** French first and English. Street names can contain local-language words.
- **Licences:**
  - OSM data is under the ODbL: attribution is required and derived databases must stay open.
  - Each imagery source has its own terms (section 7.4).
- **Personal data:** the survey contains names and phone numbers. Cameroon's personal data protection law
  (Law No. 2024/017) and the project's own ethics rules apply. Plaques and public outputs contain **no names**.
- **Team:** a small team with one main developer. The stack must stay simple enough for one person to maintain.

---

## 5. Functional requirements

### 5.1 Project and data import

| ID | Requirement | Status |
|---|---|---|
| FR-01 | Create a project from an OSM extract, an area outline, building points, places and earlier edit tables (`init`, `setup`). | Done |
| FR-02 | Download the OSM roads of a new community from inside the app (area drawn or chosen), without a command line. | Planned |
| FR-03 | Import building footprints or points from other sources (survey CSV, Google/Microsoft Open Buildings, OSM buildings) with a duplicate check. | Planned |
| FR-04 | Keep each input file's provenance: source, date and licence. | Partial |

### 5.2 Road network editing (stage 1)

| ID | Requirement | Status |
|---|---|---|
| FR-10 | Show OSM roads, drawn roads and satellite imagery. Draw, reshape, split, connect, delete a section of a road. | Done |
| FR-11 | Undo and redo every edit, apply edits in the order they were made, and keep the full history. | Done |
| FR-12 | Set per-edge attributes: drivable (yes / no / partly), paved, gives addresses (yes / no). | Done |
| FR-13 | Detect and show parts cut off from the network, uncertain endpoints and unclear portions. | Done |
| FR-14 | Import and export roads as KML, to edit in Google Earth. | Done |
| FR-15 | Work areas: grid by quartier, each with five progress stages, assignment and notes. | Done (assignment Planned) |
| FR-16 | Record GPS tracks from a phone to draw or check a road in the field. | Planned |

### 5.3 Street identity, rank and direction (stage 2)

| ID | Requirement | Status |
|---|---|---|
| FR-20 | Merge road pieces into streets with stable identifiers, keeping an identifier when a street is only edited. | Done |
| FR-21 | Street rank (0 trunk … 5 path) and numbering direction from a reference point (radial) or a grid. | Done |
| FR-22 | Let an editor cut, join or reverse a street, with a preview. | Done |

### 5.4 Street names (stage 3)

| ID | Requirement | Status |
|---|---|---|
| FR-30 | Naming plan: the fewest streets the community must name so that every street has a name or a derived name. | Done |
| FR-31 | Derived names in walking order (`Voie 447 du Boulevard X`), naming rules R1–R3. | Done |
| FR-32 | Propose, discuss and approve names: who proposed, decision and date; reject duplicates and similar names. | Partial |
| FR-33 | Abbreviation rules for signs; maximum length on a plaque. | Partial |

### 5.5 Buildings and addresses (stage 4)

| ID | Requirement | Status |
|---|---|---|
| FR-40 | Number every building from its access point: metres along the street, even on the right, odd on the left, with letters when houses share a number. | Done |
| FR-41 | Houses on a path that gives no addresses take the number of the junction where the path leaves the street, with a letter in walking order. | Done (rule for which paths: **Decision**) |
| FR-42 | Choose an access point by hand when the nearest road is wrong. | Done |
| FR-43 | Status of each house: complete / waiting for a street name / no street. | Done |
| FR-44 | Add a missing building on the map, and mark a demolished one. | Planned |
| FR-45 | Reference buildings (chiefdom, school…) never move their street's numbering. | Done |

### 5.6 Register and permanence

| ID | Requirement | Status |
|---|---|---|
| FR-50 | Approve one house or a whole work area. An approved address never changes by itself. | Done |
| FR-51 | Permanent code with a check digit, never reused. The final format is **Decision** (current `FTN-000123-0`, versus `TCK 0575 4575`). | Partial |
| FR-52 | When the map would now give an approved house another address, list it *to review*. A correction needs a reason and keeps the code. | Done |
| FR-53 | Retire an address (house gone) with a reason. Its number and code are never given again. | Done |
| FR-54 | Who may approve (administrator only today, quartier representatives later). | **Decision** |
| FR-55 | History of each address: proposed, approved, corrected, retired, with person and date. | Done |

### 5.7 Plaques and signs

| ID | Requirement | Status |
|---|---|---|
| FR-60 | Plaque per house as SVG at real size (200 × 250 mm), with village, quartier, number, street, QR code (code + position, no name) and code. A draft is marked. | Done (QR to verify with phones) |
| FR-61 | Street-name signs per junction, with print list and positions. | Partial |
| FR-62 | Print batches: one PDF per work area, with a list for the plaque maker and installers. | Planned |
| FR-63 | Installation tracking: plaque made, installed, photo, date. | Planned |

### 5.8 Accounts, audit and safety

| ID | Requirement | Status |
|---|---|---|
| FR-70 | Invited accounts, roles enforced by the server, revocable sessions, password rules. | Done |
| FR-71 | Every change is recorded with its author: undo, checkpoints, restore. A restore never takes back approvals. | Done |
| FR-72 | Backup and restore command; a restore drill is documented. | Partial |

### 5.9 Publication and external use

| ID | Requirement | Status |
|---|---|---|
| FR-80 | Publish approved addresses as an **immutable versioned snapshot** (version, date, source revision, approver, reason). | Planned |
| FR-81 | Read-only API on the snapshots: lookup by code, text search, reverse lookup from coordinates, the access point for routing. | Planned |
| FR-82 | Public address page per code (what the QR code could open), without personal data. | Planned |
| FR-83 | Upload confirmed street names, and geometry traced on allowed imagery, to OSM through the documented workflow. | Partial (export exists) |
| FR-84 | Exports: CSV and GeoPackage of streets, edges, nodes, buildings, signs and register. | Done |

### 5.10 Several communities

| ID | Requirement | Status |
|---|---|---|
| FR-90 | Several communities on one server, each isolated (data, accounts, backups). | Planned |
| FR-91 | Community settings: name, trigram, reference point, numbering step, code prefix. | Partial |

---

## 6. Non-functional requirements

| ID | Area | Requirement |
|---|---|---|
| NFR-01 | Performance | Recomputing the network of one community takes under 60 s; addresses under 30 s. A map page loads under 5 s on 3G without imagery. (Measured: 10–46 s network and 10–19 s addresses on a laptop.) |
| NFR-02 | Bandwidth | Satellite imagery only on request, cached in the browser. Vector data compressed (gzip). A future offline mode stores one work area on the phone. |
| NFR-03 | Availability | During field campaigns: daily backup, recovery in under 4 hours, at most one day of edits lost. These targets are to be confirmed by the project. |
| NFR-04 | Security | HTTPS only, invited accounts, server-side permissions, rate-limited sign-in, no secrets in git, a security review before going public. |
| NFR-05 | Privacy | No personal data in plaques, public pages, exports to third parties or OSM. Survey personal data stays in its access-controlled folder. |
| NFR-06 | Stability of identifiers | Street IDs, building IDs and address codes never change silently. Every change is an event with an author. |
| NFR-07 | Languages | Every screen in French and English. Messages are written for non-specialists. |
| NFR-08 | Maintainability | Each module has one purpose. Tests exist for each rule; the full suite passes before any release. Agreed rules are recorded in `docs/project-status.md`. |
| NFR-09 | Portability | Runs on Windows for development and on Linux (Docker) for hosting. Dependencies come from the lockfile. |
| NFR-10 | Licences | OSM attribution is shown. Imagery used for OSM uploads must be allowed by OSM (section 7.4). |

---

## 7. System design

### 7.1 Current architecture (pilot)

```text
Browser: HTML/CSS/JavaScript + Leaflet (vendored), French/English
        │  JSON / GeoJSON over HTTP
FastAPI + Uvicorn, one process per project
        │  GeoPandas, Shapely, osmnx, igraph, SciPy (computation in memory)
SQLite (WAL) or PostgreSQL: event log, checkpoints, audit, accounts
        +  project files: input/, network/, computed/
```

Data model, simplified:

- **Event log**: every edit (road, attribute, name, approval) is an event. The project state is the sum of the events that
  were not undone. Undo marks an event undone; checkpoints save a state.
- **Derived results**: the network (streets, IDs, names) and the addresses are computed from the state and cached by hash.
- **Register**: approved addresses with code, snapshot and history. It is part of the state but excluded from the network
  hash.

### 7.2 Target architecture

```text
             Editors (web app)              Field team (phone, offline PWA)
                    │                                  │
        ┌───────────┴──── Editor API (FastAPI) ────────┘
        │                    │
        │            Job worker (recomputation, exports, PDF batches)
        │                    │
        │   PostgreSQL + PostGIS (one schema per community) ── object storage (imagery cache, photos, PDFs, backups)
        │
        └── Publish ──► immutable snapshot (versioned) ──► Public read-only API + address pages
                                                         ──► OSM upload (names; geometry from allowed imagery)
```

Move to the target in this order, keeping the same Python rules all along:

1. Finish Fotouni on the current editor.
2. Host on one Linux server with Docker and HTTPS, and test a restore.
3. Fix the code format and the publication schema.
4. Add publish and snapshots, then the read-only API.
5. Add PostGIS and a job worker only when several communities or users require it.
6. Rebuild the map on MapLibre and add offline mode once the workflows are stable.

### 7.3 Technologies

| Layer | Now | Recommended next | Why |
|---|---|---|---|
| Computation | Python 3.12+, GeoPandas, Shapely 2, osmnx, igraph, SciPy | Same | Well suited to graphs and geometry; already tested |
| API | FastAPI, Pydantic, Uvicorn | Same, plus Alembic migrations | Typed, fast, simple |
| Database | SQLite (WAL); PostgreSQL optional | PostgreSQL 16 + PostGIS | Spatial queries, several communities, `pg_dump` backups |
| Jobs | One thread in the process | RQ or Arq with Redis, when needed | Long recomputations outside the request |
| Front end | Vanilla JavaScript, Leaflet | TypeScript + Vite; MapLibre GL JS with vector tiles (PMTiles) | Smooth maps with many features, offline tiles; split `app.js` by domain |
| Field app | none | PWA (service worker, IndexedDB), or a QField/ODK form | Offline field work on cheap phones |
| Imagery | Google and Esri tiles | A licensed source for display; OSM-allowed sources (Esri World Imagery, Bing, Maxar via iD) for tracing that goes to OSM | Licence |
| Hosting | Local Windows | One VPS (2 vCPU, 4 GB RAM) with Docker Compose, Caddy (HTTPS), PostGIS, nightly encrypted backups off the server | Cheap, enough for the pilot |
| Quality | pytest (≈ 425 tests), Playwright | GitHub Actions running the tests on every push; Ruff for linting | Protect the rules |
| Monitoring | none | Health checks, Uptime Kuma, Sentry for errors, log rotation | Know before users complain |

### 7.4 OpenStreetMap rules for any upload

- Use a dedicated OSM account, a clear changeset comment and, for organised work, a wiki page that follows the
  *Organised Editing Guidelines*.
- **Imagery:** tracing from Google Maps or Google Earth imagery is forbidden in OSM. Only geometry traced on sources that
  OSM allows (the imagery list of the iD and JOSM editors), or GPS tracks recorded by the team, may be uploaded.
- **Names:** street names decided by the community are local knowledge and can be uploaded (`name=*`). Derived names
  ("Voie 447 du …") are internal and are **not** uploaded as `name=*`.
- **Deletions:** only delete in OSM what no longer exists on the ground. A road deleted in the app because it is not
  needed for addressing stays in OSM.
- Never upload personal data.

### 7.5 Development approach

- **Branches:** short feature branches, merged by pull request into `main` after the tests pass. One topic per commit.
- **Decisions:** every agreed rule is written in `docs/project-status.md`, then a test,
  then the code.
- **Data:** never test on the practice project or production data; always on a copy. Database changes go through
  migrations.
- **Releases:** before each field campaign, a tagged release, a full test run, a backup and a restore drill.

---

## 8. Open decisions

| Decision | Owner | Blocks |
|---|---|---|
| Final format and meaning of the permanent code (`TCK 0575 4575` or `FTN-000123-0`) | Project lead | FR-51, plaques |
| Which paths give no addresses (length, number of houses, dead end) | Project lead | FR-41 |
| Who may approve addresses and names | Project lead | FR-54, FR-32 |
| What the QR code opens (code only, or a public page) | Project lead | FR-82 |
| Public data: which fields, retention, consent | Project lead, ethics | FR-80–82 |
| Hosting provider, budget, number of users | Project lead | NFR-03, section 7.2 |
| Next community after Fotouni | Project lead | FR-02, FR-90 |
