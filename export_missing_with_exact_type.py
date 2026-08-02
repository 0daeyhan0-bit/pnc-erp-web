import ctypes
import os
import glob
import time
import re
import struct

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

def export_missing_exact_type(pbl_path, all_pbls, base_out_dir):
    pbl_name = os.path.basename(pbl_path)
    lib_no_ext = os.path.splitext(pbl_name)[0]
    out_dir = os.path.join(base_out_dir, lib_no_ext)
    os.makedirs(out_dir, exist_ok=True)

    existing_files = set([os.path.splitext(f)[0] for f in os.listdir(out_dir)])

    # Store tuples of (entry_name, entry_type)
    entries = []

    def dir_cb(p_info, p_user):
        try:
            raw = ctypes.string_at(p_info, 1024)
            # Entry type is at offset 0 (integer / short / byte)
            entry_type = struct.unpack('<h', raw[0:2])[0]
            name = raw[784:1024].decode('utf-16-le', errors='ignore').split('\x00')[0].strip()
            if name and re.match(r'^[a-zA-Z0-9_가-힣]+$', name):
                entries.append((name, entry_type))
        except: pass

    cb = DIRPROC(dir_cb)

    h_session = orca.PBORCA_SessionOpen()
    if not h_session:
        return 0, 0, 0, 0

    lib_arr_type = ctypes.c_wchar_p * len(all_pbls)
    lib_arr = lib_arr_type(*all_pbls)
    orca.PBORCA_SessionSetLibraryList(h_session, lib_arr, len(all_pbls))

    orca.PBORCA_LibraryDirectory(h_session, pbl_path, "", 0, cb, None)

    # Unique entries
    dict_entries = {}
    for n, t in entries:
        if n not in dict_entries:
            dict_entries[n] = t

    missing = [n for n in dict_entries if n not in existing_files]

    newly_added = 0
    for m_name in missing:
        e_type = dict_entries[m_name]
        # Try exact type first, if fails try all types
        types_to_try = [e_type] + [t for t in range(11) if t != e_type]
        for etype in types_to_try:
            buf = ctypes.create_unicode_buffer(10 * 1024 * 1024)
            res = orca.PBORCA_LibraryEntryExport(h_session, pbl_path, m_name, etype, buf, 10 * 1024 * 1024)
            if res == 0:
                ext = TYPE_EXT_MAP.get(etype, "srx")
                safe_name = "".join([c if c.isalnum() or c in "._- " else "_" for c in m_name])
                with open(os.path.join(out_dir, safe_name + "." + ext), "w", encoding="utf-8") as f:
                    f.write(buf.value)
                newly_added += 1
                break

    orca.PBORCA_SessionClose(h_session)
    final_cnt = len(os.listdir(out_dir))
    return len(dict_entries), len(missing), newly_added, final_cnt

def main():
    src_dir = r"C:\Users\hdy56\OneDrive\바탕 화면\업무서류\ilshinERP__260415"
    base_out_dir = r"c:\Users\hdy56\OneDrive\바탕 화면\파워빌드분석\src_extracted"
    pbl_files = sorted(glob.glob(os.path.join(src_dir, "*.pbl")))

    print("=== EXACT TYPE MISSING EXTRACTION STARTED ===")

    tot_orig = 0
    tot_miss = 0
    tot_added = 0
    tot_final = 0

    for i, pbl in enumerate(pbl_files, start=1):
        orig, miss, added, final = export_missing_exact_type(pbl, pbl_files, base_out_dir)
        tot_orig += orig
        tot_miss += miss
        tot_added += added
        tot_final += final
        print("[{}/{}] {} -> Orig: {} | Final: {} | Missing: {} | Added: {}".format(
            i, len(pbl_files), os.path.basename(pbl), orig, final, miss, added
        ))

    print("\nEXACT TYPE EXTRACTION COMPLETE REPORT")
    print("Total PBLs: {}, Total Orig: {}, Total Final: {}, Total Added: {}".format(
        len(pbl_files), tot_orig, tot_final, tot_added
    ))

if __name__ == "__main__":
    main()
