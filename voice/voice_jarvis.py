"""
Voice interface for Melvin God Mode — JARVIS-style voice assistant.
"""

import time
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# Optional imports — degrade gracefully when hardware is unavailable
try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False
    logger.warning("speech_recognition not installed; microphone input disabled")

try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    logger.warning("pyttsx3 not installed; text-to-speech disabled")

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

WAKE_WORDS = ("hey melvin", "melvin")

DEFAULT_CONFIG = {
    "ollama_url": "http://localhost:11434",
    "ollama_model": "llama3",
    "devops_agent_url": "http://localhost:8080/devops",
    "tts_rate": 175,
    "tts_volume": 0.9,
    "listen_timeout": 5,
    "phrase_time_limit": 15,
    "energy_threshold": 300,
    "dynamic_energy": True,
    "wake_word_required": True,
    "audio_feedback": True,
}

SYSTEM_KEYWORDS = (
    "docker", "container", "kubernetes", "k8s", "restart", "deploy",
    "service", "pod", "node", "cluster", "logs", "status",
)


class VoiceJarvis:
    """JARVIS-style voice assistant for Melvin God Mode."""

    def __init__(self, config: Optional[dict] = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self._running = False
        self.healing_log: list[dict] = []

        self._recognizer = self._init_recognizer()
        self._tts_engine = self._init_tts()
        self._microphone = self._init_microphone()

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _init_recognizer(self):
        if not SR_AVAILABLE:
            return None
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = self.config["energy_threshold"]
        recognizer.dynamic_energy_threshold = self.config["dynamic_energy"]
        return recognizer

    def _init_tts(self):
        if not TTS_AVAILABLE:
            return None
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", self.config["tts_rate"])
            engine.setProperty("volume", self.config["tts_volume"])
            # Prefer a male voice for the JARVIS aesthetic
            voices = engine.getProperty("voices")
            for voice in voices:
                if "male" in voice.name.lower() or "david" in voice.name.lower():
                    engine.setProperty("voice", voice.id)
                    break
            return engine
        except Exception as exc:
            logger.error("TTS engine init failed: %s", exc)
            return None

    def _init_microphone(self):
        if not SR_AVAILABLE:
            return None
        try:
            mic = sr.Microphone()
            # Quick warm-up calibration
            with mic as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=1)
            logger.info("Microphone initialised and calibrated")
            return mic
        except (OSError, AttributeError) as exc:
            logger.warning("Microphone not available: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Core I/O
    # ------------------------------------------------------------------

    def listen(self) -> str:
        """Capture a spoken phrase and return its transcription."""
        if not SR_AVAILABLE or self._microphone is None:
            logger.error("Microphone unavailable — cannot listen")
            return ""

        try:
            with self._microphone as source:
                logger.debug("Listening…")
                audio = self._recognizer.listen(
                    source,
                    timeout=self.config["listen_timeout"],
                    phrase_time_limit=self.config["phrase_time_limit"],
                )
            text = self._recognizer.recognize_google(audio).lower().strip()
            logger.info("Heard: %s", text)
            return text
        except sr.WaitTimeoutError:
            return ""
        except sr.UnknownValueError:
            logger.debug("Speech not understood")
            return ""
        except sr.RequestError as exc:
            logger.error("Speech recognition service error: %s", exc)
            return ""
        except Exception as exc:
            logger.error("Unexpected listen error: %s", exc)
            return ""

    def speak(self, text: str) -> None:
        """Convert *text* to speech."""
        print(f"[MELVIN] {text}")
        if not TTS_AVAILABLE or self._tts_engine is None:
            return
        try:
            self._tts_engine.say(text)
            self._tts_engine.runAndWait()
        except Exception as exc:
            logger.error("TTS error: %s", exc)

    # ------------------------------------------------------------------
    # Wake-word detection
    # ------------------------------------------------------------------

    def _contains_wake_word(self, text: str) -> bool:
        return any(w in text for w in WAKE_WORDS)

    def _strip_wake_word(self, text: str) -> str:
        for w in WAKE_WORDS:
            if text.startswith(w):
                return text[len(w):].strip(" ,")
        return text

    # ------------------------------------------------------------------
    # Command routing
    # ------------------------------------------------------------------

    def _is_system_command(self, text: str) -> bool:
        return any(kw in text for kw in SYSTEM_KEYWORDS)

    def _route_to_ollama(self, text: str) -> str:
        if not REQUESTS_AVAILABLE:
            return "Ollama client library not available."
        try:
            payload = {
                "model": self.config["ollama_model"],
                "prompt": text,
                "stream": False,
            }
            resp = requests.post(
                f"{self.config['ollama_url']}/api/generate",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except Exception as exc:
            logger.error("Ollama error: %s", exc)
            return "I could not reach the language model right now."

    def _route_to_devops_agent(self, text: str) -> str:
        if not REQUESTS_AVAILABLE:
            return "Requests library not available."
        try:
            resp = requests.post(
                self.config["devops_agent_url"],
                json={"command": text},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json().get("response", "DevOps command executed.")
        except Exception as exc:
            logger.error("DevOps agent error: %s", exc)
            return "DevOps agent is unreachable. Check your cluster."

    def process_command(self, text: str) -> str:
        """Route *text* to the appropriate back-end and return a response."""
        if not text:
            return ""

        text = text.strip()

        # Hard-coded utility commands
        if text in ("stop", "quit", "exit", "goodbye", "bye"):
            self._running = False
            return "Shutting down voice interface. Goodbye."

        if "what time is it" in text or "current time" in text:
            return f"The current time is {time.strftime('%H:%M')}."

        if "what day is it" in text or "today's date" in text:
            return f"Today is {time.strftime('%A, %B %d, %Y')}."

        if "help" in text:
            return (
                "I can answer questions, control containers, manage the cluster, "
                "and assist with your infrastructure. Just ask."
            )

        if self._is_system_command(text):
            return self._route_to_devops_agent(text)

        return self._route_to_ollama(text)

    # ------------------------------------------------------------------
    # Audio feedback
    # ------------------------------------------------------------------

    def _play_activation_sound(self) -> None:
        """Non-blocking audio feedback on wake-word detection."""
        if not self.config.get("audio_feedback"):
            return
        try:
            import os
            # Use system bell as a lightweight fallback
            os.system("echo -e '\a'")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Blocking main loop: listen → process → speak → repeat."""
        self._running = True
        logger.info("Voice interface started")
        self.speak("Melvin God Mode online. Awaiting your command.")

        while self._running:
            try:
                raw = self.listen()
                if not raw:
                    continue

                if self.config["wake_word_required"]:
                    if not self._contains_wake_word(raw):
                        continue
                    self._play_activation_sound()
                    command = self._strip_wake_word(raw)
                else:
                    command = raw

                if not command:
                    self.speak("Yes? How can I help?")
                    # Listen for the actual command immediately
                    command = self.listen()

                response = self.process_command(command)
                if response:
                    self.speak(response)

            except KeyboardInterrupt:
                logger.info("Voice loop interrupted by user")
                break
            except Exception as exc:
                logger.error("Voice loop error: %s", exc)
                time.sleep(1)

        logger.info("Voice interface stopped")

    def stop(self) -> None:
        """Signal the run loop to exit."""
        self._running = False

    def run_in_thread(self) -> threading.Thread:
        """Start the voice loop in a daemon thread."""
        t = threading.Thread(target=self.run, name="VoiceJarvis", daemon=True)
        t.start()
        return t


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    jarvis = VoiceJarvis()
    jarvis.run()
