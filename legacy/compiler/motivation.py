#!/usr/bin/env python3
"""
YouTube Motivation Video Compiler - Format TikTok
Fetch plein de candidats, score par potentiel viral, garde les meilleurs.

INSTALLATION:
    pip install yt-dlp moviepy==1.0.3 Pillow requests tqdm

USAGE:
    python motivation.py
"""

import os
import sys
import json
import re
import requests
import subprocess
import math
from datetime import datetime, timezone

# Fix encodage Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
from moviepy.editor import VideoFileClip, CompositeVideoClip
import PIL

if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

# ============================================
# CONFIGURATION
# ============================================
CONFIG = {
    'candidates_per_query': 8,
    'max_videos': 3,
    'max_duration_per_part': 60,
    'zoom_factor': 1.15,
    'crop_position': 'center',

    # TikTok Upload
    'tiktok_username': 'dvlad2',
    'auto_upload': True,
    'tiktok_tags': '#motivation #mindset #discipline #success #viral #fyp #foryou #foryoupage #motivationfrancaise #developpementpersonnel #mentalite',

    # Filtres de qualite
    'min_views': 50_000,           # minimum 50k vues
    'min_like_ratio': 0.02,        # minimum 2% like ratio
    'max_duration': 300,           # max 5 min (au dela = trop long)
    'min_duration': 15,            # min 15s
    'min_channel_subs': 1_000,     # chaine avec au moins 1k abonnes
}

# ============================================
# QUERIES - Francais + anglais populaire
# ============================================
SEARCH_QUERIES = [
    # Francais - discours motivation
    "discours motivation francais",
    "motivation francais court viral",
    "discours motivant francais shorts",
    "motivation developpement personnel francais",
    "discipline mentale motivation francais",
    "ne lache jamais motivation francais",
    "motivation reussite francais",
    "motivation sport francais discours",
    "confiance en soi motivation francais",
    "mentalite de champion motivation francais",
    # Francais - createurs connus
    "david laroche motivation",
    "franck nicolas motivation",
    "motivation entrepreneur francais",
    # Anglais viral (sous-titre souvent dispo) - shorts/courts uniquement
    "motivation speech 1 minute viral",
    "motivational speech short powerful",
    "discipline equals freedom motivation short",
]


# ============================================
# PHASE 1 : FETCH DES CANDIDATS
# ============================================

def fetch_candidates(query, max_results=8):
    """Fetch des videos avec toutes les metadata pour le scoring"""
    print(f"  Recherche: '{query}' (max {max_results})...")

    cmd = [
        "yt-dlp",
        f"ytsearch{max_results}:{query}",
        "--dump-json",
        "--no-download",
        "--no-warnings",
        "-q"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        candidates = []

        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            try:
                data = json.loads(line)

                # Extraire la langue/description pour detecter le francais
                title = data.get('title', '')
                description = data.get('description', '') or ''
                language = data.get('language', '') or ''
                tags = data.get('tags', []) or []

                candidates.append({
                    'id': data.get('id', ''),
                    'title': title,
                    'description': description[:500],
                    'url': data.get('webpage_url', f"https://www.youtube.com/watch?v={data.get('id', '')}"),
                    'duration': data.get('duration', 0) or 0,
                    'view_count': data.get('view_count', 0) or 0,
                    'like_count': data.get('like_count', 0) or 0,
                    'comment_count': data.get('comment_count', 0) or 0,
                    'upload_date': data.get('upload_date', ''),
                    'width': data.get('width', 1920) or 1920,
                    'height': data.get('height', 1080) or 1080,
                    'channel': data.get('channel', ''),
                    'channel_follower_count': data.get('channel_follower_count', 0) or 0,
                    'language': language,
                    'tags': tags,
                    'categories': data.get('categories', []) or [],
                })
            except json.JSONDecodeError:
                continue

        print(f"    -> {len(candidates)} candidats trouves")
        return candidates

    except Exception as e:
        print(f"    Erreur: {e}")
        return []


# ============================================
# PHASE 2 : FILTRES + SCORING
# ============================================

# Mots-cles qui indiquent du contenu meme/low-quality/pas motivation
BLACKLIST_KEYWORDS = [
    'meme', 'memes', 'funny', 'compilation drole', 'prank', 'troll',
    'asmr', 'mukbang', 'unboxing', 'gaming', 'gameplay', 'fortnite',
    'minecraft', 'roblox', 'gta', 'reaction', 'tier list',
    'star trek grindset',  # le genre de video meme qu'on veut pas
]

# Mots-cles francais qui boostent le score
FRENCH_KEYWORDS = [
    'francais', 'francaise', 'french', 'fr',
    'motivation francaise', 'discours', 'reussite', 'mentalite',
    'developpement personnel', 'confiance', 'discipline',
    'ne lache', 'abandonne', 'courage', 'force mentale',
    'entrepreneur', 'objectif', 'reve', 'croire',
]

# Chaines connues de qualite motivation
TRUSTED_CHANNELS = [
    'david laroche', 'franck nicolas', 'motiversity', 'ben lionel scott',
    'absolute motivation', 'mulligan brothers', 'goalcast',
    'eddie pinero', 'your world within', 'law of attraction coaching',
    'team fearless', 'motivation2study', 'successfied',
    'inspiration station', 'chispa motivation',
]


def is_french_content(video):
    """Detecte si le contenu est en francais"""
    text = (video['title'] + ' ' + video['description'] + ' ' + ' '.join(video['tags'])).lower()

    # Langue explicite
    if video['language'] in ('fr', 'fra', 'french'):
        return True

    # Mots francais typiques dans le titre/description
    french_indicators = [
        'francais', 'francaise', 'en francais', 'fr ', '#fr ',
        'discours', 'reussite', 'ne lache', 'abandonn',
        'mentalite', 'developpement', 'confiance en soi',
        'croire en', 'objectif', 'entrepreneur francais',
        'la vie', "l'echec", "n'abandonne", "tu peux", "ta vie",
        "jamais", "courage", "force mentale",
    ]

    matches = sum(1 for kw in french_indicators if kw in text)
    return matches >= 2


def is_blacklisted(video):
    """Filtre les videos low-quality"""
    text = (video['title'] + ' ' + ' '.join(video['tags'])).lower()
    return any(kw in text for kw in BLACKLIST_KEYWORDS)


def is_trusted_channel(video):
    """Verifie si la chaine est connue pour du bon contenu"""
    channel = video['channel'].lower()
    return any(tc in channel for tc in TRUSTED_CHANNELS)


def passes_quality_filters(video):
    """Filtre les videos qui ne passent pas les criteres minimum"""
    if video['view_count'] < CONFIG['min_views']:
        return False, "pas assez de vues"

    if video['duration'] < CONFIG['min_duration']:
        return False, "trop court"

    if video['duration'] > CONFIG['max_duration']:
        return False, "trop long"

    if video['view_count'] > 0:
        like_ratio = video['like_count'] / video['view_count']
        if like_ratio < CONFIG['min_like_ratio']:
            return False, "like ratio trop bas"

    if is_blacklisted(video):
        return False, "contenu blackliste"

    return True, "ok"


def score_video(video):
    """Score un candidat de 0 a 100 selon son potentiel viral TikTok"""
    scores = {}

    # === 1. Vues normalisees (log scale) - 15% ===
    views = max(video['view_count'], 1)
    # 100k = 0.5, 1M = 0.75, 10M = 1.0
    scores['views'] = min(math.log10(views) / 7.0, 1.0)

    # === 2. Like ratio - 15% ===
    if video['view_count'] > 0:
        like_ratio = video['like_count'] / video['view_count']
        # 3% = bon, 5%+ = excellent
        scores['like_ratio'] = min(like_ratio / 0.05, 1.0)
    else:
        scores['like_ratio'] = 0

    # === 3. Engagement (commentaires) - 5% ===
    if video['view_count'] > 0:
        comment_ratio = video['comment_count'] / video['view_count']
        scores['engagement'] = min(comment_ratio / 0.005, 1.0)
    else:
        scores['engagement'] = 0

    # === 4. Duree ideale TikTok - 20% ===
    dur = video['duration']
    if 20 <= dur <= 60:
        scores['duration'] = 1.0
    elif 60 < dur <= 90:
        scores['duration'] = 0.8
    elif 90 < dur <= 180:
        scores['duration'] = 0.5
    elif 15 <= dur < 20:
        scores['duration'] = 0.6
    else:
        scores['duration'] = 0.2

    # === 5. Format vertical (deja pret pour TikTok) - 10% ===
    w, h = video['width'], video['height']
    if w / h < 0.7:
        scores['vertical'] = 1.0
    elif w / h < 1.0:
        scores['vertical'] = 0.5  # carre
    else:
        scores['vertical'] = 0.2

    # === 6. FRANCAIS - 20% (le plus important) ===
    if is_french_content(video):
        scores['french'] = 1.0
    else:
        # Pas francais = gros malus, mais pas eliminatoire si tres viral
        scores['french'] = 0.1

    # === 7. Chaine de confiance - 10% ===
    if is_trusted_channel(video):
        scores['channel'] = 1.0
    elif video['channel_follower_count'] > 100_000:
        scores['channel'] = 0.8
    elif video['channel_follower_count'] > 10_000:
        scores['channel'] = 0.5
    elif video['channel_follower_count'] > 1_000:
        scores['channel'] = 0.3
    else:
        scores['channel'] = 0.1

    # === 8. Recency - 5% ===
    if video['upload_date']:
        try:
            upload = datetime.strptime(video['upload_date'], '%Y%m%d').replace(tzinfo=timezone.utc)
            days_ago = (datetime.now(timezone.utc) - upload).days
            if days_ago < 30:
                scores['recency'] = 1.0
            elif days_ago < 90:
                scores['recency'] = 0.8
            elif days_ago < 365:
                scores['recency'] = 0.5
            else:
                scores['recency'] = 0.2
        except:
            scores['recency'] = 0.3
    else:
        scores['recency'] = 0.3

    # Poids
    weights = {
        'views': 0.15,
        'like_ratio': 0.15,
        'engagement': 0.05,
        'duration': 0.20,
        'vertical': 0.10,
        'french': 0.20,
        'channel': 0.10,
        'recency': 0.05,
    }

    total = sum(scores[k] * weights[k] for k in weights)
    final_score = round(total * 100, 1)

    return final_score, scores


def rank_candidates(candidates):
    """Filtre, score et trie tous les candidats"""
    # Dedup
    seen_ids = set()
    unique = []
    for c in candidates:
        if c['id'] not in seen_ids:
            seen_ids.add(c['id'])
            unique.append(c)

    print(f"\n  {len(unique)} candidats uniques (sur {len(candidates)} total)")

    # Filtres de qualite
    passed = []
    filtered_out = 0
    for c in unique:
        ok, reason = passes_quality_filters(c)
        if ok:
            passed.append(c)
        else:
            filtered_out += 1

    print(f"  {len(passed)} passent les filtres qualite ({filtered_out} elimines)")

    # Score
    for c in passed:
        c['score'], c['score_details'] = score_video(c)
        c['is_french'] = is_french_content(c)

    ranked = sorted(passed, key=lambda x: x['score'], reverse=True)
    return ranked


def print_ranking(ranked, top_n=15):
    """Affiche le classement"""
    print(f"\n{'=' * 70}")
    print(f"TOP {min(top_n, len(ranked))} CANDIDATS")
    print(f"{'=' * 70}")

    for i, v in enumerate(ranked[:top_n], 1):
        dur_str = f"{v['duration']}s"
        views_str = f"{v['view_count']:,}".replace(',', ' ')
        vertical = "V" if v['width'] / v['height'] < 0.7 else "H"
        lang = "FR" if v.get('is_french') else "EN"

        print(f"\n  #{i} [{v['score']}/100] [{lang}] {v['title'][:50]}")
        print(f"      {views_str} vues | {dur_str} | {vertical} | {v['channel'][:25]}")

        d = v['score_details']
        print(f"      vues:{d['views']:.1f} like:{d['like_ratio']:.1f} dur:{d['duration']:.1f} FR:{d['french']:.1f} chan:{d['channel']:.1f} vert:{d['vertical']:.1f}")


# ============================================
# PHASE 3 : DOWNLOAD + PROCESSING
# ============================================

def download_video(url, video_id, output_dir="downloads"):
    """Telecharge une video - utilise l'ID pour verifier le bon fichier"""
    os.makedirs(output_dir, exist_ok=True)

    # Nettoyer le dossier
    for f in os.listdir(output_dir):
        try:
            os.remove(os.path.join(output_dir, f))
        except:
            pass

    output_template = os.path.join(output_dir, "%(id)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "--merge-output-format", "mp4",
        "-o", output_template,
        "--no-playlist",
        url
    ]

    try:
        print(f"  Telechargement...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        # Verifier que c'est le bon fichier
        for f in os.listdir(output_dir):
            if f.endswith(('.mp4', '.mkv', '.webm')):
                filepath = os.path.join(output_dir, f)
                print(f"    Telecharge: {f}")
                return filepath

        # Log erreur si rien telecharge
        if result.stderr:
            print(f"    Erreur yt-dlp: {result.stderr[:200]}")
        return None
    except Exception as e:
        print(f"  Erreur: {e}")
        return None


def is_vertical_video(clip):
    w, h = clip.size
    return (w / h) < 0.7


def convert_to_tiktok(clip, zoom=1.1, crop_pos='center'):
    TARGET_W, TARGET_H = 1080, 1920
    orig_w, orig_h = clip.size

    if is_vertical_video(clip):
        print(f"    Short detecte ({orig_w}x{orig_h}) - resize")
        return clip.resize((TARGET_W, TARGET_H))

    print(f"    Horizontal ({orig_w}x{orig_h}) - crop + zoom {zoom}x")
    target_ratio = TARGET_W / TARGET_H
    new_w, new_h = int(orig_w * zoom), int(orig_h * zoom)
    clip = clip.resize((new_w, new_h))

    if orig_w / orig_h > target_ratio:
        crop_w = int(new_h * target_ratio)
        x1 = (new_w - crop_w) // 2
        clip = clip.crop(x1=x1, y1=0, width=crop_w, height=new_h)
    else:
        crop_h = int(new_w / target_ratio)
        if crop_pos == 'top':
            y1 = 0
        elif crop_pos == 'bottom':
            y1 = new_h - crop_h
        else:
            y1 = (new_h - crop_h) // 2
        clip = clip.crop(x1=0, y1=y1, width=new_w, height=crop_h)

    return clip.resize((TARGET_W, TARGET_H))


def add_text(clip, text, font_path=None):
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np
    from moviepy.video.VideoClip import ImageClip

    try:
        w, h = clip.size
        img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype(font_path, 70) if font_path else ImageFont.load_default()
        except:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x, y = (w - tw) // 2, (h - th) // 2

        for dx in range(-5, 6):
            for dy in range(-5, 6):
                draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, 255))
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))

        txt_clip = ImageClip(np.array(img), transparent=True).set_duration(clip.duration)
        return CompositeVideoClip([clip, txt_clip])
    except Exception as e:
        print(f"    Erreur texte: {e}")
        return clip


def split_video(video_path, max_dur=60, font_path=None, title="Motivation", zoom=1.15, crop_pos='center'):
    """Decoupe une video en parties - recharge le clip pour chaque part (fix bug audio moviepy)"""
    os.makedirs("output", exist_ok=True)
    print(f"\n Traitement: {os.path.basename(video_path)}")

    try:
        # Premier passage : lire les infos
        clip = VideoFileClip(video_path)
        total_dur = clip.duration
        has_audio = clip.audio is not None
        w, h = clip.size
        is_vertical = is_vertical_video(clip)
        clip.close()

        print(f"  Duree: {total_dur:.1f}s | {w}x{h} | Audio: {'oui' if has_audio else 'non'} | {'Vertical' if is_vertical else 'Horizontal'}")

        num_parts = max(1, int(total_dur // max_dur) + (1 if total_dur % max_dur > 5 else 0))
        print(f"  Parties: {num_parts}")

        outputs = []

        for i in range(num_parts):
            start = i * max_dur
            end = min((i + 1) * max_dur, total_dur)

            if end - start < 10 and i > 0:
                continue

            print(f"\n  Part {i + 1}/{num_parts} ({start:.0f}s - {end:.0f}s)")

            # Recharger le clip pour chaque part (fix bug audio moviepy)
            clip = VideoFileClip(video_path)
            segment = clip.subclip(start, end)
            segment_audio = segment.audio

            segment_converted = convert_to_tiktok(segment, zoom, crop_pos)

            if segment_audio is not None:
                segment_converted = segment_converted.set_audio(segment_audio)

            overlay = f"{title} Part {i + 1}" if num_parts > 1 else title
            segment_final = add_text(segment_converted, overlay, font_path)

            if segment_audio is not None:
                segment_final = segment_final.set_audio(segment_audio)

            safe_title = "".join(c for c in title if c.isalnum() or c in ' -_')[:25]
            filename = f"{safe_title}_part{i + 1:02d}.mp4" if num_parts > 1 else f"{safe_title}.mp4"
            output_path = os.path.join("output", filename)

            print(f"    Export: {filename}")

            segment_final.write_videofile(
                output_path,
                fps=30,
                codec="libx264",
                audio_codec="aac",
                temp_audiofile=f"temp_{i}.m4a",
                remove_temp=True,
                threads=4,
                preset='medium',
                verbose=False,
                logger=None
            )

            outputs.append({
                'path': output_path,
                'part': i + 1,
                'total_parts': num_parts,
                'duration': end - start,
                'title': title
            })

            try:
                segment_final.close()
                segment_converted.close()
                segment.close()
                clip.close()
            except:
                pass

        return outputs

    except Exception as e:
        print(f"  Erreur: {e}")
        import traceback
        traceback.print_exc()
        return []


def upload_to_tiktok(video_path, title, username, description=None):
    uploader_dir = "./vendor/TiktokAutoUploader"
    cookie_dir = os.path.join(uploader_dir, "CookiesDir")

    if not os.path.exists(uploader_dir):
        print(f"\n TiktokAutoUploader non trouve dans {uploader_dir}")
        return False

    if not os.path.exists(video_path):
        print(f"\n Video non trouvee : {video_path}")
        return False

    print(f"\n Upload: {os.path.basename(video_path)}")

    video_path_abs = os.path.abspath(video_path)
    original_dir = os.getcwd()

    try:
        os.chdir(uploader_dir)

        def check_cookie_exists(cookie_name):
            if not os.path.exists(cookie_dir):
                return False
            for filename in os.listdir(cookie_dir):
                if cookie_name in filename:
                    return True
            return False

        def run_command(command):
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout_output = ""
            for line in iter(process.stdout.readline, ""):
                print(line, end="")
                stdout_output += line
            process.stdout.close()
            process.wait()
            return process.returncode, stdout_output

        if not check_cookie_exists(username):
            print(f"\n Connexion requise pour {username}...")
            login_command = [sys.executable, "cli.py", "login", "-n", username]
            return_code, output = run_command(login_command)
            if "Unnecessary login" not in output and "session already saved" not in output and return_code != 0:
                return False

        full_title = f"{title} {description}" if description else title
        upload_command = [sys.executable, "cli.py", "upload", "--user", username, "-v", video_path_abs, "-t",
                          full_title]
        return_code, output = run_command(upload_command)

        if return_code == 0:
            print(f"  Upload reussi !")
            return True
        else:
            print(f"  Echec")
            return False

    except Exception as e:
        print(f"\n Erreur: {e}")
        return False
    finally:
        os.chdir(original_dir)


# ============================================
# MAIN
# ============================================

def main():
    print("=" * 70)
    print("  MOTIVATION TIKTOK - SMART RANKING v2")
    print("=" * 70)
    print(f"\n Config:")
    print(f"  - {len(SEARCH_QUERIES)} queries (FR + EN viral)")
    print(f"  - {CONFIG['candidates_per_query']} candidats/query")
    print(f"  - Filtres: >{CONFIG['min_views']} vues, >{CONFIG['min_like_ratio']*100}% likes, {CONFIG['min_duration']}-{CONFIG['max_duration']}s")
    print(f"  - Top {CONFIG['max_videos']} selectionnes")
    print(f"  - Auto-upload: {'OUI' if CONFIG['auto_upload'] else 'NON'}")

    # PHASE 1 : Fetch
    print(f"\n{'=' * 70}")
    print("PHASE 1 : RECHERCHE DES CANDIDATS")
    print(f"{'=' * 70}")

    all_candidates = []
    for query in SEARCH_QUERIES:
        found = fetch_candidates(query, max_results=CONFIG['candidates_per_query'])
        all_candidates.extend(found)

    if not all_candidates:
        print("\n Aucun candidat trouve")
        return

    print(f"\n  Total brut: {len(all_candidates)} candidats fetches")

    # PHASE 2 : Filtre + Score + Rank
    print(f"\n{'=' * 70}")
    print("PHASE 2 : FILTRAGE & SCORING")
    print(f"{'=' * 70}")

    ranked = rank_candidates(all_candidates)

    if not ranked:
        print("\n Aucun candidat ne passe les filtres")
        return

    print_ranking(ranked, top_n=15)

    # Compter FR vs EN dans le top
    top_fr = sum(1 for v in ranked[:10] if v.get('is_french'))
    print(f"\n  Dans le top 10: {top_fr} FR / {10 - top_fr} EN")

    # Selection
    selected = ranked[:CONFIG['max_videos']]

    print(f"\n{'=' * 70}")
    print(f"SELECTION FINALE : {len(selected)} videos")
    print(f"{'=' * 70}")
    for i, v in enumerate(selected, 1):
        lang = "FR" if v.get('is_french') else "EN"
        print(f"  #{i} [{v['score']}/100] [{lang}] {v['title'][:55]}")
        print(f"      {v['url']}")

    # PHASE 3 : Download + Process
    print(f"\n{'=' * 70}")
    print("PHASE 3 : DOWNLOAD & PROCESSING")
    print(f"{'=' * 70}")

    font = download_font()
    os.makedirs("downloads", exist_ok=True)
    all_outputs = []

    for idx, video in enumerate(selected, 1):
        print(f"\n{'=' * 60}")
        print(f" [{idx}/{len(selected)}] {video['title'][:50]}...")
        print(f"   Score: {video['score']}/100 | {video['url']}")
        print("=" * 60)

        path = download_video(video['url'], video['id'])
        if not path:
            continue

        short_title = " ".join(video['title'].split()[:3])[:20]

        outputs = split_video(
            path,
            max_dur=CONFIG['max_duration_per_part'],
            font_path=font,
            title=short_title,
            zoom=CONFIG['zoom_factor'],
            crop_pos=CONFIG['crop_position']
        )
        all_outputs.extend(outputs)

        try:
            os.remove(path)
        except:
            pass

    # Nettoyage
    try:
        for f in os.listdir("downloads"):
            os.remove(os.path.join("downloads", f))
        os.rmdir("downloads")
    except:
        pass

    # Resume
    print(f"\n{'=' * 70}")
    print("RESULTAT FINAL")
    print(f"{'=' * 70}")

    if all_outputs:
        print(f"\n {len(all_outputs)} video(s) dans 'output/':")
        total = 0
        for o in all_outputs:
            print(f"  - {os.path.basename(o['path'])} ({o['duration']:.0f}s)")
            total += o['duration']
        print(f"\n Duree totale: {total:.0f}s | Format: 1080x1920")

        if CONFIG['auto_upload']:
            print(f"\n{'=' * 70}")
            print("UPLOAD TIKTOK")
            print(f"{'=' * 70}")

            # Mix une musique triste tendance differente par sortie
            try:
                from music_helper import mix_background_music
                used = []
                for o in all_outputs:
                    out_with_music = o['path'].replace('.mp4', '_music.mp4')
                    mixed = mix_background_music(
                        video_path=o['path'],
                        output_path=out_with_music,
                        vibe='tendance',
                        music_volume=0.5,
                        duck_original=0.35,
                    )
                    if mixed:
                        o['path'] = mixed
                        used.append(os.path.basename(mixed))
                if used:
                    print(f"  Musiques ajoutees: {len(used)}")
            except Exception as e:
                print(f"  ⚠ Impossible de mixer la musique: {e}")

            for o in all_outputs:
                title_with_part = o['title']
                if o['total_parts'] > 1:
                    title_with_part = f"{o['title']} Part {o['part']}"

                success = upload_to_tiktok(
                    video_path=o['path'],
                    title=title_with_part,
                    username=CONFIG['tiktok_username'],
                    description=CONFIG['tiktok_tags']
                )

                if not success:
                    print(f"\n Upload manuel: cd vendor/TiktokAutoUploader && python cli.py upload --user {CONFIG['tiktok_username']} -v ../../{o['path']}")
    else:
        print("\n Aucune video creee")

    print("\n TERMINE !")


if __name__ == "__main__":
    main()
