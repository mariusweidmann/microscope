#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2019 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
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

import abc
import ctypes
import enum
import importlib
import typing
import unittest
import unittest.mock

import microscope.testsuite.mock
import microscope.testsuite.test_devices

## FIXME: Need better/cleaner?
##
## Import the camera module after the import of the wrapper with
## the mocked CDLL
with microscope.testsuite.mock.patched_cdll():
    from microscope._wrappers import ueye
import microscope.cameras.ids


class OperationMode(enum.Enum):
    """Operation modes of IDS cameras"""
    closed = 0 # not opened yet, or shutdown
    ## Operation modes (when opened, not closed):
    freerun = 1
    trigger = 2
    standby = 3


TRIGGER_MODES = [
    ueye.SET_TRIGGER_MASK,
    ueye.SET_TRIGGER_CONTINUOUS,
    ueye.SET_TRIGGER_HI_LO,
    ueye.SET_TRIGGER_LO_HI,
    ueye.SET_TRIGGER_SOFTWARE,
    ueye.SET_TRIGGER_HI_LO_SYNC,
    ueye.SET_TRIGGER_LO_HI_SYNC,
    ueye.SET_TRIGGER_PRE_HI_LO,
    ueye.SET_TRIGGER_PRE_LO_HI,
]


class UnexpectedUsageError(Exception):
    """Mock was used in an invalid manner.

    Mocks do not have to mock every possible behaviour, they should
    only mock the required behaviour.  This error is raised if such
    non mocked behaviour is requested.  For example, when passing an
    invalid parameter functions return an error code.  However, if we
    should never be calling the function in such incorrect manner, it
    makes the mock simpler to simply raise this exception.  This also
    ensures that a test case will fail.

    This exception differs from `NotImplementedError` in that it is
    raised when the reached state/behaviour is not meant to be mocked
    at all because it is undesirable to ever reach it in the first
    place.
    """
    pass


class IDSCameraMock(microscope.testsuite.mock.CameraMock,
                    metaclass=abc.ABCMeta):
    """Abstract Base Class for IDS camera mocks.

    It is not always clear if certain limitations should be placed on
    the camera or the SDK:

    - A camera starts in closed mode.  From there, it can only go into
      freerun mode via `is_InitCamera`.  Once in freerun mode, it can
      change to the trigger or standby mode.  However, we place that
      limitation on the SDK and not on the camera.  This makes it
      easier to create a camera mock at the state we need it for
      testing.

    - The default colourmode is not yet clear to us whether it should
      be defined on the SDK or the camera.  We are keeping it in the
      camera.
    """
    def __init__(self) -> None:
        self._operation_mode = OperationMode.closed # type: OperationMode
        self._trigger_mode = 0 # type: int

        self._reset_settings()

    @abc.abstractmethod
    def _reset_settings(self) -> None:
        """Set the modifiable properties"""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def supported_colourmodes(self) -> typing.Iterable[int]:
        ## This needs to be found by iterating over all colourmodes,
        ## and check SUCCESS in SetColorMode (hCam, Mode)
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def default_colourmode(self) -> int:
        ## The colourmode that is set after init the camera.
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def colourmode(self) -> int:
        """colourmode used for image data, not the sensor colourmode"""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def supported_trigger_modes_mask(self) -> int:
        """The supported modes linked by logical ORs"""
        ## Output of SetExternalTrigger(h, GET_SUPPORTED_TRIGGER_MODE)
        raise NotImplementedError()

    @property
    def supported_trigger_modes(self) -> typing.Iterable[int]:
        tmodes = []
        for tmode in TRIGGER_MODES:
            if (tmode & self.supported_trigger_modes_mask) == tmode:
                tmodes.append(tmode)
        return tmodes

    @property
    def unsupported_trigger_modes(self) -> typing.Iterable[int]:
        return set(TRIGGER_MODES) ^ set(self.supported_trigger_modes)

    @property
    def trigger_mode(self) -> int:
        ## No setter for this property, it's set when entering trigger
        ## mode.  To change, re-enter with a different trigger mode.
        if not self.on_trigger_mode():
            raise RuntimeError('no trigger mode when not in trigger mode')
        return self._trigger_mode

    def to_closed_mode(self) -> None:
        self._operation_mode = OperationMode.closed
        ## XXX: not sure if this should be called by the library
        self._reset_settings()

    def to_freerun_mode(self) -> None:
        self._operation_mode = OperationMode.freerun

    def to_trigger_mode(self, trigger_mode: int) -> None:
        ## FIXME: having an argument here seems like each should be
        ## its own state
        if trigger_mode not in self.supported_trigger_modes:
            raise ValueError('trigger mode not supported')
        self._trigger_mode = trigger_mode
        self._operation_mode = OperationMode.trigger

    def to_standby_mode(self) -> None:
        self._operation_mode = OperationMode.standby

    def on_closed_mode(self) -> bool:
        return self._operation_mode == OperationMode.closed

    def on_freerun_mode(self) -> bool:
        return self._operation_mode == OperationMode.freerun

    def on_trigger_mode(self) -> bool:
        return self._operation_mode == OperationMode.trigger

    def on_standby_mode(self) -> bool:
        return self._operation_mode == OperationMode.standby


def print_pixel_clock_info(handle):
    ## This info changes for each colourmode. Need a tool to get the
    ## info for each.
    pixel_clock_range = (ueye.UINT * 3)()
    status = ueye.PixelClock(handle, ueye.PIXELCLOCK_CMD.GET_RANGE,
                             ctypes.byref(pixel_clock_range),
                             ctypes.sizeof(pixel_clock_range))
    if status != ueye.SUCCESS:
        raise RuntimeError()
    if pixel_clock_range[2] != 0:
        raise RuntimeError('not discrete pixel clocks')

    ## number of pixel clocks changes.
    n_pixel_clocks = ueye.UINT(0)
    status = ueye.PixelClock(handle, ueye.PIXELCLOCK_CMD.GET_NUMBER,
                             ctypes.byref(n_pixel_clocks),
                             ctypes.sizeof(n_pixel_clocks))
    if status != ueye.SUCCESS:
        raise RuntimeError()
    print('this colourmode has %d pixel clocks' % n_pixel_clocks.value)

    pixel_clocks = (ueye.UINT * n_pixel_clocks.value)()
    status = ueye.PixelClock(handle, ueye.PIXELCLOCK_CMD.GET_LIST,
                             ctypes.byref(pixel_clocks),
                             ctypes.sizeof(pixel_clocks))
    if status != ueye.SUCCESS:
        raise RuntimeError()
    print('this colourmode has this pixel clocks', list(pixel_clocks))


class UI306xCP_M(IDSCameraMock):
    """Modelled after an UI-3060CP-M-GL Rev.2
    """

    def __init__(self) -> None:
        super().__init__()

        ## For CAMERA_INFO struct
        self.model = 'UI306xCP-M'
        self.full_model_name = 'UI306xCP-M'
        self.serial_number = '4103350857'
        self.camera_id = 1
        self.sensor_id = 538 # also for SENSORINFO

        ## For SENSORINFO struct
        self.sensor_name = 'UI306xCP-M'
        self.sensor_colourmode = 1 # IS_COLORMODE_MONOCHROME
        self.pixel_size = 5.86 # µm

    def _reset_settings(self) -> None:
        self._colourmode = self.default_colourmode
        ## FIXME: do time properly
        self._exposure_msec = 19.89156783

    @property
    def supports_enabling(self) -> bool:
        return True

    @property
    def sensor_width(self) -> int:
        return 1936

    @property
    def sensor_height(self) -> int:
        return 1216

    @property
    def supported_colourmodes(self) -> typing.Iterable[int]:
        ## This is a monochrome camera but these RGB and other colour
        ## modes are still supported (success with SetColorMode)
        return [
            ueye.CM_BGR10_PACKED,
            ueye.CM_BGR10_UNPACKED,
            ueye.CM_BGR12_UNPACKED,
            ueye.CM_BGR565_PACKED,
            ueye.CM_BGR5_PACKED,
            ueye.CM_BGR8_PACKED,
            ueye.CM_BGRA12_UNPACKED,
            ueye.CM_BGRA8_PACKED,
            ueye.CM_BGRY8_PACKED,
            ueye.CM_MONO10,
            ueye.CM_MONO12,
            ueye.CM_MONO16,
            ueye.CM_MONO8,
            ueye.CM_RGB10_UNPACKED,
            ueye.CM_RGB12_UNPACKED,
            ueye.CM_RGB8_PACKED,
            ueye.CM_RGB8_PLANAR,
            ueye.CM_RGBA12_UNPACKED,
            ueye.CM_RGBA8_PACKED,
            ueye.CM_RGBY8_PACKED,
            ueye.CM_SENSOR_RAW10,
            ueye.CM_SENSOR_RAW12,
            ueye.CM_SENSOR_RAW16,
            ueye.CM_SENSOR_RAW8,
            ueye.CM_UYVY_BAYER_PACKED,
            ueye.CM_UYVY_MONO_PACKED,
            ueye.CM_UYVY_PACKED,
        ]

    @property
    def default_colourmode(self) -> int:
        ## This is weird.  Even though this camera has a monochrome
        ## sensor, the defaul colourmode is a colour one :/
        return 1 # CM_BGR8_PACKED

    @property
    def colourmode(self) -> int:
        return self._colourmode

    @colourmode.setter
    def colourmode(self, new_colourmode: int) -> None:
        if new_colourmode in self.supported_colourmodes:
            self._colourmode = new_colourmode
        else:
            raise ValueError('not a supported colourmode')

    @property
    def supported_trigger_modes_mask(self) -> int:
        return 4107


class TestIDSCameraMock:
    """Tests for all IDS camera mocks, to be mixed in unittest.TestCase.

    For each IDS camera mock, we create a TestCase class, and define
    the `camera` property during `setUp()`.
    """

    ## Declared for type checking tools
    camera: IDSCameraMock
    assertTrue: typing.Callable
    assertEqual: typing.Callable

    def assertToClosed(self, msg=None):
        """Fail if camera does not change to closed mode"""
        self.camera.to_closed_mode()
        self.assertTrue(self.camera.on_closed_mode(), msg)

    def assertToFreerun(self, msg=None):
        """Fail if camera does not change to freerun mode"""
        self.camera.to_freerun_mode()
        self.assertTrue(self.camera.on_freerun_mode(), msg)

    def assertToStandby(self, msg=None):
        """Fail if camera does not change to standby mode"""
        self.camera.to_standby_mode()
        self.assertTrue(self.camera.on_standby_mode(), msg)

    def assertToTrigger(self, tmode: int, msg=None):
        """Fail if camera does not change to specified trigger mode"""
        self.camera.to_trigger_mode(tmode)
        self.assertTrue(self.camera.on_trigger_mode(), msg)
        self.assertEqual(self.camera.trigger_mode, tmode, msg)

    def test_starts_closed(self):
        self.assertTrue(self.camera.on_closed_mode())

    def test_to_freerun_mode_and_back(self):
        self.assertToFreerun()
        self.assertToClosed()

    def test_from_closed_to_standby_and_back(self):
        self.assertToStandby()
        self.assertToClosed()

    def test_from_closed_to_trigger_and_back(self):
        for tmode in self.camera.supported_trigger_modes:
            self.assertToTrigger(tmode)
            self.assertToClosed()

    def test_supported_trigger_modes(self):
        for tmode in self.camera.supported_trigger_modes:
            self.assertToTrigger(tmode)

    def test_unsupported_trigger_mode(self):
        """Unsupported modes fail and camera stays on previous mode"""
        self.camera.to_freerun_mode()
        for tmode in self.camera.unsupported_trigger_modes:
            with self.assertRaisesRegex(ValueError, ' mode not supported'):
                self.camera.to_trigger_mode(tmode)
            self.assertTrue(self.camera.on_freerun_mode())

    def test_getting_trigger_mode_in_other_modes(self):
        def assert_trigger_mode_getter_fails():
            with self.assertRaisesRegex(RuntimeError, 'not in trigger mode'):
                self.camera.trigger_mode
        self.assertToClosed()
        assert_trigger_mode_getter_fails()
        self.assertToFreerun()
        assert_trigger_mode_getter_fails()
        self.assertToStandby()
        assert_trigger_mode_getter_fails()


## Once we get mocks of different cameras, we will probably need some
## sort of dynamic creation of TestCase.  Probably we will need our
## own TestSuite and TestLoader.
class TestUI306xCP_MMock(TestIDSCameraMock, unittest.TestCase):
    def setUp(self):
        self.camera = UI306xCP_M()


class MockSystem:
    """Mock system where cameras are plugged and unplugged from.

    We are doing the device id assignment here on the system instead
    of the device.  I'm not sure what is more representative of
    reality.  At least this keeps the methods to plug/unplug cameras
    out of the lib.

    We need to check how it actually works if there is more than one
    device around.  The device ID is used all over the library but
    it's not persistent.  If they are given by order that they are
    connected, and IDs are reused, then unplugging a camera and
    plugging another will cause issues.  Right?

    .. todo::

       Confirm that device IDs are given by increasing order.  Restart
       system.  Plug device A and check its device ID.  We expect it
       to be 1.  Plug device B and check its device ID.  We expect it
       to be 2.

    .. todo::

       Check what happens when devices are plugged in and out.  Plug
        device A and check its device ID is 1.  Unplug device A.
        Plug device B and check it's device ID is 2 (or at least not
        1).  Plug device A again and check whether its device ID is
        the same as before.

    """
    def __init__(self) -> None:
        self._id_to_camera = {} # type: typing.Dict[int, IDSCameraMock]

    @property
    def n_cameras(self) -> int:
        return len(self._id_to_camera)

    @property
    def cameras(self) -> typing.Iterable[IDSCameraMock]:
        return self._id_to_camera.values()

    def get_camera(self, device_id: int) -> IDSCameraMock:
        """
        Throws `KeyError` if there is no such camera.
        """
        return self._id_to_camera[device_id]

    def get_device_id(self, camera: IDSCameraMock) -> int:
        device_ids = [i for i, c in self._id_to_camera.items() if c is camera]
        assert len(device_ids) == 1, 'somehow we broke internal dict'
        return device_ids[0]

    def plug_camera(self, camera: IDSCameraMock) -> None:
        ## TODO: this assumes that connecting camera A gets ID 1, then
        ## connecting camera B gets ID 2, unconnecting camera A frees
        ## ID 1.  Reconnecting camera A again will use ID 3.  Is this
        ## true?
        next_id = 1 + max(self._id_to_camera.keys(), default=0)
        self._id_to_camera[next_id] = camera

    def unplug_camera(self, camera: IDSCameraMock) -> None:
        """
        Throws `KeyError` if there is no such camera.
        """
        self._id_to_camera.pop(self.get_device_id(camera))

    def get_next_available_camera(self) -> typing.Optional[IDSCameraMock]:
        ## TODO: test if next really gives them sorted by id
        for device_id in sorted(self._id_to_camera):
            camera = self._id_to_camera[device_id]
            if camera.on_closed_mode():
                return camera
        return None # there is no available camera


class MockLibueye(microscope.testsuite.mock.MockLib):
    """Mocks IDS uEye API SDK version 4.90.0035"""
    def __init__(self, system: MockSystem) -> None:
        super().__init__()
        self._system = system


    def is_InitCamera(self, phCam, hWnd):
        if hWnd.value is not None:
            raise UnexpectedUsageError('we only run in DIB mode')
        hCam = phCam.contents

        if hCam.value == 0:
            device_id = 0
        elif not (hCam.value & 0x8000):
            raise UnexpectedUsageError("we don't init by camera id")
        else:
            device_id = hCam.value & (~0x8000)

        ## If any error happens, hCam is set to / remains zero.
        hCam.value = 0
        if device_id == 0:
            camera = self._system.get_next_available_camera()
            if camera is None:
                return 3 # IS_CANT_OPEN_DEVICE
        else:
            try:
                camera = self._system.get_camera(device_id)
            except KeyError: # no such device
                return 3 # IS_CANT_OPEN_DEVICE
        if not camera.on_closed_mode(): # device already open
            return 3 # IS_CANT_OPEN_DEVICE

        camera.to_freerun_mode()
        hCam.value = self._system.get_device_id(camera)
        return 0 # IS_SUCCESS


    def is_CameraStatus(self, hCam, nInfo, ulValue):
        try:
            camera = self._system.get_camera(hCam.value)
        except KeyError:
            return 1 # IS_INVALID_CAMERA_HANDLE

        if nInfo.value == ueye.STANDBY_SUPPORTED:
            if ulValue.value == ueye.GET_STATUS:
                if camera.supports_enabling:
                    return ueye.TRUE
                else:
                    ## TODO: in theory, this should return FALSE but
                    ## we never got access to such a camera so check
                    ## it first.
                    raise NotImplementedError()
            else:
                raise ValueError('to query standby, value must be GET_STATUS')

        elif nInfo.value == ueye.STANDBY:
            if ulValue.value == ueye.FALSE:
                camera.to_freerun_mode()
            elif ulValue.value == ueye.TRUE:
                camera.to_standby_mode()
            else:
                raise ValueError('to set standby, value must be TRUE or FALSE')
        else:
            raise UnexpectedusageError()
        return ueye.SUCCESS


    def is_DeviceInfo(self, hCam, nCommand, pParam, cbSizeOfParam):
        ## Despite using the same variable name, this function does
        ## not actually take the camera handle.  This is probably
        ## because is_DeviceInfo() works with cameras not yet opened.
        if hCam.value <= ueye.USE_DEVICE_ID:
            return 125 # IS_INVALID_PARAMETER

        device_id = hCam.value & (~ ueye.USE_DEVICE_ID)

        camera = self._system.get_camera(device_id)

        if nCommand.value == ueye.DEVICE_INFO_CMD_GET_DEVICE_INFO:
            ## TODO: this info we do use
            raise NotImplementedError()
        else:
            raise UnexpectedUsageError('invalid DeviceInfo command')


    def is_ExitCamera(self, hCam):
        try:
            camera = self._system.get_camera(hCam.value)
        except KeyError:
            return 1 # IS_INVALID_CAMERA_HANDLE
        if camera.on_closed_mode():
            return 1 # IS_INVALID_CAMERA_HANDLE
        camera.to_closed_mode()
        return 0 # IS_SUCCESS


    def is_GetCameraList(self, pucl):
        n_cameras = self._system.n_cameras

        ## If dwCount is zero, then it's a request to only get the
        ## number of devices and not to fill the rest of the device
        ## info.
        if pucl.contents.dwCount == 0:
            pucl.contents.dwCount = n_cameras
            return 0

        ## The SDK makes use of a nasty struct array hack.  Fail if we
        ## forget to do the proper casting.  If the casting was done
        ## right, then uci will always have a length of one.
        if len(pucl.contents.uci) != 1:
            raise RuntimeError('pucl need to be cast to PUEYE_CAMERA_LIST')

        ## The SDK can handle this case.  However, if we ever got to
        ## that state, we are already doing something wrong.
        if pucl.contents.dwCount != n_cameras:
            raise NotImplementedError('incorrect number of devices')

        uci_correct_type = ueye.UEYE_CAMERA_INFO * n_cameras
        full_uci = ctypes.cast(ctypes.byref(pucl.contents.uci),
                               ctypes.POINTER(uci_correct_type))
        ## XXX: WTF happens if there's gaps on device ids?
        for camera, uci in zip(self._system.cameras, full_uci.contents):
            uci.dwCameraID = camera.camera_id
            uci.dwDeviceID = self._system.get_device_id(camera)
            uci.dwSensorID = camera.sensor_id
            uci.dwInUse = 0 if camera.on_closed_mode() else 1
            uci.SerNo = camera.serial_number.encode()
            uci.Model = camera.model.encode()
            uci.FullModelName = camera.full_model_name.encode()
        return 0


    def is_GetNumberOfCameras(self, pnNumCams):
        pnNumCams.contents.value = self._system.n_cameras
        return 0


    def is_GetSensorInfo(self, hCam, pInfo):
        try:
            camera = self._system.get_camera(hCam.value)
        except KeyError:
            return 1

        if camera.on_closed_mode():
            return 1

        pInfo.contents.SensorID = camera.sensor_id
        pInfo.contents.strSensorName = camera.sensor_name.encode()
        pInfo.contents.nColorMode = camera.sensor_colourmode
        pInfo.contents.nMaxWidth = camera.sensor_width
        pInfo.contents.nMaxHeight = camera.sensor_height
        pInfo.contents.wPixelSize = int(camera.pixel_size * 100)
        return 0


    def is_SetColorMode(self, hCam, Mode):
        try:
            camera = self._system.get_camera(hCam.value)
        except KeyError:
            return 1 # IS_INVALID_CAMERA_HANDLE
        if camera.on_closed_mode():
            return 1 # IS_INVALID_CAMERA_HANDLE

        if Mode.value == ueye.GET_COLOR_MODE:
            return camera.colourmode
        elif camera.on_standby_mode():
            ## colourmode can't be set while on standby mode
            return 101 # INVALID_MODE

        try:
            camera.colourmode = Mode.value
        except ValueError:
            ## This can fail for two reasons.  The camera does not
            ## support this colourmode (INVALID_COLOR_FORMAT) or the
            ## value is not a colourmode (INVALID_PARAMETER).  We only
            ## mock the first behaviour because we don't have a list
            ## of all possible colourmodes.
            return 174 # INVALID_COLOR_FORMAT

        return 0


    def is_SetExternalTrigger(self, hCam, nTriggerMode):
        try:
            camera = self._system.get_camera(hCam.value)
        except KeyError:
            return 1
        if camera.on_closed_mode():
            return 1

        if nTriggerMode.value == ueye.GET_SUPPORTED_TRIGGER_MODE:
            return camera.supported_trigger_modes_mask
        elif nTriggerMode.value == ueye.GET_EXTERNALTRIGGER:
            if not camera.on_trigger_mode():
                return 0
            else:
                return camera.trigger_mode
        elif nTriggerMode.value == ueye.GET_TRIGGER_STATUS:
            raise NotImplementedError('not implemented return signal level')
        else:
            try:
                camera.to_trigger_mode(nTriggerMode.value)
            except ValueError:
                return -1 # NO_SUCCESS
            return 0


    def is_Exposure(self, hCam, nCommand, pParam, cbSizeOfParam):
        try:
            camera = self._system.get_camera(hCam.value)
        except KeyError:
            return 1
        if camera.on_closed_mode():
            return 1

        if nCommand.value == ueye.EXPOSURE_CMD.GET_EXPOSURE:
            if cbSizeOfParam.value != 8:
                return ueye.INVALID_PARAMETER
            param = ctypes.cast(pParam, ctypes.POINTER(ctypes.c_double))
            param.contents.value = camera._exposure_msec
            return 0
        else:
            raise NotImplementedError()


    def is_PixelClock(self, hCam, nCommand, pParam, cbSizeOfParam):
        raise NotImplementedError()


    def is_FreezeVideo(self, hCam, Wait):
        raise NotImplementedError()


    def is_SetBinning(self, hCam, mode):
        raise NotImplementedError()

    def is_SetImageMem(self, hCam, pcMem, pid):
        raise NotImplementedError()

    def is_SetAllocatedImageMem(self, hCam, width, height, bitspixel, pcImgMem,
                                pid):
        raise NotImplementedError()

    def is_FreeImageMem(self, hCam, pcMem, pid):
        raise NotImplementedError()


class TestLibueyeWithoutCamera(unittest.TestCase):
    """Test behavior when there are no cameras connected."""
    def setUp(self):
        self.system = MockSystem()
        lib  = MockLibueye(self.system)
        libnames = ['libueye_api.so', 'ueye_api', 'ueye_api_64']
        with microscope.testsuite.mock.mocked_c_dll(lib, libnames):
            self.lib = importlib.reload(ueye)

    def test_init_next_available_without_cameras(self):
        h = ueye.HIDS(0 | ueye.USE_DEVICE_ID)
        status = self.lib.InitCamera(ctypes.byref(h), None)
        self.assertEqual(status, 3)
        self.assertEqual(h.value, 0)

    def test_init_given_id_without_cameras(self):
        h = ueye.HIDS(1 | ueye.USE_DEVICE_ID)
        status = self.lib.InitCamera(ctypes.byref(h), None)
        self.assertEqual(status, 3)
        self.assertEqual(h.value, 0)

    def test_exit_without_cameras(self):
        h0 = ueye.HIDS(0)
        h1 = ueye.HIDS(1)
        self.assertEqual(self.lib.ExitCamera(h0), 1)
        self.assertEqual(self.lib.ExitCamera(h1), 1)

    def test_get_number_of_cameras(self):
        n_cameras = ctypes.c_int(1)
        status = self.lib.GetNumberOfCameras(ctypes.byref(n_cameras))
        self.assertEqual(status, 0)
        self.assertEqual(n_cameras.value, 0)


class TestLibueyeInitCamera(unittest.TestCase):
    """Test behaviour of is_InitCamera

    In most of our tests, we want a camera plugged in and already
    initialized as part of setUp.  In this TestCase we only have the
    camera connected, so we can test the initialisation itself.

    """
    def setUp(self):
        self.system = MockSystem()
        lib  = MockLibueye(self.system)
        libnames = ['libueye_api.so', 'ueye_api', 'ueye_api_64']
        with microscope.testsuite.mock.mocked_c_dll(lib, libnames):
            self.lib = importlib.reload(ueye)
        self.camera = UI306xCP_M()
        self.system.plug_camera(self.camera)

    def assertInitWithSuccess(self, h):
        status = self.lib.InitCamera(ctypes.byref(h), None)
        self.assertEqual(status, 0)
        self.assertEqual(h.value, 1)
        self.assertTrue(self.camera.on_freerun_mode())

    def test_camera_closed_before_init(self):
        self.assertTrue(self.camera.on_closed_mode())

    def test_init_by_camera_id(self):
        ## We never initialise a camera by its ID, so our mock should
        ## raise an exception if we ever try to do it.
        h = ueye.HIDS(1)
        with self.assertRaisesRegex(UnexpectedUsageError, 'camera id'):
            self.lib.InitCamera(ctypes.byref(h), None)

    def test_init_with_window_handle(self):
        h = ueye.HIDS(1)
        with self.assertRaisesRegex(UnexpectedUsageError, 'DIB mode'):
            self.lib.InitCamera(ctypes.byref(h), ctypes.c_void_p(1))

    def test_init_next(self):
        """Initialise the next available camera"""
        h = ueye.HIDS(0)
        self.assertInitWithSuccess(h)

    def test_init_next_by_device_id(self):
        """Initialise next available camera with USE_DEVICE_ID flag"""
        h = ueye.HIDS(0 | ueye.USE_DEVICE_ID)
        self.assertInitWithSuccess(h)

    def test_init_specific(self):
        """Initialise camera by device id"""
        h = ueye.HIDS(1 | ueye.USE_DEVICE_ID)
        self.assertInitWithSuccess(h)

    def test_exit_before_init(self):
        """Fails to ExitCamera an already closed camera"""
        h = ueye.HIDS(1)
        self.assertEqual(self.lib.ExitCamera(h), 1)
        self.assertEqual(h.value, 1)
        self.assertTrue(self.camera.on_closed_mode())

    def test_get_number_of_cameras(self):
        n_cameras = ctypes.c_int(0)
        status = self.lib.GetNumberOfCameras(ctypes.byref(n_cameras))
        self.assertEqual(status, 0)
        self.assertEqual(n_cameras.value, 1)

    def test_set_colourmode(self):
        """Fails to SetColorMode a closed camera"""
        status = self.lib.SetColorMode(ueye.HIDS(1), ueye.CM_MONO10)
        self.assertEqual(status, 1)

    def test_set_triggermode(self):
        """Fails to set trigger mode on a closed camera"""
        status = self.lib.SetExternalTrigger(ueye.HIDS(1),
                                             ueye.SET_TRIGGER_SOFTWARE)
        self.assertEqual(status, 1)


class TestLibueye(unittest.TestCase):
    """There is only one camera plugged in, so its device ID is 1.
    """
    def setUp(self):
        self.system = MockSystem()
        lib  = MockLibueye(self.system)
        libnames = ['libueye_api.so', 'ueye_api', 'ueye_api_64']
        with microscope.testsuite.mock.mocked_c_dll(lib, libnames):
            self.lib = importlib.reload(ueye)
        self.camera = UI306xCP_M()
        self.system.plug_camera(self.camera)

        self.h = ueye.HIDS(1 | ueye.USE_DEVICE_ID)
        status = self.lib.InitCamera(ctypes.byref(self.h), None)
        if status != 0:
            raise RuntimeError('error in InitCamera during setUp')

    def assertSuccess(self, status, msg=None):
        self.assertEqual(status, 0, msg)

    def test_initial_operation_mode(self):
        """After Init, camera is in freerun mode"""
        self.assertTrue(self.camera.on_freerun_mode())

    def test_init_twice(self):
        """Init a camera twice fails and invalidates the handle"""
        self.h = ueye.HIDS(self.h.value | ueye.USE_DEVICE_ID)
        status = self.lib.InitCamera(ctypes.byref(self.h), None)
        self.assertEqual(status, 3)
        self.assertEqual(self.h.value, 0)

        ## Calling Init twice fails because the camera is already
        ## open, but the camera itself should continue to work.
        self.assertTrue(self.camera.on_freerun_mode())

    def test_exit(self):
        """Exit an Init camera works"""
        self.assertSuccess(self.lib.ExitCamera(self.h))
        self.assertTrue(self.camera.on_closed_mode())

    def test_exit_twice(self):
        """Exit a closed camera fails"""
        self.assertSuccess(self.lib.ExitCamera(self.h))
        self.assertEqual(self.lib.ExitCamera(self.h), 1)
        self.assertTrue(self.camera.on_closed_mode())

    def test_to_standby(self):
        self.assertSuccess(self.lib.CameraStatus(self.h, ueye.STANDBY,
                                                 ueye.TRUE))
        self.assertTrue(self.camera.on_standby_mode())

    def test_to_standby_device_on_standby(self):
        self.camera.to_standby_mode()
        self.assertSuccess(self.lib.CameraStatus(self.h, ueye.STANDBY,
                                                 ueye.TRUE))
        self.assertTrue(self.camera.on_standby_mode())

    def test_out_of_standby(self):
        self.camera.to_standby_mode()
        self.assertSuccess(self.lib.CameraStatus(self.h, ueye.STANDBY,
                                                 ueye.FALSE))
        self.assertTrue(self.camera.on_freerun_mode())

    def test_out_of_standby_a_device_not_on_standby(self):
        ## After Init, a camera is in freerun mode.  Getting out of
        ## standby does not error, it simply does nothing.
        self.assertSuccess(self.lib.CameraStatus(self.h, ueye.STANDBY,
                                                 ueye.FALSE))
        self.assertTrue(self.camera.on_freerun_mode())

    def test_is_standby_supported(self):
        status = self.lib.CameraStatus(self.h, ueye.STANDBY_SUPPORTED,
                                       ueye.GET_STATUS)
        self.assertEqual(status, 1) # is supported

    def test_invalid_call_to_standby_supported(self):
        """Invalid usage of STANDBY_SUPPORTED raises exception"""
        ## To query whether the camera supports standby, is not enough
        ## to pass STANDBY_SUPPORTED.  The third argument must also be
        ## GET_STATUS.  If the third argument is incorrect, then
        ## CameraStatus returns SUCCESS which is the same as FALSE.
        ## This lead us to think that our camera did not support
        ## standby mode for a while.  Since we should never be calling
        ## CameraStatus in such incorrect manner, our mock raises an
        ## Exception.
        with self.assertRaisesRegex(ValueError, 'GET_STATUS'):
            self.lib.CameraStatus(self.h, ueye.STANDBY_SUPPORTED, ueye.TRUE)

    def test_get_number_of_cameras(self):
        n_cameras = ctypes.c_int(0)
        status = self.lib.GetNumberOfCameras(ctypes.byref(n_cameras))
        self.assertEqual(status, 0)
        self.assertEqual(n_cameras.value, 1)

    def test_empty_camera_list(self):
        """GetCameraList with dwCount 0 does not fill uci member"""
        camera_list = ueye.UEYE_CAMERA_LIST()
        status = self.lib.GetCameraList(ctypes.byref(camera_list))
        self.assertEqual(status, 0)
        self.assertEqual(camera_list.dwCount, 1)
        ## Because dwCount was set to zero, the camera info was not
        ## filled in.
        self.assertEqual(camera_list.uci[0].dwDeviceID, 0)
        self.assertEqual(camera_list.uci[0].SerNo, b'')

    def test_camera_list_of_incorrect_length(self):
        ## We should never be calling GetCameraList with a
        ## UEYE_CAMERA_LIST of incorrect length so our mock raises an
        ## exception if we try.
        camera_list = ueye.camera_list_factory(4)
        camera_list.dwCount = 4
        with self.assertRaisesRegex(NotImplementedError, 'number of devices'):
            self.lib.GetCameraList(ctypes.cast(ctypes.byref(camera_list),
                                               ueye.PUEYE_CAMERA_LIST))

    def test_get_camera_list(self):
        camera_list = ueye.UEYE_CAMERA_LIST()
        camera_list.dwCount = 1
        status = self.lib.GetCameraList(ctypes.pointer(camera_list))
        self.assertEqual(status, 0)
        self.assertEqual(camera_list.dwCount, 1)
        self.assertEqual(camera_list.uci[0].dwDeviceID, 1)
        self.assertEqual(camera_list.uci[0].dwInUse, 1)
        self.assertEqual(camera_list.uci[0].SerNo.decode(),
                         self.camera.serial_number)

    def test_get_standby_camera_list(self):
        """Standby cameras count as cameras in use"""
        self.camera.to_standby_mode()
        camera_list = ueye.UEYE_CAMERA_LIST()
        camera_list.dwCount = 1
        self.lib.GetCameraList(ctypes.pointer(camera_list))
        self.assertEqual(camera_list.uci[0].dwInUse, 1)

    def test_get_closed_camera_list(self):
        """Closed cameras are not in use"""
        self.camera.to_closed_mode()
        camera_list = ueye.UEYE_CAMERA_LIST()
        camera_list.dwCount = 1
        self.lib.GetCameraList(ctypes.pointer(camera_list))
        self.assertEqual(camera_list.uci[0].dwInUse, 0)

    def test_get_sensor_info(self):
        sensor_info = ueye.SENSORINFO()
        status = self.lib.GetSensorInfo(self.h, ctypes.byref(sensor_info))
        self.assertEqual(status, 0)
        self.assertEqual(sensor_info.nMaxWidth, self.camera.sensor_width)
        self.assertEqual(sensor_info.nMaxHeight, self.camera.sensor_height)
        self.assertEqual(sensor_info.nColorMode,
                         chr(self.camera.sensor_colourmode).encode())

    def test_set_colourmode(self):
        self.assertSuccess(self.lib.SetColorMode(self.h, ueye.CM_MONO16))
        self.assertEqual(self.camera.colourmode, ueye.CM_MONO16)

    def test_set_colourmode_invalid_id(self):
        status = self.lib.SetColorMode(ueye.HIDS(9), ueye.CM_MONO10)
        self.assertEqual(status, 1)

    def test_get_colourmode(self):
        self.assertEqual(self.lib.SetColorMode(self.h, ueye.GET_COLOR_MODE),
                         self.camera.colourmode)

    def test_set_unsupported_colourmode(self):
        self.assertEqual(self.lib.SetColorMode(self.h, ueye.CM_RGB10_PACKED),
                         ueye.INVALID_COLOR_FORMAT)
        ## There is also error code 125 (INVALID_PARAMETER) if we use
        ## an invalid colourmode such as CM_MODE_MASK.

    def test_get_colourmode_on_standby(self):
        """Can get current colourmode while on standby"""
        self.camera.to_standby_mode()
        self.assertEqual(self.lib.SetColorMode(self.h, ueye.GET_COLOR_MODE),
                         self.camera.colourmode)

    def test_set_colourmode_on_standby(self):
        self.camera.to_standby_mode()
        self.assertEqual(self.lib.SetColorMode(self.h, ueye.CM_MONO16),
                         ueye.INVALID_MODE)

    def test_set_same_colourmode_on_standby(self):
        ## Fails even if the "new" colourmode is the same as the current.
        self.camera.to_standby_mode()
        self.assertEqual(self.lib.SetColorMode(self.h, self.camera.colourmode),
                         ueye.INVALID_MODE)

    def test_set_triggermode(self):
        status = self.lib.SetExternalTrigger(self.h, ueye.SET_TRIGGER_SOFTWARE)
        self.assertSuccess(status)
        self.assertTrue(self.camera.on_trigger_mode())
        self.assertEqual(self.camera.trigger_mode, ueye.SET_TRIGGER_SOFTWARE)

    def test_set_triggermode_invalid_id(self):
        status = self.lib.SetExternalTrigger(ueye.HIDS(9),
                                             ueye.SET_TRIGGER_SOFTWARE)
        self.assertEqual(status, 1)

    def test_get_supported_trigger_modes(self):
        modes = self.lib.SetExternalTrigger(self.h,
                                            ueye.GET_SUPPORTED_TRIGGER_MODE)
        self.assertEqual(modes, 4107)

    def test_set_trigger_mode(self):
        status = self.lib.SetExternalTrigger(self.h, ueye.SET_TRIGGER_SOFTWARE)
        self.assertSuccess(status)
        self.assertTrue(self.camera.on_trigger_mode())
        self.assertEqual(self.camera.trigger_mode, ueye.SET_TRIGGER_SOFTWARE)

    def test_get_current_trigger_mode(self):
        self.camera.to_trigger_mode(ueye.SET_TRIGGER_SOFTWARE)
        mode = self.lib.SetExternalTrigger(self.h, ueye.GET_EXTERNALTRIGGER)
        self.assertEqual(mode, ueye.SET_TRIGGER_SOFTWARE)

    def test_get_current_trigger_mode_not_on_trigger_mode(self):
        """Trigger mode 0 when not on trigger mode"""
        mode = self.lib.SetExternalTrigger(self.h, ueye.GET_EXTERNALTRIGGER)
        self.assertEqual(mode, 0)
        self.camera.to_standby_mode()
        mode = self.lib.SetExternalTrigger(self.h, ueye.GET_EXTERNALTRIGGER)
        self.assertEqual(mode, 0)

    def test_set_unsupported_trigger_mode(self):
        status = self.lib.SetExternalTrigger(self.h, ueye.SET_TRIGGER_PRE_HI_LO)
        self.assertEqual(status, -1)



## TODO: need to add tests for GetCameraList with more than one camera
## so we can test for the struct hack there.

class InitUI306xCP_M(unittest.TestCase):
    def setUp(self):
        system = MockSystem()

        ## TODO: Maybe the libnames should be properties on the lib?
        ## Or maybe we should limit the patching to the only place
        ## where the patch is needed and skip the names altogether,
        lib  = MockLibueye(system)
        libnames = ['libueye_api.so', 'ueye_api', 'ueye_api_64']

        with microscope.testsuite.mock.mocked_c_dll(lib, libnames):
            ## We only need to reload the ueye wrapper module, since
            ## it also affects the already loaded ids camera module.
            importlib.reload(ueye)

        self.fake = UI306xCP_M()
        system.plug_camera(self.fake)

    def test_init_by_serial_number(self):
        self.device = microscope.cameras.ids.IDSuEye(self.fake.serial_number)

    def test_incorrect_serial_number(self):
        with self.assertRaisesRegex(RuntimeError, 'serial number'):
            microscope.cameras.ids.IDSuEye('1' + self.fake.serial_number)


class TestUI306xCP_M(unittest.TestCase,
                     microscope.testsuite.test_devices.CameraTests):
    def setUp(self):
        system = MockSystem()

        ## TODO: Maybe the libnames should be properties on the lib?
        ## Or maybe we should limit the patching to the only place
        ## where the patch is needed and skip the names altogether,
        lib  = MockLibueye(system)
        libnames = ['libueye_api.so', 'ueye_api', 'ueye_api_64']

        with microscope.testsuite.mock.mocked_c_dll(lib, libnames):
            ## We only need to reload the ueye wrapper module, since
            ## it also affects the already loaded ids camera module.
            importlib.reload(ueye)

        self.fake = UI306xCP_M()
        system.plug_camera(self.fake)
        self.device = microscope.cameras.ids.IDSuEye()

    def tearDown(self):
        self.device.shutdown()


if __name__ == '__main__':
    unittest.main()
