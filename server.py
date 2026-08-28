import os
from flask import Flask, jsonify, render_template_string
from flask_cors import CORS

class OverlayServer:
    def __init__(self, overlay_dir="overlay"):
        self.app = Flask(__name__)
        CORS(self.app)
        self.overlay_dir = overlay_dir
        self.chat_messages = []
        self.max_messages = 50
        
        # Rotas
        self.app.route("/")(self.overlay)
        self.app.route("/chat")(self.chat)

    def _read_file(self, filename):
        path = os.path.join(self.overlay_dir, filename)
        # Fallback para o caso de o arquivo ainda não existir
        return "" if not os.path.exists(path) else open(path, 'r', encoding='utf-8').read()

    def overlay(self):
        # Template simplificado que busca o conteúdo dos arquivos
        template = """<!DOCTYPE html>
        <html>
        <head><style>{{ css|safe }}</style></head>
        <body>{{ html|safe }}<script>{{ js|safe }}</script></body>
        </html>"""
        return render_template_string(template, 
            html=self._read_file("index.html"),
            css=self._read_file("style.css"),
            js=self._read_file("script.js"))

    def chat(self):
        return jsonify(self.chat_messages)

    def add_message(self, user, message, platform):
        self.chat_messages.append({"user": user, "message": message, "platform": platform})
        if len(self.chat_messages) > self.max_messages:
            self.chat_messages.pop(0)

    def update_overlay_files(self, html, css, js):
        os.makedirs(self.overlay_dir, exist_ok=True)
        with open(os.path.join(self.overlay_dir, "index.html"), "w", encoding="utf-8") as f: f.write(html)
        with open(os.path.join(self.overlay_dir, "style.css"), "w", encoding="utf-8") as f: f.write(css)
        with open(os.path.join(self.overlay_dir, "script.js"), "w", encoding="utf-8") as f: f.write(js)

    def run(self):
        self.app.run(host="0.0.0.0", port=5000, debug=False, threaded=True, use_reloader=False)