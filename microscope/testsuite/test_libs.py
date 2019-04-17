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

"""Test units for the fake shared library used for tests.
"""

import ctypes
import unittest

import microscope.testsuite.libs
import microscope.testsuite.mock_devices

from microscope._defs import ueye

class TestLibueyeWithoutCamera(unittest.TestCase):
    """Test behavior when there is no camera connected."""
    def setUp(self):
        self.lib = microscope.testsuite.libs.MockLibueye()

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


class TestLibueyeBeforeInit(unittest.TestCase):
    """Tests for before `InitCamera`

    In the other test cases, a camera is plugged in *and* initialized
    as part of the test case setup.  These tests only have the camera
    connected.
    """
    def setUp(self):
        self.camera = microscope.testsuite.mock_devices.IDSCamera()
        self.lib = microscope.testsuite.libs.MockLibueye()
        self.lib.plug_in_camera(self.camera)

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


class TestLibueye(unittest.TestCase):
    """There is only one camera plugged in, so its device ID is 1.
    """
    def setUp(self):
        self.camera = microscope.testsuite.mock_devices.IDSCamera()
        self.lib = microscope.testsuite.libs.MockLibueye()
        self.lib.plug_in_camera(self.camera)
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


if __name__ == '__main__':
    unittest.main()
