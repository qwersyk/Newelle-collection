from .extensions import NewelleExtension
from gi.repository import Gtk, Gio, GLib, Gdk
import re

class TimerExtension(NewelleExtension):
    name = "Timer"
    id = "timer"

    def get_replace_codeblocks_langs(self) -> list:
        return ["timer"]

    def get_additional_prompts(self) -> list:
        return [
            {
                "key": "timer",
                "setting_name": "timer",
                "title": "Timer Codeblocks",
                "description": "Allow creating timers from code blocks with title and duration",
                "editable": True,
                "show_in_settings": True,
                "default": True,
                "text": "Create timers with a single code block using language timer. Example:\n```timer\ntitle: Tea\nduration: 00:05:00\n```"
            }
        ]

    def add_tab_menu_entries(self) -> list:
        from .handlers import TabButtonDescription
        return [TabButtonDescription("Timer", "alarm-symbolic", lambda x, y: self._open_timer_tab(None, "", auto_start=False))]

    def get_gtk_widget(self, codeblock: str, lang: str) -> Gtk.Widget | None:
        if lang != "timer":
            return None
        cfg = self._parse_timer_block(codeblock)
        title = cfg.get("title") or "Timer"
        secs = max(0, int(cfg.get("seconds") or 0))
        card = Gtk.Button()
        card.add_css_class("flat")
        card.add_css_class("timer-chip")
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        icon = Gtk.Image.new_from_icon_name("alarm-symbolic")
        name = Gtk.Label(label=title, xalign=0)
        name.add_css_class("dim-label")
        name.set_hexpand(True)
        top.append(icon)
        top.append(name)
        time_lbl = Gtk.Label(xalign=0)
        time_lbl.add_css_class("timer-chip-time")
        time_lbl.set_text(self._format_hms(secs))
        v.append(top)
        v.append(time_lbl)
        card.set_child(v)
        css = Gtk.CssProvider()
        css.load_from_data(b"""
        .timer-chip {
            padding: 8px 10px;
            border-radius: 10px;
            border: 1px solid alpha(@theme_fg_color, 0.15);
            background: @theme_base_color;
        }
        .timer-chip-time {
            font-size: 18px;
            font-weight: 700;
        }
        """)
        Gtk.StyleContext.add_provider_for_display(card.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        card.set_tooltip_text("Open and start timer")
        card.connect("clicked", lambda _b: self._open_timer_tab(None, codeblock, auto_start=True))
        return card

    def _open_timer_tab(self, _btn, codeblock: str, auto_start: bool = False):
        cfg = self._parse_timer_block(codeblock)
        css = Gtk.CssProvider()
        css.load_from_data(b"""
        .timer-wrap {
            border: 1px solid alpha(@theme_fg_color, 0.15);
            border-radius: 12px;
            padding: 12px;
            background: @theme_base_color;
        }
        .timer-time {
            font-weight: 800;
            font-size: 56px;
            letter-spacing: 1px;
        }
        .timer-title {
            font-size: 14px;
            opacity: 0.85;
        }
        .timer-running {
            outline: 2px solid @accent_color;
            outline-offset: -2px;
            border-radius: 12px;
        }
        .timer-warning {
            outline: 2px solid #f39c12;
            outline-offset: -2px;
            border-radius: 12px;
        }
        .timer-finished {
            outline: 2px solid #2ecc71;
            outline-offset: -2px;
            border-radius: 12px;
            background-image: linear-gradient(180deg, alpha(#2ecc71,0.08), transparent);
        }
        .dim-label {
            opacity: 0.8;
        }
        .finish-card {
            background: @theme_base_color;
            border: 1px solid alpha(@theme_fg_color, 0.15);
            border-radius: 12px;
            padding: 16px;
        }
        .finish-title {
            font-size: 20px;
            font-weight: 700;
        }
        .finish-sub {
            opacity: 0.8;
        }
        """)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        state = {
            "title": (cfg.get("title") or "Timer").strip() or "Timer",
            "orig_seconds": max(0, cfg.get("seconds", 0)),
            "remaining": max(0, cfg.get("seconds", 0)),
            "tick_id": 0,
            "running": False,
            "finished": False,
            "blink_id": 0,
            "warn_threshold": 10
        }
        overlay = Gtk.Overlay()
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        overlay.set_child(scroller)
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, hexpand=True, vexpand=True)
        main.set_margin_top(10)
        main.set_margin_bottom(10)
        main.set_margin_start(10)
        main.set_margin_end(10)
        main.set_size_request(360, -1)
        scroller.set_child(main)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class("timer-wrap")
        main.append(card)
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title_entry = Gtk.Entry()
        title_entry.set_placeholder_text("Title")
        title_entry.set_text(state["title"])
        title_entry.add_css_class("timer-title")
        title_entry.set_hexpand(True)
        hdr.append(title_entry)
        btn_start = Gtk.Button()
        btn_start.set_tooltip_text("Start")
        btn_start.set_child(self._btn_content("media-playback-start-symbolic", "Start"))
        hdr.append(btn_start)
        card.append(hdr)
        time_display = Gtk.Label(xalign=0.5)
        time_display.add_css_class("timer-time")
        time_display.set_halign(Gtk.Align.CENTER)
        card.append(time_display)
        click_time = Gtk.GestureClick()
        click_time.connect("released", lambda *_: on_start_clicked(None))
        time_display.add_controller(click_time)
        progress = Gtk.LevelBar()
        progress.set_min_value(0.0)
        progress.set_max_value(1.0)
        progress.set_value(0.0)
        card.append(progress)
        section_lbl = Gtk.Label(label="Duration", xalign=0)
        section_lbl.add_css_class("dim-label")
        main.append(section_lbl)
        row_duration = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        sb_h = Gtk.SpinButton.new_with_range(0, 99, 1)
        sb_m = Gtk.SpinButton.new_with_range(0, 59, 1)
        sb_s = Gtk.SpinButton.new_with_range(0, 59, 1)
        for sb in (sb_h, sb_m, sb_s):
            sb.set_width_chars(2)
        row_duration.append(self._mini_labeled("h", sb_h))
        row_duration.append(self._mini_labeled("m", sb_m))
        row_duration.append(self._mini_labeled("s", sb_s))
        main.append(row_duration)
        row_presets = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for label, secs in [("1m", 60), ("5m", 300), ("10m", 600), ("25m", 1500)]:
            b = Gtk.Button(label=label)
            b.add_css_class("flat")
            b.connect("clicked", lambda _b, s=secs: set_seconds(s))
            row_presets.append(b)
        main.append(row_presets)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_reset = Gtk.Button()
        btn_reset.set_tooltip_text("Reset")
        btn_reset.add_css_class("flat")
        btn_reset.set_child(self._btn_content("view-refresh-symbolic", "Reset"))
        actions.append(btn_reset)
        btn_snooze = Gtk.Button()
        btn_snooze.set_tooltip_text("Snooze +5m")
        btn_snooze.add_css_class("flat")
        btn_snooze.set_child(self._btn_content("alarm-symbolic", "+5m"))
        btn_snooze.set_visible(False)
        actions.append(btn_snooze)
        main.append(actions)
        finish_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        finish_box.add_css_class("finish-card")
        finish_title = Gtk.Label(xalign=0.5)
        finish_title.add_css_class("finish-title")
        finish_sub = Gtk.Label(xalign=0.5)
        finish_sub.add_css_class("finish-sub")
        finish_title.set_text("Finished")
        finish_sub.set_text("")
        finish_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        finish_row.set_halign(Gtk.Align.CENTER)
        btn_again = Gtk.Button()
        btn_again.set_child(self._btn_content("media-playback-start-symbolic", "Again"))
        btn_again.add_css_class("suggested-action")
        btn_close = Gtk.Button()
        btn_close.add_css_class("flat")
        btn_close.set_child(self._btn_content("window-close-symbolic", "Close"))
        finish_row.append(btn_again)
        finish_row.append(btn_close)
        finish_box.append(finish_title)
        finish_box.append(finish_sub)
        finish_box.append(finish_row)
        overlay.add_overlay(finish_box)
        finish_box.set_halign(Gtk.Align.CENTER)
        finish_box.set_valign(Gtk.Align.CENTER)
        finish_box.set_visible(False)
        tab = self.ui_controller.add_tab(overlay)
        tab.set_icon(Gio.ThemedIcon.new("alarm-symbolic"))

        def set_seconds(total: int):
            total = max(0, int(total))
            state["orig_seconds"] = total
            state["remaining"] = total
            h = total // 3600
            m = (total % 3600) // 60
            s = total % 60
            sb_h.set_value(h)
            sb_m.set_value(m)
            sb_s.set_value(s)
            update_time_display()
            update_title()
            update_progress()
            update_styles()

        def spin_to_seconds() -> int:
            return int(sb_h.get_value()) * 3600 + int(sb_m.get_value()) * 60 + int(sb_s.get_value())

        def update_time_display():
            time_display.set_text(self._format_hms(state["remaining"]))

        def update_progress():
            total = state["orig_seconds"] or max(1, state["remaining"])
            done = total - state["remaining"]
            val = 0.0 if total <= 0 else max(0.0, min(1.0, done / total))
            progress.set_value(val)

        def update_title():
            clean_title = title_entry.get_text().strip() or "Timer"
            state["title"] = clean_title
            if state["finished"]:
                tab.set_title(f"{clean_title} – Done")
                return
            if state["running"]:
                tab.set_title(f"{clean_title} – {self._format_hms(state['remaining'])}")
            else:
                tab.set_title(f"{clean_title}")

        def update_styles():
            ctx = card.get_style_context()
            ctx.remove_class("timer-running")
            ctx.remove_class("timer-warning")
            ctx.remove_class("timer-finished")
            if state["finished"]:
                ctx.add_class("timer-finished")
            elif state["running"]:
                if state["remaining"] <= state["warn_threshold"]:
                    ctx.add_class("timer-warning")
                else:
                    ctx.add_class("timer-running")

        def start_blink():
            if state["blink_id"]:
                return
            def blink():
                cur = time_display.get_opacity()
                time_display.set_opacity(1.0 if cur < 0.6 else 0.4)
                return True
            state["blink_id"] = GLib.timeout_add(300, blink)

        def stop_blink():
            if state["blink_id"]:
                GLib.source_remove(state["blink_id"])
                state["blink_id"] = 0
            time_display.set_opacity(1.0)

        def play_sound():
            try:
                GLib.spawn_command_line_async("canberra-gtk-play -i bell")
                return
            except Exception:
                pass
            try:
                disp = Gdk.Display.get_default()
                if disp:
                    disp.beep()
            except Exception:
                pass

        def tick():
            if not state["running"]:
                return False
            if state["remaining"] <= 0:
                finish()
                return False
            state["remaining"] -= 1
            update_time_display()
            update_title()
            update_progress()
            update_styles()
            return True

        def start_timer():
            if state["remaining"] <= 0:
                state["orig_seconds"] = max(0, spin_to_seconds())
                state["remaining"] = state["orig_seconds"]
            if state["remaining"] <= 0:
                return
            state["running"] = True
            state["finished"] = False
            stop_blink()
            btn_start.set_tooltip_text("Pause")
            btn_start.set_child(self._btn_content("media-playback-pause-symbolic", "Pause"))
            btn_snooze.set_visible(False)
            finish_box.set_visible(False)
            title_entry.set_sensitive(False)
            for sb in (sb_h, sb_m, sb_s):
                sb.set_sensitive(False)
            update_title()
            update_styles()
            if state["tick_id"]:
                GLib.source_remove(state["tick_id"])
                state["tick_id"] = 0
            state["tick_id"] = GLib.timeout_add_seconds(1, tick)

        def pause_timer():
            state["running"] = False
            if state["tick_id"]:
                GLib.source_remove(state["tick_id"])
                state["tick_id"] = 0
            btn_start.set_tooltip_text("Start")
            btn_start.set_child(self._btn_content("media-playback-start-symbolic", "Start"))
            title_entry.set_sensitive(True)
            for sb in (sb_h, sb_m, sb_s):
                sb.set_sensitive(True)
            update_title()
            update_styles()

        def reset_timer():
            state["running"] = False
            state["finished"] = False
            if state["tick_id"]:
                GLib.source_remove(state["tick_id"])
                state["tick_id"] = 0
            stop_blink()
            state["remaining"] = state["orig_seconds"] if state["orig_seconds"] > 0 else spin_to_seconds()
            if state["orig_seconds"] == 0:
                state["orig_seconds"] = state["remaining"]
            btn_start.set_tooltip_text("Start")
            btn_start.set_child(self._btn_content("media-playback-start-symbolic", "Start"))
            btn_snooze.set_visible(False)
            finish_box.set_visible(False)
            title_entry.set_sensitive(True)
            for sb in (sb_h, sb_m, sb_s):
                sb.set_sensitive(True)
            update_time_display()
            update_title()
            update_progress()
            update_styles()

        def finish():
            state["running"] = False
            state["finished"] = True
            if state["tick_id"]:
                GLib.source_remove(state["tick_id"])
                state["tick_id"] = 0
            btn_start.set_tooltip_text("Start")
            btn_start.set_child(self._btn_content("media-playback-start-symbolic", "Start"))
            title_entry.set_sensitive(True)
            for sb in (sb_h, sb_m, sb_s):
                sb.set_sensitive(True)
            update_time_display()
            update_progress()
            update_title()
            update_styles()
            btn_snooze.set_visible(True)
            finish_title.set_text("Finished")
            finish_sub.set_text(state["title"])
            finish_box.set_visible(True)
            play_sound()
            start_blink()

        def on_start_clicked(_b):
            if state["running"]:
                pause_timer()
            else:
                if state["remaining"] == 0:
                    set_seconds(spin_to_seconds() or state["orig_seconds"] or 0)
                start_timer()

        btn_start.connect("clicked", on_start_clicked)

        def on_reset_clicked(_b):
            reset_timer()
        btn_reset.connect("clicked", on_reset_clicked)

        def on_snooze_clicked(_b):
            extra = 5 * 60
            now = state["remaining"]
            state["finished"] = False
            finish_box.set_visible(False)
            stop_blink()
            set_seconds((now if now > 0 else 0) + extra)
            start_timer()
        btn_snooze.connect("clicked", on_snooze_clicked)

        def on_again_clicked(_b):
            stop_blink()
            finish_box.set_visible(False)
            set_seconds(state["orig_seconds"] or spin_to_seconds())
            start_timer()
        btn_again.connect("clicked", on_again_clicked)

        def on_close_finish(_b):
            finish_box.set_visible(False)
        btn_close.connect("clicked", on_close_finish)

        def on_spin_changed(_s):
            if not state["running"]:
                state["orig_seconds"] = spin_to_seconds()
                state["remaining"] = state["orig_seconds"]
                update_time_display()
                update_title()
                update_progress()
                update_styles()
        for s in (sb_h, sb_m, sb_s):
            s.connect("value-changed", on_spin_changed)

        def on_title_changed(_e):
            update_title()
        title_entry.connect("changed", on_title_changed)

        if state["orig_seconds"] > 0:
            set_seconds(state["orig_seconds"])
        else:
            set_seconds(300)
        if auto_start:
            start_timer()
        def initial_focus():
            title_entry.grab_focus()
            return False
        GLib.idle_add(initial_focus)

    def _format_hms(self, t: int) -> str:
        t = max(0, int(t))
        h = t // 3600
        m = (t % 3600) // 60
        s = t % 60
        if h > 0:
            return f"{h:d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _mini_labeled(self, title: str, widget: Gtk.Widget) -> Gtk.Widget:
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        l = Gtk.Label(label=title, xalign=0.5)
        l.add_css_class("dim-label")
        l.set_halign(Gtk.Align.CENTER)
        widget.set_halign(Gtk.Align.CENTER)
        b.append(l)
        b.append(widget)
        return b

    def _btn_content(self, icon_name: str, text: str) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.append(Gtk.Image.new_from_icon_name(icon_name))
        box.append(Gtk.Label(label=text))
        return box

    def _parse_timer_block(self, text: str) -> dict:
        title = ""
        seconds = 0
        if not text:
            return {"title": title, "seconds": seconds}
        lines = [l.rstrip("\r\n") for l in text.splitlines()]
        headers = {}
        for l in lines:
            if ":" in l:
                k, v = l.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        title = headers.get("title", "") or ""
        dur = headers.get("duration", "") or ""
        def parse_duration(s: str) -> int:
            s = s.strip().lower()
            if not s:
                return 0
            if re.match(r"^\d{1,3}:\d{2}(:\d{2})?$", s):
                parts = [int(p) for p in s.split(":")]
                if len(parts) == 3:
                    h, m, sec = parts
                else:
                    h, m, sec = 0, parts[0], parts[1]
                return h * 3600 + m * 60 + sec
            total = 0
            for num, unit in re.findall(r"(\d+)\s*([hms])", s):
                num = int(num)
                if unit == "h":
                    total += num * 3600
                elif unit == "m":
                    total += num * 60
                elif unit == "s":
                    total += num
            if total == 0 and s.isdigit():
                total = int(s)
            return total
        seconds = max(0, parse_duration(dur))
        return {"title": title, "seconds": seconds}