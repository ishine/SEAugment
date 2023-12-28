# encoding: utf-8
"""
@author:  Ryuk
@contact: jeryuklau@gmail.com
"""

import torch
from torch import nn

from noisexorcist.config import configurable
from noisexorcist.modeling.backbones import build_backbone
from noisexorcist.modeling.losses import *
from .process import extract_inputs, extract_groundtruth


class Baseline(nn.Module):
    """
    Baseline architecture. Any models that contains the following two components:
    1. Per-image feature extraction (aka backbone)
    2. Per-image feature aggregation and loss computation
    """

    @configurable
    def __init__(
            self,
            *,
            backbone,
            input_type,
            output_type,
            loss_kwargs=None
    ):
        """
        NOTE: this interface is experimental.

        Args:
            backbone:
        """
        super().__init__()
        # backbone
        self.backbone = backbone
        self.loss_kwargs = loss_kwargs
        self.input_type = input_type
        self.output_type = output_type

    @classmethod
    def from_config(cls, cfg):
        backbone = build_backbone(cfg)
        return {
            'backbone': backbone,
            'input_type': cfg.MODEL.INPUT_TYPE,
            'output_type': cfg.MODEL.OUTPUT_TYPE,
            'loss_kwargs':
                {
                    # loss name
                    'loss_names': cfg.MODEL.LOSSES.NAME,

                    # loss hyperparameters
                    'ce': {
                        'eps': cfg.MODEL.LOSSES.CE.EPSILON,
                        'alpha': cfg.MODEL.LOSSES.CE.ALPHA,
                        'scale': cfg.MODEL.LOSSES.CE.SCALE,
                        'index': cfg.MODEL.LOSSES.CE.INDEX,
                        'gt_type': cfg.MODEL.LOSSES.CE.GT_TYPE
                    },
                    'mse': {
                        'eps': cfg.MODEL.LOSSES.MSE.EPSILON,
                    },
                    'wmse': {
                        'alpha': cfg.MODEL.LOSSES.WMSE.ALPHA,
                    },
                    'snr': {
                        'eps': cfg.MODEL.LOSSES.SNR.EPS,
                    },
                    'ci_sdr': {
                        'filter_length': cfg.MODEL.LOSSES.CI_SDR.FILTER_LENGTH,
                    }
                }
        }

    def forward(self, batched_inputs):
        inputs = self.preprocess_inputs(batched_inputs)

        outputs = self.backbone(inputs)
        if self.training:
            losses = self.losses(outputs, inputs)
            return losses
        else:
            return outputs


    def preprocess_inputs(self, batched_inputs):
        """
        get the input of model.
        """
        inputs = extract_inputs(batched_inputs, self.input_type)
        return inputs


    def losses(self, batched_outputs, batched_inputs):
        """
        Compute loss from modeling's outputs, the loss function input arguments
        must be the same as the outputs of the model forwarding.
        """
        # model predictions
        outputs = self.preprocess_outputs(batched_outputs)

        loss_dict = {}
        loss_names = self.loss_kwargs['loss_names']

        if 'CrossEntropyLoss' in loss_names:
            ce_kwargs = self.loss_kwargs.get('ce')
            loss_dict['loss_cls'] = cross_entropy_loss(
                outputs[ce_kwargs.get('index')],
                extract_groundtruth(batched_inputs, ce_kwargs.get('gt_type')),
                ce_kwargs.get('eps'),
                ce_kwargs.get('alpha'),
            ) * ce_kwargs.get('scale')


        return loss_dict
