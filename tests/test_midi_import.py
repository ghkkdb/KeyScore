"""MIDI 主旋律提取测试。"""

from __future__ import annotations

import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

import mido

from keyscore.midi_import import import_midi
from keyscore.score_document import pitch_index, serialize_document


class MidiImportTests(unittest.TestCase):
    """验证 MIDI 选轨、最高音折叠和顺序化处理。"""

    def test_import_selects_densest_track_and_keeps_highest_onset_note(self) -> None:
        """应选择音符最多的轨道，同起点复音只保留最高音。"""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "测试旋律.mid"
            midi = mido.MidiFile(type=1, ticks_per_beat=480)
            metadata = mido.MidiTrack()
            metadata.append(mido.MetaMessage("set_tempo", tempo=600_000, time=0))
            metadata.append(
                mido.MetaMessage(
                    "time_signature",
                    numerator=3,
                    denominator=4,
                    time=0,
                )
            )
            midi.tracks.append(metadata)
            accompaniment = mido.MidiTrack()
            accompaniment.append(mido.MetaMessage("track_name", name="Accompaniment", time=0))
            accompaniment.append(mido.Message("note_on", note=48, velocity=80, time=0))
            accompaniment.append(mido.Message("note_off", note=48, velocity=0, time=480))
            midi.tracks.append(accompaniment)
            melody = mido.MidiTrack()
            melody.append(mido.MetaMessage("track_name", name="Melody", time=0))
            melody.append(mido.Message("note_on", note=60, velocity=80, time=0))
            melody.append(mido.Message("note_on", note=64, velocity=80, time=0))
            melody.append(mido.Message("note_on", note=67, velocity=80, time=480))
            melody.append(mido.Message("note_off", note=60, velocity=0, time=480))
            melody.append(mido.Message("note_off", note=64, velocity=0, time=0))
            melody.append(mido.Message("note_off", note=67, velocity=0, time=0))
            midi.tracks.append(melody)
            midi.save(path)

            result = import_midi(path)

            self.assertEqual(result.document.title, "测试旋律")
            self.assertEqual(result.document.bpm, 100)
            self.assertEqual(result.document.beat, "3/4")
            self.assertEqual(result.report.track_name, "Melody")
            self.assertEqual(result.report.source_notes, 3)
            self.assertEqual(result.report.collapsed_notes, 1)
            self.assertEqual(result.report.shortened_notes, 1)
            self.assertEqual(len(result.document.groups), 2)
            self.assertEqual(pitch_index(result.document.groups[0].pitches[0]), 28)
            self.assertEqual(result.document.groups[0].duration_beats, Fraction(1))
            self.assertIn("@title 测试旋律", serialize_document(result.document))


if __name__ == "__main__":
    unittest.main()
