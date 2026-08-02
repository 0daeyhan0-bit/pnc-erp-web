import ctypes
import os

pborca_dll = r"C:\Program Files (x86)\Sybase\Shared\PowerBuilder\pborc105.dll"
orca = ctypes.WinDLL(pborca_dll)

class PBORCA_ENTRYINFO(ctypes.Structure):
    _fields_ = [
        ("lpszEntryName", ctypes.c_wchar * 256),
        ("lpszComments", ctypes.c_wchar * 256),
        ("lEntrySize", ctypes.c_int32),
        ("otEntryType", ctypes.c_int32),
        ("lCreateTime", ctypes.c_int32)
    ]

DIRPROC = ctypes.WINFUNCTYPE(None, ctypes.POINTER(PBORCA_ENTRYINFO), ctypes.c_void_p)

entries = []

def dir_callback(p_entry_info, p_user_data):
    entry = p_entry_info.contents
    raw_name = entry.lpszEntryName
    clean_name = raw_name.split('\x00')[0]
    etype = entry.otEntryType
    entries.append((clean_name, etype))

cb_func = DIRPROC(dir_callback)

orca.PBORCA_SessionOpen.restype = ctypes.c_void_p
orca.PBORCA_SessionOpen.argtypes = []

orca.PBORCA_SessionClose.restype = None
orca.PBORCA_SessionClose.argtypes = [ctypes.c_void_p]

orca.PBORCA_SessionSetLibraryList.restype = ctypes.c_int
orca.PBORCA_SessionSetLibraryList.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_wchar_p),
    ctypes.c_int
]

orca.PBORCA_LibraryDirectory.restype = ctypes.c_int
orca.PBORCA_LibraryDirectory.argtypes = [
    ctypes.c_void_p,
    ctypes.c_wchar_p,
    ctypes.c_wchar_p,
    ctypes.c_int,
    DIRPROC,
    ctypes.c_void_p
]

orca.PBORCA_LibraryEntryExport.restype = ctypes.c_int
orca.PBORCA_LibraryEntryExport.argtypes = [
    ctypes.c_void_p,
    ctypes.c_wchar_p,
    ctypes.c_wchar_p,
    ctypes.c_int,
    ctypes.c_wchar_p,
    ctypes.c_int
]

h_session = orca.PBORCA_SessionOpen()
pbl_path = r"C:\Users\hdy56\OneDrive\바탕 화면\업무서류\ilshinERP__260415\cm_com.pbl"

lib_arr = (ctypes.c_wchar_p * 1)(pbl_path)
orca.PBORCA_SessionSetLibraryList(h_session, lib_arr, 1)

orca.PBORCA_LibraryDirectory(
    h_session,
    pbl_path,
    "",
    0,
    cb_func,
    None
)

print("Clean Entries (First 10):")
for name, etype in entries[:10]:
    buf_len = 5 * 1024 * 1024
    buf = ctypes.create_unicode_buffer(buf_len)
    res = orca.PBORCA_LibraryEntryExport(
        h_session,
        pbl_path,
        name,
        etype,
        buf,
        buf_len
    )
    print("  Name: '{}', Type: {}, Export Code: {}".format(name, etype, res))
    if res == 0:
        print("   Sample Content:", repr(buf.value[:100]))

orca.PBORCA_SessionClose(h_session)
