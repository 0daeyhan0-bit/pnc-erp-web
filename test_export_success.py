import ctypes
import os

pborca_dll = r"C:\Program Files (x86)\Sybase\Shared\PowerBuilder\pborc105.dll"
orca = ctypes.WinDLL(pborca_dll)

DIRPROC = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)

entries = []

# Map entry types to extensions
TYPE_EXT_MAP = {
    0: "sra",
    1: "srd",
    2: "srf",
    3: "srm",
    4: "srq",
    5: "srs",
    6: "sru",
    7: "srw",
    8: "srp",
    9: "srj",
    10: "srp"
}

def dir_callback(p_entry_info, p_user_data):
    raw_bytes = ctypes.string_at(p_entry_info, 1500)
    # Entry Name is at offset 784 (wchar_t)
    entry_name = raw_bytes[784:1300].decode('utf-16-le', errors='ignore').split('\x00')[0]
    comment = raw_bytes[0:512].decode('utf-16-le', errors='ignore').split('\x00')[0]
    
    # Let's inspect otEntryType (usually int32 at offset 512 or 516 or 520)
    # Try all types 0 to 10 in LibraryEntryExport
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

out_dir = r"c:\Users\hdy56\OneDrive\바탕 화면\파워빌드분석\src_extracted\cm_com"
os.makedirs(out_dir, exist_ok=True)

success_count = 0
for name, comment in entries:
    if not name:
        continue
    # Test entry types 0 to 10 to export
    exported = False
    for etype in range(11):
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
        if res == 0:
            ext = TYPE_EXT_MAP.get(etype, "srx")
            out_file = os.path.join(out_dir, "{}.{}".format(name, ext))
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(buf.value)
            success_count += 1
            exported = True
            print(" [SUCCESS] Exported {} (Type: {}, Ext: .{})".format(name, etype, ext))
            break
            
print("Export Completed! Total Succeeded: {}/{}".format(success_count, len(entries)))
orca.PBORCA_SessionClose(h_session)
