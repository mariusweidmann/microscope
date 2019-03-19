#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2019 David Pinto <david.pinto@bioch.ox.ac.uk>
##
## Microscope is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## Microscope is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Microscope.  If not, see <http://www.gnu.org/licenses/>.

"""Meadowlark Optics Spatial light modulator

Wrapper to the C++ Software Development Kit for PCIe 16-bit Devices

Technically, this wraps the PCIe16Interface shared library but that
name is too generic.  Also, it seems to actually end up calling the
C++ BNSPCIe16Board library so we call that instead which is also a bit
more clear.
"""

import ctypes
import ctypes.util
import os

from ctypes import c_bool
from ctypes import c_char_p
from ctypes import c_double
from ctypes import c_int
from ctypes import c_uint
from ctypes import c_ushort

c_ushort_p = ctypes.POINTER(c_ushort)


SDK = ctypes.util.find_library('PCIe16Interface')
if SDK is None:
    raise RuntimeError('Failed to find BNS dll')


LC_TYPE = c_int # enum for representing liquid crystal types
FERROELECTRIC = c_int(0)
NEMATIC = c_int(1)

CAL_TYPE = c_int # enum for representing 2D calibration image types
NUC = c_int(0)
WFC = c_int(1)

TEMPUNITS = c_int # enum for representing temperature units
CELSIUS = c_int(0)
FAHRENHEIT = c_int(1)


def make_prototype(name, argtypes, restype=None):
    func = getattr(SDK, name)
    func.argtypes = argtypes
    func.restype = restype
    return func

## Opens all available PCIe 16-bit SLM controllers and returns the
## number of boards available
Constructor = make_prototype('Constructor', [LC_TYPE], c_int)

## Closes all PCIe 16-bit SLM Controllers that were opened with
## Constructor.
Deconstructor = make_prototype('Deconstructor', [])


## ReadTIFF(FilePath, ImageData, ScaleWidth, ScaleHeight)
ReadTIFF = make_prototype('ReadTIFF', [c_char_p, c_ushort_p, c_uint, c_uint])

## WriteImage(Board, Image)
WriteImage = make_prototype('WriteImage', [c_int, c_ushort_p])

## LoadSequence(Board, Images, NumberOfImages)
LoadSequence = make_prototype('LoadSequence', [c_int, c_ushort_p, c_int])

## SetSequencingRate(FrameRate)
SetSequencingRate = make_prototype('SetSequencingRate', [c_double])

## StartSequence()
StartSequence = make_prototype('StartSequence', [])

## GetCurSeqImage(Board)
GetCurSeqImage = make_prototype('GetCurSeqImage', [c_int], c_int)

## StopSequence()
StopSequence = make_prototype('StopSequence', [])

## GetImageSize(Board)
GetImageSize = make_prototype('GetImageSize', [c_int], c_int)

## GetSLMPower(Board)
GetSLMPower = make_prototype('GetSLMPower', [c_int], c_bool)

## SLMPower(Board, PowerOn)
SLMPower = make_prototype('SLMPower', [c_int, c_bool])

## WriteCal(Board, CalType, Image)
WriteCal = make_prototype('WriteCal', [c_int, CAL_TYPE, c_ushort_p])

## LoadLUTFile(Board, LUTPath)
LoadLUTFile = make_prototype('LoadLUTFile', [c_int, c_char_p])

## SetTrueFrames(Board, TrueFrames)
SetTrueFrames = make_prototype('SetTrueFrames', [c_int, c_int])

## GetInternalTemp(Board, units)
GetInternalTemp = make_prototype('GetInternalTemp', [c_int, TEMPUNITS],
                                 c_double)
