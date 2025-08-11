from .extensions import NewelleExtension
from gi.repository import Gtk, Gio, GLib
import json, threading

class QuizExtension(NewelleExtension):
    id = "quiz"
    name = "Quiz"

    def get_replace_codeblocks_langs(self) -> list:
        return ["quizinit", "quiz"]

    def get_additional_prompts(self) -> list:
        return [
            {
                "key": "quizinit",
                "setting_name": "quizinit",
                "title": "Quiz Init",
                "description": "Initialize the Quiz panel and score",
                "editable": True,
                "show_in_settings": True,
                "default": True,
                "text": "Use a `quizinit` block to set up the quiz panel. Example:\n```quizinit\ntitle: General Knowledge Quiz\n```"
            },
            {
                "key": "quiz",
                "setting_name": "quiz",
                "title": "Quiz Question",
                "description": "Ask a question with a hint, commentary, and explanation.",
                "editable": True,
                "show_in_settings": True,
                "default": True,
                "text": "Use a `quiz` block for a single question. Provide YAML/JSON-like config.\nExample:\n```quiz\nquestion: What is the largest planet in our Solar System?\n# Modes: single_choice | multiple_choice | text_input\nmode: single_choice\noptions:\n  - Earth\n  - Mars\n  - Jupiter\n  - Saturn\ncorrect_answer: Jupiter\nhint: It's a gas giant known for its Great Red Spot.\ncommentary_correct: Exactly! You're a star!\ncommentary_incorrect: Not quite. It's a tricky one!\nexplanation: Jupiter is the largest planet, with a mass more than two and a half times that of all the other planets in the Solar System combined.\n```\nFor multiple_choice, use `correct_answers` with a list."
            }
        ]

    def get_gtk_widget(self, codeblock: str, lang: str) -> Gtk.Widget | None:
        return None

    def get_answer(self, codeblock: str, lang: str) -> str | None:
        if lang == "quizinit":
            self._panel_tab = None
            self._panel_root = None
            self._container = None
            self._content_box = None
            self._title_lbl = None
            self._score_lbl = None
            self._mounted = False
            self._pending_render = None
            self._active_wait = None
            self._state = {"title": "Quiz", "score": 0, "total": 0}
            cfg_text = codeblock or ""
            self._on_init_clicked(cfg_text)
            return "The quiz has started."

        if lang != "quiz":
            return None

        q_data = self._parse_quiz_block(codeblock)

        sem = threading.Semaphore(0)
        result = {"user_answer": None, "is_correct": None}

        def choose_callback(answer):
            if self._active_wait and self._active_wait.get("result") is result:
                is_correct = self._check_answer(answer, q_data)
                
                result["user_answer"] = answer
                result["is_correct"] = is_correct

                self._state["total"] += 1
                if is_correct:
                    self._state["score"] += 1

                GLib.idle_add(self._refresh_header)
                
                commentary = q_data.get("commentary_correct") if is_correct else q_data.get("commentary_incorrect")
                explanation = q_data.get("explanation")

                def release_sem():
                    if self._active_wait and self._active_wait.get("sem") is sem:
                        self._active_wait["sem"].release()
                        self._active_wait = None

                GLib.idle_add(self._render_feedback, is_correct, commentary, explanation, release_sem)

        def render():
            if self._mounted and self._content_box is not None:
                self._render_question(q_data, choose_callback)
                self._pending_render = None
            else:
                self._pending_render = lambda: self._render_question(q_data, choose_callback)
            return False

        if self._active_wait:
            try:
                self._active_wait["result"]["user_answer"] = "CANCELLED"
                self._active_wait["sem"].release()
            except Exception:
                pass
        self._active_wait = {"sem": sem, "result": result}

        GLib.idle_add(render)
        sem.acquire()
        
        return f"User answered: {result['user_answer']}. Correct: {result['is_correct']}"

    def _on_init_clicked(self, cfg_text: str):
        config = self._parse_init_config(cfg_text)
        self._state["title"] = config.get("title", "Quiz")
        self._state["score"] = 0
        self._state["total"] = 0

        if self._panel_root is None:
            self._build_panel()
        
        self._refresh_header()
        if self._content_box:
             for c in list(self._content_box):
                self._content_box.remove(c)

        if not self._mounted:
            self._panel_tab = self.ui_controller.add_tab(self._panel_root)
            self._panel_tab.set_icon(Gio.ThemedIcon.new("help-faq-symbolic"))
            self._panel_tab.set_title(self._state.get("title") or "Quiz")
            self._mounted = True
        
        if self._pending_render:
            GLib.idle_add(self._pending_render)
            self._pending_render = None

    def _ensure_css(self, widget: Gtk.Widget):
        css = Gtk.CssProvider()
        css.load_from_data(b"""
        .quiz-title { font-weight: 800; font-size: 15px; letter-spacing: .2px; }
        .quiz-score { font-weight: 700; font-size: 13px; opacity: .8; }
        .quiz-card { border-radius: 12px; padding: 10px; background: alpha(@theme_fg_color, .05); }

        .quiz-q-card { border-radius: 10px; padding: 10px; background: transparent; border: 1px solid alpha(@theme_fg_color, .12); }
        .quiz-q-title { font-weight: 900; font-size: 15px; }

        .quiz-opt { padding: 8px 10px; border-radius: 10px; background: alpha(@theme_bg_color, .7); }
        .quiz-opt:hover { background: alpha(@theme_fg_color, .12); }
        .quiz-submit { border-radius: 10px; padding: 8px 10px; background: linear-gradient(135deg, #38bdf8, #3b82f6); color: white; }
        .quiz-submit label { color: white; font-weight: 800; }
        
        .quiz-hint-btn { font-size: 11px; padding: 2px 6px; border-radius: 99px; }
        .quiz-hint-box { border-radius: 8px; padding: 8px; margin-top: 6px; background: alpha(@theme_fg_color, .07); }
        
        .quiz-feedback { border-radius: 12px; padding: 12px; color: white; }
        .quiz-feedback.correct { background: linear-gradient(135deg, #22c55e, #16a34a); }
        .quiz-feedback.incorrect { background: linear-gradient(135deg, #ef4444, #b91c1c); }
        .quiz-feedback-title { font-weight: 800; font-size: 16px; }
        .quiz-feedback-expl { opacity: .9; margin-top: 4px; }
        """)
        Gtk.StyleContext.add_provider_for_display(widget.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _build_panel(self):
        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True); scroller.set_vexpand(True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_margin_top(8); scroller.set_margin_bottom(8)
        scroller.set_margin_start(8); scroller.set_margin_end(8)

        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        container.set_size_request(280, -1)
        scroller.set_child(container)
        self._ensure_css(scroller)

        header_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        header_card.add_css_class("quiz-card")

        self._title_lbl = Gtk.Label(xalign=0); self._title_lbl.add_css_class("quiz-title")
        self._score_lbl = Gtk.Label(xalign=0); self._score_lbl.add_css_class("quiz-score")
        header_card.append(self._title_lbl)
        header_card.append(self._score_lbl)

        self._content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        container.append(header_card)
        container.append(self._content_box)

        self._panel_root = scroller
        self._container = container

    def _refresh_header(self):
        if self._title_lbl:
            self._title_lbl.set_text(self._state.get("title") or "Quiz")
        if self._score_lbl:
            score = self._state.get("score", 0)
            total = self._state.get("total", 0)
            self._score_lbl.set_text(f"Score: {score} / {total}")
        return False

    def _render_question(self, q_data: dict, on_choose):
        if self._content_box is None: return
        for c in list(self._content_box): self._content_box.remove(c)

        q_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        q_card.add_css_class("quiz-q-card")
        
        q_title = Gtk.Label(label=q_data.get("question", "What is your answer?"), xalign=0)
        q_title.add_css_class("quiz-q-title")
        q_title.set_wrap(True)
        q_card.append(q_title)

        if q_data.get("hint"):
            hint_rev = Gtk.Revealer()
            hint_btn = Gtk.Button(label="Show Hint"); hint_btn.add_css_class("quiz-hint-btn"); hint_btn.add_css_class("flat")
            def toggle_hint(_btn):
                hint_rev.set_reveal_child(not hint_rev.get_reveal_child())
                _btn.set_visible(False)
            hint_btn.connect("clicked", toggle_hint)
            
            hint_box = Gtk.Box(); hint_box.add_css_class("quiz-hint-box")
            hint_box.append(Gtk.Label(label=q_data["hint"], xalign=0, wrap=True))
            hint_rev.set_child(hint_box)
            q_card.append(hint_btn)
            q_card.append(hint_rev)

        self._content_box.append(q_card)

        opts_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._content_box.append(opts_box)

        mode = q_data.get("mode", "single_choice")
        options = q_data.get("options", [])

        def disable_ui():
            for child in list(opts_box):
                child.set_sensitive(False)
            q_card.set_sensitive(False)

        if mode == "single_choice":
            for opt in options:
                b = Gtk.Button()
                b.add_css_class("quiz-opt")
                b.set_child(Gtk.Label(label=opt, xalign=0, wrap=True))
                b.connect("clicked", lambda _b, v=opt: (disable_ui(), on_choose(v)))
                opts_box.append(b)

        elif mode == "text_input":
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            entry = Gtk.Entry(); entry.set_placeholder_text("Type your answer…")
            entry.set_hexpand(True)
            submit = Gtk.Button(); submit.add_css_class("quiz-submit"); submit.set_child(Gtk.Label(label="Submit"))
            def do_submit(_=None):
                val = (entry.get_text() or "").strip()
                if val:
                    disable_ui()
                    on_choose(val)
            submit.connect("clicked", do_submit)
            entry.connect("activate", do_submit)
            row.append(entry); row.append(submit)
            opts_box.append(row)

        elif mode == "multiple_choice":
            checks = []
            for opt in options:
                cb = Gtk.CheckButton(label=opt)
                checks.append(cb)
                opts_box.append(cb)
            
            submit = Gtk.Button(); submit.add_css_class("quiz-submit"); submit.set_child(Gtk.Label(label="Submit Answer"))
            def do_submit_multi(_=None):
                selected = [c.get_label() for c in checks if c.get_active()]
                if selected:
                    disable_ui()
                    submit.set_sensitive(False)
                    on_choose(selected)
            submit.connect("clicked", do_submit_multi)
            opts_box.append(submit)

        self._scroll_panel_to_bottom()

    def _render_feedback(self, is_correct: bool, commentary: str, explanation: str, on_next):
        if self._content_box is None: return False
        
        feedback_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        feedback_box.add_css_class("quiz-feedback")
        feedback_box.add_css_class("correct" if is_correct else "incorrect")

        icon_text = "✓" if is_correct else "✕"
        title_text = commentary or ("Correct!" if is_correct else "Incorrect")
        
        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        icon = Gtk.Label(label=icon_text); icon.add_css_class("quiz-feedback-title")
        title = Gtk.Label(label=title_text, xalign=0); title.add_css_class("quiz-feedback-title")
        title.set_wrap(True)
        title_row.append(icon); title_row.append(title)
        feedback_box.append(title_row)

        if explanation:
            expl_label = Gtk.Label(label=explanation, xalign=0, wrap=True)
            expl_label.add_css_class("quiz-feedback-expl")
            feedback_box.append(expl_label)
        
        next_btn = Gtk.Button(label="Next Question →")
        next_btn.set_halign(Gtk.Align.END)
        next_btn.add_css_class("pill")
        next_btn.connect("clicked", lambda _: on_next())
        feedback_box.append(next_btn)
        
        self._content_box.append(feedback_box)
        self._scroll_panel_to_bottom()
        return False

    def _scroll_panel_to_bottom(self):
        w = self._content_box
        while w is not None and not isinstance(w, Gtk.ScrolledWindow):
            w = w.get_parent()
        if isinstance(w, Gtk.ScrolledWindow):
            vadj = w.get_vadjustment()
            GLib.idle_add(lambda: vadj.set_value(vadj.get_upper() - vadj.get_page_size()), priority=GLib.PRIORITY_LOW)

    def _check_answer(self, user_answer, q_data):
        mode = q_data.get("mode")
        if mode == "multiple_choice":
            correct = sorted(q_data.get("correct_answers", []))
            user = sorted(user_answer) if isinstance(user_answer, list) else []
            return correct == user
        else:
            correct = q_data.get("correct_answer", "")
            user = user_answer if isinstance(user_answer, str) else ""
            return user.strip().lower() == correct.strip().lower()

    def _parse_init_config(self, text: str) -> dict:
        text = text or ""
        try:
            return json.loads(text)
        except Exception:
            pass
        
        cfg = {}
        for line in text.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                if key.strip().lower() == "title":
                    cfg["title"] = value.strip()
        return cfg

    def _parse_quiz_block(self, text: str) -> dict:
        text = text or ""
        data = {}
        lines = [l for l in text.splitlines() if l.strip()]
        
        current_list_key = None
        for i, line in enumerate(lines):
            line_strip = line.strip()
            if line_strip.startswith("-"):
                if current_list_key and current_list_key in data:
                    item = line.split("-", 1)[1].strip()
                    data[current_list_key].append(item)
                continue

            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip().lower().replace(" ", "_")
                value = value.strip()
                
                if value:
                    data[key] = value
                    current_list_key = None
                else:
                    data[key] = []
                    current_list_key = key
            elif i == 0 and "question" not in data:
                 data["question"] = line_strip

        if 'correct_answers' in data and isinstance(data['correct_answers'], str):
             data['correct_answers'] = [item.strip() for item in data['correct_answers'].split(',')]

        return data