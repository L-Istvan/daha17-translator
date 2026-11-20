 # Telepítés

1. Virtuális környezet létrehozása
```python3 -m venv .venv```

2. Virtuális környezet aktiválása
```source .venv/bin/activate```

3. Könyvtárak telepítése
```pip install requests beautifulsoup4 python-dotenv```
A szükséges Python-könyvtárakat telepíti:
- requests: weboldalak lekérése HTTP-n keresztül.
- beautifulsoup4: HTML-oldalak feldolgozása, például címek keresése.
- python-dotenv: a helyi `.env` fájl betöltése.

4. Playwright és a háttérben futó Chromium telepítése
```bash
pip install playwright
python3 -m playwright install chromium
```

5. Letöltő telepítése
```bash
pip install yt-dlp
```
Az MP4 elkészítéséhez az `ffmpeg` parancsnak is elérhetőnek kell lennie.

## Futtatás

```bash
python3 main.py
```

A beállításokat a `main.py` három hívásában add meg:

```python
from downloader import dowloadEpisod
from downloadSubtitle import download_subtitle
from subtitleTranslation import translate_episode_subtitle


if __name__ == "__main__":
    dowloadEpisod(
        directory="/home/fedora/Videók",
        target_episode=25,
        page_url="https://www.kanald.com.tr/daha-17/bolumler/daha-17-son-bolum",
    )
    download_subtitle(episode=25, directory="/home/fedora/Videók")
    translate_episode_subtitle(
        episode=25, directory="/home/fedora/Videók",
        model="gpt-6.2-astra", batch_size=100,
        start_number=1, context_blocks=10, lookahead_blocks=5,
        memory_path="series_memory.json", cache_policy="auto",
    )
```

A `directory` egy már létező célmappa; a `"."` az aktuális munkamappát jelenti.
Nem létező útvonal vagy fájl megadása esetén a program még a hálózati
lekérések előtt hibával leáll; nem hoz létre mappát.
A `target_episode` a minimálisan várt epizódszám, a `page_url` az epizódoldal címe.
A fájlnév az oldal tényleges epizódszámát követi, például
`Daha17_25_1080p.mp4`. Meglévő MP4-et nem ír felül.

A program ellenőrzi az epizód számát, lekéri az oldal Dailymotion-videóazonosítóját,
majd ablak nélkül betölti a Dailymotion-lejátszót. A kapott HLS mesterlistából
kifejezetten a `/h264_aac_fhd/.../manifest.m3u8` címet választja ki és ellenőrzi.
Nem kell kézzel kattintani vagy Entert nyomni. A lejátszó betöltése után legfeljebb
60 másodpercig vár az FHD címre; hiányában hibával kilép.

A cím aláírást tartalmaz, ezért később lejárhat. Friss címért futtasd újra a programot.

A feliratletöltés az explicit megadott `episode` részhez tartozó
`https://engelsiz.kanald.com.tr/daha-17/bolumler/daha-17-<epizódszám>-bolum`
oldalon megkeresi a `doy<epizódszám>.srt` hivatkozást. A relatív címet feloldja,
és a török feliratot az MP4 mellé menti, például `Daha17_24_1080p.tr.srt` néven.
Így a lejátszók a videóhoz társíthatják. Meglévő feliratot nem ír felül.
Ha nincs felirat vagy hibás a letöltése, ezt jelzi, és `None`-t ad vissza. A felirat tartalmában SRT időzítést is ellenőriz.
A videó és a felirat letöltését külön a `main.py` hívja meg; a `downloader.py`
csak a videót kezeli. A felirat epizódszámát külön paraméterként kell megadni.
A videó minimum epizódszáma és a felirat pontos epizódszáma külön beállítás;
ha az oldal újabb videót kínál, a felirat továbbra is a megadott részhez készül.
A felirat hibakezelése a `downloadSubtitle.py`-ban van.

## Magyar felirat fordítása

A `subtitleTranslation.py` memóriába tölti a török SRT-t, és 100 forrásblokkos
adagokat dolgoz fel. A `main.py` továbbra is csak paraméterezett hívásokat tartalmaz.

A `series_memory.json` tartalmazza a jóváhagyott neveket, beceneveket,
kapcsolatokat és a 160 szavas, a 24. rész végéig ismert történeti összefoglalót.
Minden API-kérés megkapja ezt a stabil háttéranyagot. A modell nem írja át a
memóriát; új eseményeknél kézzel frissítendő. A `ready` memória összefoglalója
150–250 szavas lehet. A szereplők tudását nem szabad az elbeszélői háttértudással
azonosítani, és a háttérből nem szabad párbeszédet kitalálni.

Minden fordítási kéréshez az előző legfeljebb 10 megtartott blokk török–magyar
párja kerül előzményként, valamint a következő 5 török blokk előretekintésként.
Ezek kizárólag háttéradatok, az API csak az aktuális adagot fordítja le.
A megtartott magyar blokkok folyamatos sorszámozása alapértelmezetten 1-ről
indul; a kihagyások nem fogyasztanak magyar sorszámot. A prompt rögzíti a
természetes párbeszéd, névkövetkezetesség, megszólítások és tartalmi szűrés szabályait.

A `subtitleQuality.py` kiszámolja a megjelenési időt, a szóközökkel együtt mért
látható karakterszámot, a karakter/másodperc értéket és a sorhosszakat. A 17 CPS
feletti sebesség, a két sornál több és a 42 karakternél hosszabb sor figyelmeztetés.
A sortörések és HTML-formázó tagek nem számítanak látható karakternek. A nem
pozitív vagy hibás időzítés hibát okoz. A 15–17 CPS irányérték, a jelentés fontosabb.

Az API minden kihagyott forrásblokkot **külön ellenőrzési kérésben** vizsgál meg.
A megtartandónak ítélt beszédet visszapótolja; a bizonytalan, hiányos vagy hibás
döntés megállítja az adagot. Ezt követően kizárólag az olvashatósági hibás magyar
blokkokat küldi vissza egy javítási körre, a környező török–magyar mondatokkal.
Az ép blokkokat nem fordítja újra. A javítás sem módosíthat sorszámot vagy időzítést.
A maradó olvashatósági problémák a jelentésben szerepelnek, további automatikus
javítási kör nincs. A fordítás és a kihagyásellenőrzés is modellválasz, nem emberi
tartalmi garancia.

A kész `.hu.srt` mellé `.hu.review.json` jelentés kerül a kihagyott török szövegekkel,
a külön API-audit döntéseivel és minden magyar blokk olvashatósági mérésével.
A kihagyások továbbra is felülvizsgálhatók; a `semantic_completeness_verified`
értéke nem válik automatikusan igazzá. Azonos időzítésű több forrásblokk esetén
a program megáll, mert az SRT-válaszból nem lehetne biztosan párosítani őket.

### Folytatás mentett adagokból

A `.hu.checkpoints/` könyvtárban atomi JSON-fájlokba menti minden sikeres adag
kezdeti fordítását és ellenőrzött változatát. A sikeres API-válaszokat is megőrzi,
így egy későbbi javítási lépés hibája után a korábbi sikeres hívásokat nem ismétli.
Az állapot a teljes forráshoz, modellhez, prompthoz, memóriához és az adagolási
beállításokhoz kötött. Ha ezek változnak, új munkamenet indul; a régi mentés
megmarad. A mentések tartalomlenyomatát beolvasáskor ellenőrzi.

Félbeszakadt fordításhoz közvetlenül a fordítást hívd újra azonos paraméterekkel,
így a már létező videót nem kell újra letölteni:

```python
from subtitleTranslation import translate_episode_subtitle

translate_episode_subtitle(
    episode=25, directory=".", model="gpt-6.2-astra",
    batch_size=100, start_number=1, context_blocks=10,
    lookahead_blocks=5, memory_path="series_memory.json", cache_policy="auto",
)
```

A teljes magyar SRT-t és jelentést csak minden adag sikeres feldolgozása után
menti. Meglévő végleges kimenetet nem ír felül. Új modell vagy memória kipróbálásához
előbb nevezd át a két végleges kimenetet; a checkpointok elkülönülnek. Sérült
mentésnél megáll, nem fizet automatikusan újrafordításért. Egy API-hívás szerveroldali
sikere és a helyi mentés közötti megszakadás esetén nem garantálható a kettős költség
elkerülése. A mentések és válaszfájlok feliratszöveget tartalmaznak, API-kulcsot nem.

### API és mérés

Az API-kulcsot a projekt `.env` fájljában add meg: `OPENAI_API_KEY=sajat_kulcs`.
A fordító automatikusan betölti; a már megadott környezeti változót nem írja felül.
A `.env` Gitből kizárt, és csak a tulajdonosa olvashatja/írhatja.

Az `OPENAI_API_KEY` környezeti változó szükséges. Bashben parancselőzményekbe
írás nélkül megadható:

```bash
read -rsp 'OpenAI API-kulcs: ' OPENAI_API_KEY
export OPENAI_API_KEY
python3 main.py
```

A meglévő `requests` csomagot használja. A fordítás, kihagyásellenőrzés és javítás
külön díjköteles hívások; a hibátlan, kihagyás nélküli adaghoz csak a fordítás kell.
Az API megkapja a feliratot és a sorozatmemóriát, `store=False` beállítással.

A `cache_policy="auto"` GPT-5.6 és újabb modelleknél a stabil developer-prefix
végére explicit cache-határt tesz, 30 perces élettartammal. Ilyen modellnél
`"12h"` is választható. Régebbi modellnél az `auto` nem küld új cache-paramétert;
a modell és a fiók támogatása szerint `"in_memory"` vagy `"24h"` adható meg.
A cache-írás is járhat költséggel, a találat nem garantált.
Lásd az [OpenAI cache-dokumentációját](https://developers.openai.com/api/docs/guides/prompt-caching).

A `.hu.usage.jsonl` napló hívásonként tárolja a modell nevét, feladattípust,
futásidőt, bemeneti/kimeneti/összes tokeneket, cached tokeneket, cache-írási
tokeneket (ha az API közli), és a cache-találat tényét. Megkülönbözteti a helyi
válasz- és adagújrafelhasználást a szerveroldali cache-találattól. Az API-hibák,
az adagok és a sikeres teljes futás ideje is naplózva van. A mérési napló nem
tartalmaz kulcsot vagy feliratszöveget. Az API és hálózati hibákra nincs korlátlan
automatikus újrapróbálás: az újraindítás a helyi mentésekből folytat.

A letöltést a yt-dlp végzi négy párhuzamos szegmenssel (`-N 4`),
`--abort-on-unavailable-fragments` és `--remux-video mp4` beállítással.
Az MP4-be csomagolás nem kódolja újra a videót. Sikertelen letöltés esetén
a program hibával lép ki; a részleges fájlok megmaradhatnak a folytatáshoz.

A letöltés után a program elutasítja az üres fájlt, majd FFmpeggel végigolvassa
és dekódolja a videót és a hangsávokat. Csak sikeres ellenőrzés után jelzi késznek
a letöltést. Ez nagy fájlnál időbe telhet; a hibás MP4 megmarad, ezért újrapróbálás
előtt el kell távolítani vagy át kell nevezni.

## Tesztek

```bash
.venv/bin/python -m unittest -v
```

A tesztek nem töltenek le videót az internetről. Az FFmpeg ellenőrzéséhez
egy rövid helyi tesztvideót állítanak elő; ez a teszt FFmpeg nélkül kimarad.

## Fájlok

- `main.py`: videóletöltés, feliratletöltés és fordítás paraméterezett hívásai.
- `downloader.py`: ellenőrzések, Dailymotion FHD cím kinyerése, videóletöltés és hibakezelés.
- `downloadSubtitle.py`: a török SRT felirat keresése, ellenőrzése és mentése.
- `subtitleTranslation.py`: memóriába olvasás, 100 blokkonkénti API-fordítás és magyar SRT mentése.
- `series_memory.json`, `seriesMemory.py`: jóváhagyott sorozatháttér és ellenőrzött betöltése.
- `subtitleApi.py`: API-hívások, cache-beállítás, kihagyásellenőrzés és célzott javítás.
- `translationStorage.py`: atomi mentés, lenyomatok és mérési napló.
- `test_translationPipeline.py`: több lépéses fordítás, helyreállítás és költségmentes API-szimuláció tesztjei.
- `subtitleQuality.py`: időtartam, olvasási sebesség, sorhossz és kihagyások ellenőrzése.
- `test_subtitleQuality.py`: olvashatósági mérés és kihagyásjelentés tesztjei.
- `test_subtitleTranslation.py`: adagolás, fordítási válaszok és API-hibák tesztjei, fizetős hívás nélkül.
- `test_downloader.py`, `test_downloadSubtitle.py`: videó- és feliratletöltési tesztek.
