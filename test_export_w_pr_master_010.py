import ctypes
import os

pborca_dll = r"C:\Program Files (x86)\Sybase\Shared\PowerBuilder\pborc105.dll"
orca = ctypes.WinDLL(pborca_dll)

DIRPROC = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)

entries = []
def dir_callback(p_entry_info, p_user_data):
    try:
        raw_bytes = ctypes.string_at(p_entry_info, 1024)
        for off in range(0, 1000, 2):
            wstr = raw_bytes[off:off+300].decode('utf-16-le', errors='ignore').split('\x00')[0]
            if wstr == "w_pr_master_010" or "w_pr_master" in wstr:
                if wstr not in entries:
                    entries.append(wstr)
    except Exception:
        pass

cb_func = DIRPROC(dir_callback)

h_session = orca.PBORCA_SessionOpen()
pbl_path = r"C:\Users\hdy56\OneDrive\바탕 화면\업무서류\ilshinERP__260415\pr_master_01.pbl"

lib_arr = (ctypes.c_wchar_p * 1)(pbl_path)
orca.PBORCA_SessionSetLibraryList(h_session, lib_arr, 1)

orca.PBORCA_LibraryDirectory(h_session, pbl_path, "", 0, cb_func, None)

target_name = "w_pr_master_010"
out_dir = r"c:\Users\hdy56\OneDrive\바탕 화면\파워빌드분석\src_extracted\pr_master_01"
os.makedirs(out_dir, exist_ok=True)

for etype in range(11):
    buf_len = 10 * 1024 * 1024
    buf = ctypes.create_unicode_buffer(buf_len)
    res = orca.PBORCA_LibraryEntryExport(h_session, pbl_path, target_name, etype, buf, buf_len)
    if res == 0:
        out_file = os.path.join(out_dir, "w_pr_master_010.srw")
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(buf.value)
        print("SUCCESS! Exported w_pr_master_010.srw to:", out_file)
        break

orca.PBORCA_SessionClose(h_session)
