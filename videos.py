#!/usr/bin/env python3
"""
YouTube Science Video Compiler - Format TikTok
Télécharge des vidéos de sciences sur YouTube et les découpe en parties de 1 minute max.
Upload automatique sur TikTok.

INSTALLATION:
    pip install yt-dlp moviepy==1.0.3 Pillow requests tqdm

USAGE:
    python youtube_science_tiktok.py
"""

import os
import sys
import requests
import subprocess
from moviepy.editor import VideoFileClip, CompositeVideoClip
from tqdm import tqdm
import PIL

if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

# ============================================
# CONFIGURATION - MODIFIE ICI
# ============================================
CONFIG = {
    'search_query': 'science facts amazing',  # Recherche YouTube
    'max_videos': 3,  # Nombre de vidéos à télécharger
    'max_duration_per_part': 60,  # Durée max par partie (secondes)
    'zoom_factor': 1.15,  # Zoom (1.0 = pas de zoom) - ignoré pour les shorts
    'crop_position': 'center',  # 'center', 'top', 'bottom'

    # TikTok Upload
    'tiktok_username': 'dvlad2',  # Ton username TikTok
    'auto_upload': True,  # Upload automatique activé
    'tiktok_tags': '#science #viral #fyp #foryou #foryoupage',
}


def download_font():
    """Télécharge la police Bangers"""
    font_path = "Bangers-Regular.ttf"
    if os.path.exists(font_path):
        return font_path
    try:
        print("  📥 Téléchargement de la police...")
        url = "https://github.com/google/fonts/raw/main/ofl/bangers/Bangers-Regular.ttf"
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        with open(font_path, 'wb') as f:
            f.write(r.content)
        return font_path
    except:
        return None


def search_youtube(query, max_results=5):
    """Recherche des vidéos sur YouTube"""
    print(f"\n🔍 Recherche YouTube : '{query}'...")
    cmd = ["yt-dlp", f"ytsearch{max_results}:{query}", "--get-id", "--get-title", "--get-duration", "--no-warnings",
           "-q"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        lines = result.stdout.strip().split('\n')
        videos = []
        i = 0
        while i < len(lines) - 2:
            title, vid_id, duration = lines[i].strip(), lines[i + 1].strip(), lines[i + 2].strip()
            if vid_id and len(vid_id) == 11:
                videos.append({
                    'id': vid_id,
                    'title': title,
                    'duration': duration,
                    'url': f"https://www.youtube.com/watch?v={vid_id}"
                })
            i += 3
        print(f"  ✓ {len(videos)} vidéos trouvées")
        for v in videos:
            print(f"    - {v['title'][:50]}... ({v['duration']})")
        return videos
    except Exception as e:
        print(f"  ❌ Erreur: {e}")
        return []


def download_video(url, output_dir="downloads"):
    """Télécharge une vidéo YouTube AVEC le son"""
    os.makedirs(output_dir, exist_ok=True)
    output_template = os.path.join(output_dir, "%(id)s.%(ext)s")

    # Supprimer les anciens fichiers
    for f in os.listdir(output_dir):
        try:
            os.remove(os.path.join(output_dir, f))
        except:
            pass

    # Commande qui garantit vidéo + audio
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "--merge-output-format", "mp4",
        "-o", output_template,
        "--no-playlist",
        url
    ]

    try:
        print(f"  ⬇️  Téléchargement...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        for f in os.listdir(output_dir):
            if f.endswith('.mp4') or f.endswith('.mkv') or f.endswith('.webm'):
                filepath = os.path.join(output_dir, f)
                print(f"    ✓ Téléchargé: {f}")
                return filepath

        return None
    except Exception as e:
        print(f"  ❌ Erreur: {e}")
        return None


def is_vertical_video(clip):
    """Détecte si la vidéo est déjà verticale (short/TikTok)"""
    w, h = clip.size
    ratio = w / h
    return ratio < 0.7  # 9:16 = 0.5625


def convert_to_tiktok(clip, zoom=1.1, crop_pos='center'):
    """Convertit au format TikTok 9:16 - Ne touche pas aux shorts"""
    TARGET_W, TARGET_H = 1080, 1920
    orig_w, orig_h = clip.size

    # Si c'est déjà un short/vertical, juste redimensionner
    if is_vertical_video(clip):
        print(f"    📱 Short détecté ({orig_w}x{orig_h}) - redimensionnement simple")
        return clip.resize((TARGET_W, TARGET_H))

    print(f"    🖥️ Vidéo horizontale ({orig_w}x{orig_h}) - crop + zoom {zoom}x")

    target_ratio = TARGET_W / TARGET_H

    # Zoom
    new_w, new_h = int(orig_w * zoom), int(orig_h * zoom)
    clip = clip.resize((new_w, new_h))

    # Crop
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
    """Ajoute du texte sur la vidéo"""
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

        # Contour noir
        for dx in range(-5, 6):
            for dy in range(-5, 6):
                draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, 255))
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))

        txt_clip = ImageClip(np.array(img), transparent=True).set_duration(clip.duration)
        return CompositeVideoClip([clip, txt_clip])
    except Exception as e:
        print(f"    ⚠ Erreur texte: {e}")
        return clip


def split_video(video_path, max_dur=60, font_path=None, title="Science", zoom=1.15, crop_pos='center'):
    """Découpe une vidéo en parties de max_dur secondes"""
    os.makedirs("output", exist_ok=True)
    print(f"\n🎬 Traitement: {os.path.basename(video_path)}")

    try:
        # Charger avec audio explicitement
        clip = VideoFileClip(video_path)
        total_dur = clip.duration
        has_audio = clip.audio is not None
        w, h = clip.size
        is_vertical = is_vertical_video(clip)

        print(
            f"  📊 Durée: {total_dur:.1f}s | {w}x{h} | Audio: {'✓' if has_audio else '✗'} | {'📱 Vertical' if is_vertical else '🖥️ Horizontal'}")

        num_parts = max(1, int(total_dur // max_dur) + (1 if total_dur % max_dur > 5 else 0))
        print(f"  📦 Parties: {num_parts}")

        outputs = []

        for i in range(num_parts):
            start = i * max_dur
            end = min((i + 1) * max_dur, total_dur)

            if end - start < 10 and i > 0:
                continue

            print(f"\n  🎞️ Part {i + 1}/{num_parts} ({start:.0f}s - {end:.0f}s)")

            # Extraire le segment avec audio
            segment = clip.subclip(start, end)
            segment_audio = segment.audio  # Sauvegarder l'audio

            # Convertir au format TikTok
            segment = convert_to_tiktok(segment, zoom, crop_pos)

            # Remettre l'audio après conversion
            if segment_audio is not None:
                segment = segment.set_audio(segment_audio)

            # Ajouter le texte
            overlay = f"{title} Part {i + 1}" if num_parts > 1 else title
            segment_with_text = add_text(segment, overlay, font_path)

            # Remettre l'audio après ajout du texte
            if segment_audio is not None:
                segment_with_text = segment_with_text.set_audio(segment_audio)

            safe_title = "".join(c for c in title if c.isalnum() or c in ' -_')[:25]
            filename = f"{safe_title}_part{i + 1:02d}.mp4" if num_parts > 1 else f"{safe_title}.mp4"
            output_path = os.path.join("output", filename)

            print(f"    💾 Export: {filename}")

            segment_with_text.write_videofile(
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
                segment_with_text.close()
                segment.close()
            except:
                pass

        clip.close()
        return outputs

    except Exception as e:
        print(f"  ❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return []


def upload_to_tiktok(video_path, title, username, description=None):
    """Upload une vidéo sur TikTok"""
    uploader_dir = "./vendor/TiktokAutoUploader"
    cookie_dir = os.path.join(uploader_dir, "CookiesDir")

    if not os.path.exists(uploader_dir):
        print(f"\n⚠ TiktokAutoUploader non trouvé dans {uploader_dir}")
        return False

    if not os.path.exists(video_path):
        print(f"\n❌ Vidéo non trouvée : {video_path}")
        return False

    print(f"\n📤 Upload: {os.path.basename(video_path)}")

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
            print(f"\n🔐 Connexion requise pour {username}...")
            login_command = [sys.executable, "cli.py", "login", "-n", username]
            return_code, output = run_command(login_command)
            if "Unnecessary login" not in output and "session already saved" not in output and return_code != 0:
                return False

        full_title = f"{title} {description}" if description else title
        upload_command = [sys.executable, "cli.py", "upload", "--user", username, "-v", video_path_abs, "-t",
                          full_title]
        return_code, output = run_command(upload_command)

        if return_code == 0:
            print(f"  ✅ Upload réussi !")
            return True
        else:
            print(f"  ❌ Échec")
            return False

    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        return False
    finally:
        os.chdir(original_dir)


def main():
    print("=" * 60)
    print("🔬 YOUTUBE SCIENCE → TIKTOK COMPILER")
    print("=" * 60)
    print(f"\n📋 Config:")
    print(f"  - Recherche: {CONFIG['search_query']}")
    print(f"  - Vidéos: {CONFIG['max_videos']} | Durée max: {CONFIG['max_duration_per_part']}s")
    print(f"  - Auto-upload TikTok: {'✅' if CONFIG['auto_upload'] else '❌'}")

    font = download_font()

    queries = [
        CONFIG['search_query'],
        CONFIG['search_query'] + " short",
        CONFIG['search_query'] + " viral"
    ]

    videos = []
    for q in queries:
        videos.extend(search_youtube(q, max_results=2))
        if len(videos) >= CONFIG['max_videos']:
            break

    videos = videos[:CONFIG['max_videos']]

    if not videos:
        print("\n❌ Aucune vidéo trouvée")
        return

    os.makedirs("downloads", exist_ok=True)
    all_outputs = []

    for idx, video in enumerate(videos, 1):
        print(f"\n{'=' * 60}")
        print(f"📹 [{idx}/{len(videos)}] {video['title'][:50]}...")
        print(f"   {video['url']}")
        print("=" * 60)

        path = download_video(video['url'])
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

    # Résumé
    print("\n" + "=" * 60)
    print("🎉 VIDÉOS CRÉÉES !")
    print("=" * 60)

    if all_outputs:
        print(f"\n📁 {len(all_outputs)} vidéo(s) dans 'output/':")
        total = 0
        for o in all_outputs:
            print(f"  ✓ {os.path.basename(o['path'])} ({o['duration']:.0f}s)")
            total += o['duration']
        print(f"\n📊 Durée totale: {total:.0f}s | Format: 1080x1920")

        if CONFIG['auto_upload']:
            print("\n" + "=" * 60)
            print("📤 UPLOAD TIKTOK")
            print("=" * 60)

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
                    print(
                        f"\n💡 Upload manuel: cd vendor/TiktokAutoUploader && python cli.py upload --user {CONFIG['tiktok_username']} -v ../../{o['path']}")
    else:
        print("\n⚠ Aucune vidéo créée")

    print("\n✅ TERMINÉ !")


if __name__ == "__main__":
    main()