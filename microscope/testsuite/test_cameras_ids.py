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


class IDSCameraMock(microscope.testsuite.mock.CameraMock,
                    metaclass=abc.ABCMeta):
    def __init__(self) -> None:
        self._operation_mode = OperationMode.closed # type: OperationMode
        self._trigger_mode = 0 # type: int

    @property
    @abc.abstractmethod
    def supported_trigger_modes(self) -> typing.Iterable[int]:
        """A list of all supported modes"""
        raise NotImplementedError()

    @property
    def unsupported_trigger_modes(self) -> typing.Iterable[int]:
        return set(TRIGGER_MODES) ^ set(self.supported_trigger_modes)

    @property
    def _supported_trigger_modes_mask(self) -> int:
        mask = 0
        for mode in self.supported_trigger_modes:
            mask |= mode
        return mask

    @property
    def trigger_mode(self) -> int:
        ## No setter for this property, it's set when entering trigger
        ## mode.  To change, re-enter with a different trigger mode.
        if not self.on_trigger_mode():
            raise RuntimeError('no trigger mode when not in trigger mode')
        return self._trigger_mode

    def to_closed_mode(self) -> None:
        self._operation_mode = OperationMode.closed

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
        self.sensor_colourmode = 1
        self.pixel_size = 5.86 # µm

        ## This is a monochrome camera but these RGB and other colour
        ## modes are still supported.  Well, SetColorMode returns
        ## success.  This is weird
        self._supported_colourmodes = [
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
        self._colourmode = 0 # type: int

        ## FIXME: do time properly
        self._exposure_msec = 19.89156783

        self._reset_settings()

    def supports_enabling(self) -> bool:
        return True

    @property
    def sensor_width(self) -> int:
        return 1936

    @property
    def sensor_height(self) -> int:
        return 1216

    @property
    def supported_trigger_modes(self) -> typing.Iterable[int]:
        return [
            ueye.SET_TRIGGER_SOFTWARE,
            ueye.SET_TRIGGER_HI_LO,
            ueye.SET_TRIGGER_LO_HI,
        ]

    @property
    def colourmode(self):
        return self._colourmode

    @colourmode.setter
    def colourmode(self, new_colourmode):
        if new_colourmode in self._supported_colourmodes:
            self._colourmode = new_colourmode
        else:
            raise ValueError('not supported')

    def _reset_settings(self) -> None:
        ## Default mode is colour, despite this being a monochrome camera.
        self._colourmode = ueye.CM_BGR8_PACKED

    def to_closed_mode(self) -> None:
        super().to_closed_mode()
        self._reset_settings()


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
        self.camera.to_closed_mode()
        self.assertTrue(self.camera.on_closed_mode(), msg)

    def assertToFreerun(self, msg=None):
        self.camera.to_freerun_mode()
        self.assertTrue(self.camera.on_freerun_mode(), msg)

    def assertToStandby(self, msg=None):
        self.camera.to_standby_mode()
        self.assertTrue(self.camera.on_standby_mode(), msg)

    def assertToTrigger(self, tmode: int, msg=None):
        self.camera.to_trigger_mode(tmode)
        self.assertTrue(self.camera.on_trigger_mode(), msg)
        self.assertEqual(self.camera.trigger_mode, tmode, msg)

    def test_starts_closed(self):
        self.assertTrue(self.camera.on_closed_mode())

    def test_to_freerun_mode_and_back(self):
        self.assertToFreerun()
        self.assertToClosed()

    def test_from_closed_to_standby_and_back(self):
        ## When camera is in closed mode, the SDK only allows going to
        ## freerun mode.  We have that limitation on our mock of the
        ## SDK but not on the camera itself because makes it easier to
        ## write tests that start with the camera in a specific state.
        self.assertToStandby()
        self.assertToClosed()

    def test_from_closed_to_trigger_and_back(self):
        ## See other comment about testing from closed to trigger mode
        for tmode in self.camera.supported_trigger_modes:
            self.assertToTrigger(tmode)
            break # only the first is from closed mode
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
        def test_it_fails():
            with self.assertRaisesRegex(RuntimeError, 'not in trigger mode'):
                self.camera.trigger_mode
        test_it_fails() # in closed mode
        self.assertToFreerun()
        test_it_fails()
        self.assertToStandby()
        test_it_fails()


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
        ## May throw KeyError
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
        self._id_to_camera.pop(self.get_device_id(camera))

    def get_next_available_camera(self) -> typing.Optional[IDSCameraMock]:
        for device_id in sorted(self._id_to_camera):
            camera = self._id_to_camera[device_id]
            if camera.on_closed_mode():
                return camera
        return None # there is no available camera


class MockLibueye(microscope.testsuite.mock.MockLib):
    """Mocks IDS uEye API SDK, based on version 4.90."""
    def __init__(self, system: MockSystem) -> None:
        super().__init__()
        self._system = system


    def is_InitCamera(self, phCam, hWnd):
        if hWnd.value is not None:
            raise NotImplementedError('we only run in DIB mode')
        hCam = phCam.contents

        if hCam.value == 0:
            device_id = 0
        elif not (hCam.value & 0x8000):
            raise NotImplementedError("we don't init by camera id")
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
                if camera.supports_enabling():
                    return ueye.TRUE
                else:
                    ## TODO: in theory, this should return FALSE but
                    ## we never got access to such a camera so check
                    ## it first.
                    raise NotImplementedError()
            else:
                raise RuntimeError('for query, ulValue must be GET_STATUS')

        elif nInfo.value == ueye.STANDBY:
            if ulValue.value == ueye.FALSE:
                camera.to_freerun_mode()
            elif ulValue.value == ueye.TRUE:
                camera.to_standby_mode()
            else:
                raise NotImplementedError()
        else:
            raise NotImplementedError()
        return ueye.SUCCESS


    def is_DeviceInfo(self):
        pass


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
            return camera._supported_trigger_modes_mask
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


class TestLibueyeWithoutCamera(unittest.TestCase):
    """Test behavior when there is no camera connected."""
    def setUp(self):
        self.system = MockSystem()

        lib  = MockLibueye(self.system)
        libnames = ['libueye_api.so', 'ueye_api', 'ueye_api_64']
        with microscope.testsuite.mock.mocked_c_dll(lib, libnames):
            self.lib = importlib.reload(ueye)

    def test_init_next_without_devices(self):
        h = ueye.HIDS(0 | ueye.USE_DEVICE_ID)
        status = self.lib.InitCamera(ctypes.byref(h), None)
        self.assertEqual(status, 3)
        self.assertEqual(h.value, 0)

    def test_init_specific_without_devices(self):
        h = ueye.HIDS(1 | ueye.USE_DEVICE_ID)
        status = self.lib.InitCamera(ctypes.byref(h), None)
        self.assertEqual(status, 3)
        self.assertEqual(h.value, 0)

    def test_exit(self):
        h0 = ueye.HIDS(0)
        h1 = ueye.HIDS(1)
        self.assertEqual(self.lib.ExitCamera(h0), 1)
        self.assertEqual(self.lib.ExitCamera(h1), 1)

    def test_get_number_of_cameras(self):
        n_cameras = ctypes.c_int(1)
        status = self.lib.GetNumberOfCameras(ctypes.byref(n_cameras))
        self.assertEqual(status, 0)
        self.assertEqual(n_cameras.value, 0)

    def test_set_colourmode(self):
        status = self.lib.SetColorMode(ueye.HIDS(1), ueye.CM_MONO10)
        self.assertEqual(status, 1)

    def test_set_triggermode(self):
        status = self.lib.SetExternalTrigger(ueye.HIDS(1),
                                             ueye.SET_TRIGGER_SOFTWARE)
        self.assertEqual(status, 1)


class TestLibueyeBeforeInit(unittest.TestCase):
    """Tests for before `InitCamera`

    In the other test cases, a camera is plugged in *and* initialized
    as part of the test case setup.  These tests only have the camera
    connected.
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

    def test_init_with_window_handle(self):
        h = ueye.HIDS(1)
        with self.assertRaisesRegex(NotImplementedError, 'DIB mode'):
            self.lib.InitCamera(ctypes.byref(h), ctypes.c_void_p(1))

    def test_camera_closed_before_init(self):
        self.assertTrue(self.camera.on_closed_mode())

    def test_init_by_camera_id(self):
        h = ueye.HIDS(1)
        with self.assertRaisesRegex(NotImplementedError, 'camera id'):
            self.lib.InitCamera(ctypes.byref(h), None)

    def test_init_next(self):
        h = ueye.HIDS(0)
        self.assertInitWithSuccess(h)

    def test_init_next_by_device_id(self):
        """Init next available works even with USE_DEVICE_ID flag"""
        h = ueye.HIDS(0 | ueye.USE_DEVICE_ID)
        self.assertInitWithSuccess(h)

    def test_init_specific(self):
        h = ueye.HIDS(1 | ueye.USE_DEVICE_ID)
        self.assertInitWithSuccess(h)

    def test_exit_before_init(self):
        """Exit before Init fails"""
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
        status = self.lib.SetColorMode(ueye.HIDS(1), ueye.CM_MONO10)
        self.assertEqual(status, 1)

    def test_set_triggermode(self):
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
        ## open, but the camera itself continues to work fine.
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

    def test_invalid_standby_supported(self):
        ## We made a similar error for a while and though that our
        ## camera did not support standby mode.  What really happens
        ## if the third argument is not GET_VALUE, is that the library
        ## returns SUCCESS which is the same as FALSE.  On our fake
        ## lib, we just raise an error since we should never be
        ## triggering it.
        with self.assertRaisesRegex(RuntimeError, 'GET_STATUS'):
            self.lib.CameraStatus(self.h, ueye.STANDBY_SUPPORTED, ueye.TRUE)

    def test_get_number_of_cameras(self):
        n_cameras = ctypes.c_int(0)
        status = self.lib.GetNumberOfCameras(ctypes.byref(n_cameras))
        self.assertEqual(status, 0)
        self.assertEqual(n_cameras.value, 1)

    def test_empty_camera_list(self):
        camera_list = ueye.UEYE_CAMERA_LIST()
        status = self.lib.GetCameraList(ctypes.byref(camera_list))
        self.assertEqual(status, 0)
        self.assertEqual(camera_list.dwCount, 1)
        ## Because dwCount was set to zero, the camera info was not
        ## filled in.
        self.assertEqual(camera_list.uci[0].dwDeviceID, 0)
        self.assertEqual(camera_list.uci[0].SerNo, b'')

    def test_camera_list_of_incorrect_length(self):
        camera_list = ueye.camera_list_type_factory(4)()
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
        self.assertEqual(camera_list.uci[0].SerNo, b'4103350857')

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
        for attr, val in [('nMaxWidth', self.camera.sensor_width),
                          ('nMaxHeight', self.camera.sensor_height),
                          ('nColorMode', chr(self.camera.sensor_colourmode).encode()),]:
            self.assertEqual(getattr(sensor_info, attr), val)

    def test_set_colourmode(self):
        self.assertSuccess(self.lib.SetColorMode(self.h, ueye.CM_MONO16))
        self.assertEqual(self.camera.colourmode, ueye.CM_MONO16)

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


if __name__ == '__main__':
    unittest.main()
