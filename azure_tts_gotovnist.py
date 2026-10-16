# -*- coding: utf-8 -*-
"""
НейроЗнайко · Готовність до школи — озвучка фраз тесту через Azure Speech.

Працює разом з azure_tts.py (той самий ключ, голоси, темп і pronunciation.json) і нічого в ньому не змінює.
Покладіть поруч в одну папку: azure_tts.py, pronunciation.json, цей файл і voice_manifest_gotovnist.json.
Файли з'являться в audio/gotovnist/uk/ та audio/gotovnist/ru/ — застосунок gotovnist.html шукає їх саме там.

Запуск:
    python azure_tts_gotovnist.py check uk            — ПЕРЕВІРКА НАГОЛОСІВ: усі окремі слова з номерами в кількох MP3
                                                        (audio/_check/uk_1.mp3 …) і список audio/_check/uk.txt
    python azure_tts_gotovnist.py --words --lang uk   — озвучити лише окремі слова (назви картинок)
    python azure_tts_gotovnist.py                     — озвучити все, чого ще немає (обидві мови)
    python azure_tts_gotovnist.py --lang ru           — лише одна мова
    python azure_tts_gotovnist.py --force             — перезаписати всі файли (після зміни голосу чи темпу)
    python azure_tts_gotovnist.py refresh "сова"      — переозвучити лише фрази з цим словом (після правки pronunciation.json)
    python azure_tts_gotovnist.py list uk             — показати всі фрази мови з ключами (нічого не озвучує)
Перевірити вимову окремого слова, як і раніше: python azure_tts.py say uk "текст"
"""
import json, os, sys, time
import azure_tts as A

HERE = os.path.dirname(os.path.abspath(__file__))

def check(man, lang, per_file=40):
    """Усі окремі слова мови — пронумеровані, по 40 у файлі, з паузами. Слухаєте й записуєте номери з неправильним наголосом."""
    words = [t for t in man[lang].values() if " " not in t.strip()]
    out = os.path.join(HERE, "audio", "_check"); os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, lang + ".txt"), "w", encoding="utf-8") as f:
        for i, w in enumerate(words, 1):
            f.write("%d. %s\n" % (i, w))
    A.PRON = A.load_pron()
    key, region = A.ask_credentials()
    voice = A.VOICES[lang]
    esc = lambda x: x.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    rate = A.RATE[lang] if isinstance(A.RATE, dict) else A.RATE
    for n0 in range(0, len(words), per_file):
        chunk = words[n0:n0 + per_file]
        parts = ["%d. <break time='250ms'/>%s<break time='900ms'/>" % (n0 + i + 1, A.apply_pron(lang, esc(A.clean(w)), voice)) for i, w in enumerate(chunk)]
        inner = '<prosody rate="%s" pitch="%s">%s</prosody>' % (rate, A.PITCH, " ".join(parts))
        if "Multilingual" in voice:
            inner = '<lang xml:lang="%s">%s</lang>' % (A.LOCALES[lang], inner)
        body = '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="%s"><voice name="%s">%s</voice></speak>' % (A.LOCALES[lang], voice, inner)
        path = os.path.join(out, "%s_%d.mp3" % (lang, n0 // per_file + 1))
        A.save(path, A.synth(key, region, lang, "", voice, raw_body=body))
        print("✓ %s  (слова %d–%d)" % (path, n0 + 1, n0 + len(chunk)))
        time.sleep(A.PAUSE_SEC)
    print("\nСписок із номерами: " + os.path.join(out, lang + ".txt"))
    print("Послухайте файли й надішліть номери слів, де наголос або вимова неправильні.")

def main():
    args = sys.argv[1:]
    mp = os.path.join(HERE, "voice_manifest_gotovnist.json")
    if not os.path.exists(mp):
        raise SystemExit("Не знайдено voice_manifest_gotovnist.json поруч зі скриптом.")
    man = json.load(open(mp, encoding="utf-8"))["gotovnist"]
    if args and args[0] == "list":
        lang = args[1] if len(args) > 1 else "uk"
        for k, t in man[lang].items():
            print(k, " ", t)
        print("\nУсього фраз: %d" % len(man[lang]))
        return
    if args and args[0] == "check":
        return check(man, args[1] if len(args) > 1 else "uk")
    refresh = bool(args) and args[0] == "refresh"
    frag = " ".join(a for a in args[1:] if not a.startswith("--")) if refresh else ""
    if refresh and not frag:
        raise SystemExit('Використання: python azure_tts_gotovnist.py refresh "слово або фраза"')
    force = "--force" in args or refresh
    words_only = "--words" in args
    only = [a for i, a in enumerate(args) if i > 0 and args[i - 1] == "--lang"]
    jobs = []
    for lang, items in man.items():
        if lang not in A.VOICES or (only and lang not in only):
            continue
        folder = os.path.join(HERE, "audio", "gotovnist", lang)
        os.makedirs(folder, exist_ok=True)
        for key, text in items.items():
            if words_only and " " in text.strip():
                continue
            if frag and frag.lower() not in A.clean(text).lower():
                continue
            path = os.path.join(folder, key + ".mp3")
            if force or not os.path.exists(path) or os.path.getsize(path) == 0:
                jobs.append((lang, key, text, path))
    chars = sum(len(A.clean(j[2])) for j in jobs)
    print("Потрібно озвучити файлів: %d (≈ %d символів)." % (len(jobs), chars))
    if not jobs:
        print("Усе вже озвучено ✓")
        return
    A.PRON = A.load_pron()
    key, region = A.ask_credentials()
    print("Орієнтовний час: ~%.0f хв. Можна перервати (Ctrl+C) і запустити знову — готове збережеться.\n" % (len(jobs) * (A.PAUSE_SEC + 0.8) / 60))
    fails = 0
    for i, (lang, name, text, path) in enumerate(jobs, 1):
        try:
            data = A.synth(key, region, lang, text)
            if len(data) < 500:
                raise RuntimeError("порожня відповідь")
            A.save(path, data)
            print("[%d/%d] ✓ gotovnist/%s/%s.mp3  «%s»" % (i, len(jobs), lang, name, A.clean(text)[:50]))
        except (RuntimeError, OSError) as e:
            print("[%d/%d] ✗ gotovnist/%s/%s: %s" % (i, len(jobs), lang, name, e))
            fails += 1
        time.sleep(A.PAUSE_SEC)
    print("\nГотово." + (" Не вдалося: %d — просто запустіть скрипт ще раз." % fails if fails else " Усі файли створено ✓"))
    print("Далі: завантажте папку audio/gotovnist на GitHub поруч із gotovnist.html.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nЗупинено. Запустіть скрипт знову — він продовжить з місця зупинки.")
