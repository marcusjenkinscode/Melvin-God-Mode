"""
REST API Blueprint for Melvin God Mode Web UI.
Provides endpoints for models, chat, agents, cluster, and system stats.
"""

import os
import json
import subprocess
import requests
import psutil
from flask import Blueprint, jsonify, request, current_app

api_bp = Blueprint("api", __name__)

OLLAMA_BASE = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ollama(path, method="GET", payload=None, stream=False, timeout=30):
    url = f"{OLLAMA_BASE}{path}"
    try:
        if method == "GET":
            r = requests.get(url, timeout=timeout, stream=stream)
        else:
            r = requests.post(url, json=payload, timeout=timeout, stream=stream)
        return r
    except requests.exceptions.ConnectionError:
        return None


def _error(msg, code=500):
    return jsonify({"error": msg}), code


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@api_bp.route("/api/models", methods=["GET"])
def list_models():
    """Return list of locally available Ollama models."""
    resp = _ollama("/api/tags")
    if resp is None:
        return _error("Ollama service unavailable", 503)
    if not resp.ok:
        return _error(f"Ollama error: {resp.text}", resp.status_code)
    data = resp.json()
    models = [
        {
            "name": m.get("name"),
            "size": m.get("size"),
            "modified_at": m.get("modified_at"),
            "digest": m.get("digest", "")[:12],
            "details": m.get("details", {}),
        }
        for m in data.get("models", [])
    ]
    return jsonify({"models": models})


@api_bp.route("/api/models/pull", methods=["POST"])
def pull_model():
    """Initiate a model pull from Ollama registry."""
    body = request.get_json(silent=True) or {}
    model_name = (body.get("name") or "").strip()
    if not model_name:
        return _error("Missing field: name", 400)
    resp = _ollama("/api/pull", method="POST", payload={"name": model_name, "stream": False}, timeout=300)
    if resp is None:
        return _error("Ollama service unavailable", 503)
    if not resp.ok:
        return _error(f"Pull failed: {resp.text}", resp.status_code)
    return jsonify({"status": "ok", "model": model_name})


@api_bp.route("/api/models/<path:model_name>", methods=["DELETE"])
def delete_model(model_name):
    """Delete a locally stored Ollama model."""
    resp = _ollama("/api/delete", method="POST", payload={"name": model_name})
    if resp is None:
        return _error("Ollama service unavailable", 503)
    if not resp.ok:
        return _error(f"Delete failed: {resp.text}", resp.status_code)
    return jsonify({"status": "deleted", "model": model_name})


@api_bp.route("/api/models/info", methods=["POST"])
def model_info():
    """Return detailed model info."""
    body = request.get_json(silent=True) or {}
    model_name = (body.get("name") or "").strip()
    if not model_name:
        return _error("Missing field: name", 400)
    resp = _ollama("/api/show", method="POST", payload={"name": model_name})
    if resp is None:
        return _error("Ollama service unavailable", 503)
    if not resp.ok:
        return _error(f"Model info failed: {resp.text}", resp.status_code)
    return jsonify(resp.json())


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@api_bp.route("/api/chat", methods=["POST"])
def chat():
    """Send a chat message to Ollama and return the full response."""
    body = request.get_json(silent=True) or {}
    model = (body.get("model") or "llama3").strip()
    message = (body.get("message") or "").strip()
    history = body.get("history", [])

    if not message:
        return _error("Missing field: message", 400)

    messages = []
    for entry in history:
        role = entry.get("role", "user")
        content = entry.get("content", "")
        if role in ("user", "assistant", "system") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    payload = {"model": model, "messages": messages, "stream": False}
    resp = _ollama("/api/chat", method="POST", payload=payload, timeout=120)
    if resp is None:
        return _error("Ollama service unavailable", 503)
    if not resp.ok:
        return _error(f"Chat error: {resp.text}", resp.status_code)

    data = resp.json()
    assistant_msg = data.get("message", {}).get("content", "")
    return jsonify({"response": assistant_msg, "model": model})


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

def _load_agent_registry():
    """Attempt to import agent classes and return status map."""
    agents_info = []
    agent_files = [
        ("planner", "planner_agent", "PlannerAgent"),
        ("coder", "coder_agent", "CoderAgent"),
        ("debugger", "debugger_agent", "DebuggerAgent"),
        ("devops", "devops_agent", "DevOpsAgent"),
        ("research", "research_agent", "ResearchAgent"),
        ("security", "security_agent", "SecurityAgent"),
        ("architect", "architect_agent", "ArchitectAgent"),
    ]
    for slug, module_name, class_name in agent_files:
        agents_info.append({
            "id": slug,
            "name": class_name.replace("Agent", " Agent"),
            "module": module_name,
            "status": "idle",
        })
    return agents_info


@api_bp.route("/api/agents", methods=["GET"])
def agent_status():
    """Return list of available agents and their current status."""
    return jsonify({"agents": _load_agent_registry()})


@api_bp.route("/api/agents/run", methods=["POST"])
def run_agent():
    """
    Trigger an agent task asynchronously.

    TODO: Integrate with a proper async task queue (e.g. Celery + Redis or
    a threading.Thread pool) to actually execute agent modules. Currently
    validates inputs and returns a queued status as a stub.
    """
    body = request.get_json(silent=True) or {}
    agent_id = (body.get("agent") or "").strip()
    task = (body.get("task") or "").strip()

    if not agent_id or not task:
        return _error("Missing fields: agent, task", 400)

    valid_ids = {a["id"] for a in _load_agent_registry()}
    if agent_id not in valid_ids:
        return _error(f"Unknown agent: {agent_id}", 404)

    return jsonify({
        "status": "queued",
        "agent": agent_id,
        "task": task,
        "message": f"Task queued for {agent_id}. Integrate with task queue for async execution.",
    })


# ---------------------------------------------------------------------------
# Cluster
# ---------------------------------------------------------------------------

@api_bp.route("/api/cluster", methods=["GET"])
def cluster_status():
    """Return cluster node status (local + any configured remotes)."""
    nodes = []

    # Local node always present
    cpu_pct = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    nodes.append({
        "id": "local",
        "host": "127.0.0.1",
        "role": "primary",
        "status": "online",
        "cpu_pct": cpu_pct,
        "mem_total_gb": round(mem.total / 1024 ** 3, 2),
        "mem_used_gb": round(mem.used / 1024 ** 3, 2),
    })

    # Check for remote nodes defined in environment
    remote_hosts = os.environ.get("MELVIN_CLUSTER_NODES", "")
    for host in filter(None, remote_hosts.split(",")):
        host = host.strip()
        nodes.append({
            "id": host,
            "host": host,
            "role": "worker",
            "status": "unknown",
            "cpu_pct": None,
            "mem_total_gb": None,
            "mem_used_gb": None,
        })

    return jsonify({"nodes": nodes, "count": len(nodes)})


# ---------------------------------------------------------------------------
# System Stats
# ---------------------------------------------------------------------------

@api_bp.route("/api/system", methods=["GET"])
def system_stats():
    """Return current CPU, memory, and disk utilisation."""
    cpu_pct = psutil.cpu_percent(interval=0.2)
    cpu_per_core = psutil.cpu_percent(interval=0.2, percpu=True)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    boot_time = psutil.boot_time()

    return jsonify({
        "cpu": {
            "percent": cpu_pct,
            "per_core": cpu_per_core,
            "count": psutil.cpu_count(logical=True),
            "physical_count": psutil.cpu_count(logical=False),
        },
        "memory": {
            "total_gb": round(mem.total / 1024 ** 3, 2),
            "used_gb": round(mem.used / 1024 ** 3, 2),
            "free_gb": round(mem.available / 1024 ** 3, 2),
            "percent": mem.percent,
        },
        "disk": {
            "total_gb": round(disk.total / 1024 ** 3, 2),
            "used_gb": round(disk.used / 1024 ** 3, 2),
            "free_gb": round(disk.free / 1024 ** 3, 2),
            "percent": disk.percent,
        },
        "network": {
            "bytes_sent_mb": round(net.bytes_sent / 1024 ** 2, 2),
            "bytes_recv_mb": round(net.bytes_recv / 1024 ** 2, 2),
        },
        "boot_time": boot_time,
    })


# ---------------------------------------------------------------------------
# GPU Stats
# ---------------------------------------------------------------------------

def _parse_nvidia_smi():
    """Query nvidia-smi and return per-GPU stats list."""
    query = (
        "index,name,utilization.gpu,utilization.memory,"
        "memory.used,memory.total,temperature.gpu,power.draw"
    )
    try:
        result = subprocess.run(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return []
        gpus = []
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 8:
                continue
            def _float(v):
                try:
                    return float(v)
                except (ValueError, TypeError):
                    return None
            gpus.append({
                "index": int(parts[0]) if parts[0].isdigit() else 0,
                "name": parts[1],
                "gpu_util_pct": _float(parts[2]),
                "mem_util_pct": _float(parts[3]),
                "mem_used_mb": _float(parts[4]),
                "mem_total_mb": _float(parts[5]),
                "temp_c": _float(parts[6]),
                "power_w": _float(parts[7]),
            })
        return gpus
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


@api_bp.route("/api/gpu", methods=["GET"])
def gpu_stats():
    """Return GPU utilisation via nvidia-smi (empty list if no NVIDIA GPU)."""
    gpus = _parse_nvidia_smi()
    return jsonify({"gpus": gpus, "count": len(gpus)})
