# Project status — Fotouni pilot

Status of the Fotouni pilot and the work that remains. Updated 19 November 2026.

## Where the project stands

| Pass | State |
|---|---|
| 1. Roads (geometry) | Finished: all 58 work areas checked on Esri imagery. |
| 2. Street names | Not started. Unnamed streets carry their 4-digit number until they receive a name. |
| 3. Addresses and plaques | Every surveyed house has a draft address. None is validated in the register yet. |

- 2,127 surveyed houses, all with an address in the `TCK 0575 0230` format, plus 62 reference points (landmarks),
  which have no plaque address by design.
- Houses more than 50 m from any road are linked to their nearest street by a road point chosen by hand.
- Work areas are 950 m squares (`R01C08`…); a square touching the boundary is kept whole.
- Drivable is set on every road from its OpenStreetMap class; surface (tarmac or dirt) is not set by hand yet.

## Road review method

25 areas had a full review on the sharp Esri imagery. The other 33 had a fast pass, then a targeted check: an
automatic scan for roads over roofs, loose ends and crossings without a junction, and a close-up every 100 m along
every road, reviewed by eye. Lines 4 m or more beside their track, over a roof or wrongly joined were corrected.
One block of four areas (R10C07, R10C08, R11C06, R11C07) was shifted 5 m east and 1.2 m south onto the imagery.
Some roads remain 2–3 m beside their track (1142, 276, 261, 69, 283, 1552, 1101, 1487, 360, part of 932): below GPS
accuracy, left as they are.

## Agreed rules

- **Address**: quartier trigram + street (4-digit number, or the street's 4-letter code once it has a name) + 4-digit
  house number. Odd numbers on the left, even on the right.
- **Alleys** keep the side letter: `TCK (447D)KUET 0230` (447 = distance along the parent street ÷ 10 m; D right,
  G left).
- **Plaque**, top to bottom: `FOTOUNI · TCK`; the family name (one or two lines); a QR code, black on white, with town
  and quartier, family name, GPS position and address; the address. Colours approved.
- **Phone numbers are internal only**: never on a plaque, card or QR code; shown only to administrators in the list
  of address changes.
- **Addresses are not locked.** When an edit changes a validated address, the family is informed and their card
  changes; the register's change list supports this.
- **Street numbers are internal.** Only streets with a real name are uploaded to OpenStreetMap.
- **Imagery**: Esri World Imagery (sharper Wayback release 49059 by default). Google imagery is not used.
- The app is an internal tool for the team.

## Remaining work

1. **Testing** of all 58 work areas and the address format, until 30 November 2026; fix what is reported.
2. **Field checks**: 9 access paths marked "uncertain" and 23 houses linked to a road more than 150 m away
   (mostly near `5.2806, 10.2200`).
3. **Road 284 / 1553** (`5.31689, 10.22425`, R07C06): 284 runs 3 m beside 1553 for its last 30 m. Cleaner: cut
   1553 at its bend in the street editor and end 284 there.
4. **Street names** (pass 2): names the community already uses, area by area; check duplicates and 4-letter codes.
5. **Road flags**: surface on the main roads; "gives no address" only where a stub should not number houses (this
   renumbers houses, so before validation).
6. **Validation** (pass 3): validate addresses into the register area by area.
7. **Plaques and cards**: the print tool exists (SVG at real size); confirm the file format with the plaque maker.
8. **OpenStreetMap upload filter**, before any upload. The current `osm_changes.osm` export is not safe to upload as
   it is. It needs: a names-only mode (add names to existing roads); new roads only when drawn on Esri; no
   deletions; no moves that only re-align a road to the imagery. The 24 roads of `input/missing_roads.kml` were
   drawn in Google Earth and must be redrawn on Esri or left out.
9. **Code structure**: `app.js` and `server.py` are long single files; split them by feature without changing
   behaviour, with the test suite passing.

## Licensing notes

- Esri World Imagery and its Wayback releases: display with the attribution shown; listed by OpenStreetMap as
  imagery that may be traced.
- OpenStreetMap tiles (`tile.openstreetmap.org`): fine for light, internal use with attribution.
- Leaflet 1.9.4 is bundled in `static/vendor/` with its BSD-2 copyright header.
- KML import and export is an open file format.
- The repository has no licence file yet: all rights are reserved by the authors until one is chosen.
