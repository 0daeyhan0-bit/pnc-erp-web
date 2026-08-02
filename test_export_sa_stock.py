import ctypes
import os

pborca_dll = r"C:\Program Files (x86)\Sybase\Shared\PowerBuilder\pborc105.dll"
orca = ctypes.WinDLL(pborca_dll)

DIRPROC = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)

entries = []

def dir_callback(p_entry_info, p_user_data):
    raw_bytes = ctypes.string_at(p_entry_info, 1024)
    entry_name = raw_bytes[784:1024].decode('utf-16-le', errors='ignore').split('\x00')[0]
    comment = raw_bytes[0:512].decode('utf-16-le', errors='ignore').split('\x00')[0]
    if entry_name:
        entries.append((entry_name, comment))

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

src_dir = r"C:\Users\hdy56\OneDrive\바탕 화면\업무서류\ilshinERP__260415"
import glob
pbl_files = glob.glob(os.path.join(src_dir, "*.pbl"))

# Pass ALL PBLs in library list
lib_arr = (ctypes.c_wchar_p * len(pbl_files))(*pbl_files)
res_set = orca.PBORCA_SessionSetLibraryList(h_session, lib_arr, len(pbl_files))
print("SessionSetLibraryList Result:", res_set)

target_pbl = r"C:\Users\hdy56\OneDrive\바탕 화면\업무서류\ilshinERP__260415\sa_stock_01.pbl"

res_dir = orca.PBORCA_LibraryDirectory(
    h_session,
    target_pbl,
    "",
    0,
    cb_func,
    None
)
print("LibraryDirectory Result:", res_dir, "Found entries:", len(entries))

for name, comment in entries[:10]:
    success = False
    for etype in range(11):
        buf_len = 10 * 1024 * 1024
        buf = ctypes.create_unicode_buffer(buf_len)
        res_exp = orca.PBORCA_LibraryEntryExport(
            h_session,
            target_pbl,
            name,
            etype,
            buf,
            buf_len
        )
        if res_exp == 0:
            print(" [SUCCESS] Exported:", name, "etype:", etype)
            success = True
            break
    if not success:
        print(" [FAIL] Could not export:", name)

orca.PBORCA_SessionClose(h_session)
