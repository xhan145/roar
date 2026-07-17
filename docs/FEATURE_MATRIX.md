# Feature matrix

**Gates are ENFORCED as of v0.22.0** — with grandfathering. This matrix pins what
is gated, what never can be, and what existing users keep.

## Grandfathering (the compatibility decision)

Every paid-target feature below **shipped free through v0.21.0**. Removing them
from people who already had them would break the promise in rule 17 of the
commercial brief ("do not silently move an existing free feature into a paid
tier"), so:

- **Existing installs are grandfathered.** On first launch of v0.22.0, an install
  that predates gating receives a **one-time grant** of exactly the features that
  shipped free (`legacy_grant.py`). **Nobody loses anything they already had.**
- **New installs are gated** normally, and see an upgrade explanation on
  intentional interaction with a paid feature.
- A grant is **feature IDs only — never an edition**. Only a signed licence sets
  an edition, so "no unsigned value unlocks an edition" still holds.
- Features that **never shipped free** (project vocabulary, developer snippet
  packs, file/developer tagging) are marked **planned** and are Developer-only for
  everyone — they are never granted, and never claimed as existing.

**Consequence, stated plainly:** because everything already shipped free, the paid
tiers monetise **new users only** until new Pro/Developer capabilities are built.

## Matrix

Prices are one-time: **Core free · Pro $29 · Developer Pack $49 · Supporter $99.**
No subscription, no account, no cloud transcription, no telemetry.

| Feature | Core (free) | Pro | Developer | Supporter |
|---|---|---|---|---|
| Push-to-talk dictation | ✅ | ✅ | ✅ | ✅ |
| Hands-free (double-tap) | ✅ | ✅ | ✅ | ✅ |
| Streaming preview | ✅ | ✅ | ✅ | ✅ |
| Multilingual dictation | ✅ | ✅ | ✅ | ✅ |
| Scratch-that undo | ✅ | ✅ | ✅ | ✅ |
| Basic spoken commands | ✅ | ✅ | ✅ | ✅ |
| History + search | ✅ | ✅ | ✅ | ✅ |
| **All privacy & delete controls** | ✅ always | ✅ always | ✅ always | ✅ always |
| Basic vocabulary | ✅ | ✅ | ✅ | ✅ |
| Safe diagnostics + Safe Mode | ✅ | ✅ | ✅ | ✅ |
| Manual update check | ✅ | ✅ | ✅ | ✅ |
| Advanced milestones | — | ✅ | ✅ | ✅ |
| Smart formatting | — | ✅ | ✅ | ✅ |
| Snippet packs / extended variables | — | ✅ | ✅ | ✅ |
| Vocabulary suggestions | — | ✅ | ✅ | ✅ |
| History filters/tags | — | ✅ | ✅ | ✅ |
| Advanced cleanup controls | — | ✅ | ✅ | ✅ |
| Settings import/export | — | ✅ | ✅ | ✅ |
| Code mode / symbol dictation | — | — | ✅ | ✅ |
| App profiles / per-app language | — | — | ✅ | ✅ |
| Project vocabulary / file tagging | — | — | ✅ | ✅ |
| Developer snippet packs | — | — | ✅ | ✅ |

Unknown or corrupt edition ⇒ Core. Unknown features default to allowed.

Guarantees, in plain words:

- Core dictation remains free.
- Privacy controls remain free.
- History and audio deletion remain free.
- Offline use remains free.
