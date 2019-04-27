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

import contextlib
import ctypes
import enum
import importlib
import sys
import typing
import unittest
import unittest.mock

import microscope.testsuite.mock
import microscope.testsuite.test_devices

## FIXME: Need better/cleaner?
##
## Import the camera module after the import of the wrapper with
## the mocked CDLL
with unittest.mock.patch('ctypes.CDLL'):
    from microscope._wrappers import ueye
import microscope.cameras.ids


class CameraMock:
    pass


class UI306xCP_M(CameraMock):
    """Modelled after an UI-3060CP-M-GL Rev.2
    """

    class OperationMode(enum.Enum):
        closed = 0 # not opened yet, or shutdown
        ## Operation modes (when opened, not closed):
        freerun = 1
        trigger = 2
        standby = 3

    def __init__(self) -> None:
        self.operation_mode = self.OperationMode.closed # type: OperationMode

        ## For CAMERA_INFO struct
        self.model = 'UI306xCP-M'
        self.full_model_name = 'UI306xCP-M'
        self.serial_number = '4103350857'
        self.camera_id = 1
        self.sensor_id = 538 # also for SENSORINFO

        ## For SENSORINFO struct
        self.sensor_name = 'UI306xCP-M'
        self.width = 1936
        self.height = 1216
        self.pixel_size = 5.86 # µm

        self._reset_settings()

    def supports_standby(self) -> bool:
        return True

    def _reset_settings(self) -> None:
        pass

    def on_closed(self) -> bool:
        return self.operation_mode == self.OperationMode.closed

    def on_open(self) -> bool:
        """Not really an operation mode, just a mode other than closed"""
        return not self.on_closed()

    def on_freerun(self) -> bool:
        return self.operation_mode == self.OperationMode.freerun

    def on_trigger(self) -> bool:
        return self.operation_mode == self.OperationMode.trigger

    def on_standby(self) -> bool:
        return self.operation_mode == self.OperationMode.standby

    def to_freerun_mode(self) -> None:
        self.operation_mode = self.OperationMode.freerun

    def to_trigger_mode(self) -> None:
        self.operation_mode = self.OperationMode.trigger

    def to_standby_mode(self) -> None:
        self.operation_mode = self.OperationMode.standby

    def to_closed_mode(self) -> None:
        self.operation_mode = self.OperationMode.closed
        self._reset_settings()


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
        self._id_to_camera = {} # type: dict[int, CameraMock]

    @property
    def n_cameras(self) -> int:
        return len(self._id_to_camera)

    @property
    def cameras(self) -> typing.Sequence[CameraMock]:
        return self._id_to_camera.values()

    def get_camera(self, device_id: int) -> CameraMock:
        ## May throw KeyError
        return self._id_to_camera[device_id]

    def get_device_id(self, camera: CameraMock) -> int:
        device_ids = [i for i, c in self._id_to_camera.items() if c is camera]
        assert len(device_ids) == 1, 'somehow we broke internal dict'
        return device_ids[0]

    def plug_camera(self, camera: CameraMock) -> None:
        ## TODO: this assumes that connecting camera A gets ID 1, then
        ## connecting camera B gets ID 2, unconnecting camera A frees
        ## ID 1.  Reconnecting camera A again will use ID 3.  Is this
        ## true?
        next_id = 1 + max(self._id_to_camera.keys(), default=0)
        self._id_to_camera[next_id] = camera

    def unplug_camera(self, camera: CameraMock) -> None:
        self._id_to_camera.pop(self.get_device_id(camera))

    def get_next_available_camera(self) -> typing.Optional[CameraMock]:
        for device_id in sorted(self._id_to_camera):
            camera = self._id_to_camera[device_id]
            if camera.on_closed():
                return camera
        ## returns None if there is no available camera


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
        if camera.on_open():
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
                if camera.supports_standby():
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
        if camera.on_closed():
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
            uci.dwInUse = 1 if camera.on_open() else 0
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

        if camera.on_closed():
            return 1

        pInfo.contents.SensorID = camera.sensor_id
        pInfo.contents.strSensorName = camera.sensor_name.encode()
#        pInfo.contents.nColorMode = camera. # TODO: colormode
        pInfo.contents.nMaxWidth = camera.width
        pInfo.contents.nMaxHeight = camera.height
        pInfo.contents.wPixelSize = int(camera.pixel_size * 100)
        return 0


    def is_SetColorMode(self):
        pass
    def is_SetExternalTrigger(self):
        pass


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
        self.assertTrue(self.camera.on_freerun())

    def test_camera_closed_before_init(self):
        self.assertTrue(self.camera.on_closed())

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
        self.assertTrue(self.camera.on_closed())

    def test_get_number_of_cameras(self):
        n_cameras = ctypes.c_int(0)
        status = self.lib.GetNumberOfCameras(ctypes.byref(n_cameras))
        self.assertEqual(status, 0)
        self.assertEqual(n_cameras.value, 1)


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

    def test_initial_operation_mode(self):
        """After Init, camera is in freerun mode"""
        self.assertTrue(self.camera.on_freerun())

    def test_init_twice(self):
        """Init a camera twice fails and invalidates the handle"""
        self.h = ueye.HIDS(self.h.value | ueye.USE_DEVICE_ID)
        status = self.lib.InitCamera(ctypes.byref(self.h), None)
        self.assertEqual(status, 3)
        self.assertEqual(self.h.value, 0)

        ## Calling Init twice fails because the camera is already
        ## open, but the camera itself continues to work fine.
        self.assertTrue(self.camera.on_freerun())

    def test_exit(self):
        """Exit an Init camera works"""
        self.assertEqual(self.lib.ExitCamera(self.h), 0)
        self.assertTrue(self.camera.on_closed())

    def test_exit_twice(self):
        """Exit a closed camera fails"""
        self.assertEqual(self.lib.ExitCamera(self.h), 0)
        self.assertEqual(self.lib.ExitCamera(self.h), 1)
        self.assertTrue(self.camera.on_closed())

    def test_to_standby(self):
        status = self.lib.CameraStatus(self.h, ueye.STANDBY, ueye.TRUE)
        self.assertEqual(status, 0)
        self.assertTrue(self.camera.on_standby())

    def test_to_standby_device_on_standby(self):
        self.camera.to_standby_mode()
        status = self.lib.CameraStatus(self.h, ueye.STANDBY, ueye.TRUE)
        self.assertEqual(status, 0)
        self.assertTrue(self.camera.on_standby())

    def test_out_of_standby(self):
        self.camera.to_standby_mode()
        status = self.lib.CameraStatus(self.h, ueye.STANDBY, ueye.FALSE)
        self.assertEqual(status, 0)
        self.assertTrue(self.camera.on_freerun())

    def test_out_of_standby_a_device_not_on_standby(self):
        ## After Init, a camera is in freerun mode.  Getting out of
        ## standby does not error, it simply does nothing.
        status = self.lib.CameraStatus(self.h, ueye.STANDBY, ueye.FALSE)
        self.assertEqual(status, 0)
        self.assertTrue(self.camera.on_freerun())

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
        status = self.lib.GetSensorInfo(self.h.value, ctypes.byref(sensor_info))
        self.assertEqual(status, 0)
        for attr, val in [('nMaxWidth', 1936), ('nMaxHeight', 1216),]:
            self.assertEqual(getattr(sensor_info, attr), val)

## TODO: need to add tests for GetCameraList with more than one camera
## so we can test for the struct hack there.


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
