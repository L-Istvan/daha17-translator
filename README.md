# Telepítés

Python 3.10 vagy újabb, Git, valamint FFmpeg/ffprobe szükséges.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
```

A `requirements.txt` a letöltő és fordító Python-függőségei mellett a külön
[**videa-uploader**](https://github.com/L-Istvan/videa-uploader) csomagot is
telepíti GitHubról. A feltöltő egy ellenőrzött teljes commitazonosítóhoz van kötve;
nem a szomszédos munkamappát és nem egy helyi feltöltőkód-másolatot használja.
A `yt-dlp` is ebből a fájlból települ.

## Futtatás

```bash
python3 main.py
```

Teljes videó- és hangellenőrzéssel:

```bash
python3 main.py -safe
```

A `--safe` ugyanígy használható. Kapcsoló nélkül csak a videófájl meglétét és
nem üres méretét ellenőrzi; a sérült képkockák és hangsávok észrevétlenek maradhatnak.
Pythonból a `run_pipeline(..., safe=True)` kapcsolja be a teljes ellenőrzést.
Mindkét indítás a teljes folyamatot futtatja; a kapcsoló csak az alapos
videóellenőrzést szabályozza. Az FFmpeg kapcsoló nélkül is szükséges a letöltött
videó MP4-be csomagolásához.

A `main.py` sorrendben futtatja a videóletöltést, a török felirat letöltését,
majd a magyar fordítást és az opcionális Videa-feltöltést. Bármelyik lépés hibájánál azonnal leáll; a következő
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

Meglévő videót és feliratot nem tölt újra. A videót `-safe` módban FFmpeggel ellenőrzi, a
feliratot helyben SRT-ként beolvassa; üres vagy hibás fájllal nem folytatja.
A felirat először `.srt.part` néven mentődik, és csak sikeres írás után kapja meg
a végleges nevét. A magyar kimenet meglétekor ellenőrzi a formátumot és kihagyja
a fordítást; félbeszakadt fordítást a kész adagokból folytat.

A `directory` egy már létező célmappa; a `"."` az aktuális munkamappát jelenti.
Nem létező útvonal vagy fájl megadása esetén a program még a hálózati
lekérések előtt hibával leáll; nem hoz létre mappát.
A külön használt letöltőben a `target_episode` alapból minimumot jelent;
a főprogram pontos epizódegyezést kér. Az `episode` alapján az epizódlistából
választja ki a tényleges oldalt: a 25. részhez a 25. rész archivált oldalát,
a legújabbhoz annak aktuális linkjét. Így egy új rész megjelenése nem akadályozza
a korábbi rész új letöltését. A `page_url` külön hívásnál explicit felülbírálás.
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
adagokat felhasználja. A teljes fordításhoz a `main.py` elején állítsd
`max_batches = None` értékre; ekkor a már kész adagokból folytatja a teljes feliratot.

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

A letöltés után a program elutasítja a hiányzó vagy üres fájlt. A főprogram
`-safe` kapcsolóval FFmpeggel végigolvassa és dekódolja a videót és a hangsávokat,
a már meglévő MP4-et is. Ilyenkor csak sikeres ellenőrzés után folytatja a folyamatot.
A közvetlen `downloader.run()` és `download_episode()` hívások alapból teljes
ellenőrzést végeznek; ezeknél a `safe=False` kapcsolja ki. Ez nagy fájlnál időbe telhet; a hibás MP4 megmarad, ezért újrapróbálás
előtt el kell távolítani vagy át kell nevezni.

## 4. fázis: Videa-feltöltés

A főprogram a külön [videa-uploader](https://github.com/L-Istvan/videa-uploader)
csomag nyilvános Python-függvényeit hívja:

```python
from videa_uploader import upload_video, attach_subtitle
```

A feltöltés és a feliratcsatolás megvalósítása, valamint ezek saját tesztjei
kizárólag a külön repóban vannak. Ebben a projektben a lépések sorrendje,
a beállítások átadása és az eredmények naplózása maradt.

A negyedik fázis előbb feltölti az eredeti MP4-et, majd külön „Magyar”
feliratként csatolja a harmadik fázis kész SRT-jét. A felirat nincs ráégetve.
A `main.py` elején kapcsolható be a teljes folyamat:

```python
max_batches = None
upload_to_videa = True
```

Az új feltöltés címe, leírása és címkéi mindig a beállított epizódszámból készülnek.
Például a 25. résznél:

- Cím: `Daha 17 25 rész magyar felirattal`
- Leírás: `Daha 17 25 rész magyar felirattal. Török sorozat magyar feliratos epizódja.`
  Üres sor után: `Magyar felirat: AI segítségével fordítva.`
- Címkék: `Daha 17 25 rész magyar felirattal`, `Daha 17 25 rész`, `Daha 17 25`.

A már kész feltöltés adatlapját az újraindítás nem írja át. A feltöltő normál Videát használ,
`film/animáció` kategóriával; a további részleteket a csomag README-je írja le.
A program nem ad át `force=True` értéket: a duplikálást megelőző ellenőrzések
bekapcsolva maradnak.
A főprogram `headless=True` értékkel indítja a feltöltőt, ezért nem jelenik meg
böngészőablak. A `videa-uploader login` kézi bejelentkezése továbbra is látható.

### Állandó fájlnév másik projekt számára

Sikeres feltöltés és feliratcsatolás után a célmappában mindig ugyanaz a
`latest_upload.json` fájl frissül, például:

```json
{"episode": 25, "url": "https://videa.hu/player?v=abcdefghijkl1234"}
```

A másik projektnek csak ezt az állandó útvonalat kell ismernie, és az `url`
mezőt kiolvasnia. Az első sikeres futás előtt a fájl még nem létezik.
Sikertelen futáskor az előző eredmény megmarad; az `episode` mutatja, melyik
részhez tartozik. Újraindításkor a már kész feltöltés linkje is kikerül ide.
A fájl cseréje atomi, így az olvasó nem kap félkész JSON-t.
A Videa videófeldolgozása a link mentésekor még tarthat.
Ez a helyi eredményfájl nem kerül Gitbe. Kiolvasás a másik projektben:

```python
import json
from pathlib import Path

latest = Path("/a/letoltesi/celmappa/latest_upload.json")
if latest.is_file():
    result = json.loads(latest.read_text(encoding="utf-8"))
    episode = result["episode"]
    url = result["url"]
```

### Bejelentkezés és meglévő munkamenet

Új telepítésnél:

```bash
videa-uploader login
```

Ez csak kézi bejelentkezést és munkamenetmentést végez. A csomag alapértelmezett
helye `~/.config/videa-uploader/session.json` (`XDG_CONFIG_HOME` figyelembevételével).

Az átállás a korábbi projektbeli `.videa-session.json` fájlt is felismeri.
Ha mindkét helyen van mentés, a legutóbb mentettet használja, egyező időpontnál
a csomag alapértelmezettjét. Így a `videa-uploader login` friss belépését nem
árnyékolja be a korábbi helyi fájl. A kiválasztott útvonal a negyedik fázis
indulásakor megjelenik a terminálon és a `pipeline.log` fájlban.
Kifejezetten a régi helyi mentés frissítéséhez:

```bash
videa-uploader --session "$PWD/.videa-session.json" login
```

A `.env` fájlban a `VIDEA_SESSION_PATH` felülbírálhatja a munkamenet helyét.
A kiválasztás sorrendje: explicit `VIDEA_SESSION_PATH`, a két ismert hely közül
a legfrissebb meglévő mentés, végül a csomag alapértelmezett helye. A videóhoz és a
felirathoz ugyanazt a munkamenetet adja át. A bejelentkezési fájlokat nem másolja.

A főprogram betölti a projekt `.env` fájlját, és az opcionális `VIDEA_EMAIL`,
`VIDEA_PASSWORD` értékeket kifejezetten átadja a feltöltőnek. A könyvtár önmagában
nem tölti be ennek a projektnek a beállításait. Valódi adatot ne írj a forráskódba.

### Mentések és önálló parancsok

A videó melletti meglévő `.videa.json` mentések használhatók maradnak. Kész
videót és azonos, már csatolt feliratot nem küld újra. Bizonytalan korábbi
kísérletnél leáll, és ellenőrzést kér; nem készít automatikusan másolatot.
A negyedik fázis eredménye és hibája továbbra is a `pipeline.log` fájlba kerül.

A csomag önálló parancsai is használhatók. Az első **valódi feltöltést végez**,
a második csak egy már feltöltött videóhoz csatolja az SRT-t:

```bash
videa-uploader upload sajat_tesztvideo.mp4 --title "Teszt" --subtitle magyar.srt
videa-uploader subtitle Daha17_25_1080p.mp4 Daha17_25_1080p.hu.srt --name "Magyar"
```

Ha a régi helyi munkamenetet használod, a parancs elé a fenti `--session` opciót
is add meg. A csomag frissítéséhez a `requirements.txt` Videa-hivatkozásában
rögzített commitot kell tudatosan frissíteni és az új függőséget telepíteni;
a Videa-repóba történő push önmagában nem módosítja a telepített verziót.

## Tesztek

```bash
.venv/bin/python -m unittest -v
```

A tesztek nem töltenek le videót az internetről. Az FFmpeg ellenőrzéséhez
egy rövid helyi tesztvideót állítanak elő; ez a teszt FFmpeg nélkül kimarad.

## Fájlok

- `main.py`: a három alaplépés és az opcionális Videa-feltöltés vezérlése, naplózás.
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
- `requirements.txt`: Python-függőségek és a külön Videa-csomag rögzített GitHub-verziója.
