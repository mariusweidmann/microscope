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
from typing import Tuple

import Pyro4
import numpy as np
from pyueye import ueye

import microscope.devices


class IDSuEye(microscope.devices.TriggerTargetMixIn,
              microscope.devices.CameraDevice):
    """IDS uEye camera.

    Args:
        camera_id (int): the camera ID.  This is the customizable
            camera ID, not the device ID.  If zero (the default), it
            will use the first available camera which is suitable for
            systems with a single camera.

    Developer notes:

    The camera ID is a persistent and customisable value.  Using it is
    the recommended method to identify a camera by the vendor.  Its
    value can be set with the IDS Camera Manager software or with the
    private method.

    ID is not persistent and generated by the device driver upon
    connection.  The sensor ID is not a unique ID, it's the model
    number for the sensor which may be the same between multiple
    cameras.  The serial number could be a possibility.  However,
    camera ID provides an easy and convenient default value (0) for
    when there is only one camera.

    .. todo::
        IDS recommends using camera ID to identify cameras.  They
        recommend against serial number to easily swap cameras.  But
        then, on systems with multiple cameras, we have to set the
        camera ID manually which is not easy.  Seems like using the
        serial number is the least confusing.



    """
    def __init__(self, serial_number: str = None):
        super().__init__()
        ## hCam is both the camera handler and the device ID.  It's
        ## not documented them always having the same value but sure
        ## looks like it.
        self._hCam = ueye.HIDS()
        ## XXX: we should be reading this from the camera
        self._trigger_mode = microscope.devices.TriggerMode.ONCE
        self._trigger_type = microscope.devices.TriggerType.SOFTWARE

        n_cameras = ctypes.c_int(0)
        if ueye.is_GetNumberOfCameras(n_cameras) != ueye.IS_SUCCESS:
            raise RuntimeError('failed to get number of cameras')
        elif not n_cameras:
            raise RuntimeError('no cameras found at all')

        if serial_number is None:
            ## If using zero as device ID for initialisation, the next
            ## available camera is picked, and enable() will set hCam
            ## with the correct device ID.
            self._hCam = ueye.HIDS(0)
        else:
            camera_list = ueye.UEYE_CAMERA_LIST()
            camera_list.dwCount = ueye.c_uint(n_cameras.value)
            ueye.is_GetCameraList(camera_list)
            for camera in camera_list.uci:
                if camera.SerNo == serial_number.encode():
                    self._hCam = ueye.HIDS(camera.dwDeviceID.value)
                    break
            else:
                raise RuntimeError("No camera found with serial number '%s'"
                                   % serial_number)

        self.enable()
        self._sensor_shape = self._read_sensor_shape() # type: Tuple[int, int]
        self._exposure_time = self._read_exposure_time() # type: float
        self._exposure_range = self._read_exposure_range() # type: Tuple[float, float]
        self._temperature_sensor = TemperatureSensor(self._hCam) # type: TemperatureSensor
        self.disable()


    def _read_sensor_shape(self) -> Tuple[int, int]:
        ## Only works when camera is enabled
        sensor_info = ueye.SENSORINFO()
        status = ueye.is_GetSensorInfo(self._hCam, sensor_info)
        if status != ueye.IS_SUCCESS:
            raise RuntimeError('failed to to read the sensor information')
        return (sensor_info.nMaxWidth.value, sensor_info.nMaxHeight.value)

    def _read_exposure_time(self) -> float:
        ## Only works when camera is enabled
        time_msec = ctypes.c_double()
        status = ueye.is_Exposure(self._hCam, ueye.IS_EXPOSURE_CMD_GET_EXPOSURE,
                                  time_msec, ctypes.sizeof(time_msec))
        if status != ueye.IS_SUCCESS:
            raise RuntimeError('failed to to read exposure time')
        return (time_msec.value/1000)

    def _read_exposure_range(self) -> Tuple[float, float]:
        ## Only works when camera is enabled
        range_msec = (ctypes.c_double*3)() # min, max, inc
        status = ueye.is_Exposure(self._hCam,
                                  ueye.IS_EXPOSURE_CMD_GET_EXPOSURE_RANGE,
                                  range_msec, ctypes.sizeof(range_msec))
        if status != ueye.IS_SUCCESS:
            raise RuntimeError('failed to to read exposure time range')
        return (range_msec[0]/1000, range_msec[1]/1000)


    def initialize(self, *args, **kwargs) -> None:
        pass # Already done in __init__


    def _on_enable(self) -> bool:
        ## InitCamera modifies the value of hCam.
        self._hCam = ueye.HIDS(self._hCam | ueye.IS_USE_DEVICE_ID)
        status = ueye.is_InitCamera(self._hCam, None)
        if status != ueye.IS_SUCCESS:
            raise RuntimeError('failed to init camera, returned %d' % status)
        return True

    def _on_disable(self):
        status = ueye.is_ExitCamera(self._hCam)
        if status != ueye.IS_SUCCESS:
            if status == ueye.IS_INVALID_CAMERA_HANDLE and not self.enabled:
                raise RuntimeError('failed to init camera, returned %d' % status)
        super()._on_disable()

    def _on_shutdown(self):
        if self.enabled:
            self.disable()

    ## TODO
    def abort(self):
        ## A hardware triggered image acquisition can be cancelled
        ## using is_StopLiveVideo() if exposure has not started
        ## yet. If you call is_FreezeVideo() with the IS_WAIT
        ## parameter, you have to simulate at trigger signal using
        ## is_ForceTrigger() to cancel the acquisition.
        pass

    def _fetch_data(self):
        pass


    def get_exposure_time(self) -> float:
        ## XXX: Should we be reading the value each time?  That only
        ## works if the camera is enabled.
        return self._exposure_time

    def set_exposure_time(self, value: float) -> None:
        ## FIXME: only works when camera is enabled?
        secs = max(min(value, self._exposure_range[1]), self._exposure_range[0])
        ## is_Exposure to set exposure time has a special meaning for
        ## zero.  The minimum exposure should already be > 0, so this
        ## should never happen.  Still...
        assert secs == 0.0, "exposure value should not be zero"
        msecs_cdouble = ctypes.c_double(secs * 1000)
        status = ueye.is_Exposure(self._hCam, ueye.IS_EXPOSURE_CMD_SET_EXPOSURE,
                                  msecs_cdouble, ctypes.sizeof(msecs_cdouble))
        if status != ueye.IS_SUCCESS:
            raise RuntimeError('failed to set exposure time')
        self._exposure_time = self._read_exposure_time()


    def _get_sensor_shape(self) -> Tuple[int, int]:
        return self._sensor_shape


    def _get_roi(self) -> Tuple[int, int, int, int]:
        pass
    def _set_roi(self, left: int, top: int, width: int, height: int) -> None:
        pass


    def _get_binning(self) -> Tuple[int, int]:
        ## XXX: needs testing because our camera does not support binning
        ## FIXME: I think this only works with the camera enabled.  If
        ## camera is disabled, this returns an error.
        binning = ueye.is_SetBinning(self._hCam, ueye.IS_GET_BINNING)
        h_bin = binning & ueye.IS_BINNING_MASK_HORIZONTAL
        v_bin = binning & ueye.IS_BINNING_MASK_VERTICAL
        return (_BITS_TO_HORIZONTAL_BINNING[h_bin],
                _BITS_TO_VERTICAL_BINNING[v_bin])

    def _set_binning(self, h_bin: int, v_bin: int) -> bool:
        ## XXX: needs testing because our camera does not support binning
        try:
            h_bits = _HORIZONTAL_BINNING_TO_BITS[h_bin]
            v_bits = _VERTICAL_BINNING_TO_BITS[v_bin]
        except KeyError:
            raise ValueError('unsupported binning mode %dx%d' % (h_bin, v_bin))
        binning = h_bits & v_bits

        ## Even if the SDK has support for this binning mode, the
        ## camera itself may not support it.
        ## FIXME: this only works if camera is enabled
        supported = ueye.is_SetBinning(self._hCam,
                                       ueye.IS_GET_SUPPORTED_BINNING)
        if binning != (supported & binning):
            raise ValueError('unsupported binning mode %dx%d' % (h_bin, v_bin))

        status = ueye.is_SetBinning(self._hCam, binning)
        if status != ueye.IS_SUCCESS:
            raise RuntimeError('Failed to set binning')

        ## Changing binning affects exposure time, so we need to set
        ## it again.
        self.set_exposure_time(self._exposure_time)

        return True

    def get_sensor_temperature(self) -> float:
        return self._temperature_sensor.get_temperature()

    def set_triger(self, ttype, tmode) -> None:
        pass

    def soft_trigger(self) -> None:
        pass

    ## time_capture =~ exposure_time + (1 / max_frame_rate) but: "Some
    ## sensors support an overlap trigger mode (see Camera and sensor
    ## data). This feature allows overlapping the trigger for a new
    ## image capture with the readout of the previous image"

    def acquire(self) -> np.array:
        """Blocks and acquires image."""
        im_size = self.get_sensor_shape()
        bitspixel = self._get_bits_per_pixel()
        if bitspixel == 8:
            dtype = np.uint8
        else:
            dtype = np.uint16
        ## FIXME: what about 32?
        buffer = np.zeros(im_size, dtype=dtype)
        pid = ueye.c_int()
        ## INT is_AllocImageMem (HIDS hCam, INT width, INT height,
        ##                       INT bitspixel, char** ppcImgMem, INT* pid)
        status = ueye.is_AllocImageMem(self._hCam, im_size[0], im_size[1],
                                       bitspixel,
                                       buffer.ctypes.data_as(ctypes.c_char_p),
                                       pid)
        if status != ueye.IS_SUCCESS:
            raise RuntimeError('failed to alloc image')
        ## INT is_SetImageMem (HIDS hCam, char* pcImgMem, INT id)
        status = ueye.is_Set_ImageMem(self._hCam, buffer, pid)
        if status != ueye.IS_SUCCESS:
            raise RuntimeError('failed to set image mem')
        status = ueye.is_FreezeVideo(self._hCam, ueye.IS_WAIT) # blocking call
        if status != ueye.IS_SUCCESS:
            raise RuntimeError('failed to acquire image')

    def _get_bits_per_pixel(self):
        """Current number of bits per image pixel."""
        colormode = ueye.is_SetColorMode(self._hCam, ueye.IS_GET_COLOR_MODE)
        try:
            return _COLORMODE_TO_N_BITS[colormode]
        except KeyError:
            ## If it's not a colormode enum value, then it may be an
            ## error status code.
            raise RuntimeError('failed to get "colormode". Error code %d'
                               % colormode)


class TemperatureSensor:
    """The camera temperature sensor.

    I think this could be a device on its own right.  But maybe not.
    If we have it on the camera device and other functions needs the
    stuff from info, it's less memory.

    Not all cameras will have a temperature sensor.  Documentation
    says only USB3 and GigE uEye cameras.

    """
    def __init__(self, hCam):
        self._hCam = hCam
        self._info = ueye.IS_DEVICE_INFO()

    def get_temperature(self) -> float:
        status = ueye.is_DeviceInfo(self._hCam | ueye.IS_USE_DEVICE_ID,
                                    ueye.IS_DEVICE_INFO_CMD_GET_DEVICE_INFO,
                                    self._info, ctypes.sizeof(self._info))
        if status != ueye.IS_SUCCESS:
            raise RuntimeError('failed to get device info')

        ## Documentation for wTemperature (uint16_t)
        ##   Bit 15: algebraic sign
        ##   Bit 14...11: filled according to algebraic sign
        ##   Bit 10...4: temperature (places before the decimal point)
        ##   Bit 3...0: temperature (places after the decimal point)
        ##
        ## We have no clue what to do with bits 14...11.  Its's too
        ## much work to get an answer out of IDS support.
        bits = self._info.infoDevHeartbeat.wTemperature.value
        sign = bits >> 15
        integer_part = bits >> 4 & 0b111111
        fractional_part = bits & 0b1111
        return ((-1)**sign) * float(integer_part) + (fractional_part/16.0)


_BITS_TO_HORIZONTAL_BINNING = {
    0 : 1,
    ueye.IS_BINNING_2X_HORIZONTAL : 2,
    ueye.IS_BINNING_3X_HORIZONTAL : 3,
    ueye.IS_BINNING_4X_HORIZONTAL : 4,
    ueye.IS_BINNING_5X_HORIZONTAL : 5,
    ueye.IS_BINNING_6X_HORIZONTAL : 6,
    ueye.IS_BINNING_8X_HORIZONTAL : 8,
    ueye.IS_BINNING_16X_HORIZONTAL : 16,
}

_HORIZONTAL_BINNING_TO_BITS = {v:k for k, v in _BITS_TO_HORIZONTAL_BINNING.items()}

_BITS_TO_VERTICAL_BINNING = {
    0 : 1,
    ueye.IS_BINNING_2X_VERTICAL : 2,
    ueye.IS_BINNING_3X_VERTICAL : 3,
    ueye.IS_BINNING_4X_VERTICAL : 4,
    ueye.IS_BINNING_5X_VERTICAL : 5,
    ueye.IS_BINNING_6X_VERTICAL : 6,
    ueye.IS_BINNING_8X_VERTICAL : 8,
    ueye.IS_BINNING_16X_VERTICAL : 16,
}

_VERTICAL_BINNING_TO_BITS = {v:k for k, v in _BITS_TO_VERTICAL_BINNING.items()}

_COLORMODE_TO_N_BITS = {
    ueye.IS_CM_MONO8 : 8,
    ueye.IS_CM_SENSOR_RAW8: 8,
    ueye.IS_CM_MONO12 : 16,
    ueye.IS_CM_MONO16 : 16,
    ueye.IS_CM_SENSOR_RAW12 : 16,
    ueye.IS_CM_SENSOR_RAW16 : 16,
    ueye.IS_CM_BGR5_PACKED : 16,
    ueye.IS_CM_BGR565_PACKED : 16,
    ueye.IS_CM_UYVY_PACKED : 16,
    ueye.IS_CM_CBYCRY_PACKED : 16,
    ueye.IS_CM_RGB8_PACKED : 24,
    ueye.IS_CM_BGR8_PACKED : 24,
    ueye.IS_CM_RGBA8_PACKED : 32,
    ueye.IS_CM_BGRA8_PACKED : 32,
    ueye.IS_CM_RGBY8_PACKED : 32,
    ueye.IS_CM_BGRY8_PACKED : 32,
    ueye.IS_CM_RGB10_PACKED : 32,
    ueye.IS_CM_BGR10_PACKED : 32,
}