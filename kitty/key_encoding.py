#!/usr/bin/env python3
# vim:fileencoding=utf-8
# License: GPL v3 Copyright: 2017, Kovid Goyal <kovid at kovidgoyal.net>

from enum import IntEnum
from functools import lru_cache
from typing import Dict, NamedTuple, Optional, Tuple, Union

from . import fast_data_types as defines
from .fast_data_types import KeyEvent as WindowSystemKeyEvent
from .key_names import character_key_name_aliases, functional_key_name_aliases
from .types import ParsedShortcut

# number name mappings {{{
# start csi mapping (auto generated by gen-key-constants.py do not edit)
functional_key_number_to_name_map = {
    57344: 'ESCAPE',
    57345: 'ENTER',
    57346: 'TAB',
    57347: 'BACKSPACE',
    57348: 'INSERT',
    57349: 'DELETE',
    57350: 'LEFT',
    57351: 'RIGHT',
    57352: 'UP',
    57353: 'DOWN',
    57354: 'PAGE_UP',
    57355: 'PAGE_DOWN',
    57356: 'HOME',
    57357: 'END',
    57358: 'CAPS_LOCK',
    57359: 'SCROLL_LOCK',
    57360: 'NUM_LOCK',
    57361: 'PRINT_SCREEN',
    57362: 'PAUSE',
    57363: 'MENU',
    57364: 'F1',
    57365: 'F2',
    57366: 'F3',
    57367: 'F4',
    57368: 'F5',
    57369: 'F6',
    57370: 'F7',
    57371: 'F8',
    57372: 'F9',
    57373: 'F10',
    57374: 'F11',
    57375: 'F12',
    57376: 'F13',
    57377: 'F14',
    57378: 'F15',
    57379: 'F16',
    57380: 'F17',
    57381: 'F18',
    57382: 'F19',
    57383: 'F20',
    57384: 'F21',
    57385: 'F22',
    57386: 'F23',
    57387: 'F24',
    57388: 'F25',
    57389: 'F26',
    57390: 'F27',
    57391: 'F28',
    57392: 'F29',
    57393: 'F30',
    57394: 'F31',
    57395: 'F32',
    57396: 'F33',
    57397: 'F34',
    57398: 'F35',
    57399: 'KP_0',
    57400: 'KP_1',
    57401: 'KP_2',
    57402: 'KP_3',
    57403: 'KP_4',
    57404: 'KP_5',
    57405: 'KP_6',
    57406: 'KP_7',
    57407: 'KP_8',
    57408: 'KP_9',
    57409: 'KP_DECIMAL',
    57410: 'KP_DIVIDE',
    57411: 'KP_MULTIPLY',
    57412: 'KP_SUBTRACT',
    57413: 'KP_ADD',
    57414: 'KP_ENTER',
    57415: 'KP_EQUAL',
    57416: 'KP_SEPARATOR',
    57417: 'KP_LEFT',
    57418: 'KP_RIGHT',
    57419: 'KP_UP',
    57420: 'KP_DOWN',
    57421: 'KP_PAGE_UP',
    57422: 'KP_PAGE_DOWN',
    57423: 'KP_HOME',
    57424: 'KP_END',
    57425: 'KP_INSERT',
    57426: 'KP_DELETE',
    57427: 'MEDIA_PLAY',
    57428: 'MEDIA_PAUSE',
    57429: 'MEDIA_PLAY_PAUSE',
    57430: 'MEDIA_REVERSE',
    57431: 'MEDIA_STOP',
    57432: 'MEDIA_FAST_FORWARD',
    57433: 'MEDIA_REWIND',
    57434: 'MEDIA_TRACK_NEXT',
    57435: 'MEDIA_TRACK_PREVIOUS',
    57436: 'MEDIA_RECORD',
    57437: 'LOWER_VOLUME',
    57438: 'RAISE_VOLUME',
    57439: 'MUTE_VOLUME',
    57440: 'LEFT_SHIFT',
    57441: 'LEFT_CONTROL',
    57442: 'LEFT_ALT',
    57443: 'LEFT_SUPER',
    57444: 'LEFT_HYPER',
    57445: 'RIGHT_SHIFT',
    57446: 'RIGHT_CONTROL',
    57447: 'RIGHT_ALT',
    57448: 'RIGHT_SUPER',
    57449: 'RIGHT_HYPER',
    57450: 'ISO_LEVEL3_SHIFT',
    57451: 'ISO_LEVEL5_SHIFT'}
csi_number_to_functional_number_map = {
    2: 57348,
    3: 57349,
    5: 57354,
    6: 57355,
    7: 57356,
    8: 57357,
    9: 57346,
    11: 57364,
    12: 57365,
    13: 57345,
    14: 57367,
    15: 57368,
    17: 57369,
    18: 57370,
    19: 57371,
    20: 57372,
    21: 57373,
    23: 57374,
    24: 57375,
    27: 57344,
    127: 57347}
letter_trailer_to_csi_number_map = {'A': 57352, 'B': 57353, 'C': 57351, 'D': 57350, 'F': 8, 'H': 7, 'P': 11, 'Q': 12, 'R': 13, 'S': 14}
tilde_trailers = {57348, 57349, 57354, 57355, 57368, 57369, 57370, 57371, 57372, 57373, 57374, 57375}
# end csi mapping
# }}}


@lru_cache(2)
def get_name_to_functional_number_map() -> Dict[str, int]:
    return {v: k for k, v in functional_key_number_to_name_map.items()}


@lru_cache(2)
def get_functional_to_csi_number_map() -> Dict[int, int]:
    return {v: k for k, v in csi_number_to_functional_number_map.items()}


@lru_cache(2)
def get_csi_number_to_letter_trailer_map() -> Dict[int, str]:
    return {v: k for k, v in letter_trailer_to_csi_number_map.items()}


PRESS: int = 1
REPEAT: int = 2
RELEASE: int = 4


class EventType(IntEnum):
    PRESS = PRESS
    REPEAT = REPEAT
    RELEASE = RELEASE


@lru_cache(maxsize=128)
def parse_shortcut(spec: str) -> ParsedShortcut:
    if spec.endswith('+'):
        spec = spec[:-1] + 'plus'
    parts = spec.split('+')
    key_name = parts[-1]
    key_name = functional_key_name_aliases.get(key_name.upper(), key_name)
    is_functional_key = key_name.upper() in get_name_to_functional_number_map()
    if is_functional_key:
        key_name = key_name.upper()
    else:
        key_name = character_key_name_aliases.get(key_name.upper(), key_name)
    mod_val = 0
    if len(parts) > 1:
        mods = tuple(config_mod_map.get(x.upper(), SUPER << 8) for x in parts[:-1])
        for x in mods:
            mod_val |= x
    return ParsedShortcut(mod_val, key_name)


class KeyEvent(NamedTuple):
    type: EventType = EventType.PRESS
    mods: int = 0
    key: str = ''
    text: str = ''
    shifted_key: str = ''
    alternate_key: str = ''
    shift: bool = False
    alt: bool = False
    ctrl: bool = False
    super: bool = False

    def matches(self, spec: Union[str, ParsedShortcut], types: int = EventType.PRESS | EventType.REPEAT) -> bool:
        if not self.type & types:
            return False
        q = self.mods
        is_shifted = bool(self.shifted_key and self.shift)
        if is_shifted:
            q = self.mods & ~SHIFT
            kq = self.shifted_key
        else:
            kq = self.key
        if isinstance(spec, str):
            spec = parse_shortcut(spec)
        if q != spec.mods:
            return False
        return kq == spec.key_name

    def as_window_system_event(self) -> WindowSystemKeyEvent:
        action = defines.GLFW_PRESS
        if self.type is EventType.REPEAT:
            action = defines.GLFW_REPEAT
        elif self.type is EventType.RELEASE:
            action = defines.GLFW_RELEASE
        mods = 0
        if self.mods:
            if self.shift:
                mods |= defines.GLFW_MOD_SHIFT
            if self.alt:
                mods |= defines.GLFW_MOD_ALT
            if self.ctrl:
                mods |= defines.GLFW_MOD_CONTROL
            if self.super:
                mods |= defines.GLFW_MOD_SUPER

        fnm = get_name_to_functional_number_map()

        def as_num(key: str) -> int:
            return (fnm.get(key) or ord(key)) if key else 0

        return WindowSystemKeyEvent(
            key=as_num(self.key), shifted_key=as_num(self.shifted_key),
            alternate_key=as_num(self.alternate_key), mods=mods,
            action=action, text=self.text)


SHIFT, ALT, CTRL, SUPER = 1, 2, 4, 8
enter_key = KeyEvent(key='ENTER')
backspace_key = KeyEvent(key='BACKSPACE')
config_mod_map = {
    'SHIFT': SHIFT,
    'ALT': ALT,
    'OPTION': ALT,
    '⌥': ALT,
    '⌘': SUPER,
    'CMD': SUPER,
    'SUPER': SUPER,
    'CTRL': CTRL,
    'CONTROL': CTRL
}


def decode_key_event(csi: str, csi_type: str) -> KeyEvent:
    parts = csi.split(';')

    def get_sub_sections(x: str, missing: int = 0) -> Tuple[int, ...]:
        return tuple(int(y) if y else missing for y in x.split(':'))

    first_section = get_sub_sections(parts[0])
    second_section = get_sub_sections(parts[1], 1) if len(parts) > 1 else ()
    third_section = get_sub_sections(parts[2]) if len(parts) > 2 else ()
    mods = (second_section[0] - 1) if second_section else 0
    action = second_section[1] if len(second_section) > 1 else 1
    keynum = first_section[0]
    if csi_type in 'ABCDHFPQRS':
        keynum = letter_trailer_to_csi_number_map[csi_type]

    def key_name(num: int) -> str:
        if not num:
            return ''
        if num != 13:
            num = csi_number_to_functional_number_map.get(num, num)
            ans = functional_key_number_to_name_map.get(num)
        else:
            ans = 'ENTER' if csi_type == 'u' else 'F3'
        if ans is None:
            ans = chr(num)
        return ans

    return KeyEvent(
        mods=mods, shift=bool(mods & SHIFT), alt=bool(mods & ALT),
        ctrl=bool(mods & CTRL), super=bool(mods & SUPER),
        key=key_name(keynum),
        shifted_key=key_name(first_section[1] if len(first_section) > 1 else 0),
        alternate_key=key_name(first_section[2] if len(first_section) > 2 else 0),
        type={1: EventType.PRESS, 2: EventType.REPEAT, 3: EventType.RELEASE}[action],
        text=''.join(map(chr, third_section))
    )


def csi_number_for_name(key_name: str) -> int:
    if not key_name:
        return 0
    fn = get_name_to_functional_number_map().get(key_name)
    if fn is None:
        return ord(key_name)
    return get_functional_to_csi_number_map().get(fn, fn)


def encode_key_event(key_event: KeyEvent) -> str:
    key = csi_number_for_name(key_event.key)
    shifted_key = csi_number_for_name(key_event.shifted_key)
    alternate_key = csi_number_for_name(key_event.alternate_key)
    lt = get_csi_number_to_letter_trailer_map()
    if key_event.key == 'ENTER':
        trailer = 'u'
    else:
        trailer = lt.get(key, 'u')
    if trailer != 'u':
        key = 1
    mods = key_event.mods
    text = key_event.text
    ans = '\033['
    if key != 1 or mods or shifted_key or alternate_key or text:
        ans += f'{key}'
    if shifted_key or alternate_key:
        ans += ':' + (f'{shifted_key}' if shifted_key else '')
        if alternate_key:
            ans += f':{alternate_key}'
    action = 1
    if key_event.type is EventType.REPEAT:
        action = 2
    elif key_event.type is EventType.RELEASE:
        action = 3
    if mods or action > 1 or text:
        m = 0
        if key_event.shift:
            m |= 1
        if key_event.alt:
            m |= 2
        if key_event.ctrl:
            m |= 4
        if key_event.super:
            m |= 8
        if action > 1 or m:
            ans += f';{m+1}'
            if action > 1:
                ans += f':{action}'
        elif text:
            ans += ';'
    if text:
        ans += ';' + ':'.join(map(str, map(ord, text)))
    fn = get_name_to_functional_number_map().get(key_event.key)
    if fn is not None and fn in tilde_trailers:
        trailer = '~'
    return ans + trailer


def decode_key_event_as_window_system_key(text: str) -> Optional[WindowSystemKeyEvent]:
    csi, trailer = text[2:-1], text[-1]
    try:
        k = decode_key_event(csi, trailer)
    except Exception:
        return None
    return k.as_window_system_event()
