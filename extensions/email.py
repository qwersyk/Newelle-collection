from .extensions import NewelleExtension
from gi.repository import Gtk, Gio, GLib
import smtplib, ssl, mimetypes, os
from email.message import EmailMessage

class MailSenderExtension(NewelleExtension):
    name = "Email Composer"
    id = "email_composer"

    def get_replace_codeblocks_langs(self) -> list:
        return ["email"]

    def get_extra_settings(self):
        return [
            {
                "key": "smtp_email",
                "title": "Email Address",
                "description": "Account email address used as From and for SMTP authentication",
                "type": "entry",
                "default": ""
            },
            {
                "key": "smtp_password",
                "title": "Email Password",
                "description": "Password or app-specific password for SMTP authentication",
                "type": "entry",
                "default": ""
            },
            {
                "key": "smtp_host",
                "title": "SMTP Host",
                "description": "SMTP server hostname",
                "type": "entry",
                "default": ""
            },
            {
                "key": "smtp_port",
                "title": "SMTP Port",
                "description": "SMTP server port (e.g. 587 for STARTTLS, 465 for SSL)",
                "type": "entry",
                "default": "587"
            },
            {
                "key": "smtp_security",
                "title": "SMTP Security",
                "description": "Connection security for SMTP",
                "type": "combo",
                "values": ["STARTTLS", "SSL", "NONE"],
                "default": "STARTTLS"
            },
            {
                "key": "from_name",
                "title": "From Name",
                "description": "Optional display name to use in the From header",
                "type": "entry",
                "default": ""
            },
            {
                "key": "default_signature",
                "title": "Signature",
                "description": "Optional signature appended to new messages",
                "type": "entry",
                "default": ""
            }
        ]

    def get_additional_prompts(self) -> list:
        return [
            {
                "key": "email",
                "setting_name": "email",
                "title": "Email Codeblocks",
                "description": "Allow the assistant to compose emails as structured code blocks to be edited and sent",
                "editable": True,
                "show_in_settings": True,
                "default": True,
                "text": "You can propose emails using a single code block with language email. Use RFC822-like headers, then a blank line, then the body. Supported headers: to, cc, bcc, subject, content-type (text/plain or text/html), attachments (comma-separated file paths). Example:\n```email\nto: user@example.com\ncc:\nbcc:\nsubject: Project update\ncontent-type: text/plain\nattachments: /path/to/file1.pdf, /path/to/file2.png\n\nHello team,\nHere is the latest status...\n```"
            }
        ]

    def get_gtk_widget(self, codeblock: str, lang: str) -> Gtk.Widget | None:
        if lang != "email":
            return None
        b = Gtk.Button()
        b.add_css_class("suggested-action")
        b.add_css_class("pill")
        b.set_tooltip_text("Open Email Editor")
        b.set_child(Gtk.Image.new_from_icon_name("mail-send-symbolic"))
        b.connect("clicked", self._open_mail_tab, codeblock)
        return b

    def add_tab_menu_entries(self) -> list:
        from .handlers import TabButtonDescription
        return [TabButtonDescription("Email Composer", "mail-send-symbolic", lambda x, y: self._open_mail_tab(None, ""))]

    def _open_mail_tab(self, _btn, codeblock: str):
        parsed = self._parse_email_block(codeblock)

        overlay = Gtk.Overlay()
        overlay.set_hexpand(True)
        overlay.set_vexpand(True)

        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_kinetic_scrolling(True)
        overlay.set_child(scroller)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, hexpand=True, vexpand=True)
        main.set_margin_top(10)
        main.set_margin_bottom(10)
        main.set_margin_start(10)
        main.set_margin_end(10)
        main.set_size_request(380, -1)
        scroller.set_child(main)

        banner_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        banner_box.add_css_class("email-banner")
        banner_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
        banner_label = Gtk.Label(xalign=0)
        banner_box.append(banner_icon)
        banner_box.append(banner_label)
        banner_box.set_halign(Gtk.Align.FILL)
        banner_box.set_valign(Gtk.Align.START)
        banner_box.set_margin_top(6)
        banner_box.set_margin_start(6)
        banner_box.set_margin_end(6)
        banner_box.set_visible(False)
        overlay.add_overlay(banner_box)

        css = Gtk.CssProvider()
        css.load_from_data(b"""
        .email-banner {
            padding: 8px 12px;
            border-radius: 8px;
            color: @theme_fg_color;
        }
        .email-banner.success {
            background-color: #2ecc71;
            color: white;
        }
        .email-banner.error {
            background-color: #e74c3c;
            color: white;
        }
        """)
        Gtk.StyleContext.add_provider_for_display(
            main.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        header = Gtk.Label(label="Email Composer", xalign=0)
        header.add_css_class("title-4")
        main.append(header)

        def labeled(title: str, widget: Gtk.Widget) -> Gtk.Widget:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            lbl = Gtk.Label(label=title, xalign=0)
            lbl.add_css_class("dim-label")
            box.append(lbl)
            box.append(widget)
            return box

        from_addr = self.get_setting("smtp_email") or ""
        from_name = self.get_setting("from_name") or ""

        entry_from = Gtk.Entry()
        entry_from.set_placeholder_text("Full name and <email>")
        entry_from.set_text((from_name + " <" + from_addr + ">").strip() if (from_addr or from_name) else "")

        entry_to = Gtk.Entry(); entry_to.set_placeholder_text("user@example.com, user2@example.com")
        entry_cc = Gtk.Entry(); entry_cc.set_placeholder_text("Optional")
        entry_bcc = Gtk.Entry(); entry_bcc.set_placeholder_text("Optional")
        entry_subject = Gtk.Entry(); entry_subject.set_placeholder_text("Subject")

        ct_combo = Gtk.DropDown.new_from_strings(["text/plain", "text/html"])

        if parsed["to"]:
            entry_to.set_text(", ".join(parsed["to"]))
        if parsed["cc"]:
            entry_cc.set_text(", ".join(parsed["cc"]))
        if parsed["bcc"]:
            entry_bcc.set_text(", ".join(parsed["bcc"]))
        entry_subject.set_text(parsed["subject"])
        ct_combo.set_selected(0 if parsed["content_type"].lower().strip() != "text/html" else 1)

        main.append(labeled("From", entry_from))
        main.append(labeled("To", entry_to))
        main.append(labeled("Cc", entry_cc))
        main.append(labeled("Bcc", entry_bcc))
        main.append(labeled("Subject", entry_subject))
        main.append(labeled("Content Type", ct_combo))

        attachments = []

        attach_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        attach_label = Gtk.Label(label="Attachments (0)", xalign=0)
        attach_label.add_css_class("dim-label")
        attach_header.append(attach_label)
        attach_header.append(Gtk.Box())
        btn_attach_add = Gtk.Button()
        btn_attach_add.set_tooltip_text("Add attachment")
        btn_attach_add.add_css_class("flat")
        btn_attach_add.set_child(Gtk.Image.new_from_icon_name("list-add-symbolic"))
        attach_header.append(btn_attach_add)
        main.append(attach_header)

        attach_revealer = Gtk.Revealer()
        attach_revealer.set_reveal_child(False)
        attach_scrolled = Gtk.ScrolledWindow()
        attach_scrolled.set_min_content_height(120)
        attach_scrolled.set_hexpand(True)
        attach_scrolled.set_vexpand(False)
        attach_list = Gtk.ListBox()
        attach_scrolled.set_child(attach_list)
        attach_revealer.set_child(attach_scrolled)
        main.append(attach_revealer)

        def update_attach_caption():
            attach_label.set_text(f"Attachments ({len(attachments)})")

        def append_attachment_row(path: str):
            row = Gtk.ListBoxRow()
            h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            name_lbl = Gtk.Label(label=os.path.basename(path), xalign=0)
            name_lbl.set_hexpand(True)
            remove_btn = Gtk.Button()
            remove_btn.set_tooltip_text("Remove")
            remove_btn.add_css_class("flat")
            remove_btn.set_child(Gtk.Image.new_from_icon_name("user-trash-symbolic"))
            def do_remove(_b):
                if path in attachments:
                    attachments.remove(path)
                attach_list.remove(row)
                update_attach_caption()
            remove_btn.connect("clicked", do_remove)
            h.append(name_lbl)
            h.append(remove_btn)
            row.set_child(h)
            attach_list.append(row)

        for p in parsed["attachments"]:
            if os.path.exists(p):
                attachments.append(p)
                append_attachment_row(p)
        update_attach_caption()

        def toggle_attachments(_w, *_a):
            attach_revealer.set_reveal_child(not attach_revealer.get_reveal_child())

        click_toggle = Gtk.GestureClick()
        click_toggle.connect("released", toggle_attachments)
        attach_label.add_controller(click_toggle)

        def add_attachment(_btn):
            dialog = Gtk.FileDialog()
            def on_selected(_src, res):
                try:
                    file = dialog.open_finish(res)
                    if not file:
                        return
                    path = file.get_path()
                    if not path:
                        return
                    attachments.append(path)
                    append_attachment_row(path)
                    update_attach_caption()
                    attach_revealer.set_reveal_child(True)
                except Exception:
                    pass
            dialog.open(self.ui_controller.window, None, on_selected)
        btn_attach_add.connect("clicked", add_attachment)

        body_label = Gtk.Label(label="Body", xalign=0)
        body_label.add_css_class("dim-label")
        main.append(body_label)

        body_editor_view = Gtk.TextView()
        body_editor_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        body_editor = body_editor_view.get_buffer()
        initial_body = parsed["body"]
        sig = self.get_setting("default_signature") or ""
        if initial_body.strip() == "" and sig.strip() != "":
            initial_body = "\n\n" + sig
        body_editor.set_text(initial_body)

        body_scroll = Gtk.ScrolledWindow()
        body_scroll.set_child(body_editor_view)
        body_scroll.set_hexpand(True)
        body_scroll.set_vexpand(True)
        body_scroll.set_min_content_height(250)
        main.append(body_scroll)

        send_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        send_row.set_halign(Gtk.Align.END)

        btn_send = Gtk.Button()
        btn_send.add_css_class("suggested-action")
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_icon = Gtk.Image.new_from_icon_name("mail-send-symbolic")
        btn_text = Gtk.Label(label="Send")
        btn_spinner = Gtk.Spinner(spinning=False)
        btn_spinner.set_visible(False)
        btn_box.append(btn_icon)
        btn_box.append(btn_text)
        btn_box.append(btn_spinner)
        btn_send.set_child(btn_box)

        send_row.append(btn_send)
        main.append(send_row)

        tab = self.ui_controller.add_tab(overlay)
        def update_tab_title(_entry=None):
            title = entry_subject.get_text().strip()
            tab.set_title(title if title else "Email Composer")
        update_tab_title()
        entry_subject.connect("changed", update_tab_title)
        tab.set_icon(Gio.ThemedIcon.new("mail-send-symbolic"))

        def textbuffer_to_str(buf: Gtk.TextBuffer) -> str:
            start = buf.get_start_iter()
            end = buf.get_end_iter()
            return buf.get_text(start, end, True)

        def parse_from_field(s: str):
            s = (s or "").strip()
            if "<" in s and ">" in s:
                name = s.split("<")[0].strip().strip('"')
                addr = s.split("<")[1].split(">")[0].strip()
                return name, addr
            return "", s

        def parse_recipients(s: str):
            return [x.strip() for x in (s or "").split(",") if x.strip()]

        def set_sending_ui(sending: bool):
            btn_send.set_sensitive(not sending)
            btn_spinner.set_visible(sending)
            btn_spinner.set_spinning(sending)
            btn_text.set_text("Sending..." if sending else "Send")

        def show_banner(kind: str, msg: str):
            ctx = banner_box.get_style_context()
            ctx.remove_class("success")
            ctx.remove_class("error")
            if kind == "success":
                ctx.add_class("success")
                banner_icon.set_from_icon_name("emblem-ok-symbolic")
            else:
                ctx.add_class("error")
                banner_icon.set_from_icon_name("dialog-error-symbolic")
            banner_label.set_text(msg)
            banner_box.set_visible(True)
            def hide():
                banner_box.set_visible(False)
                return False
            GLib.timeout_add(2600, hide)

        def send_clicked(_btn):
            set_sending_ui(True)

            from_name_val, from_addr_val = parse_from_field(entry_from.get_text() or self.get_setting("smtp_email") or "")
            if not from_addr_val:
                from_addr_val = self.get_setting("smtp_email") or ""
            to_list = parse_recipients(entry_to.get_text())
            cc_list = parse_recipients(entry_cc.get_text())
            bcc_list = parse_recipients(entry_bcc.get_text())
            subject_val = entry_subject.get_text()
            body_val = textbuffer_to_str(body_editor)
            ctype = "text/html" if ct_combo.get_selected() == 1 else "text/plain"

            smtp_host = self.get_setting("smtp_host") or ""
            try:
                smtp_port = int(self.get_setting("smtp_port") or "0")
            except Exception:
                smtp_port = 0
            smtp_email = self.get_setting("smtp_email") or ""
            smtp_password = self.get_setting("smtp_password") or ""
            smtp_security = (self.get_setting("smtp_security") or "STARTTLS").upper()

            def work():
                try:
                    if not to_list and not cc_list and not bcc_list:
                        raise RuntimeError("No recipients specified.")
                    if not smtp_host or not smtp_port or not smtp_email:
                        raise RuntimeError("Missing SMTP settings.")

                    msg = EmailMessage()
                    if from_name_val:
                        msg["From"] = f"{from_name_val} <{from_addr_val}>"
                    else:
                        msg["From"] = from_addr_val
                    if to_list:
                        msg["To"] = ", ".join(to_list)
                    if cc_list:
                        msg["Cc"] = ", ".join(cc_list)
                    if subject_val:
                        msg["Subject"] = subject_val
                    if ctype == "text/html":
                        msg.set_content(body_val, subtype="html")
                    else:
                        msg.set_content(body_val, subtype="plain")

                    for p in list(attachments):
                        try:
                            ctype_guess, _enc = mimetypes.guess_type(p)
                            if ctype_guess is None:
                                maintype, subtype = "application", "octet-stream"
                            else:
                                maintype, subtype = ctype_guess.split("/", 1)
                            with open(p, "rb") as f:
                                data = f.read()
                            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=os.path.basename(p))
                        except Exception:
                            pass

                    all_rcpts = to_list + cc_list + bcc_list
                    if smtp_security == "SSL":
                        context = ssl.create_default_context()
                        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=30) as server:
                            if smtp_password:
                                server.login(smtp_email, smtp_password)
                            server.send_message(msg, from_addr=from_addr_val or smtp_email, to_addrs=all_rcpts)
                    else:
                        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
                            server.ehlo()
                            if smtp_security == "STARTTLS":
                                context = ssl.create_default_context()
                                server.starttls(context=context)
                                server.ehlo()
                            if smtp_password:
                                server.login(smtp_email, smtp_password)
                            server.send_message(msg, from_addr=from_addr_val or smtp_email, to_addrs=all_rcpts)

                    def ok():
                        set_sending_ui(False)
                        show_banner("success", "Email sent successfully.")
                        return False
                    GLib.idle_add(ok)

                except Exception as e:
                    def err():
                        set_sending_ui(False)
                        show_banner("error", f"Failed to send: {e}")
                        return False
                    GLib.idle_add(err)

            from threading import Thread
            Thread(target=work, daemon=True).start()

        btn_send.connect("clicked", send_clicked)

        def initial_focus():
            body_editor_view.grab_focus()
            return False
        GLib.idle_add(initial_focus)

    def _parse_email_block(self, text: str) -> dict:
        lines = [l.rstrip("\r\n") for l in (text or "").splitlines()]
        headers = {}
        body_lines = []
        in_body = False
        for l in lines:
            if in_body:
                body_lines.append(l)
                continue
            if l.strip() == "":
                in_body = True
                continue
            if ":" in l:
                k, v = l.split(":", 1)
                headers[k.strip().lower()] = v.strip()
            else:
                in_body = True
                body_lines.append(l)

        def split_list(v):
            return [x.strip() for x in (v or "").split(",") if x.strip()]

        parsed = {
            "to": split_list(headers.get("to", "")),
            "cc": split_list(headers.get("cc", "")),
            "bcc": split_list(headers.get("bcc", "")),
            "subject": headers.get("subject", ""),
            "content_type": headers.get("content-type", "text/plain"),
            "attachments": split_list(headers.get("attachments", "")),
            "body": "\n".join(body_lines).strip("\n")
        }
        return parsed
