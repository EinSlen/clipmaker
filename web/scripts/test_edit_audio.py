import hashlib
import importlib.util
import io
import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import textwrap
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from datetime import date, timedelta

import edit_audio as edit


class EditAudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"CLIPMAKER_EDIT_AUDIO_DIR": str(self.root)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.clips = []

    def add(self, mood="sad", mix="premixed", frequency=440):
        pcm = b''.join(struct.pack('<hh', int(5000 * math.sin(i * frequency * math.tau / 48000)),
                                 int(3000 * math.sin(i * (frequency + 50) * math.tau / 48000))) for i in range(12 * 48000))
        path = self.root / "fixture.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
            wav.writeframes(pcm)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        path.rename(self.root / f"{digest}.wav")
        clip = {"id": digest, "title": "Technical test signal, not real speech", "mood": mood, "mix": mix,
                "kind": "spoken", "language": "en", "duration": 12, "active": True,
                "rights": "original", "speechReviewed": True, "rightsConfirmed": True,
                "credit": "Synthetic test only", "source": "unit test", "rightsEvidence": "unit test"}
        self.clips.append(clip)
        self.save()
        return clip

    def save(self):
        (self.root / "catalog.json").write_text(json.dumps({"clips": self.clips}), encoding='utf-8')

    def test_empty_library_does_not_select_a_song(self):
        self.save()
        with self.assertRaisesRegex(ValueError, 'Aucune voix'):
            edit.select_clip(1, 'edit-sad')

    def test_cloud_client_identifies_itself_without_changing_authentication_or_redirect_safety(self):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = b'{}'
        with patch.dict(os.environ, {'CLIPMAKER_UPLOAD_TOKEN': 'test-only-token'}), patch.object(edit, 'build_opener', return_value=opener) as factory:
            for suffix, payload in [('/select', {'profile': 'edit-sad'}), ('/' + 'a' * 64, None)]:
                self.assertEqual(edit.cloud(suffix, payload), b'{}')
                request = opener.open.call_args.args[0]
                self.assertEqual(request.get_header('User-agent'), 'ClipMaker/1.0 (+https://github.com/EinSlen/clipmaker)')
                self.assertEqual(request.get_header('Authorization'), 'Bearer test-only-token')
                self.assertNotIn('test-only-token', request.full_url)
                self.assertIsInstance(factory.call_args.args[0], edit.NoRedirect)

    def test_non_json_cloud_denial_reports_status_without_echoing_response_body(self):
        opener = MagicMock()
        opener.open.side_effect = HTTPError(edit.BASE, 403, 'Forbidden', {}, io.BytesIO(b'edge denied; not a JSON API response'))
        with patch.dict(os.environ, {'CLIPMAKER_UPLOAD_TOKEN': 'test-only-token'}), patch.object(edit, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(ValueError, 'HTTP 403') as caught:
                edit.cloud('/select', {})
            self.assertNotIn('edge denied', str(caught.exception))
            self.assertEqual(opener.open.call_count, 1, 'do not repeatedly retry an authentication/edge refusal')

    def test_selection_pins_retry_and_refuses_a_disabled_voice(self):
        first = self.add()
        selected = edit.select_clip(1, 'edit-sad', '2026-08-31', 'one')
        self.add(frequency=900)
        self.assertEqual(edit.select_clip(88, 'edit-sad', '2026-08-31', 'one'), selected)
        first['active'] = False
        self.save()
        with self.assertRaisesRegex(ValueError, 'désactivé'):
            edit.select_clip(1, 'edit-sad', '2026-08-31', 'one')

    def selection_pool(self):
        # Metadata-only fixtures: selection tests do not claim these are audio.
        baseline = self.add()
        self.clips = [{**baseline, 'id': hashlib.sha256(f'selection-fixture-{i}'.encode()).hexdigest()}
                      for i in range(4)]
        self.save()

    def test_daily_rotation_uses_the_whole_mood_pool_and_preserves_retries(self):
        self.selection_pool()
        start = date(2026, 9, 1)
        selected = []
        for index in range(12):
            day = (start + timedelta(days=index)).isoformat()
            clip = edit.select_clip(index, 'edit-sad', day, 'softbody-dvlad')
            selected.append(clip['id'])
            self.assertEqual(clip, edit.select_clip(index + 9000, 'edit-sad', day, 'softbody-dvlad'))
            self.assertEqual(clip['mood'], 'sad')
        for offset in (0, 4, 8):
            self.assertEqual(len(set(selected[offset:offset + 4])), 4)
        self.assertTrue(all(first != second for first, second in zip(selected, selected[1:])))

    def test_dated_manual_previews_get_seed_specific_pins_without_changing_daily_keys(self):
        self.selection_pool()
        manual = [edit.select_clip(seed, 'edit-sad', '2026-09-01', 'manual-3d') for seed in range(8)]
        self.assertEqual(len({clip['selectionKey'] for clip in manual}), 8)
        self.assertEqual(len({clip['id'] for clip in manual[:4]}), 4)
        self.clips.reverse()
        self.save()
        for seed, expected in enumerate(manual):
            self.assertEqual(edit.select_clip(seed, 'edit-sad', '2026-09-01', 'manual-3d'), expected)
            self.assertEqual(edit.select_clip(seed, 'edit-sad', '2026-09-02', 'manual-3d'), expected)
        daily = edit.select_clip(1, 'edit-sad', '2026-09-01', 'softbody-dvlad')
        self.assertEqual(daily['selectionKey'], 'edit-selection-v1:softbody-dvlad:2026-09-01:edit-sad')

    def test_cloud_manual_preview_uses_a_seed_namespace_but_daily_retry_does_not(self):
        clip = self.add()
        with patch.dict(os.environ, {'CLIPMAKER_EDIT_AUDIO_DIR': ''}), patch.object(edit, 'cloud', return_value=json.dumps({'clip': clip}).encode()) as request:
            for seed in (910103, 910104, 910103):
                edit.select_clip(seed, 'edit-sad', '2026-09-01', 'manual-3d')
            previews = [call.args[1]['channel'] for call in request.call_args_list]
            self.assertEqual(previews, ['preview-910103', 'preview-910104', 'preview-910103'])
            self.assertTrue(all(call.args[1]['date'] == '1970-01-01' for call in request.call_args_list))
            edit.select_clip(910103, 'edit-sad', '2026-09-02', 'manual-3d')
            self.assertEqual(request.call_args.args[1], request.call_args_list[0].args[1])
            request.reset_mock()
            for seed in (1, 999):
                edit.select_clip(seed, 'edit-sad', '2026-09-01', 'softbody-dvlad')
            self.assertEqual([call.args[1]['channel'] for call in request.call_args_list], ['softbody-dvlad'] * 2)
            self.assertTrue(all(call.args[1]['date'] == '2026-09-01' for call in request.call_args_list))

    def test_rejects_wrong_mood_non_speech_and_unconfirmed_rights(self):
        clip = self.add()
        for field, value in [('kind', 'song'), ('language', 'fr'), ('rightsConfirmed', False),
                             ('speechReviewed', False), ('duration', 30), ('duration', float('nan')),
                             ('id', '../secret'), ('mix', 'random'), ('sha256', 'a' * 64)]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                edit.validate_clip({**clip, field: value}, 'edit-sad')
        with self.assertRaises(ValueError):
            edit.validate_clip(clip, 'edit-revenge')

    def test_integrity_failure_is_not_a_fallback(self):
        clip = self.add()
        (self.root / f"{clip['id']}.wav").write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            edit.fetch_clip(clip)

    def test_premixed_audio_keeps_stereo_and_never_repeats_after_the_phrase(self):
        self.add()
        output = self.root / 'mix.wav'
        def no_bed(*args):
            self.fail('A premixed edit must not receive a second music bed')
        metadata = edit.prepare_edit_soundtrack(30, output, 1, 'edit-sad', synth_bed=no_bed)
        with wave.open(str(output), 'rb') as wav:
            self.assertEqual((wav.getnchannels(), wav.getframerate(), wav.getnframes()), (2, 48000, 1440000))
            wav.setpos(48000)
            signal = struct.unpack('<' + 'h' * 4000, wav.readframes(2000))
            self.assertTrue(any(signal))
            self.assertNotEqual(signal[::2], signal[1::2])
            wav.setpos(14 * 48000)
            self.assertFalse(any(wav.readframes(16 * 48000)), 'The speech must not loop')
        self.assertEqual(metadata['music_mode'], 'spoken-edit')
        self.assertFalse(metadata['music_added_bed'])
        self.assertFalse(metadata['music_looped'])
        self.assertEqual(metadata['music_excerpt_start'], 0)
        self.assertEqual(metadata['music_excerpt_duration'], 12)

    def test_voice_only_adds_ducked_bed_with_complete_output(self):
        clip = self.add(mix='voice-only')
        def bed(duration, target, seed):
            with wave.open(str(target), 'wb') as wav:
                wav.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
                wav.writeframes(struct.pack('<hh', 300, 300) * int(duration * 48000))
        output = self.root / 'voice-and-bed.wav'
        result = edit.prepare_edit_soundtrack(30, output, 1, 'edit-auto', synth_bed=bed)
        self.assertTrue(result['music_added_bed'])
        self.assertEqual(result['music_source_sha256'], clip['id'])
        self.assertIn('sidechaincompress', edit.mix_filter(30, False))
        self.assertNotIn('sidechaincompress', edit.mix_filter(30, True))
        self.assertNotIn('aloop', edit.mix_filter(30, False))

    def test_workflow_preflights_audio_before_blender_and_pins_the_final_clip(self):
        root = Path(__file__).resolve().parents[2]
        workflow = (root / '.github/workflows/soft-body-artifact.yml').read_text(encoding='utf-8')
        plan = workflow.split('  prepare:')[0]
        self.assertIn('select_clip(channel["seed"]', plan)
        self.assertIn('fetch_clip(clip)', plan)
        self.assertIn('DAILY_EDIT_CLIP_ID', workflow)
        self.assertIn('--env CLIPMAKER_UPLOAD_TOKEN', workflow)
        self.assertIn('assertEditAudioQuality', workflow)

    def test_actual_github_matrix_refuses_empty_audio_and_carries_the_selected_clip(self):
        root = Path(__file__).resolve().parents[2]
        workflow = (root / '.github/workflows/soft-body-artifact.yml').read_text(encoding='utf-8')
        matrix = textwrap.dedent(workflow.split("python3 - <<'PY'", 1)[1].split('\n          PY', 1)[0])
        # Fix only the clock for this audio-planning test. The workflow keeps
        # Paris time; the test is independent of today and Windows tzdata.
        self.assertIn('datetime.now(ZoneInfo("Europe/Paris"))', matrix)
        matrix = matrix.replace('datetime.now(ZoneInfo("Europe/Paris"))', 'datetime.fromisoformat("2026-08-31T12:00:00+02:00")')
        output = self.root / 'github-output'
        environment = {**os.environ, 'GITHUB_EVENT_NAME': 'workflow_dispatch', 'FRAME_COUNT': '900',
                       'GITHUB_OUTPUT': str(output), 'GITHUB_STEP_SUMMARY': str(self.root / 'summary'),
                       'MANUAL_MUSIC_PROFILE': 'edit-sad', 'USE_CLOUD_CONFIG': 'false', 'PLAN_ONLY': 'true'}
        self.save()
        failed = subprocess.run([sys.executable, '-c', matrix], cwd=root, env=environment, capture_output=True)
        self.assertNotEqual(failed.returncode, 0)
        self.assertFalse(output.exists())
        clip = self.add()
        valid = subprocess.run([sys.executable, '-c', matrix], cwd=root, env=environment, capture_output=True)
        self.assertEqual(valid.returncode, 0, valid.stderr.decode(errors='replace'))
        values = dict(line.split('=', 1) for line in output.read_text().splitlines())
        self.assertEqual(values['render_enabled'], 'false')
        channel = json.loads(values['channels'])['include'][0]
        self.assertEqual(channel['edit_clip_id'], clip['id'])

    def test_production_mux_has_900_frames_and_30_seconds_of_stereo_aac(self):
        self.add()
        music = self.root / 'spoken-mix.wav'
        edit.prepare_edit_soundtrack(30, music, 1, 'edit-sad', synth_bed=lambda *args: self.fail('Unexpected extra music'))
        spec = importlib.util.spec_from_file_location('edit_test_renderer', Path(__file__).with_name('render-premium-3d.py'))
        renderer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(renderer)
        silent, video = self.root / 'silent.mp4', self.root / 'test.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=s=16x16:r=30:d=30',
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-an', str(silent)], check=True)
        effects = self.root / 'effects.wav'
        with wave.open(str(effects), 'wb') as wav:
            wav.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
            wav.writeframes(b'\0' * 30 * 48000 * 4)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(silent), '-i', str(effects), '-i', str(music),
                        '-filter_complex', renderer.build_continuous_audio_filter(.58, True, True),
                        '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-ar', '48000',
                        '-b:a', '160k', '-shortest', str(video)], check=True)
        probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(video)]))
        vid, aud = probe['streams']
        self.assertEqual((vid['nb_frames'], vid['avg_frame_rate']), ('900', '30/1'))
        self.assertEqual((aud['codec_name'], aud['sample_rate'], aud['channels']), ('aac', '48000', 2))
        self.assertAlmostEqual(float(aud['duration']), 30, delta=.04)
        self.assertAlmostEqual(float(probe['format']['duration']), 30, delta=.04)

    def test_local_renderer_refuses_an_external_song_or_muted_voice_before_blender(self):
        spec = importlib.util.spec_from_file_location('edit_test_renderer', Path(__file__).with_name('render-premium-3d.py'))
        renderer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(renderer)
        for music, volume in [('other-song.wav', .58), (None, 0)]:
            with self.assertRaisesRegex(ValueError, 'cannot be replaced'):
                renderer.render(SimpleNamespace(music_profile='edit-sad', music=music, music_volume=volume))


if __name__ == '__main__':
    unittest.main()
