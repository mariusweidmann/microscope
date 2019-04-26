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
import typing
import unittest.mock


class MockCFuncPtr:
    def __init__(self, func: typing.Callable) -> None:
        self._func = func
        self.argtypes = [] # typing.Sequence[of ctypes]
        self.restype = ctypes.c_int

    def __call__(self, *args, **kwargs) -> typing.Any:
        prototype = ctypes.CFUNCTYPE(self.restype, *self.argtypes)
        func = prototype(self._func)
        return func(*args, **kwargs)


class MockLib:
    pass


class MockCDLL:
    def __init__(self, lib: MockLib) -> None:
        self._lib = lib

    def __getattr__(self, name: str) -> MockCFuncPtr:
        func = MockCFuncPtr(getattr(self._lib, name))
        setattr(self, name, func)
        return func


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
