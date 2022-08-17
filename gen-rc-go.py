#!./kitty/launcher/kitty +launch
# License: GPLv3 Copyright: 2022, Kovid Goyal <kovid at kovidgoyal.net>

import os
import subprocess
import sys
from typing import List

import kitty.constants as kc
from kitty.cli import OptionDict, OptionSpecSeq, parse_option_spec
from kitty.rc.base import RemoteCommand, all_command_names, command_for_name


def serialize_as_go_string(x: str) -> str:
    return x.replace('\n', '\\n').replace('"', '\\"')


def replace(template: str, **kw: str) -> str:
    for k, v in kw.items():
        template = template.replace(k, v)
    return template


class Option:

    def __init__(self, x: OptionDict) -> None:
        flags = sorted(x['aliases'], key=len)
        short = ''
        if len(flags) > 1 and not flags[0].startswith("--"):
            short = flags[0][1:]
        long = flags[-1][2:]
        if not long:
            raise SystemExit(f'No long flag for {x} with flags {flags}')
        self.short, self.long = short, long
        self.usage = serialize_as_go_string(x['help'].strip())
        self.type = x['type']

    def to_flag_definition(self, base: str = 'ans.Flags()') -> str:
        if self.type == 'bool-set':
            if self.short:
                return f'{base}.BoolP("{self.long}", "{self.short}", false, "{self.usage}")'
            return f'{base}.Bool("{self.long}", false, "{self.usage}")'
        return ''


def build_go_code(name: str, cmd: RemoteCommand, seq: OptionSpecSeq, template: str) -> str:
    template = '\n' + template[len('//go:build exclude'):]
    NO_RESPONSE_BASE = 'true' if cmd.no_response else 'false'
    af: List[str] = []
    a = af.append
    for x in seq:
        if isinstance(x, str):
            continue
        o = Option(x)
        a(o.to_flag_definition())
    ans = replace(
        template,
        CMD_NAME=name, __FILE__=__file__, CLI_NAME=name.replace('_', '-'),
        SHORT_DESC=serialize_as_go_string(cmd.short_desc),
        LONG_DESC=serialize_as_go_string(cmd.desc.strip()),
        NO_RESPONSE_BASE=NO_RESPONSE_BASE, ADD_FLAGS_CODE='\n'.join(af))
    return ans


def main() -> None:
    if 'prewarmed' in getattr(sys, 'kitty_run_data'):
        os.environ.pop('KITTY_PREWARM_SOCKET')
        os.execlp(sys.executable, sys.executable, '+launch', __file__, *sys.argv[1:])
    with open('constants_generated.go', 'w') as f:
        dp = ", ".join(map(lambda x: f'"{serialize_as_go_string(x)}"', kc.default_pager_for_help))
        f.write(f'''\
// auto-generated by {__file__} do no edit

package kitty

type VersionType struct {{
    Major, Minor, Patch int
}}
var VersionString string = "{kc.str_version}"
var WebsiteBaseURL string = "{kc.website_base_url}"
var Version VersionType = VersionType{{Major: {kc.version.major}, Minor: {kc.version.minor}, Patch: {kc.version.patch},}}
var DefaultPager []string = []string{{ {dp} }}
var VCSRevision string = ""
var RC_ENCRYPTION_PROTOCOL_VERSION string = "{kc.RC_ENCRYPTION_PROTOCOL_VERSION}"
var IsFrozenBuild bool = false
''')
    with open('tools/cmd/at/template.go') as f:
        template = f.read()
    for name in all_command_names():
        cmd = command_for_name(name)
        opts = parse_option_spec(cmd.options_spec)[0]
        code = build_go_code(name, cmd, opts, template)
        dest = f'tools/cmd/at/{name}_generated.go'
        if os.path.exists(dest):
            os.remove(dest)
        with open(dest, 'w') as f:
            f.write(code)
        cp = subprocess.run('gofmt -s -w tools/cmd/at'.split())
        if cp.returncode != 0:
            raise SystemExit(cp.returncode)


if __name__ == '__main__':
    main()
