# Community Addressing Cameroon: system design boundary

Status: implementation guide for the Fotouni pilot. This records the current
architecture and the target boundary; it does not invent approval rules that
the project team has not decided.

## Current editor

The current product is an authenticated GIS editing workspace:

```text
Browser (HTML/CSS/JavaScript + Leaflet)
             |
        JSON/GeoJSON API
             |
FastAPI process ─ GIS/graph computation in memory
             |
 SQLite/PostgreSQL + persistent input/network files
```

- Python, GeoPandas, Shapely, igraph and SciPy are appropriate for geometry,
  routing and naming optimisation.
- Plain JavaScript and Leaflet are appropriate for the pilot. `app.js` should
  be split gradually by domain, without a pre-pilot framework rewrite.
- One process owns one project. Computed network/address objects are local to
  that process, so multiple workers or interchangeable replicas are unsafe.
- Accounts, permissions, undo/redo, checkpoints and audit evidence belong to
  the editor. Work-area completion is manual progress, not publication approval.

## Required publication boundary

Ride-pooling, marketplace and public clients must not read the mutable editor
database directly. The target boundary is:

```text
Editors → review/acceptance decision → immutable versioned snapshot
                                      → read-only address API
                                      → ride / marketplace / public lookup
```

A publication must have a version, timestamp, community, source editor
revision, schema version and approval identity/reason. Re-publication creates a
new version; it does not mutate an already-consumed version silently.

The external contract will likely need address lookup by permanent ID, text
search, reverse lookup from coordinates, the approved house access point,
street/community metadata and dataset-version metadata. Exact fields,
visibility of residents/survey attributes, approval roles and retention are
project decisions and must be agreed before implementation.

## Evolution without a rewrite

1. Complete Fotouni data and acceptance scenarios on the existing editor.
2. Validate Linux/Docker, HTTPS, account bootstrap, backup and restore.
3. Freeze stable street/building/address identities and the publication schema.
4. Implement explicit review/publish and an immutable snapshot export.
5. Serve snapshots through a separately scalable read-only API/database.
6. Move CPU-heavy recomputation to a durable worker only when concurrency or
   availability requires it; keep full-computation equivalence and fallback.
7. Add multi-community administration only after isolation, authorization and
   backup ownership are defined.

## Production gates

- clean full test run on the release candidate;
- real Fotouni acceptance workflow and unresolved-warning policy;
- reproducible Linux image and dependency lock;
- restore drill and rollback procedure;
- load/concurrency measurement with the agreed user count;
- security review, log/monitoring/alert ownership and TLS renewal;
- approved publication/privacy contract for downstream applications.
