# -*- coding:utf-8 -*-
"""
作者：Ryuk
日期：2023年12月18日
"""

import numpy as np
import random
import math
import scipy.signal


class BreakAugment:
    def __init__(self, sample_rate=16000, break_duration=0.01, break_ceil=50, break_floor=10):
        self.sample_rate = sample_rate
        self.break_segment = sample_rate * break_duration
        self.break_ceil = break_ceil
        self.break_floor = break_floor

    def get_mask(self, x):
        break_count = (self.break_floor - self.break_ceil) * random.random() + self.break_ceil
        break_duration = break_count * self.break_segment
        mask = np.ones(x.size())
        break_start = int(x.size(1) * random.random())
        break_end = int(min(x.size(1), break_start+break_duration))
        mask[:, break_start:break_end] = 0
        return mask

    def __call__(self, x):
        break_mask = self.get_mask(x)
        x = x * break_mask
        return x


class ClipAugment:
    def __init__(self, clip_ceil=1, clip_floor=0.5):
        self.clip_ceil = clip_ceil
        self.clip_floor = clip_floor

    def get_clip(self):
        return (self.clip_floor - self.clip_ceil) * random.random() + self.clip_ceil

    def __call__(self, x):
        clip_level = self.get_clip()
        x[np.abs(x)>clip_level] = clip_level
        return x


class HowlingAugment:
    def __init__(self, IR, gain_floor=1, gain_ceil=10, frame_len=128, hop_len=None):
        super().__init__()
        self.IR = IR
        self.gain_floor = gain_floor
        self.gain_ceil = gain_ceil
        self.frame_len = frame_len
        if hop_len is None:
            self.hop_len = self.frame_len // 2
        else:
            self.hop_len = hop_len
        self.win = np.hanning(self.frame_len)

    def get_MSG(self):
        ir_spec = np.fft.rfft(self.IR)
        ir_mag = np.abs(ir_spec)
        ir_phase = np.angle(ir_spec)

        MLG = np.mean(np.abs(ir_mag) ** 2)
        zero_phase_index = np.where(np.logical_and(-0.1 < ir_phase, ir_phase < 0.1))
        ir_zero_phase_mag = ir_mag[zero_phase_index]
        peak_gain = np.max(np.abs(ir_zero_phase_mag) ** 2)
        MSG = -10 * np.log10(peak_gain / MLG)

        return MSG

    def scale_IR(self, target_gain):
        ir_spec = np.fft.rfft(self.IR)
        ir_mag = np.abs(ir_spec)

        MLG = np.mean(np.abs(ir_mag) ** 2)
        mean_gain = 10 * np.log10(MLG)
        reqdBLoss = target_gain - mean_gain
        factor = 0.5 ** (reqdBLoss / 6)
        self.IR = self.IR / factor

    def get_gain(self):
        return (self.gain_floor - self.gain_ceil) * random.random() + self.gain_ceil

    def howling(self, x):
        sample_len = x.size(1)
        howling_out = np.zeros(x.size())
        conv_len = self.frame_len + self.IR.size(1) - 1
        frame_start = 0
        for i in range(sample_len):
            cur_frame = x[:, frame_start:frame_start+self.frame_len]
            windowed_frame = self.win * cur_frame
            howling_out[:,frame_start:frame_start+self.frame_len] += windowed_frame

            conv_frame = np.convolve(windowed_frame.flatten(), self.IR.flatten(), mode="full")

            frame_start = frame_start + self.hop_len
            if frame_start+conv_len < sample_len:
                x[:,frame_start:frame_start+conv_len] += conv_frame
            else:
                break

            x = np.minimum(x, np.ones(sample_len))
            x = np.maximum(x, -np.ones(sample_len))

        howling_out = np.minimum(howling_out, np.ones(sample_len))
        howling_out = np.maximum(howling_out, -np.ones(sample_len))
        return howling_out

    def __call__(self, x):
        target_gain = self.get_MSG() + 2
        self.scale_IR(target_gain)
        x = self.howling(x)
        return x


class MixAugment:
    def __init__(self, snr_ceil=30, snr_floor=-5):
        super().__init__()
        self.snr_ceil = snr_ceil
        self.snr_floor = snr_floor

    def get_snr(self, n):
        return (self.snr_floor - self.snr_ceil) * np.random.rand([n]) + self.snr_ceil

    def __call__(self, speech, noise):
        samples = speech.size(0)
        snr = self.get_snr(samples)
        noise = noise * np.norm(speech) / np.norm(noise)
        scalar = np.pow(10.0, (0.05 * snr)).reshape([speech.size(0), 1])
        noise = np.div(noise, scalar)
        mix = speech + noise
        return mix


class ReverbAugment:
    def __init__(self, rir):
        super().__init__()
        self.rir = rir

    def __call__(self, x):
        reverbed = scipy.signal.fftconvolve(x, self.rir, mode="full")
        reverbed = reverbed[0: x.shape[0]]
        return reverbed


class SpecAugment:
    def __init__(self):
        super().__init__()
        self.a_hp = np.array([-1.99599, 0.99600])
        self.b_hp = np.array([-2, 1])

    def _uni_rand(self):
        return np.random.rand(1) - 0.5

    def _rand_resp(self):
        a1 = 0.75 * self._uni_rand()
        a2 = 0.75 * self._uni_rand()
        b1 = 0.75 * self._uni_rand()
        b2 = 0.75 * self._uni_rand()
        return a1, a2, b1, b2

    def __call__(self, x):
        a1, a2, b1, b2 = self._rand_resp()
        x = scipy.signal.lfilter([1, self.b_hp[0], self.b_hp[1]], [1, self.a_hp[0], self.a_hp[1]], x)
        x = scipy.signal.lfilter([1, b1, b2], [1, a1, a2], x)
        return x


class VolumeAugment:
    def __init__(self, sample_rate=16000, segment_len=0.5, vol_ceil=10, vol_floor=-10):
        super().__init__()
        self.sample_rate = sample_rate
        self.segment_len = segment_len
        self.segment_samples = int(self.sample_rate * self.segment_len)
        self.vol_ceil = vol_ceil
        self.vol_floor = vol_floor

    def get_vol(self, sample_length):
        segments = sample_length / (self.segment_len * self.sample_rate)
        step_db = np.arange(self.vol_ceil, self.vol_floor, (self.vol_floor - self.vol_ceil) /segments)
        return step_db

    def apply_gain(self, segments, db):
        gain = np.pow(10.0, (0.05 * db))
        segments = segments * gain
        return segments

    def __call__(self, x):
        step_db = self.get_vol(x.size(1))
        for i in range(step_db.size(0)):
            start = i * self.segment_samples
            end = min((i+1) * self.segment_samples, x.size(1))
            x[:, start:end] = self.apply_gain(x[:, start:end], step_db[i])
        return x