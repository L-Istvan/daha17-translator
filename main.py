"""Videóletöltés, török felirat letöltése és magyar fordítás külön hívásokkal."""

from downloader import dowloadEpisod
from downloadSubtitle import download_subtitle
from subtitleTranslation import translate_episode_subtitle


if __name__ == "__main__":
    dowloadEpisod(
        directory=".",
        target_episode=25,
        page_url="https://www.kanald.com.tr/daha-17/bolumler/daha-17-son-bolum",
    )
    download_subtitle(
        episode=25,
        directory=".",
    )
    translate_episode_subtitle(
        episode=25,
        directory=".",
        model="gpt-6.2-astra",
        batch_size=100,
        start_number=1,
        context_blocks=10,
        lookahead_blocks=5,
        memory_path="series_memory.json",
        cache_policy="auto",
    )
