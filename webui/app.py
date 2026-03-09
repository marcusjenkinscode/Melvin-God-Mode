"""
Melvin God Mode — Flask + SocketIO Web Application
Entry point for the Web UI server.
"""

import os
import sys
import json
import logging
import requests
import yaml
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, disconnect
from flask_cors import CORS

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_CONFIG_PATH = os.environ.get(
    "MELVIN_CONFIG",
    os.path.join(os.path.dirname(__file__), "..", "configs", "settings.yaml"),
)

def _load_config():
    try:
        with open(_CONFIG_PATH, "r") as fh:
            return yaml.safe_load(fh)
    except Exception:
        return {}

cfg = _load_config()
webui_cfg = cfg.get("webui", {})
ollama_cfg = cfg.get("ollama", {})

SECRET_KEY = webui_cfg.get("secret_key", os.environ.get("SECRET_KEY", "dev-secret-key"))
DEBUG = webui_cfg.get("debug", os.environ.get("FLASK_DEBUG", "false").lower() == "true")
HOST = webui_cfg.get("host", "0.0.0.0")
PORT = int(webui_cfg.get("port", 5000))

OLLAMA_HOST = os.environ.get(
    "OLLAMA_HOST",
    f"http://{ollama_cfg.get('host', '127.0.0.1')}:{ollama_cfg.get('port', 11434)}",
)
OLLAMA_TIMEOUT = int(ollama_cfg.get("timeout", 120))

if SECRET_KEY == "CHANGE_ME_IN_PRODUCTION":
    logging.warning(
        "⚠️  Using default secret key — set webui.secret_key in settings.yaml before production!"
    )

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app():
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["OLLAMA_HOST"] = OLLAMA_HOST
    app.config["OLLAMA_TIMEOUT"] = OLLAMA_TIMEOUT
    app.config["DEBUG"] = DEBUG

    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Register API blueprint — support both direct execution and package import
    try:
        from api import api_bp  # when running `python app.py` from webui/
    except ImportError:
        from webui.api import api_bp  # when imported as a package
    app.register_blueprint(api_bp)

    # ------------------------------------------------------------------
    # Page routes
    # ------------------------------------------------------------------

    @app.route("/")
    def index():
        return render_template("index.html", page="home")

    @app.route("/chat")
    def chat():
        return render_template("chat.html", page="chat")

    @app.route("/dashboard")
    def dashboard():
        return render_template("dashboard.html", page="dashboard")

    @app.route("/models")
    def models():
        return render_template("models.html", page="models")

    @app.route("/agents")
    def agents():
        return render_template("agents.html", page="agents")

    @app.route("/cluster")
    def cluster():
        return render_template("cluster.html", page="cluster")

    return app


app = create_app()
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    logger=False,
    engineio_logger=False,
)


# ---------------------------------------------------------------------------
# SocketIO events
# ---------------------------------------------------------------------------

@socketio.on("connect")
def handle_connect():
    emit("status", {"msg": "Connected to Melvin God Mode", "sid": request.sid})


@socketio.on("disconnect")
def handle_disconnect():
    pass  # Clean-up handled by SocketIO internally


@socketio.on("chat_message")
def handle_chat_message(data):
    """
    Receives {model, message, history} from the client,
    streams the Ollama response back token by token.
    """
    model = (data.get("model") or "llama3").strip()
    message = (data.get("message") or "").strip()
    history = data.get("history", [])

    if not message:
        emit("chat_error", {"error": "Empty message"})
        return

    messages = []
    for entry in history:
        role = entry.get("role", "user")
        content = entry.get("content", "")
        if role in ("user", "assistant", "system") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    payload = {"model": model, "messages": messages, "stream": True}

    emit("chat_start", {"model": model})

    full_response = []
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json=payload,
            stream=True,
            timeout=OLLAMA_TIMEOUT,
        )
        resp.raise_for_status()

        for raw_line in resp.iter_lines():
            if not raw_line:
                continue
            try:
                chunk = json.loads(raw_line.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

            token = chunk.get("message", {}).get("content", "")
            if token:
                full_response.append(token)
                emit("chat_token", {"token": token})

            if chunk.get("done"):
                break

    except requests.exceptions.ConnectionError:
        emit("chat_error", {"error": "Cannot reach Ollama — is the service running?"})
        return
    except requests.exceptions.Timeout:
        emit("chat_error", {"error": "Ollama request timed out."})
        return
    except requests.exceptions.HTTPError as exc:
        emit("chat_error", {"error": f"Ollama HTTP error: {exc}"})
        return
    except Exception as exc:  # noqa: BLE001
        emit("chat_error", {"error": f"Unexpected error: {exc}"})
        return

    emit("chat_done", {"full_response": "".join(full_response), "model": model})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG if DEBUG else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    print(f"🚀 Melvin God Mode Web UI starting on http://{HOST}:{PORT}")
    socketio.run(app, host=HOST, port=PORT, debug=DEBUG, use_reloader=False)
