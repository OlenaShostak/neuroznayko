# -*- coding: utf-8 -*-
"""
НейроЗнайко / НейроЗнайка / NeuroWhizKid / Neuroznajko — озвучка через Azure Speech.

Що робить: читає voice_manifest.json (усі фрази застосунку й банку ігор чотирма мовами)
і створює MP3-файли:
    audio/app/<мова>/<ключ>.mp3    — для index.html
    audio/bank/<мова>/<ключ>.mp3   — для bank.html
Вже створені файли пропускаються, тож скрипт можна запускати повторно (докачає лише нове).

Запуск (у папці, де лежать цей файл і voice_manifest.json):
    python azure_tts.py test      — пробна озвучка 4 фраз у папку audio/_test (послухати голоси)
    python azure_tts.py           — озвучити все
    python azure_tts.py --force   — перезаписати всі файли (наприклад, після зміни голосу)

Потрібен лише Python 3.8+; додаткові бібліотеки не потрібні.
"""
import json, os, re, sys, time, html, urllib.request, urllib.error

# ======================= НАЛАШТУВАННЯ =======================
# Ключ і регіон можна вписати сюди (у лапках) або ввести під час запуску.
AZURE_KEY = ""          # напр. "3f2a...c9"  (KEY 1 з розділу «Keys and Endpoint»)
AZURE_REGION = ""       # напр. "westeurope" (поле Location/Region)

# Голоси (можна замінити на альтернативні з коментаря)
VOICES = {
    "uk": "uk-UA-PolinaNeural",     # альтернатива: uk-UA-OstapNeural (чоловічий)
    "ru": "ru-RU-SvetlanaNeural",   # альтернатива: ru-RU-DariyaNeural
    "en": "en-US-AvaNeural",        # альтернатива: en-US-JennyNeural
    "pl": "pl-PL-ZofiaNeural",      # альтернатива: pl-PL-AgnieszkaNeural, pl-PL-MarekNeural
}
LOCALES = {"uk": "uk-UA", "ru": "ru-RU", "en": "en-US", "pl": "pl-PL"}
RATE = "-5%"      # темп: трохи повільніше для дошкільнят ("0%" — звичайний)
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

def clean(text):
    t = re.sub(r"<[^>]+>", " ", text)          # прибрати HTML-теги
    t = html.unescape(t)
    t = EMOJI.sub("", t)                       # прибрати емодзі
    t = re.sub(r"\s+", " ", t).strip()
    return t

def ssml(lang, text):
    t = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    return (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{LOCALES[lang]}">'
            f'<voice name="{VOICES[lang]}"><prosody rate="{RATE}" pitch="{PITCH}">{t}</prosody></voice></speak>')

def endpoint(region):
    return os.environ.get("AZURE_TTS_ENDPOINT") or f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"

def synth(key, region, lang, text):
    body = ssml(lang, clean(text)).encode("utf-8")
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
    key = AZURE_KEY or os.environ.get("AZURE_SPEECH_KEY", "")
    region = AZURE_REGION or os.environ.get("AZURE_SPEECH_REGION", "")
    if not key:
        key = input("Вставте KEY 1 з Azure (Keys and Endpoint) і натисніть Enter: ").strip()
    if not region:
        region = input("Введіть регіон (Location/Region), напр. westeurope: ").strip()
    region = region.lower().replace(" ", "")
    if not key or not region:
        raise SystemExit("Потрібні ключ і регіон.")
    return key, region

def main():
    args = sys.argv[1:]
    manifest_path = os.path.join(HERE, "voice_manifest.json")
    if not os.path.exists(manifest_path):
        raise SystemExit("Не знайдено voice_manifest.json поруч зі скриптом.")
    man = json.load(open(manifest_path, encoding="utf-8"))
    key, region = ask_credentials()

    if args and args[0] == "test":
        out = os.path.join(HERE, "audio", "_test"); os.makedirs(out, exist_ok=True)
        for lang in VOICES:
            text = man["bank"][lang].get("hello") or next(iter(man["app"][lang].values()))
            data = synth(key, region, lang, text)
            p = os.path.join(out, f"test_{lang}.mp3"); save(p, data)
            print(f"✓ {lang}: {p}")
        print("\nПослухайте файли в audio/_test. Якщо голоси подобаються — запустіть: python azure_tts.py")
        return

    force = "--force" in args
    jobs = []
    for section in ("app", "bank"):
        for lang, items in man[section].items():
            if lang not in VOICES:
                continue
            folder = os.path.join(HERE, "audio", section, lang)
            os.makedirs(folder, exist_ok=True)
            for name, text in items.items():
                path = os.path.join(folder, name + ".mp3")
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
