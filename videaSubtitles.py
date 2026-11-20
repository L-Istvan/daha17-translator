"""SRT csatolása meglévő videóhoz a Videa saját feliratkezelő kérésével."""

import argparse
import json
from pathlib import Path
import re
import sys

from playwright.sync_api import Error as PlaywrightError, sync_playwright

from subtitleTranslation import format_subtitle, parse_subtitle
from translationStorage import atomic_json, digest
from uploadVidea import HOME, SESSION, checked_response


def attach_subtitle(video, subtitle, *, name='Magyar', session_path=SESSION):
    """Csak az SRT-t menti; az MP4-et és a videó adatlapját nem módosítja.

    A Videa all_head.js fájljának VIDEA.subtitles.saveSubtitle() és
    validateSubtitle() műveleteit követi. Bizonytalan írást nem ismétel meg.
    """
    video = Path(video).expanduser().resolve()
    subtitle = Path(subtitle).expanduser().resolve()
    if not video.is_file() or not video.stat().st_size:
        raise ValueError(f'A videó hiányzik vagy üres: {video}')
    text = subtitle.read_text(encoding='utf-8-sig')
    text = format_subtitle(parse_subtitle(text)) + '\n'
    if not name.strip() or len(text.encode('utf-8')) > 1024 * 1024:
        raise ValueError('Nem üres feliratnév és legfeljebb 1 MB-os SRT szükséges.')

    state_path = video.with_suffix('.videa.json')
    state = json.loads(state_path.read_text())
    stat = video.stat()
    identity = {'path': str(video), 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}
    if state.get('file') != identity:
        raise RuntimeError('A videó nem egyezik a feltöltési mentésben szereplő fájllal.')
    vcode = state.get('vcode', '')
    if state.get('status') != 'complete' or not isinstance(vcode, str) or not re.fullmatch(r'[A-Za-z0-9]{16}', vcode):
        raise RuntimeError('A feliratcsatoláshoz sikeresen elmentett Videa-videó szükséges.')
    fingerprint = digest({'name': name, 'srt': text})
    records = state.setdefault('subtitles', {})
    previous = records.get(name)
    if previous:
        if previous.get('status') == 'complete' and previous.get('hash') == fingerprint:
            print(f'A(z) {name} felirat már csatolva, kihagyva.')
            return previous['st_id']
        raise RuntimeError(f'A(z) {name} felirat már szerepel a mentésben, eltérő vagy bizonytalan állapotban. '
                           'Ellenőrizd a Videa feliratait; nem csatolok automatikusan másolatot.')

    session_path = Path(session_path)
    if not session_path.is_file():
        raise RuntimeError('Videa-belépés szükséges: python3 uploadVidea.py --login')
    with sync_playwright() as playwright:
        request = playwright.request.new_context(storage_state=str(session_path))
        try:
            def command(cmd, **fields):
                payload = {'cmd': cmd, **fields}
                response = request.post(HOME + '/interface?logcmd=' + cmd,
                    form={'json': json.dumps(payload, ensure_ascii=False)},
                    headers={'Origin': HOME, 'Referer': HOME + '/feltoltes'}, timeout=60000)
                return checked_response(response, cmd)

            # A szerver előbb ellenőrzi a formátumot; ez még nem csatol feliratot.
            command('validateVideoSubtitleByRequest', srt=text)
            records[name] = {'hash': fingerprint, 'status': 'attaching', 'file': str(subtitle)}
            atomic_json(state_path, state)
            print(f'Videa: {name} felirat csatolása...', flush=True)
            added = command('addVideoSubtitleByRequest', index=0, vcode=vcode,
                            name=name, filename=subtitle.name, shift=0, srt=text)
            st_id = added.get('st_id')
            if isinstance(st_id, bool) or not str(st_id).isdigit() or int(st_id) <= 0:
                raise RuntimeError('A Videa nem adott érvényes feliratazonosítót; az eredmény bizonytalan.')
            records[name].update(status='complete', st_id=st_id)
            atomic_json(state_path, state)
            print(f'Videa: {name} felirat elmentve (azonosító: {st_id}).')
            return st_id
        except PlaywrightError:
            raise RuntimeError('A Videa feliratkezelő kérése sikertelen vagy időtúllépés történt. '
                               f'Ellenőrizd a videó feliratait és a mentést: {state_path}') from None
        finally:
            request.dispose()


def cli():
    parser = argparse.ArgumentParser(description='Magyar SRT csatolása már feltöltött Videa-videóhoz, MP4-átvitel nélkül.')
    parser.add_argument('video', type=Path)
    parser.add_argument('subtitle', type=Path)
    parser.add_argument('--name', default='Magyar')
    args = parser.parse_args()
    try:
        attach_subtitle(args.video, args.subtitle, name=args.name)
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        print(f'Videa-felirat: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(cli())
