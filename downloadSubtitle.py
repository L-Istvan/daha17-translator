"""Török SRT felirat letöltése a Kanal D akadálymentes epizódoldaláról.

Az epizódszám alapján megkeresi a doy<epizód>.srt hivatkozást, feloldja
annak relatív URL-jét, és ellenőrzi az SRT időzítés jelenlétét.
A feliratot az MP4-hez illő néven menti a meglévő célmappába, felülírás nélkül.
A download_subtitle() a fájl útvonalát adja vissza; hiányzó feliratnál vagy
hibánál None-t ad és üzenetet ír. A megszakítást 130-as kilépési kóddal jelzi.
"""

import re
import sys
from html import unescape
from pathlib import Path
from urllib.parse import urljoin

import requests


def _download_subtitle(episode, directory):
    """A doy<epizód>.srt hivatkozás feloldása és mentése felülírás nélkül."""
    if isinstance(episode, bool) or not isinstance(episode, int) or episode < 1:
        raise ValueError("Az epizódszám pozitív egész legyen.")
    directory = Path(directory).expanduser().resolve()
    if not directory.exists():
        raise ValueError(f"A letöltési mappa nem létezik: {directory}")
    if not directory.is_dir():
        raise ValueError(f"A letöltési hely nem mappa: {directory}")
    output = directory / f"Daha17_{episode}_1080p.tr.srt"
    if output.exists():
        print(f"A felirat már létezik, kihagyva: {output}")
        return output
    page_url = f"https://engelsiz.kanald.com.tr/daha-17/bolumler/daha-17-{episode}-bolum"
    page = requests.get(page_url, timeout=30)
    page.raise_for_status()
    match = re.search(rf'''[^"'<>\s]*\bdoy{episode}\.srt\b(?:\?[^"'<>\s]*)?''', page.text, re.I)
    if match is None:
        print(f"Nem található török felirat a(z) {episode}. részhez.")
        return None
    subtitle_url = urljoin(page.url or page_url, unescape(match.group(0)))
    subtitle = requests.get(subtitle_url, timeout=30)
    subtitle.raise_for_status()
    # A HTTP 200 önmagában nem elég: hibaoldalt ne mentsünk SRT-ként.
    text = subtitle.content.decode("utf-8-sig", errors="replace")
    if not re.search(r"\d{2}:\d{2}:\d{2},\d{3}\s+-->\s+\d{2}:\d{2}:\d{2},\d{3}", text):
        raise RuntimeError("A letöltött felirat nem érvényes SRT.")
    try:
        with output.open("xb") as file:
            file.write(subtitle.content)
    except FileExistsError:
        print(f"A felirat már létezik, kihagyva: {output}")
        return output
    except OSError:
        output.unlink(missing_ok=True)
        raise
    print(f"Török felirat kész: {output}")
    return output


def download_subtitle(episode, directory):
    """Paraméterezhető belépési pont a feliratletöltés saját hibakezelésével."""
    try:
        return _download_subtitle(episode, directory)
    except KeyboardInterrupt:
        print("\nFeliratletöltés megszakítva.", file=sys.stderr)
        raise SystemExit(130)
    except (requests.RequestException, OSError, RuntimeError, ValueError) as error:
        print(f"A felirat letöltése sikertelen: {error}", file=sys.stderr)
        return None
