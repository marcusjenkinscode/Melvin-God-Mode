"""
Melvin AI – Central Configuration
==================================
All tuneable knobs live here. Override with environment variables
prefixed with MELVIN_ (e.g. MELVIN_DATA_DIR=/mnt/ssd).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

# ---------------------------------------------------------------------------
# Directory layout
# ---------------------------------------------------------------------------
_env = os.environ.get

DATA_DIR: Path = Path(_env("MELVIN_DATA_DIR", str(Path.home() / ".melvin")))
DATASET_FILE: Path = DATA_DIR / "dataset.enc"          # encrypted JSON lines
KEY_FILE: Path = DATA_DIR / "dataset.key"              # Fernet key
TOOLS_CACHE_FILE: Path = DATA_DIR / "tools_cache.json"
MODELS_DIR: Path = DATA_DIR / "models"
LOG_FILE: Path = DATA_DIR / "melvin.log"

DATA_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------
OLLAMA_HOST: str = _env("MELVIN_OLLAMA_HOST", "http://localhost:11434")

# ---------------------------------------------------------------------------
# Models available – tuned for a 24 GB RAM / 650 GB storage machine.
# Each entry:  (ollama_tag, category, size_gb, min_ram_gb, preferred_gpu)
# ---------------------------------------------------------------------------
@dataclass
class ModelSpec:
    tag: str                    # e.g. "llama3.1:8b"
    display_name: str
    category: str               # general | code | creative | math | osint
    size_gb: float              # on-disk size
    min_ram_gb: float           # minimum RAM to run comfortably
    preferred_gpu: bool = True
    description: str = ""

MODEL_CATALOGUE: List[ModelSpec] = [
    ModelSpec(
        "llama3.1:8b", "Llama 3.1 8B", "general",
        size_gb=4.7, min_ram_gb=6,
        description="Meta's flagship 8B model – excellent general-purpose reasoning."
    ),
    ModelSpec(
        "mistral:7b", "Mistral 7B", "creative",
        size_gb=4.1, min_ram_gb=6,
        description="Fast & creative; great for writing, brainstorming, summarisation."
    ),
    ModelSpec(
        "codellama:13b", "CodeLlama 13B", "code",
        size_gb=7.4, min_ram_gb=10,
        description="Code generation & explanation across 20+ programming languages."
    ),
    ModelSpec(
        "deepseek-coder:6.7b", "DeepSeek Coder 6.7B", "code",
        size_gb=3.8, min_ram_gb=6,
        description="State-of-the-art code model, fast and lightweight."
    ),
    ModelSpec(
        "phi3:medium", "Phi-3 Medium 14B", "math",
        size_gb=8.0, min_ram_gb=10, preferred_gpu=False,
        description="Microsoft's reasoning-focused model, great for maths and logic."
    ),
    ModelSpec(
        "qwen2.5:7b", "Qwen 2.5 7B", "general",
        size_gb=4.4, min_ram_gb=6,
        description="Alibaba multilingual model – 128k context, strong on instructions."
    ),
    ModelSpec(
        "llava:13b", "LLaVA 13B", "vision",
        size_gb=8.0, min_ram_gb=10,
        description="Vision-language model – can describe images from file paths."
    ),
    ModelSpec(
        "llama3.1:70b-instruct-q4_K_M", "Llama 3.1 70B (Q4)", "general",
        size_gb=40.0, min_ram_gb=22,
        description="Best quality model; needs ~22 GB RAM (fits on 24 GB with nothing else running)."
    ),
]

# ---------------------------------------------------------------------------
# Agent personalities / system prompts
# ---------------------------------------------------------------------------
AGENT_PROMPTS = {
    "general": (
        "You are Melvin, an expert AI assistant. "
        "You are direct, helpful, and technically precise. "
        "Format code blocks with triple backticks and language identifiers."
    ),
    "code": (
        "You are Melvin Code, an expert software engineer and security researcher. "
        "Produce clean, well-commented, production-ready code. "
        "Always explain what the code does and highlight any security considerations."
    ),
    "creative": (
        "You are Melvin Creative, a versatile writer and storyteller. "
        "Your writing is vivid, original, and tailored to the requested style."
    ),
    "math": (
        "You are Melvin Math, a mathematical reasoning assistant. "
        "Show all working steps clearly. Use LaTeX notation where it aids clarity."
    ),
    "osint": (
        "You are Melvin OSINT, an open-source intelligence expert. "
        "Provide methodical, legal research strategies and tool recommendations. "
        "Always remind users to operate within the law."
    ),
    "security": (
        "You are Melvin Security, a certified ethical hacker and penetration tester. "
        "Provide guidance strictly for authorised testing and educational purposes. "
        "Always include legal and ethical disclaimers."
    ),
}

# ---------------------------------------------------------------------------
# UI settings
# ---------------------------------------------------------------------------
APP_NAME = "Melvin AI"
APP_VERSION = "2.0.0"
MAX_THOUGHT_LINES = 200
HISTORY_DISPLAY_LINES = 50

# ---------------------------------------------------------------------------
# Tool categories & seed tools (registry is generated from these)
# ---------------------------------------------------------------------------
TOOL_CATEGORIES = {
    "Network Scanning": [
        ("nmap",        "Network mapper – host discovery & port scanning"),
        ("masscan",     "Fastest TCP port scanner on the internet"),
        ("zmap",        "Single-packet network scanner"),
        ("unicornscan", "Asynchronous network reconnaissance tool"),
        ("netcat",      "TCP/UDP networking utility"),
        ("hping3",      "Custom packet crafter & ping tool"),
    ],
    "Vulnerability Analysis": [
        ("nikto",       "Web server vulnerability scanner"),
        ("wpscan",      "WordPress security scanner"),
        ("openvas",     "Open Vulnerability Assessment System"),
        ("lynis",       "Security auditing & hardening tool"),
        ("vulners",     "Vulnerability database search CLI"),
    ],
    "Penetration Testing": [
        ("metasploit-framework", "The world's most used penetration testing framework"),
        ("sqlmap",      "Automatic SQL injection & DB takeover tool"),
        ("beef-xss",    "Browser exploitation framework"),
        ("exploitdb",   "Offline copy of the Exploit Database"),
        ("commix",      "Command injection exploitation tool"),
    ],
    "Wireless": [
        ("aircrack-ng", "Wi-Fi network security toolkit"),
        ("kismet",      "Wireless network detector, sniffer & IDS"),
        ("wifite",      "Automated wireless attack tool"),
        ("reaver",      "WPS brute-force attack tool"),
        ("hostapd",     "IEEE 802.11 AP and auth server daemon"),
    ],
    "Web Applications": [
        ("burpsuite",   "Web security testing platform"),
        ("zaproxy",     "OWASP Zed Attack Proxy"),
        ("ffuf",        "Fast web fuzzer"),
        ("gobuster",    "Directory/file & DNS busting tool"),
        ("feroxbuster", "Fast, simple, recursive content discovery"),
        ("httpie",      "User-friendly HTTP client"),
        ("wfuzz",       "Web application fuzzer"),
    ],
    "Forensics": [
        ("sleuthkit",   "Collection of command-line digital forensics tools"),
        ("autopsy",     "Digital forensics platform & GUI"),
        ("volatility3", "Memory forensics framework"),
        ("binwalk",     "Firmware analysis tool"),
        ("foremost",    "File carving and recovery"),
        ("exiftool",    "Read/write metadata in files"),
    ],
    "Password Attacks": [
        ("john",        "John the Ripper – password cracker"),
        ("hashcat",     "World's fastest CPU-based password recovery"),
        ("hydra",       "Online password brute-force tool"),
        ("cewl",        "Custom wordlist generator"),
        ("crunch",      "Wordlist generator"),
        ("medusa",      "Parallel network login auditor"),
    ],
    "Sniffing & Spoofing": [
        ("wireshark",   "Network protocol analyser"),
        ("tcpdump",     "Command-line packet analyser"),
        ("ettercap",    "Man-in-the-middle attacks tool"),
        ("bettercap",   "Swiss army knife for network attacks"),
        ("arpspoof",    "ARP spoofing tool"),
    ],
    "Reverse Engineering": [
        ("ghidra",      "NSA Software Reverse Engineering Suite"),
        ("radare2",     "Portable reversing framework"),
        ("gdb",         "GNU Debugger"),
        ("objdump",     "Object file display utility"),
        ("ltrace",      "Library call tracer"),
        ("strace",      "System call tracer"),
        ("pwndbg",      "GDB plugin for exploit development"),
    ],
    "OSINT": [
        ("theharvester","E-mail, domain & IP OSINT tool"),
        ("maltego",     "Visual intelligence and forensics platform"),
        ("recon-ng",    "Web reconnaissance framework"),
        ("sherlock",    "Hunt usernames across social networks"),
        ("holehe",      "Check e-mail account usage on websites"),
        ("maigret",     "Collect information from username on 2000+ sites"),
        ("phoneinfoga", "Phone number OSINT scanner"),
    ],
    "System Administration": [
        ("htop",        "Interactive process viewer"),
        ("iotop",       "I/O usage monitor"),
        ("glances",     "Cross-platform system monitoring tool"),
        ("nmon",        "Performance monitor"),
        ("btop",        "Resource monitor – modern replacement for htop"),
        ("duf",         "Disk Usage/Free utility"),
        ("lsof",        "List open files"),
    ],
    "File Management": [
        ("rsync",       "Fast remote file copy & synchronisation"),
        ("rclone",      "Cloud storage manager"),
        ("bat",         "Cat with syntax highlighting"),
        ("fd",          "User-friendly alternative to find"),
        ("fzf",         "Fuzzy file finder"),
        ("ranger",      "Terminal file manager"),
    ],
    "Text Processing": [
        ("grep",        "Pattern search tool"),
        ("awk",         "Text processing language"),
        ("sed",         "Stream editor for filtering and transforming text"),
        ("jq",          "Lightweight command-line JSON processor"),
        ("ripgrep",     "Regex search across files (rg)"),
        ("miller",      "Like awk/sed/cut for CSV, TSV, JSON"),
    ],
    "Programming": [
        ("git",         "Distributed version control"),
        ("gcc",         "GNU Compiler Collection"),
        ("make",        "Build automation tool"),
        ("python3",     "Python interpreter"),
        ("nodejs",      "JavaScript runtime"),
        ("rustc",       "Rust compiler"),
        ("go",          "Go language toolchain"),
        ("docker",      "Container platform"),
    ],
    "Multimedia": [
        ("ffmpeg",      "Multimedia framework – convert, stream, record"),
        ("yt-dlp",      "Download videos from YouTube and 1000+ sites"),
        ("sox",         "Audio processing toolkit"),
        ("imagemagick", "Image manipulation suite (convert, mogrify)"),
        ("mpv",         "Media player"),
    ],
    "Cryptography": [
        ("openssl",     "Cryptography & SSL/TLS toolkit"),
        ("gpg",         "GNU Privacy Guard"),
        ("age",         "Simple, modern file encryption"),
        ("veracrypt",   "Disk encryption software"),
        ("steghide",    "Steganography program"),
    ],
    "Cloud & DevOps": [
        ("kubectl",     "Kubernetes CLI"),
        ("terraform",   "Infrastructure as code"),
        ("ansible",     "IT automation platform"),
        ("helm",        "Kubernetes package manager"),
        ("awscli",      "Amazon Web Services CLI"),
    ],
    "Misc": [
        ("cowsay",      "Configurable talking cow"),
        ("figlet",      "ASCII art text banner generator"),
        ("toilet",      "Display large colourful text"),
        ("lolcat",      "Rainbow coloured output"),
        ("neofetch",    "System info with ASCII logo"),
        ("cmatrix",     "Matrix-like falling characters in terminal"),
    ],
}

# ---------------------------------------------------------------------------
# Tool install commands (apt, pip, snap, cargo, go, manual)
# ---------------------------------------------------------------------------
TOOL_INSTALL_OVERRIDES = {
    "metasploit-framework": {"apt": "metasploit-framework"},
    "ghidra": {"manual": "https://ghidra-sre.org/"},
    "maltego": {"manual": "https://www.maltego.com/downloads/"},
    "burpsuite": {"manual": "https://portswigger.net/burp/releases/"},
    "zaproxy": {"snap": "zaproxy --classic"},
    "docker": {"apt": "docker.io"},
    "nodejs": {"apt": "nodejs"},
    "rustc": {"manual": "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"},
    "go": {"manual": "https://go.dev/dl/"},
    "pwndbg": {"manual": "git clone https://github.com/pwndbg/pwndbg && cd pwndbg && ./setup.sh"},
    "sherlock": {"pip": "sherlock-project"},
    "holehe": {"pip": "holehe"},
    "maigret": {"pip": "maigret"},
    "phoneinfoga": {"manual": "https://github.com/sundowndev/phoneinfoga/releases"},
    "volatility3": {"pip": "volatility3"},
    "yt-dlp": {"pip": "yt-dlp"},
    "ripgrep": {"apt": "ripgrep"},
    "bat": {"apt": "bat"},
    "fd": {"apt": "fd-find"},
    "fzf": {"apt": "fzf"},
    "duf": {"snap": "duf"},
    "miller": {"apt": "miller"},
    "age": {"apt": "age"},
    "helm": {"snap": "helm --classic"},
    "kubectl": {"snap": "kubectl --classic"},
    "terraform": {"snap": "terraform --classic"},
    "awscli": {"pip": "awscli"},
    "rclone": {"apt": "rclone"},
    "imagemagick": {"apt": "imagemagick"},
    "mpv": {"apt": "mpv"},
    "neofetch": {"apt": "neofetch"},
    "cmatrix": {"apt": "cmatrix"},
    "btop": {"apt": "btop"},
    "lsof": {"apt": "lsof"},
}
