import os
import queue
import threading
import time
from collections import deque
from datetime import datetime

import dearpygui.dearpygui as dpg
import psutil

import engine
from bots.kick import KickBot
from bots.tiktok import TikTokBot
from bots.twitch import TwitchBot
from bots.youtube import YouTubeBot


COLORS = {
    "bg": (2, 8, 24, 255),
    "panel": (5, 16, 35, 255),
    "panel_alt": (8, 20, 43, 255),
    "border": (28, 55, 90, 255),
    "cyan": (20, 214, 246, 255),
    "magenta": (228, 20, 164, 255),
    "green": (24, 230, 96, 255),
    "muted": (125, 139, 165, 255),
    "white": (232, 239, 250, 255),
    "twitch": (145, 70, 255, 255),
    "youtube": (255, 35, 70, 255),
    "tiktok": (255, 45, 145, 255),
    "kick": (83, 252, 24, 255),
}

PLATFORMS = {
    "twitch": ("TWITCH", "TW", TwitchBot),
    "youtube": ("YOUTUBE", "YT", YouTubeBot),
    "tiktok": ("TIKTOK", "TT", TikTokBot),
    "kick": ("KICK", "K", KickBot),
}


class DashboardApp:
    def __init__(self):
        self.events = queue.Queue()
        self.bots = []
        self.messages = deque(maxlen=50)
        self.activity = deque(maxlen=80)
        self.counts = {platform: 0 for platform in PLATFORMS}
        self.connected = {platform: False for platform in PLATFORMS}
        self.is_capturing = False
        self.is_stopping = False
        self.closed = False
        self.session_started = None
        self.current_page = "dashboard"
        self.last_stats_update = 0.0
        self.process = psutil.Process(os.getpid())
        self.process.cpu_percent()
        self._server_started = False

    def build(self):
        self._build_theme()
        self._load_fonts()
        self._load_logo()

        with dpg.window(tag="primary_window", no_scrollbar=True, no_collapse=True):
            with dpg.group(horizontal=True):
                self._build_sidebar()

                with dpg.child_window(
                    tag="main_area",
                    width=-1,
                    height=-1,
                    border=False,
                    no_scrollbar=True,
                ):
                    self._build_header()

                    with dpg.child_window(width=-1, height=-1, border=False):
                        self._build_dashboard_page()
                        self._build_platforms_page()
                        self._build_editor_page()
                        self._build_chat_page()
                        self._build_logs_page()
                        self._build_settings_page()

        self._start_server()
        self._add_activity("Aplicação v1.2.0 iniciada", COLORS["cyan"])
        self._refresh_activity()
        self._refresh_overlay_preview()

    def _load_fonts(self):
        font_path = r"C:\Windows\Fonts\segoeui.ttf"
        if not os.path.exists(font_path):
            return
        with dpg.font_registry():
            dpg.add_font(font_path, 16, tag="font_regular")
        dpg.bind_font("font_regular")

    def _build_theme(self):
        with dpg.theme() as theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, COLORS["bg"])
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, COLORS["panel"])
                dpg.add_theme_color(dpg.mvThemeCol_PopupBg, COLORS["panel_alt"])
                dpg.add_theme_color(dpg.mvThemeCol_Border, COLORS["border"])
                dpg.add_theme_color(dpg.mvThemeCol_Text, COLORS["white"])
                dpg.add_theme_color(dpg.mvThemeCol_TextDisabled, COLORS["muted"])
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, COLORS["panel_alt"])
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (15, 37, 68, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Button, (12, 28, 54, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (22, 63, 95, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (151, 17, 122, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Header, (22, 63, 95, 255))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (107, 24, 137, 255))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, (171, 18, 137, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Tab, (7, 20, 42, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TabHovered, (20, 80, 110, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TabSelected, (133, 20, 125, 255))
                dpg.add_theme_color(dpg.mvThemeCol_CheckMark, COLORS["cyan"])
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab, (30, 77, 108, 255))
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 14, 14)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 10, 8)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 10, 9)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 8)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6)
                dpg.add_theme_style(dpg.mvStyleVar_GrabRounding, 6)
        dpg.bind_theme(theme)

    def _load_logo(self):
        try:
            width, height, _, data = dpg.load_image(engine.resource_path("assets/netrunner.png"))
            with dpg.texture_registry(show=False):
                dpg.add_static_texture(width, height, data, tag="logo_texture")
        except Exception:
            pass

    def _build_sidebar(self):
        with dpg.child_window(width=250, height=-1, border=True):
            with dpg.group(horizontal=True):
                if dpg.does_item_exist("logo_texture"):
                    dpg.add_image("logo_texture", width=62, height=62)
                with dpg.group():
                    dpg.add_text("NETRUNNER", color=COLORS["white"])
                    dpg.add_text("OVERLAY ENGINE", color=COLORS["cyan"])

            dpg.add_separator()
            dpg.add_spacer(height=18)

            entries = [
                ("dashboard", "DASH  Dashboard"),
                ("platforms", "LIVE  Plataformas"),
                ("editor", "</> Overlay Editor"),
                ("chat", "CHAT  Chat ao Vivo"),
                ("logs", "LOG   Logs"),
                ("settings", "CFG   Configurações"),
            ]
            for page, label in entries:
                dpg.add_button(
                    label=label,
                    width=-1,
                    height=46,
                    callback=self._switch_page,
                    user_data=page,
                    tag=f"nav_{page}",
                )

            dpg.add_spacer(height=220)
            dpg.add_separator()
            dpg.add_text("Netrunner Engine", color=COLORS["white"])
            dpg.add_text("v1.2.0  |  PRIVATE PREVIEW", color=COLORS["cyan"])

    def _build_header(self):
        with dpg.table(header_row=False, policy=dpg.mvTable_SizingStretchProp):
            dpg.add_table_column(init_width_or_weight=1.0)
            dpg.add_table_column(width_fixed=True, init_width_or_weight=285)
            with dpg.table_row():
                with dpg.table_cell():
                    dpg.add_text("DASHBOARD", tag="page_title", color=COLORS["white"])
                    dpg.add_text("Visão geral do sistema", tag="page_subtitle", color=COLORS["muted"])
                with dpg.table_cell():
                    with dpg.group(horizontal=True):
                        dpg.add_text("ENGINE ONLINE", color=COLORS["green"], tag="engine_status")
                        dpg.add_button(
                            label="INICIAR ENGINE",
                            width=150,
                            callback=self.toggle_capture,
                            tag="header_engine_button",
                        )

        dpg.add_separator()

    def _build_dashboard_page(self):
        with dpg.group(tag="page_dashboard"):
            with dpg.table(header_row=False, policy=dpg.mvTable_SizingStretchProp):
                dpg.add_table_column(init_width_or_weight=2.1)
                dpg.add_table_column(init_width_or_weight=1.25)
                with dpg.table_row():
                    with dpg.table_cell():
                        self._build_dashboard_left()
                    with dpg.table_cell():
                        self._build_live_chat_panel("chat_feed_dashboard", 590)
            self._build_compact_editor()

    def _build_dashboard_left(self):
        with dpg.table(header_row=False, policy=dpg.mvTable_SizingStretchSame):
            for _ in PLATFORMS:
                dpg.add_table_column()
            with dpg.table_row():
                for platform in PLATFORMS:
                    with dpg.table_cell():
                        self._platform_card(platform)

        with dpg.child_window(height=137, border=True):
            dpg.add_text("OVERLAY SERVER", color=COLORS["white"])
            dpg.add_text("Servidor local pronto para o OBS", color=COLORS["muted"])
            with dpg.group(horizontal=True):
                dpg.add_text("http://127.0.0.1:5000/overlay", color=COLORS["cyan"])
                dpg.add_button(label="COPIAR LINK", callback=self.copy_obs_link)

        with dpg.child_window(height=150, border=True):
            dpg.add_text("ESTATÍSTICAS", color=COLORS["white"])
            with dpg.table(header_row=False, policy=dpg.mvTable_SizingStretchSame):
                for _ in range(4):
                    dpg.add_table_column()
                with dpg.table_row():
                    for tag, label in (
                        ("stat_messages", "Total de mensagens"),
                        ("stat_platforms", "Plataformas ativas"),
                        ("stat_session", "Tempo de sessão"),
                        ("stat_resources", "CPU / Memória"),
                    ):
                        with dpg.table_cell():
                            dpg.add_text("0", tag=tag, color=COLORS["white"])
                            dpg.add_text(label, color=COLORS["muted"])

        with dpg.child_window(height=155, border=True):
            dpg.add_text("ATIVIDADE RECENTE", color=COLORS["white"])
            with dpg.child_window(tag="activity_feed", height=105, border=False):
                pass

    def _platform_card(self, platform):
        name, icon, _ = PLATFORMS[platform]
        with dpg.child_window(height=145, border=True, no_scrollbar=True):
            with dpg.group(horizontal=True):
                dpg.add_text(icon, color=COLORS[platform])
                dpg.add_text(name, color=COLORS["white"])
            dpg.add_spacer(height=12)
            dpg.add_text("OFFLINE | Desconectado", tag=f"status_{platform}", color=COLORS["muted"])
            dpg.add_text("0 mensagens", tag=f"count_{platform}", color=COLORS[platform])

    def _build_compact_editor(self):
        with dpg.child_window(tag="overlay_editor_panel", height=365, border=True):
            with dpg.group(horizontal=True):
                dpg.add_text("OVERLAY EDITOR", color=COLORS["white"])
                dpg.add_checkbox(label="Auto preview", default_value=True, tag="auto_preview_compact")
                dpg.add_button(label="RESET", callback=self.reset_overlay)
                dpg.add_button(label="APLICAR", callback=self.apply_overlay)
            with dpg.table(header_row=False, policy=dpg.mvTable_SizingStretchProp):
                dpg.add_table_column(init_width_or_weight=2.1)
                dpg.add_table_column(init_width_or_weight=1.0)
                with dpg.table_row():
                    with dpg.table_cell():
                        with dpg.tab_bar():
                            with dpg.tab(label="HTML"):
                                dpg.add_input_text(
                                    multiline=True,
                                    default_value=engine.LIVE_HTML,
                                    height=250,
                                    width=-1,
                                    tag="editor_html",
                                )
                            with dpg.tab(label="CSS"):
                                dpg.add_input_text(
                                    multiline=True,
                                    default_value=engine.LIVE_CSS,
                                    height=250,
                                    width=-1,
                                    tag="editor_css",
                                )
                            with dpg.tab(label="JS"):
                                dpg.add_input_text(
                                    multiline=True,
                                    default_value=engine.LIVE_JS,
                                    height=250,
                                    width=-1,
                                    tag="editor_js",
                                )
                    with dpg.table_cell():
                        dpg.add_text("PREVIEW", color=COLORS["white"])
                        with dpg.child_window(tag="overlay_preview", height=250, border=True):
                            pass

    def _build_live_chat_panel(self, tag, height):
        with dpg.child_window(height=height, border=True):
            dpg.add_text("CHAT AO VIVO", color=COLORS["white"])
            dpg.add_text("Mensagens recebidas em tempo real", color=COLORS["muted"])
            dpg.add_separator()
            with dpg.child_window(tag=tag, height=height - 115, border=False):
                dpg.add_text("Aguardando mensagens...", color=COLORS["muted"])
            dpg.add_input_text(
                hint="Filtrar mensagens...",
                width=-1,
                callback=self._filter_changed,
                tag=f"{tag}_filter",
            )

    def _build_platforms_page(self):
        with dpg.group(tag="page_platforms", show=False):
            dpg.add_text("Canais acompanhados", color=COLORS["muted"])
            fields = (
                ("twitch", "Canal Twitch"),
                ("youtube", "URL ou ID da live no YouTube"),
                ("tiktok", "@ do canal TikTok"),
                ("kick", "Canal Kick"),
            )
            for platform, hint in fields:
                with dpg.child_window(height=92, border=True):
                    dpg.add_text(PLATFORMS[platform][0], color=COLORS[platform])
                    dpg.add_input_text(hint=hint, width=-1, tag=f"input_{platform}")
            with dpg.group(horizontal=True):
                dpg.add_button(label="INICIAR CAPTURA", width=220, callback=self.start_capture)
                dpg.add_button(label="ENCERRAR CAPTURA", width=220, callback=self.stop_capture)

    def _build_editor_page(self):
        with dpg.group(tag="page_editor", show=False):
            dpg.add_text("O editor completo está integrado ao Dashboard.", color=COLORS["muted"])
            dpg.add_button(
                label="ABRIR EDITOR NO DASHBOARD",
                callback=lambda sender, app_data, user_data: self._switch_page(user_data="dashboard"),
            )
            dpg.add_separator()
            dpg.add_text("Alterações aplicadas entram imediatamente no endereço do OBS.", color=COLORS["cyan"])

    def _build_chat_page(self):
        with dpg.group(tag="page_chat", show=False):
            self._build_live_chat_panel("chat_feed_full", 650)

    def _build_logs_page(self):
        with dpg.group(tag="page_logs", show=False):
            with dpg.child_window(tag="log_feed", height=650, border=True):
                dpg.add_text("Logs do Netrunner", color=COLORS["cyan"])

    def _build_settings_page(self):
        with dpg.group(tag="page_settings", show=False):
            with dpg.child_window(height=240, border=True):
                dpg.add_text("CONFIGURAÇÕES", color=COLORS["white"])
                dpg.add_checkbox(label="Manter overlay local", default_value=True, enabled=False)
                dpg.add_input_text(label="Porta", default_value="5000", enabled=False)
                dpg.add_text("O servidor aceita conexões somente em 127.0.0.1.", color=COLORS["green"])
                dpg.add_text("Nenhuma credencial de plataforma é armazenada.", color=COLORS["cyan"])
            with dpg.child_window(height=150, border=True):
                dpg.add_text("SOBRE", color=COLORS["white"])
                dpg.add_text("Netrunner Overlay Engine v1.2.0")
                dpg.add_text("Interface Dear PyGui • distribuição proprietária", color=COLORS["muted"])

    def _switch_page(self, sender=None, app_data=None, user_data=None):
        page = user_data or "dashboard"
        titles = {
            "dashboard": ("DASHBOARD", "Visão geral do sistema"),
            "platforms": ("PLATAFORMAS", "Configure as capturas"),
            "editor": ("OVERLAY EDITOR", "Personalize o overlay do OBS"),
            "chat": ("CHAT AO VIVO", "Mensagens recebidas"),
            "logs": ("LOGS", "Eventos e diagnósticos"),
            "settings": ("CONFIGURAÇÕES", "Preferências locais"),
        }
        for candidate in titles:
            dpg.configure_item(f"page_{candidate}", show=candidate == page)
        self.current_page = page
        title, subtitle = titles[page]
        dpg.set_value("page_title", title)
        dpg.set_value("page_subtitle", subtitle)

    def _start_server(self):
        if self._server_started:
            return
        threading.Thread(target=engine.run_flask, name="OverlayServer", daemon=True).start()
        self._server_started = True

    def toggle_capture(self):
        if self.is_capturing:
            self.stop_capture()
        else:
            self.start_capture()

    def start_capture(self):
        if self.is_capturing or self.is_stopping:
            return
        configs = []
        for platform, (_, _, bot_class) in PLATFORMS.items():
            channel = str(dpg.get_value(f"input_{platform}") or "").strip()
            if channel:
                configs.append((platform, bot_class, channel))
        if not configs:
            self._log("Informe ao menos um canal na página Plataformas.", COLORS["youtube"])
            self._switch_page(user_data="platforms")
            return

        self.bots = [bot for bot in self.bots if bot.isRunning()]
        running_types = {type(bot) for bot in self.bots}
        started = 0
        for platform, bot_class, channel in configs:
            if bot_class in running_types:
                continue
            bot = bot_class(channel)
            bot.new_message.connect(lambda user, message, source, q=self.events: q.put(("message", user, message, source)))
            bot.status_update.connect(lambda status, source=platform, q=self.events: q.put(("status", source, status)))
            bot.finished.connect(lambda current=bot, source=platform, q=self.events: q.put(("finished", source, current)))
            self.bots.append(bot)
            bot.start()
            started += 1
            self._set_platform(platform, False, "Conectando...")
        if started:
            self.is_capturing = True
            self.session_started = time.monotonic()
            dpg.configure_item("header_engine_button", label="PARAR ENGINE")
            self._add_activity("Captura iniciada", COLORS["green"])

    def stop_capture(self):
        if self.is_stopping:
            return
        self.is_stopping = True
        self.is_capturing = False
        for bot in self.bots:
            bot.running = False
            bot.requestInterruption()
        dpg.configure_item("header_engine_button", label="INICIAR ENGINE")
        for platform in PLATFORMS:
            self._set_platform(platform, False, "Desconectado")
        self._add_activity("Captura encerrada", COLORS["youtube"])
        self.is_stopping = False

    def copy_obs_link(self):
        dpg.set_clipboard_text("http://127.0.0.1:5000/overlay")
        self._log("Link do OBS copiado.", COLORS["cyan"])

    def apply_overlay(self):
        engine.LIVE_HTML = dpg.get_value("editor_html")
        engine.LIVE_CSS = dpg.get_value("editor_css")
        engine.LIVE_JS = dpg.get_value("editor_js")
        self._refresh_overlay_preview()
        self._log("Overlay atualizado em tempo real.", COLORS["green"])

    def reset_overlay(self):
        dpg.set_value("editor_html", engine.LIVE_HTML)
        dpg.set_value("editor_css", engine.LIVE_CSS)
        dpg.set_value("editor_js", engine.LIVE_JS)
        self._log("Editor recarregado com a versão ativa.", COLORS["cyan"])

    def _filter_changed(self, sender, app_data):
        self._refresh_chats()

    def tick(self):
        if self.closed:
            return
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind = event[0]
            if kind == "message":
                self._receive_message(*event[1:])
            elif kind == "status":
                self._receive_status(*event[1:])
            elif kind == "finished":
                self._bot_finished(*event[1:])

        now = time.monotonic()
        if now - self.last_stats_update >= 1:
            self.last_stats_update = now
            self._update_stats()

    def _receive_message(self, user, message, platform):
        timestamp = datetime.now().strftime("%H:%M:%S")
        record = {
            "user": str(user),
            "message": str(message),
            "platform": platform,
            "timestamp": timestamp,
        }
        self.messages.append(record)
        self.counts[platform] = self.counts.get(platform, 0) + 1
        dpg.set_value(f"count_{platform}", f"{self.counts[platform]} mensagens")

        global_sequence = None
        with engine.CHAT_LOCK:
            engine.MESSAGE_SEQUENCE += 1
            global_sequence = engine.MESSAGE_SEQUENCE
            engine.CHAT_MESSAGES.append({
                "id": global_sequence,
                "user": str(user),
                "message": str(message),
                "platform": platform,
            })
            while len(engine.CHAT_MESSAGES) > engine.MAX_MESSAGES:
                engine.CHAT_MESSAGES.pop(0)

        self._log(f"[{platform.upper()}] {user}: {message}", COLORS[platform], activity=False)
        self._refresh_chats()

    def _receive_status(self, platform, status):
        lower = status.lower()
        if "conectado" in lower or "sintonizada" in lower:
            self._set_platform(platform, True, "Conectado")
        elif "desconectado" in lower or "erro" in lower:
            self._set_platform(platform, False, "Desconectado")
        self._log(f"[{platform.upper()}] {status}", COLORS[platform])

    def _bot_finished(self, platform, bot):
        if bot in self.bots:
            self.bots.remove(bot)
        self._set_platform(platform, False, "Desconectado")
        if self.is_capturing and not any(current.isRunning() for current in self.bots):
            self.is_capturing = False
            dpg.configure_item("header_engine_button", label="INICIAR ENGINE")

    def _set_platform(self, platform, connected, label):
        self.connected[platform] = connected
        color = COLORS["green"] if connected else COLORS["muted"]
        state = "ONLINE" if connected else "OFFLINE"
        dpg.set_value(f"status_{platform}", f"{state} | {label}")
        dpg.configure_item(f"status_{platform}", color=color)

    def _refresh_chats(self):
        for tag in ("chat_feed_dashboard", "chat_feed_full"):
            if not dpg.does_item_exist(tag):
                continue
            query = str(dpg.get_value(f"{tag}_filter") or "").strip().lower()
            dpg.delete_item(tag, children_only=True)
            visible = [
                item for item in self.messages
                if not query or query in item["user"].lower() or query in item["message"].lower()
            ]
            if not visible:
                dpg.add_text("Aguardando mensagens...", parent=tag, color=COLORS["muted"])
                continue
            for item in list(visible)[-20:]:
                platform = item["platform"]
                with dpg.group(parent=tag):
                    with dpg.group(horizontal=True):
                        dpg.add_text(PLATFORMS[platform][1], color=COLORS[platform])
                        dpg.add_text(item["user"], color=COLORS["white"])
                        dpg.add_text(item["timestamp"], color=COLORS["muted"])
                    dpg.add_text(item["message"], color=(205, 215, 232, 255), wrap=420)
                    dpg.add_separator()
            dpg.set_y_scroll(tag, dpg.get_y_scroll_max(tag))
        self._refresh_overlay_preview()

    def _refresh_overlay_preview(self):
        if not dpg.does_item_exist("overlay_preview"):
            return
        dpg.delete_item("overlay_preview", children_only=True)
        sample = list(self.messages)[-3:] or [
            {"platform": "twitch", "user": "gabrielsilva", "message": "Salve! Bora pra live"},
            {"platform": "youtube", "user": "joaogames", "message": "Que overlay brabo demais!"},
        ]
        for item in sample:
            platform = item["platform"]
            with dpg.group(parent="overlay_preview"):
                with dpg.group(horizontal=True):
                    dpg.add_text(PLATFORMS[platform][1], color=COLORS[platform])
                    dpg.add_text(item["user"], color=COLORS["white"])
                dpg.add_text(item["message"], color=(205, 215, 232, 255), wrap=290)
                dpg.add_separator()

    def _log(self, text, color=None, activity=True):
        if dpg.does_item_exist("log_feed"):
            dpg.add_text(f"{datetime.now().strftime('%H:%M:%S')}  {text}", parent="log_feed", color=color or COLORS["white"])
            dpg.set_y_scroll("log_feed", dpg.get_y_scroll_max("log_feed"))
        if activity:
            self._add_activity(text, color or COLORS["white"])

    def _add_activity(self, text, color):
        self.activity.appendleft((datetime.now().strftime("%H:%M:%S"), text, color))
        self._refresh_activity()

    def _refresh_activity(self):
        if not dpg.does_item_exist("activity_feed"):
            return
        dpg.delete_item("activity_feed", children_only=True)
        for timestamp, text, color in list(self.activity)[:5]:
            with dpg.group(parent="activity_feed", horizontal=True):
                dpg.add_text(timestamp, color=COLORS["muted"])
                dpg.add_text("-", color=COLORS["magenta"])
                dpg.add_text(text, color=color)

    def _update_stats(self):
        total = sum(self.counts.values())
        active = sum(1 for value in self.connected.values() if value)
        elapsed = 0 if self.session_started is None else int(time.monotonic() - self.session_started)
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        cpu = self.process.cpu_percent()
        memory = self.process.memory_info().rss / (1024 * 1024)
        dpg.set_value("stat_messages", str(total))
        dpg.set_value("stat_platforms", str(active))
        dpg.set_value("stat_session", f"{hours:02}:{minutes:02}:{seconds:02}")
        dpg.set_value("stat_resources", f"{cpu:.0f}% / {memory:.0f} MB")

    def shutdown(self):
        if self.closed:
            return
        self.closed = True
        for bot in self.bots:
            try:
                bot.running = False
                bot.requestInterruption()
            except Exception:
                pass
        for bot in self.bots:
            try:
                bot.wait(1200)
            except Exception:
                pass
        self.bots.clear()
