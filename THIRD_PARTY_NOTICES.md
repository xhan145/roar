# Third-party notices — ROAR Read Aloud additions

ROAR Read Aloud can use the following third-party components. This summary does
not replace their license texts. A distributed installer or optional voice pack
must include the complete applicable license and NOTICE files.

The complete Apache License 2.0 text used by the Kokoro/Misaki software and the
Kokoro-82M model/voices is shipped at `licenses/Apache-2.0.txt` and copied into
the hash-verified voice pack as `LICENSE-KOKORO-82M.txt`.

- Kokoro 0.9.4, Misaki 0.9.4, Transformers 4.53.2, huggingface-hub 0.33.4,
  UIAutomation for Python 2.0.29, and Kokoro-82M v1.0 model/voice files:
  Apache License 2.0.
- PyTorch 2.7.1, NumPy 2.2.6, and Click 8.2.1: BSD-3-Clause.
- Loguru 0.7.3, spaCy 3.8.14, comtypes 1.4.16, and python-sounddevice 0.5.5:
  MIT.
- PortAudio: PortAudio license (MIT-style).

Kokoro-82M source and model card:
https://huggingface.co/hexgrad/Kokoro-82M

Kokoro source:
https://github.com/hexgrad/kokoro

eSpeak-NG is not bundled or required by ROAR's English MVP. It is licensed
GPL-3.0-or-later and requires a separate redistribution review if added later.

See `docs/TTS_DEPENDENCY_INVENTORY.md` for versions, roles, provenance,
supply-chain controls, and unresolved release work.
