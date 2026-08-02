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

orca.PBORCA_SessionSetLibraryList.restype = ctypes.c_int
orca.PBORCA_SessionSetLibraryList.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_char_p),
    ctypes.c_int
]

orca.PBORCA_SessionSetCurrentApplication.restype = ctypes.c_int
orca.PBORCA_SessionSetCurrentApplication.argtypes = [
    ctypes.c_void_p,
    ctypes.c_char_p,
    ctypes.c_char_p
]

orca.PBORCA_LibraryDirectory.restype = ctypes.c_int
orca.PBORCA_LibraryDirectory.argtypes = [
    ctypes.c_void_p,
    ctypes.c_char_p,
    ctypes.c_char_p,
    ctypes.c_int,
    DIRPROC,
    ctypes.c_void_p
]

orca.PBORCA_LibraryEntryExport.restype = ctypes.c_int
orca.PBORCA_LibraryEntryExport.argtypes = [
    ctypes.c_void_p,
    ctypes.c_char_p,
    ctypes.c_char_p,
    ctypes.c_int,
    ctypes.c_char_p,
    ctypes.c_int
]

h_session = orca.PBORCA_SessionOpen()
pbl_path = r"C:\Users\hdy56\OneDrive\바탕 화면\업무서류\ilshinERP__260415\cm_com.pbl"

pbl_b = pbl_path.encode('cp949')
lib_arr = (ctypes.c_char_p * 1)(pbl_b)
r1 = orca.PBORCA_SessionSetLibraryList(h_session, lib_arr, 1)
print("SetLibraryList:", r1)

r2 = orca.PBORCA_SessionSetCurrentApplication(h_session, pbl_b, b"partnererp")
print("SetCurrentApplication:", r2)

r3 = orca.PBORCA_LibraryDirectory(h_session, pbl_b, b"", 0, cb_func, None)
print("LibraryDirectory:", r3)
print("Entries count:", len(entries))
for e in entries[:5]:
    print(" ", e)

if entries:
    name, etype, esize = entries[0]
    name_b = name.encode('cp949')
    buf_len = 2 * 1024 * 1024
    buf = ctypes.create_string_buffer(buf_len)
    r4 = orca.PBORCA_LibraryEntryExport(h_session, pbl_b, name_b, etype, buf, buf_len)
    print("Export code for {}: {}".format(name, r4))
    if r4 == 0:
        print("Export content start:")
        print(buf.value[:200].decode('cp949', errors='ignore'))

orca.PBORCA_SessionClose(h_session)
