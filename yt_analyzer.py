#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube анализатор:
- Извлича метаданни и субтитри чрез yt-dlp (без да сваля видеото).
- Запазва субтитрите с таймстампи и чист текст.
- Изпраща текста към DeepSeek за резюме и тематичен анализ.
- Запазва AI резултата в JSON за по-нататъшна обработка.
- Локален анализ: честота на думите.
"""

import os
import re
import sys
import json
import requests
from collections import Counter
from urllib.parse import urlparse, parse_qs

import yt_dlp
from stop_words import get_stop_words


# ============================================================
# 1. STOP WORDS (само от пакета stop-words)
# ============================================================
try:
    BULGARIAN_STOPWORDS = set(get_stop_words("bulgarian"))
    ENGLISH_STOPWORDS = set(get_stop_words("english"))
except Exception as e:
    print(f"❌ Грешка при зареждане на stop-words: {e}")
    print("   Инсталирай пакета: pip install stop-words")
    sys.exit(1)

ALL_STOPWORDS = BULGARIAN_STOPWORDS | ENGLISH_STOPWORDS


# ============================================================
# 2. UTILITIES
# ============================================================
def get_video_id(url: str) -> str | None:
    """Извлича video ID от YouTube URL."""
    parsed = urlparse(url)
    if parsed.hostname in ("youtu.be", "www.youtu.be"):
        return parsed.path[1:].split("?")[0]
    if parsed.hostname in ("youtube.com", "www.youtube.com"):
        if parsed.path == "/watch":
            return parse_qs(parsed.query).get("v", [None])[0]
        if parsed.path.startswith(("/embed/", "/v/")):
            return parsed.path.split("/")[2]
    return None


def format_duration(seconds) -> str:
    """Форматира продължителност в чч:мм:сс или мм:сс."""
    if not seconds:
        return "—"
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}ч {m:02d}м {s:02d}с" if h else f"{m}м {s:02d}с"


def format_date(yyyymmdd: str) -> str:
    """YYYYMMDD → DD.MM.YYYY."""
    if yyyymmdd and len(yyyymmdd) == 8:
        return f"{yyyymmdd[6:8]}.{yyyymmdd[4:6]}.{yyyymmdd[0:4]}"
    return yyyymmdd or "—"


def format_timestamp(seconds: float) -> str:
    """Секунди → [ЧЧ:ММ:СС] или [ММ:СС]."""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"[{h:02d}:{m:02d}:{s:02d}]" if h else f"[{m:02d}:{s:02d}]"


def section(title: str, icon: str = ""):
    """Извежда заглавие на секция с рамка."""
    prefix = f"{icon} " if icon else ""
    print(f"\n{'═' * 64}")
    print(f"  {prefix}{title.upper()}")
    print(f"{'═' * 64}")


def subsection(title: str):
    """Извежда подзаглавие."""
    print(f"\n  ── {title} ──")


# ============================================================
# 3. МЕТАДАННИ ЧРЕЗ yt-dlp
# ============================================================
def get_video_metadata(video_id: str) -> dict | None:
    """Извлича метаданни за видеото чрез yt-dlp (без сваляне)."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": False,
        "writeautomaticsub": False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return {
            "title":         info.get("title", ""),
            "description":   info.get("description", ""),
            "uploader":      info.get("uploader", ""),
            "upload_date":   info.get("upload_date", ""),
            "duration":      info.get("duration"),
            "view_count":    info.get("view_count"),
            "like_count":    info.get("like_count"),
            "comment_count": info.get("comment_count"),
            "categories":    info.get("categories", []) or [],
            "tags":          info.get("tags", []) or [],
            "is_live":       info.get("is_live", False),
            "webpage_url":   info.get("webpage_url", url),
        }
    except Exception as e:
        print(f"  ⚠️  Грешка при извличане на метаданни: {type(e).__name__}: {e}")
        return None


def print_metadata(meta: dict):
    """Извежда метаданните на видеото в четим вид."""
    if not meta:
        print("  (няма налични метаданни)")
        return

    section("Информация за видеото", "📺")

    print(f"\n  Заглавие        {meta['title']}")
    print(f"  Канал           {meta['uploader']}")
    print(f"  Дата            {format_date(meta['upload_date'])}")
    print(f"  Продължителност {format_duration(meta['duration'])}")

    if meta.get("is_live"):
        print(f"  На живо         да")
    if meta.get("view_count") is not None:
        print(f"  Гледания        {meta['view_count']:,}")
    if meta.get("like_count") is not None:
        print(f"  Харесвания      {meta['like_count']:,}")
    if meta.get("comment_count") is not None:
        print(f"  Коментари       {meta['comment_count']:,}")
    if meta.get("categories"):
        print(f"  Категория       {', '.join(meta['categories'])}")
    if meta.get("tags"):
        tags = meta["tags"]
        tags_str = ", ".join(tags[:10])
        if len(tags) > 10:
            tags_str += f" … (+{len(tags) - 10})"
        print(f"  Тагове          {tags_str}")
    print(f"  URL             {meta['webpage_url']}")

    if meta.get("description"):
        subsection("Описание")
        print()
        for line in meta["description"].splitlines():
            print(f"  {line}")

def save_metadata(video_id: str, meta: dict) -> str | None:
    """Запазва метаданните на видеото в текстов файл."""
    if not meta:
        return None

    filename = f"{video_id}_metadata.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"Заглавие:         {meta.get('title', '')}\n")
        f.write(f"Канал:            {meta.get('uploader', '')}\n")
        f.write(f"Дата на качване:  {format_date(meta.get('upload_date', ''))}\n")
        f.write(f"Продължителност:  {format_duration(meta.get('duration'))}\n")

        if meta.get("is_live"):
            f.write(f"На живо:          да\n")
        if meta.get("view_count") is not None:
            f.write(f"Гледания:         {meta['view_count']:,}\n")
        if meta.get("like_count") is not None:
            f.write(f"Харесвания:       {meta['like_count']:,}\n")
        if meta.get("comment_count") is not None:
            f.write(f"Коментари:        {meta['comment_count']:,}\n")
        if meta.get("categories"):
            f.write(f"Категория:        {', '.join(meta['categories'])}\n")
        if meta.get("tags"):
            f.write(f"Тагове:           {', '.join(meta['tags'])}\n")

        f.write(f"URL:              {meta.get('webpage_url', '')}\n")

        if meta.get("description"):
            f.write(f"\n--- Описание ---\n")
            f.write(meta["description"])
            f.write("\n")

    return filename

# ============================================================
# 4. СУБТИТРИ С ТАЙМСТАМПИ
# ============================================================
def get_subtitles_with_timestamps(video_id: str,
                                  preferred_langs=("bg", "en")) -> list[dict] | None:
    """
    Извлича субтитрите чрез yt-dlp, включително таймстампите.
    Връща: [{"start": float, "duration": float, "text": str}, ...]
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        print(f"  ⚠️  Грешка при извличане на info: {type(e).__name__}: {e}")
        return None

    subtitles = info.get("subtitles") or {}
    auto_subs = info.get("automatic_captions") or {}

    # Приоритет: ръчни → автоматични → каквото има
    chosen_track, chosen_lang, chosen_is_auto = None, None, False

    for source, is_auto in ((subtitles, False), (auto_subs, True)):
        for lang in preferred_langs:
            if lang in source:
                for fmt in source[lang]:
                    if fmt.get("ext") in ("json3", "vtt", "srv1", "srv2", "srv3", "ttml"):
                        chosen_track, chosen_lang, chosen_is_auto = fmt, lang, is_auto
                        break
            if chosen_track:
                break
        if chosen_track:
            break

    # Fallback: първият наличен
    if not chosen_track:
        for source, is_auto in ((subtitles, False), (auto_subs, True)):
            for lang, tracks in source.items():
                for fmt in tracks:
                    if fmt.get("ext") in ("json3", "vtt", "srv1", "srv2", "srv3", "ttml"):
                        chosen_track, chosen_lang, chosen_is_auto = fmt, lang, is_auto
                        break
                if chosen_track:
                    break
            if chosen_track:
                break

    if not chosen_track:
        print("  ❌ Не са намерени субтитри за това видео.")
        return None

    print(f"  ✅ Субтитри: език = {chosen_lang}, "
          f"автоматични = {'да' if chosen_is_auto else 'не'}, "
          f"формат = {chosen_track.get('ext')}")

    sub_url = chosen_track.get("url")
    if not sub_url:
        print("  ❌ Липсва URL за субтитрите.")
        return None

    try:
        import urllib.request
        with urllib.request.urlopen(sub_url, timeout=30) as resp:
            content = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  ❌ Грешка при изтегляне на субтитрите: {e}")
        return None

    ext = chosen_track.get("ext")
    if ext == "json3":
        return _parse_json3(content)
    return _parse_vtt(content)


def _parse_json3(content: str) -> list[dict]:
    """Парсва YouTube json3 формат."""
    data = json.loads(content)
    result = []
    for event in data.get("events", []):
        segs = event.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs).strip()
        if not text:
            continue
        result.append({
            "start":    event.get("tStartMs", 0) / 1000.0,
            "duration": event.get("dDurationMs", 0) / 1000.0,
            "text":     text,
        })
    return result


def _parse_vtt(content: str) -> list[dict]:
    """Парсва WebVTT формат."""
    def to_sec(t: str) -> float:
        parts = t.replace(",", ".").split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return 0.0

    result = []
    lines = content.splitlines()
    time_re = re.compile(
        r"(\d{1,2}:\d{2}:\d{2}[.,]\d{3}|\d{1,2}:\d{2}[.,]\d{3})\s*-->\s*"
        r"(\d{1,2}:\d{2}:\d{2}[.,]\d{3}|\d{1,2}:\d{2}[.,]\d{3})"
    )

    i = 0
    while i < len(lines):
        m = time_re.match(lines[i].strip())
        if m:
            start, end = to_sec(m.group(1)), to_sec(m.group(2))
            i += 1
            buf = []
            while i < len(lines) and lines[i].strip():
                buf.append(lines[i].strip())
                i += 1
            text = re.sub(r"<[^>]+>", "", " ".join(buf)).strip()
            if text:
                result.append({"start": start,
                               "duration": max(0.0, end - start),
                               "text": text})
        else:
            i += 1
    return result


def save_subtitles(video_id: str, segments: list[dict]) -> str:
    """Запазва субтитрите с таймстампи в текстов файл."""
    filename = f"{video_id}_subtitles.txt"
    with open(filename, "w", encoding="utf-8") as f:
        for seg in segments:
            f.write(f"{format_timestamp(seg['start'])} {seg['text']}\n")
    return filename


# ============================================================
# 5. DEEPSEEK API
# ============================================================
def analyze_with_deepseek(text: str,
                          max_summary_sentences: int = 10,
                          max_topics: int = 10) -> dict | None:
    """
    Изпраща текста към DeepSeek и получава:
      - резюме
      - списък с теми/сфери, открити от AI

    Връща: {"summary": str, "topics": [{"name", "description",
                                        "keywords", "importance"}]}
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("  ❌ Липсва DEEPSEEK_API_KEY в променливите на средата.")
        print("     Задай го с: export DEEPSEEK_API_KEY='твоят_ключ'")
        return None

    truncated = text[:30000]
    if len(text) > 30000:
        print(f"  ℹ️  Текстът е отрязан до 30 000 знака (от общо {len(text):,}).")

    system_prompt = (
        "Ти си опитен анализатор на новинарско съдържание с познания по "
        "психология на комуникацията и медийно въздействие. Получаваш "
        "транскрипт на видео (на български език) и трябва да върнеш "
        "СТРУКТУРИРАН JSON отговор с точно три ключа: "
        "'summary', 'topics' и 'psychology'.\n\n"
        "ПРАВИЛА:\n"
        f"1. 'summary' – кратко резюме на български език, не повече от "
        f"{max_summary_sentences} изречения.\n"
        f"2. 'topics' – списък от не повече от {max_topics} теми/сфери, "
        "за които реално се говори. Всяка тема е обект с полета:\n"
        "   - 'name': кратко име (2-4 думи).\n"
        "   - 'description': 1-2 изречения какво точно се казва.\n"
        "   - 'keywords': списък от 5-8 конкретни думи/фрази.\n"
        "   - 'importance': 'висока', 'средна' или 'ниска'.\n"
        "3. 'psychology' – психологически и комуникационен анализ. "
        "Обект със следните полета:\n"
        "   - 'emotional_tone': кратко описание на преобладаващия "
        "емоционален тон (напр. 'неутрален', 'тревожен', 'алармиращ', "
        "'успокояващ', 'смесен').\n"
        "   - 'emotions_detected': списък от емоции, които текстът "
        "предизвиква или отразява (напр. 'тревога', 'надежда', 'гняв', "
        "'страх', 'съчувствие', 'неутралност').\n"
        "   - 'target_audience': обект с полета:\n"
        "       * 'segments': списък от вероятни аудиторни сегменти "
        "(напр. 'пенсионери', 'работещи родители', 'бизнес среди', "
        "'млади хора', 'политически ангажирани граждани').\n"
        "       * 'reasoning': 2-3 изречения защо точно тези сегменти.\n"
        "   - 'usefulness': за какво би била полезна информацията на "
        "тези аудитории (2-3 изречения).\n"
        "   - 'potential_impact': списък от потенциални въздействия "
        "върху аудиторията – всеки е обект с полета 'effect' (кратко "
        "описание) и 'audience' (за кого се отнася).\n"
        "   - 'polarizing_topics': списък от теми, които биха могли да "
        "предизвикат поляризация или силна реакция.\n"
        "   - 'psychological_mechanisms': списък от използвани "
        "психологически механизми (напр. 'framing', 'priming', "
        "'емоционално зареждане', 'социално сравнение').\n"
        "   - 'caveats': задължително 1-2 изречения, че това е "
        "спекулативен анализ на база съдържание, а не научно "
        "изследване на реалната аудитория.\n\n"
        "ВАЖНО:\n"
        "- Открий темите от САМИЯ ТЕКСТ.\n"
        "- Подреди темите по важност.\n"
        "- Бъди конкретен – използвай примери от текста.\n"
        "- Отговорът ТРЯБВА да е валиден JSON, без обяснения извън JSON."
    )

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": (
                f"Ето транскрипта на видеото:\n\n{truncated}\n\n"
                "Върни JSON с 'summary' и 'topics' според инструкциите."
            )},
        ],
        "temperature": 0.3,
        "max_tokens": 4000,
        "response_format": {"type": "json_object"},
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        session = requests.Session()
        session.trust_env = False  # игнорира прокси променливите
        response = session.post(
            "https://api.deepseek.com/chat/completions",
            headers=headers, json=payload, timeout=180,
        )

        if response.status_code != 200:
            print(f"  ❌ HTTP {response.status_code}: {response.text[:300]}")
            return None

        content = response.json()["choices"][0]["message"]["content"].strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            cleaned = content.strip("` \n")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError as e:
                print(f"  ❌ Невалиден JSON: {e}")
                print(f"  📄 Суров отговор: {content[:500]}")
                return None

    except requests.exceptions.Timeout:
        print("  ❌ Timeout: DeepSeek не отговори в рамките на 180 секунди.")
        return None
    except Exception as e:
        print(f"  ❌ DeepSeek API грешка: {type(e).__name__}: {e}")
        return None


def print_ai_result(result: dict):
    """Извежда AI резюмето и тематичния анализ в четим вид."""
    if not result:
        return

    # ---- Резюме ----
    section("AI резюме", "📝")
    summary = (result.get("summary") or "").strip()
    if summary:
        # Пренасяме текста на блокове по ~80 знака за четимост
        print(f"\n{summary}")
        #import textwrap
        #for paragraph in summary.split("\ n"):
        #    if paragraph.strip():
        #        wrapped = textwrap.fill(paragraph.strip(),
        #                                width=68,
        #                                initial_indent="  ",
        #                                subsequent_indent="  ")
        #        print(f"\n{wrapped}")
    else:
        print("\n  (няма резюме)")

    # ---- Теми ----
    topics = result.get("topics") or []
    section("AI открити теми и сфери", "🎯")

    if not topics:
        print("\n  (не са открити теми)")
        return

    importance_icons = {"висока": "🔴", "средна": "🟡", "ниска": "🟢"}

    for i, t in enumerate(topics, 1):
        name = t.get("name", "?")
        desc = t.get("description", "")
        kws = t.get("keywords", []) or []
        imp = (t.get("importance") or "средна").lower()
        icon = importance_icons.get(imp, "⚪")

        print(f"\n  {i:>2}. {icon} {name}  [{imp}]")
        if desc:
            import textwrap
            wrapped = textwrap.fill(desc, width=68,
                                    initial_indent="      ",
                                    subsequent_indent="      ")
            print(wrapped)
        if kws:
            print(f"      Ключови думи: {', '.join(kws)}")


def print_psychology_analysis(result: dict):
    """Извежда психологическия анализ от AI резултата."""
    if not result:
        return

    psy = result.get("psychology")
    if not psy:
        return

    section("Психологически и комуникационен анализ", "🧠")

    # ---- Емоционален тон ----
    tone = psy.get("emotional_tone", "")
    if tone:
        print(f"\n  😊 Емоционален тон: {tone}")

    # ---- Открити емоции ----
    emotions = psy.get("emotions_detected") or []
    if emotions:
        print(f"\n  💭 Открити емоции:")
        for e in emotions:
            print(f"      • {e}")

    # ---- Целева аудитория ----
    aud = psy.get("target_audience") or {}
    segments = aud.get("segments") or []
    reasoning = aud.get("reasoning", "")

    if segments or reasoning:
        print(f"\n  👥 Вероятна целева аудитория:")
        for s in segments:
            print(f"      • {s}")
        if reasoning:
            print(f"\n      Обосновка: {reasoning}")

    # ---- Полезност ----
    usefulness = psy.get("usefulness", "")
    if usefulness:
        print(f"\n  💡 Полезност на информацията:")
        print(f"      {usefulness}")

    # ---- Потенциално въздействие ----
    impacts = psy.get("potential_impact") or []
    if impacts:
        print(f"\n  ⚡ Потенциално въздействие:")
        for imp in impacts:
            effect = imp.get("effect", "")
            audience = imp.get("audience", "")
            print(f"      • {effect}")
            if audience:
                print(f"        (за: {audience})")

    # ---- Поляризиращи теми ----
    polarizing = psy.get("polarizing_topics") or []
    if polarizing:
        print(f"\n  ⚠️  Поляризиращи теми:")
        for p in polarizing:
            print(f"      • {p}")

    # ---- Психологически механизми ----
    mechanisms = psy.get("psychological_mechanisms") or []
    if mechanisms:
        print(f"\n  🔬 Психологически механизми:")
        for m in mechanisms:
            print(f"      • {m}")

    # ---- Предупреждение ----
    caveats = psy.get("caveats", "")
    if caveats:
        print(f"\n  ℹ️  {caveats}")


# ============================================================
# 6. ЛОКАЛЕН АНАЛИЗ НА ЧЕСТОТАТА
# ============================================================
def print_word_frequency(text: str, top_n: int = 20):
    """Извежда най-често срещаните думи (без stop думи)."""
    words = re.findall(r"\w+", text.lower(), flags=re.UNICODE)
    words = [w for w in words if w.isalpha() and len(w) > 1]
    filtered = [w for w in words if w not in ALL_STOPWORDS]
    freq = Counter(filtered)

    section("Най-често срещани думи", "📊")
    print()

    if not freq:
        print("  (няма данни)")
        return

    max_count = freq.most_common(1)[0][1]
    for word, count in freq.most_common(top_n):
        bar_len = int(30 * count / max_count) if max_count > 0 else 0
        bar = "●" * bar_len
        print(f"  {word:<20} {count:>4}  {bar}")


# ============================================================
# 7. MAIN
# ============================================================
def main():
    if len(sys.argv) < 2:
        print("Употреба: python yt_analyzer.py <YouTube_URL>")
        sys.exit(1)

    url = sys.argv[1]
    print(f"\n🔗 URL: {url}")

    video_id = get_video_id(url)
    if not video_id:
        print("❌ Неуспешно извличане на Video ID от URL.")
        sys.exit(1)
    print(f"✅ Video ID: {video_id}")

    # ---- Метаданни ----
    meta = get_video_metadata(video_id)
    print_metadata(meta)

    # ---- Субтитри ----
    section("Изтегляне на субтитри", "📥")
    print()
    segments = get_subtitles_with_timestamps(video_id)

    if not segments:
        print("\n❌ Неуспешно извличане на субтитри.")
        sys.exit(1)

    # ---- Запазване на субтитрите ----
    sub_file = save_subtitles(video_id, segments)
    full_text = " ".join(seg["text"] for seg in segments)

    with open(f"{video_id}_transcript.txt", "w", encoding="utf-8") as f:
        f.write(full_text)

    meta_file = save_metadata(video_id, meta)

    section("Запазени файлове", "💾")
    print(f"\n  📄 {sub_file}")
    print(f"     └─ {len(segments):,} сегмента с таймстампи")
    print(f"  📄 {video_id}_transcript.txt")
    print(f"     └─ {len(full_text):,} знака чист текст")
    if meta_file:
        print(f"  📄 {meta_file}")
        print(f"     └─ заглавие, канал, дата, описание и др.")

    # ---- AI анализ ----
    section("AI анализ (DeepSeek)", "🤖")
    print()
    ai_result = analyze_with_deepseek(full_text, max_summary_sentences=10)

    if ai_result:
        # Запази JSON
        json_file = f"{video_id}_ai_analysis.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(ai_result, f, ensure_ascii=False, indent=2)
        print(f"  💾 JSON резултат: {json_file}")

        # Изведи красиво
        print_ai_result(ai_result)
        print_psychology_analysis(ai_result)
    else:
        print("  ⚠️  AI анализът не успя.")

    # ---- Локален анализ на думи ----
    print_word_frequency(full_text, top_n=20)

    # ---- Край ----
    print(f"\n{'═' * 64}")
    print(f"  ✅  ГОТОВО")
    print(f"{'═' * 64}\n")


if __name__ == "__main__":
    main()
