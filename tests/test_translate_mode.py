"""Translate mode: model resolution, task selection, config plumbing."""

import app as app_mod
import config as config_mod
import transcriber as tr


def test_default_is_off():
    assert config_mod.DEFAULTS["translate_to_english"] is False


def test_translate_forces_a_multilingual_model_on_auto():
    assert tr.resolve_model("auto", "cuda", "en") == tr.GPU_MODEL_EN
    assert tr.resolve_model("auto", "cuda", "en", translate=True) == tr.GPU_MODEL_MULTI
    assert tr.resolve_model("auto", "cpu", "en", translate=True) == tr.CPU_MODEL_MULTI
    # explicit model picks are respected as always
    assert tr.resolve_model("small.en", "cpu", "en", translate=True) == "small.en"


def test_run_passes_translate_task(monkeypatch):
    calls = {}

    class FakeModel:
        def transcribe(self, audio, **kw):
            calls.update(kw)
            return iter(()), None

    t = tr.Transcriber(accel={"translate_to_english": True})
    t._model = FakeModel()
    t._run([0.0])
    assert calls["task"] == "translate"
    assert calls["language"] is None      # source language is auto-detected


def test_run_defaults_to_transcribe_task():
    calls = {}

    class FakeModel:
        def transcribe(self, audio, **kw):
            calls.update(kw)
            return iter(()), None

    t = tr.Transcriber(language="en", accel={})
    t._model = FakeModel()
    t._run([0.0])
    assert calls["task"] == "transcribe"
    assert calls["language"] == "en"


def test_toggling_translate_reloads_the_model():
    old = dict(config_mod.DEFAULTS)
    new = dict(config_mod.DEFAULTS)
    new["translate_to_english"] = True
    assert ("reload_model", new["model"]) in app_mod.diff_config(old, new)


def test_config_round_trips_the_flag(tmp_path):
    p = str(tmp_path / "config.json")
    cfg = config_mod.load(p)
    cfg["translate_to_english"] = True
    config_mod.save(cfg, p)
    assert config_mod.load(p)["translate_to_english"] is True
