"""Quran metadata: surahs, reciter registry, styles, reference parsing."""
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = json.load(open(os.path.join(BASE, "quran_uthmani.json"), encoding="utf-8"))
SURAHS = {s["n"]: s for s in DATA}

# taken from the data itself so prefix matching uses identical codepoints
BASMALA = SURAHS[1]["ayahs"][0].replace("﻿", "").strip()

# 47 reciters, per-ayah mp3 sets on everyayah.com (SSSAAA.mp3 naming).
# Ordered roughly by popularity for the picker.
RECITERS = [
    ("Alafasy_128kbps", "مشاري العفاسي"),
    ("Abdul_Basit_Murattal_192kbps", "عبد الباسط عبد الصمد (مرتل)"),
    ("Abdul_Basit_Mujawwad_128kbps", "عبد الباسط عبد الصمد (مجود)"),
    ("Husary_128kbps", "محمود خليل الحصري"),
    ("Husary_128kbps_Mujawwad", "الحصري (مجود)"),
    ("Husary_Muallim_128kbps", "الحصري (معلم)"),
    ("Minshawy_Murattal_128kbps", "محمد صديق المنشاوي (مرتل)"),
    ("Minshawy_Mujawwad_192kbps", "المنشاوي (مجود)"),
    ("Minshawy_Teacher_128kbps", "المنشاوي (معلم)"),
    ("Abdurrahmaan_As-Sudais_192kbps", "عبد الرحمن السديس"),
    ("Saood_ash-Shuraym_128kbps", "سعود الشريم"),
    ("MaherAlMuaiqly128kbps", "ماهر المعيقلي"),
    ("Abu_Bakr_Ash-Shaatree_128kbps", "أبو بكر الشاطري"),
    ("Muhammad_Jibreel_128kbps", "محمد جبريل"),
    ("Muhammad_Ayyoub_128kbps", "محمد أيوب"),
    ("Abdullah_Basfar_192kbps", "عبد الله بصفر"),
    ("Hudhaify_128kbps", "علي الحذيفي"),
    ("Hani_Rifai_192kbps", "هاني الرفاعي"),
    ("Ahmed_ibn_Ali_al-Ajamy_128kbps_ketaballah.net", "أحمد بن علي العجمي"),
    ("Nasser_Alqatami_128kbps", "ناصر القطامي"),
    ("Yasser_Ad-Dussary_128kbps", "ياسر الدوسري"),
    ("Fares_Abbad_64kbps", "فارس عباد"),
    ("Ghamadi_40kbps", "سعد الغامدي"),
    ("Salah_Al_Budair_128kbps", "صلاح البدير"),
    ("Salaah_AbdulRahman_Bukhatir_128kbps", "صلاح عبد الرحمن بوخاطر"),
    ("Khaalid_Abdullaah_al-Qahtaanee_192kbps", "خالد عبد الله القحطاني"),
    ("Muhsin_Al_Qasim_192kbps", "محسن القاسم"),
    ("Abdullaah_3awwaad_Al-Juhaynee_128kbps", "عبد الله عواد الجهني"),
    ("Abdullah_Matroud_128kbps", "عبد الله المطرود"),
    ("Ibrahim_Akhdar_32kbps", "إبراهيم الأخضر"),
    ("Ayman_Sowaid_64kbps", "أيمن سويد"),
    ("Mohammad_al_Tablaway_128kbps", "محمد الطبلاوي"),
    ("Muhammad_AbdulKareem_128kbps", "محمد عبد الكريم"),
    ("Mustafa_Ismail_48kbps", "مصطفى إسماعيل"),
    ("mahmoud_ali_al_banna_32kbps", "محمود علي البنا"),
    ("Ali_Jaber_64kbps", "علي جابر"),
    ("Ahmed_Neana_128kbps", "أحمد نعينع"),
    ("Akram_AlAlaqimy_128kbps", "أكرم العلاقمي"),
    ("Ali_Hajjaj_AlSuesy_128kbps", "علي حجاج السويسي"),
    ("Sahl_Yassin_128kbps", "سهل ياسين"),
    ("Yaser_Salamah_128kbps", "ياسر سلامة"),
    ("Nabil_Rifa3i_48kbps", "نبيل الرفاعي"),
    ("khalefa_al_tunaiji_64kbps", "خليفة الطنيجي"),
    ("aziz_alili_128kbps", "عزيز عليلي"),
    ("Parhizgar_48kbps", "شهريار برهيزكار"),
    ("Karim_Mansoori_40kbps", "كريم منصوري"),
    ("AbdulSamad_64kbps_QuranExplorer.Com", "عبد الصمد"),
]

AUDIO_URL = "https://everyayah.com/data/{folder}/{sss:03d}{aaa:03d}.mp3"

STYLE_NAMES = {
    "chat": "دردشة واتساب",
    "dark": "دارك خالص",
    "night": "ليل ونجوم",
    "ornament": "زخرفة إسلامية",
    "nature": "طبيعة",
    "solid": "لون سادة",
}

SOLID_COLORS = {
    "navy":     {"bg": (22, 33, 58),    "light": False, "ar": "كحلي"},
    "black":    {"bg": (14, 14, 16),    "light": False, "ar": "أسود"},
    "emerald":  {"bg": (11, 58, 44),    "light": False, "ar": "زمردي"},
    "burgundy": {"bg": (87, 28, 43),    "light": False, "ar": "عنابي"},
    "purple":   {"bg": (36, 21, 54),    "light": False, "ar": "بنفسجي"},
    "sand":     {"bg": (239, 230, 210), "light": True,  "ar": "رملي"},
}

AR_DIGITS_OUT = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
AR_DIGITS_IN = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def ar_num(n):
    return str(n).translate(AR_DIGITS_OUT)


def ayah_text(surah, ayah):
    """Uthmani text; basmala stripped from ayah 1 (it is shown as its own line)."""
    t = SURAHS[surah]["ayahs"][ayah - 1].replace("﻿", "").strip()
    if ayah == 1 and surah not in (1, 9) and t.startswith(BASMALA):
        t = t[len(BASMALA):].strip()
    return t


def show_basmala(surah, a1):
    return a1 == 1 and surah != 9


# simplified surah names for name lookup (no diacritics)
SURAH_SIMPLE = ["الفاتحة","البقرة","آل عمران","النساء","المائدة","الأنعام","الأعراف","الأنفال","التوبة","يونس",
"هود","يوسف","الرعد","إبراهيم","الحجر","النحل","الإسراء","الكهف","مريم","طه",
"الأنبياء","الحج","المؤمنون","النور","الفرقان","الشعراء","النمل","القصص","العنكبوت","الروم",
"لقمان","السجدة","الأحزاب","سبأ","فاطر","يس","الصافات","ص","الزمر","غافر",
"فصلت","الشورى","الزخرف","الدخان","الجاثية","الأحقاف","محمد","الفتح","الحجرات","ق",
"الذاريات","الطور","النجم","القمر","الرحمن","الواقعة","الحديد","المجادلة","الحشر","الممتحنة",
"الصف","الجمعة","المنافقون","التغابن","الطلاق","التحريم","الملك","القلم","الحاقة","المعارج",
"نوح","الجن","المزمل","المدثر","القيامة","الإنسان","المرسلات","النبأ","النازعات","عبس",
"التكوير","الانفطار","المطففين","الانشقاق","البروج","الطارق","الأعلى","الغاشية","الفجر","البلد",
"الشمس","الليل","الضحى","الشرح","التين","العلق","القدر","البينة","الزلزلة","العاديات",
"القارعة","التكاثر","العصر","الهمزة","الفيل","قريش","الماعون","الكوثر","الكافرون","النصر",
"المسد","الإخلاص","الفلق","الناس"]

_ALEF = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه"})
_NAME_INDEX = {}
for _i, _n in enumerate(SURAH_SIMPLE, 1):
    _NAME_INDEX[_n.translate(_ALEF)] = _i


def find_surah(token):
    token = token.strip().translate(_ALEF)
    token = re.sub(r"^(سوره|سورة)\s+", "", token)
    return _NAME_INDEX.get(token)


_REF_NUM = re.compile(r"^(\d{1,3})\s*[:：]\s*(\d{1,3})(?:\s*[-–]\s*(\d{1,3}))?$")
_REF_NAME = re.compile(r"^(.+?)\s+(\d{1,3})(?:\s*[-–]\s*(\d{1,3}))?$")


def parse_ref(text):
    """Parse '2:255', '2:255-257', 'يس 36', 'الفاتحة 1-7' -> (surah, a1, a2).

    Raises ValueError with an Arabic user-facing message.
    """
    t = (text or "").strip().translate(AR_DIGITS_IN)
    surah = a1 = a2 = None
    m = _REF_NUM.match(t)
    if m:
        surah, a1, a2 = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0) or None
    else:
        m = _REF_NAME.match(t)
        if m:
            surah = find_surah(m.group(1))
            if surah:
                a1, a2 = int(m.group(2)), int(m.group(3) or 0) or None
    if not surah:
        raise ValueError("لم أفهم المرجع. اكتب مثلًا: 2:255 أو 36:1-5 أو «الفاتحة 1-7»")
    if not (1 <= surah <= 114):
        raise ValueError("رقم السورة يجب أن يكون بين 1 و114.")
    if a2 is None:
        a2 = a1
    n_ayahs = len(SURAHS[surah]["ayahs"])
    if not (1 <= a1 <= n_ayahs) or not (a1 <= a2 <= n_ayahs):
        raise ValueError(f"سورة {SURAH_SIMPLE[surah-1]} فيها {ar_num(n_ayahs)} آية فقط. راجع الأرقام.")
    if a2 - a1 + 1 > 60:
        raise ValueError("الحد الأقصى ٦٠ آية في المقطع الواحد و٥ دقائق إجمالًا.")
    return surah, a1, a2


_DIACRITICS = re.compile(r"[ً-ْٰـۖ-ۭۚ-۟۠-۩]")


def _norm(t):
    t = _DIACRITICS.sub("", t)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ٱ", "ا"),
                 ("ة", "ه"), ("ى", "ي"), ("ؤ", "و"), ("ئ", "ي")):
        t = t.replace(a, b)
    t = re.sub(r"[^ء-ي ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


_NORM_INDEX = None
_BASMALA_N = ""


def _norm_index():
    global _NORM_INDEX, _BASMALA_N
    if _NORM_INDEX is None:
        _BASMALA_N = _norm(BASMALA)
        _NORM_INDEX = [(s, i + 1, _norm(ayah_text(s, i + 1)))
                       for s in range(1, 115)
                       for i in range(len(SURAHS[s]["ayahs"]))]
    return _NORM_INDEX


def match_verse(text):
    """Match pasted verse text to (surah, ayah, score 0..1), or None."""
    import difflib
    n = _norm(text or "")
    if _BASMALA_N and n.startswith(_BASMALA_N) and len(n) > len(_BASMALA_N) + 6:
        n = n[len(_BASMALA_N):].strip()
    if len(n) < 8:
        return None
    idx = _norm_index()
    npad, cands = f" {n} ", []
    for s, a, an in idx:
        if not an or len(an) < 8:
            continue
        apad = f" {an} "
        if npad in apad or apad in npad:
            score = 0.95 + 0.05 * min(len(n), len(an)) / max(len(n), len(an))
            cands.append((score, s, a))
    if cands:
        cands.sort(reverse=True)
        return (cands[0][1], cands[0][2], cands[0][0])
    ntok = set(n.split())
    need = max(2, int(0.5 * len(ntok)))
    pre = []
    for s, a, an in idx:
        shared = len(ntok & set(an.split()))
        if shared >= need:
            pre.append((shared, s, a, an))
    pre.sort(key=lambda x: -x[0])
    nw = n.split()
    best_r, best = 0.0, None
    for shared, s, a, an in pre[:40]:
        aw = an.split()
        if len(aw) <= len(nw) + 3:
            rmax = difflib.SequenceMatcher(None, n, an).ratio()
        else:
            rmax = 0.0
            for wlen in (len(nw) - 1, len(nw), len(nw) + 1, len(nw) + 2):
                if wlen < 2:
                    continue
                for i in range(len(aw) - wlen + 1):
                    r = difflib.SequenceMatcher(None, n, " ".join(aw[i:i + wlen])).ratio()
                    if r > rmax:
                        rmax = r
        if rmax > best_r:
            best_r, best = rmax, (s, a)
    if best and best_r >= 0.72:
        return (best[0], best[1], best_r)
    return None
