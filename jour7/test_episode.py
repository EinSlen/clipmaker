import json
import tempfile
import unittest
from pathlib import Path

from episode import ROOT, captions, chunks, layout, paper_edges, trim_paper


def spoken(lines):
    """Word boundaries the way Edge TTS reports them: no punctuation, 0.3 s each."""
    words, clock = [], 0.0
    for line in lines:
        for token in line.split():
            text = token.strip(".,;:!?")
            if text:
                words.append({"text": text, "start": clock, "end": clock + 0.25})
                clock += 0.3
        clock += 0.5
    return words


LINES = [
    "Voilà ce qui arrive quand tu dors peu.",
    "Jour un. Tu tiens le coup.",
    "Et toi, tu dors combien d'heures ?",
]


class LayoutTest(unittest.TestCase):
    def test_every_word_lands_in_its_scene_and_scenes_start_before_their_first_word(self):
        words = spoken(LINES)
        starts, total = layout(words, LINES)
        self.assertEqual(starts[0], 0.0)
        self.assertEqual([word["scene"] for word in words].count(1), 6)
        first_of_scene_one = next(word for word in words if word["scene"] == 1)
        self.assertLess(starts[1], first_of_scene_one["start"])
        self.assertGreater(total, words[-1]["end"])
        self.assertEqual(words[-1]["shown"], "d'heures")
        self.assertTrue(words[-1]["stop"])

    def test_a_script_that_does_not_match_the_voice_stops_the_render(self):
        words = spoken(LINES)[:-1]
        with self.assertRaises(SystemExit):
            layout(words, LINES)


class ChunkTest(unittest.TestCase):
    def test_lines_stay_short_and_never_run_across_a_pause_or_a_scene(self):
        words = spoken(LINES)
        layout(words, LINES)
        groups = chunks(words)
        for group in groups:
            self.assertLessEqual(len(group), 3)
            self.assertEqual(len({word["scene"] for word in group}), 1)
            for word in group[:-1]:
                self.assertFalse(word["stop"])
        self.assertEqual([word["shown"] for word in groups[3]], ["Jour", "un"])


class CaptionTest(unittest.TestCase):
    def test_badges_appear_only_over_the_scenes_that_have_one(self):
        words = spoken(LINES)
        starts, total = layout(words, LINES)
        script = captions(words, starts, total, [None, "JOUR 1", None])
        badges = [line for line in script.splitlines() if ",Badge," in line]
        self.assertEqual(len(badges), 1)
        self.assertTrue(badges[0].endswith("JOUR 1"))
        self.assertIn("{\\c&H003DC8FF&}Voilà", script)


class PaperTest(unittest.TestCase):
    def test_flat_light_lines_count_and_a_drawn_line_ends_them(self):
        paper = [[240] * 96] * 4
        drawing = [[30, 220] * 48]
        self.assertEqual(paper_edges(paper + drawing, 25), 4)
        self.assertEqual(paper_edges(drawing + paper, 25), 0)
        self.assertEqual(paper_edges(paper * 10, 25), 25)

    def test_a_paper_frame_is_trimmed_but_a_pale_sky_is_kept(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as folder:
            framed = Path(folder) / "framed.png"
            image = Image.new("RGB", (768, 1344), (240, 232, 215))
            pencil = ImageDraw.Draw(image)
            for x in range(60, 708, 12):
                pencil.line([(x, 80), (x + 40, 1264)], fill=(90, 60, 30), width=5)
            image.save(framed)
            self.assertTrue(trim_paper(framed))
            with Image.open(framed) as trimmed:
                self.assertLess(trimmed.width, 768)
                self.assertLess(trimmed.height, 1344)

            sky = Path(folder) / "sky.png"
            image = Image.new("RGB", (768, 1344), (240, 232, 215))
            pencil = ImageDraw.Draw(image)
            for x in range(0, 768, 12):
                pencil.line([(x, 500), (x + 40, 1344)], fill=(90, 60, 30), width=5)
            image.save(sky)
            self.assertFalse(trim_paper(sky))


class EpisodeFilesTest(unittest.TestCase):
    def test_every_episode_folder_holds_a_complete_script(self):
        folders = sorted((ROOT / "episodes").iterdir())
        self.assertTrue(folders)
        for number, folder in enumerate(folders, start=1):
            self.assertRegex(folder.name, rf"^{number:03d}-[a-z0-9-]+$")
            episode = json.loads((folder / "episode.json").read_text(encoding="utf-8"))
            self.assertEqual(folder.name.split("-", 1)[1], episode["slug"])
            self.assertLessEqual(len(episode["caption"]), 2200)
            self.assertIn("#jour7", episode["caption"])
            self.assertTrue(episode["sources"])
            self.assertGreaterEqual(len(episode["scenes"]), 4)
            for scene in episode["scenes"]:
                self.assertTrue(scene["line"].strip())
                self.assertTrue(scene["picture"].strip())
                self.assertTrue(scene["badge"] is None or scene["badge"].startswith("JOUR "))


if __name__ == "__main__":
    unittest.main()
