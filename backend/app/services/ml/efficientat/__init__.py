"""
EfficientAT MobileNet audio tagger, vendored.

From https://github.com/fschmid56/EfficientAT (MIT, Copyright (c) 2022 Florian
Schmid; see LICENSE in this folder). Only what inference with the AudioSet
`mn*_as` checkpoints needs is kept, and it depends on torch alone: the
torchvision conv block and the torchaudio kaldi mel banks are written out here,
so a venue box needs neither. The layer names are unchanged, so the published
checkpoints load as they are.
"""

from .frontend import MelFrontend
from .mobilenet import build_mn, count_parameters

__all__ = ["MelFrontend", "build_mn", "count_parameters"]
