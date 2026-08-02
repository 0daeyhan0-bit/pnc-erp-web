import ctypes

pborca_dll = r"C:\Program Files (x86)\Sybase\Shared\PowerBuilder\pborc105.dll"
orca = ctypes.WinDLL(pborca_dll)

DIRPROC = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)

offsets_found = []

def dir_callback(p_entry_info, p_user_data):
    raw_bytes = ctypes.string_at(p_entry_info, 2048)
    # Search for wchar strings in raw_bytes
    # Let's decode wchar_t every 2 bytes
    for offset in range(0, 1500, 2):
        try:
            wstr = raw_bytes[offset:offset+200].decode('utf-16-le', errors='ignore').split('\x00')[0]
            if wstr.startswith('w_') or wstr.startswith('d_') or wstr.startswith('u_') or wstr.startswith('m_') or wstr.startswith('f_'):
                offsets_found.append((offset, wstr))
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

out_file = r"c:\Users\hdy56\OneDrive\바탕 화면\파워빌드분석\offsets_found.txt"
with open(out_file, "w", encoding="utf-8") as f:
    for off, wstr in offsets_found[:30]:
        f.write("Offset {}: {}\n".format(off, wstr))

print("Found {} offsets with valid PB object names.".format(len(offsets_found)))
orca.PBORCA_SessionClose(h_session)
