from .extensions import NewelleExtension
from gi.repository import Gtk, Gio, GLib
import urllib.request, urllib.parse, json, threading, math
from datetime import datetime

class WeatherExtension(NewelleExtension):
    id = "weather_extension"
    name = "Weather"

    def get_replace_codeblocks_langs(self) -> list:
        return ["weather"]

    def get_extra_settings(self) -> list:
        return [
            {
                "key": "weather_units",
                "title": "Units",
                "description": "Units system",
                "type": "combo",
                "values": ["metric", "imperial"],
                "default": "metric",
            },
            {
                "key": "weather_lang",
                "title": "Language",
                "description": "Language for place names",
                "type": "entry",
                "default": "en",
            },
        ]

    def get_additional_prompts(self) -> list:
        return [
            {
                "key": "weather",
                "setting_name": "weather",
                "title": "Weather Codeblocks",
                "description": "Show styled weather cards for places and times",
                "editable": True,
                "show_in_settings": True,
                "default": True,
                "text": "Each line describes a request. Supported:\n- City or place name\n- City @ 2025-08-11 12:00\n- 55.75, 37.62\n- 55.75, 37.62 @ 2025-08-11T12:00\nGlobal overrides at top as key: value (units: metric|imperial, lang: en|ru|...).\nExample:\n```weather\nunits: metric\nlang: en\nMoscow @ 2025-08-11 12:00\n59.93, 30.33\n```"
            }
        ]

    def get_gtk_widget(self, codeblock: str, lang: str) -> Gtk.Widget | None:
        if lang != "weather":
            return None
        requests, globals_cfg = self._parse_weather_block(codeblock)
        if not requests:
            return None

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, hexpand=True, vexpand=True)
        root.set_margin_top(10)
        root.set_margin_bottom(10)
        root.set_margin_start(10)
        root.set_margin_end(10)

        css = Gtk.CssProvider()
        css.load_from_data(b"""
        .wx-card {
            border-radius: 16px;
            padding: 14px;
            box-shadow: 0 10px 28px alpha(@theme_fg_color, 0.18);
        }
        .wx-sun { background-image: linear-gradient(135deg, #FFCF6F, #FF7E5F); color: #232323; }
        .wx-cloud { background-image: linear-gradient(135deg, #B0BEC5, #90A4AE); color: #101417; }
        .wx-rain { background-image: linear-gradient(135deg, #74ABE2, #5563DE); color: #0e1221; }
        .wx-snow { background-image: linear-gradient(135deg, #E0F7FA, #B3E5FC); color: #143a4a; }
        .wx-storm { background-image: linear-gradient(135deg, #7F7FD5, #86A8E7); color: #0f1330; }
        .wx-night { background-image: linear-gradient(135deg, #1E3C72, #2A5298); color: #E8F1FF; }

        .wx-title { font-weight: 800; font-size: 14px; letter-spacing: .2px; }
        .wx-temp { font-size: 38px; font-weight: 900; }
        .wx-subtle { opacity: .9; }
        .wx-row { padding-top: 6px; }

        .wx-chip {
            background-color: alpha(@theme_bg_color, 0.18);
            border-radius: 999px;
            padding: 4px 8px;
            font-weight: 600;
        }
        .wx-chip-box { border-spacing: 8px; }

        .wx-cta {
            border-radius: 999px;
            padding: 8px 14px;
            background-image: linear-gradient(135deg, #FF7E5F, #F83E6D);
            color: white;
            border: none;
            box-shadow: 0 6px 18px rgba(248, 62, 109, 0.35);
        }
        .wx-cta:hover { filter: brightness(1.06); }
        .wx-cta label { color: white; font-weight: 800; }
        """)
        Gtk.StyleContext.add_provider_for_display(root.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        units_pref = (globals_cfg.get("units") or self.get_setting("weather_units") or "metric").lower()
        lang_pref = (globals_cfg.get("lang") or self.get_setting("weather_lang") or "en").lower()

        cards = []
        for req in requests:
            card = self._make_card_placeholder()
            root.append(card["card"])
            cards.append((card, req, units_pref, lang_pref))

        def worker():
            for card, req, u, lng in cards:
                try:
                    entry = self._resolve_and_fetch(req, u, lng)
                    GLib.idle_add(self._fill_card, card, entry, u)
                except Exception as e:
                    GLib.idle_add(self._error_card, card, str(e))
        threading.Thread(target=worker, daemon=True).start()

        return root

    def _make_card_placeholder(self):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("wx-card")
        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title = Gtk.Label(label="Loading…", xalign=0); title.add_css_class("wx-title"); title.set_hexpand(True)
        cta = Gtk.Button()
        cta.add_css_class("wx-cta")
        cta.set_child(Gtk.Label(label="Learn more"))
        cta.set_sensitive(False)
        title_row.append(title); title_row.append(cta)

        main = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        icon = Gtk.Image.new_from_icon_name("weather-overcast-symbolic"); icon.set_pixel_size(48)
        main_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        temp = Gtk.Label(label="--°", xalign=0); temp.add_css_class("wx-temp")
        summary = Gtk.Label(label="", xalign=0); summary.add_css_class("wx-subtle")
        timez = Gtk.Label(label="", xalign=0); timez.add_css_class("wx-subtle")
        main_text.append(temp); main_text.append(summary); main_text.append(timez)
        main.append(icon); main.append(main_text)

        chips = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        chips.add_css_class("wx-chip-box")
        chip1 = self._chip("—", "weather-clear-symbolic")
        chip2 = self._chip("—", "weather-windy-symbolic")
        chip3 = self._chip("—", "weather-showers-symbolic")
        chips.append(chip1); chips.append(chip2); chips.append(chip3)

        card.append(title_row); card.append(main); card.append(chips)
        return {"card": card, "title": title, "cta": cta, "icon": icon, "temp": temp, "summary": summary, "timez": timez, "chip1": chip1, "chip2": chip2, "chip3": chip3}

    def _chip(self, text, icon_name):
        b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        b.add_css_class("wx-chip")
        i = Gtk.Image.new_from_icon_name(icon_name)
        l = Gtk.Label(label=text)
        b.append(i); b.append(l)
        return b

    def _fill_card(self, card, entry, units_pref):
        name = entry.get("name") or f"{entry['lat']:.3f},{entry['lon']:.3f}"
        wcode = entry["weathercode"]
        is_night = entry["is_night"]
        temp = entry["temperature"]
        app_temp = entry.get("apparent_temperature")
        rh = entry.get("humidity")
        wind = entry.get("windspeed")
        pop = entry.get("precip_prob")
        precip = entry.get("precip")
        tz = entry.get("timezone", "")
        units_temp = "°F" if units_pref == "imperial" else "°C"
        units_wind = "mph" if units_pref == "imperial" else "km/h"
        units_precip = "in" if units_pref == "imperial" else "mm"

        card["title"].set_text(name)
        icon_name, desc = self._icon_and_desc(wcode, is_night)
        card["icon"].set_from_icon_name(icon_name)
        card["temp"].set_text(f"{round(temp):d}{units_temp}" if not math.isnan(temp) else f"--{units_temp}")
        card["summary"].set_text(desc)
        card["timez"].set_text(entry["local_time_str"] + (f" · {tz}" if tz else ""))

        c1 = f"Feels like: {round(app_temp):d}{units_temp}" if app_temp is not None else ""
        c2 = f"Wind: {round(wind)} {units_wind}" if wind is not None else ""
        rain_txt = []
        if pop is not None: rain_txt.append(f"POP {pop}%")
        if precip is not None: rain_txt.append(f"{precip:.1f} {units_precip}")
        if rh is not None: rain_txt.append(f"RH {rh}%")
        c3 = ", ".join(rain_txt)
        self._set_chip(card["chip1"], c1, "weather-clear-symbolic")
        self._set_chip(card["chip2"], c2, "weather-windy-symbolic")
        self._set_chip(card["chip3"], c3, "weather-showers-symbolic")

        for cls in ("wx-sun","wx-cloud","wx-rain","wx-snow","wx-storm","wx-night"):
            card["card"].remove_css_class(cls)
        card["card"].add_css_class(self._bg_class(wcode, is_night))

        lat = entry["lat"]; lon = entry["lon"]; when = entry["iso_time"]
        url = self._windy_link(lat, lon, when)
        def open_more(_b):
            tab = self.ui_controller.new_browser_tab(url, new=True)
            if tab:
                tab.set_title(f"Weather · {name}")
                tab.set_icon(Gio.ThemedIcon.new("globe-symbolic"))
        card["cta"].connect("clicked", open_more)
        card["cta"].set_sensitive(True)
        return False

    def _set_chip(self, chip_box, text, icon_name):
        children = list(chip_box)
        if len(children) == 2 and isinstance(children[1], Gtk.Label):
            if isinstance(children[0], Gtk.Image):
                children[0].set_from_icon_name(icon_name)
            children[1].set_text(text or "—")

    def _error_card(self, card, msg):
        card["title"].set_text("Weather error")
        card["summary"].set_text(msg)
        card["temp"].set_text("--")
        card["cta"].set_sensitive(False)
        for cls in ("wx-sun","wx-cloud","wx-rain","wx-snow","wx-storm","wx-night"):
            card["card"].remove_css_class(cls)
        card["card"].add_css_class("wx-storm")
        return False

    def _resolve_and_fetch(self, req, units_pref: str, lang: str):
        lat, lon, name = None, None, req.get("name", "")
        if "lat" in req and "lon" in req:
            lat, lon = float(req["lat"]), float(req["lon"])
        else:
            lat, lon, name = self._geocode_first(name, lang)
        if units_pref == "imperial":
            unit_params = {"temperature_unit": "fahrenheit","windspeed_unit": "mph","precipitation_unit": "inch","timeformat": "iso8601"}
        else:
            unit_params = {"temperature_unit": "celsius","windspeed_unit": "kmh","precipitation_unit": "mm","timeformat": "iso8601"}
        hourly_vars = ["temperature_2m","apparent_temperature","weathercode","relativehumidity_2m","precipitation_probability","precipitation","windspeed_10m"]
        params = {"latitude": f"{lat:.6f}","longitude": f"{lon:.6f}","hourly": ",".join(hourly_vars),"current_weather": "true","timezone": "auto"}
        params.update(unit_params)
        url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
        data = self._http_json(url)
        target_iso = None
        if req.get("time") is not None:
            target_iso = self._normalize_time(req["time"])
        idx, local_time_str, iso_time = self._pick_hour_index(data, target_iso)
        hourly = data.get("hourly", {})
        def g(k): return hourly.get(k, [])
        wcode = self._safe_get(g("weathercode"), idx)
        temp = self._safe_get(g("temperature_2m"), idx)
        app_temp = self._safe_get(g("apparent_temperature"), idx)
        rh = self._safe_get(g("relativehumidity_2m"), idx)
        pop = self._safe_get(g("precipitation_probability"), idx)
        precip = self._safe_get(g("precipitation"), idx)
        wind = self._safe_get(g("windspeed_10m"), idx)
        try:
            hour = int(iso_time[11:13]); is_night = hour < 6 or hour >= 21
        except Exception:
            is_night = False
        return {"name": name,"lat": lat,"lon": lon,"timezone": data.get("timezone", ""), "iso_time": iso_time,"local_time_str": local_time_str,"weathercode": int(wcode) if wcode is not None else 0,"temperature": float(temp) if temp is not None else math.nan,"apparent_temperature": float(app_temp) if app_temp is not None else None,"humidity": int(rh) if rh is not None else None,"precip_prob": int(pop) if pop is not None else None,"precip": float(precip) if precip is not None else None,"windspeed": float(wind) if wind is not None else None,"is_night": is_night}

    def _geocode_first(self, name: str, lang: str):
        q = name.strip()
        if not q:
            raise RuntimeError("Empty place name")
        url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode({"name": q,"count": 1,"language": lang or "en","format": "json"})
        data = self._http_json(url)
        results = data.get("results") or []
        if not results:
            raise RuntimeError(f"Place not found: {q}")
        r = results[0]
        nm = r.get("name", q); cc = r.get("country_code", ""); admin = r.get("admin1", "")
        display = nm + (f", {admin}" if admin else "") + (f" ({cc})" if cc else "")
        return float(r["latitude"]), float(r["longitude"]), display

    def _http_json(self, url: str):
        req = urllib.request.Request(url, headers={"User-Agent": "Newelle-Weather/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
        return json.loads(raw.decode("utf-8"))

    def _normalize_time(self, t):
        s = str(t).strip().replace("T", " ")
        if len(s) == 10:
            s = s + " 00:00"
        try:
            dt = datetime.fromisoformat(s)
        except Exception:
            return None
        return dt.strftime("%Y-%m-%dT%H:00")

    def _pick_hour_index(self, data, target_iso: str | None):
        hourly = data.get("hourly", {})
        times = hourly.get("time") or []
        if not times:
            cw = data.get("current_weather") or {}
            iso = cw.get("time", "")
            local = iso.replace("T", " ")
            return 0, local, iso
        if target_iso is None:
            cw_iso = (data.get("current_weather") or {}).get("time")
            if cw_iso and cw_iso in times:
                idx = times.index(cw_iso)
                return idx, cw_iso.replace("T", " "), cw_iso
            iso = times[-1]
            return len(times) - 1, iso.replace("T", " "), iso
        best_i = 0; best_diff = 10**9
        for i, iso in enumerate(times):
            try:
                d = abs(self._iso_to_tuple(iso) - self._iso_to_tuple(target_iso))
                if d < best_diff:
                    best_diff = d; best_i = i
            except Exception:
                pass
        iso = times[best_i]
        return best_i, iso.replace("T", " "), iso

    def _iso_to_tuple(self, s):
        y = int(s[0:4]); m = int(s[5:7]); d = int(s[8:10]); h = int(s[11:13])
        return (((y * 100) + m) * 100 + d) * 100 + h

    def _safe_get(self, arr, i):
        try:
            return arr[i]
        except Exception:
            return None

    def _icon_and_desc(self, code: int, night: bool):
        mapping_day = {
            0: ("weather-clear-symbolic", "Clear"),
            1: ("weather-few-clouds-symbolic", "Mostly clear"),
            2: ("weather-few-clouds-symbolic", "Partly cloudy"),
            3: ("weather-overcast-symbolic", "Overcast"),
            45: ("weather-fog-symbolic", "Fog"),
            48: ("weather-fog-symbolic", "Rime fog"),
            51: ("weather-showers-symbolic", "Drizzle"),
            53: ("weather-showers-symbolic", "Drizzle"),
            55: ("weather-showers-symbolic", "Dense drizzle"),
            56: ("weather-freezing-rain-symbolic", "Freezing drizzle"),
            57: ("weather-freezing-rain-symbolic", "Freezing drizzle"),
            61: ("weather-showers-symbolic", "Light rain"),
            63: ("weather-showers-symbolic", "Rain"),
            65: ("weather-showers-symbolic", "Heavy rain"),
            66: ("weather-freezing-rain-symbolic", "Freezing rain"),
            67: ("weather-freezing-rain-symbolic", "Freezing rain"),
            71: ("weather-snow-symbolic", "Light snow"),
            73: ("weather-snow-symbolic", "Snow"),
            75: ("weather-snow-symbolic", "Heavy snow"),
            77: ("weather-snow-symbolic", "Snow grains"),
            80: ("weather-showers-symbolic", "Rain showers"),
            81: ("weather-showers-symbolic", "Rain showers"),
            82: ("weather-showers-symbolic", "Violent showers"),
            85: ("weather-snow-symbolic", "Snow showers"),
            86: ("weather-snow-symbolic", "Snow showers"),
            95: ("weather-storm-symbolic", "Thunderstorm"),
            96: ("weather-storm-symbolic", "Thunderstorm with hail"),
            99: ("weather-storm-symbolic", "Thunderstorm with hail"),
        }
        icon, desc = mapping_day.get(code, ("weather-overcast-symbolic", "Weather"))
        if night:
            if icon == "weather-clear-symbolic":
                icon = "weather-clear-night-symbolic"
            elif icon == "weather-few-clouds-symbolic":
                icon = "weather-few-clouds-night-symbolic"
        return icon, desc

    def _bg_class(self, code: int, night: bool):
        if night:
            return "wx-night"
        if code in (0, 1):
            return "wx-sun"
        if code in (2, 3, 45, 48):
            return "wx-cloud"
        if code in (61, 63, 65, 80, 81, 82, 56, 57, 66, 67, 51, 53, 55):
            return "wx-rain"
        if code in (71, 73, 75, 77, 85, 86):
            return "wx-snow"
        if code in (95, 96, 99):
            return "wx-storm"
        return "wx-cloud"

    def _windy_link(self, lat: float, lon: float, iso_time: str):
        return f"https://www.windy.com/{lat:.4f}/{lon:.4f}?{lat:.4f},{lon:.4f},8"

    def _parse_weather_block(self, text: str):
        lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
        globals_cfg = {}
        requests = []
        for l in lines:
            if ":" in l and l.split(":", 1)[0].lower() in ("units", "lang"):
                k, v = l.split(":", 1)
                globals_cfg[k.strip().lower()] = v.strip()
                continue
            if "@" in l:
                loc, t = l.split("@", 1)
                loc = loc.strip(); t = t.strip()
            else:
                loc, t = l, None
            if "," in loc:
                parts = [p.strip() for p in loc.split(",")]
                if len(parts) >= 2:
                    try:
                        lat = float(parts[0]); lon = float(parts[1])
                        requests.append({"lat": lat, "lon": lon, "time": t, "name": None})
                        continue
                    except Exception:
                        pass
            if loc:
                requests.append({"name": loc, "time": t})
        return requests, globals_cfg