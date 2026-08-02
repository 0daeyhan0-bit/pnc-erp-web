import ctypes
import os
import glob
import time
import re

pborca_dll = r"C:\Program Files (x86)\Sybase\Shared\PowerBuilder\pborc105.dll"
orca = ctypes.WinDLL(pborca_dll)

DIRPROC = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)

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

def export_pbl_isolated(pbl_path, base_out_dir):
    pbl_name = os.path.basename(pbl_path)
    lib_name_no_ext = os.path.splitext(pbl_name)[0]
    out_dir = os.path.join(base_out_dir, lib_name_no_ext)
    os.makedirs(out_dir, exist_ok=True)

    entries = []

    def dir_callback(p_entry_info, p_user_data):
        try:
            raw_bytes = ctypes.string_at(p_entry_info, 1024)
            entry_name = ""
            for off in range(0, 1000, 2):
                wstr = raw_bytes[off:off+300].decode('utf-16-le', errors='ignore').split('\x00')[0]
                if wstr and not wstr.startswith((' ', '\t', '\r', '\n')) and len(wstr) > 1:
                    if wstr.startswith(('w_', 'dw_', 'u_', 'm_', 'f_', 'd_', 'p_', 'cs_', 'pr_', 'sa_', 'pu_', 'hr_', 'ma_', 'qa_', 'cm_', 'app_', 'partnererp', 'ds_', 'tt_', 'mc_')):
                        entry_name = wstr
                        break
            if not entry_name:
                entry_name = raw_bytes[784:1024].decode('utf-16-le', errors='ignore').split('\x00')[0]
                
            if entry_name and re.match(r'^[a-zA-Z0-9_가-힣]+$', entry_name):
                entries.append(entry_name)
        except Exception:
            pass

    cb_func = DIRPROC(dir_callback)

    h_session = orca.PBORCA_SessionOpen()
    if not h_session:
        return 0, 0

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

    success_count = 0
    exported_names = set()

    for name in entries:
        if not name or name in exported_names:
            continue
            
        for etype in range(11):
            buf_len = 10 * 1024 * 1024
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
                safe_name = "".join([c if c.isalnum() or c in "._- " else "_" for c in name])
                out_file = os.path.join(out_dir, "{}.{}".format(safe_name, ext))
                with open(out_file, "w", encoding="utf-8") as f:
                    f.write(buf.value)
                success_count += 1
                exported_names.add(name)
                break

    orca.PBORCA_SessionClose(h_session)
    return success_count, len(entries)

def main():
    src_dir = r"C:\Users\hdy56\OneDrive\바탕 화면\업무서류\ilshinERP__260415"
    base_out_dir = r"c:\Users\hdy56\OneDrive\바탕 화면\파워빌드분석\src_extracted"
    
    pbl_files = glob.glob(os.path.join(src_dir, "*.pbl"))
    print("Found {} PBL files in {}".format(len(pbl_files), src_dir))
    
    start_time = time.time()
    total_objects = 0

    for i, pbl_path in enumerate(sorted(pbl_files)):
        pbl_name = os.path.basename(pbl_path)
        try:
            succ, total = export_pbl_isolated(pbl_path, base_out_dir)
            total_objects += succ
            print("[{}/{}] {} -> Found: {}, Exported: {}".format(i+1, len(pbl_files), pbl_name, total, succ))
        except Exception as e:
            print("[{}/{}] ERROR exporting {}: {}".format(i+1, len(pbl_files), pbl_name, str(e)))

    elapsed = time.time() - start_time
    print("\n==========================================")
    print("FAST 100% ALL PBL EXPORT COMPLETED!")
    print("Total PBLs Processed: {}".format(len(pbl_files)))
    print("Total Objects Exported: {}".format(total_objects))
    print("Elapsed Time: {:.2f}s".format(elapsed))
    print("==========================================")

if __name__ == "__main__":
    main()
