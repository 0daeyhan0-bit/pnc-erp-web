import ctypes
import os
import glob

pborca_dll = r"C:\Program Files (x86)\Sybase\Shared\PowerBuilder\pborc105.dll"
orca = ctypes.WinDLL(pborca_dll)

DIRPROC = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)

entries = []
def dir_callback(p_entry_info, p_user_data):
    try:
        raw_bytes = ctypes.string_at(p_entry_info, 1024)
        name = raw_bytes[784:1024].decode('utf-16-le', errors='ignore').split('\x00')[0].strip()
        if name:
            entries.append(name)
    except Exception:
        pass

cb_func = DIRPROC(dir_callback)

src_dir = r"C:\Users\hdy56\OneDrive\바탕 화면\업무서류\ilshinERP__260415"
pbl_files = sorted(glob.glob(os.path.join(src_dir, "*.pbl")))

for pbl in pbl_files:
    h_session = orca.PBORCA_SessionOpen()
    lib_arr = (ctypes.c_wchar_p * 1)(pbl)
    orca.PBORCA_SessionSetLibraryList(h_session, lib_arr, 1)
    
    entries = []
    orca.PBORCA_LibraryDirectory(h_session, pbl, "", 0, cb_func, None)
    
    sim = [e for e in entries if "w_pr_master" in e or "w_pr_" in e or "w_master" in e]
    if sim:
        print("PBL:", os.path.basename(pbl), "Matches:", sim[:10])
        
    orca.PBORCA_SessionClose(h_session)
