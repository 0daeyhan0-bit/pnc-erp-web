import ctypes
import os

pborca_dll = r"C:\Program Files (x86)\Sybase\Shared\PowerBuilder\pborc105.dll"
orca = ctypes.WinDLL(pborca_dll)

class PBORCA_ENTRYINFO(ctypes.Structure):
    _fields_ = [
        ("lpszEntryName", ctypes.c_char * 256),
        ("lpszComments", ctypes.c_char * 256),
        ("lEntrySize", ctypes.c_int32),
        ("otEntryType", ctypes.c_int32),
        ("lCreateTime", ctypes.c_int32)
    ]

# Callback prototype: void __stdcall (PPBORCA_ENTRYINFO, void*)
DIRPROC = ctypes.WINFUNCTYPE(None, ctypes.POINTER(PBORCA_ENTRYINFO), ctypes.c_void_p)

entries = []

def dir_callback(p_entry_info, p_user_data):
    entry = p_entry_info.contents
    name = entry.lpszEntryName.decode('cp949', errors='ignore')
    etype = entry.otEntryType
    esize = entry.lEntrySize
    entries.append((name, etype, esize))

cb_func = DIRPROC(dir_callback)

orca.PBORCA_SessionOpen.restype = ctypes.c_void_p
orca.PBORCA_SessionOpen.argtypes = []

orca.PBORCA_SessionClose.restype = None
orca.PBORCA_SessionClose.argtypes = [ctypes.c_void_p]

orca.PBORCA_LibraryDirectory.restype = ctypes.c_int
orca.PBORCA_LibraryDirectory.argtypes = [
    ctypes.c_void_p,
    ctypes.c_char_p,
    ctypes.c_char_p,
    ctypes.c_int,
    DIRPROC,
    ctypes.c_void_p
]

h_session = orca.PBORCA_SessionOpen()
pbl_path = r"C:\Users\hdy56\OneDrive\바탕 화면\업무서류\ilshinERP__260415\partnererp.pbl"

res = orca.PBORCA_LibraryDirectory(
    h_session,
    pbl_path.encode('cp949'),
    b"",
    0,
    cb_func,
    None
)

print("LibraryDirectory Result Code: {}".format(res))
print("Total Entries Found in partnererp.pbl: {}".format(len(entries)))
for e in entries[:10]:
    print(" ", e)

orca.PBORCA_SessionClose(h_session)
