"""
Log-mel frontend for the EfficientAT checkpoints.

The evaluation path of EfficientAT's `AugmentMelSTFT` (models/preprocess.py),
with its augmentation removed and the kaldi mel filterbank built here rather
than taken from torchaudio. The checkpoints were trained on exactly this input:
32 kHz mono, pre-emphasis, an 800-sample Hann window in a 1024-point FFT, a
320-sample hop, 128 kaldi mel bands from 0 Hz to 15 kHz, then log and a fixed
rescale. Anything else and the scores drift.
"""

import math

import torch
from torch import nn

SAMPLE_RATE = 32000


def _mel(freq):
    return 1127.0 * torch.log(1.0 + freq / 700.0)


def kaldi_mel_banks(n_mels: int, n_fft: int, sample_rate: int, fmin: float, fmax: float) -> torch.Tensor:
    """Triangular kaldi mel filters, shape (n_mels, n_fft // 2).

    `torchaudio.compliance.kaldi.get_mel_banks` with no vocal tract length
    warping, which is how EfficientAT calls it.
    """
    num_fft_bins = n_fft // 2
    fft_bin_width = sample_rate / n_fft
    mel_low = 1127.0 * math.log(1.0 + fmin / 700.0)
    mel_high = 1127.0 * math.log(1.0 + fmax / 700.0)
    delta = (mel_high - mel_low) / (n_mels + 1)

    index = torch.arange(n_mels, dtype=torch.float32).unsqueeze(1)
    left = mel_low + index * delta
    centre = mel_low + (index + 1.0) * delta
    right = mel_low + (index + 2.0) * delta

    mel = _mel(fft_bin_width * torch.arange(num_fft_bins, dtype=torch.float32)).unsqueeze(0)
    up = (mel - left) / (centre - left)
    down = (right - mel) / (right - centre)
    return torch.clamp(torch.minimum(up, down), min=0.0)


class MelFrontend(nn.Module):
    """Waveform (batch, samples) at 32 kHz to the model's (batch, 128, frames)."""

    def __init__(self, n_mels: int = 128, sr: int = SAMPLE_RATE, win_length: int = 800,
                 hopsize: int = 320, n_fft: int = 1024, fmin: float = 0.0, fmax_aug_range: int = 2000):
        super().__init__()
        self.n_fft = n_fft
        self.hopsize = hopsize
        self.win_length = win_length
        fmax = sr // 2 - fmax_aug_range // 2
        self.register_buffer("window", torch.hann_window(win_length, periodic=False), persistent=False)
        self.register_buffer("preemphasis", torch.as_tensor([[[-0.97, 1.0]]]), persistent=False)
        banks = kaldi_mel_banks(n_mels, n_fft, sr, fmin, fmax)
        # One zero column for the Nyquist bin, as the original pads it.
        self.register_buffer("mel_basis", nn.functional.pad(banks, (0, 1)), persistent=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = nn.functional.conv1d(x.unsqueeze(1), self.preemphasis).squeeze(1)
        spec = torch.stft(x, self.n_fft, hop_length=self.hopsize, win_length=self.win_length,
                          center=True, normalized=False, window=self.window, return_complex=True)
        power = spec.real ** 2 + spec.imag ** 2
        melspec = torch.matmul(self.mel_basis, power)
        melspec = (melspec + 0.00001).log()
        return (melspec + 4.5) / 5.0
