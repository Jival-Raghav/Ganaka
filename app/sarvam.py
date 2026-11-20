"""Sarvam AI adapter (speech-to-text, text-to-speech, translation). Uses the REST API when SARVAM_API_KEY is set;
otherwise returns None so the web app falls back to the browser's Web Speech API."""
import os, base64
LANG = {"en": "en-IN", "hi": "hi-IN", "kn": "kn-IN"}


def enabled():
    return bool(os.environ.get("SARVAM_API_KEY"))


def _h():
    return {"api-subscription-key": os.environ["SARVAM_API_KEY"]}


def transcribe(audio: bytes, filename="audio.webm", lang="kn"):
    if not enabled():
        return None
    import httpx
    r = httpx.post("https://api.sarvam.ai/speech-to-text", headers=_h(), files={"file": (filename, audio)}, data={"language_code": LANG.get(lang, "unknown"), "model": "saarika:v2.5"}, timeout=60)
    r.raise_for_status()
    return r.json().get("transcript")


def speak(text: str, lang="kn"):
    if not enabled():
        return None
    import httpx
    r = httpx.post("https://api.sarvam.ai/text-to-speech", headers={**_h(), "Content-Type": "application/json"},
                   json={"inputs": [text[:500]], "target_language_code": LANG.get(lang, "en-IN"), "model": "bulbul:v2"}, timeout=60)
    r.raise_for_status()
    a = r.json().get("audios", [None])[0]
    return a  # base64 wav


def translate(text: str, to_lang: str, from_lang="en"):
    if not enabled() or to_lang == from_lang:
        return None
    import httpx
    r = httpx.post("https://api.sarvam.ai/translate", headers={**_h(), "Content-Type": "application/json"},
                   json={"input": text, "source_language_code": LANG[from_lang], "target_language_code": LANG[to_lang], "model": "mayura:v1"}, timeout=60)
    r.raise_for_status()
    return r.json().get("translated_text")
