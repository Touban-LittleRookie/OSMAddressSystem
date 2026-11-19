"""House plaques and address cards as SVG, with a QR code drawn here (no imaging or QR library is needed).

The plaque is the agreed format (``docs/project-status.md``), on the approved colours:

1. at the top, the village and the quartier trigram (``FOTOUNI · TCK``);
2. the family name of the household, on up to two lines;
3. a QR code, black squares on white, holding the village and trigram, the family name, the GPS position and the address;
4. at the bottom, the address in the "plaque d'immatriculation" format (``TCK (447D)KUET 0230``, see :mod:`.plate`).

No phone number is printed or put in the QR code. An address that is not validated yet is marked as a draft.

The QR code is byte mode, error correction M, versions 1 to 9 (up to 180 bytes), mask 0. The SVG is in millimetres
(plaque 200 x 250 mm, card 85.6 x 54 mm), so a plaque maker can use it at real size; a browser prints it to PDF.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

# version: (error correction codewords per block, [(number of blocks, data codewords per block), ...]) at level M
_BLOCKS = {1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]), 5: (24, [(2, 43)]), 6: (16, [(4, 27)]),
           7: (18, [(4, 31)]), 8: (22, [(2, 38), (2, 39)]), 9: (22, [(3, 36), (2, 37)])}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46]}
QR_MAX_BYTES = 180


def _gf_mul(x: int, y: int) -> int:
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_ecc(data: list[int], degree: int) -> list[int]:
    div = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            div[j] = _gf_mul(div[j], root)
            if j + 1 < degree:
                div[j] ^= div[j + 1]
        root = _gf_mul(root, 2)
    res = [0] * degree
    for b in data:
        f = b ^ res.pop(0)
        res.append(0)
        for i in range(degree):
            res[i] ^= _gf_mul(div[i], f)
    return res


def _data_capacity(version: int) -> int:
    return sum(n * k for n, k in _BLOCKS[version][1])


def _codewords(raw: bytes, version: int) -> list[int]:
    """Data split in blocks with their error correction, interleaved as the standard says."""
    cap = _data_capacity(version)
    bits = [0, 1, 0, 0] + [(len(raw) >> i) & 1 for i in range(7, -1, -1)]
    for b in raw:
        bits += [(b >> i) & 1 for i in range(7, -1, -1)]
    bits += [0] * min(4, cap * 8 - len(bits))
    bits += [0] * (-len(bits) % 8)
    data = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(data) < cap:
        data.append(pad)
        pad ^= 0xEC ^ 0x11
    ec, groups = _BLOCKS[version]
    blocks, at = [], 0
    for n, k in groups:
        for _ in range(n):
            blocks.append(data[at:at + k])
            at += k
    eccs = [_rs_ecc(b, ec) for b in blocks]
    out = [b[i] for i in range(max(len(b) for b in blocks)) for b in blocks if i < len(b)]
    return out + [e[i] for i in range(ec) for e in eccs]


def _build(text: str) -> tuple[list[list[bool]], list[list[bool]], int]:
    """``(modules, function-module mask, version)`` of the QR code of ``text``."""
    raw = text.encode("utf-8")
    version = next((v for v in _BLOCKS if 12 + 8 * len(raw) <= _data_capacity(v) * 8), None)
    if version is None:
        raise ValueError(f"text too long for the plaque QR code ({QR_MAX_BYTES} bytes at most)")
    n = 17 + 4 * version
    cw = _codewords(raw, version)
    m = [[False] * n for _ in range(n)]
    fn = [[False] * n for _ in range(n)]

    def put(x, y, dark):
        m[y][x], fn[y][x] = dark, True

    for i in range(n):
        put(6, i, i % 2 == 0)
        put(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < n and 0 <= y < n:
                    put(x, y, max(abs(dx), abs(dy)) not in (2, 4))
    pos = _ALIGN[version]
    for a in pos:
        for b in pos:
            if (a, b) in ((pos[0], pos[0]), (pos[0], pos[-1]), (pos[-1], pos[0])):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    put(a + dx, b + dy, max(abs(dx), abs(dy)) != 1)
    fmt = 0                                                  # level M (00), mask 0
    rem = fmt
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    fb = ((fmt << 10) | rem) ^ 0x5412
    bit = lambda v, i: ((v >> i) & 1) == 1                   # noqa: E731
    for i in range(6):
        put(8, i, bit(fb, i))
    put(8, 7, bit(fb, 6)); put(8, 8, bit(fb, 7)); put(7, 8, bit(fb, 8))  # noqa: E702
    for i in range(9, 15):
        put(14 - i, 8, bit(fb, i))
    for i in range(8):
        put(n - 1 - i, 8, bit(fb, i))
    for i in range(8, 15):
        put(8, n - 15 + i, bit(fb, i))
    put(8, n - 8, True)
    if version >= 7:                                         # version information, two copies
        rem = version
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        vb = (version << 12) | rem
        for i in range(18):
            a, b = n - 11 + i % 3, i // 3
            put(a, b, bit(vb, i))
            put(b, a, bit(vb, i))

    i, right = 0, n - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(n):
            for j in range(2):
                x = right - j
                y = n - 1 - vert if ((right + 1) & 2) == 0 else vert
                if not fn[y][x] and i < len(cw) * 8:
                    m[y][x] = ((cw[i >> 3] >> (7 - (i & 7))) & 1) == 1
                    i += 1
        right -= 2
    for y in range(n):
        for x in range(n):
            if not fn[y][x] and (x + y) % 2 == 0:
                m[y][x] = not m[y][x]
    return m, fn, version


def qr_matrix(text: str) -> list[list[bool]]:
    """The modules of a QR code for ``text`` (True = dark).

    Args:
        text: At most :data:`QR_MAX_BYTES` bytes in UTF-8.

    Returns:
        A square list of rows.

    Raises:
        ValueError: When the text is too long.
    """
    return _build(text)[0]


def qr_text(plate: str | None, name: str | None, lat: float | None, lon: float | None, community: str = "FOTOUNI",
            quartier: str | None = None) -> str:
    """What the QR code holds, in the decided order: village and trigram, family name, GPS position, address. Nothing private.

    The name is shortened when the whole text would not fit in the QR code.
    """
    head = f"{community} · {quartier}" if quartier else community
    gps = f"GPS : {lat:.5f}, {lon:.5f}" if lat is not None and lon is not None else None
    addr = f"Adresse : {plate}" if plate else "Adresse : non validée"

    def build(nm):
        return "\n".join(x for x in [head, f"Famille : {nm}" if nm else None, gps, addr] if x)

    nm = (name or "").strip()
    while nm and len(build(nm).encode("utf-8")) > QR_MAX_BYTES:
        nm = nm[:-1].rstrip()
    return build(nm)


def _lines(text: str, width: int = 22, most: int = 2) -> list[str]:
    words, out, cur = [w for w in str(text or "").replace(" - ", " - ").split(" ") if w], [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        out.append(cur)
    if len(out) > most:
        out = out[:most - 1] + [" ".join(out[most - 1:])]
    return out or [""]


_FONT = "font-family=\"'Segoe UI','Inter','Helvetica Neue',Arial,sans-serif\""
_BG, _INK, _LINE = "#1d1d1f", "#ecebe6", "#a9a9a6"


def _qr_rects(m, x0: float, y0: float, box: float, quiet: int = 4) -> str:
    size = len(m)
    mod = box / (size + 2 * quiet)
    return "".join(f'<rect x="{x0 + (x + quiet) * mod:.3f}" y="{y0 + (y + quiet) * mod:.3f}" width="{mod + 0.06:.3f}" height="{mod + 0.06:.3f}"/>'
                   for y in range(size) for x in range(size) if m[y][x])


def _fit(text: str, width_mm: float, most: float, ratio: float = 0.62) -> float:
    """A font size (mm) at which ``text`` fits in ``width_mm`` (``ratio``: average glyph width per size, bold sans)."""
    return round(min(most, width_mm / max(1, len(text)) / ratio), 1)


def plaque_svg(plate: str | None, name: str | None, lat: float | None, lon: float | None, community: str = "FOTOUNI",
               quartier: str | None = None, draft: bool = False) -> str:
    """The plaque of one house (200 x 250 mm).

    Args:
        plate: Address in the plaque format (``TCK (447D)KUET 0230``), None when incomplete.
        name: Family name (or business name) printed under the head line; None leaves the space empty.
        lat: Latitude of the house (for the QR code).
        lon: Longitude.
        community: Village name.
        quartier: Quartier trigram (``TCK``).
        draft: Mark the plaque as a draft (address not validated).

    Returns:
        The SVG document.
    """
    W, H = 200, 250
    m = qr_matrix(qr_text(plate, name, lat, lon, community, quartier))
    box, by = 80, 112
    bx = (W - box) / 2
    head = escape(f"{community} · {quartier}" if quartier else community)
    lines = _lines((name or "").upper(), 18, 2) if name else []
    size = min(_fit(max(lines, key=len), 170, 20, 0.66), 20) if lines else 0
    ys = [70] if len(lines) == 1 else [58, 58 + size + 4]
    name_txt = "".join(f'<text x="{W / 2}" y="{y:.1f}" font-size="{size}" font-weight="800" letter-spacing=".6">{escape(t)}</text>'
                       for t, y in zip(lines, ys))
    bottom = escape(plate) if plate else "ADRESSE NON VALIDÉE"
    bsize = _fit(bottom, 176, 17, 0.66)
    mark = (f'<text x="{W / 2}" y="{H / 2 + 20}" font-size="30" font-weight="800" fill="#e53935" opacity=".28" text-anchor="middle" '
            f'transform="rotate(-28 {W / 2} {H / 2})" {_FONT}>BROUILLON</text>') if draft else ""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">
<rect width="{W}" height="{H}" rx="7" fill="{_BG}"/>
<rect x="6" y="6" width="{W - 12}" height="{H - 12}" rx="5" fill="none" stroke="{_LINE}" stroke-width="1.1"/>
<g fill="{_INK}" text-anchor="middle" {_FONT}>
  <text x="{W / 2}" y="25" font-size="8.5" font-weight="600" letter-spacing="2.2">{head}</text>
  {name_txt}
  <text x="{W / 2}" y="222" font-size="{bsize}" font-weight="800" letter-spacing="1.2">{bottom}</text>
</g>
<rect x="{bx}" y="{by}" width="{box}" height="{box}" rx="3" fill="#ffffff"/>
<g fill="#111111" shape-rendering="crispEdges">{_qr_rects(m, bx, by, box)}</g>
{mark}
</svg>
'''


def card_svg(plate: str | None, name: str | None, lat: float | None, lon: float | None, community: str = "FOTOUNI",
             quartier: str | None = None, quartier_name: str | None = None, draft: bool = False) -> str:
    """The address card given to the household (bank-card size, 85.6 x 54 mm), same content as the plaque.

    Args:
        plate: Address (``TCK (447D)KUET 0230``).
        name: Family name.
        lat: Latitude.
        lon: Longitude.
        community: Village name.
        quartier: Quartier trigram.
        quartier_name: Quartier name written out (``Tchikong``).
        draft: Mark as a draft.

    Returns:
        The SVG document.
    """
    W, H = 85.6, 54
    m = qr_matrix(qr_text(plate, name, lat, lon, community, quartier))
    box = 30
    bx, by = W - box - 4, 15
    nm = (name or "").upper()
    nlines = _lines(nm, 20, 2) if nm else []
    nsize = min(_fit(max(nlines, key=len), 46, 4.2, 0.66), 4.2) if nlines else 0
    addr = escape(plate) if plate else "ADRESSE NON VALIDÉE"
    asize = _fit(plate or "ADRESSE NON VALIDÉE", 43, 5.2, 0.68)
    where = escape(f"{community} · {quartier_name or ''} ({quartier})" if quartier else community)
    name_txt = "".join(f'<text x="5" y="{25 + k * (nsize + 1.4):.1f}" font-size="{nsize}" font-weight="800">{escape(t)}</text>'
                       for k, t in enumerate(nlines))
    gps = f"{lat:.5f}, {lon:.5f}" if lat is not None and lon is not None else ""
    mark = (f'<text x="{W / 2}" y="{H / 2 + 4}" font-size="11" font-weight="800" fill="#e53935" opacity=".3" text-anchor="middle" '
            f'transform="rotate(-18 {W / 2} {H / 2})" {_FONT}>BROUILLON</text>') if draft else ""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">
<rect width="{W}" height="{H}" rx="3.2" fill="{_BG}"/>
<g fill="{_INK}" {_FONT}>
  <text x="5" y="8.5" font-size="2.6" font-weight="600" letter-spacing=".7">CARTE D'ADRESSE</text>
  <text x="5" y="13.5" font-size="3" font-weight="600">{where}</text>
  {name_txt}
  <text x="5" y="42" font-size="{asize}" font-weight="800" letter-spacing=".3">{addr}</text>
  <text x="5" y="48" font-size="2.4" fill="{_LINE}">GPS {gps}</text>
</g>
<rect x="{bx}" y="{by}" width="{box}" height="{box}" rx="1.5" fill="#ffffff"/>
<g fill="#111111" shape-rendering="crispEdges">{_qr_rects(m, bx, by, box)}</g>
{mark}
</svg>
'''
