#!/usr/bin/env python
# vim:fileencoding=utf-8
# License: GPL v3 Copyright: 2016, Kovid Goyal <kovid at kovidgoyal.net>

import ctypes
import sys
from collections import namedtuple
from math import ceil, floor, pi, sin, sqrt

from kitty.config import defaults
from kitty.constants import isosx
from kitty.fast_data_types import (
    Screen, change_wcwidth, get_fallback_font, send_prerendered_sprites,
    set_font, set_font_size, set_logical_dpi, set_send_sprite_to_gpu,
    sprite_map_set_limits, test_render_line, test_shape
)
from kitty.fonts.box_drawing import render_box_char, render_missing_glyph

if isosx:
    from .core_text import get_font_files, font_for_family
else:
    from .fontconfig import get_font_files, font_for_family


def create_symbol_map(opts):
    val = opts.symbol_map
    family_map = {}
    faces = []
    for family in val.values():
        if family not in family_map:
            font, bold, italic = font_for_family(family)
            family_map[family] = len(faces)
            faces.append((font, bold, italic))
    sm = tuple((a, b, family_map[f]) for (a, b), f in val.items())
    return sm, tuple(faces)


FontState = namedtuple(
    'FontState',
    'family pt_sz cell_width cell_height baseline underline_position underline_thickness'
)


def set_font_family(opts=None, override_font_size=None):
    opts = opts or defaults
    sz = override_font_size or opts.font_size
    font_map = get_font_files(opts)
    faces = [font_map['medium']]
    for k in 'bold italic bi'.split():
        if k in font_map:
            faces.append(font_map[k])
    sm, sfonts = create_symbol_map(opts)
    cell_width, cell_height, baseline, underline_position, underline_thickness = set_font(
        render_box_drawing, sm, sfonts, sz, *faces
    )
    set_font_family.state = FontState(
        opts.font_family, sz, cell_width, cell_height, baseline,
        underline_position, underline_thickness
    )
    return cell_width, cell_height


def resize_fonts(new_sz):
    s = set_font_family.state
    cell_width, cell_height, baseline, underline_position, underline_thickness = set_font_size(new_sz)
    set_font_family.state = FontState(
        s.family, new_sz, cell_width, cell_height, baseline,
        underline_position, underline_thickness
    )
    return cell_width, cell_height


def add_line(buf, cell_width, position, thickness, cell_height):
    y = position - thickness // 2
    while thickness:
        thickness -= 1
        offset = cell_width * y
        for x in range(cell_width):
            buf[offset + x] = 255
        y += 1


def add_curl(buf, cell_width, position, thickness, cell_height):
    xfactor = 2.0 * pi / cell_width
    yfactor = thickness

    def clamp_y(y):
        return max(0, min(int(y), cell_height - 1))

    def clamp_x(x):
        return max(0, min(int(x), cell_width - 1))

    def add_intensity(x, y, distance):
        buf[cell_width * y + x] = min(
            255, buf[cell_width * y + x] + int(255 * (1 - distance))
        )

    for x_exact in range(cell_width):
        y_exact = yfactor * sin(x_exact * xfactor) + position
        y_below = clamp_y(floor(y_exact))
        y_above = clamp_y(ceil(y_exact))
        x_before, x_after = map(clamp_x, (x_exact - 1, x_exact + 1))
        for x in {x_before, x_exact, x_after}:
            for y in {y_below, y_above}:
                dist = sqrt((x - x_exact)**2 + (y - y_exact)**2) / 2
                add_intensity(x, y, dist)


def render_special(underline=0, strikethrough=False, missing=False):
    s = set_font_family.state
    cell_width, cell_height, baseline = s.cell_width, s.cell_height, s.baseline
    underline_position, underline_thickness = s.underline_position, s.underline_thickness
    underline_position = min(underline_position, cell_height - underline_thickness)
    CharTexture = ctypes.c_ubyte * (cell_width * cell_height)
    ans = CharTexture if missing else CharTexture()

    def dl(f, *a):
        f(ans, cell_width, *a)

    if underline:
        t = underline_thickness
        if underline == 2:
            t = max(1, min(cell_height - underline_position - 1, t))
        dl(
            add_curl
            if underline == 2 else add_line, underline_position, t, cell_height
        )
    if strikethrough:
        pos = int(0.65 * baseline)
        dl(add_line, pos, underline_thickness, cell_height)

    if missing:
        buf = bytearray(cell_width * cell_height)
        render_missing_glyph(buf, cell_width, cell_height)
        ans = CharTexture.from_buffer(buf)
    return ans


def prerender():
    # Pre-render the special blank, underline and strikethrough cells
    cells = render_special(1), render_special(2), render_special(0, True), render_special(missing=True)
    if send_prerendered_sprites(*map(ctypes.addressof, cells)) != len(cells):
        raise RuntimeError('Your GPU has too small a max texture size')


def render_box_drawing(codepoint):
    s = set_font_family.state
    cell_width, cell_height = s.cell_width, s.cell_height
    CharTexture = ctypes.c_ubyte * (cell_width * cell_height)
    buf = render_box_char(
        chr(codepoint), CharTexture(), cell_width, cell_height
    )
    return ctypes.addressof(buf), buf


def setup_for_testing(family='monospace', size=11.0, dpi=96.0):
    from kitty.utils import get_logical_dpi
    opts = defaults._replace(font_family=family)
    sprites = {}

    def send_to_gpu(x, y, z, data):
        sprites[(x, y, z)] = data

    sprite_map_set_limits(100000, 100)
    set_send_sprite_to_gpu(send_to_gpu)
    set_logical_dpi(dpi, dpi)
    get_logical_dpi((dpi, dpi))
    cell_width, cell_height = set_font_family(opts, override_font_size=size)
    prerender()
    return sprites, cell_width, cell_height


def render_string(text, family='monospace', size=11.0, dpi=96.0):
    try:
        sprites, cell_width, cell_height = setup_for_testing(family, size, dpi)
        s = Screen(None, 1, len(text)*2)
        line = s.line(0)
        s.draw(text)
        test_render_line(line)
    finally:
        set_send_sprite_to_gpu(None)
    cells = []
    for i in range(s.columns):
        sp = line.sprite_at(i)
        if sp != (0, 0, 0):
            cells.append(sprites[sp])
    return cell_width, cell_height, cells


def shape_string(text="abcd", family='monospace', size=11.0, dpi=96.0, path=None):
    import json
    try:
        sprites, cell_width, cell_height = setup_for_testing(family, size, dpi)
        s = Screen(None, 1, len(text)*2)
        line = s.line(0)
        s.draw(text)
        data = test_shape(line, path)
        return json.loads('[' + data + ']')
    finally:
        set_send_sprite_to_gpu(None)
    return data


def test_render_string(text='Hello, world!', family='monospace', size=144.0, dpi=96.0):
    from tempfile import NamedTemporaryFile
    from kitty.fast_data_types import concat_cells, current_fonts
    from kitty.icat import detect_support, show
    if not hasattr(test_render_string, 'detected') and not detect_support():
        raise SystemExit('Your terminal does not support the graphics protocol')
    test_render_string.detected = True

    cell_width, cell_height, cells = render_string(text, family, size, dpi)
    rgb_data = concat_cells(cell_width, cell_height, tuple(cells))
    with NamedTemporaryFile(delete=False) as f:
        f.write(rgb_data)
    cf = current_fonts()
    fonts = [cf['medium'].display_name()]
    fonts.extend(f.display_name() for f in cf['fallback'])
    msg = 'Rendered string {} below, with fonts: {}\n'.format(text, ', '.join(fonts))
    try:
        print(msg)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(msg.encode('utf-8') + b'\n')
    show(f.name, cell_width * len(cells), cell_height, 24)
    print('\n')


def test_fallback_font(qtext=None, bold=False, italic=False):
    set_logical_dpi(96.0, 96.0)
    set_font_family()
    trials = (qtext,) if qtext else ('你', 'He\u0347\u0305', '\U0001F929')
    for text in trials:
        f = get_fallback_font(text, bold, italic)
        try:
            print(text, f)
        except UnicodeEncodeError:
            sys.stdout.buffer.write((text + ' %s\n' % f).encode('utf-8'))


def showcase():
    change_wcwidth(True)
    f = 'monospace' if isosx else 'Liberation Mono'
    test_render_string('He\u0347\u0305llo\u0341, w\u0302or\u0306l\u0354d!', family=f)
    test_render_string('你好,世界', family=f)
    test_render_string('|\U0001F601|\U0001F64f|\U0001F63a|', family=f)
    test_render_string('A=>>B!=C', family='Fira Code')
