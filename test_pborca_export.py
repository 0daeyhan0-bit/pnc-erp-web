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
pbl_path = r"C:\Users\hdy56\OneDrive\바탕 화면\업무서류\ilshinERP__260415\partnererp.pbl"

# Set Library List
pbl_bytes = pbl_path.encode('cp949')
lib_arr = (ctypes.c_char_p * 1)(pbl_bytes)
res_lib = orca.PBORCA_SessionSetLibraryList(h_session, lib_arr, 1)
print("SessionSetLibraryList Result: {}".format(res_lib))

res_dir = orca.PBORCA_LibraryDirectory(
    h_session,
    pbl_bytes,
    b"",
    0,
    cb_func,
    None
)
print("LibraryDirectory Result Code: {}".format(res_dir))
print("Total Entries Found in partnererp.pbl: {}".format(len(entries)))
for e in entries[:10]:
    print(" ", e)

if entries:
    name, etype, esize = entries[0]
    name_bytes = name.encode('cp949')
    # Export test
    buf_len = 1024 * 1024
    buf = ctypes.create_string_buffer(buf_len)
    res_exp = orca.PBORCA_LibraryEntryExport(
        h_session,
        pbl_bytes,
        name_bytes,
        etype,
        buf,
        buf_len
    )
    print("Export Result Code for {}: {}".format(name, res_exp))
    if res_exp == 0:
        print("Sample Export Content:")
        print(buf.value[:300].decode('cp949', errors='ignore'))

orca.PBORCA_SessionClose(h_session)
