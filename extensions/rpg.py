from .extensions import NewelleExtension
from gi.repository import Gtk, Gio, GLib
import json, threading, re

class RPGExtension(NewelleExtension):
    id = "rpg"
    name = "RPG"


    def get_replace_codeblocks_langs(self) -> list:
        return ["rpginit", "rpg"]

    def get_additional_prompts(self) -> list:
        return [
            {
                "key": "rpginit",
                "setting_name": "rpginit",
                "title": "RPG Init",
                "description": "Initialize the RPG panel and game state",
                "editable": True,
                "show_in_settings": True,
                "default": True,
                "text": "Use a single rpginit block to initialize the game panel. Provide YAML/JSON-like config.\nExample:\n```rpginit\ntitle: The Lost Cave\ninventory:\n- Torch\n- Rope\nstats:\n  HP: 10\n  Gold: 3\ntraits:\n- Brave\nachievements:\n- First Steps 🏅\n```"
            },
            {
                "key": "rpg",
                "setting_name": "rpg",
                "title": "RPG Question",
                "description": "Ask a question with options; optionally mutate state (stats/inventory/traits/achievements) or end the game.",
                "editable": True,
                "show_in_settings": True,
                "default": True,
                "text": "Example:\n```rpg\nquestion: Cave mouth wind howls. What do you do?\noptions:\n- 🕯️ Light the torch (HP -1)\n- 🗡️ Draw sword (Morale +1)\n- 🏃 Sneak inside (Stealth +1)\nallow_custom: true\nadd_inventory:\n- Torch\nadd_traits:\n- Limping\nadd_achievements:\n- First Steps 🏅\n# End instantly:\n# end: win|lose\n# end_title: Victory!\n# end_message: You found the relic.\n# stats_delta: HP:-1, Gold:+3\n```"
            }
        ]

    def get_gtk_widget(self, codeblock: str, lang: str) -> Gtk.Widget | None:

        
        return None

    def get_answer(self, codeblock: str, lang: str) -> str | None:
        if lang == "rpginit":
            self._panel_tab = None
            self._panel_root = None
            self._container = None
            self._content_box = None
            self._title_lbl = None
            self._stats_box = None
            self._inv_flow = None
            self._traits_box = None
            self._ach_list = None
            self._reveal_traits = None
            self._reveal_ach = None
            self._mounted = False
            self._pending_render = None
            self._active_wait = None
            self._state = {
                "title": "RPG",
                "inventory": [],
                "stats": {},
                "traits": [],
                "achievements": []
            }
            cfg_text = codeblock or ""
            self._on_init_clicked(cfg_text)
            return "The game has started."
            
        if lang != "rpg":
            return None

        q, options, allow_custom, mutations = self._parse_rpg_block(codeblock)

        if mutations:
            GLib.idle_add(self._apply_mutations, mutations)

        if "end" in mutations:
            status = str(mutations.get("end")).lower().strip()
            win = status == "win"
            title = mutations.get("end_title") or ("Victory! 🏆" if win else "Defeat 💀")
            msg = mutations.get("end_message") or ("You achieved your goal." if win else "Your journey ends here.")
            GLib.idle_add(self._render_end_screen, win, title, msg)
            return f"RPG End: {'WIN' if win else 'LOSE'}"

        sem = threading.Semaphore(0)
        result = {"value": None}

        def choose_callback(choice: str):
            if self._active_wait and self._active_wait.get("result") is result:
                result["value"] = choice
                self._active_wait["sem"].release()
                self._active_wait = None

        def render():
            if self._mounted and self._content_box is not None:
                self._render_question(q, options, allow_custom, choose_callback)
                self._pending_render = None
            else:
                self._pending_render = lambda: self._render_question(q, options, allow_custom, choose_callback)
            return False

        if self._active_wait:
            try:
                self._active_wait["result"]["value"] = "CANCELLED"
                self._active_wait["sem"].release()
            except Exception:
                pass
        self._active_wait = {"sem": sem, "result": result}

        GLib.idle_add(render)
        sem.acquire()
        return f"RPG Answer: {result['value']}"

    def _on_init_clicked(self, cfg_text: str):
        state = self._parse_init_config(cfg_text)
        self._state.update(state)
        if self._panel_root is None:
            self._build_panel(self._state)
        else:
            self._refresh_header(self._state)
            self._refresh_sections(self._state)
        if not self._mounted:
            self._panel_tab = self.ui_controller.add_tab(self._panel_root)
            self._panel_tab.set_icon(Gio.ThemedIcon.new("applications-games-symbolic"))
            self._panel_tab.set_title(self._state.get("title") or "RPG")
            self._mounted = True
        if self._pending_render:
            try:
                self._pending_render()
            except Exception:
                pass
            self._pending_render = None

    def _ensure_css(self, widget: Gtk.Widget):
        css = Gtk.CssProvider()
        css.load_from_data(b"""
        .rpg-title { font-weight: 800; font-size: 15px; letter-spacing: .2px; }
        .rpg-subtle { opacity: .8; }
        .rpg-chip { border-radius: 999px; padding: 3px 8px; background: alpha(@theme_fg_color, .07); }
        .rpg-chip > label { font-weight: 700; }
        .rpg-card { border-radius: 12px; padding: 10px; background: alpha(@theme_fg_color, .05); }

        .rpg-q { border-radius: 10px; padding: 10px; background: transparent; border: 1px solid alpha(@theme_fg_color, .12); }
        .rpg-q-title { font-weight: 900; font-size: 15px; }

        .rpg-opt { padding: 8px 10px; border-radius: 10px; background: alpha(@theme_bg_color, .7); }
        .rpg-opt:hover { background: alpha(@theme_fg_color, .12); }
        .rpg-submit { border-radius: 10px; padding: 8px 10px; background: linear-gradient(135deg, #FF7E5F, #F83E6D); color: white; }
        .rpg-submit label { color: white; font-weight: 800; }

        .rpg-end { border-radius: 14px; padding: 16px; background: linear-gradient(135deg, #22c55e, #16a34a); color: white; }
        .rpg-end.lose { background: linear-gradient(135deg, #ef4444, #b91c1c); }
        """)
        Gtk.StyleContext.add_provider_for_display(widget.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _build_panel(self, state):
        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True); scroller.set_vexpand(True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_margin_top(8); scroller.set_margin_bottom(8)
        scroller.set_margin_start(8); scroller.set_margin_end(8)

        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        container.set_size_request(260, -1)
        scroller.set_child(container)
        self._ensure_css(scroller)

        header_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        header_card.add_css_class("rpg-card")

        self._title_lbl = Gtk.Label(xalign=0)
        self._title_lbl.add_css_class("rpg-title")
        sub = Gtk.Label(xalign=0)
        sub.add_css_class("rpg-subtle")
        header_card.append(self._title_lbl)
        header_card.append(sub)

        stats_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header_card.append(stats_row)
        self._stats_box = stats_row

        inv_header, inv_rev, inv_flow_container = self._section("Inventory 🎒")
        inv_flow = Gtk.FlowBox()
        inv_flow.set_valign(Gtk.Align.START)
        inv_flow.set_max_children_per_line(3)
        inv_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        inv_flow.set_column_spacing(6)
        inv_flow.set_row_spacing(6)
        inv_flow_container.append(inv_flow)
        self._inv_flow = inv_flow

        traits_header, traits_rev, traits_box = self._section("Traits 🧩")
        self._traits_box = traits_box
        self._reveal_traits = traits_rev

        ach_header, ach_rev, ach_box = self._section("Achievements 🏆")
        self._ach_list = ach_box
        self._reveal_ach = ach_rev

        self._content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        container.append(header_card)
        container.append(inv_header); container.append(inv_rev)
        container.append(traits_header); container.append(traits_rev)
        container.append(ach_header); container.append(ach_rev)
        container.append(self._content_box)

        self._panel_root = scroller
        self._container = container
        self._refresh_header(state)
        self._refresh_sections(state)

    def _section(self, title_text: str):
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        title = Gtk.Label(label=title_text, xalign=0); title.add_css_class("rpg-title"); title.set_hexpand(True)
        toggle = Gtk.Button(); toggle.add_css_class("pill"); toggle.add_css_class("flat")
        toggle.set_child(Gtk.Label(label="▼"))
        header.append(title); header.append(toggle)
        rev = Gtk.Revealer(); rev.set_reveal_child(True)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        body.set_margin_start(4); body.set_margin_end(4); body.set_margin_bottom(6)
        rev.set_child(body)
        def on_toggle(_b):
            rev.set_reveal_child(not rev.get_reveal_child())
            lbl = "▲" if rev.get_reveal_child() else "▼"
            toggle.set_child(Gtk.Label(label=lbl))
        toggle.connect("clicked", on_toggle)
        return header, rev, body

    def _refresh_header(self, state):
        if self._title_lbl:
            self._title_lbl.set_text(state.get("title") or "RPG")
        inv_count = len(state.get("inventory") or [])
        stats_count = len((state.get("stats") or {}).keys())
        parent = self._title_lbl.get_parent()
        if parent and len(list(parent)) >= 2:
            children = list(parent)
            if isinstance(children[1], Gtk.Label):
                children[1].set_text(f"Stats: {stats_count} · Inventory: {inv_count}")

        if self._stats_box:
            for c in list(self._stats_box):
                self._stats_box.remove(c)
            for k, v in (state.get("stats") or {}).items():
                self._stats_box.append(self._chip(f"{k}: {v}", "emblem-default"))

    def _refresh_sections(self, state):
        if self._inv_flow:
            for c in list(self._inv_flow):
                self._inv_flow.remove(c)
            for item in (state.get("inventory") or []):
                pill = self._pill(self._decorate_inventory(item))
                child = Gtk.FlowBoxChild(); child.set_child(pill)
                self._inv_flow.append(child)

        if self._traits_box:
            for c in list(self._traits_box):
                self._traits_box.remove(c)
            for t in (state.get("traits") or []):
                self._traits_box.append(self._chip(t, "dialog-information-symbolic"))

        if self._ach_list:
            for c in list(self._ach_list):
                self._ach_list.remove(c)
            for a in (state.get("achievements") or []):
                self._ach_list.append(self._chip(a, "emblem-ok-symbolic"))
            if not self._ach_list.get_first_child():
                self._ach_list.append(Gtk.Label(label="No achievements yet", xalign=0))

    def _chip(self, text, icon_name):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.add_css_class("rpg-chip")
        icon = Gtk.Image.new_from_icon_name(icon_name)
        lbl = Gtk.Label(label=text)
        box.append(icon); box.append(lbl)
        return box

    def _pill(self, text):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.add_css_class("rpg-chip")
        lbl = Gtk.Label(label=text)
        box.append(lbl)
        return box

    def _decorate_inventory(self, name: str) -> str:
        nm = name.strip()
        mapping = {
            "torch": "🕯️ Torch",
            "rope": "🧵 Rope",
            "potion": "🧪 Potion",
            "sword": "🗡️ Sword",
            "shield": "🛡️ Shield",
            "key": "🗝️ Key",
            "map": "🗺️ Map",
        }
        base = mapping.get(nm.lower())
        return base or (f"🎒 {nm}")

    def _render_question(self, question: str, options: list[str], allow_custom: bool, on_choose):
        if self._content_box is None:
            return
        for c in list(self._content_box):
            self._content_box.remove(c)

        qcard = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        qcard.add_css_class("rpg-q")
        qtitle = Gtk.Label(label=(question or "What do you do?"), xalign=0)
        qtitle.add_css_class("rpg-q-title")
        qtitle.set_wrap(True)
        qcard.append(qtitle)
        self._content_box.append(qcard)

        opts_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._content_box.append(opts_box)

        def choose(value: str):
            for child in list(opts_box):
                if isinstance(child, Gtk.Button):
                    child.set_sensitive(False)
                if isinstance(child, Gtk.Box):
                    for ch in list(child):
                        if isinstance(ch, Gtk.Button) or isinstance(ch, Gtk.Entry):
                            ch.set_sensitive(False)
            on_choose(value)
        for opt in options:
            b = Gtk.Button()
            b.add_css_class("rpg-opt")
            b.set_child(Gtk.Label(label=opt))
            b.connect("clicked", lambda _b, v=opt: choose(v))
            opts_box.append(b)

        if allow_custom:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            e = Gtk.Entry(); e.set_placeholder_text("Type your own action…")
            e.set_hexpand(True)
            submit = Gtk.Button(); submit.add_css_class("rpg-submit"); submit.set_child(Gtk.Label(label="Submit"))
            def do_submit(_b=None):
                val = (e.get_text() or "").strip()
                if val:
                    choose(val)
            submit.connect("clicked", do_submit)
            e.connect("activate", do_submit)
            row.append(e); row.append(submit)
            opts_box.append(row)

        self._scroll_panel_to_top()

    def _scroll_panel_to_top(self):
        w = self._content_box
        parent = None
        while w is not None and not isinstance(w, Gtk.ScrolledWindow):
            w = w.get_parent()
            parent = w
        if isinstance(w, Gtk.ScrolledWindow):
            vadj = w.get_vadjustment()
            GLib.idle_add(lambda: vadj.set_value(0), priority=GLib.PRIORITY_LOW)

    def _render_end_screen(self, win: bool, title: str, message: str):
        if self._content_box is None:
            return False
        for c in list(self._content_box):
            self._content_box.remove(c)
        wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        wrap.add_css_class("rpg-end")
        if not win:
            wrap.add_css_class("lose")
        emoji = Gtk.Label(label=("🏆" if win else "💀"), xalign=0.5)
        emoji.set_margin_bottom(4)
        h = Gtk.Label(label=title, xalign=0.5); h.add_css_class("rpg-title")
        p = Gtk.Label(label=message, xalign=0.5); p.add_css_class("rpg-subtle"); p.set_wrap(True)
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        restart = Gtk.Button(); restart.add_css_class("rpg-submit")
        restart.set_child(Gtk.Label(label="New Game"))
        def do_restart(_b):
            self._reset_game(keep_achievements=True)
        
        restart.connect("clicked", do_restart)
        wrap.append(emoji); wrap.append(h); wrap.append(p); wrap.append(btn_row)
        self._content_box.append(wrap)
        return False

    def _reset_game(self, keep_achievements: bool = True):
        keep_ach = list(self._state.get("achievements") or []) if keep_achievements else []
        title = self._state.get("title")
        self._state = {"title": title or "RPG", "inventory": [], "stats": {}, "traits": [], "achievements": keep_ach}
        self._refresh_header(self._state)
        self._refresh_sections(self._state)
        if self._content_box:
            for c in list(self._content_box):
                self._content_box.remove(c)

    def _apply_mutations(self, m):
        changed = False
        if "stats_delta" in m:
            for k, dv in m["stats_delta"].items():
                cur = self._state["stats"].get(k, 0)
                try:
                    cur = int(cur)
                except Exception:
                    try:
                        cur = float(cur)
                    except Exception:
                        cur = 0
                self._state["stats"][k] = cur + dv
                changed = True
        if "set_stats" in m:
            for k, v in m["set_stats"].items():
                self._state["stats"][k] = v
                changed = True
        if "add_inventory" in m:
            for it in m["add_inventory"]:
                if it not in self._state["inventory"]:
                    self._state["inventory"].append(it)
                    changed = True
        if "remove_inventory" in m:
            for it in m["remove_inventory"]:
                if it in self._state["inventory"]:
                    self._state["inventory"].remove(it)
                    changed = True
        if "add_traits" in m:
            for t in m["add_traits"]:
                if t not in self._state["traits"]:
                    self._state["traits"].append(t)
                    changed = True
        if "remove_traits" in m:
            for t in m["remove_traits"]:
                if t in self._state["traits"]:
                    self._state["traits"].remove(t)
                    changed = True
        if "add_achievements" in m:
            for a in m["add_achievements"]:
                if a not in self._state["achievements"]:
                    self._state["achievements"].append(a)
                    changed = True
        if changed:
            self._refresh_header(self._state)
            self._refresh_sections(self._state)
        return False

    def _parse_init_config(self, text: str) -> dict:
        text = text or ""
        try:
            data = json.loads(text)
            return {
                "title": data.get("title") or "RPG",
                "inventory": list(data.get("inventory") or []),
                "stats": dict(data.get("stats") or {}),
                "traits": list(data.get("traits") or []),
                "achievements": list(data.get("achievements") or []),
            }
        except Exception:
            pass
        cfg = {"title": "RPG", "inventory": [], "stats": {}, "traits": [], "achievements": []}
        lines = [l.rstrip() for l in text.splitlines()]
        mode = None
        for line in lines:
            if not line.strip():
                continue
            if line.strip().endswith(":"):
                key = line.strip()[:-1].strip().lower()
                if key in ("inventory", "stats", "traits", "achievements"):
                    mode = key
                else:
                    mode = None
                continue
            if mode == "inventory" and line.strip().startswith("-"):
                cfg["inventory"].append(line.split("-", 1)[1].strip()); continue
            if mode == "traits" and line.strip().startswith("-"):
                cfg["traits"].append(line.split("-", 1)[1].strip()); continue
            if mode == "achievements" and line.strip().startswith("-"):
                cfg["achievements"].append(line.split("-", 1)[1].strip()); continue
            if mode == "stats" and ":" in line:
                k, v = line.split(":", 1); cfg["stats"][k.strip()] = self._num_or_str(v.strip()); continue
            if ":" in line:
                k, v = line.split(":", 1)
                if k.strip().lower() == "title":
                    cfg["title"] = v.strip() or "RPG"
        return cfg

    def _parse_rpg_block(self, text: str):
        text = text or ""
        question = ""
        options = []
        allow_custom = False
        mutations = {}
        lines = [l.rstrip() for l in text.splitlines() if l.strip()]

        def parse_list(after_idx):
            out = []
            i = after_idx + 1
            while i < len(lines) and lines[i].lstrip().startswith("-"):
                out.append(lines[i].split("-", 1)[1].strip())
                i += 1
            return out, i

        i = 0
        in_opts = False
        while i < len(lines):
            l = lines[i]
            low = l.lower()
            if low.startswith("question:"):
                question = l.split(":", 1)[1].strip()
            elif low.startswith("options:"):
                in_opts = True
                options, i = parse_list(i)
                continue
            elif l.lstrip().startswith("-") and in_opts:
                options.append(l.split("-", 1)[1].strip())
            elif low.startswith("allow_custom:"):
                allow_custom = l.split(":", 1)[1].strip().lower() in ("true", "1", "yes", "y")
            elif low.startswith("end:"):
                mutations["end"] = l.split(":", 1)[1].strip()
            elif low.startswith("end_title:"):
                mutations["end_title"] = l.split(":", 1)[1].strip()
            elif low.startswith("end_message:"):
                mutations["end_message"] = l.split(":", 1)[1].strip()
            elif low.startswith("add_inventory:"):
                mutations["add_inventory"] = parse_list(i)
            elif low.startswith("remove_inventory:"):
                mutations["remove_inventory"] = parse_list(i)
            elif low.startswith("add_traits:"):
                mutations["add_traits"] = parse_list(i)
            elif low.startswith("remove_traits:"):
                mutations["remove_traits"] = parse_list(i)
            elif low.startswith("add_achievements:"):
                mutations["add_achievements"] = parse_list(i)
            elif low.startswith("stats_delta:"):
                ds = l.split(":", 1)[1].strip()
                mutations["stats_delta"] = self._parse_stats_delta(ds)
            elif low.startswith("set_stats:"):
                j = i + 1
                sets = {}
                while j < len(lines) and ":" in lines[j] and not lines[j].lower().startswith((
                    "question:", "options:", "allow_custom:", "end:", "add_", "remove_", "stats_delta:", "set_stats:", "end_title:", "end_message:"
                )):
                    kk, vv = lines[j].split(":", 1)
                    sets[kk.strip()] = self._num_or_str(vv.strip())
                    j += 1
                if sets:
                    mutations["set_stats"] = sets
            elif not question and ":" not in l and not l.lstrip().startswith("-"):
                question = l
            i += 1

        if not question and lines:
            question = lines[0]

        return question or "What do you do?", options, allow_custom, mutations

    def _parse_stats_delta(self, s: str) -> dict:
        d = {}
        for part in s.split(","):
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                k, v = part.split(":", 1)
                d[k.strip()] = self._num_or_str(v.strip(), allow_signed=True)
        return d

    def _num_or_str(self, v: str, allow_signed: bool = False):
        if re.fullmatch(r"[+-]?\d+", v if allow_signed else v.lstrip("+")):
            try: return int(v)
            except Exception: pass
        if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", v if allow_signed else v.lstrip("+")):
            try: return float(v)
            except Exception: pass
        return v
