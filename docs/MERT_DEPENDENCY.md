# Where the app depends on MERT, and what replacing it takes

MERT-v1-95M (m-a-p/MERT-v1-95M) is published under CC BY-NC 4.0, so a venue
that charges for its nights can't run it. Nothing here removes it; this is the
list to decide from.

## What MERT actually does today

MERT is meant to give a valence/arousal "emotion" reading that tints and paces
the show. It needs a trained emotion head on top (`emotion_head.pt`) to do
that, and no head ships with the app or the installer. Without one,
`MERTModel._derive_emotion_from_embeddings` runs: it takes the 95M-parameter
transformer's embeddings and then works out valence and arousal mostly from
the raw spectrum (RMS, band energies, centroid), with the embedding mean
nudging valence by a tenth at most. So on every box today, MERT costs a
transformer pass twice a second and returns what is, in effect, a spectral
heuristic. Removing it would change very little on the night.

It is only active where `data/models/mert_v1_95m` exists, which happens when
`scripts/install_models.py` is run with no flags, with `--all` or with
`--mert`.

## Every place that touches it

Code that loads or runs it:

- `backend/app/services/ml/mert_model.py`: the model, the emotion vector and
  the emotion-to-lighting mapping (`map_to_lighting`).
- `backend/app/services/ml/__init__.py`: imports `MERTModel`,
  `EmotionVector`, `LightingEmotionMapping`.
- `backend/app/services/ml/model_manager.py`: `_load_mert` (tried first,
  HuBERT is the fallback), `model_paths['mert']`, and the mood call that
  prefers MERT over HuBERT.
- `backend/app/core/config.py`: `MERT_MODEL_PATH`, `EMOTION_HEAD_PATH`.
- `scripts/install_models.py`: `install_mert()`, called by the default
  install, `--all` and `--mert`. MERT is not in `RESTRICTED_LICENCES`, so the
  default install pulls it with no warning.

Code that uses what it produces:

- `backend/app/services/audio/audio_analyzer.py`
  - `_mert_model`, `_mert_task`, `_mert_interval` (2 Hz): runs it in the
    background and keeps `_last_emotion_vector` and `_last_emotion_mapping`.
  - `_analyze_mood`: when MERT is loaded, valence and arousal come from it;
    otherwise HuBERT, otherwise the spectral fallback. These feed
    `audio_features` valence/arousal, which the live renderer turns into
    colour through `_rebuild_get_emotional_color`.
  - The analyser output carries `emotion_vector` and `emotion_mapping`.
- `backend/app/services/effects/effects_engine.py`
  - `_apply_ml_data`: `emotion_mapping` sets the wash colour temperature
    (palette warmth) and the wash fixture spread (coverage), and is kept as
    `_ml_emotion_mapping`.
  - The layered renderer uses `_ml_emotion_mapping` for movement speed and
    for dimmer and saturation modulation.
  - The pro state exposes `emotion_mapping` to the UI.
- `backend/app/services/pipeline/training_data.py`: an optional
  `mert_embedding` field for training rows. Nothing fills it in the live path.

Docs that describe it: `docs/LOCAL_ML_MODELS_GUIDE.md`,
`docs/ASSESSMENT_AND_ROADMAP_2026-07.md`,
`docs/VIDEO_TO_DMX_TRAINING_PIPELINE.md`,
`docs/AI_MUSIC_SENTIMENT_RESEARCH.md`.

## What replacing it would take

Small, because everything downstream reads an emotion vector and a mapping,
not MERT itself.

1. Stop installing it by default: add `"mert"` to `RESTRICTED_LICENCES` in
   `scripts/install_models.py` and gate `install_mert()` the way BeatNet and
   YOLOv9 are gated. One file, a few lines. Boxes that already have it keep
   it until the folder is deleted.
2. Give `_analyze_mood` another source of valence and arousal. The club genre
   model (EfficientAT, MIT) already reads AudioSet's mood tags (happy, sad,
   tender, exciting, angry, scary) and returns a mood with valence and
   arousal every five seconds. Wiring that in, and building the same
   `emotion_mapping` from it with the existing `map_to_lighting` rules, is
   a contained change in the analyser plus tests. Where the genre model isn't
   on the box, the existing spectral fallback already covers it.
3. Optionally, later: delete `mert_model.py`, the config keys and the docs
   sections once nobody runs it.

What the show loses: very little today, since without an emotion head MERT's
output is mostly the spectral heuristic the fallback already computes. What
it would lose in future: the option of training an emotion head on MERT.
A head trained on a commercially licensed encoder (the EfficientAT
embeddings, for one) would do the same job.

HuBERT, the existing fallback, is a speech model and not a good mood source
for music either, so the club model's mood is the better replacement.
