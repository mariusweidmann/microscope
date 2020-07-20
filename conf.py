from microscope.devices import device
from microscope.cameras import ids
from microscope.testsuite.devices import TestLaser
DEVICES = [
     device(ids, '127.0.0.1', 8005),
     device(ids, '127.0.0.1', 8006),
     device(TestLaser, '127.0.0.1', 8007),
]
