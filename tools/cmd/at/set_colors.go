// License: GPLv3 Copyright: 2022, Kovid Goyal, <kovid at kovidgoyal.net>

package at

import (
	"bufio"
	"fmt"
	"os"
	"strings"

	"kitty/tools/utils"
	"kitty/tools/utils/style"
)

var nullable_colors = map[string]bool{
	// generated by gen-config.py do not edit
	// NULLABLE_COLORS_START
	"active_border_color":  true,
	"cursor":               true,
	"cursor_text_color":    true,
	"selection_background": true,
	"selection_foreground": true,
	"tab_bar_background":   true,
	"tab_bar_margin_color": true,
	"visual_bell_color":    true,
	// NULLABLE_COLORS_END
}

func set_color_in_color_map(key, val string, ans map[string]any, check_nullable, skip_nullable bool) error {
	if val == "none" {
		if check_nullable && !nullable_colors[key] {
			if skip_nullable {
				return nil
			}
			return fmt.Errorf("The color %s cannot be set to none", key)
		}
		ans[key] = nil
	} else {
		col, err := style.ParseColor(val)
		if err != nil {
			return fmt.Errorf("%s is not a valid color", val)
		}
		ans[key] = col.AsRGB()
	}
	return nil
}

func parse_colors_and_files(args []string) (map[string]any, error) {
	ans := make(map[string]any, len(args))
	for _, arg := range args {
		key, val, found := utils.Cut(strings.ToLower(arg), "=")
		if found {
			err := set_color_in_color_map(key, val, ans, true, false)
			if err != nil {
				return nil, err
			}
		} else {
			path := utils.Expanduser(arg)
			f, err := os.Open(path)
			if err != nil {
				return nil, err
			}
			defer f.Close()
			scanner := bufio.NewScanner(f)
			for scanner.Scan() {
				key, val, found := utils.Cut(scanner.Text(), " ")
				if found {
					set_color_in_color_map(strings.ToLower(key), strings.ToLower(strings.TrimSpace(val)), ans, true, true)
				}
			}
		}
	}
	return ans, nil
}
