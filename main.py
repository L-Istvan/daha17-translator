"""Videó → török felirat → magyar fordítás → opcionális Videa-feltöltés."""

from datetime import datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

from downloader import run as download_video, URL
from downloadSubtitle import download_subtitle
from subtitleTranslation import translate_episode_subtitle
from uploadVidea import upload_video
from videaSubtitles import attach_subtitle

episode = 25
max_batches = None
upload_to_videa = True


def record_status(directory, stage, status, reason):
    timestamp = datetime.now(ZoneInfo("Europe/Budapest")).isoformat(timespec="seconds")
    reason = str(reason).replace("\n", " ")
    line = f"{timestamp} | {status} | {stage} | {reason}"
    print(line, flush=True)
    try:
        with (Path(directory).expanduser() / "pipeline.log").open("a", encoding="utf-8") as file:
            file.write(line + "\n")
    except OSError as error:
        print(f"A pipeline.log nem írható: {error}", file=sys.stderr)


def run_pipeline(*, episode=25, directory=".", max_batches=6, upload=False):
    stage = "------- 1. Videó ----------"
    try:
        if upload and max_batches is not None:
            stage = "4. Videa-feltöltés"
            raise ValueError('A tesztfordítás után nincs automatikus feltöltés. Teljes futáshoz max_batches=None szükséges.')
        video = download_video(directory=directory, target_episode=episode,
                               page_url=URL, exact_episode=True)
        if video is None:
            raise RuntimeError(f"A(z) {episode}. rész nem elérhető vagy nem azonosítható az oldalon.")
        record_status(directory, stage, "KÉSZ", video)

        stage = "--------- 2. Török felirat ----------"
        subtitle = download_subtitle(episode=episode, directory=directory, raise_errors=True)
        if subtitle is None:
            raise RuntimeError("A török felirat nem érhető el vagy a letöltése sikertelen.")
        record_status(directory, stage, "KÉSZ", subtitle)

        stage = "-------- 3. Magyar fordítás --------"
        translated = translate_episode_subtitle(
            episode=episode,
            directory=directory,
            model="gpt-6-sol",
            batch_size=100,
            max_batches=max_batches,
            start_number=1,
            context_blocks=10,
            lookahead_blocks=5,
            memory_path="series_memory.json",
            cache_policy="auto",
            raise_errors=True,
        )
        if translated is None:
            raise RuntimeError("A magyar fordítás nem készült el.")
        record_status(directory, stage, "KÉSZ", translated)
        if upload:
            stage = "4. Videa-feltöltés"
            url = upload_video(video, title=f"Daha 17 – {episode}. rész")
            attach_subtitle(video, translated)
            record_status(directory, stage, "KÉSZ", url)
    except KeyboardInterrupt:
        record_status(directory, stage, "LEÁLLT", "Felhasználói megszakítás (Ctrl+C).")
        return 130
    except Exception as error:
        record_status(directory, stage, "LEÁLLT", f"{type(error).__name__}: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run_pipeline(episode=episode, max_batches=max_batches, upload=upload_to_videa))
