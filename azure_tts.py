# -*- coding: utf-8 -*-
"""
НейроЗнайко / НейроЗнайка / NeuroWhizKid / Neuroznajko — озвучка через Azure Speech.

Що робить: читає voice_manifest.json (усі фрази застосунку й банку ігор чотирма мовами)
і створює MP3-файли:
    audio/app/<мова>/<ключ>.mp3    — для index.html
    audio/bank/<мова>/<ключ>.mp3   — для bank.html
Вже створені файли пропускаються, тож скрипт можна запускати повторно (докачає лише нове).

Запуск (у папці, де лежать цей файл і voice_manifest.json):
    python azure_tts.py test               — пробна озвучка 4 фраз у папку audio/_test (послухати голоси)
    python azure_tts.py                    — озвучити все, чого ще немає
    python azure_tts.py --force            — перезаписати всі файли (наприклад, після зміни голосу чи темпу)
    python azure_tts.py --force --lang uk  — перезаписати лише одну мову (uk / ru / en / pl)
    python azure_tts.py say uk "Дивись уважно, куди стрибає зайчик"
                                           — озвучити будь-який текст у audio/_test/say_uk.mp3 (перевірка наголосів і темпу)
    python azure_tts.py refresh "зайчик"   — переозвучити лише ті фрази, де є це слово (після виправлення вимови)

ВИПРАВЛЕННЯ ВИМОВИ (наголоси): файл pronunciation.json поруч зі скриптом, наприклад
    { "uk": { "розумниця": "<phoneme alphabet='ipa' ph='rozˈumnɪt͡sʲa'>розумниця</phoneme>" } }
Значення може бути звичайним словом (перебудованим так, щоб голос читав правильно) або SSML-тегом
<phoneme> із транскрипцією IPA (наголос — знак ˈ перед наголошеним складом).
Перевірити варіант: python azure_tts.py say uk "Розумниця, натисни", потім refresh "розумниця".
Інший голос для проби: python azure_tts.py say uk "текст" --voice uk-UA-OstapNeural

Потрібен лише Python 3.8+; додаткові бібліотеки не потрібні.
"""
import json, os, re, sys, time, html, urllib.request, urllib.error

# ======================= НАЛАШТУВАННЯ =======================
# Ключ і регіон можна вписати сюди (у лапках) або ввести під час запуску.
AZURE_KEY = ""          # напр. "3f2a...c9"  (KEY 1 з розділу «Keys and Endpoint»)
AZURE_REGION = ""       # напр. "westeurope" (поле Location/Region)

# Голоси (можна замінити на альтернативні з коментаря)
VOICES = {
    "uk": "de-DE-SeraphinaMultilingualNeural",   # Серафина (багатомовна) говорить українською без акценту; наголоси — pronunciation.json
                                                 # альтернативи: uk-UA-OstapNeural (чоловічий), uk-UA-PolinaNeural
    "ru": "ru-RU-SvetlanaNeural",   # альтернатива: ru-RU-DariyaNeural
    "en": "en-US-AvaNeural",        # альтернатива: en-US-JennyNeural
    "pl": "pl-PL-ZofiaNeural",      # альтернатива: pl-PL-AgnieszkaNeural, pl-PL-MarekNeural
}
LOCALES = {"uk": "uk-UA", "ru": "ru-RU", "en": "en-US", "pl": "pl-PL"}
RATE = {"uk": "0%", "ru": "0%", "en": "-5%", "pl": "-3%"}   # темп для кожної мови окремо ("0%" — звичайний, "+10%" — швидше)
PITCH = "+0%"     # висота голосу
PAUSE_SEC = 3.2   # пауза між запитами (безкоштовний тариф має обмеження кількості запитів за хвилину)
# ============================================================

HERE = os.path.dirname(os.path.abspath(__file__))
FORMAT = "audio-24khz-48kbitrate-mono-mp3"
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]")

def load_pron():
    p = os.path.join(HERE, "pronunciation.json")
    if not os.path.exists(p):
        return {}
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception as e:
        raise SystemExit("pronunciation.json містить помилку: %s" % e)

PRON = {}

def apply_pron(lang, text, voice=None):
    table = PRON.get(voice or VOICES.get(lang, "")) or PRON.get(lang) or {}   # спершу розділ для конкретного голосу, потім для мови
    for src, dst in table.items():
        text = re.sub(r"(?<!\w)" + re.escape(src) + r"(?!\w)", dst, text, flags=re.IGNORECASE)
    return text

def clean(text):
    t = re.sub(r"<[^>]+>", " ", text)          # прибрати HTML-теги
    t = html.unescape(t)
    t = EMOJI.sub("", t)                       # прибрати емодзі
    t = t.replace("'", "\u02bc").replace("\u2019", "\u02bc")   # український апостроф ʼ (U+02BC) — голос читає його правильніше
    t = re.sub(r"\s+", " ", t).strip()
    return t

def ssml(lang, text, voice=None):
    t = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    voice = voice or VOICES[lang]
    t = apply_pron(lang, t, voice)   # заміни з pronunciation.json; значення можуть містити SSML-теги (<phoneme …>)
    rate = RATE[lang] if isinstance(RATE, dict) else RATE
    return (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{LOCALES[lang]}">'
            f'<voice name="{voice}">' + (f'<lang xml:lang="{LOCALES[lang]}">' if "Multilingual" in voice else '') +
            f'<prosody rate="{rate}" pitch="{PITCH}">{t}</prosody>' + ('</lang>' if "Multilingual" in voice else '') + '</voice></speak>')

def endpoint(region):
    return os.environ.get("AZURE_TTS_ENDPOINT") or f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"

def synth(key, region, lang, text, voice=None, raw_body=None):
    body = (raw_body or ssml(lang, clean(text), voice)).encode("utf-8")
    req = urllib.request.Request(endpoint(region), data=body, method="POST", headers={
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": FORMAT,
        "User-Agent": "NeuroZnayko-TTS",
    })
    delay = 5
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise SystemExit("\n❌ Azure відхилив ключ (помилка %d). Перевірте KEY і REGION — вони мають бути з одного ресурсу Speech." % e.code)
            if e.code == 400:
                raise RuntimeError("Azure не прийняв текст (400): " + text[:60])
            if e.code in (429, 500, 502, 503, 504):
                print(f"   … сервер просить зачекати ({e.code}), повтор через {delay} с")
                time.sleep(delay); delay = min(delay * 2, 60); continue
            raise
        except urllib.error.URLError as e:
            print(f"   … немає зв'язку ({e.reason}), повтор через {delay} с")
            time.sleep(delay); delay = min(delay * 2, 60)
    raise RuntimeError("Не вдалося після кількох спроб: " + text[:60])

def save(path, data):
    """Запис файлу з повторними спробами: Windows інколи тимчасово блокує запис
    (антивірус, OneDrive/Synology-синхронізація робочого столу тощо)."""
    last = None
    for attempt in range(5):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
            return
        except OSError as e:
            last = e
            time.sleep(2 + attempt * 2)
    raise OSError(f"не вдалося записати файл ({last}). Спробуйте перенести папку з робочого столу, напр. у C:\\neuroznayko")

def ask_credentials():
    key = (AZURE_KEY or os.environ.get("AZURE_SPEECH_KEY", "")).strip()
    region = (AZURE_REGION or os.environ.get("AZURE_SPEECH_REGION", "")).strip()
    ok_key = lambda k: re.fullmatch(r"[A-Za-z0-9]{20,100}", k or "") is not None
    tries = 0
    while not ok_key(key):
        if key:
            print("⚠ Ключ виглядає неправильно (мабуть, вставився двічі або разом із текстом). Вставте лише KEY 1, один раз.")
        tries += 1
        if tries > 3:
            raise SystemExit("Не вдалося отримати коректний ключ. Скопіюйте KEY 1 з Azure ще раз.")
        key = input("Вставте KEY 1 з Azure (Keys and Endpoint) і натисніть Enter: ").strip()
    tries = 0
    while not re.fullmatch(r"[a-z0-9]{3,40}", region.lower().replace(" ", "")):
        if region:
            print("⚠ Регіон має бути одним словом латиницею, напр. swedencentral")
        tries += 1
        if tries > 3:
            raise SystemExit("Не вдалося отримати регіон.")
        region = input("Введіть регіон (Location/Region), напр. swedencentral: ").strip()
    return key, region.lower().replace(" ", "")

def main():
    args = sys.argv[1:]
    manifest_path = os.path.join(HERE, "voice_manifest.json")
    if not os.path.exists(manifest_path):
        raise SystemExit("Не знайдено voice_manifest.json поруч зі скриптом.")
    man = json.load(open(manifest_path, encoding="utf-8"))
    global PRON
    PRON = load_pron()
    key, region = ask_credentials()

    if args and args[0] == "variants":
        # python azure_tts.py variants uk <голос>  — озвучує всі варіанти слів із variants.json одним файлом, з номерами
        if len(args) < 3:
            raise SystemExit("Використання: python azure_tts.py variants uk de-DE-SeraphinaMultilingualNeural")
        lang, voice = args[1], args[2]
        separate = "--separate" in args   # кожен варіант — окремим файлом audio/_test/v01.mp3, v02.mp3… (як звучатиме в застосунку)
        vp = os.path.join(HERE, "variants.json")
        if not os.path.exists(vp):
            raise SystemExit("Не знайдено variants.json поруч зі скриптом.")
        V = json.load(open(vp, encoding="utf-8"))
        esc = lambda x: x.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        parts, n = [], 0
        print("\nНОМЕРИ ВАРІАНТІВ:")
        for word, entry in V.items():
            # запис може бути списком варіантів або {"context": "речення з {w}", "cands": [...]} — тоді слово звучить у реченні
            ctx, cands = ("{w}", entry) if isinstance(entry, list) else (entry.get("context", "{w}"), entry["cands"])
            for c in cands:
                n += 1
                shown = c if not c.startswith("<") else "(транскрипція IPA)"
                print(f"  {n:>2}. {word}  →  {ctx.replace('{w}', shown)}")
                piece = c if c.startswith("<") else esc(c)
                sent = apply_pron(lang, esc(clean(ctx.replace("{w}", "\uE000"))), voice).replace("\uE000", piece)
                parts.append(f"{n}. <break time='250ms'/>{sent}<break time='900ms'/>")
                if separate:
                    r_ = RATE[lang] if isinstance(RATE, dict) else RATE
                    one = f'<prosody rate="{r_}" pitch="{PITCH}">{sent}</prosody>'
                    if "Multilingual" in voice:
                        one = f'<lang xml:lang="{LOCALES[lang]}">' + one + "</lang>"
                    b1 = (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{LOCALES[lang]}">'
                          f'<voice name="{voice}">{one}</voice></speak>')
                    od = os.path.join(HERE, "audio", "_test"); os.makedirs(od, exist_ok=True)
                    save(os.path.join(od, f"v{n:02d}.mp3"), synth(key, region, lang, "", voice, raw_body=b1))
                    time.sleep(PAUSE_SEC)
        rate = RATE[lang] if isinstance(RATE, dict) else RATE
        inner = f'<prosody rate="{rate}" pitch="{PITCH}">' + " ".join(parts) + "</prosody>"
        if "Multilingual" in voice:
            inner = f'<lang xml:lang="{LOCALES[lang]}">' + inner + "</lang>"
        body = (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{LOCALES[lang]}">'
                f'<voice name="{voice}">{inner}</voice></speak>')
        if separate:
            print("\n✓ Окремі файли: audio\\_test\\v01.mp3 … v%02d.mp3 — кожен звучить так, як звучатиме в застосунку." % n)
            return
        out = os.path.join(HERE, "audio", "_test"); os.makedirs(out, exist_ok=True)
        p = os.path.join(out, "variants.mp3"); save(p, synth(key, region, lang, "", voice, raw_body=body))
        print("\n✓ " + p + "\nПослухайте й запишіть номери, що звучать правильно.")
        return

    if args and args[0] == "say":
        if len(args) < 3:
            raise SystemExit('Використання: python azure_tts.py say uk "текст"')
        rest = args[2:]
        voice = None
        if "--voice" in rest:
            i = rest.index("--voice"); voice = rest[i + 1]; rest = rest[:i] + rest[i + 2:]
        if "--plain" in rest:            # без замін із pronunciation.json
            rest.remove("--plain"); PRON = {}
        lang, text = args[1], " ".join(rest)
        out = os.path.join(HERE, "audio", "_test"); os.makedirs(out, exist_ok=True)
        p = os.path.join(out, f"say_{lang}.mp3"); save(p, synth(key, region, lang, text, voice))
        print("✓ " + p + "   (темп " + (RATE[lang] if isinstance(RATE, dict) else RATE) + ")")
        return

    if args and args[0] == "test":
        out = os.path.join(HERE, "audio", "_test"); os.makedirs(out, exist_ok=True)
        for lang in VOICES:
            text = man["bank"][lang].get("hello") or next(iter(man["app"][lang].values()))
            data = synth(key, region, lang, text)
            p = os.path.join(out, f"test_{lang}.mp3"); save(p, data)
            print(f"✓ {lang}: {p}")
        print("\nПослухайте файли в audio/_test. Якщо голоси подобаються — запустіть: python azure_tts.py")
        return

    force = "--force" in args or (args and args[0] == "refresh")
    only_langs = [a for i, a in enumerate(args) if i > 0 and args[i - 1] == "--lang"]
    frag = " ".join(a for a in args[1:] if not a.startswith("--")) if args and args[0] == "refresh" else ""
    if args and args[0] == "refresh" and not frag:
        raise SystemExit('Використання: python azure_tts.py refresh "слово або фраза"')
    jobs = []
    for section in ("app", "bank"):
        for lang, items in man[section].items():
            if lang not in VOICES or (only_langs and lang not in only_langs):
                continue
            folder = os.path.join(HERE, "audio", section, lang)
            os.makedirs(folder, exist_ok=True)
            for name, text in items.items():
                path = os.path.join(folder, name + ".mp3")
                if frag and frag.lower() not in clean(text).lower():
                    continue
                if force or not os.path.exists(path) or os.path.getsize(path) == 0:
                    jobs.append((section, lang, name, text, path))
    chars = sum(len(clean(j[3])) for j in jobs)
    print(f"Потрібно озвучити файлів: {len(jobs)} (≈ {chars} символів; безкоштовний ліміт — 500 000 символів на місяць).")
    if not jobs:
        print("Усе вже озвучено ✓"); return
    mins = len(jobs) * (PAUSE_SEC + 0.8) / 60
    print(f"Орієнтовний час: ~{mins:.0f} хв. Можна перервати (Ctrl+C) і запустити знову — готове збережеться.\n")
    fails = []
    for i, (section, lang, name, text, path) in enumerate(jobs, 1):
        try:
            data = synth(key, region, lang, text)
            if len(data) < 500:
                raise RuntimeError("порожня відповідь")
            save(path, data)
            print(f"[{i}/{len(jobs)}] ✓ {section}/{lang}/{name}.mp3  «{clean(text)[:50]}»")
        except (RuntimeError, OSError) as e:
            print(f"[{i}/{len(jobs)}] ✗ {section}/{lang}/{name}: {e}")
            fails.append(path)
        time.sleep(PAUSE_SEC)
    print("\nГотово." + (f" Не вдалося: {len(fails)} — просто запустіть скрипт ще раз." if fails else " Усі файли створено ✓"))
    print("Далі: завантажте папку audio на GitHub поруч з index.html і bank.html.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nЗупинено. Запустіть скрипт знову — він продовжить з місця зупинки.")
