import os
import glob
import ctypes

pborca_dll = r"C:\Program Files (x86)\Sybase\Shared\PowerBuilder\pborc105.dll"
orca = ctypes.WinDLL(pborca_dll)

DIRPROC = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)

TYPE_EXT_MAP = {0: "sra", 1: "srd", 2: "srf", 3: "srm", 4: "srq", 5: "srs", 6: "sru", 7: "srw", 8: "srp", 9: "srj", 10: "srp"}

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

src_dir = r"C:\Users\hdy56\OneDrive\바탕 화면\업무서류\ilshinERP__260415"
base_out_dir = r"c:\Users\hdy56\OneDrive\바탕 화면\파워빌드분석\src_extracted"
pbl_files = sorted(glob.glob(os.path.join(src_dir, "*.pbl")))

print("=== STARTING 100% FAST AUDIT ===")

h_session = orca.PBORCA_SessionOpen()
lib_arr = (ctypes.c_wchar_p * len(pbl_files))(*pbl_files)
orca.PBORCA_SessionSetLibraryList(h_session, lib_arr, len(pbl_files))

total_orig_objs = 0
total_extracted_objs = 0
fixed_objs = 0

for i, pbl in enumerate(pbl_files, start=1):
    pbl_name = os.path.basename(pbl)
    lib_no_ext = os.path.splitext(pbl_name)[0]
    out_dir = os.path.join(base_out_dir, lib_no_ext)
    os.makedirs(out_dir, exist_ok=True)
    
    entries = []
    def dir_cb(p_info, p_user):
        try:
            raw = ctypes.string_at(p_info, 1024)
            name = raw[784:1024].decode('utf-16-le', errors='ignore').split('\x00')[0].strip()
            if name: entries.append(name)
        except: pass
    cb = DIRPROC(dir_cb)
    
    orca.PBORCA_LibraryDirectory(h_session, pbl, "", 0, cb, None)
    unique_orig = sorted(list(set(entries)))
    
    extracted_names = set([os.path.splitext(f)[0] for f in os.listdir(out_dir)])
    missing = [o for o in unique_orig if o not in extracted_names]
    
    added = 0
    for m_obj in missing:
        for etype in range(11):
            buf = ctypes.create_unicode_buffer(10 * 1024 * 1024)
            if orca.PBORCA_LibraryEntryExport(h_session, pbl, m_obj, etype, buf, 10 * 1024 * 1024) == 0:
                ext = TYPE_EXT_MAP.get(etype, "srx")
                with open(os.path.join(out_dir, m_obj + "." + ext), "w", encoding="utf-8") as f:
                    f.write(buf.value)
                added += 1
                break
                
    curr_cnt = len(os.listdir(out_dir))
    total_orig_objs += len(unique_orig)
    total_extracted_objs += curr_cnt
    fixed_objs += added
    print("[{}/{}] {} -> Orig: {} | Extracted: {} | Fixed: {}".format(i, len(pbl_files), pbl_name, len(unique_orig), curr_cnt, added))

orca.PBORCA_SessionClose(h_session)
print("\nAUDIT COMPLETED!")
print("Total Original Objects: {}, Total Extracted Files: {}, Total Newly Fixed: {}".format(total_orig_objs, total_extracted_objs, fixed_objs))
