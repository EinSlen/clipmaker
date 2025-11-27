import os
import json
import requests
from bs4 import BeautifulSoup
from moviepy.editor import (
    VideoFileClip, concatenate_videoclips,
    CompositeVideoClip, AudioFileClip, ColorClip
)
from tqdm import tqdm
import streamlink
import re
from urllib.parse import urlparse

# Fix pour Pillow 10+ (ANTIALIAS a été supprimé)
import PIL

if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS


# Pour l'upload vers Tiktok on utilise une lib extérieur
# https://github.com/makiisthenes/TiktokAutoUploader


# -----------------------------------------------------
# 0. Télécharger une police si nécessaire
# -----------------------------------------------------
def download_font():
    """Télécharge une police gratuite si elle n'existe pas"""
    font_path = "Bangers-Regular.ttf"

    if os.path.exists(font_path):
        print(f"  ✓ Police déjà téléchargée : {font_path}")
        return font_path

    try:
        print("  📥 Téléchargement de la police Bangers...")
        # Police gratuite de Google Fonts
        font_url = "https://github.com/google/fonts/raw/main/ofl/bangers/Bangers-Regular.ttf"
        response = requests.get(font_url, timeout=10)
        response.raise_for_status()

        with open(font_path, 'wb') as f:
            f.write(response.content)

        print(f"  ✓ Police téléchargée : {font_path}")
        return font_path
    except Exception as e:
        print(f"  ⚠ Erreur lors du téléchargement de la police : {e}")
        return None


# -----------------------------------------------------
# 1. Extraire le nom du streamer depuis l'URL
# -----------------------------------------------------
def extract_streamer_name(url):
    """Extrait le nom du streamer depuis l'URL Twitch"""
    parsed = urlparse(url)
    path_parts = parsed.path.strip('/').split('/')
    if path_parts:
        return path_parts[0]
    return "Streamer"


# -----------------------------------------------------
# 2. Extraire les liens de clips depuis la page Twitch
# -----------------------------------------------------
def extract_clips_from_mobile(url):
    """Récupère les URLs des clips depuis la page Twitch mobile"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15'
    }
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    clips = []
    scripts = soup.find_all("script", type="application/ld+json")
    for s in scripts:
        if not s.string:
            continue
        try:
            data = json.loads(s.string)
            graph = data.get("@graph", [])
            for item in graph:
                if item.get("@type") == "ItemList":
                    for elem in item.get("itemListElement", []):
                        if elem.get("@type") == "VideoObject":
                            clip_url = elem.get("url")
                            if clip_url:
                                clips.append(clip_url)
        except json.JSONDecodeError:
            continue

    return list(set(clips))


# -----------------------------------------------------
# 3. Télécharger un clip Twitch avec Streamlink
# -----------------------------------------------------
def download_clip_streamlink(url, filename):
    """Télécharge un clip Twitch en utilisant streamlink"""
    try:
        streams = streamlink.streams(url)
        if "best" not in streams:
            raise ValueError(f"Aucun stream disponible pour {url}")
        stream = streams["best"]
        with open(filename, "wb") as f:
            fd = stream.open()
            for chunk in iter(lambda: fd.read(1024 * 64), b""):
                f.write(chunk)
        return filename
    except Exception as e:
        raise Exception(f"Erreur lors du téléchargement : {e}")


# -----------------------------------------------------
# 3b. Convertir vidéo au format TikTok (9:16)
# -----------------------------------------------------
def convert_to_tiktok_format(clip, target_width=1080, target_height=1920):
    """
    Convertit une vidéo au format TikTok (9:16 - vertical)
    Zoom et recadrage au centre
    """
    # Dimensions actuelles
    original_width, original_height = clip.size

    # Calculer le ratio actuel et le ratio cible
    current_ratio = original_width / original_height
    target_ratio = target_width / target_height  # 9:16 = 0.5625

    if current_ratio > target_ratio:
        # La vidéo est trop large : on va recadrer les côtés
        new_width = int(original_height * target_ratio)
        x_center = original_width / 2
        x1 = int(x_center - new_width / 2)
        y1 = 0
        clip_cropped = clip.crop(x1=x1, y1=y1, width=new_width, height=original_height)
    else:
        # La vidéo est trop haute : on va recadrer en haut/bas
        new_height = int(original_width / target_ratio)
        y_center = original_height / 2
        x1 = 0
        y1 = int(y_center - new_height / 2)
        clip_cropped = clip.crop(x1=x1, y1=y1, width=original_width, height=new_height)

    # Redimensionner à la résolution TikTok
    clip_resized = clip_cropped.resize((target_width, target_height))

    return clip_resized


# -----------------------------------------------------
# 4. Ajouter du texte sur la vidéo (avec Pillow/PIL)
# -----------------------------------------------------
def add_text_overlay(video_clip, text, font_path=None):
    """Ajoute un texte au centre de la vidéo pendant toute sa durée"""
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np
    from moviepy.video.VideoClip import ImageClip

    print(f"📝 Ajout du texte '{text}' avec Pillow...")

    try:
        # Dimensions de la vidéo
        width, height = video_clip.size

        # Créer une image transparente
        img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Charger la police - taille adaptée au format vertical
        font_size = 60  # Un peu plus grand pour le format vertical
        try:
            if font_path and os.path.exists(font_path):
                font = ImageFont.truetype(font_path, font_size)
                print(f"  ✓ Police chargée : {font_path}")
            else:
                # Fallback vers la police par défaut
                font = ImageFont.load_default()
                print("  ℹ Utilisation de la police par défaut")
        except Exception as e:
            font = ImageFont.load_default()
            print(f"  ℹ Utilisation de la police par défaut ({e})")

        # Obtenir la taille du texte
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Position centrée
        x = (width - text_width) // 2
        y = (height - text_height) // 2

        # Dessiner le contour noir (stroke)
        stroke_width = 4
        for adj_x in range(-stroke_width, stroke_width + 1):
            for adj_y in range(-stroke_width, stroke_width + 1):
                draw.text((x + adj_x, y + adj_y), text, font=font, fill=(0, 0, 0, 255))

        # Dessiner le texte blanc par-dessus
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))

        # Convertir l'image PIL en array numpy
        img_array = np.array(img)

        # Créer un clip image à partir de l'array
        txt_clip = ImageClip(img_array, transparent=True).set_duration(video_clip.duration).set_start(0)

        print(f"  ✓ Texte créé avec succès (durée: {video_clip.duration:.1f}s)")

        # Superposer le texte sur la vidéo
        return CompositeVideoClip([video_clip, txt_clip])

    except Exception as e:
        print(f"  ⚠ Erreur lors de la création du texte : {e}")
        print("  💡 La vidéo sera générée SANS texte")
        import traceback
        traceback.print_exc()
        return video_clip


# -----------------------------------------------------
# 5. Construire la vidéo finale avec transitions
# -----------------------------------------------------
def build_final_video(clips_paths, intro_sound=None, transition_sound=None,
                      text="Streamer >>>", target_duration=60, font_path=None,
                      black_screen_duration=0.3):
    """
    Construit la vidéo finale en concaténant les clips avec :
    - Format TikTok (9:16 vertical - 1080x1920)
    - Image noire entre chaque clip (transition)
    - Son au début
    - Sons de transition entre chaque clip
    - Texte au centre pendant toute la durée
    - Durée totale d'environ 1 minute
    """
    if not clips_paths:
        print("❌ Aucun clip à traiter")
        return

    loaded_clips = []
    total_duration = 0

    # Format TikTok
    TIKTOK_WIDTH = 1080
    TIKTOK_HEIGHT = 1920

    print(f"\n📹 Chargement et conversion des clips au format TikTok (9:16 - {TIKTOK_WIDTH}x{TIKTOK_HEIGHT})...")

    # Charger les clips jusqu'à atteindre la durée cible
    black_screens_time = 0

    for i, path in enumerate(clips_paths):
        # Calculer la durée totale incluant les écrans noirs
        effective_duration = total_duration + black_screens_time

        if effective_duration >= target_duration:
            break

        try:
            clip = VideoFileClip(path)

            # Convertir au format TikTok
            clip_tiktok = convert_to_tiktok_format(clip, TIKTOK_WIDTH, TIKTOK_HEIGHT)

            remaining_time = target_duration - effective_duration

            if clip_tiktok.duration > remaining_time:
                # Couper le clip pour ne pas dépasser la durée cible
                clip_tiktok = clip_tiktok.subclip(0, remaining_time)

            loaded_clips.append(clip_tiktok)
            total_duration += clip_tiktok.duration

            # Ajouter le temps de l'écran noir (sauf pour le dernier clip)
            if i < len(clips_paths) - 1:
                black_screens_time += black_screen_duration

            print(
                f"  ✓ Clip {i + 1}: {clip_tiktok.duration:.1f}s [Format TikTok] (total: {effective_duration + clip_tiktok.duration:.1f}s)")

        except Exception as e:
            print(f"  ✗ Erreur avec {path}: {e}")
            import traceback
            traceback.print_exc()
            continue

    if not loaded_clips:
        print("❌ Aucune vidéo n'a pu être chargée")
        return

    print(f"\n🔧 Assemblage de {len(loaded_clips)} clips avec écrans noirs de transition...")

    # Créer la liste finale avec les clips et les écrans noirs
    clips_with_transitions = []

    for i, clip in enumerate(loaded_clips):
        clips_with_transitions.append(clip)

        # Ajouter un écran noir après chaque clip sauf le dernier
        if i < len(loaded_clips) - 1:
            # Créer un écran noir au format TikTok
            black_screen = ColorClip(
                size=(TIKTOK_WIDTH, TIKTOK_HEIGHT),
                color=(0, 0, 0),
                duration=black_screen_duration
            )
            clips_with_transitions.append(black_screen)
            print(f"  ⚫ Écran noir ajouté après le clip {i + 1} ({black_screen_duration}s)")

    # Concaténer tous les clips avec les écrans noirs
    final_video = concatenate_videoclips(clips_with_transitions, method="compose")

    print(f"  ✓ Durée totale avec transitions : {final_video.duration:.1f}s")
    print(f"  ✓ Format final : {final_video.size[0]}x{final_video.size[1]} (TikTok 9:16)")

    # Ajouter le texte overlay pendant TOUTE la durée
    final_video = add_text_overlay(final_video, text, font_path=font_path)

    # Ajouter le son de début (intro)
    if intro_sound and os.path.exists(intro_sound):
        try:
            print("\n🎵 Ajout du son d'intro...")
            intro_audio = AudioFileClip(intro_sound)

            # Si la vidéo a déjà de l'audio, on mixe
            if final_video.audio:
                from moviepy.audio.AudioClip import CompositeAudioClip
                intro_audio = intro_audio.set_duration(min(intro_audio.duration, final_video.duration))
                final_audio = CompositeAudioClip([
                    final_video.audio,
                    intro_audio.volumex(0.4).audio_fadeout(1)
                ])
                final_video = final_video.set_audio(final_audio)
            else:
                final_video = final_video.set_audio(intro_audio.set_duration(final_video.duration))
            print("  ✓ Son d'intro ajouté")
        except Exception as e:
            print(f"  ⚠ Impossible d'ajouter le son d'intro : {e}")

    # Ajouter les sons de transition entre clips
    if transition_sound and os.path.exists(transition_sound):
        try:
            print("🎵 Ajout des sons de transition...")
            transition_audio = AudioFileClip(transition_sound)

            # Calculer les positions de transition (aux moments des écrans noirs)
            transition_times = []
            current_time = 0
            for i, clip in enumerate(loaded_clips[:-1]):
                current_time += clip.duration
                transition_times.append(current_time)
                current_time += black_screen_duration

            # Mixer les sons de transition avec l'audio existant
            if final_video.audio and transition_times:
                from moviepy.audio.AudioClip import CompositeAudioClip
                audio_tracks = [final_video.audio]

                for t_time in transition_times:
                    trans_clip = transition_audio.volumex(0.5).set_start(t_time)
                    audio_tracks.append(trans_clip)

                final_audio = CompositeAudioClip(audio_tracks)
                final_video = final_video.set_audio(final_audio)
                print(f"  ✓ {len(transition_times)} sons de transition ajoutés")

        except Exception as e:
            print(f"  ⚠ Impossible d'ajouter les sons de transition : {e}")

    # Export de la vidéo finale
    output_file = "final_compilation_tiktok.mp4"
    print(f"\n💾 Export de la vidéo finale vers '{output_file}'...")
    final_video.write_videofile(
        output_file,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        temp_audiofile="temp-audio.m4a",
        remove_temp=True,
        threads=4,
        preset='medium'
    )

    # Nettoyage
    for clip in loaded_clips:
        clip.close()
    final_video.close()

    print(f"\n✅ Vidéo '{output_file}' créée avec succès !")
    print(f"   Format : {TIKTOK_WIDTH}x{TIKTOK_HEIGHT} (9:16 - TikTok/Shorts)")
    print(f"   Durée finale : {total_duration:.1f}s")
    print(f"   Nombre de clips : {len(loaded_clips)}")
    print(f"   Écrans noirs : {len(loaded_clips) - 1}")


# -----------------------------------------------------
# MAIN
# -----------------------------------------------------
def main():
    # Configuration
    twitch_url = "https://m.twitch.tv/anyme023/clips/?featured=true&range=all"

    # Extraire le nom du streamer depuis l'URL
    streamer_name = extract_streamer_name(twitch_url)
    text_overlay = f"{streamer_name} core >>>"

    print("=" * 60)
    print("🎬 TWITCH CLIP COMPILER - FORMAT TIKTOK")
    print("=" * 60)
    print(f"Streamer : {streamer_name}")
    print(f"URL : {twitch_url}")
    print(f"Format : 1080x1920 (9:16 - TikTok/YouTube Shorts)")
    print("=" * 60)

    # Télécharger la police
    print("\n🔤 Préparation de la police...")
    font_path = download_font()

    # Étape 1 : Extraction des clips
    print("\n📥 Extraction des clips depuis Twitch...")
    try:
        links = extract_clips_from_mobile(twitch_url)
        print(f"✓ {len(links)} clips trouvés")
    except Exception as e:
        print(f"❌ Erreur lors de l'extraction : {e}")
        return

    if not links:
        print("❌ Aucun clip trouvé. Vérifiez l'URL.")
        return

    # Créer le dossier pour les clips
    os.makedirs("clips", exist_ok=True)
    clips_local = []

    # Étape 2 : Téléchargement des clips
    print(f"\n⬇️  Téléchargement des clips...")
    for i, url in enumerate(tqdm(links[:20], desc="Téléchargement"), 1):
        filename = f"clips/clip_{i:03d}.mp4"
        try:
            download_clip_streamlink(url, filename)
            clips_local.append(filename)
        except Exception as e:
            print(f"\n  ⚠ Erreur avec le clip {i} : {e}")
            continue

    print(f"\n✓ {len(clips_local)} clips téléchargés avec succès")

    if not clips_local:
        print("❌ Aucun clip n'a pu être téléchargé")
        return

    # Étape 3 : Création de la vidéo finale
    print("\n" + "=" * 60)
    build_final_video(
        clips_paths=clips_local,
        intro_sound="intro.mp3",
        transition_sound="transition.mp3",
        text=text_overlay,
        target_duration=60,
        font_path=font_path,
        black_screen_duration=0.3
    )

    print("\n" + "=" * 60)
    print("🎉 TERMINÉ !")
    print("🎥 Ta vidéo est prête pour TikTok/YouTube Shorts !")
    print("=" * 60)


if __name__ == "__main__":
    main()