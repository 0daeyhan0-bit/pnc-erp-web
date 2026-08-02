import re
import os

def extract_pbl_sources(pbl_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with open(pbl_path, "rb") as f:
        content = f.read()
    
    # Search for $PBExportHeader$ pattern in UTF-16LE bytes and ASCII bytes
    # ASCII: b'$PBExportHeader$'
    # UTF-16LE: b'$\x00P\x00B\x00E\x00x\x00p\x00o\x00r\x00t\x00H\x00e\x00a\x00d\x00e\x00r\x00$\x00'
    
    ascii_pattern = re.compile(rb'\$PBExportHeader\$([^\r\n]+)')
    utf16_pattern = re.compile(rb'\$\x00P\x00B\x00E\x00x\x00p\x00o\x00r\x00t\x00H\x00e\x00a\x00d\x00e\x00r\x00\$\x00([^\r\n\x00]+\x00)+')
    
    ascii_matches = [(m.start(), m.group(1).decode('ascii', errors='ignore').strip(), 'ascii') for m in ascii_pattern.finditer(content)]
    utf16_matches = [(m.start(), m.group(0).decode('utf-16-le', errors='ignore').replace('$PBExportHeader$', '').strip(), 'utf16') for m in utf16_pattern.finditer(content)]
    
    all_matches = sorted(ascii_matches + utf16_matches, key=lambda x: x[0])
    
    print("PBL: {} | Total Objects Found: {}".format(os.path.basename(pbl_path), len(all_matches)))
    
    exported_count = 0
    for i, (start_idx, file_name_info, enc_type) in enumerate(all_matches):
        if i + 1 < len(all_matches):
            end_idx = all_matches[i + 1][0]
        else:
            end_idx = len(content)
            
        chunk = content[start_idx:end_idx]
        
        if enc_type == 'utf16':
            try:
                text = chunk.decode('utf-16-le', errors='ignore')
            except Exception:
                text = chunk.decode('cp949', errors='ignore')
        else:
            try:
                text = chunk.decode('cp949', errors='ignore')
            except Exception:
                text = chunk.decode('utf-16-le', errors='ignore')
                
        lines = text.splitlines()
        clean_lines = []
        for line in lines:
            if not line:
                clean_lines.append("")
                continue
            printable_ratio = sum(1 for c in line if c.isprintable() or c in '\t\r\n') / (len(line) + 1e-5)
            if printable_ratio < 0.5 and len(line) > 15:
                break
            clean_lines.append(line)
            
        clean_text = "\n".join(clean_lines)
        
        if clean_text:
            out_file_name = file_name_info
            if not out_file_name or "." not in out_file_name:
                out_file_name = "object_{}.src".format(i+1)
                
            safe_file_name = "".join([c if c.isalnum() or c in "._- " else "_" for c in out_file_name])
            out_path = os.path.join(out_dir, safe_file_name)
            
            with open(out_path, "w", encoding="utf-8") as out_f:
                out_f.write(clean_text)
            exported_count += 1
            
    return exported_count

pbl_file = r"C:\Users\hdy56\OneDrive\바탕 화면\업무서류\ilshinERP__260415\cm_com.pbl"
out = r"c:\Users\hdy56\OneDrive\바탕 화면\파워빌드분석\src_extracted\cm_com"
count = extract_pbl_sources(pbl_file, out)
print("Successfully extracted {} objects to {}".format(count, out))
