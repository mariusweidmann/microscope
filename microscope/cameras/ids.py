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

"""Interface to IDS cameras.
"""

import ctypes

from pyueye import ueye
import Pyro4

import microscope.devices

class IDS(microscope.devices.CameraDevice):
    """Foo

    The cmaera ID must not change

    Args:
        camera_id (int): the camera ID.  This is the customizable
            camera ID, not the device ID.  If zero (the default), it
            will use the first available camera which is suitable for
            systems with a single camera.
    """
    def __init__(self, camera_id=0):
        super().__init__()
        self._hCam = ueye.HIDS(camera_id)
        dwCount = ctypes.c_int(0)
        if ueye.is_GetNumberOfCameras(n_cameras) != ueye.IS_SUCCESS:
            raise RuntimeError('failed to get number of cameras')
        ## We need to set dwCount before calling GetCameraList, or the info will come all emp
        pucl = ueye.UEYE_CAMERA_LIST()
        pucl.dwCount = ueye.c_ulong(dwCount.value)
        if ueye.is_GetCameraList(pucl) != ueye.IS_SUCCESS:
            raise RuntimeError('failed to get cameras list')

    def enable(self):
        status = ueye.is_InitCamera(self._hCam, None)
        if status != ueye.IS_SUCCESS:
            raise RuntimeError('failed to init camera, returned %d' % status)


    def disable(self):
        status = ueye.is_ExitCamera(self._hCam)
        if status != ueye.IS_SUCCESS:
            if status == ueye.IS_INVALID_CAMERA_HANDLE and not self.enabled:
            raise RuntimeError('failed to init camera, returned %d' % status)
        super().disable()
