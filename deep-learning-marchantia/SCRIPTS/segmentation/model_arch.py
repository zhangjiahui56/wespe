import torch
import torch.nn as nn
from torch.nn import functional as F
from torchvision import datasets, models, transforms

import numpy as np

def conv3x3(in_, out):
    return nn.Conv2d(in_, out, 3, padding=1)

class ConvRelu(nn.Module):
    def __init__(self, in_: int, out: int):
        super(ConvRelu, self).__init__()
        self.conv = conv3x3(in_, out)
        self.activation = nn.ReLU(inplace=True)

    def forward(self, x):
        x = self.conv(x)
        x = self.activation(x)
        return x

class DecoderBlock(nn.Module):
    """
    Parameters for Deconvolution were chosen to avoid artifacts, following
    link https://distill.pub/2016/deconv-checkerboard/
    """

    def __init__(self, in_channels, middle_channels, out_channels, is_deconv=True):
        super(DecoderBlock, self).__init__()
        self.in_channels = in_channels

        if is_deconv:
            self.block = nn.Sequential(
                ConvRelu(in_channels, middle_channels),
                nn.ConvTranspose2d(middle_channels, out_channels, kernel_size=4, stride=2, padding=1),
                nn.ReLU(inplace=True)
            )
        else:
            self.block = nn.Sequential(
                nn.Upsample(scale_factor=2, mode='bilinear'),
                ConvRelu(in_channels, middle_channels),
                ConvRelu(middle_channels, out_channels),
            )

    def forward(self, x):
        return self.block(x)

class UNet16(nn.Module):
    def __init__(self, feature_dim, num_classes=1, num_filters=32, pretrained=False):
        """
        :param num_classes:
        :param num_filters:
        :param pretrained:
            False - no pre-trained network used
            True - encoder pre-trained with VGG16
        """
        super().__init__()
        self.pool = nn.MaxPool2d(2, 2)        

        self.feature_dim = feature_dim
        self.num_classes = num_classes

        self.encoder = models.vgg16(pretrained=pretrained).features

        self.relu = nn.ReLU(inplace=True)

        # Encoder
        self.conv1 = nn.Sequential(self.encoder[0], self.relu,
                                   self.encoder[2], self.relu)
        self.conv2 = nn.Sequential(self.encoder[5], self.relu,
                                   self.encoder[7], self.relu)
        self.conv3 = nn.Sequential(self.encoder[10], self.relu,
                                   self.encoder[12], self.relu,
                                   self.encoder[14], self.relu)
        self.conv4 = nn.Sequential(self.encoder[17], self.relu,
                                   self.encoder[19], self.relu,
                                   self.encoder[21], self.relu)
        self.conv5 = nn.Sequential(self.encoder[24], self.relu,
                                   self.encoder[26], self.relu,
                                   self.encoder[28], self.relu)

        # Decoder
        # DecoderBlock(in_channels, middle_channels, out_channels)
        self.center = DecoderBlock(512, num_filters * 8 * 2, num_filters * 8)
        self.dec5 = DecoderBlock(512 + num_filters * 8, num_filters * 8 * 2, num_filters * 8, is_deconv=True)
        self.dec4 = DecoderBlock(512 + num_filters * 8, num_filters * 8 * 2, num_filters * 8, is_deconv=True)
        self.dec3 = DecoderBlock(256 + num_filters * 8, num_filters * 4 * 2, num_filters * 2, is_deconv=True)
        self.dec2 = DecoderBlock(128 + num_filters * 2, num_filters * 2 * 2, num_filters, is_deconv=True)
        self.dec1 = ConvRelu(64 + num_filters, num_filters)
        
        self.sem_seg_output = nn.Conv2d(num_filters, num_classes, kernel_size=1)

        self.ins_seg_output = nn.Conv2d(num_filters, self.feature_dim, kernel_size=1)

    def forward(self, x):
        conv1 = self.conv1(x)
        conv2 = self.conv2(self.pool(conv1))
        conv3 = self.conv3(self.pool(conv2))
        conv4 = self.conv4(self.pool(conv3))
        conv5 = self.conv5(self.pool(conv4))

        center = self.center(self.pool(conv5))

        dec5 = self.dec5(torch.cat([center, conv5], 1))

        dec4 = self.dec4(torch.cat([dec5, conv4], 1))
        dec3 = self.dec3(torch.cat([dec4, conv3], 1))
        dec2 = self.dec2(torch.cat([dec3, conv2], 1))
        dec1 = self.dec1(torch.cat([dec2, conv1], 1))

        sem_seg_output = self.sem_seg_output(dec1)
        ins_seg_out = self.ins_seg_output(dec1)

        return sem_seg_output, ins_seg_out

