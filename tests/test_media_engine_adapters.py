"""Contract tests for optional concrete ASR/OCR adapters."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from aios_work_system.media.adapters import OCRSegment, TranscriptSegment
from aios_work_system.media.adapters_faster_whisper import FasterWhisperASRAdapter
from aios_work_system.media.adapters_paddleocr import PaddleOCRAdapter

class FakeWhisperModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio_path, **kwargs):
        self.calls.append((audio_path, kwargs))
        return iter(
            [
                SimpleNamespace(start=0.25, end=1.75, text="  hello world  "),
                SimpleNamespace(start=2.0, end=2.5, text="   "),
                SimpleNamespace(start=3.0, end=4.0, text="second sentence"),
            ]
        ), SimpleNamespace(language="en")


def test_faster_whisper_adapter_maps_seconds_to_milliseconds(tmp_path):
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    fake_model = FakeWhisperModel()
    created = {}

    def model_factory(model_size, **kwargs):
        created["model_size"] = model_size
        created["kwargs"] = kwargs
        return fake_model

    adapter = FasterWhisperASRAdapter(
        model_size="small",
        device="cpu",
        compute_type="int8",
        language="en",
        beam_size=3,
        model_factory=model_factory,
        package_version="1.2.1",
    )
    segments = adapter.transcribe(audio)

    assert segments == [
        TranscriptSegment(250, 1750, "hello world"),
        TranscriptSegment(3000, 4000, "second sentence"),
    ]
    assert created["model_size"] == "small"
    assert created["kwargs"]["device"] == "cpu"
    assert created["kwargs"]["compute_type"] == "int8"
    assert fake_model.calls[0][1]["language"] == "en"
    assert fake_model.calls[0][1]["vad_filter"] is True
    assert adapter.config["beam_size"] == 3
    assert adapter.version == "1.2.1"


def test_faster_whisper_adapter_rejects_invalid_model_timestamps(tmp_path):
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")

    class InvalidModel:
        def transcribe(self, path, **kwargs):
            return iter(
                [SimpleNamespace(start=float("nan"), end=2, text="bad")]
            ), None

    adapter = FasterWhisperASRAdapter(model_factory=lambda *a, **k: InvalidModel())

    with pytest.raises(ValueError, match="invalid segment timestamps"):
        adapter.transcribe(audio)


class FakePaddleResult:
    def __init__(self, payload):
        self.payload = payload

    def save_to_json(self, save_path):
        output = Path(save_path) / "frame_res.json"
        output.write_text(json.dumps(self.payload), encoding="utf-8")


class FakePaddlePipeline:
    def __init__(self, result):
        self.result = result
        self.inputs = []

    def predict(self, *, input):
        self.inputs.append(input)
        return [self.result]


def test_paddleocr_adapter_maps_boxes_scores_and_frame_timestamps(tmp_path):
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"frame")
    result = FakePaddleResult(
        {
            "res": {
                "rec_texts": ["账号设置", "low confidence"],
                "rec_boxes": [[10, 20, 100, 60], [0, 0, 20, 10]],
                "rec_scores": [0.98, 0.1],
            }
        }
    )
    fake_pipeline = FakePaddlePipeline(result)
    created = {}

    def factory(**kwargs):
        created.update(kwargs)
        return fake_pipeline

    adapter = PaddleOCRAdapter(
        lang="ch",
        device="cpu",
        min_confidence=0.5,
        text_detection_model_name="PP-OCRv6_small_det",
        text_recognition_model_name="PP-OCRv6_small_rec",
        ocr_factory=factory,
        package_version="3.7.0",
    )
    segments = adapter.recognize(image, 12_500)

    assert segments == [
        OCRSegment(
            timestamp_ms=12_500,
            text="账号设置",
            bounding_box=[10.0, 20.0, 100.0, 60.0],
            confidence=0.98,
        )
    ]
    assert created["lang"] == "ch"
    assert created["device"] == "cpu"
    assert created["text_detection_model_name"] == "PP-OCRv6_small_det"
    assert created["text_recognition_model_name"] == "PP-OCRv6_small_rec"
    assert "ocr_version" not in created
    assert "lang" not in created
    assert created["use_doc_orientation_classify"] is False
    assert fake_pipeline.inputs == [str(image.resolve())]
    assert adapter.version == "3.7.0"


def test_paddleocr_adapter_normalizes_polygon_boxes(tmp_path):
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"frame")
    result = FakePaddleResult(
        {
            "res": {
                "rec_texts": ["lesson title"],
                "rec_polys": [[[5, 10], [25, 8], [30, 40], [4, 38]]],
                "rec_scores": [0.8],
            }
        }
    )
    adapter = PaddleOCRAdapter(
        ocr_factory=lambda **kwargs: FakePaddlePipeline(result),
        package_version="3.7.0",
    )

    segments = adapter.recognize(image, 2500)

    assert segments[0].bounding_box == [4.0, 8.0, 30.0, 40.0]


def test_optional_adapters_are_lazy_and_expose_config_hash_inputs():
    small = FasterWhisperASRAdapter(
        model_size="small",
        model_factory=lambda *a, **k: FakeWhisperModel(),
        package_version="1.2.1",
    )
    medium = FasterWhisperASRAdapter(
        model_size="medium",
        model_factory=lambda *a, **k: FakeWhisperModel(),
        package_version="1.2.1",
    )
    ocr = PaddleOCRAdapter(
        ocr_factory=lambda **kwargs: FakePaddlePipeline(
            FakePaddleResult({"res": {"rec_texts": [], "rec_boxes": []}})
        ),
        package_version="3.7.0",
    )

    assert small._model is None
    assert ocr._pipeline is None
    assert small.config != medium.config
    assert ocr.config["model_version"] == "PP-OCRv6"



def test_paddleocr_requires_detection_and_recognition_names_as_a_pair():
    with pytest.raises(ValueError, match="provided together"):
        PaddleOCRAdapter(text_detection_model_name="PP-OCRv6_tiny_det")
