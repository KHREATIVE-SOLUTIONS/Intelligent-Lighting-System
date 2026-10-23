"""
Audio Input Hygiene
===================

Live audio arrives from drivers and network clients that are not trusted. An
empty buffer used to raise inside the FFT, and a single NaN failed the result
schema and sat in the median beat history for seconds.
"""

import numpy as np
import pytest

from app.services.audio.audio_analyzer import AudioAnalyzer


@pytest.fixture
def analyzer():
    return AudioAnalyzer()


@pytest.mark.parametrize("chunk", [
    np.array([], dtype=np.float32),
    np.full(2048, np.nan, dtype=np.float32),
    np.concatenate([np.zeros(2047, dtype=np.float32), [np.inf]]).astype(np.float32),
    np.linspace(-3.0, 3.0, 2048, dtype=np.float32),
])
async def test_hostile_chunks_are_analysed_not_raised(analyzer, chunk):
    result = await analyzer.process_chunk(chunk)
    assert "beat" in result and "frequency" in result


async def test_a_nan_chunk_does_not_poison_the_onset_history(analyzer):
    rng = np.random.default_rng(0)
    for _ in range(10):
        await analyzer.process_chunk(rng.uniform(-0.1, 0.1, 2048).astype(np.float32))
    await analyzer.process_chunk(np.full(2048, np.nan, dtype=np.float32))
    assert np.all(np.isfinite(np.array(analyzer.onset_history, dtype=np.float64)))
    assert np.all(np.isfinite(np.array(analyzer.rms_history, dtype=np.float64)))
