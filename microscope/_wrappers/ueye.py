#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2019 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
##
## This file is part of Microscope.
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

"""Wrapper to libueye.

There is pyueye which also provides a ctypes wrapper to libueye.
However, it's undocumented so we always need to go back to the C
documentation.  But pyueye already has its own magic so we also need
to read its source.

Function names and enums are the same as in the C library, except the
``is_`` and ``IS_`` prefix which got removed.

"""

import ctypes
import os

from microscope._defs.ueye import *


if os.name in ("nt", "ce"):
    SDK = ctypes.WinDLL("ueye_api")
else:
    SDK = ctypes.CDLL("libueye_api.so")


def prototype(name, argtypes, restype=IDSEXP):
    func = getattr(SDK, name)
    func.argtypes = argtypes
    func.restype = restype
    return func


GetNumberOfCameras = prototype('is_GetNumberOfCameras', [ctypes.POINTER(INT)])
GetCameraList = prototype('is_GetCameraList', [PUEYE_CAMERA_LIST])
DeviceInfo = prototype('is_DeviceInfo', [HIDS, UINT, ctypes.c_void_p, UINT])

InitCamera = prototype('is_InitCamera', [ctypes.POINTER(HIDS), HWND])
ExitCamera = prototype('is_ExitCamera', [HIDS])
GetSensorInfo = prototype('is_GetSensorInfo', [HIDS, PSENSORINFO])

CameraStatus = prototype('is_CameraStatus', [HIDS, INT, ULONG], IDSEXPUL)

SetColorMode = prototype('is_SetColorMode', [HIDS, INT])

SetExternalTrigger = prototype('is_SetExternalTrigger', [HIDS, INT])
