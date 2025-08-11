from .extensions import NewelleExtension
from gi.repository import Gtk, Gio
import re

class OSMViewerExtension(NewelleExtension):
    id = "osm_viewer"
    name = "OpenStreetMap Viewer"

    def get_replace_codeblocks_langs(self) -> list:
        return ["map"]

    def get_additional_prompts(self) -> list:
        return [
            {
                "key": "map",
                "setting_name": "map",
                "title": "Map Codeblocks",
                "description": "Show coordinates on OpenStreetMap",
                "editable": True,
                "show_in_settings": True,
                "default": True,
                "text": "To show a map, output only a single code block with language map. Formats supported:\n- `lat, lon` (optional third number = zoom)\n- or key/value lines, e.g.:\n```map\nlat: 55.751244\nlon: 37.618423\nzoom: 13\ntitle: Moscow Center\n```"
            }
        ]

    def get_gtk_widget(self, codeblock: str, lang: str) -> Gtk.Widget | None:
        if lang != "map":
            return None
        lat, lon, zoom, title = self._parse_coords(codeblock)
        if lat is None or lon is None:
            return None
        btn = Gtk.Button()
        btn.add_css_class("pill")
        btn.add_css_class("suggested-action")
        btn.set_tooltip_text("Open on OpenStreetMap")
        btn.set_child(Gtk.Image.new_from_icon_name("mark-location-symbolic"))
        btn.connect("clicked", lambda _b: self._open_map_tab(lat, lon, zoom, title))
        return btn

    def _open_map_tab(self, lat: float, lon: float, zoom: int, title: str):
        url = f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map={zoom}/{lat:.6f}/{lon:.6f}"
        tab = self.ui_controller.new_browser_tab(url, new=True)
        if tab is not None:
            tab.set_title(title if title else f"{lat:.5f},{lon:.5f}")
            tab.set_icon(Gio.ThemedIcon.new("mark-location-symbolic"))

    def _parse_coords(self, text: str):
        zoom = 14
        title = ""
        kv = {}
        for line in (text or "").splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                kv[k.strip().lower()] = v.strip()
        if "lat" in kv and "lon" in kv:
            try:
                lat = float(kv["lat"])
                lon = float(kv["lon"])
                if "zoom" in kv:
                    zoom = max(1, min(19, int(re.findall(r"\d+", kv["zoom"])[0])))
                title = kv.get("title", "")
                return lat, lon, zoom, title
            except Exception:
                pass

        nums = re.findall(r"[-+]?\d+(?:\.\d+)?", text or "")
        if len(nums) >= 2:
            try:
                lat = float(nums[0]); lon = float(nums[1])
                if len(nums) >= 3:
                    try:
                        zoom = max(1, min(19, int(float(nums[2]))))
                    except Exception:
                        pass
                return lat, lon, zoom, title
            except Exception:
                return None, None, zoom, title
        return None, None, zoom, title
