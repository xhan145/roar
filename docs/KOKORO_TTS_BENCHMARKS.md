# Kokoro Read Aloud benchmark

Measured 2026-07-23 on Windows 11 with a 13th Gen Intel Core i7-13620H
(10 physical / 16 logical cores), 15.6 GiB RAM, and an NVIDIA RTX 4060 Laptop
GPU. The isolated `torch==2.7.1` runtime was CPU-only, so the backend reported
`cpu`. Voice: `af_heart`; sample rate: 24 kHz; speed: 1.0.

| Input | Characters | Chunks | First audio | Total synthesis | Audio generated | Real-time factor |
|---|---:|---:|---:|---:|---:|---:|
| Short | 57 | 1 | 3,439 ms | 3,439 ms | 4,075 ms | 0.844 |
| Medium | 594 | 3 | 6,704 ms | 16,884 ms | 36,950 ms | 0.457 |
| Long | 3,149 | 13 | 8,303 ms | 84,598 ms | 203,300 ms | 0.416 |

Cold model load was 22,173 ms. Peak inference-worker resident memory was
1,544,376,320 bytes (~1.44 GiB). RTF below 1 means synthesis was faster than
playback duration. These are observations, not timing assertions; latency
depends on CPU, power mode, text, voice, sentence structure, and thermal/power
state. A repeat run produced 3,085/6,396/7,002 ms first-audio times and
0.757/0.440/0.437 RTF, demonstrating normal variability.

Disk measurements:

- Verified license/model/config/four-voice manifest payload: 329,319,649 bytes
  (~314.1 MiB).
- Installed isolated runtime in this environment: 1,802,033,988 bytes
  (~1.68 GiB).
- Combined optional footprint: 2,131,353,637 bytes (~1.98 GiB).
- Main-app selected-text dependencies (`uiautomation` + `comtypes`) occupy
  roughly 3.8 MiB in the development environment before installer compression.

Peak worker memory is collected inside the actual Python 3.12 inference process
through `K32GetProcessMemoryInfo`; measuring the virtual-environment launcher
would under-report it.
