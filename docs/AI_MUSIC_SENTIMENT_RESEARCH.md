# AI Music Sentiment & Intelligent Lighting Research Document

## Technical Research for Next-Generation Audio-Reactive Lighting Intelligence

**Project:** Intelligent Lighting System
**Date:** 2026-02-06
**Scope:** Advancing beyond single-operator training to world-class AI-driven lighting design

---

## Table of Contents

1. [Current System Analysis](#1-current-system-analysis)
2. [Advanced Music Understanding](#2-advanced-music-understanding)
3. [Learning from Multiple Sources](#3-learning-from-multiple-sources)
4. [Cutting-Edge Model Architectures](#4-cutting-edge-model-architectures)
5. [Real-Time Inference Constraints](#5-real-time-inference-constraints)
6. [Training Data Strategy](#6-training-data-strategy)
7. [Concrete Implementation Plan: Top 3 Approaches](#7-concrete-implementation-plan-top-3-approaches)
8. [Integration Roadmap](#8-integration-roadmap)

---

## 1. Current System Analysis

### 1.1 What Exists Today

The current system (`backend/app/services/`) operates with these components:

| Component | File | What It Does | Limitations |
|-----------|------|-------------|-------------|
| **BeatNet** | `ml/model_manager.py` | Real-time beat/downbeat detection via DBN inference | Only detects beats, not meter/groove; no anticipation |
| **HuBERT** | `ml/model_manager.py` | 7-class speech emotion recognition (angry, disgust, fear, happy, neutral, sad, surprise) | Trained on speech, not music; valence/arousal derived from speech emotions via heuristic weighting |
| **Audio Analyzer** | `audio/audio_analyzer.py` | 7 frequency bands, spectral flux, centroid, rolloff, RMS, BPM estimation | No structure detection, no genre, no key/harmony, no anticipation |
| **Decision Engine** | `effects/decision_engine.py` | 6-state Markov chain (INTRO/BUILDUP/PEAK/SUSTAIN/BREAKDOWN/OUTRO), energy-weighted effect selection | Hard-coded thresholds for structure detection; Markov transitions are static probabilities, not learned; no genre awareness |
| **Training Recorder** | `ml/training_recorder.py` | Records paired AudioFrame + LightingFrame at 50ms alignment tolerance | Single operator, single session, JSONL export only; no aggregation, no quality filtering |
| **Effects Engine** | `effects/effects_engine.py` | 4-layer system (base intensity, movement, dimmer, strobe) + LFO engine + color mapper | Auto-mode currently disabled; LFO engine has no audio-reactive intelligence; color mapper uses static palette hue ranges |
| **LFO Engine** | `effects/lfo_engine.py` | grandMA2-style waveform generators with phase distribution | No learning capability; parameters are all manual |
| **Color Mapper** | `effects/color_mapper.py` | HSV mapping from valence/arousal + genre palettes | Static mappings; no temporal coherence modeling |

### 1.2 Critical Gaps

1. **HuBERT is a speech model applied to music.** The emotion labels (angry, disgust, fear, happy, neutral, sad, surprise) are Ekman's basic emotions for speech. Music emotion is fundamentally different -- it requires understanding of musical features like harmony, rhythm, and timbre in combination. The heuristic `_emotions_to_valence()` and `_emotions_to_arousal()` mappings in `model_manager.py` (lines 301-323) are rough approximations at best.

2. **Structure detection is threshold-based.** The `_detect_structure_changes()` method in `decision_engine.py` (lines 353-396) uses hard-coded energy thresholds (e.g., `audio.energy_trend > 0.1 and audio.spectral_flux > 0.3`) that will fail on quiet intros with complex structure, genre crossovers, or any track that does not follow a standard EDM build-drop pattern.

3. **No anticipation.** The system reacts to audio events after they happen. A skilled lighting designer anticipates drops 4-8 bars ahead and begins building visual tension. The current system has zero predictive capability.

4. **Single-operator limitation.** The `TrainingRecorder` captures one person's decisions. There is no mechanism to learn what makes lighting "good" across multiple operators, styles, or skill levels.

5. **No genre awareness.** The `DecisionEngine` uses the same Markov transition matrix regardless of whether the music is EDM, rock, jazz, or hip-hop. The `ColorMapper` has genre palettes (`ColorPalette` enum) but they must be manually selected.

6. **Fixed fixture abstraction.** The training data records raw DMX frames and fixture-specific state. This does not generalize across different fixture types, counts, or rig layouts.

---

## 2. Advanced Music Understanding

### 2.1 State-of-the-Art Music Structure Analysis

#### 2.1.1 All-In-One Music Structure Analyzer (Taejun Kim, 2023)

The **All-In-One Music Structure Analyzer** is a transformer-based model that simultaneously performs:
- Beat tracking
- Downbeat tracking
- Tempo estimation
- Music structure segmentation (labeling sections as intro, verse, chorus, bridge, outro, etc.)
- Functional segment boundary detection

**Architecture:** Convolutional front-end for spectral features feeding into a multi-task transformer with separate prediction heads for each task. Trained on the Harmonix Set (912 songs with beat, downbeat, section, and segment annotations).

**Key paper:** Kim, T. (2023). "All-In-One Music Structure Analyzer." *Proceedings of ISMIR*.

**Why this matters for ILS:** This single model replaces BeatNet AND the threshold-based structure detection in `DecisionEngine._detect_structure_changes()`, providing proper section labels (verse, chorus, bridge, drop) rather than the current 6-state energy-based heuristic.

**Latency consideration:** The original model operates on full songs (offline). For real-time use, a causal variant is needed. The approach is to use a sliding window of 8-16 seconds with a causal transformer (masked self-attention). This introduces approximately 2-4 seconds of look-ahead latency for structure detection, which is acceptable because lighting designers plan 4-8 bars (4-16 seconds at typical BPMs) ahead anyway.

#### 2.1.2 MSAF (Music Structure Analysis Framework)

**MSAF** (Nieto & Bello, 2016) is a Python framework implementing multiple structure analysis algorithms:
- Spectral Clustering (McFee & Ellis, 2014)
- Convex NMF (Nieto & Bello, 2014)
- Structural Features (Serra et al., 2012)
- Checkerboard Kernel (Foote, 2000)

**Integration approach:** MSAF algorithms can run offline on pre-loaded tracks to provide ground-truth structure labels for training data, even when the real-time model (All-In-One) is used for inference.

#### 2.1.3 Harmonix Dataset

The **Harmonix Set** (Nieto et al., 2019) contains 912 songs with:
- Beat and downbeat annotations
- Section labels (intro, verse, chorus, bridge, outro, instrumental, solo)
- Section boundaries with human-verified timestamps

This is the primary dataset for training music structure models. Combined with the **SALAMI** dataset (Smith et al., 2011; 1,359 songs with structural annotations) and **RWC Music Database** (Goto et al., 2002), a robust training set of approximately 3,000+ annotated songs can be assembled.

#### 2.1.4 Drop Detection for EDM

Standard music structure analysis is designed for pop/rock forms. EDM requires specialized detection of:
- **Build-ups:** Rising energy, high-pass filter sweeps, snare rolls, rising pitch
- **Drops:** Sudden bass return after build-up, kick drum entry, full spectral content
- **Breakdowns:** Energy removal, often just vocals or pads over minimal percussion
- **Risers/FX:** Synthesizer sweep effects that signal upcoming transitions

**Approach:** Train a dedicated EDM structure classifier on the **EDM Structure Dataset** using mel-spectrogram + onset strength features. Key features for drop detection:
- Spectral centroid trajectory (rises during build-up, drops suddenly)
- Low-frequency energy ratio (near zero during build-up, spikes at drop)
- Onset density (increases during build-up via snare rolls)
- Spectral bandwidth (narrows during build-up high-pass filter, widens at drop)

### 2.2 Music Emotion Recognition Beyond Valence/Arousal

#### 2.2.1 The Problem with Speech Emotion Models on Music

The current system uses HuBERT (`AutoModelForAudioClassification`) trained on speech emotion. This is fundamentally flawed because:

1. **Speech emotions are expressed through prosody, pitch contour, and speaking rate.** Music "emotions" are expressed through harmony (major vs. minor), rhythm (groove, syncopation), timbre, dynamics, and cultural associations.
2. **Music can express emotions that speech cannot:** nostalgia, triumph, tension, release, hypnotic states, euphoria.
3. **Music emotion is often ambiguous and multi-layered:** a song can simultaneously feel melancholic and beautiful, or aggressive and exciting.

#### 2.2.2 Music-Specific Emotion Models

**MERT (Music undERstanding Transformer)** (Li et al., 2023)
- Pre-trained on 160K hours of music (not speech) using masked token prediction
- Produces rich musical embeddings that capture tonal, rhythmic, and timbral information
- Can be fine-tuned for emotion recognition, genre classification, and instrument detection simultaneously
- **Replaces HuBERT** as the foundation model for all audio understanding tasks

**MusicBERT** (Zeng et al., 2021)
- Symbolic music pre-training (works on MIDI/score representations)
- Complementary to audio-based models for understanding harmonic structure

**Music Emotion Recognition Datasets:**
- **MTG-Jamendo** (Bogdanov et al., 2019): 55,000 tracks with mood/theme tags from 56 categories
- **DEAM** (Aljanaki et al., 2017): 1,802 excerpts with continuous valence/arousal annotations at 2Hz
- **PMEmo** (Zhang et al., 2018): 794 songs with second-level valence/arousal + EDA/HR physiological data
- **MuSe** (Stappen et al., 2021): Multimodal music emotion with continuous arousal annotations

#### 2.2.3 Multi-Dimensional Emotion Models

Beyond valence/arousal, the following dimensions are relevant for lighting:

| Dimension | Description | Lighting Application |
|-----------|-------------|---------------------|
| **Valence** | Negative to Positive | Color warmth (cool blues for negative, warm oranges for positive) |
| **Arousal** | Calm to Excited | Movement speed, intensity, strobe frequency |
| **Dominance** | Submissive to Dominant | Fixture coverage (narrow spot vs. full wash), brightness |
| **Tension** | Relaxed to Tense | Color saturation, movement irregularity, strobe likelihood |
| **Energy Trajectory** | Building/Sustaining/Falling | Movement complexity ramp-up/down |
| **Novelty** | Familiar/Surprising | Effect change frequency |
| **Groove** | Static to Groovy | Beat-sync strength, dimmer pulse depth |
| **Darkness** | Light to Dark (aesthetic) | Dimmer base level, palette saturation |

**Model architecture for multi-dimensional emotion:**
```
Audio Waveform (16kHz)
    |
    v
MERT Encoder (frozen or fine-tuned)
    |
    v
[CLS] token + temporal pooling
    |
    v
Multi-head regression (8 emotion dimensions)
    |
    v
[valence, arousal, dominance, tension, energy_trajectory, novelty, groove, darkness]
```

**Loss function:** Concordance Correlation Coefficient (CCC) loss for each dimension, which is standard in continuous emotion recognition:

```
CCC(y, y_hat) = 2 * rho * sigma_y * sigma_y_hat / (sigma_y^2 + sigma_y_hat^2 + (mu_y - mu_y_hat)^2)
```

Where rho is Pearson's correlation, sigma is standard deviation, mu is mean. CCC penalizes both poor correlation and scale/offset mismatches.

#### 2.2.4 Temporal Emotion Trajectories

Static per-chunk emotion is insufficient. A skilled LD reads the emotional arc of an entire song. The system needs:

1. **Sliding window emotion** at approximately 2Hz (every 500ms) for reactive lighting
2. **Long-range emotion trajectory** over 30-60 second windows for anticipatory lighting
3. **Emotion change detection** to trigger lighting transitions at emotional boundaries

**Architecture for trajectory modeling:**
```
MERT per-frame embeddings (50Hz)
    |
    v
Temporal Convolutional Network (TCN) with dilated causal convolutions
    |  receptive field: 30 seconds
    v
Per-frame emotion predictions + trajectory classification
    |
    v
[current_emotion(8D), emotion_derivative(8D), next_transition_type, time_to_transition]
```

### 2.3 Beat/Rhythm Understanding

#### 2.3.1 Beyond BPM

The current system extracts BPM and beat/downbeat positions. A skilled LD understands much more:

| Feature | Description | Current Support | Needed |
|---------|-------------|----------------|--------|
| BPM | Tempo | Yes (BeatNet) | Improve accuracy |
| Beat position | 1-2-3-4 | Yes (basic) | Yes, with confidence |
| Downbeats | Bar boundaries | Yes (BeatNet) | Yes |
| Time signature | 4/4, 3/4, 6/8, etc. | Hardcoded "4/4" | Real detection needed |
| Groove pattern | Straight vs swing vs shuffle | No | Critical for feel |
| Syncopation | Off-beat emphasis | No | Important for movement timing |
| Polyrhythm | Multiple simultaneous meters | No | Relevant for complex genres |
| Metric structure | 4-bar, 8-bar, 16-bar phrases | No | Critical for section awareness |
| Rhythmic complexity | Simple to complex | No | Drives effect complexity |

#### 2.3.2 Advanced Beat and Meter Models

**BeatTransformer** (Zhao & Chen, 2024)
- Transformer-based joint beat and downbeat tracking
- Handles variable time signatures (3/4, 5/4, 7/8)
- State-of-the-art F1 scores on GTZAN, Ballroom, and Harmonix datasets

**TCN-based beat tracking** (Davies & Bock, 2019)
- Temporal Convolutional Networks for beat tracking
- Lower latency than transformer approaches
- Suitable for real-time streaming inference

**Groove analysis:**
- Quantize detected beat positions against a grid
- Measure micro-timing deviations to classify groove type (straight, swing, shuffle, behind-the-beat)
- Use the GrooveToolbox (Crestel et al., 2017) metrics: velocity variance, micro-timing patterns, syncopation index

#### 2.3.3 Phrase and Hypermeter Detection

Lighting designers think in phrases (typically 4-bar or 8-bar groups) and hypermetric structures (groups of phrases forming sections). This is the level at which lighting changes happen -- not on individual beats but on phrase boundaries.

**Approach:**
1. Detect beats and downbeats with BeatTransformer
2. Group downbeats into 4-bar phrases using autocorrelation of beat-synchronous features (chroma, energy)
3. Detect phrase boundaries using self-similarity matrix analysis (novelty curve computation)
4. Label hypermeter position: "bar 1 of 4", "bar 3 of 8", etc.

This gives the system awareness like: "We are on bar 6 of an 8-bar buildup phrase, drop is likely in 2 bars."

### 2.4 Genre Classification

#### 2.4.1 Why Genre Matters for Lighting

Different genres have radically different lighting conventions:

| Genre | Typical Lighting Style |
|-------|----------------------|
| EDM/Dance | High intensity, fast chases, heavy strobe on drops, cyan/magenta/UV colors, synchronized movement |
| Rock | Red/amber/blue, audience wash, back-lighting, gobo breakups, follows guitar solos |
| Jazz | Subtle wash, warm amber, minimal movement, spot on soloists, no strobe |
| Hip-Hop | Purple/gold, slow sweeps, crowd moments, spotlight on MC, bass-reactive |
| Pop | Bright multi-color, audience involvement, video content sync, upbeat movement |
| Metal | Red/white, extreme strobe, fast movement, blackouts, high contrast |
| Ambient/Downtempo | Slow color fades, minimal movement, low saturation, atmospheric haze |

The current `ColorPalette` enum in `color_mapper.py` captures some of this but requires manual selection. Auto-detection enables appropriate styling without user intervention.

#### 2.4.2 Genre Classification Models

**MERT fine-tuned for genre** (from Section 2.2.2) can classify genre as a secondary task. Additionally:

**PaSST (Patchout faSt Spectrogram Transformer)** (Koutini et al., 2022)
- State-of-the-art audio tagging model
- Achieves 0.471 mAP on AudioSet (632 classes including genres)
- Can simultaneously predict genre, mood, instrumentation, and acoustic properties
- Patchout regularization enables efficient training

**Approach:** Use PaSST or MERT fine-tuned on the MTG-Jamendo genre subset (87 genre tags) + FMA dataset (106,574 tracks, 161 genres). Run inference on 10-second windows and use majority voting over the first 30 seconds of a track to establish genre.

**Hierarchical genre classification:**
```
Level 0: Electronic / Acoustic / Mixed
Level 1: EDM / Rock / Jazz / Classical / Hip-Hop / Pop / Metal / World / Ambient
Level 2: House / Techno / DnB / Dubstep / Trance (within EDM)
Level 3: Deep House / Tech House / Progressive House (within House)
```

Each level provides increasingly specific lighting style guidance.

### 2.5 Key/Harmony Analysis

#### 2.5.1 Why Harmony Matters

Key and harmonic analysis enables:
- **Color-pitch mapping:** Map musical keys to colors using consistent associations (C major = white, A minor = blue, etc. based on Scriabin's color-key associations or learned mappings)
- **Tension/resolution detection:** Diminished and augmented chords create tension; resolution to tonic releases it. This directly maps to lighting tension (narrow spots, saturated colors, strobe risk) vs. release (wide wash, desaturated, smooth movement)
- **Key change detection:** Modulations signal major structural moments worthy of lighting changes
- **Chord progression awareness:** The I-IV-V-I pop progression vs. a deceptive cadence can inform whether to maintain or surprise with lighting

#### 2.5.2 Models for Harmonic Analysis

**BTC (Beat-synchronous Transformer for Chord estimation)** (Chen & Su, 2019)
- Transformer model for chord recognition from audio
- Beat-synchronous processing reduces computation
- Outputs chord labels at beat resolution

**Madmom chord recognition** (Bock et al., 2016)
- Real-time capable chord detection
- Part of the madmom library (Python)
- Can be run as a streaming processor

**Key detection:**
- **Krumhansl-Schmuckler key-finding algorithm** applied to chroma features
- Or use the pre-trained key detection from Essentia (Music Technology Group)
- Update key estimate every 4-8 bars to handle modulations

**Integration with color mapping:**
Replace the static `_get_palette_hue()` in `color_mapper.py` with a harmony-aware mapper:
```
key_detected = "A minor"  =>  base_hue = 220 (cool blue)
chord_current = "F major"  =>  hue_offset = +30 (relative to key)
tension_level = 0.7       =>  saturation = 0.9 (high tension = high saturation)
resolution = True          =>  transition_speed = slow (breathe into resolution)
```

### 2.6 Anticipation Models

#### 2.6.1 The Core Problem

The current system in `decision_engine.py` is entirely reactive. By the time `audio.is_drop` is detected (line 365-369: bass > 0.8 AND spectral_flux > 0.5 AND state == BUILDUP), the drop has already happened. The strobe fires *after* the drop, not *on* the drop.

A professional LD:
1. Recognizes a buildup pattern starting 8-16 bars before the drop
2. Begins visual buildup (narrowing focus, increasing intensity, reducing color variation)
3. Executes a blackout or freeze 1-2 beats before the drop
4. Hits the drop cue precisely on the downbeat

This requires **prediction** -- estimating what will happen 2-16 seconds in the future.

#### 2.6.2 Anticipation Architecture

**Approach 1: Template-Based Anticipation (simpler, more reliable)**

Train a classifier on labeled build-up patterns:
```
Input: 8-second audio window (mel-spectrogram)
Output: {
    is_buildup: bool,
    buildup_progress: float (0.0 = just started, 1.0 = about to drop),
    estimated_bars_to_transition: int,
    transition_type: enum (DROP, BREAKDOWN, SECTION_CHANGE, NONE)
}
```

Training data: Extract buildup sections from Harmonix + SALAMI datasets, compute progress as percentage through the labeled section.

**Approach 2: Sequence Prediction (more complex, more powerful)**

Use a causal transformer that predicts future audio features:
```
Input: Past 30 seconds of audio embeddings (from MERT, at 2Hz = 60 tokens)
Output: Predicted audio feature trajectory for next 8 seconds (16 tokens)
```

The predicted features are then fed through the same emotion/structure pipeline to estimate future states. This enables:
- "Energy will peak in approximately 4 bars" -> begin visual buildup now
- "Breakdown incoming in approximately 8 bars" -> prepare transition to sparse look
- "Key change in approximately 2 bars" -> prepare color palette shift

**Approach 3: Repetition-Based Prediction (for structured music)**

Most popular music repeats. If the system has heard the chorus once, it knows what the second chorus will be. This is essentially a self-similarity approach:

1. Compute beat-synchronous chroma features for the song so far
2. Build a self-similarity matrix in real-time
3. Detect recurring patterns (diagonals in the matrix)
4. When a pattern recurrence begins, predict the remainder based on the first occurrence

This works exceptionally well for verse-chorus structures and DJ sets where tracks are repeated or mixed from known recordings.

#### 2.6.3 Look-Ahead Buffer Architecture

For the lighting system, implement a look-ahead buffer:

```
[past 30s audio] -> [analysis models] -> [current state + predictions]
                                              |
                                              v
                                    [lighting planner]
                                              |
                                    +---------+---------+
                                    |         |         |
                               [now+0ms] [now+500ms] [now+2s] ... [now+8s]
                                    |
                                    v
                              [DMX output]
```

The lighting planner generates a timeline of future lighting states, and the system smoothly interpolates toward them. When predictions change, the timeline is re-computed. This naturally creates the "anticipatory" feel of professional lighting.

---

## 3. Learning from Multiple Sources

### 3.1 Multi-Operator Learning

#### 3.1.1 The Problem with Single-Operator Training

The current `TrainingRecorder` in `training_recorder.py` captures data from a single operator:

```python
@dataclass
class TrainingFrame:
    timestamp: float
    audio: AudioFrame      # What the music was doing
    lighting: LightingFrame # What the operator chose
```

Problems:
- Operator skill varies wildly (novice vs. professional)
- One person's aesthetic preferences are not universal
- Small dataset (one session = minutes of data, need hours)
- No quality signal (was this good lighting or bad lighting?)

#### 3.1.2 Multi-Operator Aggregation Architecture

**Ensemble of Operators:**

```
Operator 1 sessions -> Model 1 (style: "EDM aggressive")
Operator 2 sessions -> Model 2 (style: "EDM smooth")
Operator 3 sessions -> Model 3 (style: "Rock classic")
...
Operator N sessions -> Model N (style: "Jazz subtle")

User selects: "EDM aggressive" with 30% "EDM smooth" blend
    |
    v
Weighted ensemble inference:
    lighting = 0.7 * Model_1(audio) + 0.3 * Model_2(audio)
```

**Implementation:**
- Each operator records sessions tagged with their name and genre/style
- Train separate lightweight models (small MLPs or single-layer transformers) per operator
- At inference time, blend outputs using user-specified style weights
- Store operator metadata: skill rating (from peer review), genres, years of experience

**Federated Learning Extension:**

If operators are at different venues, use federated learning:
1. Each venue trains a local model on local data
2. Periodically aggregate model weights centrally (FedAvg, McMahan et al., 2017)
3. Push aggregated model back to venues
4. Local models benefit from global knowledge while keeping data private

This allows the community of ILS users to collectively improve the AI without sharing raw data.

#### 3.1.3 Operator Skill Weighting

Not all operator data is equally valuable. Weight training data by operator quality:

```
skill_weight = peer_rating * experience_factor * genre_match
```

Where:
- `peer_rating`: 1-5 stars from other operators reviewing recorded shows
- `experience_factor`: log(1 + years_experience)
- `genre_match`: 1.0 if operator specializes in this genre, 0.5 otherwise

Use importance sampling during training: high-skill operator frames are sampled more frequently.

### 3.2 Preference Learning / RLHF

#### 3.2.1 Reinforcement Learning from Human Feedback for Lighting

RLHF (Ouyang et al., 2022) can be adapted for lighting:

**Phase 1: Supervised Pre-Training**
- Train base model on all recorded operator data (audio -> lighting mapping)
- This gives a reasonable but imperfect starting point

**Phase 2: Reward Model Training**
- Show human evaluators pairs of lighting responses to the same audio clip:
  - "Which lighting sequence is better: A or B?"
- Train a reward model: R(audio, lighting_sequence) -> scalar quality score
- Need approximately 10,000-50,000 pairwise comparisons (can be crowd-sourced)

**Phase 3: RL Fine-Tuning**
- Use PPO (Proximal Policy Optimization, Schulman et al., 2017) to fine-tune the base model
- Reward signal comes from the trained reward model
- KL divergence penalty prevents the policy from diverging too far from the supervised baseline

**Reward model architecture:**
```
Audio embedding (from MERT) + Lighting sequence embedding
    |
    v
Cross-attention transformer (4 layers)
    |
    v
Scalar reward score
```

**Practical consideration:** The reward model must evaluate *sequences* of lighting (not individual frames) because lighting quality is temporal -- it is about transitions, pacing, and narrative arc, not single-frame correctness.

#### 3.2.2 Simplified Feedback Mechanism

Full RLHF requires significant infrastructure. A simpler approach:

**Thumbs Up/Down per Section:**
1. During AI-controlled playback, the operator can press "good" or "bad" buttons
2. Each press is associated with the current audio features + lighting state + recent history (last 8 bars)
3. Positive signals increase the probability of similar decisions in similar audio contexts
4. Negative signals decrease those probabilities

**Implementation:** Maintain a lookup table of (audio_feature_cluster, lighting_action) -> quality_score. Use the quality score to bias the Markov chain transitions in `DecisionEngine`:

```python
# In decision_engine.py, modify MarkovChain.get_next():
def get_next(self, category, current, energy, audio_cluster=None):
    probs = self.transitions[category][current].copy()

    # Apply learned quality weights
    if audio_cluster is not None:
        for state in probs:
            quality = self.quality_table.get((audio_cluster, state), 0.0)
            probs[state] *= (1.0 + quality)  # quality in [-1, 1]

    # ... normalize and sample
```

### 3.3 Style Transfer for Lighting

#### 3.3.1 Concept

Different LDs have distinctive styles, just as visual artists have styles. Style transfer allows:
- Training on LD_A's aggressive EDM style
- Training on LD_B's smooth jazz style
- At inference: "Generate lighting in 70% LD_A's style but 30% LD_B's smoothness"

#### 3.3.2 Architecture: Style-Conditioned Generator

```
Audio features (MERT embedding)
    |
    v
Content Encoder (shared, captures music structure)
    |
    v
Content embedding (what is happening in the music)
    +
Style embedding (how to express it in lighting)
    |
    v
Conditional Generator (transformer decoder)
    |
    v
Lighting parameters
```

**Style embedding:** Each operator gets a learned style vector (64-128 dimensions). During training, the model receives the operator ID, which selects the corresponding style embedding. During inference, style embeddings can be interpolated:

```python
style = 0.7 * style_vectors["LD_aggressive_edm"] + 0.3 * style_vectors["LD_smooth_jazz"]
```

This is analogous to AdaIN (Adaptive Instance Normalization, Huang & Belongie, 2017) in visual style transfer, but applied to temporal lighting sequences.

#### 3.3.3 Style Dimensions

Learn interpretable style dimensions through disentangled representation learning (beta-VAE approach, Higgins et al., 2017):

| Dimension | Low Value | High Value |
|-----------|-----------|------------|
| Reactivity | Slow, smooth transitions | Fast, snappy beat-sync |
| Intensity | Dim, subtle | Bright, high contrast |
| Complexity | Simple, repetitive | Complex, varied |
| Color diversity | Monochromatic | Full spectrum |
| Movement energy | Static looks | Constant motion |
| Strobe usage | Never | Frequent |
| Symmetry | Asymmetric, chaotic | Symmetric, ordered |
| Audience focus | Stage-focused | Crowd-washing |

Users can then control these dimensions directly via sliders, without needing to reference specific operators.

### 3.4 Crowd Wisdom: Community Rating System

#### 3.4.1 Architecture

```
[AI generates lighting for track X]
    |
    v
[Video recording of result]
    |
    v
[Community rates: 1-5 stars + tags: "good drop", "boring verse", "great colors"]
    |
    v
[Ratings aggregated -> training signal]
```

**Rating granularity:** Rate entire shows (coarse signal) or rate 30-second segments (fine-grained, more useful for training).

**Tag taxonomy for lighting quality:**
- **Positive:** "great_sync", "perfect_drop", "beautiful_colors", "smooth_transitions", "creative", "immersive"
- **Negative:** "off_beat", "missed_drop", "boring", "too_busy", "wrong_colors", "seizure_inducing"

**Using ratings as training signal:**
1. Cluster (audio_features, lighting_decisions) pairs by audio similarity
2. For each cluster, rank lighting decisions by community rating
3. Train a preference model: given audio, prefer higher-rated lighting decisions
4. This becomes the reward model for RLHF (Section 3.2)

### 3.5 Professional Show Analysis

#### 3.5.1 Learning from Professional Light Shows

Professional concerts and festivals are recorded on video. This is a rich but noisy data source.

**Pipeline:**
```
Concert video (YouTube, etc.)
    |
    +-- Audio track extraction (ffmpeg)
    |       |
    |       v
    |   Audio analysis pipeline (MERT + structure + beat)
    |
    +-- Video frame extraction (2-5 fps)
            |
            v
        Light state estimation:
        - Average color per screen region (OpenCV)
        - Brightness/intensity estimation
        - Strobe detection (frame-to-frame luminance change)
        - Movement detection (optical flow on light beams)
        - Color temperature estimation
```

**Limitations:**
- Camera exposure/white balance distort colors
- Crowd shots do not show full rig
- Audio is mixed differently than live
- Impossible to extract exact DMX values

**What CAN be learned:**
- Timing of lighting changes relative to music structure
- Color palette choices per genre
- Strobe timing relative to drops
- Movement speed correlation with energy
- Blackout/flash timing
- Relative intensity curves per section type

This produces a weak but large-scale training signal. Use it for pre-training, then fine-tune on high-quality operator recordings.

#### 3.5.2 Specific Dataset Construction

Target: 1,000 professional show recordings across genres:
- 300 EDM (Tomorrowland, Ultra, etc.)
- 200 Rock (stadium tours)
- 150 Pop (arena tours)
- 100 Hip-Hop
- 100 Metal
- 50 Jazz
- 50 Classical
- 50 Mixed/Other

For each video:
1. Extract audio -> compute all audio features (beat, structure, emotion, genre, key)
2. Extract video -> estimate lighting state at 2fps
3. Align audio and lighting states
4. Label quality (professional show = high quality by default)

This produces approximately 500 hours of weakly-labeled training data.

### 3.6 Imitation Learning at Scale

#### 3.6.1 Behavioral Cloning vs. DAgger

**Behavioral Cloning (BC):** Directly supervised learning from demonstrations.
- Train: minimize L2 distance between model output and operator's DMX output
- Problem: compounding errors at inference time (model drifts from training distribution)

**DAgger (Dataset Aggregation, Ross et al., 2011):**
1. Train initial policy via BC
2. Let the policy run live
3. Have the expert correct mistakes (label what they would have done differently)
4. Add corrected data to training set
5. Retrain and repeat

DAgger is more robust but requires interactive expert participation.

#### 3.6.2 Inverse Reinforcement Learning (IRL)

Instead of cloning the operator's actions, learn the **reward function** that explains their behavior:

```
Given: Expert demonstrations (audio -> lighting)
Learn: R(audio_state, lighting_action) such that the expert's policy is approximately optimal
```

**Maximum Entropy IRL** (Ziebart et al., 2008):
- Assumes the expert acts approximately optimally with respect to an unknown reward
- Learns the reward as a linear combination of state-action features
- The learned reward can then generate optimal behavior for *new* situations

**Advantages over BC:**
- Generalizes better to unseen audio (learns the "why", not just the "what")
- Can generate creative solutions the expert never demonstrated
- Naturally handles ambiguity (multiple valid lighting choices for same audio)

**Feature engineering for IRL:**
```python
def state_action_features(audio_state, lighting_action):
    return [
        audio_state.energy * lighting_action.dimmer,            # energy-brightness correlation
        audio_state.is_beat * lighting_action.strobe_active,    # beat-strobe correlation
        audio_state.bass * lighting_action.bass_color_match,    # bass-color correlation
        audio_state.is_buildup * lighting_action.intensity_ramp,# buildup-ramp correlation
        abs(lighting_action.t - lighting_action.t_prev),        # smoothness penalty
        # ... 50-100 features
    ]
```

---

## 4. Cutting-Edge Model Architectures

### 4.1 Transformer-Based Audio-to-Lighting Models

#### 4.1.1 Architecture: LightFormer

A purpose-built transformer for audio-to-lighting generation:

```
ARCHITECTURE: LightFormer

Input Processing:
  Audio: mel-spectrogram (128 bins x T frames at 50Hz)
         -> Conv2D feature extractor (4 layers)
         -> Audio tokens (D=256, T/4 tokens)

  Context: [genre_embed, venue_embed, style_embed, fixture_config_embed]
           -> Context tokens (D=256, 4 tokens)

Encoder (Causal Transformer, 6 layers):
  - Multi-head self-attention (8 heads, causal mask)
  - Rotary positional embeddings (RoPE)
  - SwiGLU feed-forward (hidden_dim=1024)
  - Pre-norm (RMSNorm)
  - Sliding window attention (window=256 tokens = 20 seconds)

  Input: [context_tokens; audio_tokens]
  Output: encoded_features (D=256, T/4 tokens)

Decoder (Cross-Attention Transformer, 4 layers):
  - Self-attention over lighting history (causal)
  - Cross-attention to encoded audio features
  - Feed-forward with SwiGLU

  Input: Previous lighting states (last 4 seconds)
  Output: Next lighting state prediction

Output Heads:
  Head 1: Fixture intensities (N_fixtures x 1, sigmoid)
  Head 2: Fixture colors (N_fixtures x 3 RGB, sigmoid)
  Head 3: Fixture positions (N_movers x 2 pan/tilt, tanh scaled)
  Head 4: Effect parameters (strobe_probability, chase_speed, etc.)
  Head 5: Section transition probability (should we change look?)

Total parameters: ~15M (small enough for real-time inference)
```

#### 4.1.2 Key Design Decisions

**Why causal attention:** The model must generate lighting in real-time without seeing future audio. Causal masking ensures the model only attends to past and present audio.

**Why sliding window:** Full self-attention is O(n^2). With 50Hz audio tokens over a 5-minute song, that is 15,000 tokens. Sliding window attention (Beltagy et al., 2020) limits attention to a local window (20 seconds) plus global context tokens, reducing complexity to O(n * w) where w is the window size.

**Why separate heads per fixture attribute:** Different fixture attributes (intensity, color, position) operate on different timescales and have different dependencies. Intensity changes on beats; color changes on sections; position changes on phrases. Separate heads allow learning these different temporal patterns.

**Loss function:**
```
L_total = L_intensity + L_color + L_position + L_effect + lambda * L_smoothness + mu * L_diversity

Where:
  L_intensity = MSE(predicted_dimmer, target_dimmer)
  L_color     = MSE(predicted_RGB, target_RGB) in perceptual color space (CIE Lab)
  L_position  = MSE(predicted_pan_tilt, target_pan_tilt)
  L_effect    = BCE(predicted_strobe, target_strobe)
  L_smoothness = MSE(delta_predicted, delta_target)  # Penalize jittery output
  L_diversity  = -entropy(predicted_effect_distribution)  # Encourage varied choices
```

### 4.2 Diffusion Models for Lighting Generation

#### 4.2.1 Concept

Diffusion models (Ho et al., 2020; Song et al., 2021) generate samples by iteratively denoising from pure noise. Applied to lighting:

```
Forward process: clean_lighting_sequence -> progressively noisier -> pure noise
Reverse process: pure noise -> iterative denoising conditioned on audio -> clean_lighting_sequence
```

**Why diffusion for lighting:**
1. **Diversity:** Given the same audio, a diffusion model can generate *different* valid lighting sequences by starting from different noise seeds. This prevents the AI from always choosing the same response.
2. **Quality:** Diffusion models are known for high-quality generation.
3. **Controllability:** Classifier-free guidance allows steering generation toward desired properties (e.g., "more aggressive", "more colorful").

#### 4.2.2 Architecture: LightDiffusion

```
ARCHITECTURE: LightDiffusion

Conditioning:
  Audio features (MERT embeddings at 2Hz)
  Genre embedding
  Style embedding
  Section label (verse, chorus, drop, etc.)

Diffusion Target:
  Lighting sequence: (T_steps x N_fixtures x C_channels)
  Where T_steps = 16 (8 seconds at 2Hz)
        N_fixtures = abstract fixture groups (not raw fixtures)
        C_channels = 7 (dimmer, R, G, B, pan, tilt, strobe)

Denoiser Network: 1D U-Net with cross-attention
  - Temporal convolutions (1D) along time axis
  - Cross-attention to audio conditioning
  - Timestep embedding (sinusoidal)
  - 4 resolution levels (16 -> 8 -> 4 -> 2 -> 4 -> 8 -> 16)

Diffusion Schedule:
  - 1000 steps during training (standard DDPM)
  - 20-50 steps during inference (DDIM for speed)

Inference time: ~50ms for 8-second lighting plan (on GPU)
```

**Classifier-free guidance for style control:**
During training, randomly drop conditioning information with probability 0.1 (unconditional generation). During inference:

```
output = unconditional_output + guidance_scale * (conditional_output - unconditional_output)
```

Higher guidance_scale = more strongly following the audio conditioning.

#### 4.2.3 Practical Consideration: Latency

Diffusion models are iterative. Even with DDIM (50 steps), generating one 8-second lighting plan takes approximately 50ms on a modern GPU. The solution is a **rolling generation buffer:**

1. Generate 8-second plan at time T
2. Begin executing first 4 seconds
3. At T+4s, generate next 8-second plan (overlapping by 4 seconds)
4. Cross-fade between plans in the overlap region

This hides generation latency while maintaining temporal coherence.

### 4.3 Multimodal Models

#### 4.3.1 Beyond Audio: Additional Input Modalities

| Modality | Source | Information | Integration |
|----------|--------|-------------|-------------|
| **Audio** | Microphone/line-in | Music content | Primary input |
| **Crowd video** | Camera | Energy level, density, movement | Secondary input for audience-reactive lighting |
| **Venue metadata** | Configuration | Room size, fixture count/type, ceiling height | Context conditioning |
| **Time of show** | Clock | Early set = warm up, peak time, last song | Pacing adjustment |
| **DJ/performer input** | MIDI controller | Manual cues, upcoming track info | Override/assist |

#### 4.3.2 Crowd Energy Detection

Use the existing YOLOv9 in `model_manager.py` or a lighter model for:

```
Camera frame -> Person detection -> Density estimation
Camera frame -> Optical flow -> Movement energy
Camera frame -> Gesture recognition -> Hands up / jumping detection

Crowd energy score = weighted_sum(density, movement, gesture_score)
```

This enables: "Crowd is going wild -> increase intensity and strobe" or "Crowd energy dropping -> pull back, save big effects for later"

#### 4.3.3 Multimodal Fusion Architecture

```
Audio branch:    MERT embeddings (256D, 2Hz)
Crowd branch:    MobileNetV3 features (128D, 2Hz from camera)
Context branch:  [genre, venue, time_of_show, fixture_config] embeddings (64D)
    |
    v
Multi-modal fusion transformer (4 layers):
  - Audio tokens attend to all modalities via cross-attention
  - Crowd tokens attend to audio (crowd reacts to music)
  - Context tokens attend to everything
    |
    v
Fused representation (256D, 2Hz)
    |
    v
Lighting generation head (from Section 4.1)
```

### 4.4 Temporal Models for Real-Time Sequence Generation

#### 4.4.1 Architecture Comparison

| Architecture | Latency | Memory | Long-Range | Training Speed | Best For |
|-------------|---------|--------|------------|----------------|----------|
| LSTM | Low | Medium | ~100 steps | Medium | Baseline sequential |
| TCN | Very low | Low | ~1000 steps (dilated) | Fast | Real-time streaming |
| Transformer | Medium | High | Unlimited (with RoPE) | Medium | Best quality |
| Mamba (S4/S6) | Very low | Low | ~10000 steps | Fast | Long sequences |
| RWKV | Very low | Low | ~10000 steps | Fast | Efficient attention alternative |

#### 4.4.2 Recommended: State Space Model (Mamba) for Streaming

**Mamba** (Gu & Dao, 2023) is a selective state space model with:
- **Linear-time inference** (vs. quadratic for transformers)
- **Constant memory** during generation (vs. growing KV cache for transformers)
- **Long-range dependencies** through selective state propagation
- **Hardware-efficient** via custom CUDA kernels

**Why Mamba for real-time lighting:**
- Must process audio continuously for hours (DJ set)
- Cannot accumulate memory over time (transformer KV cache grows)
- Needs consistent latency regardless of position in set
- Long-range dependencies matter (callback to earlier musical themes)

**Architecture:**
```
Audio features (256D at 50Hz)
    |
    v
Mamba block x 6:
  - Linear projection (256 -> 512)
  - 1D convolution (kernel=4)
  - SSM layer (state_dim=16, dt_rank=auto)
  - Gated output
  - Residual connection
    |
    v
Lighting prediction heads (same as Section 4.1)

Parameters: ~8M
Inference: <5ms per frame on CPU, <1ms on GPU
```

### 4.5 Reinforcement Learning for Lighting

#### 4.5.1 RL Formulation

**State:** Audio features (MERT embedding + beat info + structure + emotion)
**Action:** Lighting parameters (N_fixtures x channels, discretized or continuous)
**Reward:** Composite reward from multiple signals (beat sync, energy correlation, structure matching, smoothness, variety, genre appropriateness, learned reward model, human feedback)

#### 4.5.2 RL Algorithm: SAC (Soft Actor-Critic)

**SAC** (Haarnoja et al., 2018) is preferred over PPO for lighting because:
- Continuous action space (lighting parameters are continuous)
- Maximum entropy objective encourages exploration (diverse lighting choices)
- Off-policy (can learn from replayed operator demonstrations)
- Stable training

**Training loop:**
1. Initialize policy from supervised pre-training (BC on operator data)
2. Run policy in simulation (audio playback + virtual lighting visualizer)
3. Collect reward signals (automated metrics + occasional human feedback)
4. Update policy via SAC
5. Periodically evaluate on held-out tracks

### 4.6 Few-Shot / Zero-Shot Adaptation

#### 4.6.1 Adapting to New Fixture Types

The current system uses 18 fixtures (`fixture_groups.py` `create_demo_rig()`) with specific channel mappings. A real venue may have 4 fixtures or 200.

**Approach: Abstract Lighting Intentions**

Instead of predicting raw fixture values, predict abstract intentions:

```python
@dataclass
class LightingIntention:
    # Spatial
    coverage: float          # 0 = narrow spot, 1 = full wash
    symmetry: float          # 0 = asymmetric, 1 = symmetric
    focus_point: tuple       # (x, y, z) Where light is concentrated

    # Temporal
    base_intensity: float    # Overall brightness
    beat_response: float     # How strongly to flash on beats
    movement_speed: float    # How fast fixtures move
    movement_complexity: float # How complex the movement pattern

    # Color
    primary_hue: float       # 0-360
    secondary_hue: float     # 0-360
    saturation: float        # 0-1
    color_variation: float   # How much color varies across fixtures

    # Effects
    strobe_probability: float
    chase_speed: float
    blackout: bool
```

A **rig adapter** then maps intentions to specific fixture commands:

```
LightingIntention -> RigAdapter(fixture_config) -> DMX values per fixture
```

The rig adapter is rule-based (not learned) and handles:
- Mapping coverage to fixture selection (narrow = few fixtures, wide = all)
- Mapping focus_point to pan/tilt for available movers
- Mapping colors to fixtures with RGB vs. CMY vs. color wheel
- Distributing chase across available fixture count

This means the AI model only needs to learn intentions, and the adapter handles any rig.

#### 4.6.2 Few-Shot Venue Adaptation

When deploying to a new venue:

1. **Zero-shot:** Use the pre-trained model + rig adapter. Should work reasonably well.
2. **Few-shot (5-10 minutes):** Operator runs one song manually. System calibrates actual dimmer output range, pan/tilt range for the space, which fixtures are "upstage" vs "downstage" vs "audience", and color temperature characteristics.
3. **Full adaptation (1 hour):** Operator runs a full set. System fine-tunes style preferences for this venue.

Use **LoRA** (Low-Rank Adaptation, Hu et al., 2022) for efficient fine-tuning: freeze the base model, train small adapter matrices. A venue-specific adapter is approximately 100KB and can be saved/loaded instantly.

---

## 5. Real-Time Inference Constraints

### 5.1 Latency Budget

```
Audio capture:         ~5ms (buffer size dependent)
Audio analysis:        ~10ms (FFT + features)
ML inference:          ~15ms (target)
Decision/planning:     ~5ms
DMX frame generation:  ~2ms
ArtNet transmission:   ~5ms
Fixture response:      ~50ms (mechanical, unavoidable for movers)
                      --------
Total:                ~92ms (audio-to-physical-light)
```

The ML inference budget is **15ms maximum**. This is tight but achievable.

### 5.2 Model Quantization and Optimization

#### 5.2.1 ONNX Runtime

Convert PyTorch models to ONNX for optimized inference:

```python
# Export LightFormer to ONNX
torch.onnx.export(
    model,
    dummy_input,
    "lightformer.onnx",
    opset_version=17,
    dynamic_axes={"audio": {0: "batch", 1: "time"}}
)

# Run with ONNX Runtime
import onnxruntime as ort
session = ort.InferenceSession("lightformer.onnx", providers=['CUDAExecutionProvider'])
```

ONNX Runtime typically provides 2-4x speedup over native PyTorch inference.

#### 5.2.2 INT8 Quantization

For CPU deployment (venues without GPU):

```python
from onnxruntime.quantization import quantize_dynamic

quantize_dynamic(
    "lightformer.onnx",
    "lightformer_int8.onnx",
    weight_type=QuantType.QInt8
)
```

INT8 quantization typically provides:
- 2-4x further speedup on CPU
- Less than 1% quality degradation for this task
- Approximately 4x reduction in model size

### 5.3 Model Size Targets

| Component | Parameters | Size (FP32) | Size (INT8) | Inference Time (CPU) | Inference Time (GPU) |
|-----------|-----------|-------------|-------------|---------------------|---------------------|
| Audio Feature Extractor (MERT-small) | 25M | 100MB | 25MB | ~50ms/chunk | ~5ms/chunk |
| Structure Analyzer | 5M | 20MB | 5MB | ~15ms/chunk | ~2ms/chunk |
| LightFormer | 15M | 60MB | 15MB | ~20ms/frame | ~3ms/frame |
| Emotion Model | 3M | 12MB | 3MB | ~5ms/chunk | ~1ms/chunk |
| **Total** | **48M** | **192MB** | **48MB** | - | - |

**Note:** MERT-small is the bottleneck. Options:
1. Run MERT at lower frequency (every 500ms instead of every frame)
2. Use a distilled version (MERT-tiny, ~5M params)
3. Use pre-computed MERT features for known tracks (cache)

### 5.4 Streaming Inference Architecture

```
Audio Input (continuous stream)
    |
    v
Ring Buffer (4 seconds)
    |
    +-- Every 23ms (1 hop): FFT features, beat detection (lightweight)
    |                            |
    |                            v
    |                     [Low-latency path: beat -> strobe trigger, <5ms]
    |
    +-- Every 100ms: Audio embedding (MERT-small)
    |                     |
    |                     v
    |              [Medium-latency path: emotion, genre, key -> color, intensity]
    |
    +-- Every 500ms: Structure analysis, anticipation prediction
                          |
                          v
                   [High-latency path: section detection -> movement pattern, effect selection]

All paths feed into:
    LightingStateMachine
        |
        v
    DMX frame generation (every 25ms = 40Hz as per config.DMX_FPS)
```

This three-tier architecture ensures:
- Beat-reactive effects (strobe, flash) happen within 5ms of the beat
- Color and intensity changes happen within 100ms
- Structural changes (movement pattern, effect selection) happen within 500ms
- All within the 15ms ML budget per path because paths run at different frequencies

### 5.5 Edge Deployment

For venues without powerful GPUs:

**Option 1: NVIDIA Jetson Orin Nano ($200)**
- 40 TOPS INT8 inference
- Sufficient for all models at target latency
- Low power (15W)
- Runs ONNX Runtime with CUDA

**Option 2: Intel NUC with OpenVINO**
- Use OpenVINO for optimized CPU inference
- Quantized INT8 models
- Sufficient for all models except MERT-full (use distilled)

**Option 3: Cloud-Edge Hybrid**
- Lightweight models (beat detection, strobe timing) run locally
- Heavy models (MERT, structure analysis) run in cloud with 50-100ms latency
- Fallback to local-only if connection drops

---

## 6. Training Data Strategy

### 6.1 Building Large-Scale Paired Datasets

#### 6.1.1 Data Sources and Scale Targets

| Source | Paired Data? | Quality | Volume Target | Effort |
|--------|-------------|---------|---------------|--------|
| ILS operator recordings | Yes (perfect pairing) | Varies by operator | 100 hours | Medium |
| Professional show videos | Weak (estimated pairing) | High (professional) | 500 hours | High |
| MIDI lighting data (grandMA2 exports) | Yes (perfect pairing) | High | 50 hours | Medium |
| Synthetic generation | Yes (perfect pairing) | Medium (rule-based) | 10,000 hours | Low |
| Community contributions | Yes (perfect pairing) | Varies | 1,000 hours (over time) | Ongoing |

#### 6.1.2 Enhanced Training Recorder

Extend the current `TrainingRecorder` to capture richer data:

```python
@dataclass
class EnhancedAudioFrame:
    timestamp: float
    bpm: float
    energy: float
    bass: float
    mid: float
    high: float
    valence: float
    arousal: float
    spectral_flux: float
    is_beat: bool
    beat_position: int
    spectrum: List[float]
    # NEW: Rich features
    mert_embedding: List[float]       # 256D from MERT
    section_label: str                 # "verse", "chorus", "drop", etc.
    section_progress: float            # 0.0 to 1.0 within section
    genre: str                         # Detected genre
    key: str                           # Detected key (e.g., "Am")
    chord: str                         # Current chord (e.g., "F")
    groove_type: str                   # "straight", "swing", "shuffle"
    tension: float                     # Harmonic tension (0-1)
    phrase_position: int               # Bar within phrase (1-8)
    bars_to_next_section: int          # Predicted bars until section change

@dataclass
class EnhancedLightingFrame:
    timestamp: float
    fixtures: List[Dict]
    dmx_frame: List[int]
    # NEW: Abstract intentions
    intention: LightingIntention       # Abstract representation
    active_effects: List[str]          # Which LFO effects are active
    decision_engine_state: str         # Current state from decision engine
    operator_id: str                   # Who is operating
    quality_rating: Optional[float]    # Post-session quality rating
```

### 6.2 Data Augmentation for Lighting

#### 6.2.1 Audio Augmentation

| Augmentation | Effect on Audio | Required Lighting Adjustment |
|-------------|----------------|------------------------------|
| Time stretch (0.8x-1.2x) | Changes tempo | Scale all timing proportionally |
| Pitch shift (+/- 2 semitones) | Changes key | Shift color hue proportionally |
| Volume scaling | Changes energy | Scale intensity proportionally |
| EQ (boost bass) | Changes frequency balance | Adjust color temperature |
| Noise addition (crowd noise) | Slight degradation | No change (robustness) |

#### 6.2.2 Lighting Augmentation

| Augmentation | Description | Purpose |
|-------------|-------------|---------|
| Color rotation | Shift all hues by random offset | Learn structure independent of color |
| Intensity scaling | Scale all dimmers by 0.5-1.5x | Robustness to different brightness preferences |
| Fixture permutation | Randomly swap fixture assignments | Generalize across rig layouts |
| Temporal jitter | Shift lighting +/- 50ms | Robustness to slight timing differences |
| Mirror | Swap left/right fixtures | Symmetry augmentation |
| Effect substitution | Replace one movement pattern with similar one | Learn equivalence classes |

#### 6.2.3 Contrastive Augmentation

Create negative examples by misaligning audio and lighting:

```
Positive pair: (audio_chorus, lighting_chorus)  -- from same moment
Negative pair: (audio_chorus, lighting_verse)   -- mismatched
Negative pair: (audio_chorus, lighting_random)  -- random
```

Train with contrastive loss to ensure the model understands the semantic relationship between audio and lighting, not just temporal patterns.

### 6.3 Synthetic Data Generation

#### 6.3.1 Rule-Based Synthetic Generator

```python
class SyntheticLightingGenerator:
    """Generates lighting from audio using expert rules, for pre-training."""

    def generate(self, audio_features, genre):
        # Rule 1: Intensity follows energy
        intensity = 0.3 + 0.7 * audio_features.energy

        # Rule 2: Color follows emotion
        hue = self.emotion_to_hue(audio_features.valence, audio_features.arousal, genre)

        # Rule 3: Movement speed follows BPM and energy
        movement_speed = audio_features.bpm / 240 * audio_features.energy

        # Rule 4: Strobe on drops only
        strobe = 1.0 if audio_features.is_drop else 0.0

        # Rule 5: Big changes at section boundaries
        if audio_features.is_section_boundary:
            hue = (hue + 180) % 360  # Complementary color

        # ... 50 more rules encoding professional LD knowledge
        return LightingFrame(intensity, hue, movement_speed, strobe, ...)
```

This generates infinite training data. Quality is medium (rules are rigid), but it provides a solid pre-training foundation. Fine-tune on real operator data afterward.

### 6.4 Cross-Rig Generalization

The key to cross-rig generalization is training on **abstract lighting intentions** rather than raw DMX values (see Section 4.6.1). The conversion pipeline extracts coverage, average intensity, color histogram, movement energy, symmetry, and chase direction from raw DMX frames. The rig adapter maps intentions back to any specific fixture configuration.

---

## 7. Concrete Implementation Plan: Top 3 Approaches

### 7.1 APPROACH 1: LightFormer -- Transformer Audio-to-Lighting Model

This is the primary recommended approach. It provides the highest quality output and most flexible architecture.

#### 7.1.1 Architecture Diagram

```
                        +------------------+
                        |  Audio Input     |
                        |  (16kHz stream)  |
                        +--------+---------+
                                 |
                    +------------+------------+
                    |                         |
            +-------v-------+       +--------v--------+
            | MERT-Small    |       | Beat/Structure  |
            | (frozen)      |       | Analyzer        |
            | Runs at 2Hz   |       | (All-In-One)    |
            +-------+-------+       +--------+--------+
                    |                         |
                    v                         v
            +-------+-------+       +--------+--------+
            | Audio Embed   |       | Beat, Section,  |
            | (256D tokens) |       | Key, Chord info |
            +-------+-------+       +--------+--------+
                    |                         |
                    +-----+-------+-----------+
                          |       |
                    +-----v-------v-----+
                    |  Context Tokens   |
                    |  [genre, style,   |
                    |   venue, section]  |
                    +--------+----------+
                             |
                    +--------v----------+
                    |  LightFormer      |
                    |  Encoder          |
                    |  (6-layer causal  |
                    |   transformer)    |
                    +--------+----------+
                             |
                    +--------v----------+
                    |  LightFormer      |
                    |  Decoder          |
                    |  (4-layer cross-  |
                    |   attention)      |
                    +--------+----------+
                             |
              +--------------+---------------+
              |              |               |
    +---------v---+  +------v------+  +-----v-------+
    | Intensity   |  | Color Head  |  | Position    |
    | Head        |  | (N x RGB)   |  | Head        |
    | (N x dim)   |  |             |  | (M x pan/   |
    |             |  |             |  |  tilt)       |
    +------+------+  +------+------+  +------+------+
           |                |                |
           +-------+--------+-------+--------+
                   |                |
           +-------v-------+ +-----v---------+
           | Lighting      | | Rig Adapter   |
           | Intention     | | (rule-based)  |
           +-------+-------+ +-----+---------+
                   |                |
                   +-------+--------+
                           |
                   +-------v--------+
                   |  DMX Frame     |
                   |  Generator     |
                   +-------+--------+
                           |
                   +-------v--------+
                   |  ArtNet Output |
                   +----------------+
```

#### 7.1.2 Training Pipeline

**Phase 1: Pre-Training on Synthetic Data (Week 1-2)**
- Generate 10,000 hours of synthetic audio-lighting pairs
- Pre-train LightFormer to convergence
- Loss: MSE on intensity + color + position

**Phase 2: Pre-Training on Professional Show Data (Week 3-4)**
- Process 500 hours of professional concert videos
- Extract weak audio-lighting pairs
- Fine-tune LightFormer on this data
- Add contrastive loss for audio-lighting alignment

**Phase 3: Fine-Tuning on Operator Data (Week 5-6)**
- Collect 100+ hours from multiple operators via enhanced TrainingRecorder
- Fine-tune with operator style embeddings
- Add smoothness and diversity losses

**Phase 4: RLHF Refinement (Week 7-8)**
- Collect 10,000 pairwise human preferences
- Train reward model
- PPO fine-tuning with reward model

**Phase 5: Deployment and Continuous Learning (Ongoing)**
- Deploy with LoRA adapters for per-venue customization
- Continuous data collection from shows
- Monthly model updates

#### 7.1.3 Integration with Existing Codebase

Files to modify:

1. **`backend/app/services/ml/model_manager.py`** - Add _load_mert(), _load_lightformer(), _load_structure_analyzer(), predict_lighting() methods. Remove HuBERT dependence for emotion.

2. **`backend/app/services/audio/audio_analyzer.py`** - Add compute_mert_embedding(), detect_structure(), detect_genre(), detect_key_chord() methods. Expand process_chunk().

3. **`backend/app/services/effects/decision_engine.py`** - Replace _detect_structure_changes() with ML-based structure detection. Replace MarkovChain with LightFormer inference. Add anticipation_buffer.

4. **`backend/app/services/ml/training_recorder.py`** - Upgrade to EnhancedAudioFrame and EnhancedLightingFrame. Add LightingIntention extraction, operator ID, quality rating, ShowRecorder.

5. **NEW: `backend/app/services/ml/rig_adapter.py`** - LightingIntention dataclass, RigAdapter class, IntentionExtractor class.

6. **NEW: `backend/app/services/ml/lightformer.py`** - LightFormer model definition, ONNX Runtime inference wrapper, streaming inference with state management.

7. **`backend/app/services/effects/effects_engine.py`** - Add AI-driven mode alongside existing LFO and manual modes. Integrate LightFormer predictions into _update_fixtures(). Add smooth blending between AI and manual control.

8. **`backend/app/core/config.py`** - Add model paths for MERT, LightFormer, All-In-One. Add AI mode configuration.

#### 7.1.4 Compute Requirements

**Training:** 4x NVIDIA A100 (40GB), ~200 GPU-hours, ~$800 on cloud
**Inference:** Minimum Intel i7 CPU (INT8, ~30ms), Recommended any NVIDIA GPU (~5ms)

#### 7.1.5 Timeline

| Week | Milestone | Deliverable |
|------|-----------|-------------|
| 1 | MERT integration | Audio embeddings available in audio_analyzer.py |
| 2 | All-In-One integration | Real-time structure detection replacing energy thresholds |
| 3 | Synthetic data pipeline | 10K hours of synthetic training data |
| 4 | LightFormer v1 training | First model trained on synthetic data |
| 5 | Professional show pipeline | 500 hours of weakly-labeled data processed |
| 6 | LightFormer v2 training | Model fine-tuned on real + synthetic data |
| 7 | Rig adapter + intention layer | Cross-rig generalization working |
| 8 | ONNX export + optimization | Real-time inference at <15ms |
| 9 | Enhanced training recorder | Multi-operator data collection ready |
| 10 | Operator fine-tuning | Style-conditioned model working |
| 11 | RLHF pipeline | Preference collection + reward model |
| 12 | Full integration | AI mode available in effects engine |

---

### 7.2 APPROACH 2: Mamba-Based Real-Time Streaming Model

This approach prioritizes minimal latency and CPU-deployable inference over maximum quality.

#### 7.2.1 Architecture Diagram

```
                    +------------------+
                    |  Audio Input     |
                    |  (44.1kHz)       |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  Feature Extract |
                    |  (mel-spec,      |
                    |   chroma, onset) |
                    |  128D at 50Hz    |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  Conv1D Front-End|
                    |  (3 layers,      |
                    |   128->256D)     |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  Mamba Blocks    |
                    |  x 6             |
                    |  (256D, SSM      |
                    |   state_dim=16)  |
                    |                  |
                    |  Constant memory |
                    |  Linear time     |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  Output Heads    |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  Rig Adapter     |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  DMX Output      |
                    +------------------+

  Parameters: ~8M
  Inference: <5ms/frame (CPU), <1ms/frame (GPU)
  Memory: Constant (no growing KV cache)
```

#### 7.2.2 Training Pipeline

**Phase 1 (Week 1):** Feature engineering using existing audio_analyzer.py features (~150D)
**Phase 2 (Week 2-3):** Synthetic pre-training on same data pipeline as Approach 1
**Phase 3 (Week 4-5):** Operator fine-tuning on real data
**Phase 4 (Week 6):** ONNX export, INT8 quantization, deployment

#### 7.2.3 Advantages

- No large pre-trained model dependency (no MERT)
- Constant memory during inference (critical for 8-hour DJ sets)
- CPU-deployable without quality sacrifice
- Simpler training pipeline, faster iteration

#### 7.2.4 Disadvantages

- Lower music understanding (handcrafted features vs. learned embeddings)
- No anticipation capability
- Less creative output (smaller model capacity)

#### 7.2.5 Compute Requirements

**Training:** 1x NVIDIA A100, ~20 GPU-hours, ~$60 on cloud
**Inference:** Minimum Intel i5 CPU with 8GB RAM. No GPU required.

---

### 7.3 APPROACH 3: Hybrid RL Agent with Reward Shaping

This approach uses reinforcement learning to discover creative lighting strategies beyond what any human operator demonstrates.

#### 7.3.1 Architecture Diagram

```
                    +-------------------+
                    |  Audio Input      |
                    +--------+----------+
                             |
                    +--------v----------+
                    |  MERT-Small       |
                    |  (frozen encoder) |
                    +--------+----------+
                             |
                    +--------v----------+
                    |  State Encoder    |
                    |  (2-layer MLP)    |
                    |  Audio + History  |
                    |  -> 256D state    |
                    +--------+----------+
                             |
              +--------------+---------------+
              |                              |
    +---------v-----------+     +------------v----------+
    |  Actor Network      |     |  Critic Network       |
    |  (Policy)           |     |  (Value Function)     |
    |  3-layer MLP        |     |  3-layer MLP          |
    |  256->256->action   |     |  256->256->1          |
    +----------+----------+     +------------------------+
               |
    +----------v----------+
    |  Composite Reward   |
    |  (automatic metrics |
    |   + learned model   |
    |   + human feedback) |
    +---------------------+
```

#### 7.3.2 Training Pipeline

**Phase 1 (Week 1-3):** Build simulation environment (audio playback + reward computation at 1000x real-time)
**Phase 2 (Week 4):** Pre-train actor via behavioral cloning on operator data
**Phase 3 (Week 5-7):** SAC training with automatic reward metrics
**Phase 4 (Week 8-9):** Collect 5,000 A/B human preference comparisons, train reward model
**Phase 5 (Week 10-11):** RL fine-tuning with full composite reward
**Phase 6 (Week 12):** ONNX export, deployment, integration

#### 7.3.3 Compute Requirements

**Training:** 2x NVIDIA A100, ~500 GPU-hours (RL is sample-inefficient), ~$2,000 on cloud
**Inference:** Same as Approach 2 (small actor network, CPU-deployable)

---

## 8. Integration Roadmap

### 8.1 Recommended Strategy: Incremental Approach

Do not attempt to implement all three approaches simultaneously. Instead:

**Month 1-2:** Implement Approach 2 (Mamba) as a quick win
- Provides immediate improvement over current Markov chain
- CPU-deployable, minimal infrastructure
- Gets the enhanced audio feature pipeline built

**Month 3-4:** Implement Approach 1 (LightFormer) components
- Add MERT for rich audio embeddings
- Add All-In-One for structure detection
- Train LightFormer on accumulated data

**Month 5-6:** Add Approach 3 (RL) components
- Build simulation environment using LightFormer as teacher
- Train RL agent for creative exploration
- Implement RLHF pipeline

### 8.2 Backward Compatibility

All new AI features must be **opt-in**. The existing system must continue working. Add a mode selector:

```python
class AIMode(Enum):
    MANUAL = "manual"           # Current behavior: LFO + manual control
    MARKOV = "markov"           # Current auto mode: decision_engine.py Markov chain
    MAMBA = "mamba"             # Approach 2: lightweight streaming model
    LIGHTFORMER = "lightformer" # Approach 1: transformer model
    RL_AGENT = "rl_agent"       # Approach 3: RL agent
    HYBRID = "hybrid"           # Blend AI with manual overrides
```

### 8.3 A/B Testing Framework

Build an A/B testing system to measure improvement:

1. Play the same track through two AI modes
2. Record both lighting outputs
3. Show side-by-side videos to evaluators
4. Track win rates per mode per genre

This data also feeds back into the RLHF reward model.

### 8.4 Key Performance Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Beat sync accuracy | >95% of beats trigger visible response within 50ms | Automated: compare beat times with intensity changes |
| Section detection accuracy | >80% F1 on labeled test set | Automated: compare predicted vs. ground-truth sections |
| Latency (audio to DMX) | <50ms for beat response, <200ms for color/structure | Automated: timestamp logging |
| Human preference win rate | >70% vs. current Markov chain | A/B testing |
| Cross-genre performance | <10% quality degradation on unseen genres | Genre-stratified evaluation |
| Cross-rig generalization | <15% quality degradation on unseen fixture counts | Test with 4, 8, 18, 36 fixture rigs |
| Continuous operation | Stable for 8+ hours (no memory leaks, no quality degradation) | Stress test |

### 8.5 Research References

| Reference | Year | Relevance |
|-----------|------|-----------|
| Kim, T. "All-In-One Music Structure Analyzer" | 2023 | Section/beat/tempo detection |
| Li, Y. et al. "MERT: Acoustic Music Understanding Model at Scale" | 2023 | Music-native audio embeddings |
| Nieto, O. & Bello, J. "Systematic Exploration of Computational Music Structure Research" | 2016 | MSAF framework |
| Nieto, O. et al. "The Harmonix Set" | 2019 | Training dataset for structure |
| Koutini, K. et al. "Efficient Training of Audio Transformers with Patchout" | 2022 | PaSST for audio tagging |
| Bogdanov, D. et al. "The MTG-Jamendo Dataset" | 2019 | Genre/mood training data |
| Aljanaki, A. et al. "Developing a Benchmark for Emotional Analysis of Music" | 2017 | DEAM emotion dataset |
| Gu, A. & Dao, T. "Mamba: Linear-Time Sequence Modeling with Selective State Spaces" | 2023 | Mamba architecture |
| Haarnoja, T. et al. "Soft Actor-Critic" | 2018 | SAC algorithm |
| Schulman, J. et al. "Proximal Policy Optimization Algorithms" | 2017 | PPO for RLHF |
| Ouyang, L. et al. "Training Language Models to Follow Instructions with Human Feedback" | 2022 | RLHF methodology |
| McMahan, B. et al. "Communication-Efficient Learning of Deep Networks from Decentralized Data" | 2017 | Federated learning |
| Ross, S. et al. "A Reduction of Imitation Learning to No-Regret Online Learning" | 2011 | DAgger |
| Ziebart, B. et al. "Maximum Entropy Inverse Reinforcement Learning" | 2008 | IRL |
| Ho, J. et al. "Denoising Diffusion Probabilistic Models" | 2020 | Diffusion models |
| Hu, E. et al. "LoRA: Low-Rank Adaptation of Large Language Models" | 2022 | Efficient fine-tuning |
| Huang, X. & Belongie, S. "Arbitrary Style Transfer with Adaptive Instance Normalization" | 2017 | Style transfer |
| Higgins, I. et al. "beta-VAE" | 2017 | Disentangled representations |
| Beltagy, I. et al. "Longformer" | 2020 | Sliding window attention |
| Chen, T. & Su, L. "Harmony Transformer" | 2019 | Chord recognition |
| Bock, S. et al. "madmom" | 2016 | Audio analysis library |
| Davies, M. & Bock, S. "TCN for Beat Tracking" | 2019 | TCN beat tracking |
| Zhao, Y. & Chen, Z. "BeatTransformer" | 2024 | Transformer beat tracking |
| Smith, J. et al. "SALAMI Dataset" | 2011 | Structure annotations |
| Goto, M. et al. "RWC Music Database" | 2002 | Music dataset |
| Zeng, M. et al. "MusicBERT" | 2021 | Symbolic music understanding |
| Zhang, K. et al. "PMEmo" | 2018 | Music emotion dataset |
| McFee, B. & Ellis, D. "Analyzing Song Structure with Spectral Clustering" | 2014 | Structure analysis |
| Foote, J. "Automatic Audio Segmentation Using Audio Novelty" | 2000 | Novelty segmentation |

---

## Summary

The current ILS has a solid foundation with its 4-layer effects engine, LFO system, and basic audio analysis. The three proposed approaches build on this foundation:

1. **LightFormer (Approach 1):** Highest quality, requires GPU, 12-week timeline. Best for venues that want the best possible AI lighting. Uses MERT + transformer + RLHF.

2. **Mamba Streaming (Approach 2):** Fastest to deploy, CPU-friendly, 6-week timeline. Best for getting AI lighting out quickly across many venues. Uses handcrafted features + SSM.

3. **RL Agent (Approach 3):** Most creative potential, longest training, 12-week timeline. Best for discovering novel lighting approaches that surpass human operators. Uses SAC + reward learning.

The recommended path is to implement Approach 2 first for quick wins, then layer in Approach 1 components for higher quality, and finally add Approach 3 for creative exploration. All approaches share the common infrastructure of enhanced audio features, abstract lighting intentions, and the rig adapter layer.
