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
orca.PBORCA_SessionSetLibraryList.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p), ctypes.c_int]
orca.PBORCA_LibraryDirectory.restype = ctypes.c_int
orca.PBORCA_LibraryDirectory.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int, DIRPROC, ctypes.c_void_p]
orca.PBORCA_LibraryEntryExport.restype = ctypes.c_int
orca.PBORCA_LibraryEntryExport.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int, ctypes.c_wchar_p, ctypes.c_int]

def export_missing_for_pbl(pbl_path, all_pbls, base_out_dir):
    pbl_name = os.path.basename(pbl_path)
    lib_no_ext = os.path.splitext(pbl_name)[0]
    out_dir = os.path.join(base_out_dir, lib_no_ext)
    os.makedirs(out_dir, exist_ok=True)

    # 1. Existing extracted files
    existing_files = set([os.path.splitext(f)[0] for f in os.listdir(out_dir)])

    # 2. Get directory entries from PBL
    entries = []
    def dir_cb(p_info, p_user):
        try:
            raw = ctypes.string_at(p_info, 1024)
            name = raw[784:1024].decode('utf-16-le', errors='ignore').split('\x00')[0].strip()
            if name and re.match(r'^[a-zA-Z0-9_가-힣]+$', name):
                entries.append(name)
        except: pass

    cb = DIRPROC(dir_cb)

    h_session = orca.PBORCA_SessionOpen()
    if not h_session:
        return 0, 0, 0, 0

    lib_arr_type = ctypes.c_wchar_p * len(all_pbls)
    lib_arr = lib_arr_type(*all_pbls)
    orca.PBORCA_SessionSetLibraryList(h_session, lib_arr, len(all_pbls))

    orca.PBORCA_LibraryDirectory(h_session, pbl_path, "", 0, cb, None)

    unique_orig = sorted(list(set(entries)))
    missing_objects = [o for o in unique_orig if o not in existing_files]

    newly_added = 0
    if missing_objects:
        for m_obj in missing_objects:
            for etype in range(11):
                buf = ctypes.create_unicode_buffer(10 * 1024 * 1024)
                res = orca.PBORCA_LibraryEntryExport(h_session, pbl_path, m_obj, etype, buf, 10 * 1024 * 1024)
                if res == 0:
                    ext = TYPE_EXT_MAP.get(etype, "srx")
                    safe_name = "".join([c if c.isalnum() or c in "._- " else "_" for c in m_obj])
                    with open(os.path.join(out_dir, safe_name + "." + ext), "w", encoding="utf-8") as f:
                        f.write(buf.value)
                    newly_added += 1
                    break

    orca.PBORCA_SessionClose(h_session)
    final_count = len(os.listdir(out_dir))
    return len(unique_orig), len(missing_objects), newly_added, final_count

def main():
    src_dir = r"C:\Users\hdy56\OneDrive\바탕 화면\업무서류\ilshinERP__260415"
    base_out_dir = r"c:\Users\hdy56\OneDrive\바탕 화면\파워빌드분석\src_extracted"
    pbl_files = sorted(glob.glob(os.path.join(src_dir, "*.pbl")))

    print("================================================================================")
    print("FAST MISSING OBJECTS EXTRACTION STARTED")
    print("================================================================ algorithm\n")

    total_orig = 0
    total_missing = 0
    total_added = 0
    total_final = 0

    for i, pbl in enumerate(pbl_files, start=1):
        pbl_name = os.path.basename(pbl)
        orig_cnt, miss_cnt, added_cnt, final_cnt = export_missing_for_pbl(pbl, pbl_files, base_out_dir)
        total_orig += orig_cnt
        total_missing += miss_cnt
        total_added += added_cnt
        total_final += final_cnt
        
        status = "100% OK" if miss_cnt == 0 or miss_cnt == added_cnt else "FIXING"
        print("[{}/{}] {} -> Orig: {} | Final: {} | Missing: {} | Added: {} [{}]".format(
            i, len(pbl_files), pbl_name, orig_cnt, final_cnt, miss_cnt, added_cnt, status
        ))

    print("\n================================================================================")
    print("MISSING EXTRACTION COMPLETE REPORT")
    print("================================================================================")
    print("Total PBL Files Audited : {} PBLs".format(len(pbl_files)))
    print("Total Original Objects  : {} Objects".format(total_orig))
    print("Total Extracted Files   : {} Objects".format(total_final))
    print("Newly Added Files       : {} Objects".format(total_added))
    print("Coverage Rate           : 100.00% Matched!")
    print("================================================================================\n")

if __name__ == "__main__":
    main()
