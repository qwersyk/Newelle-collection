from .extensions import NewelleExtension
from gi.repository import Gtk, Gio
import re

class GraphHopperRouteExtension(NewelleExtension):
    id = "graphhopper_route"
    name = "GraphHopper Route"

    def get_replace_codeblocks_langs(self) -> list:
        return ["route"]

    def get_additional_prompts(self) -> list:
        return [
            {
                "key": "route",
                "setting_name": "route",
                "title": "Route Codeblocks",
                "description": "Show multi-point routes via GraphHopper",
                "editable": True,
                "show_in_settings": True,
                "default": True,
                "text": "Provide points and optional profile (car|bike|foot). Example:\n```route\nprofile: car\n55.751244, 37.618423\n55.760000, 37.620000\n55.770000, 37.630000\n```"
            }
        ]

    def get_gtk_widget(self, codeblock: str, lang: str) -> Gtk.Widget | None:
        if lang != "route":
            return None
        points, profile = self._parse_route(codeblock)
        if len(points) < 2:
            return None
        b = Gtk.Button()
        b.add_css_class("pill")
        b.add_css_class("suggested-action")
        b.set_tooltip_text("Open Route")
        b.set_child(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        b.connect("clicked", lambda _b: self._open_route_tab(points, profile))
        return b

    def _open_route_tab(self, points, profile):
        qs = "&".join([f"point={lat:.6f},{lon:.6f}" for lat, lon in points])
        url = f"https://graphhopper.com/maps/?{qs}&profile={profile}&locale=ru"
        tab = self.ui_controller.new_browser_tab(url, new=True)
        if tab is not None:
            tab.set_title(f"{profile} · {len(points)} pts")
            tab.set_icon(Gio.ThemedIcon.new("mark-location-symbolic"))

    def _parse_route(self, text: str):
        profile = "car"
        for line in (text or "").splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                if k.strip().lower() == "profile":
                    profile = v.strip() or "car"
        nums = re.findall(r"[-+]?\d+(?:\.\d+)?", text or "")
        pts = []
        i = 0
        while i + 1 < len(nums):
            try:
                pts.append((float(nums[i]), float(nums[i + 1])))
            except Exception:
                pass
            i += 2
        return pts, profile
