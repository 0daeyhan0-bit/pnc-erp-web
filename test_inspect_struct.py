import ctypes

pborca_dll = r"C:\Program Files (x86)\Sybase\Shared\PowerBuilder\pborc105.dll"
orca = ctypes.WinDLL(pborca_dll)

DIRPROC = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)

def dir_callback(p_entry_info, p_user_data):
    raw_bytes = ctypes.string_at(p_entry_info, 1024)
    # Print first entry's text & fields
    print("Raw bytes len:", len(raw_bytes))
    # Try decoding unicode strings in raw_bytes
    # Let's search for wchar strings
    wstrs = []
    curr = []
    for i in range(0, len(raw_bytes)-1, 2):
        char_val = raw_bytes[i] + raw_bytes[i+1]*256
        if char_val != 0 and char_val < 65535:
            curr.append(chr(char_val))
        else:
            if len(curr) >= 3:
                wstrs.append("".join(curr))
            curr = []
    print("Found wchar strings:", wstrs[:5])
    # Print integers in the structure
    ints = [struct_val[0] for struct_val in [ctypes.struct.unpack_from("<i", raw_bytes, offset) for offset in range(0, 1024, 4)]]
    print("Ints at offsets:", list(enumerate(ints[:20])))

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

orca.PBORCA_SessionClose(h_session)
