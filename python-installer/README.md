# Melvin God Mode – Python Installer

An all-in-one, interactive **TUI (Text User Interface)** installer for
**Melvin God Mode**, written in pure Python using the built-in `curses` module.

No extra pip packages required – just Python 3.9+.

## Features

- Full-screen terminal UI with keyboard navigation
- Install, configure, update, and uninstall flows
- Live progress bars for each installation step
- Model selection menu (Ollama models)
- Automatic detection of already-installed components

## Usage

```bash
python3 installer.py
```

Or make it executable and run directly:

```bash
chmod +x installer.py
./installer.py
```

## Requirements

- Python 3.9 or newer
- `curses` module (included in Python standard library on Linux/macOS)
- Internet connection (for downloading Ollama and AI models)
- `sudo`/root access (for system-level installation steps)

## Navigation

| Key | Action |
|-----|--------|
| `↑` / `↓` | Move selection up / down |
| `Enter` | Confirm selection |
| `q` / `Esc` | Go back / quit |
| `Space` | Toggle checkbox option |

## Supported Platforms

The Python installer works on any Unix-like system with Python 3.9+.
For Debian-specific helpers (systemd service, apt packages) see the
`../Debian/` folder.
