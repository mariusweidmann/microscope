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
import contextlib
import ctypes
import typing
import unittest.mock


class DeviceMock(metaclass=abc.ABCMeta):
    """Base class for mocking of a device hardware

    You probably should be subclassing the base classes for device
    specific hardware such as `LaserMock`, `CameraMock`, etc.

    """
    @property
    @abc.abstractmethod
    def supports_enabling(self) -> bool:
        """Whether this device can be enabled/disabled.

        A device that supports this can be enabled and disabled
        multiple times, it is not a one time thing only.
        """
        raise NotImplementedError()


class LaserMock(DeviceMock, metaclass=abc.ABCMeta):
    @property
    @abc.abstractmethod
    def min_power(self) -> float:
        """Min power in mW laser is capable of."""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def max_power(self) -> float:
        """Max power in mW laser is capable of."""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def current_power(self) -> float:
        """The current laser power in mW (should return 0 if off)"""
        raise NotImplementedError()

    @current_power.setter
    @abc.abstractmethod
    def current_power(self, power: float) -> None:
        """Set current laser power.

        Should raise an erro if trying to set outside the valid range
        or the device is off.
        """
        raise NotImplementedError()


class DeformableMirrorMock(DeviceMock, metaclass=abc.ABCMeta):
    @property
    @abc.abstractmethod
    def n_actuators(self) -> int:
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def current_pattern(self): # -> numpy.ndarray (1D)
        raise NotImplementedError()


class CameraMock(DeviceMock, metaclass=abc.ABCMeta):
    @property
    @abc.abstractmethod
    def sensor_width(self) -> int:
        """Width of sensor in pixels"""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def sensor_height(self) -> int:
        """Height of sensor in pixels"""
        raise NotImplementedError()


class MockCFuncPtr:
    """Mock a C function, the attributes of a CDLL.

    This mock is stricter than the real Python as it requires the
    argtypes to be defined and defaults to an empty list instead of
    `None`.
    """
    def __init__(self, func: typing.Callable) -> None:
        self._func = func
        self.argtypes = [] # type: typing.Sequence
        self.restype = ctypes.c_int

    def __call__(self, *args) -> typing.Any:
        ## With real ctypes functions, there is only an error if there
        ## are not enough arguments and extra arguments are silently
        ## discarded.  We are a bit more strict on the mock.
        if len(args) != len(self.argtypes):
            raise TypeError('this function takes %d arguments (%d given)'
                            % (len(self.argtypes), len(args)))

        ctypes_args = []
        for arg, argtype in zip(args, self.argtypes):
            ## Documentation of ctypes has other conversions.  There
            ## are custom classes with from_param() class methods and
            ## automatically converting to pointers.  We haven't
            ## needed them yet so we don't mock them yet.
            if isinstance(arg, argtype):
                pass
            elif arg.__class__.__name__ == 'CArgObject':
                ## This is a pointer created with byref, so get a
                ## real pointer.
                arg = argtype(arg._obj)
            else:
                arg = argtype(arg)
            ctypes_args.append(arg)

        retval = self._func(*ctypes_args)

        ## Confirm that the return value is of correct type, or at
        ## least can be converted to it.  Do return the python data
        ## type though.
        try:
            self.restype(retval)
        except TypeError:
            raise TypeError('this function return value is not compatible')
        return retval


class MockLib:
    pass


class MockCDLL:
    def __init__(self, lib: MockLib) -> None:
        self._lib = lib

    def __getattr__(self, name: str) -> MockCFuncPtr:
        func = MockCFuncPtr(getattr(self._lib, name))
        setattr(self, name, func)
        return func

    ## We didn't bother implementing __getitem__ because we don't yet
    ## needed to mock a library whose functions are exported by
    ## ordinal.


@contextlib.contextmanager
def patched_cdll():
    """Context for CDLL MagickMock.

    .. todo::

       Merge with the version that replaces with a specific mock.
    """
    with unittest.mock.patch('ctypes.CDLL') as patch_cdll:
        ## WinDLL will only exist on windows systems.
        with unittest.mock.patch('ctypes.WinDLL', create=True) as patch_windll:
            yield (patch_cdll, patch_windll)

@contextlib.contextmanager
def mocked_c_dll(lib: MockLib, names: typing.Sequence[str]):
    """Patches the loading of dlls to return a mock.

    Args:
        lib: a mock of the library that will be used.
        names: list of library names that may be passed to ctypes.CDLL
            and ctypes.WinDLL constructors.

    .. todo::
       Maybe the names argument should be a property of the mock lib?

    .. todo::
       We need to provide a redirec for WinDLL too.
    """
    def redirect(name: str, *args, **kwargs):
        if name in names:
            return MockCDLL(lib)
        else:
            ctypes.CDLL(*args, **kwargs)

    patches = []
    patches.append(unittest.mock.patch('ctypes.CDLL', new=redirect))
    ## TODO: add redirect to WinDLL to the patches here
    with contextlib.ExitStack() as stack:
        for patch in patches:
            stack.enter_context(patch)
        yield patches
