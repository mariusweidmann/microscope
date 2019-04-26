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
import platform


if platform.system() == 'Windows':
    _bits, _linkage = platform.architecture()
    if _bits == '64bit':
        _libname = 'ueye_api_64'
    else:
        _libname = 'ueye_api'
else:
    _libname = 'libueye_api.so'

## TODO: seems like all functions are declared with __cdecl so we
## should be using CDLL not WinDLL, even on windows.  Right?  They
## only get declared with __stdcall if _IDS_VBSTD or _FALC_VBSTD are
## defined.
_SDK = ctypes.CDLL(_libname)


## Error codes
SUCCESS = 0
INVALID_MODE = 101


## Device enumeration
USE_DEVICE_ID = 0x8000


## Binning
GET_BINNING = 0x8000
GET_SUPPORTED_BINNING = 0x8001
GET_BINNING_TYPE = 0x8002
GET_BINNING_FACTOR_HORIZONTAL = 0x8004
GET_BINNING_FACTOR_VERTICAL = 0x8008

BINNING_DISABLE = 0x00

BINNING_2X_VERTICAL = 0x0001
BINNING_2X_HORIZONTAL = 0x0002
BINNING_4X_VERTICAL = 0x0004
BINNING_4X_HORIZONTAL = 0x0008
BINNING_3X_VERTICAL = 0x0010
BINNING_3X_HORIZONTAL = 0x0020
BINNING_5X_VERTICAL = 0x0040
BINNING_5X_HORIZONTAL = 0x0080
BINNING_6X_VERTICAL = 0x0100
BINNING_6X_HORIZONTAL = 0x0200
BINNING_8X_VERTICAL = 0x0400
BINNING_8X_HORIZONTAL = 0x0800
BINNING_16X_VERTICAL = 0x1000
BINNING_16X_HORIZONTAL = 0x2000

BINNING_MASK_VERTICAL = (BINNING_2X_VERTICAL
                         | BINNING_3X_VERTICAL
                         | BINNING_4X_VERTICAL
                         | BINNING_5X_VERTICAL
                         | BINNING_6X_VERTICAL
                         | BINNING_8X_VERTICAL
                         | BINNING_16X_VERTICAL)
BINNING_MASK_HORIZONTAL = (BINNING_2X_HORIZONTAL
                           | BINNING_3X_HORIZONTAL
                           | BINNING_4X_HORIZONTAL
                           | BINNING_5X_HORIZONTAL
                           | BINNING_6X_HORIZONTAL
                           | BINNING_8X_HORIZONTAL
                           | BINNING_16X_HORIZONTAL)


## Pixel formats
GET_COLOR_MODE = 0x8000

CM_SENSOR_RAW8 = 11
CM_SENSOR_RAW10 = 33
CM_SENSOR_RAW12 = 27
CM_SENSOR_RAW16 = 29
CM_MONO8 = 6
CM_MONO10 = 34
CM_MONO12 = 26
CM_MONO16 = 28


## Camera info constants
GET_STATUS = 0x8000
STANDBY = 24
STANDBY_SUPPORTED = 25


## Enum of commands for DeviceInfo
DEVICE_INFO_CMD_GET_DEVICE_INFO = 0x02010001


## typedefs so our code can read like the ueye header
BOOL = ctypes.c_int32
BYTE = ctypes.c_ubyte
DWORD = ctypes.c_uint32
HWND = ctypes.c_void_p
INT = ctypes.c_int32
TCHAR = ctypes.c_char
UINT = ctypes.c_uint32
ULONG = ctypes.c_uint32
WORD = ctypes.c_uint16

CHAR = ctypes.c_char
HIDS = DWORD
IDSEXP = INT
IDSEXPUL = ULONG

TRUE = 1
FALSE = 0



class SENSORINFO(ctypes.Structure):
    _pack_ = 8
    _fields_ = [
        ('SensorID', WORD),
        ('strSensorName', CHAR*32),
        ('nColorMode', ctypes.c_char),
        ('nMaxWidth', DWORD),
        ('nMaxHeight', DWORD),
        ('bMasterGain', BOOL),
        ('bRGain', BOOL),
        ('bGGain', BOOL),
        ('bBGain', BOOL),
        ('bGlobShutter', BOOL),
        ('wPixelSize', WORD),
        ('nUpperLeftBayerPixel', ctypes.c_char),
        ('Reserved', ctypes.c_char*13),
    ]

PSENSORINFO = ctypes.POINTER(SENSORINFO)


class UEYE_CAMERA_INFO(ctypes.Structure):
    _pack_ = 8
    _fields_ = [
        ('dwCameraID', DWORD),
        ('dwDeviceID', DWORD),
        ('dwSensorID', DWORD),
        ('dwInUse', DWORD),
        ('SerNo', CHAR*16),
        ('Model', CHAR*16),
        ('dwStatus', DWORD),
        ('dwReserved', DWORD*2),
        ('FullModelName', CHAR*32),
        ('dwReserved2', DWORD*5),
    ]

PUEYE_CAMERA_INFO = ctypes.POINTER(UEYE_CAMERA_INFO)


def camera_list_type_factory(n_cameras: int):
    """List of camera informations.

    This struct makes use of the `struct array hack
    <http://www.c-faq.com/struct/structhack.html>`_ for the info of
    multiple cameras.  We want to use as little magic here as possible
    so that we can just use the C documentation, but this hack does
    not work `unchanged in Python
    <https://stackoverflow.com/questions/51549340/python-ctypes-definition-with-c-struct-arrary>`_.
    The reason is that the array type in Python includes the array
    length.  So use this instead::

        camera_list = ueye.camera_list_type_factory(n_cameras)()
        camera_list.dwCount = n_cameras
        GetCameraList(ctypes.cast(ctypes.byref(camera_list),
                                  ueye.PUEYE_CAMERA_LIST))

    """
    class _UEYE_CAMERA_LIST(ctypes.Structure):
        _pack_ = 8
        _fields_ = [
            ('dwCount', ULONG),
            ('uci', UEYE_CAMERA_INFO*n_cameras),
        ]
    return _UEYE_CAMERA_LIST

UEYE_CAMERA_LIST = camera_list_type_factory(1)
PUEYE_CAMERA_LIST = ctypes.POINTER(UEYE_CAMERA_LIST)


class DEVICE_INFO_HEARTBEAT(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ('reserved_1', BYTE*24),
        ('dwRuntimeFirmwareVersion', DWORD),
        ('reserved_2', BYTE*8),
        ('wTemperature', WORD),
        ('wLinkSpeed_Mb', WORD),
        ('reserved_3', BYTE*6),
        ('wComportOffset', WORD),
        ('reserved', BYTE*200),
    ]


class DEVICE_INFO_CONTROL(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ('dwDeviceId', DWORD),
        ('reserved', BYTE*148),
    ]


class DEVICE_INFO(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ('infoDevHeartbeat', DEVICE_INFO_HEARTBEAT),
        ('infoDevControl', DEVICE_INFO_CONTROL),
        ('reserved', BYTE*240),
    ]



def prototype(name, argtypes, restype=IDSEXP):
    func = getattr(_SDK, name)
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
