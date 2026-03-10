# Melvin God Mode – Debian

This folder contains scripts and configuration files for installing and setting up **Melvin God Mode** on Debian-based systems (Debian, Ubuntu, Linux Mint, Pop!_OS, etc.).

## Requirements

- Debian 11 (Bullseye) or newer / Ubuntu 20.04 LTS or newer
- Root or sudo access
- Internet connection (for downloading dependencies)
- Python 3.9+

## Scripts

| Script | Description |
|--------|-------------|
| `install.sh` | Full installation: installs all dependencies and sets up Melvin God Mode |
| `setup-dependencies.sh` | Installs only the system-level dependencies (useful for offline/custom installs) |
| `configure.sh` | Interactive post-install configuration (models, storage paths, encryption keys) |

## Quick Start

```bash
# Clone the repository (if you haven't already)
git clone https://github.com/marcusjenkinscode/Melvin-God-Mode.git
cd Melvin-God-Mode/Debian

# Make scripts executable
chmod +x *.sh

# Run the full installer
sudo ./install.sh
```

## What Gets Installed

- **Python 3** and pip (if not already present)
- Required Python packages (`requirements.txt` in project root)
- **Ollama** – local LLM runner for serving AI models
- Systemd service unit for auto-starting Melvin on boot (optional)
- Default configuration file at `~/.config/melvin/config.json`
- Encrypted chat history directory at `~/.local/share/melvin/chats/`

## Notes

- All AI model weights are stored locally and never transmitted externally.
- Chat history is stored in JSON blocks and encrypted at rest using AES-256.
- To uninstall, run `sudo ./install.sh --uninstall`.
