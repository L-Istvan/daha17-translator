"""Török felirat közvetlen letöltése a CDN-ről."""

from pathlib import Path
import sys

import requests
from subtitleTranslation import parse_subtitle


def download_subtitle(episode, directory, *, raise_errors=False):
    output = Path(directory).expanduser().resolve() / f"Daha17_{episode}_1080p.tr.srt"
    url = f"https://cdn.duhnet.tv/C13/2013kanald/dizi/daha17/doy{episode}.srt"
    try:
        if output.exists():
            parse_subtitle(output.read_text(encoding='utf-8-sig'))
            print(f"A felirat már létezik, kihagyva: {output}")
            return output
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        parse_subtitle(response.content.decode('utf-8-sig'))
        temporary = output.with_suffix('.srt.part')
        temporary.write_bytes(response.content)
        temporary.replace(output)
    except KeyboardInterrupt:
        if raise_errors:
            raise
        raise SystemExit(130)
    except (requests.RequestException, OSError, ValueError) as error:
        if raise_errors:
            raise
        print(f"A felirat letöltése sikertelen: {error}", file=sys.stderr)
        return None
    print(f"Török felirat kész: {output}")
    return output
