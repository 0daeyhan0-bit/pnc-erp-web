import ctypes
import os

pborca_dll = r"C:\Program Files (x86)\Sybase\Shared\PowerBuilder\pborc105.dll"
orca = ctypes.WinDLL(pborca_dll)

# SessionOpen & SessionClose
orca.PBORCA_SessionOpen.restype = ctypes.c_void_p
orca.PBORCA_SessionOpen.argtypes = []

orca.PBORCA_SessionClose.restype = None
orca.PBORCA_SessionClose.argtypes = [ctypes.c_void_p]

h_session = orca.PBORCA_SessionOpen()
print("Session Handle:", h_session)

if h_session:
    orca.PBORCA_SessionClose(h_session)
    print("Session closed successfully.")
