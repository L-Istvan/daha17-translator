"""Daha 17 epizód letöltése a Kanal D oldaláról, Dailymotion FHD forrásból.

A feldolgozás fő lépései:
1. Ellenőrzi a célmappát, majd lekéri az epizódoldalt és kiolvassa a rész számát.
   A target_episode minimum: az ennél újabb epizódot is elfogadja.
2. Lekéri a Dailymotion azonosítóit, majd háttérben futó Chromium böngészővel
   megkeresi és ellenőrzi az FHD HLS lejátszási lista (manifest) címét.
3. A yt-dlp letölti a videót, és FFmpeggel MP4-be csomagolja újrakódolás nélkül.
4. Elutasítja az üres fájlt, majd FFmpeggel végigdekódolja a videót és a hangot;
   csak sikeres ellenőrzés után jelzi késznek a letöltést.

A main.py a run() függvényt hívja exact_episode=True értékkel, és közösen
naplózza a hibákat. A run() a kész fájl útvonalát adja vissza, vagy None-t,
ha nincs megfelelő epizód; hiba esetén kivételt dob. A külön használható
dowloadEpisod() a hibákat kilépési kóddá alakítja.
Meglévő MP4-et nem ír felül. Telepítés és futtatás: README.md.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path
import time
from urllib.parse import urlencode, urldefrag, urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import Error as PlaywrightError, sync_playwright

URL = "https://www.kanald.com.tr/daha-17/bolumler/daha-17-son-bolum"
TARGET_EPISODE = 25


def check_episode(soup, target_episode=TARGET_EPISODE):
    title = soup.find("h1")

    if not title:
        print("Nem található az epizód címe.")
        return None

    text = title.get_text(" ", strip=True)
    match = re.search(r"Daha\s*17\s+(\d+)\.\s*Bölüm", text, re.I)

    if not match:
        print(f"Nem sikerült azonosítani az epizódot: {text}")
        return None

    episode = int(match.group(1))

    if episode < target_episode:
        print(f"Még nincs {target_episode}. rész. Legutóbbi: {episode}.")
        return None

    print(f"Elérhető a {episode}. rész!")
    return episode


def is_fhd_manifest(url):
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and (parsed.hostname or "").endswith(".dmcdn.net")
        and "/h264_aac_fhd/" in parsed.path
        and parsed.path.endswith("/manifest.m3u8")
    )


def find_manifest(soup, page_url=URL):
    container = soup.select_one('.player-container[data-pq-type="Dailymotion"]')
    if container is None or not container.get("data-id"):
        raise RuntimeError("Az epizód Dailymotion-lejátszója nem található.")

    response = requests.get(
        urljoin(page_url, "/actions/media"),
        params={
            "id": container["data-id"],
            "p": container.get("data-part", "1"),
            "pc": container.get("data-part-count", "1"),
        },
        headers={"Referer": page_url},
        timeout=30,
    )
    response.raise_for_status()
    try:
        link = response.json()
        for key in ("data", "media", "link"):
            link = link.get(key) if isinstance(link, dict) else None
        if not isinstance(link, dict):
            raise ValueError("Hiányzó link mező")
    except ValueError as error:
        raise RuntimeError("Hibás Dailymotion médiaválasz.") from error
    video_id = link.get("securePath", "")
    player_id = link.get("serviceName", "")
    if not isinstance(video_id, str) or not isinstance(player_id, str) or not re.fullmatch(r"[A-Za-z0-9]+", video_id) or not re.fullmatch(r"[A-Za-z0-9]+", player_id):
        raise RuntimeError("Hiányos Dailymotion videó- vagy lejátszóazonosító.")

    candidates = []

    def remember(url):
        url = urldefrag(url)[0]
        if is_fhd_manifest(url) and url not in candidates:
            candidates.append(url)

    def inspect_response(response):
        remember(response.url)
        # Az FHD címet már a mesterlista is tartalmazza, akkor is,
        # ha az automatikus minőségválasztás kisebb felbontást indít.
        if response.ok and urlparse(response.url).path.endswith(".m3u8"):
            try:
                body = response.text()
            except PlaywrightError:
                return
            if body.lstrip("\ufeff \t\r\n").startswith("#EXTM3U"):
                for line in body.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        remember(urljoin(response.url, line))

    print("Dailymotion FHD manifest keresése a háttérben...", flush=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--autoplay-policy=no-user-gesture-required"],
        )
        try:
            # A HeadlessChrome azonosítóval a szolgáltató szűkebb
            # minőségi listát adhat. A böngésző továbbra is ablak nélkül fut.
            context = browser.new_context(user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{browser.version} Safari/537.36"
            ))
            page = context.new_page()
            page.on("response", inspect_response)
            embed_url = (
                f"https://geo.dailymotion.com/player/{player_id}.html?"
                + urlencode({"video": video_id, "autoplay": "1", "mute": "1"})
            )
            page.goto(embed_url, referer=page_url, wait_until="domcontentloaded", timeout=60000)
            deadline = time.monotonic() + 60
            while not candidates and time.monotonic() < deadline:
                page.wait_for_timeout(500)

            if not candidates:
                raise RuntimeError(
                    "60 másodpercen belül nem érkezett Dailymotion FHD manifest. "
                    "A lejátszó nem kínált /h264_aac_fhd/ címet."
                )

            url = candidates[0]
            manifest = context.request.get(url, timeout=30000)
            if not manifest.ok or not manifest.text().lstrip("\ufeff \t\r\n").startswith("#EXTM3U"):
                raise RuntimeError(f"Az FHD manifest nem érhető el (HTTP {manifest.status}).")
            print("\nDailymotion FHD manifest URL:")
            print(url)
            return url
        finally:
            browser.close()


def validate_download_directory(directory):
    path = Path(directory).expanduser().resolve()
    if not path.exists():
        raise ValueError(f"A letöltési mappa nem létezik: {path}")
    if not path.is_dir():
        raise ValueError(f"A letöltési hely nem mappa: {path}")
    return path


def download_episode(manifest_url, episode, directory):
    directory = validate_download_directory(directory)
    output = directory / f"Daha17_{episode}_1080p.mp4"
    if output.exists():
        print(f"A videó már létezik, letöltés kihagyva: {output}")
        return validate_video(output)
    executable = shutil.which("yt-dlp")
    if executable is None:
        raise RuntimeError("A yt-dlp nem található. Telepítés: pip install yt-dlp")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("Az MP4 elkészítéséhez telepíteni kell az FFmpeg programot.")

    print(f"Letöltés ide: {output}", flush=True)
    try:
        subprocess.run([
            executable,
            "-N", "4",
            "--abort-on-unavailable-fragments",
            "--remux-video", "mp4",
            "--no-overwrites",
            "-P", str(directory),
            "-o", f"Daha17_{episode}_1080p.%(ext)s",
            "--", manifest_url,
        ], check=True)
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"A yt-dlp letöltés sikertelen (kilépési kód: {error.returncode}).") from error
    return validate_video(output)


def validate_video(output):
    """A meglévő videót sem töltjük újra, de hibás fájllal nem folytatjuk."""
    if not output.is_file():
        raise RuntimeError(f"A letöltés után nem található az MP4: {output}")
    if output.stat().st_size == 0:
        raise RuntimeError(f"A letöltött MP4 üres: {output}")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("A videó ellenőrzéséhez telepíteni kell az FFmpeg programot.")
    print("Az MP4 épségének ellenőrzése...", flush=True)
    try:
        subprocess.run([
            ffmpeg, "-nostdin", "-v", "error", "-xerror",
            "-i", str(output), "-map", "0:v:0", "-map", "0:a?",
            "-f", "null", "-",
        ], check=True, capture_output=True)
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"A letöltött MP4 sérült vagy nem olvasható: {output}") from error
    print(f"Letöltés kész: {output}")
    return output


def run(directory=".", target_episode=TARGET_EPISODE, page_url=URL, *, exact_episode=False):
    if isinstance(target_episode, bool) or not isinstance(target_episode, int) or target_episode < 1:
        raise ValueError("Az epizódszám pozitív egész legyen.")
    directory = validate_download_directory(directory)
    output = directory / f"Daha17_{target_episode}_1080p.mp4"
    if output.exists():
        print(f"A videó már létezik, letöltés kihagyva: {output}")
        return validate_video(output)
    response = requests.get(page_url, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    episode = check_episode(soup, target_episode)
    if episode is None:
        return None
    if exact_episode and episode != target_episode:
        raise RuntimeError(f"A kért {target_episode}. rész helyett a(z) {episode}. rész érhető el az oldalon.")
    manifest_url = find_manifest(soup, page_url)
    return download_episode(manifest_url, episode, directory)


def dowloadEpisod(*, directory=".", target_episode=TARGET_EPISODE, page_url=URL):
    try:
        return run(directory=directory, target_episode=target_episode, page_url=page_url)
    except KeyboardInterrupt:
        print("\nLetöltés megszakítva.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as error:
        print(f"Hiba történt: {error}", file=sys.stderr)
        raise SystemExit(1)
