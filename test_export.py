import sys
import os
import struct

print("Python Bitness:", struct.calcsize("P") * 8)
pborca_dll = r"C:\Program Files (x86)\Sybase\Shared\PowerBuilder\pborc105.dll"
print("DLL Exists:", os.path.exists(pborca_dll))
