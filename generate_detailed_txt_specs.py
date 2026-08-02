import os
import glob
import re

base_extracted_dir = r"c:\Users\hdy56\OneDrive\바탕 화면\파워빌드분석\src_extracted"
txt_output_dir = r"c:\Users\hdy56\OneDrive\바탕 화면\파워빌드분석\source_analysis_txt"

os.makedirs(txt_output_dir, exist_ok=True)

def parse_srw_file(filepath):
    """Parse PowerBuilder Window (.srw) file for events, controls, variables, and comments."""
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    lines = content.splitlines()
    title = ""
    events = []
    controls = []
    variables = []
    
    current_event = None
    event_body = []

    for line in lines:
        lstr = line.strip()
        
        # Check Title
        if "string title =" in lstr.lower() and not title:
            title = lstr.split("=")[1].strip().strip('"')
            
        # Check controls
        if lstr.startswith("type ") and " within " in lstr:
            parts = lstr.split(" within ")
            ctrl_name = parts[0].replace("type ", "").strip()
            controls.append(ctrl_name)
            
        # Check Event Header
        if lstr.startswith("event ") or lstr.startswith("public function") or lstr.startswith("global function"):
            if current_event:
                events.append((current_event, "\n".join(event_body)))
                event_body = []
            current_event = lstr
        elif current_event:
            if lstr == "end event" or lstr == "end function":
                events.append((current_event, "\n".join(event_body)))
                current_event = None
                event_body = []
            else:
                event_body.append(line)

    if current_event:
        events.append((current_event, "\n".join(event_body)))

    return {
        'title': title,
        'controls': controls,
        'events': events,
        'line_count': len(lines)
    }

def parse_srd_file(filepath):
    """Parse DataWindow (.srd) file for SQL query, tables, arguments."""
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # Find SQL Select statement
    sql_match = re.search(r'retrieve=\s*"(.*?)"\s*(?:sort|arguments|processing|procedure|\))', content, re.DOTALL | re.IGNORECASE)
    sql_query = ""
    if sql_match:
        raw_sql = sql_match.group(1)
        # Clean up DataWindow escaped quotes ~"
        sql_query = raw_sql.replace('~"', '"').replace('\t', ' ').strip()
    else:
        # Fallback SQL search
        select_match = re.search(r'select\s+.*?\s+from\s+.*', content, re.DOTALL | re.IGNORECASE)
        if select_match:
            sql_query = select_match.group(0)[:1500]

    # Find Tables
    tables = set(re.findall(r'(?:from|join|update|into)\s+([a-zA-Z0-9_]+)', content, re.IGNORECASE))
    clean_tables = [t.upper() for t in tables if len(t) > 3 and t.upper() not in ('SELECT', 'WHERE', 'AND', 'OR', 'ON', 'AS', 'SET', 'VALUES')]

    # Find Arguments
    arg_match = re.search(r'arguments=\((.*?)\)', content, re.DOTALL | re.IGNORECASE)
    arguments = arg_match.group(1).strip() if arg_match else ""

    return {
        'sql_query': sql_query,
        'tables': clean_tables,
        'arguments': arguments,
        'line_count': len(content.splitlines())
    }

def generate_txt_analysis_for_module(mod_dir):
    mod_name = os.path.basename(mod_dir)
    mod_txt_path = os.path.join(txt_output_dir, "{}_소스상세분석.txt".format(mod_name))
    
    files = sorted(glob.glob(os.path.join(mod_dir, "*")))
    if not files:
        return 0, None

    lines_out = []
    lines_out.append("================================================================================")
    lines_out.append("📂 모듈 명: {}.pbl (소속 객체 수: {}개)".format(mod_name, len(files)))
    lines_out.append("================================================================================")
    lines_out.append("")

    for fpath in files:
        fname = os.path.basename(fpath)
        name_no_ext, ext = os.path.splitext(fname)
        ext = ext.lower()
        
        lines_out.append("--------------------------------------------------------------------------------")
        lines_out.append("📄 소스 파일: {} (유형: {})".format(fname, ext.upper()))
        lines_out.append("--------------------------------------------------------------------------------")

        if ext == ".srw":
            info = parse_srw_file(fpath)
            lines_out.append("[1] 화면 타이틀 / 설명 : {}".format(info['title'] if info['title'] else "(설정된 타이틀 없음)"))
            lines_out.append("[2] 포함된 UI 컨트롤 수 : {}개 ({})".format(len(info['controls']), ", ".join(info['controls'][:10])))
            lines_out.append("[3] 이벤트 및 함수 수  : {}개".format(len(info['events'])))
            lines_out.append("")
            lines_out.append("  [이벤트/함수 세부 스크립트 요약]")
            for ev_hdr, ev_body in info['events']:
                lines_out.append("   ▶ {}".format(ev_hdr))
                # Add sample lines of body
                body_lines = [bl.strip() for bl in ev_body.splitlines() if bl.strip() and not bl.strip().startswith("//")]
                if body_lines:
                    for bl in body_lines[:5]:
                        lines_out.append("      - {}".format(bl))
                    if len(body_lines) > 5:
                        lines_out.append("      ... (외 {} 줄 생략)".format(len(body_lines) - 5))
                else:
                    lines_out.append("      (선언 및 빈 이벤트)")
                lines_out.append("")

        elif ext == ".srd":
            info = parse_srd_file(fpath)
            lines_out.append("[1] DataWindow SQL 조회 테이블 : {}".format(", ".join(info['tables']) if info['tables'] else "없음/수동"))
            lines_out.append("[2] 조회 조건 파라미터 (Arguments) : {}".format(info['arguments'] if info['arguments'] else "없음"))
            lines_out.append("[3] DataWindow SQL 쿼리 문 :")
            if info['sql_query']:
                for qline in info['sql_query'].splitlines()[:20]:
                    lines_out.append("      {}".format(qline))
                if len(info['sql_query'].splitlines()) > 20:
                    lines_out.append("      ... (이하 SQL 생략)")
            else:
                lines_out.append("      (외부 프로시저 또는 수동 쿼리)")
            lines_out.append("")

        elif ext in (".sru", ".srf"):
            info = parse_srw_file(fpath)
            lines_out.append("[1] 유저오브젝트 / 글로벌 함수 설명")
            lines_out.append("[2] 포함된 메서드 및 이벤트 : {}개".format(len(info['events'])))
            for ev_hdr, ev_body in info['events']:
                lines_out.append("   ▶ {}".format(ev_hdr))
                body_lines = [bl.strip() for bl in ev_body.splitlines() if bl.strip() and not bl.strip().startswith("//")]
                for bl in body_lines[:5]:
                    lines_out.append("      - {}".format(bl))
            lines_out.append("")
        else:
            lines_out.append("[1] 기타 일반 파일 (크기: {} bytes)".format(os.path.getsize(fpath)))
            lines_out.append("")

        lines_out.append("")

    with open(mod_txt_path, "w", encoding="utf-8") as out_f:
        out_f.write("\n".join(lines_out))

    return len(files), mod_txt_path

def main():
    mod_dirs = sorted(glob.glob(os.path.join(base_extracted_dir, "*")))
    total_processed_files = 0
    created_txt_files = []

    for mdir in mod_dirs:
        if not os.path.isdir(mdir): continue
        cnt, txt_p = generate_txt_analysis_for_module(mdir)
        if cnt > 0 and txt_p:
            total_processed_files += cnt
            created_txt_files.append(txt_p)
            print("Generated TXT Analysis for: {} -> {} objects".format(os.path.basename(mdir), cnt))

    # Generate Total Master TXT File
    master_txt = os.path.join(r"c:\Users\hdy56\OneDrive\바탕 화면\파워빌드분석", "전체_소스코드_상세분석명세서.txt")
    with open(master_txt, "w", encoding="utf-8") as master_f:
        master_f.write("================================================================================\n")
        master_f.write("🏢 일신 ERP/MES 시스템 전체 소스 코드 개별 상세 분석 종합 명세서\n")
        master_f.write("================================================================================\n\n")
        master_f.write("총 모듈(PBL) 수 : {}개\n".format(len(created_txt_files)))
        master_f.write("총 분석 객체 수 : {}개\n\n".format(total_processed_files))
        master_f.write("각 모듈별 세부 소스 분석 텍스트 파일 목록:\n")
        for tp in created_txt_files:
            master_f.write("  - {}\n".format(os.path.basename(tp)))
        master_f.write("\n================================================================================\n\n")

        for tp in created_txt_files:
            with open(tp, "r", encoding="utf-8") as sub_f:
                master_f.write(sub_f.read())
                master_f.write("\n\n")

    print("\nMASTER TXT ANALYSIS CREATED AT:", master_txt)

if __name__ == "__main__":
    main()
