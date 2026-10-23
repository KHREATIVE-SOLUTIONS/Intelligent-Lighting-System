"""
EfficientAT's MobileNetV3 ("MN") for audio tagging.

From models/mn/model.py, models/mn/block_types.py and models/mn/utils.py of
EfficientAT (MIT, Copyright (c) 2022 Florian Schmid), which adapt torchvision's
MobileNetV3. Kept: the MLP head and channel-wise squeeze-excitation the AudioSet
checkpoints use. Removed: the other heads, the frequency and time
squeeze-excitation options, weight downloading and the debug print.
"""

from functools import partial
from typing import List, Optional

import torch
from torch import Tensor, nn


def make_divisible(v: float, divisor: int, min_value: Optional[int] = None) -> int:
    if min_value is None:
        min_value = divisor
    new_v = max(min_value, int(v + divisor / 2) // divisor * divisor)
    if new_v < 0.9 * v:
        new_v += divisor
    return new_v


def _conv_norm_act(in_ch, out_ch, kernel_size, norm_layer, activation_layer,
                   stride=1, groups=1, dilation=1):
    """torchvision's ConvNormActivation, same layout so the checkpoint keys match."""
    padding = (kernel_size - 1) // 2 * dilation
    layers: List[nn.Module] = [
        nn.Conv2d(in_ch, out_ch, kernel_size, stride, padding, dilation=dilation, groups=groups, bias=False),
        norm_layer(out_ch),
    ]
    if activation_layer is not None:
        layers.append(activation_layer(inplace=True))
    return nn.Sequential(*layers)


class SqueezeExcitation(nn.Module):
    """Channel squeeze-excitation (EfficientAT's `se_dims='c'`)."""

    def __init__(self, input_dim: int, squeeze_dim: int):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, squeeze_dim)
        self.fc2 = nn.Linear(squeeze_dim, input_dim)
        self.activation = nn.ReLU()
        self.scale_activation = nn.Sigmoid()

    def forward(self, x: Tensor) -> Tensor:
        scale = torch.mean(x, (2, 3), keepdim=True)
        shape = scale.size()
        scale = self.fc2(self.activation(self.fc1(scale.squeeze(2).squeeze(2))))
        return self.scale_activation(scale).view(shape) * x


class ConcurrentSEBlock(nn.Module):
    """Kept as a wrapper so the checkpoint's `conc_se_layers.0` keys still match."""

    def __init__(self, channels: int, se_r: int = 4):
        super().__init__()
        self.conc_se_layers = nn.ModuleList(
            [SqueezeExcitation(channels, make_divisible(channels // se_r, 8))]
        )

    def forward(self, x: Tensor) -> Tensor:
        # One layer, so the original's max over concurrent layers is the layer.
        return self.conc_se_layers[0](x)


class InvertedResidualConfig:
    def __init__(self, input_channels, kernel, expanded_channels, out_channels, use_se, activation,
                 stride, dilation, width_mult):
        self.input_channels = make_divisible(input_channels * width_mult, 8)
        self.kernel = kernel
        self.expanded_channels = make_divisible(expanded_channels * width_mult, 8)
        self.out_channels = make_divisible(out_channels * width_mult, 8)
        self.use_se = use_se
        self.use_hs = activation == "HS"
        self.stride = stride
        self.dilation = dilation


class InvertedResidual(nn.Module):
    def __init__(self, cnf: InvertedResidualConfig, norm_layer):
        super().__init__()
        self.use_res_connect = cnf.stride == 1 and cnf.input_channels == cnf.out_channels
        act = nn.Hardswish if cnf.use_hs else nn.ReLU
        layers: List[nn.Module] = []
        if cnf.expanded_channels != cnf.input_channels:
            layers.append(_conv_norm_act(cnf.input_channels, cnf.expanded_channels, 1, norm_layer, act))
        stride = 1 if cnf.dilation > 1 else cnf.stride
        layers.append(_conv_norm_act(cnf.expanded_channels, cnf.expanded_channels, cnf.kernel, norm_layer, act,
                                     stride=stride, groups=cnf.expanded_channels, dilation=cnf.dilation))
        if cnf.use_se:
            layers.append(ConcurrentSEBlock(cnf.expanded_channels))
        layers.append(_conv_norm_act(cnf.expanded_channels, cnf.out_channels, 1, norm_layer, None))
        self.block = nn.Sequential(*layers)

    def forward(self, x: Tensor) -> Tensor:
        result = self.block(x)
        if self.use_res_connect:
            result += x
        return result


class MN(nn.Module):
    def __init__(self, width_mult: float = 1.0, num_classes: int = 527, dropout: float = 0.2):
        super().__init__()
        bneck = partial(InvertedResidualConfig, width_mult=width_mult)
        setting = [
            bneck(16, 3, 16, 16, False, "RE", 1, 1),
            bneck(16, 3, 64, 24, False, "RE", 2, 1),
            bneck(24, 3, 72, 24, False, "RE", 1, 1),
            bneck(24, 5, 72, 40, True, "RE", 2, 1),
            bneck(40, 5, 120, 40, True, "RE", 1, 1),
            bneck(40, 5, 120, 40, True, "RE", 1, 1),
            bneck(40, 3, 240, 80, False, "HS", 2, 1),
            bneck(80, 3, 200, 80, False, "HS", 1, 1),
            bneck(80, 3, 184, 80, False, "HS", 1, 1),
            bneck(80, 3, 184, 80, False, "HS", 1, 1),
            bneck(80, 3, 480, 112, True, "HS", 1, 1),
            bneck(112, 3, 672, 112, True, "HS", 1, 1),
            bneck(112, 5, 672, 160, True, "HS", 2, 1),
            bneck(160, 5, 960, 160, True, "HS", 1, 1),
            bneck(160, 5, 960, 160, True, "HS", 1, 1),
        ]
        last_channel = make_divisible(1280 * width_mult, 8)
        norm_layer = partial(nn.BatchNorm2d, eps=0.001, momentum=0.01)

        layers: List[nn.Module] = [
            _conv_norm_act(1, setting[0].input_channels, 3, norm_layer, nn.Hardswish, stride=2)
        ]
        layers.extend(InvertedResidual(cnf, norm_layer) for cnf in setting)
        last_in = setting[-1].out_channels
        layers.append(_conv_norm_act(last_in, 6 * last_in, 1, norm_layer, nn.Hardswish))
        self.features = nn.Sequential(*layers)
        self.classifier = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(start_dim=1),
            nn.Linear(6 * last_in, last_channel),
            nn.Hardswish(inplace=True),
            nn.Dropout(p=dropout, inplace=True),
            nn.Linear(last_channel, num_classes),
        )

    def forward(self, x: Tensor) -> Tensor:
        """(batch, 1, mels, frames) to (batch, classes) logits."""
        return self.classifier(self.features(x))


def build_mn(width_mult: float = 1.0, num_classes: int = 527) -> MN:
    return MN(width_mult=width_mult, num_classes=num_classes)


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())
