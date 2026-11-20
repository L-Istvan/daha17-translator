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

A `main.py` sorrendben futtatja a videóletöltést, a török felirat letöltését,
majd a magyar fordítást. Bármelyik lépés hibájánál azonnal leáll; a következő
lépés nem indul el. A kért epizódszámot az `episode` változóban állítsd be.
Pythonból másik mappával is indítható:

```python
from main import run_pipeline

run_pipeline(episode=25, directory="/home/fedora/Videók")
```

A sikeres lépések és a leállások a terminálra és a célmappa `pipeline.log`
fájljába kerülnek, budapesti időponttal (UTC-eltolással), a lépés nevével és az
okkal. A napló minden indításkor bővül. A kilépési kód siker esetén 0, hibánál 1,
Ctrl+C megszakításnál 130. A napló nem tartalmaz API-kulcsot.

Meglévő videót és feliratot nem tölt újra. A videót FFmpeggel ellenőrzi, a
feliratot helyben SRT-ként beolvassa; üres vagy hibás fájllal nem folytatja.
A felirat először `.srt.part` néven mentődik, és csak sikeres írás után kapja meg
a végleges nevét. A magyar kimenet meglétekor ellenőrzi a formátumot és kihagyja
a fordítást; félbeszakadt fordítást a kész adagokból folytat.

A `directory` egy már létező célmappa; a `"."` az aktuális munkamappát jelenti.
Nem létező útvonal vagy fájl megadása esetén a program még a hálózati
lekérések előtt hibával leáll; nem hoz létre mappát.
A külön használt letöltőben a `target_episode` alapból minimumot jelent;
a főprogram pontos epizódegyezést kér. A `page_url` az epizódoldal címe.
A fájlnév az oldal tényleges epizódszámát követi, például
`Daha17_25_1080p.mp4`. Meglévő MP4-et nem ír felül.

A program ellenőrzi az epizód számát, lekéri az oldal Dailymotion-videóazonosítóját,
majd ablak nélkül betölti a Dailymotion-lejátszót. A kapott HLS mesterlistából
kifejezetten a `/h264_aac_fhd/.../manifest.m3u8` címet választja ki és ellenőrzi.
Nem kell kézzel kattintani vagy Entert nyomni. A lejátszó betöltése után legfeljebb
60 másodpercig vár az FHD címre; hiányában hibával kilép.

A cím aláírást tartalmaz, ezért később lejárhat. Friss címért futtasd újra a programot.

A feliratletöltés közvetlenül a
`https://cdn.duhnet.tv/C13/2013kanald/dizi/daha17/doy<epizódszám>.srt`
címet kéri le. Egyetlen GET kérés ellenőrzi a HTTP-státuszt és tölti le a fájlt.
A feliratot az MP4 mellé menti, például `Daha17_24_1080p.tr.srt` néven.
Meglévő feliratot nem ír felül. Ellenőrzi az SRT-formátumot is. Önálló hívásnál
hibára `None`-t ad; a főprogramnak `raise_errors=True` mellett továbbadja a konkrét hibát.
A főprogram mindhárom lépéshez ugyanazt az epizódszámot használja. Ha az oldal
másik részt kínál, nem párosítja azt a kért epizód feliratával, hanem leáll.
A letöltő külön használt `run()` függvényében a régi minimum-epizódszám viselkedés
megmaradt; a főprogram `exact_episode=True` értékkel kéri a pontos egyezést.

## Magyar felirat fordítása

A `subtitleTranslation.py` memóriába tölti a török SRT-t, és 100 forrásblokkos
adagokat dolgoz fel. A `main.py` a három lépés sorrendjét és a közös leállási naplót kezeli.

A jelenlegi `main.py` teszteléshez `max_batches=6` értéket ad át: csak az első
600 forrásblokkot dolgozza fel, és `Daha17_25_1080p.hu.test600.srt` néven menti.
A jelentés csak erre a részletre vonatkozik. A meglévő, azonos modellhez tartozó
adagokat felhasználja. A teljes fordításhoz töröld a `max_batches=6` sort, vagy
állítsd `None`-ra; ekkor a már kész adagokból folytatja a teljes feliratot.

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

Nincs külön API-s kihagyásellenőrzés vagy olvashatósági javítás. Az API-t csak
fordításra hívja; a számozást, időzítést és SRT-szerkezetet Python ellenőrzi.
A modell által kihagyott blokkokat és az olvashatósági figyelmeztetéseket helyben
listázza, nem pótolja vagy javítja automatikusan újabb modellkéréssel.

A kész `.hu.srt` mellé `.hu.review.json` jelentés kerül a kihagyott török szövegekkel
és minden magyar blokk olvashatósági mérésével. Az `omission_audits` mezőbe új
AI-döntések nem kerülnek; régi kész adagokból betöltött döntések megmaradhatnak.
A `semantic_completeness_verified` értéke hamis: nincs tartalmi garancia.
Azonos időzítésű több forrásblokk esetén a program megáll, mert az SRT-válaszból
nem lehetne biztosan párosítani őket.

### Folytatás mentett adagokból

A `.hu.checkpoints/` könyvtárban atomi JSON-fájlokba menti minden sikeres adag
kezdeti fordítását és helyben ellenőrzött kész változatát. A sikeres API-válaszokat
is megőrzi, így egy későbbi helyi hiba után a korábbi sikeres hívásokat nem ismétli.
A korábbi, API-val már ellenőrzött kész adagokat is újrahasználja. A fordítási
promptot és a mentések azonosítását ezért változatlanul hagytuk.
Az állapot a teljes forráshoz, modellhez, prompthoz, memóriához és az adagolási
beállításokhoz kötött. Ha ezek változnak, új munkamenet indul; a régi mentés
megmarad. A mentések tartalomlenyomatát beolvasáskor ellenőrzi.

Félbeszakadt fordításhoz közvetlenül a fordítást hívd újra azonos paraméterekkel,
így a már létező videót nem kell újra letölteni:

```python
from subtitleTranslation import translate_episode_subtitle

translate_episode_subtitle(
    episode=25, directory=".", model="gpt-6-sol",
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

A meglévő `requests` csomagot használja. Egy új adaghoz egy fordítási API-hívás
tartozik. A helyi ellenőrzés és jelentés nem eredményez külön díjköteles hívást.
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

- `main.py`: a három lépés vezérlése, leállás és időbélyeges naplózás.
- `downloader.py`: ellenőrzések, Dailymotion FHD cím kinyerése, videóletöltés és hibakezelés.
- `downloadSubtitle.py`: a török SRT felirat közvetlen CDN-letöltése.
- `subtitleTranslation.py`: memóriába olvasás, 100 blokkonkénti API-fordítás és magyar SRT mentése.
- `series_memory.json`, `seriesMemory.py`: jóváhagyott sorozatháttér és ellenőrzött betöltése.
- `subtitleApi.py`: fordítási API-hívás, cache-beállítás és helyi válaszmentés.
- `translationStorage.py`: atomi mentés, lenyomatok és mérési napló.
- `test_translationPipeline.py`: fordítás, helyreállítás és költségmentes API-szimuláció tesztjei.
- `subtitleQuality.py`: időtartam, olvasási sebesség, sorhossz és kihagyások ellenőrzése.
- `test_subtitleQuality.py`: olvashatósági mérés és kihagyásjelentés tesztjei.
- `test_subtitleTranslation.py`: adagolás, fordítási válaszok és API-hibák tesztjei, fizetős hívás nélkül.
- `test_downloader.py`, `test_downloadSubtitle.py`: videó- és feliratletöltési tesztek.
- `test_main.py`: sorrend, leállás, naplózás és újraindítás hálózat nélkül.
