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
from urllib.parse import urlparse
import subprocess
import sys

# Fix pour Pillow 10+ (ANTIALIAS a été supprimé)
import PIL

if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS


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
# 3b. Convertir vidéo au format TikTok (9:16) - VERSION AMÉLIORÉE
# -----------------------------------------------------
def convert_to_tiktok_format(clip, target_width=1080, target_height=1920, zoom_factor=1.1, crop_position='center'):
    """
    Convertit une vidéo au format TikTok (9:16 - vertical)
    Avec zoom intelligent et positionnement optimisé

    Args:
        clip: VideoFileClip à convertir
        target_width: Largeur cible (défaut: 1080)
        target_height: Hauteur cible (défaut: 1920)
        zoom_factor: Facteur de zoom (1.0 = pas de zoom, 1.1 = +10%, 1.2 = +20%)
        crop_position: Position du crop ('center', 'top', 'bottom')
    """
    # Dimensions actuelles
    original_width, original_height = clip.size

    # Calculer le ratio actuel et le ratio cible
    current_ratio = original_width / original_height
    target_ratio = target_width / target_height  # 9:16 = 0.5625

    # Appliquer le zoom
    zoomed_width = int(original_width * zoom_factor)
    zoomed_height = int(original_height * zoom_factor)

    # Resize avec zoom
    clip_zoomed = clip.resize((zoomed_width, zoomed_height))

    if current_ratio > target_ratio:
        # La vidéo est trop large : on va recadrer les côtés
        new_width = int(zoomed_height * target_ratio)
        x_center = zoomed_width / 2
        x1 = int(x_center - new_width / 2)

        # Position verticale selon crop_position
        if crop_position == 'top':
            y1 = 0
        elif crop_position == 'bottom':
            y1 = zoomed_height - zoomed_height
        else:  # center
            y1 = 0

        clip_cropped = clip_zoomed.crop(x1=x1, y1=y1, width=new_width, height=zoomed_height)
    else:
        # La vidéo est trop haute : on va recadrer en haut/bas
        new_height = int(zoomed_width / target_ratio)
        x1 = 0

        # Position verticale selon crop_position
        if crop_position == 'top':
            y1 = 0
        elif crop_position == 'bottom':
            y1 = zoomed_height - new_height
        else:  # center
            y_center = zoomed_height / 2
            y1 = int(y_center - new_height / 2)

        clip_cropped = clip_zoomed.crop(x1=x1, y1=y1, width=zoomed_width, height=new_height)

    # Redimensionner à la résolution TikTok exacte
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
        font_size = 60
        try:
            if font_path and os.path.exists(font_path):
                font = ImageFont.truetype(font_path, font_size)
                print(f"  ✓ Police chargée : {font_path}")
            else:
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

        # Dessiner le contour noir (stroke) - plus épais pour plus de visibilité
        stroke_width = 5
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
                      black_screen_duration=0.3, zoom_factor=1.1, crop_position='center'):
    """
    Construit la vidéo finale en concaténant les clips

    Args:
        zoom_factor: Facteur de zoom (1.0-1.2 recommandé)
        crop_position: Position du crop ('center', 'top', 'bottom')
    """
    if not clips_paths:
        print("❌ Aucun clip à traiter")
        return None

    loaded_clips = []
    total_duration = 0

    # Format TikTok
    TIKTOK_WIDTH = 1080
    TIKTOK_HEIGHT = 1920

    print(f"\n📹 Chargement et conversion des clips au format TikTok (9:16 - {TIKTOK_WIDTH}x{TIKTOK_HEIGHT})...")
    print(f"   🔍 Zoom: {zoom_factor}x | Position: {crop_position}")

    black_screens_time = 0

    for i, path in enumerate(clips_paths):
        effective_duration = total_duration + black_screens_time

        if effective_duration >= target_duration:
            break

        try:
            clip = VideoFileClip(path)

            # Conversion avec zoom intelligent
            clip_tiktok = convert_to_tiktok_format(
                clip,
                TIKTOK_WIDTH,
                TIKTOK_HEIGHT,
                zoom_factor=zoom_factor,
                crop_position=crop_position
            )

            remaining_time = target_duration - effective_duration

            if clip_tiktok.duration > remaining_time:
                clip_tiktok = clip_tiktok.subclip(0, remaining_time)

            loaded_clips.append(clip_tiktok)
            total_duration += clip_tiktok.duration

            if i < len(clips_paths) - 1:
                black_screens_time += black_screen_duration

            print(
                f"  ✓ Clip {i + 1}: {clip_tiktok.duration:.1f}s [TikTok {zoom_factor}x zoom] (total: {effective_duration + clip_tiktok.duration:.1f}s)")

        except Exception as e:
            print(f"  ✗ Erreur avec {path}: {e}")
            continue

    if not loaded_clips:
        print("❌ Aucune vidéo n'a pu être chargée")
        return None

    print(f"\n🔧 Assemblage de {len(loaded_clips)} clips avec écrans noirs de transition...")

    clips_with_transitions = []

    for i, clip in enumerate(loaded_clips):
        clips_with_transitions.append(clip)

        if i < len(loaded_clips) - 1:
            black_screen = ColorClip(
                size=(TIKTOK_WIDTH, TIKTOK_HEIGHT),
                color=(0, 0, 0),
                duration=black_screen_duration
            )
            clips_with_transitions.append(black_screen)
            print(f"  ⚫ Écran noir ajouté après le clip {i + 1} ({black_screen_duration}s)")

    final_video = concatenate_videoclips(clips_with_transitions, method="compose")

    print(f"  ✓ Durée totale avec transitions : {final_video.duration:.1f}s")
    print(f"  ✓ Format final : {final_video.size[0]}x{final_video.size[1]} (TikTok 9:16)")

    final_video = add_text_overlay(final_video, text, font_path=font_path)

    if intro_sound and os.path.exists(intro_sound):
        try:
            print("\n🎵 Ajout du son d'intro...")
            intro_audio = AudioFileClip(intro_sound)

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

    if transition_sound and os.path.exists(transition_sound):
        try:
            print("🎵 Ajout des sons de transition...")
            transition_audio = AudioFileClip(transition_sound)

            transition_times = []
            current_time = 0
            for i, clip in enumerate(loaded_clips[:-1]):
                current_time += clip.duration
                transition_times.append(current_time)
                current_time += black_screen_duration

            if final_video.audio and transition_times:
                from moviepy.audio.AudioClip import CompositeAudioClip
                audio_tracks = [final_video.audio]

                for t_time in transition_times:
                    trans_clip = transition_audio.volumex(0.8).set_start(t_time)
                    audio_tracks.append(trans_clip)

                final_audio = CompositeAudioClip(audio_tracks)
                final_video = final_video.set_audio(final_audio)
                print(f"  ✓ {len(transition_times)} sons de transition ajoutés")

        except Exception as e:
            print(f"  ⚠ Impossible d'ajouter les sons de transition : {e}")

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

    for clip in loaded_clips:
        clip.close()
    final_video.close()

    print(f"\n✅ Vidéo '{output_file}' créée avec succès !")
    print(f"   Format : {TIKTOK_WIDTH}x{TIKTOK_HEIGHT} (9:16 - TikTok/Shorts)")
    print(f"   Zoom : {zoom_factor}x")
    print(f"   Durée finale : {total_duration:.1f}s")
    print(f"   Nombre de clips : {len(loaded_clips)}")
    print(f"   Écrans noirs : {len(loaded_clips) - 1}")

    return output_file


# -----------------------------------------------------
# 6. Upload vers TikTok (version qui fonctionne)
# -----------------------------------------------------
def upload_to_tiktok(video_path, title, username, description=None):
    """
    Upload une vidéo sur TikTok en utilisant TiktokAutoUploader
    Version basée sur la méthode qui fonctionne
    """
    # Chemin vers le dossier TiktokAutoUploader
    uploader_dir = "./vendor/TiktokAutoUploader"
    cookie_dir = os.path.join(uploader_dir, "CookiesDir")

    if not os.path.exists(uploader_dir):
        print(f"\n⚠ TiktokAutoUploader non trouvé dans {uploader_dir}")
        print("💡 Assurez-vous d'avoir initialisé le submodule")
        return False

    if not os.path.exists(video_path):
        print(f"\n❌ Vidéo non trouvée : {video_path}")
        return False

    print("\n" + "=" * 60)
    print("📤 UPLOAD VERS TIKTOK")
    print("=" * 60)

    # Convertir le chemin de la vidéo en chemin absolu
    video_path_abs = os.path.abspath(video_path)

    # Sauvegarder le dossier actuel
    original_dir = os.getcwd()

    try:
        # Se déplacer dans le dossier TiktokAutoUploader
        os.chdir(uploader_dir)
        print(f"📁 Dossier de travail : {os.getcwd()}")

        # Fonction pour vérifier si le cookie existe
        def check_cookie_exists(cookie_name):
            if not os.path.exists(cookie_dir):
                return False
            for filename in os.listdir(cookie_dir):
                if cookie_name in filename:
                    print(f'✓ Cookie de {cookie_name} trouvé')
                    return True
            print(f'⚠ Cookie de {cookie_name} non trouvé')
            return False

        # Fonction pour exécuter une commande
        def run_command(command):
            print(f"🔧 Commande : {' '.join(command)}")
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            stdout_output = ""
            for stdout_line in iter(process.stdout.readline, ""):
                print(stdout_line, end="")
                stdout_output += stdout_line

            process.stdout.close()
            process.wait()

            stderr = process.stderr.read()
            if stderr:
                print(f"Sortie d'erreur : {stderr}")

            return process.returncode, stdout_output

        # Vérifier si le cookie existe, sinon faire le login
        if not check_cookie_exists(username):
            print(f"\n🔐 Connexion requise pour {username}...")
            print("⚠️  Une fenêtre Chrome va s'ouvrir pour la connexion TikTok")
            print("    Connecte-toi manuellement, puis le cookie sera sauvegardé.")

            login_command = [
                sys.executable,
                "cli.py",
                "login",
                "-n",
                username
            ]

            return_code, output = run_command(login_command)

            # Vérifier si la session est déjà sauvegardée (message normal)
            if "Unnecessary login" in output or "session already saved" in output:
                print(f"✓ Session {username} déjà active")
            elif return_code != 0:
                print(f"\n❌ Échec de la connexion")
                print("\n💡 Solution : Lance manuellement la connexion :")
                print(f"   cd vendor/TiktokAutoUploader")
                print(f"   python cli.py login -n {username}")
                print("\n   Puis relance le script principal.")
                return False
            else:
                print(f"✓ Connexion établie pour {username}")
        else:
            print(f"✓ Cookie trouvé pour {username}")

        # Préparer le titre complet
        full_title = title
        if description:
            full_title = f"{title} - {description}"

        # Commande d'upload
        print(f"\n📤 Upload de la vidéo...")
        upload_command = [
            sys.executable,
            "cli.py",
            "upload",
            "--user",
            username,
            "-v",
            video_path_abs,
            "-t",
            full_title
        ]

        return_code, output = run_command(upload_command)

        if return_code == 0:
            print("\n✅ Upload réussi !")
            return True
        else:
            print(f"\n❌ Échec de l'upload (code: {return_code})")
            return False

    except Exception as e:
        print(f"\n❌ Erreur lors de l'upload : {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Retourner au dossier original
        os.chdir(original_dir)
        print(f"📁 Retour au dossier : {os.getcwd()}")


# -----------------------------------------------------
# MAIN
# -----------------------------------------------------
def main():
    # Configuration
    twitch_url = "https://m.twitch.tv/anyme023/clips/?featured=false&range=24hr"

    # Configuration TikTok
    TIKTOK_USERNAME = 'dvlad2'
    AUTO_UPLOAD = True  # Upload automatique activé

    # ⚙️ PARAMÈTRES DE ZOOM ET CROP
    ZOOM_FACTOR = 1.1  # 1.0 = pas de zoom, 1.1 = +10%, 1.15 = +15%, 1.2 = +20%
    CROP_POSITION = 'center'  # 'center', 'top', ou 'bottom'

    # Extraire le nom du streamer depuis l'URL
    streamer_name = extract_streamer_name(twitch_url)
    text_overlay = f"{streamer_name} core >>>"

    # Titre et description TikTok
    tiktok_title = f"{streamer_name.capitalize()} core >>"
    tiktok_tags = f"#{streamer_name.lower()} #viral #fyp #foryou #foryoupage @{streamer_name.capitalize()}"

    print("=" * 60)
    print("🎬 TWITCH CLIP COMPILER - FORMAT TIKTOK OPTIMISÉ")
    print("=" * 60)
    print(f"Streamer : {streamer_name}")
    print(f"URL : {twitch_url}")
    print(f"Format : 1080x1920 (9:16 - TikTok/YouTube Shorts)")
    print(f"Zoom : {ZOOM_FACTOR}x")
    print(f"Position : {CROP_POSITION}")
    print(f"Auto-upload : {'✅ Activé' if AUTO_UPLOAD else '❌ Désactivé'}")
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
    output_video = build_final_video(
        clips_paths=clips_local,
        intro_sound="intro.mp3",
        transition_sound="transition.mp3",
        text=text_overlay,
        target_duration=60,
        font_path=font_path,
        black_screen_duration=0.3,
        zoom_factor=ZOOM_FACTOR,
        crop_position=CROP_POSITION
    )

    if not output_video:
        print("\n❌ Échec de la création de la vidéo")
        return

    print("\n" + "=" * 60)
    print("🎉 VIDÉO CRÉÉE !")
    print("=" * 60)

    # Étape 3b : Ajouter une musique triste tendance par-dessus
    try:
        from music_helper import mix_background_music
        with_music = output_video.replace(".mp4", "_music.mp4")
        mixed = mix_background_music(
            video_path=output_video,
            output_path=with_music,
            vibe="tendance",
            music_volume=0.55,
            duck_original=0.4,
        )
        if mixed:
            output_video = mixed
    except Exception as e:
        print(f"  ⚠ Impossible d'ajouter une musique : {e}")

    # Étape 4 : Upload vers TikTok
    if AUTO_UPLOAD:
        upload_success = upload_to_tiktok(
            video_path=output_video,
            title=tiktok_title,
            username=TIKTOK_USERNAME,
            description=tiktok_tags
        )

        if upload_success:
            print("\n🎊 Vidéo uploadée sur TikTok avec succès !")
        else:
            print("\n⚠ Upload échoué")
            print("\n💡 Essaye l'upload manuel :")
            print(f"   cd vendor/TiktokAutoUploader")
            print(
                f"   python cli.py upload --user {TIKTOK_USERNAME} -v ../../{output_video} -t \"{tiktok_title} - {tiktok_tags}\"")
    else:
        print("\n💡 Pour uploader sur TikTok :")
        print(f"   cd vendor/TiktokAutoUploader")
        print(
            f"   python cli.py upload --user {TIKTOK_USERNAME} -v ../../{output_video} -t \"{tiktok_title} - {tiktok_tags}\"")

    print("\n" + "=" * 60)
    print("🎥 Terminé !")
    print(f"📁 Vidéo : {output_video}")
    print("=" * 60)

    # Étape 5 : Nettoyage - Supprimer les clips téléchargés
    print("\n🧹 Nettoyage des clips téléchargés...")
    try:
        clips_deleted = 0
        for clip_file in clips_local:
            if os.path.exists(clip_file):
                os.remove(clip_file)
                clips_deleted += 1
        print(f"✓ {clips_deleted} clips supprimés")
    except Exception as e:
        print(f"⚠ Erreur lors du nettoyage : {e}")

    print("\n" + "=" * 60)
    print("✅ PROCESSUS TERMINÉ !")
    print("=" * 60)


if __name__ == "__main__":
    main()