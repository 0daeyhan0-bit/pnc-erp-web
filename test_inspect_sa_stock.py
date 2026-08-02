import ctypes
import os

pborca_dll = r"C:\Program Files (x86)\Sybase\Shared\PowerBuilder\pborc105.dll"
orca = ctypes.WinDLL(pborca_dll)

DIRPROC = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)

entries = []

def dir_callback(p_entry_info, p_user_data):
    try:
        raw_bytes = ctypes.string_at(p_entry_info, 1024)
        # Find wchar string starting with w_ or dw_ or u_ or m_ or f_
        for off in range(0, 1000, 2):
            wstr = raw_bytes[off:off+300].decode('utf-16-le', errors='ignore').split('\x00')[0]
            if wstr.startswith(('w_', 'dw_', 'u_', 'm_', 'f_', 'd_')):
                # also find otEntryType int32 at offset 512, 516, 520, etc
                # let's try etype from offset 516
                etype = ctypes.c_int32.from_buffer_copy(raw_bytes[516:520]).value
                entries.append((wstr, etype))
                break
    except Exception:
        pass

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

lib_arr = (ctypes.c_wchar_p * len(pbl_files))(*pbl_files)
orca.PBORCA_SessionSetLibraryList(h_session, lib_arr, len(pbl_files))

target_pbl = r"C:\Users\hdy56\OneDrive\바탕 화면\업무서류\ilshinERP__260415\sa_stock_01.pbl"

orca.PBORCA_LibraryDirectory(
    h_session,
    target_pbl,
    "",
    0,
    cb_func,
    None
)

print("Found valid object names:", len(entries))

success_count = 0
for name, etype in entries:
    for t in range(11):
        buf_len = 10 * 1024 * 1024
        buf = ctypes.create_unicode_buffer(buf_len)
        res = orca.PBORCA_LibraryEntryExport(
            h_session,
            target_pbl,
            name,
            t,
            buf,
            buf_len
        )
        if res == 0:
            success_count += 1
            print(" [SUCCESS] Exported:", name, "type:", t)
            break

print("Total Exported from sa_stock_01.pbl:", success_count)
orca.PBORCA_SessionClose(h_session)
