from .extensions import NewelleExtension
from gi.repository import Gtk, Gio, GLib, Gdk
import cairo

class InteractiveMindMapExtension(NewelleExtension):
    name = "Interactive Mind Map"
    id = "interactive_mind_map"

    def get_replace_codeblocks_langs(self) -> list:
        return ["mindmap"]

    def get_additional_prompts(self) -> list:
        return [
            {
                "key": "mindmap",
                "setting_name": "mindmap",
                "title": "Interactive Mind Map",
                "description": "Enable interactive mind maps parsed from code blocks.",
                "editable": True,
                "show_in_settings": True,
                "default": True,
                "text": "To create an interactive mind map, output only a code block with language mindmap. Use a single root and indented bullet lines with two spaces per level. Do not add any explanation before or after the code block.\nExample:\n```mindmap\n- Project\n  - Planning\n    - Timeline\n    - Budget\n  - Execution\n    - Tasks\n    - Risks\n  - Review\n    - Retrospective\n```"
            }
        ]

    def get_gtk_widget(self, codeblock: str, lang: str) -> Gtk.Widget | None:
        if lang != "mindmap":
            return None
        b = Gtk.Button()
        b.add_css_class("suggested-action")
        b.add_css_class("pill")
        b.set_tooltip_text("Open Mind Map")
        b.set_child(Gtk.Image.new_from_icon_name("view-grid-symbolic"))
        b.connect("clicked", self._open_mindmap_tab, codeblock)
        return b

    def _open_mindmap_tab(self, _btn, codeblock: str):
        data = self._parse_mindmap(codeblock)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, vexpand=True)
        root.set_focusable(True)

        drawing = Gtk.DrawingArea()
        drawing.set_hexpand(True)
        drawing.set_vexpand(True)

        overlay = Gtk.Overlay()
        fixed = Gtk.Fixed()
        overlay.set_child(drawing)
        overlay.add_overlay(fixed)

        state = {
            "nodes": [],
            "edges": [],
            "roots": [],
            "fixed": fixed,
            "drawing": drawing,
            "scale": 1.0,
            "min_scale": 0.02,
            "max_scale": 5.0,
            "ox": 40.0,
            "oy": 40.0,
            "ctrl": False,
            "space": False,
            "shift": False,
            "pointer": (0.0, 0.0),
            "css_provider": Gtk.CssProvider(),
            "layer_depth": 99,
            "max_depth_tree": 0
        }

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, hexpand=True, vexpand=False)
        toolbar.add_css_class("toolbar")
        toolbar.set_margin_top(6)
        toolbar.set_margin_bottom(6)
        toolbar.set_margin_start(8)
        toolbar.set_margin_end(8)

        def icon_button(name, tooltip, cb):
            btn = Gtk.Button()
            btn.add_css_class("flat")
            btn.set_tooltip_text(tooltip)
            btn.set_child(Gtk.Image.new_from_icon_name(name))
            btn.connect("clicked", cb)
            return btn

        btn_layout = icon_button("view-refresh-symbolic", "Auto layout", lambda *_: auto_layout())
        btn_layer_minus = icon_button("go-previous-symbolic", "Collapse one layer", lambda *_: collapse_one_layer())
        btn_layer_plus = icon_button("go-next-symbolic", "Expand one layer", lambda *_: expand_one_layer())
        btn_fit = icon_button("zoom-fit-best-symbolic", "Fit to view", lambda *_: fit_view())
        btn_zoom_out = icon_button("zoom-out-symbolic", "Zoom out", lambda *_: zoom_step(0.9, state["pointer"]))
        btn_zoom_reset = icon_button("zoom-original-symbolic", "Reset zoom", lambda *_: set_zoom(1.0, anchor_center()))
        btn_zoom_in = icon_button("zoom-in-symbolic", "Zoom in", lambda *_: zoom_step(1.1, state["pointer"]))
        
        nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        btn_up = icon_button("go-up-symbolic", "Move up", lambda *_: pan_direction(0, 50))
        btn_down = icon_button("go-down-symbolic", "Move down", lambda *_: pan_direction(0, -50))
        btn_left = icon_button("go-previous-symbolic", "Move left", lambda *_: pan_direction(50, 0))
        btn_right = icon_button("go-next-symbolic", "Move right", lambda *_: pan_direction(-50, 0))
        
        nav_box.append(btn_up)
        nav_box.append(btn_down)
        nav_box.append(btn_left)
        nav_box.append(btn_right)

        toolbar.append(btn_layout)
        toolbar.append(btn_layer_minus)
        toolbar.append(btn_layer_plus)
        toolbar.append(Gtk.Separator.new(Gtk.Orientation.VERTICAL))
        toolbar.append(nav_box)
        toolbar.append(Gtk.Separator.new(Gtk.Orientation.VERTICAL))
        toolbar.append(btn_fit)
        toolbar.append(btn_zoom_out)
        toolbar.append(btn_zoom_reset)
        toolbar.append(btn_zoom_in)

        root.append(toolbar)
        root.append(overlay)

        def pan_direction(dx, dy):
            state["ox"] += dx
            state["oy"] += dy
            refresh_positions()

        def update_css_for_scale():
            s = state["scale"]
            fs = max(6.0, min(18.0, 13.0 * s))
            pad_y = max(1.0, min(10.0, 6.0 * s))
            pad_x = max(4.0, min(18.0, 10.0 * s))
            min_h = max(14.0, min(28.0, 18.0 * s))
            min_w = max(18.0, min(60.0, 40.0 * s))
            radius = max(6.0, min(14.0, 10.0 * s))
            css = f"""
            .mindmap-node {{
                opacity: 1.0;
                font-size: {fs}px;
                padding: {pad_y}px {pad_x}px;
                min-height: {min_h}px;
                min-width: {min_w}px;
                border-radius: {radius}px;
                border-width: 1px;
                background-color: @theme_bg_color;
                color: @theme_fg_color;
            }}
            """
            state["css_provider"].load_from_data(css.encode("utf-8"))
            display = root.get_display()
            Gtk.StyleContext.add_provider_for_display(display, state["css_provider"], Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        def toggle_children_visibility(node):
            if not node["children"]:
                return
            
            node["collapsed"] = not node["collapsed"]
            
            def set_descendants_visible(n, visible):
                for child in n["children"]:
                    child["widget"].set_visible(visible)
                    if visible and not child["collapsed"]:
                        set_descendants_visible(child, True)
                    else:
                        set_descendants_visible(child, False)
            
            if node["collapsed"]:
                set_descendants_visible(node, False)
            else:
                set_descendants_visible(node, True)
            
            auto_layout()

        def build_nodes():
            state["nodes"].clear()
            state["edges"].clear()
            state["roots"].clear()
            state["max_depth_tree"] = 0

            def mk(item, parent, depth):
                state["max_depth_tree"] = max(state["max_depth_tree"], depth)
                n = {
                    "title": item["title"],
                    "children": [],
                    "parent": parent,
                    "collapsed": False,
                    "x": 0.0,
                    "y": 0.0,
                    "widget": None,
                    "depth": depth,
                }
                btn = Gtk.Button(label=n["title"])
                btn.add_css_class("mindmap-node")
                btn.add_css_class("pill")
                btn.set_focusable(False)

                def on_button_clicked(_button, node=n):
                    toggle_children_visibility(node)

                btn.connect("clicked", on_button_clicked)

                n["widget"] = btn
                state["nodes"].append(n)
                if parent:
                    parent["children"].append(n)
                    state["edges"].append((parent, n))
                else:
                    state["roots"].append(n)

                fixed.put(btn, 0, 0)

                for ch in item["children"]:
                    mk(ch, n, depth + 1)

            for r in data:
                mk(r, None, 0)

            state["layer_depth"] = min(2, state["max_depth_tree"])

        def node_size(n):
            w = n["widget"].get_allocated_width() or 80
            h = n["widget"].get_allocated_height() or 24
            return w, h

        def node_center(n):
            w, h = node_size(n)
            return n["x"] + (w * 0.5) / state["scale"], n["y"] + (h * 0.5) / state["scale"]

        def refresh_positions():
            for n in state["nodes"]:
                sx = int(state["ox"] + n["x"] * state["scale"])
                sy = int(state["oy"] + n["y"] * state["scale"])
                state["fixed"].move(n["widget"], sx, sy)
            drawing.queue_draw()

        def place_node(n):
            sx = int(state["ox"] + n["x"] * state["scale"])
            sy = int(state["oy"] + n["y"] * state["scale"])
            state["fixed"].move(n["widget"], sx, sy)

        def recompute_visibility():
            for n in state["nodes"]:
                n["widget"].set_visible(False)
            
            def walk(n, parent_visible):
                visible = parent_visible and (n["depth"] <= state["layer_depth"])
                n["widget"].set_visible(visible)
                if not visible:
                    return
                if n["collapsed"]:
                    return
                for c in n["children"]:
                    walk(c, True)
            
            for r in state["roots"]:
                walk(r, True)
            drawing.queue_draw()

        def collapse_one_layer():
            state["layer_depth"] = max(0, state["layer_depth"] - 1)
            recompute_visibility()
            auto_layout()

        def expand_one_layer():
            state["layer_depth"] = min(state["max_depth_tree"], state["layer_depth"] + 1)
            recompute_visibility()
            auto_layout()

        def auto_layout():
            visibles = [n for n in state["nodes"] if n["widget"].get_visible()]
            if not visibles:
                refresh_positions()
                return

            depths = {}
            for n in visibles:
                depths.setdefault(n["depth"], []).append(n)

            col_gap_world = 40.0
            col_width_world = {}
            for d, nodes_d in depths.items():
                max_w_px = 0
                for n in nodes_d:
                    w, _ = node_size(n)
                    if w > max_w_px:
                        max_w_px = w
                col_width_world[d] = max(80.0, max_w_px / state["scale"])

            x_at_depth = {}
            mx = 40.0
            acc = mx
            max_d = max(depths.keys()) if depths else 0
            for d in range(0, max_d + 1):
                w = col_width_world.get(d, 100.0)
                x_at_depth[d] = acc + w * 0.5
                acc += w + col_gap_world

            avg_h_px = sum(node_size(n)[1] for n in visibles) / max(1, len(visibles))
            row_h_world = max(26.0, (avg_h_px + 12.0) / state["scale"])

            def layout_subtree(n, cursor):
                if not n["widget"].get_visible():
                    return None
                vis_children = [c for c in n["children"] if c["widget"].get_visible()]
                if n["collapsed"] or not vis_children:
                    y = cursor[0]
                    cursor[0] += row_h_world
                else:
                    ys = []
                    for c in vis_children:
                        yc = layout_subtree(c, cursor)
                        if yc is not None:
                            ys.append(yc)
                    y = (sum(ys) / len(ys)) if ys else cursor[0]
                n["x"] = x_at_depth.get(n["depth"], mx)
                n["y"] = y
                return y

            cursor = [40.0]
            for r in state["roots"]:
                if r["widget"].get_visible():
                    layout_subtree(r, cursor)

            refresh_positions()

        def bounds_world():
            vs = [n for n in state["nodes"] if n["widget"].get_visible()]
            if not vs:
                return 0.0, 0.0, 1.0, 1.0
            minx = min(n["x"] for n in vs)
            miny = min(n["y"] for n in vs)
            maxx = max(n["x"] + node_size(n)[0] / state["scale"] for n in vs)
            maxy = max(n["y"] + node_size(n)[1] / state["scale"] for n in vs)
            return minx, miny, maxx, maxy

        def anchor_center():
            w = drawing.get_allocated_width()
            h = drawing.get_allocated_height()
            return (w * 0.5, h * 0.5)

        def set_zoom(z, anchor=None):
            z = max(state["min_scale"], min(state["max_scale"], z))
            if anchor is None:
                state["scale"] = z
                update_css_for_scale()
                refresh_positions()
                return
            ax, ay = anchor
            wx = (ax - state["ox"]) / state["scale"]
            wy = (ay - state["oy"]) / state["scale"]
            state["scale"] = z
            update_css_for_scale()
            state["ox"] = ax - wx * state["scale"]
            state["oy"] = ay - wy * state["scale"]
            refresh_positions()

        def zoom_step(f, anchor=None):
            if anchor is None:
                anchor = state["pointer"]
            set_zoom(state["scale"] * f, anchor)

        def fit_view():
            alloc_w = drawing.get_allocated_width()
            alloc_h = drawing.get_allocated_height()
            if alloc_w <= 0 or alloc_h <= 0:
                return
            x0, y0, x1, y1 = bounds_world()
            w = max(1.0, x1 - x0)
            h = max(1.0, y1 - y0)
            pad = 120.0
            sx = (alloc_w - pad) / w
            sy = (alloc_h - pad) / h
            z = max(state["min_scale"], min(state["max_scale"], min(sx, sy)))
            state["scale"] = z
            update_css_for_scale()
            state["ox"] = (alloc_w - w * z) * 0.5 - x0 * z
            state["oy"] = (alloc_h - h * z) * 0.5 - y0 * z
            refresh_positions()

        def draw_func(_a, cr: cairo.Context, _w, _h):
            cr.save()
            cr.translate(state["ox"], state["oy"])
            cr.scale(state["scale"], state["scale"])
            cr.set_line_width(1.0 / state["scale"])
            cr.set_source_rgba(0.35, 0.35, 0.40, 0.8)
            for p, c in state["edges"]:
                if (not p["widget"].get_visible()) or (not c["widget"].get_visible()):
                    continue
                px, py = node_center(p)
                cx, cy = node_center(c)
                mx = (px + cx) / 2.0
                cr.move_to(px, py)
                cr.curve_to(mx, py, mx, cy, cx, cy)
                cr.stroke()
            cr.restore()

        drawing.set_draw_func(draw_func)

        pan_mid = Gtk.GestureDrag()
        pan_mid.set_button(2)
        def pan_begin_mid(_g, _x, _y):
            state["_p_ox"] = state["ox"]
            state["_p_oy"] = state["oy"]
        def pan_update_mid(_g, dx, dy):
            state["ox"] = state["_p_ox"] + dx
            state["oy"] = state["_p_oy"] + dy
            refresh_positions()
        pan_mid.connect("drag-begin", pan_begin_mid)
        pan_mid.connect("drag-update", pan_update_mid)
        drawing.add_controller(pan_mid)

        pan_left = Gtk.GestureDrag()
        pan_left.set_button(1)
        def pan_begin_left(_g, _x, _y):
            state["_p_ox"] = state["ox"]
            state["_p_oy"] = state["oy"]
        def pan_update_left(_g, dx, dy):
            state["ox"] = state["_p_ox"] + dx
            state["oy"] = state["_p_oy"] + dy
            refresh_positions()
        pan_left.connect("drag-begin", pan_begin_left)
        pan_left.connect("drag-update", pan_update_left)
        drawing.add_controller(pan_left)

        motion = Gtk.EventControllerMotion()
        def on_motion(_c, x, y):
            state["pointer"] = (x, y)
        motion.connect("motion", on_motion)
        drawing.add_controller(motion)

        scroll = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL
            | Gtk.EventControllerScrollFlags.HORIZONTAL
            | Gtk.EventControllerScrollFlags.DISCRETE
        )
        def on_scroll(_c, dx, dy):
            if state["ctrl"]:
                if dy != 0:
                    zoom_step(1.1 if dy < 0 else 0.9, state["pointer"])
                elif dx != 0:
                    zoom_step(1.1 if dx < 0 else 0.9, state["pointer"])
                return True
            else:
                state["ox"] -= dx * 40.0
                state["oy"] -= dy * 40.0
                refresh_positions()
                return True
        scroll.connect("scroll", on_scroll)
        drawing.add_controller(scroll)

        keys = Gtk.EventControllerKey()
        def on_key_pressed(_c, keyval, _kcode, _state):
            if keyval in (Gdk.KEY_Control_L, Gdk.KEY_Control_R):
                state["ctrl"] = True
            if keyval == Gdk.KEY_space:
                state["space"] = True
            if keyval in (Gdk.KEY_Shift_L, Gdk.KEY_Shift_R):
                state["shift"] = True
            if state["ctrl"] and keyval in (Gdk.KEY_plus, Gdk.KEY_KP_Add, Gdk.KEY_equal):
                zoom_step(1.1, anchor_center())
                return True
            if state["ctrl"] and keyval in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
                zoom_step(0.9, anchor_center())
                return True
            if state["ctrl"] and keyval in (Gdk.KEY_0, Gdk.KEY_KP_0):
                set_zoom(1.0, anchor_center())
                return True
            if keyval == Gdk.KEY_f:
                fit_view()
                return True
            if keyval in (Gdk.KEY_Up, Gdk.KEY_w, Gdk.KEY_W):
                pan_direction(0, 50)
                return True
            if keyval in (Gdk.KEY_Down, Gdk.KEY_s, Gdk.KEY_S):
                pan_direction(0, -50)
                return True
            if keyval in (Gdk.KEY_Left, Gdk.KEY_a, Gdk.KEY_A):
                pan_direction(-50, 0)
                return True
            if keyval in (Gdk.KEY_Right, Gdk.KEY_d, Gdk.KEY_D):
                pan_direction(50, 0)
                return True
            return False
        def on_key_released(_c, keyval, _kcode, _state):
            if keyval in (Gdk.KEY_Control_L, Gdk.KEY_Control_R):
                state["ctrl"] = False
            if keyval == Gdk.KEY_space:
                state["space"] = False
            if keyval in (Gdk.KEY_Shift_L, Gdk.KEY_Shift_R):
                state["shift"] = False
            return False
        keys.connect("key-pressed", on_key_pressed)
        keys.connect("key-released", on_key_released)
        root.add_controller(keys)

        def initial():
            update_css_for_scale()
            build_nodes()
            recompute_visibility()
            auto_layout()
            fit_view()
            root.grab_focus()
            return False
        GLib.idle_add(initial)

        tab = self.ui_controller.add_tab(root)
        tab.set_title(data[0]["title"] if data else "Mind Map")
        tab.set_icon(Gio.ThemedIcon.new("applications-graphics-symbolic"))

    def _parse_mindmap(self, text: str) -> list:
        lines = [l.rstrip("\r\n") for l in text.splitlines()]
        items = []
        for raw in lines:
            if not raw.strip():
                continue
            s = raw.replace("\t", "  ")
            stripped = s.lstrip(" ")
            if not (stripped.startswith("- ") or stripped.startswith("* ")):
                continue
            indent = (len(s) - len(stripped)) // 2
            title = stripped[2:].strip()
            items.append((indent, title))
        root = []
        stack = []
        for indent, title in items:
            node = {"title": title, "children": []}
            while stack and stack[-1][0] >= indent:
                stack.pop()
            if stack:
                stack[-1][1]["children"].append(node)
            else:
                root.append(node)
            stack.append((indent, node))
        if not root and lines:
            root = [{"title": lines[0].strip(), "children": []}]
        return root
