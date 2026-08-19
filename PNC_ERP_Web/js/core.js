/* ===== PNC ERP core.js — 전역 상수/헬퍼/RBAC/UI (app.js 분할 1/9, 순수이동) ===== */
/* ===== PNC ERP 프론트엔드 (조회 전용 프로토타입) ===== */
// ★API 서버 주소: 페이지를 서빙한 서버(location.origin)로 자동 지정 → 내부망 어느 PC에서 열어도 동작.
//   file:// 로 직접 열거나 host가 없으면 로컬 백엔드(개발용)로 폴백.
const API_BASE=(typeof location!=='undefined' && location.protocol!=='file:' && location.host)?location.origin:'http://127.0.0.1:8010';
const won = n => (n==null||n==='')?'-':Number(n).toLocaleString('ko-KR',{maximumFractionDigits:2});
const esc = s => (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
// ★전역 날짜 기본값(모든 화면 통일): 일자=당일 · 월=당월 · 기간=당월1일~당일
const nowCD = () => {const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};   // 당일 YYYY-MM-DD
const nowCM = () => nowCD().slice(0,7);   // 당월 YYYY-MM
const nowMS = () => nowCM()+'-01';        // 당월1일 YYYY-MM-01
// ★날짜 input(type=date)은 브라우저 네이티브 키보드 편집에 맡김: 세그먼트(연/월/일) 클릭 후 숫자 입력·연속 타이핑·화살표·달력 모두 네이티브 지원.
//   (과거 전역 커스텀 핸들러가 모든 숫자키 preventDefault→ 월/일 세그먼트만 고치기 불가·YYMMDD 오인 문제. 2026-08-14 제거. 커스텀 자동채움 재도입 시 세그먼트 편집을 막지 말 것.)
const TYPE_NM={RAW:'원자재',SUB:'부자재',CON:'소모품',S_ASSY:'반제품',PROD:'완제품'};
// 용접봉 판정(품명 '용접봉' 포함). 신 원칙: 용접봉=재료비지만 BOM 아닌 용접공정 종속 → 화면에서 기본 숨김(데이터는 보존). [[newerp-weld-cost-split]]
const isWeld=nm=>/용접봉/.test(nm||'');
const tbadge = t => `<span class="bdg ${t}">${TYPE_NM[t]||t}</span>`;
const supCount = cd => (DB.itemDetail[cd]?.suppliers?.length)||0;
/* 라인 코드 → 표시명 매핑 */
const LINE_NM = (typeof DB!=='undefined' && DB.lineNames) ? DB.lineNames : {};
const lineName = l => { if(!l) return ''; const k=(''+l).trim(); return LINE_NM[k] || LINE_NM[l] || l; };
const wonI = n => (n==null||n==='')?'-':Math.round(Number(n)).toLocaleString('ko-KR');  /* 정수 금액 */
/* ===== ★Phase5: nx.stock_ledger 파생 조회 공통 뷰 (조회 8종 source=live|nx 토글) =====
   각 SCREEN load()에서 source==='nx'면 이 함수로 위임(라이브 render 대체). 라이브 기본 동작은 완전 무변경.
   nxUrl = 해당 라이브 엔드포인트 + '&source=nx'. opts={title, onBack}. 잔량=기초+ΣMAINT 균일 그리드+사유표시. */
async function nxDerivedView(c, nxUrl, opts){
  opts=opts||{};
  c.innerHTML=`<div class="page-title">${esc(opts.title||'nx 원장 파생')} <span style="font-size:12px;color:var(--muted);font-weight:400">nx원장 파생(대조용)</span></div>
   <div class="page-sub">✏️ 단일원장 <code>nx.stock_ledger</code> 파생(잔량=기초+ΣMAINT) · 병행운영 대조 · <b>기본값은 라이브</b></div>
   <div class="toolbar"><button class="btn" id="nxback">← 라이브로</button><span id="nxinfo" style="font-size:12px;color:var(--muted)"></span>
     <div class="spacer"></div><button class="btn xls" id="nxxls">📥 엑셀</button></div>
   <div class="summary-bar" id="nxsum"></div>
   <div class="grid-wrap" style="max-height:500px;overflow:auto"><table class="tbl fit"><thead id="nxth"></thead><tbody id="nxbody"><tr><td class="empty"><span class="lspin"></span> nx 원장 파생 조회 중…</td></tr></tbody></table></div>
   <div class="rowcount" id="nxcnt"></div>`;
  if(opts.onBack) c.querySelector('#nxback').onclick=opts.onBack;
  try{
    const r=await fetch(nxUrl); if(!r.ok) throw new Error('HTTP '+r.status);
    const j=await r.json(); const rows=j.rows||[], t=j.totals||{};
    c.querySelector('#nxinfo').innerHTML=j.nx_note?`ⓘ ${esc(j.nx_note)}`:`point=${esc(j.point||'')} · ${esc(j.from_ymd||'')}~${esc(j.to_ymd||'')}`;
    c.querySelector('#nxsum').innerHTML=`<div class="s-item">건수 <b>${won(rows.length)}</b></div><div class="s-item">기초 <b>${won(t.base||0)}</b></div><div class="s-item">입고 <b>${won(t.inq||0)}</b></div><div class="s-item">출고 <b>${won(t.outq||0)}</b></div><div class="s-item">기말 <b>${won(t.endq||0)}</b></div>`;
    c.querySelector('#nxth').innerHTML=`<tr><th>품목/자도번</th><th class="cap">품명</th><th>파트</th><th>거래처</th><th class="num">기초</th><th class="num">입고</th><th class="num">출고</th><th class="num">기말</th></tr>`;
    // ★#4 파트(gpc)·거래처(cust) 코드→이름(품목처럼) · 합계=grandtot 하단고정([[feedback-ui-rules]])
    const gt=rows.length?`<tr class="grandtot"><td colspan="4" class="right">총계 (${won(rows.length)}건)</td><td class="num">${won(t.base||0)}</td><td class="num">${won(t.inq||0)}</td><td class="num">${won(t.outq||0)}</td><td class="num"><b>${won(t.endq||0)}</b></td></tr>`:'';
    c.querySelector('#nxbody').innerHTML=rows.length?rows.map(x=>`<tr><td><b>${esc(x.cd)}</b></td><td class="cap" title="${esc(x.nm||'')}">${esc(x.nm||'')}</td><td title="${esc(x.gpc||'')}">${esc(x.gpc_nm||x.gpc||'')}</td><td title="${esc(x.cust||'')}">${esc(x.cust_nm||x.cust||'')}</td><td class="num">${won(x.base)}</td><td class="num">${won(x.inq)}</td><td class="num">${won(x.outq)}</td><td class="num"><b>${won(x.endq)}</b></td></tr>`).join('')+gt:`<tr><td colspan="8" class="empty">nx 원장 파생 데이터 없음${j.nx_note?' — '+esc(j.nx_note):''}</td></tr>`;
    c.querySelector('#nxcnt').textContent=`${rows.length}건 (nx 원장 파생)`;
    c.querySelector('#nxxls').onclick=()=>downloadCSV((opts.title||'nx파생')+'.csv',['품목/자도번','품명','파트','파트명','거래처','거래처명','기초','입고','출고','기말'],rows.map(x=>[x.cd,x.nm,x.gpc,x.gpc_nm,x.cust,x.cust_nm,x.base,x.inq,x.outq,x.endq]));
  }catch(e){ const b=c.querySelector('#nxbody'); if(b) b.innerHTML=`<tr><td colspan="8" class="empty" style="color:#c0392b">⚠ nx 파생 조회 실패</td></tr>`; }
}
/* ===== 전역 로딩 스피너 (모든 라이브 화면 공용) ===== */
const SPIN='<span class="lspin"></span>';
const spinRow=(cols,txt)=>`<tr><td colspan="${cols}" class="empty"><span class="lspin"></span> ${esc(txt||'라이브 조회 중…')}</td></tr>`;
(function(){const s=document.createElement('style');s.textContent=`
.lspin{display:inline-block;width:15px;height:15px;border:2px solid var(--line-2,#cbd5e1);border-top-color:var(--accent,#2f6db3);border-radius:50%;vertical-align:-3px;animation:lspin .7s linear infinite;margin-right:6px}
@keyframes lspin{to{transform:rotate(360deg)}}
.lspin-lg{width:26px;height:26px;border-width:3px}
.empty .lspin{vertical-align:-2px}
.botsum{background:linear-gradient(0deg,#eef4ff,#f8faff);border:1px solid #cfe0ff;border-radius:8px;box-shadow:0 -2px 8px rgba(30,45,70,.06);padding:8px 14px}`;document.head.appendChild(s);})();
/* 컬럼 헤더 더블클릭 정렬 (keys: 컬럼순서별 데이터키, null=정렬제외) */
/* 컬럼 너비 조절 핸들 — 우측 경계 드래그로 조절, 핸들 더블클릭으로 초기화. 모든 .tbl th에 부여 */
function addResizer(th){
  if(!th.dataset.base) th.dataset.base=th.textContent.trim();
  if(th.querySelector('.col-resizer'))return;
  const rz=document.createElement('div'); rz.className='col-resizer';
  rz.addEventListener('mousedown',e=>{e.preventDefault();e.stopPropagation();
    const sx=e.pageX, sw=th.offsetWidth;
    const mv=ev=>{const w=Math.max(0,sw+ev.pageX-sx);th.style.width=th.style.minWidth=th.style.maxWidth=w+'px';};
    const up=()=>{document.removeEventListener('mousemove',mv);document.removeEventListener('mouseup',up);};
    document.addEventListener('mousemove',mv);document.addEventListener('mouseup',up);});
  rz.addEventListener('dblclick',e=>{e.stopPropagation();th.style.width=th.style.minWidth=th.style.maxWidth='';});
  th.appendChild(rz);
}
function attachResizers(c){ c.querySelectorAll('table.tbl thead th').forEach(addResizer); }

function enableSort(c, keys, getRows, render){
  const ths=c.querySelectorAll('thead th');
  ths.forEach((th,i)=>{
    addResizer(th);
    const key=keys&&keys[i]; if(!key)return;   // keys 미전달(단일인자 호출=리사이저만)시 정렬 스킵·크래시 방지
    th.style.cursor='pointer'; th.title='더블클릭하여 정렬 · 우측 경계 드래그로 너비조절';
    th.ondblclick=()=>{
      th._d = th._d===1?-1:1; const d=th._d;
      getRows().sort((a,b)=>{let x=a[key],y=b[key];
        const nx=parseFloat(x),ny=parseFloat(y);
        if(x!=null&&y!=null&&x!==''&&y!==''&&!isNaN(nx)&&!isNaN(ny)) return (nx-ny)*d;
        return String(x==null?'':x).localeCompare(String(y==null?'':y),'ko')*d;});
      render(getRows());
      // 화살표는 첫 텍스트 노드만 교체 → 리사이저 보존
      ths.forEach(o=>{const t=o.childNodes[0]; if(t&&t.nodeType===3) t.nodeValue=o.dataset.base;});
      const t=th.childNodes[0]; if(t&&t.nodeType===3) t.nodeValue=th.dataset.base+(d===1?' ▲':' ▼');
    };
  });
}

/* ---- 모듈(상단) → 하위메뉴(좌측) 구성 ---- */
const MODULES=[
 {id:'base',nm:'기준정보 관리',ic:'📦',subs:[
   {id:'items',ic:'📦',nm:'품목 조회',cnt:DB.dashboard.items_total},
   {id:'bomview',ic:'🔀',nm:'품목 BOM 조회'},
   {id:'lgbomview',ic:'🔀',nm:'LG BOM 관리'},
   {id:'docmgr',ic:'📐',nm:'도면/문서 조회'},
   {id:'basemaster',ic:'🗂️',nm:'기준 마스터 관리'},
   {id:'prodinfo',ic:'⚙️',nm:'생산정보등록'},
 ]},
 {id:'pur',nm:'구매/자재',ic:'🧾',subs:[
   {id:'mat',ic:'📦',nm:'자재목록조회'},
   {id:'matledger',ic:'📒',nm:'자재수불장'},
   {id:'matclose',ic:'📗',nm:'자재 일마감(이동평균)'},
   {id:'dispatchdetail',ic:'📋',nm:'자재불출명세서'},
   {id:'dispatch',ic:'📤',nm:'자재불출집계표'},
   {id:'receiptdetail',ic:'🧾',nm:'자재입고명세서'},
   {id:'receipt',ic:'📥',nm:'자재입고집계표'},
   {id:'lgsagub',ic:'📊',nm:'LG사급현황'},
   {id:'matkanban',ic:'📊',nm:'자재입고현황',hide:true},
   {sep:true},
   {id:'dopippur',ic:'🚢',nm:'도입-수입입력'},
   {id:'dopipsale',ic:'✈️',nm:'도입-수출입력'},
   {sep:true},
   {id:'stockreceipt',ic:'📥',nm:'자재입고관리'},
   {id:'matreceive',ic:'📦',nm:'자재입고(발주분)'},
   {id:'stockissue',ic:'📤',nm:'자재출고관리'},
   {id:'stockadjust',ic:'🛠️',nm:'자재재고조정'},
   {id:'saguboutput',ic:'📤',nm:'사급출고관리'},
   {id:'matinout',ic:'🔁',nm:'자재 입출고현황'},
   {id:'manorder',ic:'🛒',nm:'수동발주'},
   {id:'matprice',ic:'💲',nm:'원소재/용접봉 시세',hide:true},
   {id:'sourceprofile',ic:'🧭',nm:'조달 프로파일'},
   {sep:true},
   {id:'salemagam',ic:'🧾',nm:'자재매출마감'},
   {id:'purmagam',ic:'📥',nm:'자재매입마감'},
   {id:'coopquote2',ic:'💱',nm:'협력사견적관리'},
 ]},
 {id:'partner',nm:'협력사',ic:'🤝',subs:[
   {id:'partnerplan',ic:'📋',nm:'협력사계획현황'},
   {id:'deliv420',ic:'🧾',nm:'거래명세서 발행'},
   {id:'setinreq',ic:'🏷️',nm:'거래명세서 발행(바코드)'},
   {id:'setstock',ic:'📦',nm:'자재세트입고관리'},
   {id:'sagubadjust',ic:'🛠️',nm:'협력사사급재고관리'},
 ]},
 {id:'prod',nm:'생산',ic:'🏭',subs:[
   {id:'prodstock',ic:'🏭',nm:'생산재고조회'},
   {id:'prodinout',ic:'🔁',nm:'생산입출고현황'},
   {sep:true},
   {id:'orderupload',ic:'📥',nm:'주문업로드'},
   {id:'planupload',ic:'📅',nm:'생산계획업로드'},
   {id:'planinput',ic:'➕',nm:'생산계획추가입력'},
   {id:'prodsheet',ic:'🖨️',nm:'생산전표출력관리'},
   {id:'partplan',ic:'🧩',nm:'파트별 생산계획'},
   {id:'kitting',ic:'🧰',nm:'준비실적처리(키팅)'},
   {id:'procresult',ic:'✅',nm:'공정별 생산실적등록'},
   {id:'procbarcode',ic:'🔫',nm:'공정별 바코드생산실적'},
   {id:'partresult',ic:'📈',nm:'파트별 생산실적현황'},
   {id:'prodresult',ic:'📊',nm:'생산실적현황'},
   {id:'gongsu',ic:'⏱️',nm:'공수등록(근무/지원)'},
   {sep:true},
   {id:'partstockadj',ic:'🛠️',nm:'생산파트재고조정'},
   {id:'partissue',ic:'📤',nm:'생산자재출고관리'},
 ]},
 {id:'sales',nm:'영업',ic:'📈',subs:[
   {id:'salesstock',ic:'📦',nm:'제품재고조회'},
   {id:'prodinvout',ic:'🔁',nm:'제품입출고현황'},
   {id:'prodstockadj',ic:'📦',nm:'제품재고조정'},
   {id:'saleout',ic:'📤',nm:'판매및출고등록'},
   {id:'lgsale',ic:'🚚',nm:'출하실적등록/LG송장'},
   {id:'shipment',ic:'🚚',nm:'출하실적현황'},
   {id:'salesforecast',ic:'📅',nm:'영업예상매출현황'},
   {id:'salesplan',ic:'🗓️',nm:'영업계획현황'},
   {id:'lgrecv',ic:'🏢',nm:'LG리시빙관리'},
 ]},
 {id:'gagong',nm:'가공',ic:'⚙️',subs:[
   {id:'gagongprog420',ic:'🏭',nm:'가공생산진척관리(전표발행)'},
   {id:'gagongplan4w',ic:'📋',nm:'4주간 가공계획현황'},
   {id:'gagongjeohist',ic:'🧾',nm:'가공전표이력현황'},
   {id:'gagongmove580',ic:'🚚',nm:'가공창고 이동계획'},
 ]},
 {id:'qc',nm:'품질',ic:'🔎',subs:[
   {id:'qcerror',ic:'🚫',nm:'품질불량관리'},
   {id:'scrapraw',ic:'🗑',nm:'가공스크랩관리'},
   {id:'qcspec',ic:'📐',nm:'시방변경관리'},
   {id:'qciqc',ic:'🔬',nm:'수입검사(IQC)조회'},
   {id:'meeting',ic:'📝',nm:'품질 반성회의록'},
 ]},
 {id:'dev',nm:'개발',ic:'🧪',subs:[
   {id:'devmaster',ic:'🛠️',nm:'원가/BOM 기준정보'},
   {id:'itemmaster',ic:'📇',nm:'품목마스터 관리'},
   {id:'rawmat',ic:'🧱',nm:'원소재 마스터'},
   {id:'itembom',ic:'📋',nm:'품목별 공정관리'},
   {id:'unifybom',ic:'🔀',nm:'품목 BOM관리'},
   {id:'modelbom',ic:'🧬',nm:'모델BOM 관리'},
   {id:'delivery',ic:'📦',nm:'납품 포장/적재'},
   {id:'subvariant',ic:'🧩',nm:'조달경로 통합검토'},
   {id:'costanalysis',ic:'💹',nm:'품목별 원가분석'},
   {id:'costverify',ic:'🔬',nm:'원가엔진 검증(라이브)'},
   {id:'price',ic:'💰',nm:'품목단가 조회'},
   {id:'pricemgmt',ic:'🛠️',nm:'품목단가 관리'},
   {id:'dtradeprice',ic:'🔁',nm:'직거래 LME 판가연동'},
 ]},
 {id:'mgmt',nm:'경영',ic:'📊',subs:[
   {id:'dailypurissue',ic:'📋',nm:'일일 영업/매입 현황'},
 ]},
 {id:'sys',nm:'시스템관리',ic:'⚙️',subs:[
   {id:'close',ic:'🔒',nm:'마감관리'},
   {id:'users',ic:'👤',nm:'사용자관리'},
   {id:'perm',ic:'🔑',nm:'권한관리'},
 ]},
];
const allSubs=()=>MODULES.flatMap(m=>m.subs);

/* ---- 좌측 메뉴 사용자 순서(드래그 재배치) 저장/적용 ---- */
const MENU_ORDER_KEY='pnc_menu_order_v1';
function loadMenuOrder(){try{return JSON.parse(localStorage.getItem(MENU_ORDER_KEY)||'{}')||{};}catch(e){return {};}}
function saveMenuOrder(o){try{localStorage.setItem(MENU_ORDER_KEY,JSON.stringify(o));}catch(e){}}
function applyMenuOrder(){
  const ord=loadMenuOrder();
  MODULES.forEach(m=>{
    const saved=ord[m.id]; if(!saved||!saved.length)return;
    const byId={}; m.subs.forEach(it=>{if(!it.sep)byId[it.id]=it;});
    const used=new Set(), out=[];
    saved.forEach(tok=>{ if(tok==='__sep__')out.push({sep:true});
      else if(byId[tok]&&!used.has(tok)){out.push(byId[tok]);used.add(tok);} });
    m.subs.forEach(it=>{if(!it.sep&&!used.has(it.id)){out.push(it);used.add(it.id);}});  // 신규(미저장) 항목은 뒤에
    if(out.some(it=>!it.sep))m.subs=out;
  });
}
function serializeFolder(folderEl){
  const fid=folderEl.dataset.folder;
  const toks=[...folderEl.querySelectorAll('.tree-children > *')]
    .map(k=>k.classList.contains('tree-sep')?'__sep__':k.dataset.id).filter(Boolean);
  const ord=loadMenuOrder(); ord[fid]=toks; saveMenuOrder(ord); applyMenuOrder();
}
function resetMenuOrder(){ localStorage.removeItem(MENU_ORDER_KEY); location.reload(); }

/* ---- 좌측 트리 메뉴 (열고/닫기 + 드래그 재배치) ---- */
function buildTree(){
  applyMenuOrder();
  if(!document.getElementById('menuDragCss')){const st=document.createElement('style');st.id='menuDragCss';
    st.textContent='.tree-leaf[draggable=true]{cursor:grab}.tree-leaf.dragging{opacity:.45}.tree-leaf.drop-before{box-shadow:inset 0 2px 0 #1c47a0}.tree-leaf.drop-after{box-shadow:inset 0 -2px 0 #1c47a0}.menu-reset{font-size:11px;color:#8aa0bd;cursor:pointer;padding:6px 12px}.menu-reset:hover{color:#1c47a0;text-decoration:underline}';
    document.head.appendChild(st);}
  const sb=document.getElementById('sidebar');
  let h=`<div class="tree"><div class="tree-leaf" data-id="dash">대시보드</div>`;
  MODULES.forEach(m=>{
    const subs=m.subs.filter(it=>it.sep||(!it.hide&&PERM.canView(it.id)));   // 조회권한 없는/숨김 메뉴 제외(구분선 유지)
    if(!subs.some(it=>!it.sep))return;                            // 실제 메뉴 없는 폴더는 폴더째 숨김
    h+=`<div class="tree-folder collapsed" data-folder="${m.id}">
      <div class="tree-fhead"><span class="arw">▾</span>${m.nm}</div>
      <div class="tree-children">`;
    subs.forEach(it=>{
       if(it.sep){h+=`<div class="tree-sep" data-sep="1" style="height:1px;background:#d5dde8;margin:6px 12px"></div>`;return;}
       h+=`<div class="tree-leaf" draggable="true" data-id="${it.id}">${it.nm}
       ${it.cnt!=null?`<span class="badge">${won(it.cnt)}</span>`:''}${it.soon?'<span class="badge">준비</span>':''}</div>`;});
    h+=`</div></div>`;
  });
  h+=`<div class="menu-reset" title="드래그로 바꾼 메뉴 순서를 기본값으로 되돌립니다">↺ 메뉴 순서 초기화</div>`;
  h+=`</div>`;
  sb.innerHTML=h;
  const rs=sb.querySelector('.menu-reset');if(rs)rs.onclick=()=>{if(confirm('메뉴 순서를 기본값으로 되돌릴까요?'))resetMenuOrder();};
  sb.querySelectorAll('.tree-fhead').forEach(fh=>fh.onclick=()=>fh.parentElement.classList.toggle('collapsed'));
  // 드래그 재배치(폴더 내 leaf 순서 변경 → localStorage 저장)
  let dragEl=null;
  sb.querySelectorAll('.tree-leaf[draggable=true]').forEach(lf=>{
    lf.addEventListener('dragstart',e=>{dragEl=lf;lf.classList.add('dragging');e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',lf.dataset.id);});
    lf.addEventListener('dragend',()=>{dragEl=null;sb.querySelectorAll('.tree-leaf').forEach(x=>x.classList.remove('dragging','drop-before','drop-after'));});
    lf.addEventListener('dragover',e=>{
      if(!dragEl||dragEl===lf||dragEl.parentElement!==lf.parentElement)return;   // 같은 폴더 내에서만
      e.preventDefault();e.dataTransfer.dropEffect='move';
      const r=lf.getBoundingClientRect(),after=(e.clientY-r.top)>r.height/2;
      lf.classList.toggle('drop-after',after);lf.classList.toggle('drop-before',!after);});
    lf.addEventListener('dragleave',()=>lf.classList.remove('drop-before','drop-after'));
    lf.addEventListener('drop',e=>{
      if(!dragEl||dragEl===lf||dragEl.parentElement!==lf.parentElement)return;
      e.preventDefault();
      const r=lf.getBoundingClientRect(),after=(e.clientY-r.top)>r.height/2;
      lf.parentElement.insertBefore(dragEl,after?lf.nextSibling:lf);
      lf.classList.remove('drop-before','drop-after');
      serializeFolder(lf.closest('.tree-folder'));});
  });
  sb.querySelectorAll('.tree-leaf').forEach(lf=>lf.onclick=()=>{
    const id=lf.dataset.id;
    if(id==='dash'){openTab('dash','대시보드');return;}
    const it=allSubs().find(x=>x.id===id);
    if(it.soon){alert('해당 메뉴는 준비 중입니다. (조회 기능을 하나씩 추가 중)');return;}
    openTab(it.id,it.nm);
  });
  highlightActive();
}
function highlightActive(){
  document.querySelectorAll('.tree-leaf').forEach(e=>e.classList.toggle('active',e.dataset.id===active));
}

/* ---- 탭 관리 ---- */
const tabs={}; let active=null;
const $content=document.getElementById('content'), $tabbar=document.getElementById('tabbar');
function openTab(id,nm){
  if(!tabs[id]){
    tabs[id]={nm};
    const t=document.createElement('div');t.className='tab';t.dataset.id=id;
    t.innerHTML=`<span>${nm}</span>`+(id!=='dash'?`<span class="x">✖</span>`:'');
    t.onclick=(ev)=>{if(ev.target.classList.contains('x')){closeTab(id);ev.stopPropagation();}else activate(id);};
    $tabbar.appendChild(t);tabs[id].el=t;
    const c=document.createElement('div');c.id='pg-'+id;c.style.display='none';
    $content.appendChild(c);tabs[id].pg=c;
    (SCREEN[id]||SCREEN._na)(c,id);
    attachResizers(c);
  }
  activate(id);
}
function activate(id){
  active=id;
  Object.entries(tabs).forEach(([k,v])=>{v.el.classList.toggle('active',k===id);v.pg.style.display=k===id?'block':'none';});
  highlightActive();
}
function closeTab(id){
  tabs[id].el.remove();tabs[id].pg.remove();delete tabs[id];
  const rest=Object.keys(tabs);activate(rest[rest.length-1]||'dash');
}

/* ===== ★전역 검색칸 autocomplete (UI규칙17) — 모든 화면 공통 자동적용 =====
   검색성 <input.inp>에 datalist를 자동 부착하고, 같은 화면 표(table.tbl)의 앞 컬럼(이름·코드) distinct로 초이스 채움.
   화면이 draw()로 innerHTML 갈아끼워도 MutationObserver가 재부착(자가치유). 이미 list= 있는 화면은 그대로 유지. */
(function(){
  const KW=/품번|품명|도번|자도번|코드|거래처|자재|검색|이름|모델|작업처|납품|P\/N|불출처|매입처|업체|파트|사용자|부서|작업자/;
  const sig=new WeakMap();
  function build(inp){
    const dl=document.getElementById(inp.getAttribute('list')); if(!dl)return;
    const pg=inp.closest('[id^="pg-"]')||document;
    const tbl=pg.querySelector('table.tbl')||pg.querySelector('table'); if(!tbl)return;
    const tb=tbl.querySelector('tbody'); if(!tb)return;
    const s=tb.children.length+':'+(tb.children[0]?tb.children[0].textContent.length:0);
    if(sig.get(inp)===s)return; sig.set(inp,s);   // 표 미변경이면 재빌드 안함(루프방지)
    // ★검색칸 placeholder에 맞는 헤더 컬럼에서만 후보 추출(거래처 오염 방지)
    const P=inp.getAttribute('placeholder')||'';
    let colRe=null;
    if(/품번|품명|P\/N|PART/i.test(P)) colRe=/품명|품번|품목|PART|P\/N/i;
    else if(/자도번|도번/i.test(P)) colRe=/자도번|도번|PART|MAT|자재/i;
    else if(/거래처|매입처|업체|공급처|불출처|작업처|납품/i.test(P)) colRe=/거래처|매입처|업체|공급처|불출처|작업처|납품/i;
    else if(/제번/i.test(P)) colRe=/제번|WORK/i;
    else if(/모델/i.test(P)) colRe=/모델|MODEL/i;
    else if(/라인/i.test(P)) colRe=/라인|LINE/i;
    else if(/자재/i.test(P)) colRe=/자재|MAT|품명|도번/i;
    else if(/부서|사용자|작업자|담당/i.test(P)) colRe=/부서|사용자|작업자|담당|이름|성명/i;
    let cols=[];
    if(colRe){[...tbl.querySelectorAll('thead th')].forEach((th,i)=>{ if(colRe.test((th.textContent||'').trim())) cols.push(i); });}
    if(!cols.length) cols=[0,1,2,3];   // 헤더 매칭 실패시 앞4컬럼(기존 동작)
    const set=new Set();
    for(const tr of tb.children){const tds=tr.children;
      for(const ci of cols){ if(ci<tds.length){const t=(tds[ci].textContent||'').trim();
        if(t&&t.length<40&&!/^[\d,.\-\s]+$/.test(t)&&t!=='·')set.add(t);}}
      if(set.size>1200)break;}
    dl.innerHTML=[...set].slice(0,1200).map(v=>'<option value="'+v.replace(/"/g,'&quot;').replace(/</g,'&lt;')+'"></option>').join('');
  }
  function enhance(root){
    root.querySelectorAll('input.inp:not([data-ac])').forEach(inp=>{
      const ty=(inp.getAttribute('type')||'text').toLowerCase();
      if(['date','number','month','checkbox','file','radio'].includes(ty)){inp.setAttribute('data-ac','skip');return;}
      if(inp.getAttribute('list')){inp.setAttribute('data-ac','pre');return;}   // 화면 자체 datalist 유지
      if(!KW.test(inp.getAttribute('placeholder')||'')){inp.setAttribute('data-ac','skip');return;}
      const id='ac_'+Math.random().toString(36).slice(2,9);
      const dl=document.createElement('datalist');dl.id=id;
      inp.setAttribute('list',id);inp.setAttribute('autocomplete','off');inp.setAttribute('data-ac','1');
      inp.parentNode.insertBefore(dl,inp.nextSibling);
      build(inp);
    });
    root.querySelectorAll('input.inp[data-ac="1"]').forEach(build);   // 로드된 데이터 반영 재빌드
  }
  let t=null;
  const obs=new MutationObserver(()=>{clearTimeout(t);t=setTimeout(()=>{try{enhance($content);}catch(e){}},250);});
  function start(){ if(!$content)return; obs.observe($content,{childList:true,subtree:true}); enhance($content); }
  if(document.readyState!=='loading')start(); else document.addEventListener('DOMContentLoaded',start);
})();

/* ================= 권한(RBAC) ================= */
const ROLES=['시스템관리자','원가개발','영업','구매/자재','생산','품질','조회전용','협력사'];
// ★슈퍼 계정(전권) + 개발용 자동 로그인 계정. DEV_AUTOLOGIN을 ''로 비우면 일반 로그인으로 전환.
const SUPER_USER={id:'super',pw:'super',nm:'슈퍼관리자',type:'내부',dept:'전산',pos:'대표',roles:['시스템관리자'],partner:'',email:'pncind@pncind.co.kr',tel:'',status:'사용'};
const DEV_AUTOLOGIN='';   // ''=일반 로그인(다중사용자 병행). 개발 단독확인시만 'super'
const SEED_USERS=[
  SUPER_USER,
  {id:'admin',pw:'1234',nm:'관리자',type:'내부',dept:'전산',pos:'관리자',roles:['시스템관리자'],partner:'',email:'admin@pncind.co.kr',tel:'',status:'사용'},
  {id:'kdev',pw:'1234',nm:'김개발',type:'내부',dept:'원가개발',pos:'대리',roles:['원가개발','조회전용'],partner:'',email:'',tel:'',status:'사용'},
  {id:'ysales',pw:'1234',nm:'이영업',type:'내부',dept:'영업',pos:'과장',roles:['영업'],partner:'',email:'',tel:'',status:'사용'},
  {id:'ysales2',pw:'1234',nm:'최영업',type:'내부',dept:'영업',pos:'사원',roles:['조회전용'],partner:'',email:'',tel:'',status:'사용'},
  {id:'jbuy',pw:'1234',nm:'박구매',type:'내부',dept:'구매/자재',pos:'사원',roles:['구매/자재'],partner:'',email:'',tel:'',status:'사용'},
  {id:'miraero',pw:'1234',nm:'미래정밀',type:'협력사',dept:'',pos:'',roles:['협력사'],partner:'미래정밀',email:'',tel:'',status:'사용'},
  {id:'TEST1',pw:'pnc1!',nm:'테스트1(전권)',type:'내부',dept:'전산',pos:'',roles:['시스템관리자'],partner:'',email:'',tel:'',status:'사용'},
  {id:'TEST2',pw:'pnc2!',nm:'테스트2(자재·협력사)',type:'내부',dept:'구매/자재',pos:'',roles:['구매/자재'],partner:'',email:'',tel:'',status:'사용'},
  {id:'TEST3',pw:'pnc3!',nm:'테스트3(생산)',type:'내부',dept:'생산',pos:'',roles:['생산'],partner:'',email:'',tel:'',status:'사용'},
  {id:'TEST4',pw:'pnc4!',nm:'테스트4(개발)',type:'내부',dept:'원가개발',pos:'',roles:['원가개발'],partner:'',email:'',tel:'',status:'사용'},
];
// 역할 → 편집권 부여 모듈(그룹). 시스템관리자=전권(별도). 미설정 모듈=조회만.
const ROLE_MOD={'구매/자재':['pur','partner'],'생산':['prod','gagong'],'원가개발':['dev'],'영업':['sales'],'품질':['qc'],'경영':['mgmt']};
const COMMON_VIEW=['base'];   // 전부서 공통 '조회' 모듈(기준정보=품목·BOM·도면 조회). 수정은 역할/관리자만(직원 읽기전용).
const _sid2mod=(sid)=>{for(const m of MODULES){for(const s of (m.subs||[])){if(s.id===sid)return m.id;}}return '';};
const getUsers=()=>{try{const s=localStorage.getItem('perm_users');if(s)return JSON.parse(s);}catch(e){}return JSON.parse(JSON.stringify(SEED_USERS));};
const PERM={
  userId: localStorage.getItem('perm_userId')||'admin',
  perms: (()=>{try{return JSON.parse(localStorage.getItem('perm_userperm'))||{};}catch(e){return {};}})(),  // 사용자×프로그램×{view,edit}
  savePerms(){localStorage.setItem('perm_userperm',JSON.stringify(this.perms));
    try{return fetch(API_BASE+'/api/perm/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({perms:this.perms,by:this.userId})});}catch(e){return Promise.resolve();}},
  async loadFromServer(){try{const r=await fetch(API_BASE+'/api/perm/all');if(!r.ok)return false;const j=await r.json();if(j&&j.perms){this.perms=j.perms;localStorage.setItem('perm_userperm',JSON.stringify(this.perms));return true;}}catch(e){}return false;},
  // ★계정목록 서버 로드(전 PC 공통) — 로그인 전 호출. 서버값=정본, 시드계정은 항상 병합 보장.
  async loadUsersFromServer(){try{const r=await fetch(API_BASE+'/api/perm/users');if(!r.ok)return false;const j=await r.json();
    if(j&&Array.isArray(j.users)&&j.users.length){const merged=j.users.slice();
      SEED_USERS.forEach(su=>{if(!merged.some(u=>u.id===su.id))merged.push(JSON.parse(JSON.stringify(su)));});
      localStorage.setItem('perm_users',JSON.stringify(merged));return true;}}catch(e){}return false;},
  saveUsersToServer(users){try{return fetch(API_BASE+'/api/perm/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({users,by:this.userId})});}catch(e){return Promise.resolve();}},
  setUser(id){this.userId=id;localStorage.setItem('perm_userId',id);},
  currentUser(){return getUsers().find(u=>u.id===this.userId)||{id:'-',nm:'미지정',roles:['시스템관리자']};},
  isAdmin(){return (this.currentUser().roles||[]).includes('시스템관리자');},
  can(sid,act){ if(this.isAdmin())return true;   // TEST1(시스템관리자)=전권
    const pm=(this.perms[this.userId]||{})[sid];
    if(pm){ if(act==='view')return pm.view!==false; return !!pm.edit; }   // ★TEST1이 개별 부여한 권한 우선(override)
    const roles=this.currentUser().roles||[], mod=_sid2mod(sid);
    if(act==='view' && COMMON_VIEW.includes(mod)) return true;   // 기준정보=전부서 공통 조회
    return roles.some(r=>(ROLE_MOD[r]||[]).includes(mod)); },   // 기본=본인 부서 모듈만 조회·수정(자재는 자재것만). 나머지 부서=숨김
  canView(sid){return this.can(sid,'view');},
  canEdit(sid){return this.can(sid,'edit');},
  label(){const u=this.currentUser();return `${u.nm}${this.isAdmin()?'·전권':''}`;},
};
// ===== UI규칙: 컬럼 크기 사용자 조정 (전역 .tbl 표 헤더 우측 드래그) =====
(function(){
  const EDGE=7;
  document.addEventListener('mousemove',function(e){
    if(document.body.classList.contains('col-rsz'))return;
    const th=e.target.closest&&e.target.closest('table.tbl thead th');
    if(!th){return;}
    const r=th.getBoundingClientRect();
    th.style.cursor=(r.right-e.clientX<=EDGE)?'col-resize':'';
  });
  document.addEventListener('mousedown',function(e){
    const th=e.target.closest&&e.target.closest('table.tbl thead th');
    if(!th)return;
    const r=th.getBoundingClientRect();
    if(r.right-e.clientX>EDGE)return;   // 우측 가장자리에서만
    e.preventDefault(); e.stopPropagation();
    const sx=e.pageX, sw=th.offsetWidth;
    document.body.classList.add('col-rsz'); document.body.style.cursor='col-resize';
    const mv=ev=>{const w=Math.max(24,sw+ev.pageX-sx); th.style.width=w+'px'; th.style.minWidth=w+'px'; th.style.maxWidth=w+'px';};
    const up=()=>{document.removeEventListener('mousemove',mv); document.removeEventListener('mouseup',up);
      document.body.classList.remove('col-rsz'); document.body.style.cursor='';};
    document.addEventListener('mousemove',mv); document.addEventListener('mouseup',up);
  });
})();

// 전 프로그램(화면) 목록 = MODULES flatten
function allPrograms(){const out=[];MODULES.forEach(m=>(m.subs||[]).forEach(s=>out.push({id:s.id,nm:s.nm,mod:m.nm,modId:m.id})));return out;}

/* 공용: CSV(엑셀) 다운로드 — 대부분 화면 공용. header=배열, rows=배열의 배열 */
function dlCSV(name, header, rows){
  const q=v=>{v=(v==null?'':''+v); return /[",\n\r]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v;};
  const csv='﻿'+[header,...rows].map(r=>r.map(q).join(',')).join('\r\n');
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
  a.download=name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(()=>URL.revokeObjectURL(a.href),1000);
}

/* ================= 화면들 ================= */
const SCREEN={};
SCREEN._na=(c,id)=>{c.innerHTML=`<div class="empty">「${id}」 화면은 준비 중입니다.</div>`;};

/* ===== 시방변경 상태 마커(구시방 경보) — 거래/조회 화면 공용 =====
   사용법: 품번 셀에 data-si="품번" 부여 → 렌더 후 specDecorate(container) 호출.
   red(적용지남=구시방,금지) 🔴✕ / orange(적용예정) 🟠✕ · 클릭 시 시방내용 팝업 */
const SPEC={cache:{},allLoaded:false,_p:null};
function specLoadAll(){   // 시방변경 전체맵 1회 로드(캐시)
  if(SPEC.allLoaded)return Promise.resolve();
  if(!SPEC._p)SPEC._p=fetch(API_BASE+'/api/spec/all').then(r=>r.json())
    .then(j=>{Object.assign(SPEC.cache,j.map||{});SPEC.allLoaded=true;}).catch(()=>{});
  return SPEC._p;
}
function specMark(item){
  const s=SPEC.cache[item]; if(!s)return '';
  const col=s.sev==='red'?'#c0392b':'#e08e0b';
  return `<span class="spec-x" data-si="${esc(item)}" title="시방변경 ${s.applied?'적용됨(구시방)':'예정'} · 적용 ${esc(s.apply_ymd)} · ${esc(s.rev_desc)}" style="cursor:pointer;color:${col};font-weight:900;margin-right:3px">✕</span>`;
}
function specBindPopup(container){
  container.querySelectorAll('.spec-x').forEach(el=>el.onclick=(e)=>{e.stopPropagation();const it=el.dataset.si,s=SPEC.cache[it];if(!s)return;
    alert(`[시방변경 ${s.applied?'적용됨 · 구시방':'적용 예정'}]\n\n품번: ${it}\n적용일: ${s.apply_ymd}\nECO: ${s.eco_no}\n접수일: ${s.rev_ymd}\n내용: ${s.rev_desc}\n\n${s.applied?'⛔ 적용일 경과 — 이 품번(구시방)은 발주·입고·키팅·생산·출하 금지. 재고는 폐기대상.':'⚠ 적용 예정 — 사전 확인 후 진행하세요.'}`);});
}
async function specDecorate(container){
  await specLoadAll();
  const cells=[...container.querySelectorAll('[data-si]')].filter(c=>!c.classList.contains('spec-x')&&!c.dataset.done);
  cells.forEach(c=>{const m=specMark(c.dataset.si);if(m)c.insertAdjacentHTML('afterbegin',m);c.dataset.done='1';});
  specBindPopup(container);
}

/* 공용: 품목 검색그리드 렌더러 (품목 조회 / 자재 목록 공용) */
function itemGrid(c,{title,sub,types,showSupCnt}){
  const typeOpts = Object.entries(TYPE_NM).filter(([k])=>!types||types.includes(k));
  c.innerHTML=`
   <div class="page-title">${title}</div><div class="page-sub">${sub}</div>
   <div class="toolbar">
     <label>검색</label><input class="inp" id="q" placeholder="품목코드 / 품명">
     <label>유형</label><select class="sel" id="type"><option value="">전체</option>
       ${typeOpts.map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select>
     <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
   </div>
   <div class="split">
     <div><div class="grid-wrap"><table class="tbl"><thead><tr>
        <th>품목코드</th><th>품명</th><th>유형</th><th>분류</th><th>단위</th>
        <th class="num">표준원가</th>${showSupCnt?'<th class="center">매입처</th>':''}<th class="center">사용</th>
       </tr></thead><tbody id="body"></tbody></table></div><div class="rowcount" id="cnt"></div></div>
     <div class="panel" id="i-detail"><div class="panel-h">상세 정보</div><div class="panel-b empty">좌측에서 품목을 선택하세요.</div></div>
   </div>`;
  const pool = DB.items.filter(r=>!types||types.includes(r.type));
  const body=c.querySelector('#body');
  const render=rows=>{
    body.innerHTML=rows.length?rows.map(r=>`<tr data-cd="${esc(r.cd)}">
      <td data-si="${esc(r.cd)}"><b>${esc(r.cd)}</b></td><td>${esc(r.nm)}</td><td>${tbadge(r.type)}</td>
      <td>${esc(r.cat)}</td><td class="center">${esc(r.uom)}</td>
      <td class="num">${won(r.price)}</td>${showSupCnt?`<td class="center">${supCount(r.cd)||'-'}</td>`:''}
      <td class="center"><span class="bdg ${r.useyn==='Y'?'ok':'off'}">${r.useyn==='Y'?'사용':'중지'}</span></td></tr>`).join('')
      :`<tr><td colspan="8" class="empty">결과 없음</td></tr>`;
    c.querySelector('#cnt').textContent=`${rows.length}건 표시 / 대상 ${pool.length}건`;
    body.querySelectorAll('tr[data-cd]').forEach(tr=>tr.onclick=()=>{
      body.querySelectorAll('tr').forEach(x=>x.classList.remove('sel'));tr.classList.add('sel');
      itemDetail(c,tr.dataset.cd);});
    specDecorate(body);   // 구시방 품번 X 마커
  };
  const apply=()=>{const q=c.querySelector('#q').value.trim().toLowerCase(),t=c.querySelector('#type').value;
    render(pool.filter(r=>(!t||r.type===t)&&(!q||r.cd.toLowerCase().includes(q)||(r.nm||'').toLowerCase().includes(q))));};
  c.querySelector('#go').onclick=apply;c.querySelector('#q').onkeyup=e=>{if(e.key==='Enter')apply();};
  c.querySelector('#type').onchange=apply;
  c.querySelector('#reset').onclick=()=>{c.querySelector('#q').value='';c.querySelector('#type').value='';apply();};
  render(pool); c._apply=apply;
}
function itemDetail(c,cd){
  const it=DB.items.find(x=>x.cd===cd), dt=DB.itemDetail[cd]||{suppliers:[],prices:[]};
  const sup=dt.suppliers.length?`<table class="tbl"><thead><tr><th>거래처코드</th><th>거래처명</th><th>조달구분</th><th class="center">우선</th></tr></thead>
     <tbody>${dt.suppliers.map(s=>`<tr><td>${esc(s.pcd)}</td><td>${esc(s.pnm)}</td>
       <td>${({BUY:'매입',OUTSOURCE:'가공외주',DIRECT:'직납'}[s.stype]||s.stype)}</td><td class="center">${s.pri}</td></tr>`).join('')}</tbody></table>`
     :`<div class="empty">등록된 매입처 없음</div>`;
  const px=dt.prices.length?`<table class="tbl"><thead><tr><th>유형</th><th>통화</th><th>적용일</th><th class="num">단가</th></tr></thead>
     <tbody>${dt.prices.map(p=>`<tr><td>${({STD_COST:'표준원가',SALE:'판가',BUY:'매입가',SAGUB:'사급단가'}[p.ptype]||p.ptype)}</td>
       <td class="center">${esc(p.cur)}</td><td>${esc(p.ymd)}</td><td class="num">${won(p.up)}</td></tr>`).join('')}</tbody></table>`
     :`<div class="empty">단가 이력 없음</div>`;
  c.querySelector('#i-detail').innerHTML=`<div class="panel-h">상세 정보 ${tbadge(it.type)}</div><div class="panel-b">
     <div class="detail-title">${esc(it.nm)}</div><div class="detail-code">${esc(it.cd)}</div>
     <dl class="kv" style="margin-top:12px">
       <dt>유형</dt><dd>${TYPE_NM[it.type]||it.type}</dd><dt>분류</dt><dd>${esc(it.cat)||'-'}</dd>
       <dt>기준단위</dt><dd>${esc(it.uom)}</dd><dt>표준원가</dt><dd>${won(it.price)}</dd>
       <dt>사용여부</dt><dd>${it.useyn==='Y'?'사용':'중지'}</dd></dl>
     <div class="section-t">매입처 (N:M)</div>${sup}
     <div class="section-t">단가 이력 (시계열)</div>${px}</div>`;
}

/* 품목 조회 (전체) */
/* 품목/자재 조회 — 라이브 PR_M_ITEM 전 컬럼(코드→이름), 레거시 w_pr_master_010 · mat=true→자재만+표준원가 */
function itemLiveView(c, mat){
  const API=API_BASE;
  const st={rows:[],cnt:0,q:'',lg:'',sg:'',nat:'',lgroups:[],sgroups:[],natures:[],loading:false};
  const load=async()=>{st.loading=true;draw();
    try{const r=await fetch(`${API}/api/item/list?q=${encodeURIComponent(st.q)}&lgroup=${encodeURIComponent(st.lg)}&sgroup=${encodeURIComponent(st.sg)}&nature=${encodeURIComponent(st.nat)}&mat=${mat?'1':''}`);
      const j=await r.json();st.rows=j.rows||[];st.cnt=j.cnt||0;if(j.lgroups)st.lgroups=j.lgroups;if(j.sgroups)st.sgroups=j.sgroups;if(j.natures)st.natures=j.natures;}
    catch(e){st.rows=[];}
    st.loading=false;draw();};
  const COLS=[['item_code','품번'],['nm','품명',180],['nature','성격'],['spec','규격',110],['lgroup','대분류'],['sgroup','소분류'],['pipe_kind','품목형태'],['unit','단위'],
    ['in_cust','매입처',120]].concat(mat?[['item_cost','표준원가','n']]:[]).concat([
    ['diam','외경','n'],['thick','두께','n'],['length','길이','n'],['weight','단위중량','n'],['metal','재질'],['work','작업처'],
    ['make_type','제작유형'],['status','상태'],['safe_min','안전min','n'],['safe_max','안전max','n'],['kitting_min','키팅최소','n'],
    ['weld_in','용접IN','n'],['weld_out','용접OUT','n'],['tariff','관세율','n'],['remarks','비고',140]]);
  // tbody만 렌더(정렬 시 헤더 유지·화살표 보존용) — draw와 재사용
  const rowsHTML=()=> st.loading?spinRow(COLS.length):(st.rows.length?st.rows.map(r=>`<tr>${COLS.map((x,i)=>{const v=r[x[0]];
        if(x[0]==='nature')return `<td style="white-space:nowrap"><span style="font-size:10px;color:#33507d">${esc(String(v||'').replace(/^\d+\./,''))}</span>${r.active===0?' <span title="정리대상 후보" style="color:#c0392b;font-weight:700">▲</span>':''}</td>`;
        return `<td class="${x[2]==='n'?'num':''} ${typeof x[2]==='number'?'cap':''}" ${typeof x[2]==='number'?`title="${esc(v)}" style="max-width:${x[2]}px;overflow:hidden;text-overflow:ellipsis"`:''}>${i===0?`<b>${esc(v)}</b>`:(x[2]==='n'?won(v):esc(v))}</td>`;}).join('')}</tr>`).join(''):`<tr><td colspan="${COLS.length}" class="empty">조회 결과 없음</td></tr>`);
  const draw=()=>{
    c.innerHTML=`
     <div class="page-title">📦 ${mat?'자재 목록 조회':'품목 조회'} <span style="font-size:12px;color:var(--muted);font-weight:400">라이브 · ${mat?'구매 대상 자재':'레거시 w_pr_master_010'}</span></div>
     <div class="page-sub">${mat?'구매 자재(원자재·부자재·소모품·사급) + <b>표준원가·매입처</b>':'전 컬럼 라이브 조회'}(코드→이름: 대/소분류·품목형태·단위·재질·매입처·작업처·제작유형). 원본 <code>PR_M_ITEM</code> · 빈컬럼(밸브/형상 등) 미표시</div>
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">
       <input class="inp" id="it-q" value="${esc(st.q)}" placeholder="품번/품명 검색" style="width:170px">
       <label class="tl">대분류</label><select class="inp" id="it-lg" style="width:auto"><option value="">전체</option>${st.lgroups.map(o=>`<option value="${esc(o.code)}" ${st.lg===o.code?'selected':''}>${esc(o.nm||o.code)}</option>`).join('')}</select>
       <label class="tl">소분류</label><select class="inp" id="it-sg" style="width:auto"><option value="">전체</option>${st.sgroups.map(o=>`<option value="${esc(o.code)}" ${st.sg===o.code?'selected':''}>${esc(o.nm||o.code)}</option>`).join('')}</select>
       <label class="tl">성격</label><select class="inp" id="it-nat" style="width:auto"><option value="">전체</option>${st.natures.map(o=>`<option value="${esc(o.code)}" ${st.nat===o.code?'selected':''}>${esc(o.nm||o.code)}</option>`).join('')}</select>
       <button class="btn" id="it-go">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">${won(st.cnt)}건${st.cnt>=3000?'(상한)':''}</span>
     </div>
     <div class="grid-wrap" style="max-height:calc(100vh - 250px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr>${COLS.map(x=>`<th class="${x[2]==='n'?'num':''}">${x[1]}</th>`).join('')}</tr></thead>
      <tbody>${rowsHTML()}</tbody></table></div>`;
    const g=id=>c.querySelector(id);
    g('#it-go').onclick=()=>{st.q=g('#it-q').value;st.lg=g('#it-lg').value;st.sg=g('#it-sg').value;st.nat=g('#it-nat').value;load();};
    g('#it-q').onkeyup=e=>{if(e.key==='Enter')g('#it-go').click();};
    // ★UI규칙: 헤더 더블클릭=정렬(enableSort) + 컬럼폭 드래그(addResizer 내장). tbody만 갱신해 헤더/화살표 보존
    enableSort(c, COLS.map(x=>x[0]), ()=>st.rows, ()=>{const tb=c.querySelector('tbody'); if(tb)tb.innerHTML=rowsHTML();});
  };
  load();
}

/* 자재 목록 조회 = itemLiveView(c,true) — 위 SCREEN.mat 정의(라이브) 사용 */

/* 품목단가 조회 (품목별 그룹 → 구매/판매 단가 히스토리) */
const MKT_NM={EXPORT:'수출',DOMESTIC:'내수'};
/* 전사 단가변동내역 — 라이브 PR_M_ITEM_COST 피드(직전단가 대비 Δ) */
function priceHistView(host){
  const API=API_BASE;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  let F={from:iso(new Date(T.getFullYear(),T.getMonth(),1)),to:iso(T),item:'',tag:'',lgroup:'',sgroup:'',cust:'',changed:true};
  let vT=null;
  let data={rows:[],cnt:0,changed:0}, loading=false, msg='';
  const dcol=s=>(s&&(''+s).length===6)?`${(''+s).slice(0,2)}/${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:(s||'');
  const load=async()=>{loading=true;draw();
    const qs=new URLSearchParams({from_ymd:F.from,to_ymd:F.to,item:F.item,tag:F.tag,lgroup:F.lgroup,sgroup:F.sgroup,cust:F.cust,changed:F.changed?'1':''});
    try{const r=await fetch(`${API}/api/price/history?${qs}`);data=await r.json();msg='';}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010';data={rows:[],cnt:0,changed:0};}
    loading=false;draw();};
  const dcell=d=>{if(d==null)return '<span style="color:#8aa0bd">신규</span>';
    const col=d<0?'#c0392b':(d>0?'#1c7c3a':'#888');const sg=d>0?'▲':(d<0?'▼':'–');
    return `<b style="color:${col}">${sg} ${won(Math.abs(d))}</b>`;};
  const draw=()=>{
    host.innerHTML=`
     <div class="page-sub" style="margin:2px 0 6px">전사 단가변경 이력을 <b>적용일 내림차순</b>으로. 직전단가 대비 증감(Δ) 표시. 원본 <code>PR_M_ITEM_COST</code>(라이브·읽기전용) · 구분 1=매입·E=수출판매·S=내수판매</div>
     <div class="toolbar">
       <label class="tl">적용기간</label><input class="inp" type="date" id="ph-from" value="${F.from}"> ~ <input class="inp" type="date" id="ph-to" value="${F.to}">
       <label class="tl">품번</label><input class="inp" id="ph-item" value="${esc(F.item)}" style="width:110px">
       <label class="tl">대분류</label><select class="inp" id="ph-lg" style="max-width:130px"><option value="">전체</option>${(data.lgroups||[]).map(o=>`<option value="${esc(o.code)}"${F.lgroup===o.code?' selected':''}>${esc(o.nm)}</option>`).join('')}</select>
       <label class="tl">소분류</label><select class="inp" id="ph-sg" style="max-width:130px"><option value="">전체</option>${(data.sgroups||[]).map(o=>`<option value="${esc(o.code)}"${F.sgroup===o.code?' selected':''}>${esc(o.nm)}</option>`).join('')}</select>
       <label class="tl">거래처</label><input class="inp" id="ph-cust" list="ph-custdl" autocomplete="off" value="${esc(F.cust)}" placeholder="거래처명/코드" style="width:120px"><datalist id="ph-custdl"></datalist>
       <label class="tl">구분</label><select class="inp" id="ph-tag"><option value="">전체</option><option value="1"${F.tag==='1'?' selected':''}>매입</option><option value="E"${F.tag==='E'?' selected':''}>판매(수출)</option><option value="S"${F.tag==='S'?' selected':''}>판매(내수)</option></select>
       <label class="tl" style="cursor:pointer"><input type="checkbox" id="ph-chg" ${F.changed?'checked':''}> 변동분만</label>
       <button class="btn" id="ph-search">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">${won(data.cnt)}건${F.changed?'':` · 변동 ${won(data.changed)}`}</span>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 320px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:11px"><thead><tr>
        <th>적용일</th><th>구분</th><th>품번</th><th>품명</th><th>거래처</th><th class="center">시장</th><th class="center">통화</th>
        <th class="num">단가</th><th class="num">직전단가</th><th class="num">증감</th><th class="num">재료비</th><th class="num">가공비</th><th>담당</th><th>등록일시</th></tr></thead>
      <tbody>${loading?spinRow(14):((data.rows&&data.rows.length)?data.rows.map(r=>`<tr>
        <td class="center">${dcol(r.apply_ymd)}</td><td class="center">${esc(r.tag_nm)}</td>
        <td><b>${esc(r.item)}</b></td><td class="bcap" title="${esc(r.nm)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td>
        <td class="bcap" title="${esc(r.cust_nm||r.cust)}" style="max-width:110px;overflow:hidden;text-overflow:ellipsis">${esc(r.cust_nm||r.cust)}</td>
        <td class="center">${esc(r.mkt)}</td><td class="center">${esc(r.curr)}</td>
        <td class="num"><b>${won(r.cost)}</b></td><td class="num" style="color:#888">${r.prev==null?'-':won(r.prev)}</td>
        <td class="num">${dcell(r.delta)}</td><td class="num">${won(r.mat)}</td><td class="num">${won(r.procc)}</td>
        <td>${esc(r.usr)}</td><td class="center" style="color:#8aa0bd">${esc(r.idt)}</td></tr>`).join(''):`<tr><td colspan="14" class="empty">조회 결과 없음</td></tr>`)}</tbody></table></div>`;
    const g=id=>host.querySelector(id);
    g('#ph-search').onclick=()=>{F.from=g('#ph-from').value;F.to=g('#ph-to').value;F.item=g('#ph-item').value;F.tag=g('#ph-tag').value;F.lgroup=g('#ph-lg').value;F.sgroup=g('#ph-sg').value;F.cust=g('#ph-cust').value.trim();F.changed=g('#ph-chg').checked;load();};
    g('#ph-item').onkeyup=e=>{if(e.key==='Enter')g('#ph-search').click();};
    g('#ph-cust').onkeyup=e=>{if(e.key==='Enter')g('#ph-search').click();};
    // 거래처 오토컴플리트(디바운스 서버검색 → datalist)
    g('#ph-cust').oninput=e=>{const q=e.target.value.trim();clearTimeout(vT);if(q.length<1)return;
      vT=setTimeout(async()=>{try{const r=await fetch(`${API}/api/item/vendorsearch?q=${encodeURIComponent(q)}`);const vs=(await r.json()).rows||[];
        const dl=g('#ph-custdl');if(dl)dl.innerHTML=vs.map(x=>`<option value="${esc(x.code)}">${esc(x.name)}</option>`).join('');}catch(err){}},250);};
  };
  load();
}
/* 단가이력 매입/판매 분리 섹션(각 적용월 내림차순) — tag 1/매입=매입, E/S=판매 */
function priceHistSections(rows){
  const dcol=s=>{s=''+(s||'');return s.length===6?`${s.slice(0,2)}/${s.slice(2,4)}`:s;};
  const tagColor=t=>t==='1'?'#1c47a0':(t==='E'?'#b12a2a':'#7a5c1c');
  const isBuy=t=>{t=(''+(t||'')).trim();return t==='1'||t==='매입';};
  const buy=rows.filter(r=>isBuy(r.tag)).slice().sort((a,b)=>(''+(b.apply_ymd||'')).localeCompare(''+(a.apply_ymd||'')));
  const sale=rows.filter(r=>!isBuy(r.tag)).slice().sort((a,b)=>(''+(b.apply_ymd||'')).localeCompare(''+(a.apply_ymd||'')));
  const tbl=(list)=>`<table class="tbl fit" style="font-size:11px"><thead><tr><th>단가구분</th><th>거래처</th><th class="center">적용월</th><th class="center">대표</th><th class="center">통화</th><th class="num">단가</th><th class="num">재료비</th><th class="num">가공비</th><th class="num">기타</th><th>비고</th></tr></thead>
     <tbody>${list.map(r=>`<tr>
       <td class="center"><span style="color:#fff;background:${tagColor((''+(r.tag||'')).trim())};padding:1px 6px;border-radius:8px;font-size:10px">${esc(r.tag_nm)}</span></td>
       <td class="cap" title="${esc(r.cust_nm||r.cust)}" style="max-width:130px;overflow:hidden;text-overflow:ellipsis">${esc(r.cust_nm||r.cust)||'-'}</td>
       <td class="center">${dcol(r.apply_ymd)}</td><td class="center">${r.main?'<b style="color:#e0a020">★</b>':''}</td><td class="center">${esc(r.curr_nm)}</td>
       <td class="num"><b>${won(r.item_cost)}</b></td><td class="num">${won(r.mat_cost)}</td><td class="num">${won(r.proc_cost)}</td><td class="num">${won(r.other_cost)}</td>
       <td class="cap" title="${esc(r.remarks)}" style="max-width:120px;overflow:hidden;text-overflow:ellipsis">${esc(r.remarks)}</td></tr>`).join('')}</tbody></table>`;
  const sec=(title,color,list)=>`<div class="section-t" style="margin:6px 0 3px;font-weight:700;color:${color}">${title} <span class="muted" style="font-weight:400">(${list.length}건)</span></div>${list.length?tbl(list):'<div class="empty" style="padding:6px">없음</div>'}`;
  return sec('🛒 매입단가','#1c47a0',buy)+sec('💹 판매단가 (수출/내수)','#b12a2a',sale);
}
/* 품목별 단가조회(기존) */
/* 품목별 단가조회 — 라이브 PR_M_ITEM_COST (거래처별·적용월 시계열, 레거시 w_pr_master_150) */
function priceItemView(c){
  const API=API_BASE;
  const st={rows:[],cnt:0,q:'',lg:'',sg:'',cust:'',lgroups:[],sgroups:[],sel:'',det:null,plan:null,planEdit:null,loading:false};
  let custT=null;
  const dcol=s=>{s=''+(s||'');return s.length===6?`${s.slice(0,2)}/${s.slice(2,4)}`:s;};
  const tagColor=t=>t==='1'?'#1c47a0':(t==='E'?'#b12a2a':'#7a5c1c');
  const load=async()=>{st.loading=true;draw();
    try{const r=await fetch(`${API}/api/price/search?q=${encodeURIComponent(st.q)}&lgroup=${encodeURIComponent(st.lg)}&sgroup=${encodeURIComponent(st.sg)}&cust=${encodeURIComponent(st.cust)}`);const j=await r.json();st.rows=j.rows||[];st.cnt=j.cnt||0;if(j.lgroups)st.lgroups=j.lgroups;if(j.sgroups)st.sgroups=j.sgroups;}
    catch(e){st.rows=[];}
    st.loading=false;draw();};
  const loadDet=async(item)=>{st.sel=item;st.det=null;st.plan=null;draw();
    try{st.det=await (await fetch(`${API}/api/price/item?item=`+encodeURIComponent(item))).json();}catch(e){}
    // 조달후보 계획단가(후보/계획 단가 — 정산 아님, sourcing 레이어). ★여기서도 편집 가능(조달 프로파일과 동일 nx 테이블)
    st.planEdit=null;
    try{st.plan=await (await fetch(`${API}/api/sourcing/plan_price?item=`+encodeURIComponent(item))).json();}catch(e){st.plan=null;}
    draw();};
  // ★계획단가 편집(품목단가 관리에서도 입력) — 조달 프로파일과 동일 엔드포인트 재사용 → 자동 동기화. 공통(기본)+업체별 예외(override).
  const ovk=(vc,k)=>`${vc}||${k}`;
  const peOpen=async(route_id)=>{
    const rt=((st.plan&&st.plan.routes)||[]).find(r=>r.route_id===route_id)||{};
    const vends=(rt.vendors||[]).filter(v=>v.vendor_code).map(v=>({vendor_code:v.vendor_code,vendor_name:v.vendor_name||v.vendor_code}));
    st.planEdit={route_id,vends,subs:[],children:[],direct:[],assyOv:{},sagubOv:{},loading:true,saving:false,msg:''};draw();
    try{const sr=await (await fetch(`${API}/api/sourcing/sub_price?route_id=${route_id}`)).json();
      st.planEdit.subs=(sr.subs||[]).map(s=>{const pr=(sr.prices||[]).find(p=>p.sub_item===s.sub_item)||{};
        (pr.overrides||[]).forEach(o=>{st.planEdit.assyOv[ovk(o.vendor_code,s.sub_item)]=(o.assy_price!=null?o.assy_price:null);});  // ★ASSY=업체별만
        return {sub_item:s.sub_item,sub_name:s.sub_name||'',gubun:s.gubun||''};});
      st.planEdit.direct=sr.direct_items||[];
    }catch(e){}
    try{const gr=await (await fetch(`${API}/api/sourcing/sagub_price?route_id=${route_id}`)).json();
      st.planEdit.children=(gr.rows||[]).map(x=>{(x.overrides||[]).forEach(o=>{st.planEdit.sagubOv[ovk(o.vendor_code,x.item_code)]=(o.sagub_price!=null?o.sagub_price:null);});
        return {item_code:x.item_code,item_name:x.item_name||'',sub_item:x.sub_item||'',gubun:x.gubun||'',is_purchase:!!x.is_purchase,sagub:(x.is_purchase&&x.sagub_price!=null?x.sagub_price:null)};});
    }catch(e){}
    st.planEdit.loading=false;draw();};
  const peClose=()=>{st.planEdit=null;draw();};
  const peSave=async()=>{const pe=st.planEdit;if(!pe)return;pe.saving=true;pe.msg='';draw();
    const pf=v=>(v!==''&&v!=null)?parseFloat(v):null;
    const arows=[];pe.subs.forEach(s=>{   // ★ASSY=업체별만(공통행 없음)
      pe.vends.forEach(v=>{const k=ovk(v.vendor_code,s.sub_item);if(k in pe.assyOv)arows.push({vendor_code:v.vendor_code,sub_item:s.sub_item,assy_price:pf(pe.assyOv[k])});});});
    const grows=[];pe.children.filter(x=>x.is_purchase).forEach(x=>{grows.push({vendor_code:'',item_code:x.item_code,sagub_price:pf(x.sagub)});
      pe.vends.forEach(v=>{const k=ovk(v.vendor_code,x.item_code);if(k in pe.sagubOv)grows.push({vendor_code:v.vendor_code,item_code:x.item_code,sagub_price:pf(pe.sagubOv[k])});});});
    try{
      if(arows.length){await fetch(`${API}/api/sourcing/sub_price/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:pe.route_id,rows:arows})});}
      if(grows.length){await fetch(`${API}/api/sourcing/sagub_price/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:pe.route_id,rows:grows})});}
      st.planEdit=null;
      try{st.plan=await (await fetch(`${API}/api/sourcing/plan_price?item=`+encodeURIComponent(st.sel))).json();}catch(e){}
      draw();
    }catch(e){pe.saving=false;pe.msg='❌ 저장 실패: '+e;draw();}};
  // 후보/계획 단가 섹션 — 정산 매입/판매 단가(마스터, 마감때만 수정)와 명확히 구분. 계획단가(공통+업체예외)는 여기서 편집 가능
  const planPriceSection=(pl)=>{
    const hdr=`<div class="section-t" style="color:#8a6d1c">🧭 조달후보 계획단가 <span class="muted" style="font-weight:400">(후보/계획 단가 — <b>정산 아님</b>, 여기서 편집 가능)</span></div>
      <div style="font-size:11px;color:#8a6d1c;background:#fdf7e6;border:1px solid #f0e6c8;border-radius:6px;padding:5px 8px;margin-bottom:6px"><b>ASSY 매입단가=업체별</b>(외주 SUB×업체) · <b>사급 부품가=공통+업체예외</b>(매입 부품, 예외 비우면 공통 COALESCE). 단품 매입품은 매입 마스터 자동. 업체는 배분%만. <b>계획단가(nx.item_price)</b>는 여기서 입력·저장(조달 프로파일과 자동 동기화). 위 <b>정산 매입/판매 단가</b>(마스터·마감때만 수정)와는 별개입니다.</div>`;
    if(!pl||!pl.routes||!pl.routes.length)return hdr+`<div class="empty" style="font-size:12px">조달후보(승인 route) 없음 — [개발 › 조달경로 통합검토]에서 후보 생성·승인 후 여기/조달 프로파일에서 계획단가 입력</div>`;
    const pe=st.planEdit;
    const ovtxt=(arr,pk)=>(arr&&arr.length)?' <span style="color:#b8860b;font-size:10px">['+arr.map(o=>`${esc(o.vendor_name||o.vendor_code)}:${o[pk]==null?'-':won(o[pk])}`).join(', ')+']</span>':'';
    const blocks=pl.routes.map(rt=>{
      const rlabel=`R${String(rt.route_no).padStart(2,'0')}${rt.current_flag?'·현행':''}`;
      const editable=rt.approve_flag&&rt.route_id>0;
      const editing=pe&&pe.route_id===rt.route_id;
      const badge=`<span style="background:${rt.current_flag?'#1c7c3a':'#1c47a0'};color:#fff;border-radius:8px;padding:1px 7px;font-size:11px;font-weight:700">${esc(rlabel)}</span> <span style="font-size:12px;color:#556;font-weight:600">${esc(rt.route_name||'')}</span>`;
      const vs=(rt.vendors||[]).filter(v=>v.vendor_code);
      const vendHtml=vs.length?`<div style="font-size:11px;color:#556;margin:2px 0 4px">업체 배분: ${vs.map(v=>`${esc(v.vendor_name||v.vendor_code)} <b>${v.alloc_ratio==null?'-':won(v.alloc_ratio)+'%'}</b>${v.is_active?'':' <span style="color:#aab">(비활성)</span>'}`).join(' · ')}</div>`:'<div style="font-size:11px;color:#aab;margin:2px 0 4px">지정 업체 없음</div>';
      let body;
      if(editing){
        if(pe.loading)body='<div class="empty" style="font-size:12px">불러오는 중…</div>';
        else{
          const asy=pe.subs.length?`<table class="tbl" style="font-size:12px;margin:2px 0"><thead><tr><th>외주 SUB(ASSY 매입단가=업체별)</th>${pe.vends.length?pe.vends.map(v=>`<th class="num" title="${esc(v.vendor_code)}">${esc(v.vendor_name)}</th>`).join(''):'<th class="num">업체별</th>'}</tr></thead><tbody>${pe.subs.map(s=>`<tr><td><b>🧩 ${esc(s.sub_item)}</b> <span class="cap" style="color:#8aa0bd">${esc(s.sub_name)}</span></td>${pe.vends.length?pe.vends.map(v=>{const av=pe.assyOv[ovk(v.vendor_code,s.sub_item)];return `<td class="num"><input class="inp pe-assyov num" data-vc="${esc(v.vendor_code)}" data-si="${esc(s.sub_item)}" type="number" step="1" value="${av==null?'':av}" placeholder="업체별" style="width:96px"></td>`;}).join(''):'<td class="num"><span style="font-size:10px;color:#aab">업체 지정 후</span></td>'}</tr>`).join('')}</tbody></table>`:'';
          const purch=pe.children.filter(x=>x.is_purchase);
          const madeCnt=pe.children.length-purch.length;
          const sag=purch.length?`<table class="tbl" style="font-size:12px;margin:2px 0"><thead><tr><th>사급 부품(매입)</th><th class="num">공통</th>${pe.vends.map(v=>`<th class="num">${esc(v.vendor_name)} 예외</th>`).join('')}</tr></thead><tbody>${purch.map(x=>`<tr><td><b>${esc(x.item_code)}</b> <span class="cap" style="color:#8aa0bd" title="${esc(x.item_name)}">${esc(x.item_name)}</span></td><td class="num"><input class="inp pe-sag num" data-ic="${esc(x.item_code)}" type="number" step="1" value="${x.sagub==null?'':x.sagub}" placeholder="공통" style="width:96px"></td>${pe.vends.map(v=>{const sv=pe.sagubOv[ovk(v.vendor_code,x.item_code)];return `<td class="num"><input class="inp pe-sagov num" data-vc="${esc(v.vendor_code)}" data-ic="${esc(x.item_code)}" type="number" step="1" value="${sv==null?'':sv}" placeholder="공통(${x.sagub==null?'-':won(x.sagub)})" style="width:96px"></td>`;}).join('')}</tr>`).join('')}</tbody></table>`:'';
          body=`${(pe.subs.length||purch.length)?'':'<div class="empty" style="font-size:12px">이 후보는 외주 SUB/매입 사급 부품이 없습니다(단품·제작만 — 매입 마스터/원가 자동).</div>'}
            ${asy}${sag}${madeCnt>0?`<div style="font-size:11px;color:#8aa0bd">※ 제작(가공품) ${madeCnt}건은 원가 자동(입력 대상 아님). 예외 비우면 공통 사용.</div>`:'<div style="font-size:11px;color:#8aa0bd">※ 예외 비우면 공통 사용(COALESCE).</div>'}
            ${pe.msg?`<div style="font-size:12px;color:#c0392b;font-weight:600">${esc(pe.msg)}</div>`:''}
            <div style="margin-top:4px;display:flex;gap:6px"><button class="btn pp-save" data-ri="${rt.route_id}" style="background:#8a6d1c;color:#fff" ${pe.saving?'disabled':''}>💾 계획단가 저장</button><button class="btn ghost pp-cancel">취소</button></div>`;
        }
      }else{
        const asyR=(rt.assy_subs&&rt.assy_subs.length)?rt.assy_subs.map(a=>`<span style="font-size:11px;white-space:nowrap;margin-right:10px">🧩 ${esc(a.sub_name||a.sub_item)} ${(a.overrides&&a.overrides.length)?a.overrides.map(o=>`<b>${esc(o.vendor_name||o.vendor_code)}:${o.assy_price==null?'-':won(o.assy_price)}</b>`).join(' '):'<span style="color:#c9d1dc">미입력</span>'}</span>`).join(''):'';
        const sagR=(rt.sagub_items&&rt.sagub_items.length)?rt.sagub_items.map(si=>`<span style="font-size:11px;white-space:nowrap;margin-right:10px">${esc(si.item_name||si.item_code)} <b>${si.sagub_price==null?'-':won(si.sagub_price)}</b>${ovtxt(si.overrides,'sagub_price')}</span>`).join(''):'';
        body=`<div style="font-size:11px;margin:1px 0"><span style="color:#8a6d1c;font-weight:600">ASSY 매입단가:</span> ${asyR||'<span style="color:#c9d1dc">미입력</span>'}</div>
          <div style="font-size:11px;margin:1px 0"><span style="color:#8a6d1c;font-weight:600">사급 부품가:</span> ${sagR||'<span style="color:#c9d1dc">미입력</span>'}</div>`;
      }
      return `<div style="border:1px solid #ece3c4;border-radius:8px;padding:6px 9px;margin-bottom:6px">
        <div style="display:flex;align-items:center;gap:8px">${badge}<span style="flex:1"></span>
          ${editable?(editing?'':`<button class="btn ghost pp-edit" data-ri="${rt.route_id}" style="font-size:11px;padding:1px 8px;color:#8a6d1c;border-color:#e6d29a">✏ 계획단가 편집</button>`):`<span style="font-size:10px;color:#aab">${rt.route_id>0?'미승인(편집 불가)':'현행 baseline(합성·편집 불가)'}</span>`}</div>
        ${vendHtml}${body}</div>`;
    }).join('');
    return hdr+blocks;
  };
  const draw=()=>{
    const _sc=(()=>{const g=c.querySelector('#pi-list');return g?g.scrollTop:0;})();   // 좌측 스크롤 보존
    const d=st.det;
    c.innerHTML=`
     <div class="page-sub">품번 선택 → <b>거래처별·적용월 단가 이력</b>(시계열, 소급조회의 원장). 원본 <code>PR_M_ITEM_COST</code>(라이브) · 구분 매입/LG판매/판매 · 코드→이름</div>
     <div class="split" style="grid-template-columns:1fr 1.5fr">
       <div>
         <div class="toolbar" style="flex-wrap:wrap;gap:4px"><input class="inp" id="pi-q" value="${esc(st.q)}" placeholder="품번/품명" style="width:130px">
           <select class="inp" id="pi-lg" style="width:auto"><option value="">대분류</option>${st.lgroups.map(o=>`<option value="${esc(o.code)}" ${st.lg===o.code?'selected':''}>${esc(o.nm||o.code)}</option>`).join('')}</select>
           <select class="inp" id="pi-sg" style="width:auto"><option value="">소분류</option>${st.sgroups.map(o=>`<option value="${esc(o.code)}" ${st.sg===o.code?'selected':''}>${esc(o.nm||o.code)}</option>`).join('')}</select>
           <input class="inp" id="pi-cust" list="pi-custdl" autocomplete="off" value="${esc(st.cust)}" placeholder="거래처명/코드" style="width:120px"><datalist id="pi-custdl"></datalist>
           ${st.cust?`<button class="btn ghost" id="pi-custx" title="거래처 필터 해제" style="padding:2px 6px">✖거래처</button>`:''}
           <button class="btn" id="pi-go">🔍</button><span class="rowcount">${won(st.cnt)}건${st.cnt>=1000?' (상한·검색/분류로 좁히세요)':''}</span></div>
         <div class="grid-wrap" id="pi-list" style="max-height:calc(100vh - 300px);overflow:auto"><table class="tbl fit"><thead><tr><th>품번</th><th>품명</th><th>소분류</th><th class="num">단가건</th></tr></thead>
          <tbody>${st.loading?spinRow(4):(st.rows.length?st.rows.map(r=>`<tr class="pi-row ${st.sel===r.ITEM_CODE?'sel':''}" data-cd="${esc(r.ITEM_CODE)}" style="cursor:pointer"><td><b>${esc(r.ITEM_CODE)}</b></td><td class="cap" title="${esc(r.nm)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td><td class="cap" title="${esc(r.spec)}" style="max-width:100px;overflow:hidden;text-overflow:ellipsis">${esc(r.sg_nm||'')}</td><td class="num">${won(r.cnt)}</td></tr>`).join(''):`<tr><td colspan="4" class="empty">품번/품명으로 검색</td></tr>`)}</tbody></table></div>
       </div>
       <div class="panel"><div class="panel-h">단가 이력 ${d?`— ${esc(d.item)} ${esc(d.nm)}`:''}</div>
        <div class="panel-b" style="max-height:calc(100vh - 260px);overflow:auto">${!d?'<div class="empty">좌측에서 품번을 선택하세요.</div>':((d.rows&&d.rows.length?priceHistSections(d.rows):'<div class="empty">단가 이력 없음</div>')+planPriceSection(st.plan))}</div></div>
     </div>`;
    const g=id=>c.querySelector(id);
    g('#pi-go').onclick=()=>{st.q=g('#pi-q').value;st.lg=g('#pi-lg').value;st.sg=g('#pi-sg').value;st.cust=g('#pi-cust').value.trim();load();};
    g('#pi-q').onkeyup=e=>{if(e.key==='Enter')g('#pi-go').click();};
    g('#pi-cust').onkeyup=e=>{if(e.key==='Enter'){st.cust=g('#pi-cust').value.trim();g('#pi-go').click();}};
    g('#pi-lg').onchange=()=>{st.lg=g('#pi-lg').value;load();};
    g('#pi-sg').onchange=()=>{st.sg=g('#pi-sg').value;load();};
    // 거래처 오토컴플리트(디바운스 서버검색 → datalist) + 필터해제
    g('#pi-cust').oninput=e=>{const q=e.target.value.trim();clearTimeout(custT);if(q.length<1)return;
      custT=setTimeout(async()=>{try{const r=await fetch(`${API}/api/item/vendorsearch?q=${encodeURIComponent(q)}`);const vs=(await r.json()).rows||[];
        // ★거래처명 기준 표시(코드는 보조): option value=이름, 라벨에 코드
        const dl=g('#pi-custdl');if(dl)dl.innerHTML=vs.map(x=>`<option value="${esc(x.name)}">${esc(x.name)} (${esc(x.code)})</option>`).join('');}catch(err){}},250);};
    {const cx=g('#pi-custx');if(cx)cx.onclick=()=>{st.cust='';load();};}
    c.querySelectorAll('.pi-row').forEach(tr=>tr.onclick=()=>loadDet(tr.dataset.cd));
    // 계획단가 편집 wiring(정산 이력은 읽기전용 유지, 계획단가=nx만 편집)
    c.querySelectorAll('.pp-edit').forEach(el=>el.onclick=()=>peOpen(+el.dataset.ri));
    {const pc=c.querySelector('.pp-cancel');if(pc)pc.onclick=peClose;
     const ps=c.querySelector('.pp-save');if(ps)ps.onclick=peSave;}
    c.querySelectorAll('.pe-assy').forEach(el=>el.onchange=()=>{if(st.planEdit){const s=st.planEdit.subs.find(x=>x.sub_item===el.dataset.si);if(s)s.assy=(el.value===''?null:el.value);}});
    c.querySelectorAll('.pe-sag').forEach(el=>el.onchange=()=>{if(st.planEdit){const x=st.planEdit.children.find(y=>y.item_code===el.dataset.ic);if(x)x.sagub=(el.value===''?null:el.value);}});
    c.querySelectorAll('.pe-assyov').forEach(el=>el.onchange=()=>{if(st.planEdit)st.planEdit.assyOv[ovk(el.dataset.vc,el.dataset.si)]=(el.value===''?null:el.value);});
    c.querySelectorAll('.pe-sagov').forEach(el=>el.onchange=()=>{if(st.planEdit)st.planEdit.sagubOv[ovk(el.dataset.vc,el.dataset.ic)]=(el.value===''?null:el.value);});
    attachResizers(c);
    const _g=c.querySelector('#pi-list'); if(_g&&_sc) _g.scrollTop=_sc;   // 스크롤 복원
  };
  load();
};
function priceDetail(c,cd){
  const it=DB.priceItems.find(x=>x.cd===cd);
  const buy=DB.priceBuyHist[cd]||[], sale=DB.priceSaleHist[cd]||[];
  const cur=m=>m==='Y'?'<span class="bdg ok">현행</span>':'';
  const buyTbl=buy.length?`<table class="tbl"><thead><tr><th>거래처코드</th><th>거래처명</th><th class="center">통화</th>
     <th class="num">재료비</th><th class="num">가공비</th><th class="num">기타</th><th class="num">매입단가</th><th>적용일</th><th class="center">현행</th></tr></thead>
     <tbody>${buy.map(r=>`<tr class="${r.main==='Y'?'sel':''}"><td>${esc(r.pcd)||'-'}</td><td>${esc(r.pnm)}</td><td class="center">${esc(r.cur)}</td>
       <td class="num">${won(r.mat)}</td><td class="num">${won(r.pcost)}</td><td class="num">${won(r.oth)}</td>
       <td class="num"><b>${won(r.up)}</b></td><td>${esc(r.ymd)}</td><td class="center">${cur(r.main)}</td></tr>`).join('')}</tbody></table>`
     :`<div class="empty">구매단가 없음</div>`;
  const saleTbl=sale.length?`<table class="tbl"><thead><tr><th class="center">구분</th><th>거래처코드</th><th>거래처명</th><th class="center">통화</th>
     <th class="num">판매단가</th><th>적용일</th><th class="center">현행</th></tr></thead>
     <tbody>${sale.map(r=>`<tr class="${r.main==='Y'?'sel':''}"><td class="center">${MKT_NM[r.mkt]||r.mkt||'-'}</td>
       <td>${esc(r.pcd)||'-'}</td><td>${esc(r.pnm)}</td><td class="center">${esc(r.cur)}</td>
       <td class="num"><b>${won(r.up)}</b></td><td>${esc(r.ymd)}</td><td class="center">${cur(r.main)}</td></tr>`).join('')}</tbody></table>`
     :`<div class="empty">판매단가 없음</div>`;
  c.querySelector('#pr-detail').innerHTML=`<div class="panel-h">단가 히스토리 ${tbadge(it.type)}</div><div class="panel-b">
     <div class="detail-title">${esc(it.nm)}</div><div class="detail-code">${esc(it.cd)} · ${esc(it.cat)||'-'} · ${esc(it.uom)}</div>
     <div class="section-t">🛒 구매처별 구매단가 <span class="muted">(${buy.length}건)</span></div>${buyTbl}
     <div class="section-t">💹 매출처별 판매단가 (수출/내수) <span class="muted">(${sale.length}건)</span></div>${saleTbl}</div>`;
}

/* ===== 재고 공용 (엑셀다운로드 / 단계별 그리드) ===== */
function downloadCSV(fname, headers, rows){
  const q=v=>{v=(v==null?'':String(v)); return /[",\n]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v;};
  const csv='﻿'+[headers.join(',')].concat(rows.map(r=>r.map(q).join(','))).join('\r\n');
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8;'}));
  a.download=fname; document.body.appendChild(a); a.click(); a.remove();
}
function stockGrid(c, opt){
  const pool=DB.stock.filter(r=>r.stage===opt.stage);
  const lines= opt.showLine? [...new Set(pool.map(r=>r.loc).filter(Boolean))].sort():[];
  c.innerHTML=`
   <div class="page-title">${opt.title}</div><div class="page-sub">${opt.sub}</div>
   <div class="toolbar">
     <input class="inp" id="q" placeholder="품목코드 / 품명">
     <select class="sel" id="type"><option value="">전체유형</option>${Object.entries(TYPE_NM).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select>
     ${opt.showLine?`<select class="sel" id="line"><option value="">전체라인</option>${lines.map(l=>`<option value="${esc(l)}">${esc(lineName(l))}</option>`).join('')}</select>`:''}
     <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
     <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
   </div>
   <div class="summary-bar" id="sum"></div>
   <div class="grid-wrap" style="max-height:540px"><table class="tbl"><thead><tr>
     <th>품목코드</th><th>품명</th><th>유형</th>${opt.showLine?'<th class="center">라인</th>':''}
     <th class="num">재고수량</th><th class="center">단위</th><th class="num">단가</th><th class="num">재고금액</th><th>최종입고일</th>
   </tr></thead><tbody id="body"></tbody></table></div><div class="rowcount" id="cnt"></div>`;
  let cur=[];
  const render=rows=>{cur=rows;
    c.querySelector('#body').innerHTML=rows.length?rows.map(r=>`<tr>
      <td><b>${esc(r.cd)}</b></td><td>${esc(r.nm)}</td><td>${tbadge(r.type)}</td>
      ${opt.showLine?`<td class="center">${esc(lineName(r.loc))||'-'}</td>`:''}
      <td class="num qty">${won(r.qty)}</td><td class="center">${esc(r.uom)}</td>
      <td class="num">${won(r.cost)}</td><td class="num"><b>${won(r.amt)}</b></td><td>${esc(r.lastin)||'-'}</td></tr>`).join('')
      :`<tr><td colspan="9" class="empty">결과 없음</td></tr>`;
    const qty=rows.reduce((a,b)=>a+(+b.qty||0),0), amt=rows.reduce((a,b)=>a+(+b.amt||0),0);
    c.querySelector('#sum').innerHTML=`<div class="s-item">품목수 <b>${won(rows.length)}</b></div>
      <div class="s-item">재고수량 합계 <b>${won(qty)}</b></div>
      <div class="s-item ${amt<0?'neg':''}">재고금액 합계 <b>${won(amt)} 원</b></div>`;
    c.querySelector('#cnt').textContent=`${rows.length}건 표시 / 대상 ${pool.length}건`;};
  const apply=()=>{const q=c.querySelector('#q').value.trim().toLowerCase(),t=c.querySelector('#type').value,
      ln=opt.showLine?c.querySelector('#line').value:'';
    render(pool.filter(r=>(!t||r.type===t)&&(!ln||r.loc===ln)&&(!q||r.cd.toLowerCase().includes(q)||(r.nm||'').toLowerCase().includes(q))));};
  c.querySelector('#go').onclick=apply;c.querySelector('#q').onkeyup=e=>{if(e.key==='Enter')apply();};
  c.querySelector('#type').onchange=apply; if(opt.showLine)c.querySelector('#line').onchange=apply;
  c.querySelector('#reset').onclick=()=>{c.querySelector('#q').value='';c.querySelector('#type').value='';if(opt.showLine)c.querySelector('#line').value='';apply();};
  c.querySelector('#xls').onclick=()=>downloadCSV(opt.title.replace(/[\s()]/g,'')+'.csv',
     ['품목코드','품명','유형',...(opt.showLine?['라인']:[]),'재고수량','단위','단가','재고금액','최종입고일'],
     cur.map(r=>[r.cd,r.nm,TYPE_NM[r.type]||r.type,...(opt.showLine?[lineName(r.loc)]:[]),r.qty,r.uom,r.cost,r.amt,r.lastin]));
  render(pool);
  enableSort(c,['cd','nm','type',...(opt.showLine?['loc']:[]),'qty','uom','cost','amt','lastin'],()=>cur,render);
}
const _DEMO_unifybom_UNUSED=(c)=>{
  const M={
    part:{code:'AJR75563402',name:'Tube Assembly, Manifold',cust:'LG전자',unit:'EA'},
    subParts:[
      {code:'MJU64794201',name:'Tube Connector',spec:'Ø6.35×0.70×176 CU',sagub:0,qty:1,cost:457,routes:['내부용','명진','미래','태국']},
      {code:'MJU64794202',name:'Tube Connector',spec:'Ø6.35×0.70×178 CU',sagub:0,qty:1,cost:421,routes:['내부용','명진','미래','태국']},
      {code:'MJU64794302',name:'Tube Connector',spec:'Ø9.52×0.70×167 CU',sagub:0,qty:1,cost:637,routes:['내부용','명진','미래','태국']},
      {code:'5210A22409B',name:'Tube,Connector',spec:'Ø9.52×0.70×27 CU',sagub:1,qty:1,cost:121,routes:['내부용','명진','미래','태국']},
      {code:'3H02717A',name:'COUPLING',spec:'Ø15.88×1.00×42 CU',sagub:1,qty:1,cost:458,routes:['내부용','명진','미래','태국']},
      {code:'3A00375E',name:'SOCKET(Ø12.7)',spec:'Ø12.7',sagub:0,qty:1,cost:1059,routes:['태국'],opt:'태국 경로만'},
      {code:'RAC30599327',name:'3% 용접봉',spec:'BCup-3S 2.4*700',sagub:0,qty:0.0015,cost:96600,unit:'KG',routes:['내부용','태국'],opt:'자체·태국'},
      {code:'RAC30599301-1',name:'1% 용접봉',spec:'1.8*3.8*700',sagub:0,qty:0.0048,cost:60000,unit:'KG',routes:['내부용','명진','미래','태국']},
    ],
    kit:[
      {code:'5410A30279K',name:'Insulator',qty:1,cost:97,tag:'키팅'},
      {code:'4930A20053B',name:'Holder,Sensor',qty:1,cost:35,tag:'키팅'},
      {code:'RAC30599301-1',name:'1% 용접봉 (각봉)',qty:0.0048,cost:60000,unit:'KG',tag:'부자재'},
    ],
    profiles:[
      {id:'내부용',name:'내부용',type:'자체생산',vendor:'PNC',vcode:'',partner:'없음',pnc:'절삭·은납·체결·포장',lme:false,pur:null,legacy:'-은납',cls:'self',
       split:[{who:'PNC',pct:100,lab:'절삭·은납·체결·포장'}], scope:['절삭','은납','체결포장']},
      {id:'태국',name:'태국 F&T',type:'매입(수입)',vendor:'FONE THAI',vcode:'2337',partner:'커넥터~은납',pnc:'체결·포장',lme:false,pur:4559,legacy:'-F&T',cls:'buy',active:true,
       split:[{who:'협력사',pct:72,lab:'커넥터~은납'},{who:'PNC',pct:28,lab:'체결·포장'}], scope:['체결포장']},
    ],
    proc:{ // PNC 조립공정 실측(공수) — 그룹별
      은납:[{p:'ACS 너트체결기',st:6},{p:'CAP삽입',st:4}],
      체결포장:[{p:'교정-황동',st:25},{p:'클립',st:4},{p:'원형폼피',st:3.32},{p:'포장1-일반BOX',st:3.34},{p:'품번 라벨부착',st:3}],
      절삭:[{p:'컷팅·면취·딤플·후레아·은납 (커넥터 제작)',st:null}],
    },
    labor:20776,
  };
  const f=n=>(n===''||n==null)?'':Number(n).toLocaleString('ko-KR');
  const clsChip={self:'background:#e8f0f9;color:#2f6db3;border:1px solid #2f6db3',sagub:'background:#f7edd7;color:#b6791b;border:1px solid #b6791b',buy:'background:#e0f1ee;color:#1f8a7a;border:1px solid #1f8a7a'};
  const partsOf=pid=>M.subParts.filter(p=>p.routes.includes(pid));
  const subMatOf=pid=>Math.round(partsOf(pid).reduce((s,p)=>s+p.qty*p.cost,0));
  const subCostOf=P=>P.pur!=null?P.pur:subMatOf(P.id);      // 서브 조달원가: 매입=pur, 자체=재료전개
  const kitMat=Math.round(M.kit.reduce((s,t)=>s+t.qty*t.cost,0));
  const pncST=P=>P.scope.reduce((s,g)=>s+(M.proc[g]||[]).reduce((a,x)=>a+(x.st||0),0),0);
  let pid='태국', pno='AJR75563402', pnm='', bdate='2026-07-19';
  const draw=()=>{
    const P=M.profiles.find(x=>x.id===pid);
    const parts=partsOf(pid);
    const subCost=subCostOf(P);
    const purchased=P.pur!=null;
    const total=subCost+kitMat;                              // (가공비·간접·LME는 별도 표기)
    // BOM 전개
    const rows=[{lv:0,code:M.part.code,name:M.part.name,spec:'완제품',sagub:0,qty:'',dg:'',price:'',amt:total,head:1}];
    rows.push({lv:1,code:'◆ 서브조립',name:'Tube Connector 서브조립',spec:P.vendor,sagub:0,qty:1,
      dg:purchased?(P.type+' · 매입'):'자체 · 공정전개',price:purchased?P.pur:'',amt:subCost,sub:1});
    parts.forEach(p=>rows.push({lv:2,code:p.code,name:p.name,spec:p.spec,sagub:p.sagub,qty:p.qty,
      dg:purchased?(p.sagub?'사급(원소재)':'→ 매입에 포함'):(p.sagub?'사급':(p.unit==='KG'?'부자재':'소재/구매')),
      price:p.cost,amt:Math.round(p.qty*p.cost),muted:purchased&&!p.sagub}));
    M.kit.forEach(t=>rows.push({lv:1,code:t.code,name:t.name,spec:'',sagub:0,qty:t.qty,dg:t.tag,price:t.cost,amt:Math.round(t.qty*t.cost)}));

    c.innerHTML=`
     <div class="page-title">🔀 통합 BOM (${esc(M.part.code)})</div>
     <div class="page-sub"><b>품번 1개</b> + 원가구분(내부용 / 실원가=태국 F&T)으로 전환 · 현재 BOM에 물린 서브(태국 F&T active)와 내부용 대조용 · PARTNER_ERP 실측 단가</div>
     <div class="toolbar">
       <label class="tl">PART-NO</label><input class="inp" id="q_pno" value="${esc(pno)}" style="width:150px">
       <label class="tl">품명</label><input class="inp" id="q_pnm" value="${esc(pnm)}" placeholder="품명 검색" style="width:150px">
       <label class="tl">단가기준일</label><input class="inp" type="date" id="q_bd" value="${esc(bdate)}" style="width:150px">
       <button class="btn" id="q_go">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">단가 기준일 <b>${esc(bdate)}</b> 적용</span></div>
     <div class="summary-bar">
       <div class="s-item"><span>품번</span><b>${esc(M.part.code)}</b></div>
       <div class="s-item"><span>품명</span><b>${esc(M.part.name)}</b></div>
       <div class="s-item"><span>고객</span><b>${esc(M.part.cust)}</b></div>
       <div class="s-item"><span>프로파일</span><b>${M.profiles.length}</b></div>
       <div class="s-item"><span>서브 조달원가</span><b>${f(subCost)} 원</b></div>
     </div>
     <div class="toolbar"><span class="rowcount">선택 <b style="color:var(--brand,#2a6df4)">${esc(P.name)}</b> · 구(舊) <b style="color:var(--danger)">${esc(P.legacy)}</b>${P.active?' · <b style="color:#1f8a7a">현재 BOM active</b>':''} <span style="color:var(--muted)">— 오른쪽 「원가구분·조달처」 표에서 클릭하여 전환</span></span></div>
     <div class="page-sub" style="margin:2px 0 12px;padding:9px 13px;background:#f7f9ff;border:1px solid #dbe4ff;border-radius:7px;display:flex;gap:14px;flex-wrap:wrap;align-items:center">
       <span class="badge" style="${clsChip[P.cls]}">${esc(P.type)}</span>
       <span><b>공급원</b> ${esc(P.vendor)}${P.vcode?` (${esc(P.vcode)})`:''}</span>
       <span><b>협력사 공정</b> ${esc(P.partner)}</span>
       <span><b>PNC 공정</b> ${esc(P.pnc)}</span>
       ${P.sagub?`<span><b>사급</b> ${esc(P.sagub)}</span>`:''}
       <span><b>LME</b> ${P.lme?'<span class="badge" style="background:#f6ede2;color:#b06a2c;border:1px solid #b06a2c">대상</span>':'무관'}</span>
       ${P.pur!=null?`<span><b>매입</b> ${f(P.pur)}원</span>`:'<span><b>자체</b> 공정전개</span>'}</div>

     <div style="display:flex;gap:14px;align-items:flex-start;flex-wrap:wrap">
       <div style="flex:1 1 540px;min-width:0">
         <div style="font-weight:700;margin-bottom:6px">BOM 전개 <span style="color:var(--muted);font-weight:400;font-size:12px">(${esc(P.name)})</span></div>
         <div class="grid-wrap"><table class="tbl fit"><thead><tr><th>레벨</th><th>품번</th><th>품명</th><th>규격</th><th class="center">사급</th><th class="right">소요량</th><th>조달구분</th><th class="right">단가</th><th class="right">금액</th></tr></thead><tbody>
           ${rows.map(r=>`<tr style="${r.head?'background:#eef4ff;font-weight:700':r.sub?'background:#fafbff;font-weight:600':r.muted?'color:#aaa':''}">
             <td class="center">${r.head?'0':r.lv}</td>
             <td style="padding-left:${8+r.lv*16}px;${r.sub?'color:#b06a2c':''}">${esc(r.code)}</td>
             <td>${esc(r.name)}</td><td style="color:var(--muted);font-size:12px">${esc(r.spec)}</td>
             <td class="center">${r.sagub?'<span class="badge" style="background:#f7edd7;color:#b6791b;border:1px solid #b6791b">사급</span>':''}</td>
             <td class="right">${r.qty===''?'':r.qty}</td>
             <td style="font-size:12px;color:${r.muted?'#bbb':'var(--muted)'}">${esc(r.dg)}</td>
             <td class="right">${f(r.price)}</td><td class="right">${f(r.amt)}</td></tr>`).join('')}
         </tbody></table></div>
         <div style="font-weight:700;margin:14px 0 6px">공정 분담 <span style="color:var(--muted);font-weight:400;font-size:12px">(협력사 / PNC)</span></div>
         <div style="display:flex;height:30px;border-radius:6px;overflow:hidden;border:1px solid var(--line)">
           ${P.split.map(s=>`<div style="flex:${s.pct};display:flex;align-items:center;justify-content:center;font-size:11.5px;font-weight:600;color:#fff;background:${s.who==='PNC'?'#b06a2c':'#5b6672'};white-space:nowrap;padding:0 6px">${esc(s.who)} : ${esc(s.lab)}</div>`).join('')}
         </div>
         <div style="font-weight:700;margin:14px 0 6px">PNC 수행공정 <span style="color:var(--muted);font-weight:400;font-size:12px">(조립 공수 실측 · 임율 ${f(M.labor)})</span></div>
         <div class="grid-wrap"><table class="tbl fit"><thead><tr><th>구분</th><th>공정</th><th class="right">공수(ST)</th></tr></thead><tbody>
           ${P.scope.map(g=>(M.proc[g]||[]).map((x,i)=>`<tr><td>${i===0?`<b>${esc(g)}</b>`:''}</td><td>${esc(x.p)}</td><td class="right">${x.st==null?'UPH별도':x.st}</td></tr>`).join('')).join('')}
           <tr style="background:#fafbff;font-weight:700"><td colspan="2">PNC 조립 공수 합</td><td class="right">${pncST(P).toFixed(2)}</td></tr>
         </tbody></table></div>
       </div>

       <div style="flex:0 0 400px;width:400px">
         <div style="font-weight:700;margin-bottom:6px">원가 구성 <span style="color:var(--muted);font-weight:400;font-size:12px">(${esc(P.name)})</span></div>
         <div class="grid-wrap"><table class="tbl fit"><tbody>
           <tr><td>서브 조달원가</td><td class="right">${f(subCost)}${P.pur==null?' <span style="color:#bbb;font-size:11px">재료전개</span>':' <span style="color:#bbb;font-size:11px">매입</span>'}</td></tr>
           <tr><td>키팅·부자재</td><td class="right">${f(kitMat)}</td></tr>
           <tr><td>PNC 가공비</td><td class="right">공수 ${pncST(P).toFixed(2)} × 임율</td></tr>
           <tr><td>LME 차액</td><td class="right">${P.lme?'대상 (LG인증가−협력사가)':'무관'}</td></tr>
           <tr style="background:#eef4ff;font-weight:700"><td>실원가</td><td class="right">재료+가공비+간접+이윤${P.lme?'±LME':''}</td></tr>
         </tbody></table></div>
         <div class="page-sub" style="margin-top:6px">실원가 = 재료비 + 가공비(PNC 담당공정) + 일반관리 + 이윤 ${P.lme?'± LME차액':''} · 손익 = LG단가 − 실원가</div>

         <div style="font-weight:700;margin:14px 0 6px">프로파일 비교</div>
         <div class="grid-wrap"><table class="tbl fit"><thead><tr><th>프로파일</th><th>공급구분</th><th class="center">부품</th><th class="right">서브조달</th><th>LME</th></tr></thead><tbody>
           ${M.profiles.map(p=>{const sc=subCostOf(p);return `<tr style="${pid===p.id?'background:#eef4ff;font-weight:600':''};cursor:pointer" data-cmp="${esc(p.id)}">
             <td>${esc(p.name)} <span style="color:#ccc;font-size:11px">${esc(p.legacy)}</span></td>
             <td><span class="badge" style="${clsChip[p.cls]};font-size:10.5px">${esc(p.type)}</span></td>
             <td class="center">${partsOf(p.id).length}</td>
             <td class="right"><b>${f(sc)}</b>${p.pur==null?'<span style="color:#bbb;font-size:10px"> 전개</span>':''}</td>
             <td>${p.lme?'대상':'무관'}</td></tr>`;}).join('')}
         </tbody></table></div>
         <div class="page-sub" style="margin-top:8px;padding:9px 12px;background:#fff8ec;border:1px solid #f2e2bf;border-radius:6px">
           <b>은납</b>은 형제 경로가 아니라 <b>완제품 최종조립(PNC 자체)</b> — 협력사는 inner 서브(커넥터~은납)를 대고, <b>PNC가 체결·포장</b>. 태국은 은납까지 협력사, 나머지 PNC.</div>
       </div>
     </div>`;
    c.querySelectorAll('[data-cmp]').forEach(tr=>tr.onclick=()=>{pid=tr.dataset.cmp;draw();});
    const go=()=>{const v=(c.querySelector('#q_pno').value||'').trim().toUpperCase();
      pnm=c.querySelector('#q_pnm').value||''; bdate=c.querySelector('#q_bd').value||bdate;
      if(v&&v!=='AJR75563402'){alert('시연 데이터는 AJR75563402만 준비돼 있습니다.\n(다른 품목은 대표 BOM 이관 방식으로 확장 예정)');}
      pno='AJR75563402'; draw();};
    c.querySelector('#q_go').onclick=go;
    c.querySelector('#q_pno').onkeyup=e=>{if(e.key==='Enter')go();};
    c.querySelector('#q_pnm').onkeyup=e=>{if(e.key==='Enter')go();};
  };
  draw();
};
const _C39={"0":"nnnwwnwnn","1":"wnnwnnnnw","2":"nnwwnnnnw","3":"wnwwnnnnn","4":"nnnwwnnnw","5":"wnnwwnnnn","6":"nnwwwnnnn","7":"nnnwnnwnw","8":"wnnwnnwnn","9":"nnwwnnwnn","A":"wnnnnwnnw","B":"nnwnnwnnw","C":"wnwnnwnnn","D":"nnnnwwnnw","E":"wnnnwwnnn","F":"nnwnwwnnn","G":"nnnnnwwnw","H":"wnnnnwwnn","I":"nnwnnwwnn","J":"nnnnwwwnn","K":"wnnnnnnww","L":"nnwnnnnww","M":"wnwnnnnwn","N":"nnnnwnnww","O":"wnnnwnnwn","P":"nnwnwnnwn","Q":"nnnnnnwww","R":"wnnnnnwwn","S":"nnwnnnwwn","T":"nnnnwnwwn","U":"wwnnnnnnw","V":"nwwnnnnnw","W":"wwwnnnnnn","X":"nwnnwnnnw","Y":"wwnnwnnnn","Z":"nwwnwnnnn","-":"nwnnnnwnw",".":"wwnnnnwnn"," ":"nwwnnnwnn","*":"nwnnwnwnn"};
function _barcodeDataURL(text){
  text=String(text||"").toUpperCase().replace(/[^0-9A-Z\-. ]/g,"");
  const data="*"+text+"*",nw=2,wide=5,h=54,gap=nw;
  let total=8;for(const ch of data){const p=_C39[ch]||_C39["*"];for(const e of p)total+=(e==="w"?wide:nw);total+=gap;}
  const cv=document.createElement("canvas");cv.width=Math.ceil(total);cv.height=h+4;
  const x0=cv.getContext("2d");x0.fillStyle="#fff";x0.fillRect(0,0,cv.width,cv.height);x0.fillStyle="#000";
  let x=4;for(const ch of data){const p=_C39[ch]||_C39["*"];for(let i=0;i<9;i++){const w=(p[i]==="w"?wide:nw);if(i%2===0)x0.fillRect(x,2,w,h);x+=w;}x+=gap;}
  return cv.toDataURL();
}

/* ==== 자재 재고 3화면(조정·입고·출고) = 동일 원장(nx.stock_ledger), 백엔드 가드(마감월·FK·재고부족) ==== */
const STOCK_API=API_BASE;
const STOCK_CFG={
  stockadjust:{key:'adjust',ic:'🛠️',nm:'자재개별재고조정',signed:true,
    tags:[['1','불량(−)'],['2','장부수정(±)'],['3','기초재고'],['A','개발불출(−)']],
    sub:'장부수정·불량·기초재고·개발불출 등 개별 재고 증감을 등록합니다. <b>수량은 부호 입력</b>(증가 +, 감소 −). 가드: 마감월 잠금·미등록품목·음수재고 차단.'},
  stockreceipt:{key:'receipt',ic:'📥',nm:'자재입고관리',retn:true,rettags:[['RT','반품(−)']],
    tags:[['9','개별입고'],['S','세트입고'],['C','가공입고'],['G','축관입고'],['H','5팀입고']],
    sub:'가공·세트·축관 등 자재 입고를 등록합니다(＋). 가드: 마감월 잠금·미등록품목 차단.',
    retsub:'입고된 부품을 반품합니다(−). 가드: 반품수량 ≤ 현재고(다음공정 이동분은 이미 재고감소 → 반품 불가, 마이너스 재고 방지).'},
  stockissue:{key:'issue',ic:'📤',nm:'자재출고관리',neg:true,
    tags:[['4','생산사용']],
    sub:'생산사용 등 자재 출고를 등록합니다(−, 수량은 양수 입력). 가드: 마감월 잠금·재고부족 차단.'},
};
const _nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:2});
const _toYMD=v=>v?v.slice(2).replace(/-/g,''):'';        // 2026-07-21 → 260721
const _fmtY=y=>{y=''+(y||'');return y.length>=6?`${y.slice(0,2)}-${y.slice(2,4)}-${y.slice(4,6)}`:y;};
function stockScreen(sid){
  const CFG=STOCK_CFG[sid], KEY=CFG.key;
  const dl=`${sid}-matdl`, cdl=`${sid}-custdl`;
  return (c)=>{
    let q='', rows=[], news=[], editMode=false, loading=false, msg='', itemNames={}, custNames={}, editRowKey=null, retMode=false;
    const curKey=()=>retMode?'return':KEY;                       // 반품모드=return screen(음수·≤현재고 가드)
    const curTags=()=>retMode?CFG.rettags:CFG.tags;
    const rowKey=r=>`${r.MAINT_YMD}|${r.MAINT_SEQ}`;
    // 기본 조회기간: 최근 120일
    const now=new Date(), pad=n=>String(n).padStart(2,'0');
    const iso=d=>`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
    let fromV=iso(new Date(now.getTime()-120*864e5)), toV=iso(now);
    const list=async()=>{loading=true;msg='';draw();
      try{const u=`${STOCK_API}/api/stock/list?screen=${curKey()}&ymd_from=${_toYMD(fromV)}&ymd_to=${_toYMD(toV)}&q=${encodeURIComponent(q)}`;
        const r=await fetch(u);if(!r.ok)throw new Error('HTTP '+r.status);rows=(await r.json()).rows||[];}
      catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';rows=[];}
      loading=false;draw();};
    const addRow=()=>{news.push({MAINT_YMD:toV,MAT_CODE:'',item_name:'',MAINT_TAG:curTags()[0][0],qty:'',CUST_CODE:'',cust_name:'',GAGONG_PROC_CODE:'',REMARKS:''});draw();};
    const save=async()=>{
      if(!news.length){alert('등록할 신규 행이 없습니다. ＋행추가로 입력하세요.');return;}
      const errs=[];news.forEach((n,i)=>{const y=(n.MAINT_YMD||'').trim(),m=(n.MAT_CODE||'').trim(),qn=Number(n.qty||0);
        if(!y)errs.push(`${i+1}행: 일자 필요`);if(!m)errs.push(`${i+1}행: 자도번 필요`);
        if(CFG.signed){if(qn===0)errs.push(`${i+1}행: 조정수량은 0일 수 없습니다(증가 +, 감소 −)`);}
        else if(!(qn>0))errs.push(`${i+1}행: 수량은 0보다 커야 함`);});
      if(errs.length){alert('저장 불가:\n'+errs.join('\n'));return;}
      const body={screen:curKey(),rows:news.map(n=>({MAINT_YMD:_toYMD(n.MAINT_YMD),MAT_CODE:(n.MAT_CODE||'').trim().toUpperCase(),
        MAINT_TAG:n.MAINT_TAG,qty:Number(n.qty),CUST_CODE:(n.CUST_CODE||'').trim()||null,GAGONG_PROC_CODE:(n.GAGONG_PROC_CODE||'').trim()||null,REMARKS:(n.REMARKS||'').trim()||null}))};
      try{const r=await fetch(`${STOCK_API}/api/stock/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        const j=await r.json();if(!j.ok){alert('저장 거부 (백엔드 가드):\n'+(j.errors||[]).join('\n'));return;}
        alert(`저장 완료 — ${j.count}건 등록`);news=[];editMode=false;list();}
      catch(e){alert('저장 실패: '+e.message);}};
    const updateRow=async(r,vals)=>{
      const body={screen:curKey(),MAINT_YMD:r.MAINT_YMD,MAINT_SEQ:r.MAINT_SEQ,...vals};
      try{const rr=await fetch(`${STOCK_API}/api/stock/update`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        const j=await rr.json();if(!j.ok){alert('수정 거부 (백엔드 가드):\n'+(j.errors||[]).join('\n'));return;}
        editRowKey=null;list();}catch(e){alert('수정 실패: '+e.message);}};
    const deleteRow=async r=>{if(!confirm(`이 행을 삭제할까요?\n${r.MAT_CODE} · ${_fmtY(r.MAINT_YMD)} · 수량 ${_nf(r.qty)}`))return;
      try{const rr=await fetch(`${STOCK_API}/api/stock/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({screen:curKey(),MAINT_YMD:r.MAINT_YMD,MAINT_SEQ:r.MAINT_SEQ})});
        const j=await rr.json();if(!j.ok){alert('삭제 거부 (백엔드 가드):\n'+(j.errors||[]).join('\n'));return;}
        list();}catch(e){alert('삭제 실패: '+e.message);}};
    const draw=()=>{
      const totQ=rows.reduce((s,r)=>s+Number(r.qty||0),0);
      const newTbl=editMode?`
        <div class="stk-new">
          <div class="stk-new-h">신규 등록 <span style="font-weight:400;color:var(--muted);font-size:12px">— 저장 시 일자별 채번, 마감월·FK·재고 가드 검증</span></div>
          <table class="tbl stk-tbl"><thead><tr><th>#</th><th>일자</th><th>구분</th><th>자도번</th><th>품명</th><th>수량${CFG.neg?'(출고)':''}</th><th>${retMode?'매입처':'거래처'}</th><th>비고</th><th>삭제</th></tr></thead>
          <tbody>${news.map((n,i)=>`<tr>
            <td class="center mut">${i+1}</td>
            <td><input class="ce sn-date" type="date" data-i="${i}" value="${esc(n.MAINT_YMD)}" style="width:130px"></td>
            <td><select class="ce sn-tag" data-i="${i}">${curTags().map(t=>`<option value="${t[0]}" ${t[0]===n.MAINT_TAG?'selected':''}>${esc(t[1])}</option>`).join('')}</select></td>
            <td><input class="ce sn-mat" list="${dl}" data-i="${i}" value="${esc(n.MAT_CODE)}" placeholder="자도번 검색·선택" autocomplete="off" style="width:130px"></td>
            <td class="bcap sn-nm" style="max-width:170px">${esc(n.item_name||'')}</td>
            <td><input class="ce sn-qty" type="number" step="any" ${CFG.signed?'':'min="0"'} data-i="${i}" value="${n.qty}" placeholder="${CFG.signed?'± 부호':''}" style="width:80px;text-align:right"></td>
            <td><input class="ce sn-cust" list="${cdl}" data-i="${i}" value="${esc(n.cust_name||n.CUST_CODE||'')}" placeholder="거래처명 검색(선택)" autocomplete="off" style="width:120px"></td>
            <td><input class="ce sn-rmk" data-i="${i}" value="${esc(n.REMARKS)}" style="width:120px"></td>
            <td class="center"><span class="stk-del" data-i="${i}" title="행삭제" style="cursor:pointer;color:#c0392b">✖</span></td>
          </tr>`).join('')||`<tr><td colspan="9" class="empty">＋행추가로 신규 등록 행을 추가하세요</td></tr>`}</tbody></table>
        </div>`:'';
      c.innerHTML=`
       <div class="page-title">${retMode?'↩️':CFG.ic} ${esc(CFG.nm)}${retMode?' <span style="color:#c0392b">— 반품 모드</span>':''} <span style="font-size:12px;color:var(--muted);font-weight:400">nx · 백엔드 등록·가드</span></div>
       <div class="page-sub"${retMode?' style="color:#c0392b"':''}>${esc(retMode?CFG.retsub:CFG.sub)}</div>
       <div class="toolbar">
         <label class="tl">기간</label><input class="inp" id="stk-from" type="date" value="${fromV}" style="width:150px">
         <span class="mut">~</span><input class="inp" id="stk-to" type="date" value="${toV}" style="width:150px">
         <label class="tl">자도번/거래처</label><input class="inp" id="stk-q" value="${esc(q)}" placeholder="코드 일부" style="width:150px">
         <button class="btn" id="stk-go">🔍 조회</button>
         ${CFG.retn&&!editMode?`<button class="btn ${retMode?'':'ghost'}" id="stk-ret" style="${retMode?'background:#c0392b;color:#fff;border-color:#c0392b':''}">↩ ${retMode?'입고로 전환':'반품'}</button>`:''}
         ${editMode
           ?`<button class="btn" id="stk-add">＋ ${retMode?'반품행':'행추가'}</button><button class="btn" id="stk-save">💾 저장</button><button class="btn ghost" id="stk-cancel">✖ 취소</button>`
           :`${PERM.canEdit(sid)?`<button class="btn" id="stk-edit">✎ ${retMode?'반품등록/수정':'등록/수정'}</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc(PERM.label())})</span>`}`}
         <button class="btn" id="stk-xls">⬇ 엑셀</button>
         <div class="spacer"></div><span class="rowcount">${rows.length}건 · 수량합 <b>${_nf(totQ)}</b></span>
       </div>
       <datalist id="${dl}"></datalist><datalist id="${cdl}"></datalist>
       ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
       ${newTbl}
       ${loading?`<div class="empty">조회 중…</div>`:`
       <div class="grid-wrap stk-wrap"><table class="tbl stk-tbl"><thead><tr>
         <th>일자</th><th>구분</th><th>자도번</th><th>품명</th><th>규격</th><th>수량</th><th>매입처</th><th>투입공정</th><th>비고</th><th>등록자</th>${editMode?'<th>관리</th>':''}</tr></thead>
       <tbody>${rows.map(r=>{const k=rowKey(r);
         if(editMode&&editRowKey===k)return `<tr class="stk-editing" data-key="${esc(k)}">
           <td class="center">${esc(_fmtY(r.MAINT_YMD))}</td>
           <td><select class="ce re-tag">${curTags().map(t=>`<option value="${t[0]}" ${t[0]===r.MAINT_TAG?'selected':''}>${esc(t[1])}</option>`).join('')}</select></td>
           <td><b>${esc(r.MAT_CODE||'')}</b></td>
           <td class="bcap" title="${esc(r.item_name||'')}">${esc(r.item_name||'')}</td>
           <td class="bcap" title="${esc(r.item_spec||'')}">${esc(r.item_spec||'')}</td>
           <td><input class="ce re-qty" type="number" step="any" ${CFG.signed?'':'min="0"'} value="${CFG.signed?(Number(r.qty)||0):Math.abs(Number(r.qty||0))}" style="width:80px;text-align:right"></td>
           <td><input class="ce re-cust" list="${cdl}" value="${esc(r.cust_name||r.CUST_CODE||'')}" placeholder="거래처명(선택)" autocomplete="off" style="width:120px"></td>
           <td><input class="ce re-proc" value="${esc(r.GAGONG_PROC_CODE||'')}" placeholder="(선택)" style="width:70px"></td>
           <td><input class="ce re-rmk" value="${esc(r.REMARKS||'')}" style="width:120px"></td>
           <td class="center mut">${esc(r.INSERT_USER_ID||'')}</td>
           <td class="center" style="white-space:nowrap"><span class="re-save" title="저장" style="cursor:pointer;color:#2f6db3;font-weight:700">💾</span> <span class="re-cancel" title="취소" style="cursor:pointer;color:#888">✖</span></td></tr>`;
         return `<tr data-key="${esc(k)}">
         <td class="center">${esc(_fmtY(r.MAINT_YMD))}</td>
         <td class="center"><span class="stk-tag">${esc(r.tag_name||r.MAINT_TAG||'')}</span></td>
         <td><b>${esc(r.MAT_CODE||'')}</b></td>
         <td class="bcap" title="${esc(r.item_name||'')}">${esc(r.item_name||'')}</td>
         <td class="bcap" title="${esc(r.item_spec||'')}">${esc(r.item_spec||'')}</td>
         <td class="num ${Number(r.qty)<0?'neg':''}">${_nf(r.qty)}</td>
         <td class="bcap" title="${esc(r.cust_name||r.CUST_CODE||'')}">${esc(r.cust_name||r.CUST_CODE||'')}</td>
         <td class="center mut">${esc(r.GAGONG_PROC_CODE||'')}</td>
         <td class="bcap" title="${esc(r.REMARKS||'')}">${esc(r.REMARKS||'')}</td>
         <td class="center mut">${esc(r.INSERT_USER_ID||'')}</td>${editMode?`<td class="center" style="white-space:nowrap"><span class="rowedit" data-key="${esc(k)}" title="수정" style="cursor:pointer;color:#2f6db3">✎</span> <span class="rowdel" data-key="${esc(k)}" title="삭제" style="cursor:pointer;color:#c0392b">🗑</span></td>`:''}</tr>`;
         }).join('')||`<tr><td colspan="${editMode?11:10}" class="empty">조회 결과 없음 — 기간/조건을 확인하세요</td></tr>`}</tbody></table></div>`}
       <style>
         .stk-wrap{max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px;box-shadow:0 3px 12px rgba(30,45,70,.08)}
         .stk-tbl{font-size:12px}.stk-tbl th,.stk-tbl td{padding:3px 7px;white-space:nowrap}
         .stk-tbl thead th{position:sticky;top:0;background:#f4f7fc;z-index:2}
         .stk-tbl td.bcap{max-width:160px;overflow:hidden;text-overflow:ellipsis}
         .stk-tbl td.mut,.stk-tbl .mut{color:var(--muted)}.stk-tbl td.num{text-align:right;font-variant-numeric:tabular-nums}
         .stk-tbl td.neg{color:#c0392b}
         .stk-tag{display:inline-block;padding:1px 7px;border-radius:10px;background:#eef4ff;color:#2f5aa8;font-size:11px;font-weight:600}
         .stk-new{margin:10px 0;padding:12px 14px;background:#f4fbf6;border:2px solid #1c7c3a;border-radius:10px;box-shadow:0 2px 10px rgba(28,124,58,.15)}
         .stk-new-h{font-weight:800;color:#1c7c3a;font-size:14px;margin-bottom:8px}
         .ce{border:1px solid var(--line);border-radius:4px;padding:2px 5px;font-size:12px}
       </style>`;
      // 핸들러
      const gv=id=>c.querySelector(id);
      // 거래처(매입처) 오토컴플리트: 값=거래처명, 저장시 코드매핑(규칙#21). 미해석시 입력값 그대로.
      let custT=null;
      const custSearch=v=>{clearTimeout(custT);v=(v||'').trim();if(v.length<1)return;
        custT=setTimeout(async()=>{try{const r=await fetch(`${STOCK_API}/api/item/vendorsearch?q=${encodeURIComponent(v)}`);const rr=(await r.json()).rows||[];
          const d=c.querySelector('#'+cdl);if(d)d.innerHTML=rr.map(x=>{custNames[(x.name||'').toLowerCase()]=x.code;return `<option value="${esc(x.name||'')}">${esc(x.code||'')}</option>`;}).join('');}catch(e){}},220);};
      const resolveCust=v=>{v=(v||'').trim();if(!v)return null;const code=custNames[v.toLowerCase()];return code||v;};
      gv('#stk-from').onchange=e=>fromV=e.target.value;
      gv('#stk-to').onchange=e=>toV=e.target.value;
      const qi=gv('#stk-q');qi.oninput=e=>q=e.target.value;qi.onkeyup=e=>{if(e.key==='Enter')list();};
      gv('#stk-go').onclick=list;
      const rb=gv('#stk-ret');if(rb)rb.onclick=()=>{retMode=!retMode;news=[];editMode=false;editRowKey=null;list();};
      const ed=gv('#stk-edit');if(ed)ed.onclick=()=>{editMode=true;if(!news.length)addRow();draw();};
      const cx=gv('#stk-cancel');if(cx)cx.onclick=()=>{editMode=false;news=[];editRowKey=null;draw();};
      const ad=gv('#stk-add');if(ad)ad.onclick=addRow;
      const sv=gv('#stk-save');if(sv)sv.onclick=save;
      gv('#stk-xls').onclick=()=>dlCSV(`${CFG.nm}_${_toYMD(fromV)}_${_toYMD(toV)}.csv`,
        ['일자','구분','자도번','품명','규격','수량','매입처','투입공정','비고','등록자'],
        rows.map(r=>[_fmtY(r.MAINT_YMD),r.tag_name||r.MAINT_TAG,r.MAT_CODE,r.item_name,r.item_spec,r.qty,r.cust_name||r.CUST_CODE,r.GAGONG_PROC_CODE,r.REMARKS,r.INSERT_USER_ID]));
      c.querySelectorAll('.stk-del').forEach(el=>el.onclick=()=>{news.splice(+el.dataset.i,1);draw();});
      c.querySelectorAll('.sn-date').forEach(el=>el.onchange=()=>{news[+el.dataset.i].MAINT_YMD=el.value;});
      c.querySelectorAll('.sn-tag').forEach(el=>el.onchange=()=>{news[+el.dataset.i].MAINT_TAG=el.value;});
      c.querySelectorAll('.sn-qty').forEach(el=>el.oninput=()=>{news[+el.dataset.i].qty=el.value;});
      c.querySelectorAll('.sn-cust').forEach(el=>{
        el.oninput=()=>{const i=+el.dataset.i;news[i].cust_name=el.value;news[i].CUST_CODE=resolveCust(el.value);custSearch(el.value);};
        el.onchange=()=>{const i=+el.dataset.i;news[i].cust_name=el.value;news[i].CUST_CODE=resolveCust(el.value);};});
      c.querySelectorAll('.sn-rmk').forEach(el=>el.oninput=()=>{news[+el.dataset.i].REMARKS=el.value;});
      let matT=null;
      c.querySelectorAll('.sn-mat').forEach(el=>{
        el.oninput=()=>{const i=+el.dataset.i,v=el.value.trim();news[i].MAT_CODE=v.toUpperCase();
          if(itemNames[v.toUpperCase()]!==undefined){news[i].item_name=itemNames[v.toUpperCase()];const tr=el.closest('tr');if(tr&&tr.querySelector('.sn-nm'))tr.querySelector('.sn-nm').textContent=itemNames[v.toUpperCase()];}
          clearTimeout(matT);if(v.length<2)return;
          matT=setTimeout(async()=>{try{const r=await fetch(`${STOCK_API}/api/bom/search?q=${encodeURIComponent(v)}&all_active=1`);const rr=(await r.json()).rows||[];
            const d=c.querySelector('#'+dl);if(d)d.innerHTML=rr.map(x=>{itemNames[x.item]=x.name||'';return `<option value="${esc(x.item)}">${esc(x.name||'')}</option>`;}).join('');}catch(e){}},250);};
        el.onchange=()=>{const i=+el.dataset.i,code=el.value.trim().toUpperCase();news[i].MAT_CODE=code;
          if(itemNames[code]!==undefined){news[i].item_name=itemNames[code];const tr=el.closest('tr');if(tr&&tr.querySelector('.sn-nm'))tr.querySelector('.sn-nm').textContent=itemNames[code];}};
      });
      // 기존행 인라인 수정·삭제
      c.querySelectorAll('.rowedit').forEach(el=>el.onclick=()=>{editRowKey=el.dataset.key;draw();});
      c.querySelectorAll('.rowdel').forEach(el=>el.onclick=()=>{const r=rows.find(x=>rowKey(x)===el.dataset.key);if(r)deleteRow(r);});
      const rec=c.querySelector('.re-cust');if(rec)rec.oninput=()=>custSearch(rec.value);
      const rc=c.querySelector('.re-cancel');if(rc)rc.onclick=()=>{editRowKey=null;draw();};
      const rs=c.querySelector('.re-save');if(rs)rs.onclick=()=>{const r=rows.find(x=>rowKey(x)===editRowKey);if(!r)return;
        const g=s=>c.querySelector('.stk-editing '+s);
        const qv=Number(g('.re-qty').value);
        if(CFG.signed){if(qv===0){alert('조정수량은 0일 수 없습니다(증가 +, 감소 −).');return;}}
        else if(!(qv>0)){alert('수량은 0보다 커야 합니다.');return;}
        updateRow(r,{MAINT_TAG:g('.re-tag').value,qty:qv,CUST_CODE:resolveCust(g('.re-cust').value),
          GAGONG_PROC_CODE:g('.re-proc').value.trim()||null,REMARKS:g('.re-rmk').value.trim()||null});};
    };
    list();
  };
}
Object.keys(STOCK_CFG).forEach(id=>SCREEN[id]=stockScreen(id));

/* ==== 자재출고관리 (구매/자재, 레거시 w_pu_stock_150 동일 조회) — PU_T_STOCK_MAINT TAG='B' 라이브 ==== */
/* 레거시 13컬럼(출고일자/SEQ/FROM파트창고/P·N/TO창고구분/TO파트창고/자도번/출고수량/출고단가/출고금액/비고/작업자/작업일시).
   서버 집계(건수·수량합)로 500 cap 부분합 문제 제거. 라이브 PARTNER_ERP 읽기전용(사용자 대조용). */

/* ==== 매출마감처리 (w_pu_sale_020 재설계) — 협력사 매출 업체별 마감·조정·사유 ==== */
const _mkMagam=(CFG)=>(c)=>{
  const API=API_BASE;
  const CT=DB.custTypeNames||{};
  const ctN=t=>CT[(''+t).trim()]||(''+t).trim()||'';
  const ymToInput=y=>{y=(''+(y||'')).trim();return y.length>=4?`20${y.slice(0,2)}-${y.slice(2,4)}`:'';};
  const inYm=v=>(''+(v||'')).slice(2).replace('-','');
  const canW=(typeof PERM!=='undefined')?PERM.canEdit(CFG.base):true;   // 수정권한 게이트(규칙#16)
  let ym='', rows=[], loading=false, msg='', reasons=[], q='', wmap={}, realRaw=25000, sagubRaw=20000;
  // 모달 상태
  let mc=null, detail=null, mLoading=false, mClosed=false, pEdit={}, dEdit={}, amtAdjs=[], expanded=new Set();
  const dkey=(mat,d)=>mat+'|'+d;
  const ymd6=d=>(''+ym).slice(0,4)+String(d).padStart(2,'0');
  const num=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:2});
  const won0=n=>Math.round(Number(n||0)).toLocaleString('ko-KR');

  const load=async(y)=>{loading=true;msg='';draw();
    try{const r=await fetch(`${API}/api/${CFG.base}/list?ym=${encodeURIComponent(y||'')}`);if(!r.ok)throw new Error('HTTP '+r.status);
      const j=await r.json();rows=j.rows||[];ym=j.ym||y||'';
      if(CFG.weight){try{const rw=await fetch(`${API}/api/${CFG.base}/weight_quote?ym=${encodeURIComponent(ym)}`);const jw=await rw.json();wmap={};(jw.rows||[]).forEach(w=>{wmap[w.cc]={raw_out:w.raw_out,raw_in:w.raw_in,raw_diff:w.raw_diff,raw_amt:w.settle_amt,weld_out:w.weld_out,weld_in:w.weld_in,weld_diff:w.weld_diff,weld_amt:w.weld_amt,specs:w.specs,unmapped_out:w.unmapped_out};});}catch(e){wmap={};}}}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';rows=[];}
    loading=false;draw();};
  const ensureReasons=async()=>{if(reasons.length)return;try{const r=await fetch(`${API}/api/salemagam/reasons`);reasons=(await r.json()).rows||[];}catch(e){}};

  const filt=()=>{const k=q.trim().toLowerCase();return rows.filter(r=>!k||(''+r.cc).toLowerCase().includes(k)||(''+r.nm).toLowerCase().includes(k)||(''+r.chg).toLowerCase().includes(k));};

  const draw=()=>{
    const cur=filt();
    const tAmt=cur.reduce((a,b)=>a+(+b.amt||0),0), tFin=cur.reduce((a,b)=>a+(+b.final_amt||0),0), tAdj=cur.reduce((a,b)=>a+(+b.adj_amt||0),0);
    const nClosed=cur.filter(r=>r.close_flag).length;
    const wTot=cur.reduce((a,b)=>{const w=wmap[b.cc]||{};a.out+=+w.raw_out||0;a.in+=+w.raw_in||0;a.diff+=+w.raw_diff||0;a.amt+=+w.raw_amt||0;a.wo+=+w.weld_out||0;a.wi+=+w.weld_in||0;a.wd+=+w.weld_diff||0;a.wa+=+w.weld_amt||0;return a;},{out:0,in:0,diff:0,amt:0,wo:0,wi:0,wd:0,wa:0});
    const _n=v=>(v!=null?num(v):''),_w=v=>(v!=null?won0(v):'');
    // 중량 6컬럼: 원소재(출고·소요·차액) + 용접봉(출고·소요·차액, 빈칸)
    const wc=(cc)=>{const w=wmap[cc]||{};
      return '<td class="num wcol">'+_n(w.raw_out)+'</td><td class="num wcol">'+_n(w.raw_in)+'</td><td class="num wcol '+(w.raw_diff<0?'neg':'')+'">'+_n(w.raw_diff)+'</td>'+
        '<td class="num wcol2">'+_n(w.weld_out)+'</td><td class="num wcol2">'+_n(w.weld_in)+'</td><td class="num wcol2 '+((w.weld_diff||0)<0?'neg':'')+'">'+_n(w.weld_diff)+'</td>';};
    // 조정 3컬럼: 단가조정 · 원소재정산 · 용접봉정산
    const spTip=(w)=>((w.specs||[]).slice(0,12).map(s=>`${s.mat} Φ${s.od}: 재고 ${num(s.diff)}kg ×(${won0((s.spot||0)-(s.sagub||0))}) = ${won0(s.amt)}`).join('&#10;'))||'';
    const ac=(r)=>{const w=wmap[r.cc]||{};
      return '<td class="num acol '+(r.adj_amt<0?'neg':'')+'">'+(r.adj_amt?won0(r.adj_amt):'')+'</td>'+
        '<td class="num acol '+((w.raw_amt||0)<0?'neg':'')+'" title="'+spTip(w)+'">'+_w(w.raw_amt)+'</td>'+
        '<td class="num acol '+((w.weld_amt||0)<0?'neg':'')+'">'+(w.weld_amt?won0(w.weld_amt):'')+'</td>';};
    const finw=(r)=>(+r.final_amt||0)+((wmap[r.cc]||{}).raw_amt||0)+((wmap[r.cc]||{}).weld_amt||0);
    const NC=CFG.weight?18:10, amtl=CFG.amtlbl;
    const THEAD=CFG.weight?`<thead>
       <tr>
         <th rowspan="2">코드</th><th rowspan="2">거래처명</th><th rowspan="2">담당자</th><th rowspan="2">분류</th>
         <th rowspan="2" class="num">수량</th><th rowspan="2" class="num">${amtl}</th>
         <th colspan="3" class="center wcol">원소재 <small>kg</small></th>
         <th colspan="3" class="center wcol2">용접봉 <small>kg</small></th>
         <th colspan="3" class="center acol">조정 <small>원</small></th>
         <th rowspan="2" class="num">최종금액</th>
         <th rowspan="2" class="center">상태</th><th rowspan="2" class="center">처리</th>
       </tr>
       <tr>
         <th class="num wcol">출고</th><th class="num wcol">소요</th><th class="num wcol">차액</th>
         <th class="num wcol2">출고</th><th class="num wcol2">소요</th><th class="num wcol2">차액</th>
         <th class="num acol">단가조정</th><th class="num acol">원소재정산</th><th class="num acol">용접봉정산</th>
       </tr></thead>`:`<thead><tr>
         <th>코드</th><th>거래처명</th><th>담당자</th><th>분류</th><th class="num">수량</th><th class="num">${amtl}</th><th class="num">조정</th><th class="num">최종금액</th><th class="center">상태</th><th class="center">처리</th>
       </tr></thead>`;
    const rowMid=(r)=>CFG.weight?`${wc(r.cc)}${ac(r)}<td class="num"><b>${won0(finw(r))}</b></td>`:`<td class="num ${r.adj_amt<0?'neg':''}">${r.adj_amt?won0(r.adj_amt):''}</td><td class="num"><b>${won0(r.final_amt)}</b></td>`;
    const gtMid=CFG.weight?`<td class="num">${num(wTot.out)}</td><td class="num">${num(wTot.in)}</td><td class="num ${wTot.diff<0?'neg':''}">${num(wTot.diff)}</td><td class="num wcol2">${num(wTot.wo)}</td><td class="num wcol2">${num(wTot.wi)}</td><td class="num wcol2 ${wTot.wd<0?'neg':''}">${num(wTot.wd)}</td><td class="num">${won0(tAdj)}</td><td class="num ${wTot.amt<0?'neg':''}"><b>${won0(wTot.amt)}</b></td><td class="num acol ${wTot.wa<0?'neg':''}">${wTot.wa?won0(wTot.wa):''}</td><td class="num"><b>${won0(tFin+wTot.amt+wTot.wa)}</b></td>`:`<td class="num">${won0(tAdj)}</td><td class="num"><b>${won0(tFin)}</b></td>`;
    c.innerHTML=`
     <div class="page-title">${CFG.title} <span style="font-size:12px;color:var(--muted);font-weight:400">${CFG.sub} · 거래처별 마감 · nx 저장</span></div>
     <div class="page-sub">거래처별 ${CFG.verb} 집계 → [마감]에서 품목×일자·단가변경·총액조정·사유 입력 후 확정. 원본 <code>${CFG.src}</code> · 🔴 라이브 마감기준 ${esc(ymToInput(ym)||'-')}</div>
     ${CFG.weight?`<div class="page-sub" style="color:#3a6ea5">⚖️ LME 중량정산(견적기준): [출고(tag5) − 견적소요] × (현물가 − 사급가). <b>원소재</b>=규격(재질·외경)별 nx.price_metal · <b>용접봉</b>=1% 단일단가(현물 62,700 / 사급 21,100). 협력사(수테크=소요만). 원소재정산 셀 툴팁=규격내역.</div>`:''}
     <div class="toolbar">
       <label class="tl">마감년월</label><input type="month" class="inp" id="sm-ym" value="${esc(ymToInput(ym))}" style="min-width:120px">
       <label class="tl">거래처</label><input class="inp" id="sm-q" value="${esc(q)}" placeholder="코드/거래처명/담당자" style="width:180px">
       <button class="btn" id="sm-go">🔍 조회</button>
       <div class="spacer"></div>
       <span class="rowcount">${cur.length}업체 · 마감 ${nClosed}/${cur.length} · 금액 <b>${won0(tAmt)}</b> → 최종 <b>${won0(tFin)}</b>${tAdj?` (조정 ${won0(tAdj)})`:''}</span>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="grid-wrap sm-wrap"><table class="tbl sm-tbl">${THEAD}
     <tbody>${loading?spinRow(NC):(cur.length?cur.map(r=>`<tr class="${r.close_flag?'sm-closed':''}">
       <td><b>${esc(r.cc)}</b></td><td class="bcap" title="${esc(r.nm)}">${esc(r.nm)}</td>
       <td class="center">${esc(r.chg)||'-'}</td><td>${esc(ctN(r.ct))}</td>
       <td class="num">${num(r.qty)}</td><td class="num">${won0(r.amt)}</td>
       ${rowMid(r)}
       <td class="center">${r.close_flag?'<span class="sm-badge on">🔒 마감</span>':'<span class="sm-badge">미마감</span>'}</td>
       <td class="center" style="white-space:nowrap">
         <button class="btn sm-mini sm-open" data-cc="${esc(r.cc)}" data-nm="${esc(r.nm)}">${(r.close_flag||!canW)?'상세':'✎ 마감'}</button>
         <button class="btn sm-mini ghost" title="계산서 발행(추후 구현)" disabled>🧾 계산서</button>
       </td></tr>`).join('')+`<tr class="grandtot"><td colspan="4" class="right">총계 (${cur.length}업체)</td><td class="num">${num(cur.reduce((a,b)=>a+(+b.qty||0),0))}</td><td class="num">${won0(tAmt)}</td>${gtMid}<td colspan="2"></td></tr>`:`<tr><td colspan="${NC}" class="empty">해당 마감월 ${CFG.verb} 없음</td></tr>`)}</tbody></table></div>
     <div id="sm-modal"></div>
     <style>
       .sm-wrap{max-height:calc(100vh - 260px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px;box-shadow:0 3px 12px rgba(30,45,70,.08)}
       .sm-tbl{font-size:11.5px;width:100%;table-layout:auto}.sm-tbl th,.sm-tbl td{padding:3px 5px;white-space:nowrap}
       .sm-tbl thead th{position:sticky;top:0;background:#f4f7fc;z-index:2}.sm-tbl thead tr:nth-child(2) th{top:26px}.sm-tbl td.num{text-align:right;font-variant-numeric:tabular-nums}
       .sm-tbl td.bcap{max-width:150px;overflow:hidden;text-overflow:ellipsis}.sm-tbl td.neg{color:#c0392b}.sm-tbl .center{text-align:center}
       .sm-tbl tr.sm-closed{background:#f3f8f3}
       .sm-tbl .wcol{background:#f2f8ff}.sm-tbl th.wcol{background:#e6f1ff}.sm-tbl .wcol2{background:#f2f9f4;color:#2a6b45}.sm-tbl th.wcol2{background:#e0f0e6;color:#2a6b45}
       .sm-tbl .acol{background:#fff9ec}.sm-tbl th.acol{background:#fdf2d6}
       .sm-tbl small{font-weight:400;color:#8aa0bd;font-size:9.5px}.sm-tbl tr.grandtot td{font-weight:700}.sm-tbl tr.grandtot .wcol,.sm-tbl tr.grandtot .wcol2{background:#eaf1fb}.sm-tbl tr.grandtot .acol{background:#fbf3df}
       .sm-badge{font-size:11px;padding:1px 8px;border-radius:10px;background:#eee;color:#777}.sm-badge.on{background:#e5f3e8;color:#2e7d32;font-weight:700}
       .sm-mini{padding:2px 8px;font-size:11px}
       .sm-ov{position:fixed;inset:0;background:rgba(20,30,50,.45);z-index:9998;display:flex;align-items:center;justify-content:center}
       .sm-dlg{background:#fff;width:min(1180px,96vw);max-height:92vh;border-radius:12px;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 12px 40px rgba(0,0,0,.3)}
       .sm-dlg-h{padding:12px 18px;background:linear-gradient(90deg,#1c47a0,#2f6db3);color:#fff;display:flex;align-items:center;gap:12px}
       .sm-dlg-h .x{margin-left:auto;cursor:pointer;font-size:20px;opacity:.9}
       .sm-dlg-b{padding:14px 18px;overflow:auto;flex:1}
       .sm-dlg-f{padding:11px 18px;border-top:1px solid var(--line);display:flex;align-items:center;gap:10px;background:#fafcff}
       .sm-it{font-size:12px;width:100%}.sm-it th,.sm-it td{padding:3px 7px;border-bottom:1px solid var(--line);white-space:nowrap}.sm-it th{background:#f4f7fc;text-align:right}.sm-it th:nth-child(-n+3){text-align:left}
       .sm-it td.num{text-align:right;font-variant-numeric:tabular-nums}.sm-it input{width:90px;text-align:right;border:1px solid var(--line);border-radius:4px;padding:2px 5px}
       .sm-it tr.chg input{border-color:#2f6db3;background:#eef4ff;font-weight:700}.sm-it td.dpos{color:#1f8a5a}.sm-it td.dneg{color:#c0392b}
       .sm-adj{margin-top:14px;border:1px solid #cfe0ff;border-radius:8px;padding:10px 12px;background:#fbfdff}
       .sm-adj-row{display:flex;gap:8px;align-items:center;margin:6px 0;flex-wrap:wrap}
       .sm-adj-row input[type=number]{width:120px;text-align:right}.sm-adj-row .rsel{min-width:150px}.sm-adj-row .rdet{flex:1;min-width:160px}
       .sm-sum{display:flex;gap:18px;font-size:13px;margin-left:auto}.sm-sum b{font-size:15px}
       .sm-warn{color:#c0392b;font-size:12px}
     </style>`;
    c.querySelector('#sm-ym').onchange=e=>{load(inYm(e.target.value));};
    const qi=c.querySelector('#sm-q');qi.oninput=e=>{q=e.target.value;};qi.onkeyup=e=>{if(e.key==='Enter')draw();};
    c.querySelector('#sm-go').onclick=()=>draw();
    c.querySelectorAll('.sm-open').forEach(b=>b.onclick=()=>openModal(b.dataset.cc,b.dataset.nm));
    if(mc)drawModal();
  };

  const openModal=async(cc,nm)=>{mc={cc,nm};detail=null;pEdit={};dEdit={};amtAdjs=[];expanded=new Set();mLoading=true;await ensureReasons();drawModal();
    try{const r=await fetch(`${API}/api/${CFG.base}/detail?ym=${encodeURIComponent(ym)}&cc=${encodeURIComponent(cc)}`);if(!r.ok)throw new Error('HTTP '+r.status);
      detail=await r.json();mClosed=!!detail.close_flag;
      (detail.adjustments||[]).forEach(a=>{
        if(a.adj_type==='AMT_UP'||a.adj_type==='AMT_DN'||a.adj_type==='ITEM_ADJ'){amtAdjs.push({amt:a.delta_amt,rc:a.reason_code||'',rd:a.reason_detail||''});}
        else if(a.scope==='DATE'&&a.mat_code&&a.target_ymd){const d=+(''+a.target_ymd).slice(4,6);expanded.add(a.mat_code);
          dEdit[dkey(a.mat_code,d)]={nc:(a.new_cost!=null?a.new_cost:''),nq:(a.new_qty!=null?a.new_qty:''),rc:a.reason_code||'',rd:a.reason_detail||''};}
        else if(a.mat_code){pEdit[a.mat_code]={nc:(a.new_cost!=null?a.new_cost:''),rc:a.reason_code||'',rd:a.reason_detail||''};}});}
    catch(e){detail=null;}
    mLoading=false;drawModal();};
  const closeModal=()=>{mc=null;detail=null;const m=c.querySelector('#sm-modal');if(m)m.innerHTML='';};

  // 일자별 유효단가/수량(날짜조정>품목단가>원본), 조정합 계산
  const effDay=(it,bd)=>{const de=dEdit[dkey(it.mat,bd.d)];let ec=+bd.cost, eq=+bd.qty;
    if(de){if(de.nc!=null&&de.nc!=='')ec=+de.nc;}
    else{const pe=pEdit[it.mat];if(pe&&pe.nc!=null&&pe.nc!=='')ec=+pe.nc;}
    return {ec,eq,delta:ec*eq-(+bd.cost)*(+bd.qty)};};
  const calc=()=>{const items=(detail&&detail.items)||[];let pd=0;
    items.forEach(it=>(it.byday||[]).forEach(bd=>{pd+=effDay(it,bd).delta;}));
    const ad=amtAdjs.reduce((a,b)=>a+(+b.amt||0),0);
    const base=items.reduce((a,b)=>a+(+b.amt||0),0);
    return {base,pd,ad,adj:pd+ad,final:base+pd+ad};};

  const drawModal=()=>{
    const m=c.querySelector('#sm-modal');if(!m)return;
    if(!mc){m.innerHTML='';return;}
    const rsOpt=(sel)=>`<option value="">사유 선택</option>`+reasons.map(r=>`<option value="${esc(r.code)}" ${r.code===sel?'selected':''}>${esc(r.name)}</option>`).join('');
    if(mLoading||!detail){m.innerHTML=`<div class="sm-ov"><div class="sm-dlg"><div class="sm-dlg-h"><b>${esc(mc.nm)}</b> 마감상세 <span class="x" id="sm-x">✖</span></div><div class="sm-dlg-b"><div class="empty">${SPIN}불러오는 중…</div></div></div></div>`;
      const x=m.querySelector('#sm-x');if(x)x.onclick=closeModal;return;}
    const items=detail.items||[];
    const s=calc();
    const mmdd=d=>String(d).padStart(2,'0');
    const rdis=mClosed?'disabled':'';
    const itemRows=items.map(it=>{const pe=pEdit[it.mat]||{};const nc=(pe.nc!=null&&pe.nc!=='')?+pe.nc:'';
      const idelta=(it.byday||[]).reduce((a,bd)=>a+effDay(it,bd).delta,0);const exp=expanded.has(it.mat);
      let html=`<tr class="${idelta?'chg':''}"><td><span class="sm-exp" data-mat="${esc(it.mat)}" style="cursor:pointer;color:#2f6db3;font-weight:700">${exp?'▾':'▸'}</span> <b>${esc(it.mat)}</b></td>
        <td class="bcap" title="${esc(it.nm)}" style="max-width:140px;overflow:hidden;text-overflow:ellipsis">${esc(it.nm)}</td><td class="center">${esc(it.unit)||''}</td>
        <td class="num">${num(it.qty)}</td><td class="num">${num(it.cost)}</td>
        <td class="num"><input class="sm-pc" data-mat="${esc(it.mat)}" type="number" step="any" value="${nc}" placeholder="${num(it.cost)}" ${rdis}></td>
        <td class="num ${idelta>0?'dpos':idelta<0?'dneg':''}">${idelta?won0(idelta):''}</td><td class="num">${won0(it.amt)}</td></tr>`;
      if(exp)(it.byday||[]).forEach(bd=>{const de=dEdit[dkey(it.mat,bd.d)]||{};const e=effDay(it,bd);
        html+=`<tr class="sm-day"><td style="padding-left:24px" class="mut">└ ${mmdd(bd.d)}일</td><td class="mut">일자 매출</td><td></td>
          <td class="num mut">${num(bd.qty)}</td>
          <td class="num"><input class="sm-dc" data-mat="${esc(it.mat)}" data-d="${bd.d}" type="number" step="any" value="${(de.nc!=null&&de.nc!=='')?de.nc:''}" placeholder="${num(bd.cost)}" style="width:76px" ${rdis}></td>
          <td></td><td class="num ${e.delta>0?'dpos':e.delta<0?'dneg':''}">${e.delta?won0(e.delta):''}</td><td class="num mut">${won0(bd.amt)}</td></tr>`;});
      return html;}).join('');
    let adjRows='';
    items.forEach(it=>{const pe=pEdit[it.mat];
      if(pe&&pe.nc!=null&&pe.nc!==''&&+pe.nc!==+it.cost){const dd=(it.byday||[]).reduce((a,bd)=>a+(dEdit[dkey(it.mat,bd.d)]?0:(+pe.nc-+bd.cost)*(+bd.qty)),0);
        if(dd!==0)adjRows+=`<div class="sm-adj-row"><span style="min-width:180px"><b>품목단가</b> ${esc(it.mat)} ${num(it.cost)}→${num(pe.nc)} <span class="mut">(${won0(dd)})</span></span>
          <select class="sel rsel sm-prc" data-mat="${esc(it.mat)}" ${rdis}>${rsOpt(pe.rc)}</select>
          <input class="inp rdet sm-prd" data-mat="${esc(it.mat)}" value="${esc(pe.rd||'')}" placeholder="세부 사유(선택)" ${rdis}></div>`;}
      (it.byday||[]).forEach(bd=>{const de=dEdit[dkey(it.mat,bd.d)];if(!de)return;const ncC=de.nc!=null&&de.nc!==''&&+de.nc!==+bd.cost;if(!ncC)return;const e=effDay(it,bd);
        const lbl=`단가 ${num(bd.cost)}→${num(de.nc)}`;
        adjRows+=`<div class="sm-adj-row"><span style="min-width:180px"><b>${mmdd(bd.d)}일</b> ${esc(it.mat)} ${lbl} <span class="mut">(${won0(e.delta)})</span></span>
          <select class="sel rsel sm-drc" data-mat="${esc(it.mat)}" data-d="${bd.d}" ${rdis}>${rsOpt(de.rc)}</select>
          <input class="inp rdet sm-drd" data-mat="${esc(it.mat)}" data-d="${bd.d}" value="${esc(de.rd||'')}" placeholder="세부 사유(선택)" ${rdis}></div>`;});});
    const amtAdjRows=amtAdjs.map((a,i)=>`<div class="sm-adj-row"><input type="number" step="any" class="inp sm-aamt" data-i="${i}" value="${a.amt}" placeholder="증액(+)/차감(-)" ${rdis}>
        <select class="sel rsel sm-arc" data-i="${i}" ${rdis}>${rsOpt(a.rc)}</select>
        <input class="inp rdet sm-ard" data-i="${i}" value="${esc(a.rd||'')}" placeholder="세부 사유(선택)" ${rdis}>${mClosed?'':`<span class="sm-adel" data-i="${i}" style="cursor:pointer;color:#c0392b">✖</span>`}</div>`).join('');
    m.innerHTML=`<div class="sm-ov"><div class="sm-dlg">
      <div class="sm-dlg-h"><b>${esc(mc.nm)}</b> <span style="opacity:.85">(${esc(mc.cc)}) · 마감 ${esc(ymToInput(ym))}</span>${mClosed?'<span class="sm-badge on" style="background:#fff;color:#2e7d32">🔒 마감완료</span>':''}<span class="x" id="sm-x">✖</span></div>
      <div class="sm-dlg-b">
        <div style="font-weight:700;margin-bottom:6px">품목별 매출 <span style="color:var(--muted);font-weight:400;font-size:12px">(${items.length}품목 · ▸펼치면 일자별 단가·수량 수정)</span></div>
        <div style="max-height:40vh;overflow:auto;border:1px solid var(--line);border-radius:6px"><table class="sm-it"><thead><tr><th>품번</th><th>품명</th><th class="center">단위</th><th>수량</th><th>현단가</th><th>변경단가</th><th>금액변동</th><th>매출금액</th></tr></thead><tbody>${itemRows||`<tr><td colspan="8" class="empty">품목 없음</td></tr>`}</tbody></table></div>
        <div class="sm-adj">
          <div style="font-weight:700;margin-bottom:4px">조정내역 <span style="color:var(--muted);font-weight:400;font-size:12px">(품목단가/일자별 단가·수량/총액 증감 · 사유 필수)</span></div>
          ${adjRows||'<div class="mut" style="font-size:12px">단가·수량을 바꾸면 여기에 사유 입력란이 생깁니다.</div>'}
          ${amtAdjRows}
          ${(mClosed||!canW)?'':'<button class="btn sm-mini" id="sm-add-amt">＋ 총액 증감/차감(품목무관)</button>'}
        </div>
      </div>
      <div class="sm-dlg-f">
        <div class="sm-sum"><span>원매출 <b>${won0(s.base)}</b></span>
          <span>단가·수량 <b style="${s.pd<0?'color:#c0392b':''}">${s.pd?won0(s.pd):'0'}</b></span>
          <span>총액조정 <b style="${s.ad<0?'color:#c0392b':''}">${s.ad?won0(s.ad):'0'}</b></span>
          <span>최종금액 <b style="color:#1c47a0">${won0(s.final)}</b></span></div>
        <div class="spacer"></div>
        ${!canW?`<span style="color:#c0392b;font-size:12px;margin-right:auto">🔒 수정권한 없음 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</span><button class="btn" id="sm-close2">닫기</button>`
          :mClosed?`<button class="btn ghost" id="sm-reopen">🔓 마감취소</button><button class="btn" id="sm-close2">닫기</button>`
          :`<button class="btn ghost" id="sm-save">💾 조정저장</button><button class="btn" id="sm-confirm" style="background:#1c7a37;color:#fff">🔒 마감확정</button><button class="btn ghost" id="sm-close2">닫기</button>`}
      </div>
    </div></div>`;
    m.querySelector('#sm-x').onclick=closeModal;
    const c2=m.querySelector('#sm-close2');if(c2)c2.onclick=closeModal;
    m.querySelectorAll('.sm-exp').forEach(el=>el.onclick=()=>{const mat=el.dataset.mat;if(expanded.has(mat))expanded.delete(mat);else expanded.add(mat);drawModal();});
    m.querySelectorAll('.sm-pc').forEach(el=>el.onchange=()=>{const mat=el.dataset.mat,v=el.value.trim();
      if(v===''){if(pEdit[mat]){delete pEdit[mat].nc;if(!pEdit[mat].nc)delete pEdit[mat];}}else{pEdit[mat]=Object.assign(pEdit[mat]||{rc:'',rd:''},{nc:+v});}drawModal();});
    const dedit=(el,f)=>{const k=dkey(el.dataset.mat,+el.dataset.d),v=el.value.trim();dEdit[k]=dEdit[k]||{nc:'',nq:'',rc:'',rd:''};dEdit[k][f]=(v===''?'':+v);
      if((dEdit[k].nc===''||dEdit[k].nc==null)&&(dEdit[k].nq===''||dEdit[k].nq==null)&&!dEdit[k].rc&&!(dEdit[k].rd||'').trim())delete dEdit[k];drawModal();};
    m.querySelectorAll('.sm-dc').forEach(el=>el.onchange=()=>dedit(el,'nc'));
    m.querySelectorAll('.sm-prc').forEach(el=>el.onchange=()=>{const e=pEdit[el.dataset.mat];if(e)e.rc=el.value;});
    m.querySelectorAll('.sm-prd').forEach(el=>el.oninput=()=>{const e=pEdit[el.dataset.mat];if(e)e.rd=el.value;});
    m.querySelectorAll('.sm-drc').forEach(el=>el.onchange=()=>{const e=dEdit[dkey(el.dataset.mat,+el.dataset.d)];if(e)e.rc=el.value;});
    m.querySelectorAll('.sm-drd').forEach(el=>el.oninput=()=>{const e=dEdit[dkey(el.dataset.mat,+el.dataset.d)];if(e)e.rd=el.value;});
    m.querySelectorAll('.sm-aamt').forEach(el=>el.onchange=()=>{amtAdjs[+el.dataset.i].amt=el.value===''?0:+el.value;drawModal();});
    m.querySelectorAll('.sm-arc').forEach(el=>el.onchange=()=>{amtAdjs[+el.dataset.i].rc=el.value;});
    m.querySelectorAll('.sm-ard').forEach(el=>el.oninput=()=>{amtAdjs[+el.dataset.i].rd=el.value;});
    m.querySelectorAll('.sm-adel').forEach(el=>el.onclick=()=>{amtAdjs.splice(+el.dataset.i,1);drawModal();});
    const add=m.querySelector('#sm-add-amt');if(add)add.onclick=()=>{amtAdjs.push({amt:0,rc:'',rd:''});drawModal();};
    const sv=m.querySelector('#sm-save');if(sv)sv.onclick=()=>save(false);
    const cf=m.querySelector('#sm-confirm');if(cf)cf.onclick=()=>{if(confirm(`${mc.nm} ${CFG.verb}을 마감확정할까요?\n최종금액 ${won0(calc().final)}원`))save(true);};
    const ro=m.querySelector('#sm-reopen');if(ro)ro.onclick=reopen;
  };

  const buildAdjustments=()=>{const items=(detail&&detail.items)||[];const out=[];const errs=[];
    items.forEach(it=>{
      (it.byday||[]).forEach(bd=>{const de=dEdit[dkey(it.mat,bd.d)];if(!de)return;const ncC=de.nc!=null&&de.nc!==''&&+de.nc!==+bd.cost;if(!ncC)return;
        const nc=+de.nc;const delta=nc*(+bd.qty)-(+bd.cost)*(+bd.qty);
        if(!(de.rc||(de.rd||'').trim()))errs.push(`${it.mat} ${bd.d}일: 사유 필요`);
        out.push({adj_type:'PRICE',scope:'DATE',mat_code:it.mat,target_ymd:ymd6(bd.d),old_cost:+bd.cost,new_cost:nc,old_qty:+bd.qty,new_qty:+bd.qty,delta_amt:delta,reason_code:de.rc||null,reason_detail:de.rd||null});});
      const pe=pEdit[it.mat];
      if(pe&&pe.nc!=null&&pe.nc!==''&&+pe.nc!==+it.cost){let delta=0;(it.byday||[]).forEach(bd=>{if(dEdit[dkey(it.mat,bd.d)])return;delta+=(+pe.nc-+bd.cost)*(+bd.qty);});
        if(delta!==0){if(!(pe.rc||(pe.rd||'').trim()))errs.push(`${it.mat} 품목단가: 사유 필요`);
          out.push({adj_type:'PRICE',scope:'ITEM',mat_code:it.mat,target_ymd:null,old_cost:+it.cost,new_cost:+pe.nc,old_qty:null,new_qty:null,delta_amt:delta,reason_code:pe.rc||null,reason_detail:pe.rd||null});}}});
    amtAdjs.forEach((a,i)=>{if(+a.amt!==0){if(!(a.rc||(a.rd||'').trim()))errs.push(`총액조정 ${i+1}행: 사유 필요`);
      out.push({adj_type:(+a.amt>=0?'AMT_UP':'AMT_DN'),scope:null,mat_code:null,target_ymd:null,old_cost:null,new_cost:null,old_qty:null,new_qty:null,delta_amt:+a.amt,reason_code:a.rc||null,reason_detail:a.rd||null});}});
    return {out,errs};};

  const save=async(doClose)=>{const {out,errs}=buildAdjustments();
    if(errs.length){alert('저장 불가:\n'+errs.join('\n'));return;}
    const s=calc();
    try{const r=await fetch(`${API}/api/${CFG.base}/save`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ym,cust_code:mc.cc,base_amt:s.base,adjustments:out,close:doClose})});
      const j=await r.json();if(!j.ok){alert('저장 거부:\n'+(j.errors||[]).join('\n'));return;}
      alert(doClose?`마감확정 완료 — 최종금액 ${won0(j.final_amt)}원`:`조정저장 완료 — 최종금액 ${won0(j.final_amt)}원`);
      closeModal();load(ym);}catch(e){alert('저장 실패: '+e.message);}};
  const reopen=async()=>{if(!confirm(`${mc.nm} 마감을 취소할까요?`))return;
    try{const r=await fetch(`${API}/api/${CFG.base}/reopen`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ym,cust_code:mc.cc})});
      const j=await r.json();if(!j.ok)throw new Error('reopen');alert('마감 취소됨 — 수정 가능');closeModal();load(ym);}catch(e){alert('마감취소 실패: '+e.message);}};

  load('');
};
/* 공용 필터 렌더/바인딩 — 라벨+필드 나란히(nowrap), select 자동폭, 자동완성(이름표시/코드저장) */
function qfFields(filters,F,pfx){
  return (filters||[]).map(f=>{
    const val=F[f.k]||'', nm=F[f.k+'__nm']||'';
    let fld;
    if(f.type==='select') fld=`<select class="inp" id="${pfx}${f.k}" style="min-width:${f.width||54}px;width:auto;max-width:220px">${(f.opts||[]).map(o=>`<option value="${esc(o.v)}"${String(val)===String(o.v)?' selected':''}>${esc(o.t)}</option>`).join('')}</select>`;
    else if(f.type==='auto') fld=`<span style="position:relative;display:inline-block"><input class="inp qf-ac" id="${pfx}${f.k}" data-ac="${f.k}" data-kind="${f.optKind||''}" data-showcode="${f.showCode?1:''}" autocomplete="off" value="${esc(f.showCode?val:(nm||val))}" placeholder="입력하세요" style="width:${f.width||120}px"><div class="wr-acbox" id="${pfx}acb-${f.k}" style="display:none;position:absolute;left:0;top:100%;z-index:120;min-width:100%;max-height:220px;overflow:auto;background:#fff;border:1px solid #b9d3ef;border-radius:6px;box-shadow:0 6px 16px rgba(0,0,0,.16)"></div></span>`;
    else fld=`<input class="inp" id="${pfx}${f.k}" value="${esc(val)}" placeholder="입력하세요" style="width:${f.width||90}px">`;
    return `<span style="display:inline-flex;align-items:center;gap:4px;white-space:nowrap;margin-right:2px"><label class="tl" style="margin:0">${f.label}</label>${fld}</span>`;
  }).join('');
}
function qfBind(host,filters,F,pfx,doSearch){
  const API=API_BASE; const g=id=>host.querySelector(id);
  (filters||[]).forEach(f=>{const el=g('#'+pfx+f.k); if(!el)return;
    if(f.type==='auto'){const box=g('#'+pfx+'acb-'+f.k); let t=null;
      el.oninput=()=>{F[f.k+'__nm']=el.value; F[f.k]=''; clearTimeout(t); const q=el.value.trim();
        if(!q){box.style.display='none';return;}
        t=setTimeout(()=>fetch(`${API}/api/qc/opt?kind=${f.optKind}&q=`+encodeURIComponent(q)).then(r=>r.json()).then(j=>{
          const rows=j.rows||[]; box.innerHTML=rows.length?rows.map(x=>`<div class="qf-o" data-code="${esc(x.code)}" data-name="${esc(x.name)}" style="padding:5px 10px;cursor:pointer;font-size:12px;border-bottom:1px solid #f0f3f8">${esc(x.name)} <span style="color:#9aa8bd;font-size:11px">${esc(x.code)}</span></div>`).join(''):'<div style="padding:6px 10px;color:#999;font-size:12px">결과 없음</div>';
          box.style.display='block';
          box.querySelectorAll('.qf-o').forEach(o=>o.onmousedown=()=>{F[f.k]=o.dataset.code;F[f.k+'__nm']=o.dataset.name;el.value=o.dataset.name;box.style.display='none';});
        }),180);};
      el.onblur=()=>setTimeout(()=>{if(box)box.style.display='none';},180);
      el.onkeyup=e=>{if(e.key==='Enter')doSearch();};
    } else { el.onkeyup=e=>{if(e.key==='Enter'){F[f.k]=el.value;doSearch();}}; el.onchange=()=>{F[f.k]=el.value;}; }
  });
}
/* 검색 직전 비-auto 필터값 읽기 */
function qfRead(host,filters,F,pfx){(filters||[]).forEach(f=>{if(f.type==='auto')return;const el=host.querySelector('#'+pfx+f.k);if(el)F[f.k]=el.value;});}
function wrCrud(host, cfg){
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date(), back=cfg.days||20;
  const st={F:Object.assign({from:iso(new Date(T.getFullYear(),T.getMonth(),1)),to:iso(T)},cfg.filt0||{}),
            data:{rows:[],cnt:0}, loading:false, msg:'', form:null, sel:new Set()};
  const load=async()=>{st.loading=true;render();
    try{const r=await fetch(`${API}${cfg.listEp}?`+new URLSearchParams(cfg.buildQS(st.F)));st.data=await r.json();st.msg='';}
    catch(e){st.msg='백엔드 연결 실패';st.data={rows:[],cnt:0};}
    st.loading=false;render();};
  const _req=f=>cfg.allReq?!f.optional:f.required;   // allReq=전항목 필수(예외만 optional)
  const save=async()=>{
    for(const f of cfg.form){if(_req(f)&&!String(st.form[f.k]??'').trim()){alert(f.label+' 은(는) 필수입니다');return;}}
    try{const r=await fetch(`${API}${cfg.saveEp}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg.toBody(st.form))});
      const j=await r.json();
      if(j.ok){st.msg=(j.mode==='insert'?'✅ 등록완료':'✅ 수정완료')+' (id '+j.id+')';st.form=null;await load();}
      else alert('저장 실패: '+JSON.stringify(j.errors||j));}
    catch(e){alert('저장 오류: '+e);}};
  const del=async(ids)=>{if(!ids.length){alert('삭제할 행을 체크하세요');return;}
    if(!confirm(ids.length+'건을 삭제하시겠습니까?'))return;
    try{const r=await fetch(`${API}${cfg.delEp}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids})});
      const j=await r.json();st.msg='🗑 '+j.deleted+'건 삭제완료';st.sel.clear();st.form=null;await load();}
    catch(e){alert('삭제 오류: '+e);}};
  const fld=(f)=>{
    const v=st.form[f.k]??'';
    // 드롭다운: 선택 글자에 맞춰 자동폭(width:auto)
    if(f.type==='select') return `<select class="inp" data-fk="${f.k}" style="min-width:${f.width||70}px;width:auto;max-width:280px">${(f.opts||[]).map(o=>`<option value="${esc(o.v)}" ${String(o.v)===String(v)?'selected':''}>${esc(o.t)}</option>`).join('')}</select>`;
    // 자동완성: 이름으로 보여주고 코드 저장, 한 글자 치면 후보 클릭
    if(f.type==='auto'){
      const nm=st.form[f.k+'__nm']??'', disp=f.showCode?v:(nm||v);
      return `<span style="position:relative;display:inline-block">
        <input class="inp wr-ac" data-ac="${f.k}" data-kind="${f.optKind||''}" data-showcode="${f.showCode?1:''}" data-ep="${f.searchEp||'/api/qc/opt'}" autocomplete="off" value="${esc(disp)}" placeholder="입력하세요" style="width:${f.width||140}px">
        <div class="wr-acbox" id="wr-ac-${f.k}" style="display:none;position:absolute;left:0;top:100%;z-index:120;min-width:100%;max-height:220px;overflow:auto;background:#fff;border:1px solid #b9d3ef;border-radius:6px;box-shadow:0 6px 16px rgba(0,0,0,.16)"></div></span>`;
    }
    const ph = f.ph ?? ((f.type==='date'||f.type==='num')?'':'입력하세요');
    const list=f.search?`list="wr-dl-${f.k}"`:'';
    const dl=f.search?`<datalist id="wr-dl-${f.k}"></datalist>`:'';
    return `<input class="inp" data-fk="${f.k}" ${list} type="${f.type==='date'?'date':'text'}" value="${esc(v)}" placeholder="${esc(ph)}" style="width:${f.width||110}px" ${f.type==='num'?'inputmode="decimal"':''}>${dl}`;
  };
  const render=()=>{
    const d=st.data, editing=st.form!==null;
    const ed=(typeof PERM!=='undefined')?PERM.canEdit(cfg.sid||''):true;   // 수정권한 게이트(규칙#16)
    host.innerHTML=`
     <div class="toolbar">
       <label class="tl">${cfg.dateLabel||'기간'}</label>
       <input class="inp" type="date" id="wr-from" value="${st.F.from}"> ~ <input class="inp" type="date" id="wr-to" value="${st.F.to}">
       ${qfFields(cfg.filters,st.F,'wr-f-')}
       <button class="btn" id="wr-search">🔍 조회</button>
       ${ed?`<button class="btn" id="wr-new" style="background:#1c7c3a;color:#fff">➕ 신규</button>
       <button class="btn" id="wr-del">🗑 선택삭제</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</span>`}
       <div class="spacer"></div><span class="rowcount">${nf(d.cnt||0)}건${cfg.sum?(' · '+cfg.sum(d)):''}</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:${(st.msg.includes('실패')||st.msg.includes('오류'))?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     ${(editing&&cfg.modal)?`<div class="wr-modal" style="position:fixed;inset:0;z-index:110;background:rgba(20,30,50,.38);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:26px 10px">
        <div style="background:#fff;border-radius:10px;box-shadow:0 22px 64px rgba(0,0,0,.32);width:${cfg.modalWidth||560}px;max-width:96vw">
          <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#1c47a0;color:#fff;border-radius:10px 10px 0 0">
            <b>${cfg.modalTitle||'등록'} ${st.form.id?'— 수정 (id '+st.form.id+')':'— 신규'}</b><span id="wr-x" style="cursor:pointer;font-size:17px">✕</span></div>
          <div style="padding:12px 16px;max-height:calc(100vh - 170px);overflow:auto">
            <table style="border-collapse:collapse;width:100%">${cfg.form.map(f=>`<tr>
              <td style="padding:5px 10px 5px 0;white-space:nowrap;color:#33507d;font-weight:600;font-size:12px;text-align:right;width:104px;vertical-align:middle">${f.label}${_req(f)?'<span style="color:#c0392b">*</span>':''}</td>
              <td style="padding:4px 0">${fld(f)}</td></tr>`).join('')}</table>
          </div>
          <div style="padding:11px 16px;border-top:1px solid #e2e8f2;display:flex;justify-content:space-between;align-items:center;gap:10px">
            <span style="color:#c0392b;font-size:11px;text-align:left">* 필수항목 제외품목들을 사용해보고 전산담당에게 알려주세요.</span>
            <span style="white-space:nowrap"><button class="btn" id="wr-save" style="background:#1b6ec2;color:#fff">💾 저장</button>
            <button class="btn" id="wr-cancel">닫기</button></span></div>
        </div></div>`:(editing?`<div style="background:#f2f8ff;border:1px solid #b9d3ef;border-radius:8px;padding:10px;margin:8px 0">
        <div style="font-weight:600;margin-bottom:6px">${st.form.id?'✏️ 수정 (id '+st.form.id+')':'➕ 신규 등록'}</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center">
        ${cfg.form.map(f=>`<label class="tl">${f.label}${_req(f)?'<span style="color:#c0392b">*</span>':''}</label>${fld(f)}`).join('')}
        </div>
        <div style="margin-top:8px"><button class="btn" id="wr-save" style="background:#1b6ec2;color:#fff">💾 저장</button>
        <button class="btn" id="wr-cancel">취소</button></div>
      </div>`:'')}
     <div class="grid-wrap" style="max-height:calc(100vh - ${(editing&&!cfg.modal)?430:330}px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:11px"><thead><tr><th style="width:26px"></th>${cfg.cols.map(col=>`<th class="${col.cls||''}">${col.h}</th>`).join('')}<th style="width:56px">작업</th></tr></thead>
      <tbody>${st.loading?spinRow(cfg.cols.length+2):((d.rows&&d.rows.length)?d.rows.map((r,i)=>`<tr>
        <td class="center">${ed&&r.ID?`<input type="checkbox" class="wr-chk" data-id="${r.ID}" ${st.sel.has(String(r.ID))?'checked':''}>`:''}</td>
        ${cfg.cols.map(col=>`<td class="${col.cls||''}" ${col.title?`title="${esc(r[col.title]||'')}"`:''} ${col.cap?'style="max-width:150px;overflow:hidden;text-overflow:ellipsis"':''}>${col.fmt?col.fmt(r):esc(r[col.k]??'')}</td>`).join('')}
        <td class="center">${ed&&(r.ID||cfg.editAll)?`<button class="btn wr-edit" data-idx="${i}" style="padding:1px 6px">수정</button>`:`<span style="color:#8aa0bd;font-size:10px">${r.ID?'':'📁이력'}</span>`}</td></tr>`).join(''):`<tr><td colspan="${cfg.cols.length+2}" class="empty">조회 결과 없음${ed?' (➕신규로 등록)':''}</td></tr>`)}</tbody></table></div>`;
    const g=id=>host.querySelector(id);
    const doSearch=()=>{st.F.from=g('#wr-from').value;st.F.to=g('#wr-to').value;qfRead(host,cfg.filters,st.F,'wr-f-');load();};
    g('#wr-search').onclick=doSearch;
    if(ed){g('#wr-new').onclick=()=>{st.form=cfg.newRow(st.F);render();};
      g('#wr-del').onclick=()=>del([...st.sel]);}
    host.querySelectorAll('.wr-chk').forEach(ch=>ch.onclick=()=>{const id=ch.dataset.id;ch.checked?st.sel.add(id):st.sel.delete(id);});  // ★ID는 문자열 유지(웹행 ID='YMD-SEQ' 복합키, +변환시 NaN)
    host.querySelectorAll('.wr-edit').forEach(b=>b.onclick=()=>{const r=d.rows[+b.dataset.idx];st.form=cfg.fromRow(r);render();});
    qfBind(host,cfg.filters,st.F,'wr-f-',doSearch);
    if(editing){
      g('#wr-cancel').onclick=()=>{st.form=null;render();};
      const xb=g('#wr-x'); if(xb)xb.onclick=()=>{st.form=null;render();};
      g('#wr-save').onclick=save;
      host.querySelectorAll('[data-fk]').forEach(el=>{
        el.oninput=()=>{st.form[el.dataset.fk]=el.value;
          const f=cfg.form.find(x=>x.k===el.dataset.fk);
          if(f&&f.search&&el.value.length>=2){fetch(`${API}/api/wr/itemsearch?q=`+encodeURIComponent(el.value)).then(r=>r.json()).then(j=>{
            const dl=host.querySelector('#wr-dl-'+f.k);if(dl)dl.innerHTML=(j.rows||[]).map(x=>`<option value="${esc(x.item)}">${esc(x.nm)}</option>`).join('');});}
        };
      });
      // 자동완성(이름표시·코드저장): 한 글자 치면 후보→클릭
      host.querySelectorAll('.wr-ac').forEach(el=>{
        const fk=el.dataset.ac, kind=el.dataset.kind, ep=el.dataset.ep, sc=!!el.dataset.showcode, box=host.querySelector('#wr-ac-'+fk); let t=null;
        el.oninput=()=>{ if(sc){st.form[fk]=el.value;} else {st.form[fk+'__nm']=el.value; st.form[fk]='';}  // 코드형=직접입력, 이름형=클릭확정
          clearTimeout(t); const q=el.value.trim();
          if(!q){box.style.display='none';return;}
          t=setTimeout(()=>fetch(`${API}${ep}?kind=${kind}&q=`+encodeURIComponent(q)).then(r=>r.json()).then(j=>{
            const rows=j.rows||[];
            box.innerHTML=rows.length?rows.map(x=>`<div class="wr-acopt" data-code="${esc(x.code)}" data-name="${esc(x.name)}" style="padding:5px 10px;cursor:pointer;font-size:12px;border-bottom:1px solid #f0f3f8"><b>${esc(sc?x.code:x.name)}</b> <span style="color:#9aa8bd;font-size:11px">${esc(sc?x.name:x.code)}</span></div>`).join(''):'<div style="padding:6px 10px;color:#999;font-size:12px">결과 없음</div>';
            box.style.display='block';
            box.querySelectorAll('.wr-acopt').forEach(o=>o.onmousedown=()=>{st.form[fk]=o.dataset.code;st.form[fk+'__nm']=o.dataset.name;el.value=sc?o.dataset.code:o.dataset.name;box.style.display='none';});
          }),180);};
        el.onblur=()=>setTimeout(()=>{if(box)box.style.display='none';},180);
      });
    }
  };
  load();
}
/* 모드 토글 셸(라이브 조회 ↔ nx 신규등록/편집) */
function wrShell(c, o){
  if(o.cfg&&o.sid&&!o.cfg.sid)o.cfg.sid=o.sid;   // 권한 sid 주입(규칙#16)
  // nxOnly: 컷오버 후 nx 단일원장 모드 — 레거시/nx 토글 없이 nx만 조회·편집
  const nxOnly=o.nxOnly;
  let mode=nxOnly?'edit':(o.default||'edit');
  const paint=()=>{
    const toggle=nxOnly?'':`<div style="display:flex;gap:6px;margin:6px 0 2px">
       <button class="btn ${mode==='live'?'active':''}" id="wm-live" style="${mode==='live'?'background:#b12a2a;color:#fff':''}">🔴 레거시 라이브조회</button>
       <button class="btn ${mode==='edit'?'active':''}" id="wm-edit" style="${mode==='edit'?'background:#1c7c3a;color:#fff':''}">✏️ 신규 등록/편집(nx)</button>
       <span class="page-sub" style="margin:0;align-self:center;color:#8aa0bd">※ 신규편집은 웹 등록데이터(nx)이며 레거시 라이브와 별개 원장입니다</span>
     </div>`;
    c.innerHTML=`<div class="page-title">${o.title}</div>
     <div class="page-sub">${o.sub}</div>
     ${toggle}
     <div id="wr-body"></div>`;
    if(!nxOnly){
      c.querySelector('#wm-live').onclick=()=>{if(mode!=='live'){mode='live';paint();}};
      c.querySelector('#wm-edit').onclick=()=>{if(mode!=='edit'){mode='edit';paint();}};
    }
    const body=c.querySelector('#wr-body');
    if(mode==='live') o.live(body); else if(o.cfg&&o.cfg._custom) o.cfg._custom(body); else wrCrud(body, o.cfg);
  };
  paint();
}
/* 라이브 조회(공용): partledger/procresult 그리드 */
function wrLiveLedger(body, kind){
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const ymd=s=>(s&&(''+s).length===6)?`${(''+s).slice(0,2)}/${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:(s||'');
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date(); const isAdj=(kind==='adj');
  let F={from:iso(new Date(T.getFullYear(),T.getMonth(),1)),to:iso(T),part:'',wc:''};
  let data={rows:[],cnt:0,sum_qty:0}, loading=false, msg='';
  const load=async()=>{loading=true;draw();
    const qs=new URLSearchParams({kind,from_ymd:F.from,to_ymd:F.to,part:F.part,wc:F.wc});
    try{const r=await fetch(`${API}/api/partledger/list?${qs}`);data=await r.json();msg='';}
    catch(e){msg='백엔드 연결 실패';data={rows:[],cnt:0,sum_qty:0};}
    loading=false;draw();};
  const draw=()=>{
    body.innerHTML=`
     <div class="toolbar">
       <label class="tl">${isAdj?'수정기간':'출고기간'}</label><input class="inp" type="date" id="ad-from" value="${F.from}"> ~ <input class="inp" type="date" id="ad-to" value="${F.to}">
       <label class="tl">자도번</label><input class="inp" id="ad-part" value="${esc(F.part)}" style="width:120px">
       <label class="tl">작업처</label><input class="inp" id="ad-wc" value="${esc(F.wc)}" style="width:70px">
       <button class="btn" id="ad-search">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">${nf(data.cnt)}건 · ${isAdj?'조정':'출고'}수량합 <b>${nf(data.sum_qty)}</b></span>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 340px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:11px"><thead><tr><th>${isAdj?'수정일자':'출고일자'}</th><th class="num">SEQ</th>${isAdj?'<th>파트</th>':'<th>FROM파트</th><th>TO파트</th>'}<th>자도번</th><th>품명</th><th class="num">${isAdj?'수정수량':'출고수량'}</th><th class="num">단가</th><th class="num">금액</th><th>비고</th>${isAdj?'<th>도번</th><th>작업처</th>':''}<th>작업자</th><th>작업일시</th></tr></thead>
      <tbody>${loading?spinRow(isAdj?13:12):((data.rows&&data.rows.length)?data.rows.map(r=>`<tr>
        <td class="center">${ymd(r.MAINT_YMD)}</td><td class="num">${r.MAINT_SEQ}</td>${isAdj?`<td class="center">${esc(r.part)}</td>`:`<td class="center">${esc(r.frompart)}</td><td class="center">${esc(r.part)}</td>`}<td><b>${esc(r.mat)}</b></td>
        <td class="bcap" title="${esc(r.nm)}" style="max-width:140px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td>
        <td class="num" style="color:${r.MAINT_QTY<0?'#c0392b':'#1c7c3a'}">${nf(r.MAINT_QTY)}</td><td class="num">${nf(r.MAINT_COST)}</td><td class="num">${nf(r.MAINT_AMT)}</td>
        <td class="bcap" title="${esc(r.remarks)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.remarks)}</td>
        ${isAdj?`<td>${esc(r.dobun)}</td><td class="center">${esc(r.pwc)}</td>`:''}<td>${esc(r.usr)}</td><td class="center" style="color:#8aa0bd">${esc(r.INSERT_DATETIME)}</td></tr>`).join(''):`<tr><td colspan="${isAdj?13:12}" class="empty">조회 결과 없음</td></tr>`)}</tbody></table></div>`;
    const g=id=>body.querySelector(id);
    g('#ad-search').onclick=()=>{F.from=g('#ad-from').value;F.to=g('#ad-to').value;F.part=g('#ad-part').value;F.wc=g('#ad-wc').value;load();};
    ['#ad-part','#ad-wc'].forEach(id=>g(id).onkeyup=e=>{if(e.key==='Enter')g('#ad-search').click();});
  };
  load();
}
const _y6=s=>{s=''+(s||'');return s.length===6?('20'+s.slice(0,2)+'-'+s.slice(2,4)+'-'+s.slice(4,6)):s;};
const _wnf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
const _wymd=s=>(s&&(''+s).length===6)?`${(''+s).slice(0,2)}/${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:(s||'');
const _whms=s=>(s&&(''+s).length>=4)?`${(''+s).slice(0,2)}:${(''+s).slice(2,4)}`:(s||'');

/* ===== 거래처MASTER CRUD (nx.cust, 위하고정합) — 레거시 w_cm_master_055 유지관리 ===== */
function custMaint(host){
  const API=API_BASE;
  let opts={cust_type:[],biztag:[],yn:[],ue_date:[],ue_week:[],banks:[]};
  const st={rows:[],cnt:0,q:'',use:'',ctype:'',form:null,sel:new Set(),msg:''};
  // [key,label,type,optkey] · type: req(필수텍스트)/text/num/date/sel(드롭다운)/chk(0·1)
  const FIELDS=[
    ['cust_code','거래처코드','text'],['cust_name','거래처명','req'],
    ['cust_type','거래처구분','sel','cust_type'],['business_tag','사업자구분','sel','biztag'],
    ['in_flag','매입','chk'],['out_flag','매출','chk'],['outside_flag','외주','chk'],
    ['biz_no','사업자등록번호','text'],['resident_no','주민등록번호','text'],['corp_no','법인번호','text'],
    ['owner_name','대표자성명','text'],['biz_type','업태','text'],['biz_item','종목','text'],
    ['post_no','우편번호','text'],['address1','사업장주소','text'],['address2','상세주소','text'],
    ['tel','전화번호','text'],['fax','팩스번호','text'],['homepage','홈페이지','text'],
    ['dept_name','업체부서명','text'],['charge_name','담당자명','text'],['charge_rank','직급','text'],
    ['charge_tel','담당자전화','text'],['charge_hp','담당자H.P','text'],['charge_email','담당자이메일','text'],
    ['charge_user_id','담당사원','text'],['dlvy_day','납기일','num'],['dlvy_day2','납기일2','num'],
    ['ue_date','결제조건','sel','ue_date'],['ue_week','결제주','sel','ue_week'],
    ['bank_flag','은행/보험사','chk'],['bank_code','은행','sel','banks'],['bank_bookno','계좌번호','text'],
    ['bank_person_name','예금주','text'],['cms_no','CMS번호','text'],
    ['credit_limit','여신한도','num'],['collateral_amt','담보설정액','num'],
    ['sagub_out_flag','사급출고','chk'],['set_in_flag','세트입고','chk'],['heat_label_flag','열처리라벨','chk'],['prod_check_flag','생산확인','chk'],
    ['recv_post_no','수령지우편','text'],['recv_address','수령지주소','text'],['recv_address_dtl','수령지상세','text'],
    ['print_name','출력용거래처명','text'],['trade_start','거래시작일','date'],['trade_end','거래종료일','date'],
    ['gc_gubun','GC구분','text'],['remarks','비고','text'],['use_flag','사용여부','chk'],
  ];
  const load=async()=>{
    const qs=new URLSearchParams({q:st.q,use:st.use,ctype:st.ctype});
    try{const r=await fetch(`${API}/api/cust/list?${qs}`);const j=await r.json();st.rows=j.rows||[];st.cnt=j.cnt||0;}
    catch(e){st.msg='백엔드 연결 실패';st.rows=[];}
    render();
  };
  const fld=(f)=>{
    const [k,label,type,ok]=f, v=st.form[k]??'';
    if(type==='sel'){const os=opts[ok]||[];return `<select class="inp" data-fk="${k}" style="min-width:90px;width:auto;max-width:260px"><option value="">선택</option>${os.map(o=>`<option value="${esc(o.code)}" ${String(o.code)===String(v)?'selected':''}>${esc(o.nm)}</option>`).join('')}</select>`;}
    if(type==='chk')return `<input type="checkbox" data-fk="${k}" ${(v===1||v==='1'||v===true)?'checked':''} style="width:18px;height:18px">`;
    if(type==='date')return `<input class="inp" data-fk="${k}" type="date" value="${esc(v)}" style="width:140px">`;
    const ro=(k==='cust_code'&&st.form._edit)?'readonly style="width:120px;background:#eef2f7"':'style="width:'+(type==='num'?90:160)+'px"';
    return `<input class="inp" data-fk="${k}" value="${esc(v)}" ${type==='num'?'inputmode="decimal"':''} ${ro}>`;
  };
  const render=()=>{
    const editing=st.form!==null;
    const ed=(typeof PERM!=='undefined')?PERM.canEdit('basemaster'):true;   // 수정권한 게이트(규칙#16)
    host.innerHTML=`
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">
       <label class="tl">검색</label><input class="inp" id="cm-q" value="${esc(st.q)}" placeholder="코드/명/대표자" style="width:150px">
       <label class="tl">거래처구분</label><select class="inp" id="cm-ct" style="width:auto"><option value="">전체</option>${opts.cust_type.map(o=>`<option value="${esc(o.code)}" ${st.ctype===o.code?'selected':''}>${esc(o.nm)}</option>`).join('')}</select>
       <label class="tl">사용</label><select class="inp" id="cm-use" style="width:auto"><option value="">전체</option><option value="1" ${st.use==='1'?'selected':''}>사용</option><option value="0" ${st.use==='0'?'selected':''}>중지</option></select>
       <button class="btn" id="cm-search">🔍 조회</button>
       ${ed?`<button class="btn" id="cm-new" style="background:#1c7c3a;color:#fff">➕ 신규</button>
       <button class="btn" id="cm-del">🗑 선택삭제</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</span>`}
       <div class="spacer"></div><span class="rowcount">${won(st.cnt)}건</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.includes('실패')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     ${editing?`<div class="wr-modal" style="position:fixed;inset:0;z-index:110;background:rgba(20,30,50,.38);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:24px 10px">
       <div style="background:#fff;border-radius:10px;box-shadow:0 22px 64px rgba(0,0,0,.32);width:640px;max-width:96vw">
         <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#1c47a0;color:#fff;border-radius:10px 10px 0 0">
           <b>거래처 Maint ${st.form._edit?'— 수정 ('+esc(st.form.cust_code)+')':'— 신규'}</b><span id="cm-x" style="cursor:pointer;font-size:17px">✕</span></div>
         <div style="padding:12px 16px;max-height:calc(100vh - 170px);overflow:auto">
           <table style="border-collapse:collapse;width:100%"><tbody>${(()=>{let h='';for(let i=0;i<FIELDS.length;i+=2){const a=FIELDS[i],b=FIELDS[i+1];
             const cell=f=>f?`<td style="padding:5px 8px 5px 0;white-space:nowrap;color:#33507d;font-weight:600;font-size:12px;text-align:right;width:96px">${f[1]}${f[2]==='req'||f[0]==='cust_type'?'<span style="color:#c0392b">*</span>':''}</td><td style="padding:4px 8px 4px 0">${fld(f)}</td>`:'<td></td><td></td>';
             h+=`<tr>${cell(a)}${cell(b)}</tr>`;}return h;})()}</tbody></table>
         </div>
         <div style="padding:11px 16px;border-top:1px solid #e2e8f2;display:flex;justify-content:space-between;align-items:center">
           <span style="color:#c0392b;font-size:11px">* 거래처명·거래처구분·역할(매입/매출/외주 최소1)·사업자번호는 검증됩니다.</span>
           <span><button class="btn" id="cm-save" style="background:#1b6ec2;color:#fff">💾 저장</button> <button class="btn" id="cm-cancel">닫기</button></span></div>
       </div></div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 330px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr><th style="width:26px"></th>
        <th>거래처코드</th><th>거래처명</th><th>사업자등록번호</th><th>대표자</th><th>거래처구분</th><th>역할</th><th>사업자구분</th><th>전화번호</th><th>담당자</th><th class="center">사용</th><th style="width:46px">작업</th></tr></thead>
      <tbody>${st.rows.length?st.rows.map((r,i)=>`<tr>
        <td class="center">${ed?`<input type="checkbox" class="cm-chk" data-code="${esc(r.cust_code)}" ${st.sel.has(r.cust_code)?'checked':''}>`:''}</td>
        <td><b>${esc(r.cust_code)}</b></td><td class="cap" title="${esc(r.cust_name)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.cust_name)}</td>
        <td>${esc(r.biz_no)}</td><td>${esc(r.owner_name)}</td><td>${esc(r.cust_type_nm)}</td><td>${esc(r.roles)}</td><td>${esc(r.biztag_nm)}</td>
        <td>${esc(r.tel)}</td><td>${esc(r.charge_name)}</td><td class="center">${r.use_flag?'<span class="bdg ok">사용</span>':'<span class="bdg off">중지</span>'}</td>
        <td class="center">${ed?`<button class="btn cm-edit" data-idx="${i}" style="padding:1px 6px;font-size:10px">수정</button>`:''}</td></tr>`).join(''):`<tr><td colspan="12" class="empty">조회 결과 없음${ed?' (➕신규로 등록)':''}</td></tr>`}</tbody></table></div>`;
    const g=id=>host.querySelector(id);
    g('#cm-search').onclick=()=>{st.q=g('#cm-q').value;st.ctype=g('#cm-ct').value;st.use=g('#cm-use').value;load();};
    g('#cm-q').onkeyup=e=>{if(e.key==='Enter')g('#cm-search').click();};
    if(ed){
      g('#cm-new').onclick=async()=>{let code='';try{code=(await (await fetch(`${API}/api/cust/newcode`)).json()).code;}catch(e){}
        st.form={cust_code:code,use_flag:1,in_flag:1,out_flag:1,outside_flag:0,cust_type:'',business_tag:'1'};render();};
      g('#cm-del').onclick=()=>del([...st.sel]);
      host.querySelectorAll('.cm-chk').forEach(ch=>ch.onclick=()=>{const cd=ch.dataset.code;ch.checked?st.sel.add(cd):st.sel.delete(cd);});
      host.querySelectorAll('.cm-edit').forEach(b=>b.onclick=()=>{st.form=Object.assign({_edit:1},st.rows[+b.dataset.idx]);render();});
    }
    attachResizers(host);
    if(editing){
      g('#cm-cancel').onclick=g('#cm-x').onclick=()=>{st.form=null;render();};
      g('#cm-save').onclick=save;
      host.querySelectorAll('[data-fk]').forEach(el=>{
        const k=el.dataset.fk;
        if(el.type==='checkbox')el.onchange=()=>{st.form[k]=el.checked?1:0;};
        else el.oninput=()=>{st.form[k]=el.value;};
      });
    }
  };
  const save=async()=>{
    const f=st.form;
    if(!String(f.cust_name||'').trim()){alert('거래처명은 필수입니다');return;}
    if(!String(f.cust_type||'').trim()){alert('거래처구분을 선택하세요');return;}
    if(!(f.in_flag||f.out_flag||f.outside_flag)){alert('역할(매입/매출/외주) 최소 하나를 선택하세요');return;}
    try{const r=await fetch(`${API}/api/cust/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...f,user:'웹사용자'})});
      const j=await r.json();
      if(r.ok&&j.ok){st.msg=(j.mode==='insert'?'✅ 등록완료 ':'✅ 수정완료 ')+j.cust_code;st.form=null;await load();}
      else alert('저장 실패: '+(j.detail||JSON.stringify(j)));}
    catch(e){alert('저장 오류: '+e);}
  };
  const del=async(codes)=>{if(!codes.length){alert('삭제할 행을 체크하세요');return;}
    if(!confirm(codes.length+'건을 삭제하시겠습니까?'))return;
    try{const r=await fetch(`${API}/api/cust/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({codes})});
      const j=await r.json();st.msg='🗑 '+j.deleted+'건 삭제완료';st.sel.clear();await load();}
    catch(e){alert('삭제 오류: '+e);}
  };
  (async()=>{try{opts=await (await fetch(`${API}/api/cust/opts`)).json();}catch(e){}load();})();
}

/* ===== 범용 마스터 CRUD (부서·LINE-NO 등 단순 마스터 재사용) — cfg 구동 ===== */
/* cfg={sid,keyField,listEp,saveEp,delEp,cols:[{k,h,fmt?}],fields:[[k,label,type,opts?]],newDefaults,readOnly?,newcodeEp?} */
function mstCrud(host, cfg){
  const API=API_BASE;
  const st={rows:[],cnt:0,q:'',form:null,sel:new Set(),msg:''};
  const load=async()=>{
    try{const r=await fetch(`${API}${cfg.listEp}?q=`+encodeURIComponent(st.q));const j=await r.json();st.rows=j.rows||[];st.cnt=j.cnt||0;st.msg='';}
    catch(e){st.msg='백엔드 연결 실패';st.rows=[];}
    render();
  };
  const kf=cfg.keyField;
  const fld=(f)=>{
    const [k,label,type,ops]=f, v=st.form[k]??'';
    if(type==='sel'){const os=ops||[];return `<select class="inp" data-fk="${k}" style="min-width:80px;width:auto;max-width:240px"><option value="">선택</option>${os.map(o=>`<option value="${esc(o.code)}" ${String(o.code)===String(v)?'selected':''}>${esc(o.nm)}</option>`).join('')}</select>`;}
    if(type==='chk')return `<input type="checkbox" data-fk="${k}" ${(v===1||v==='1'||v===true)?'checked':''} style="width:18px;height:18px">`;
    if(type==='date')return `<input class="inp" data-fk="${k}" type="date" value="${esc(v)}" style="width:140px">`;
    const ro=(k===kf&&st.form._edit)?'readonly style="width:130px;background:#eef2f7"':'style="width:'+(type==='num'?90:180)+'px"';
    return `<input class="inp" data-fk="${k}" value="${esc(v)}" ${type==='num'?'inputmode="decimal"':''} ${ro}>`;
  };
  const render=()=>{
    const editing=st.form!==null;
    const ed=(!cfg.readOnly)&&((typeof PERM!=='undefined')?PERM.canEdit(cfg.sid||'basemaster'):true);
    host.innerHTML=`
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">
       <label class="tl">검색</label><input class="inp" id="ms-q" value="${esc(st.q)}" placeholder="코드/명" style="width:150px">
       <button class="btn" id="ms-search">🔍 조회</button>
       ${cfg.readOnly?'<span style="color:#8aa0bd;font-size:12px">🔎 조회 전용 (편집은 개발›원가/BOM기준정보)</span>':(ed?`<button class="btn" id="ms-new" style="background:#1c7c3a;color:#fff">➕ 신규</button><button class="btn" id="ms-del">🗑 선택삭제</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</span>`)}
       <div class="spacer"></div><span class="rowcount">${won(st.cnt)}건</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.includes('실패')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     ${editing?`<div class="wr-modal" style="position:fixed;inset:0;z-index:110;background:rgba(20,30,50,.38);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:24px 10px">
       <div style="background:#fff;border-radius:10px;box-shadow:0 22px 64px rgba(0,0,0,.32);width:560px;max-width:96vw">
         <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#1c47a0;color:#fff;border-radius:10px 10px 0 0">
           <b>${esc(cfg.title||'마스터')} ${st.form._edit?'— 수정 ('+esc(st.form[kf])+')':'— 신규'}</b><span id="ms-x" style="cursor:pointer;font-size:17px">✕</span></div>
         <div style="padding:12px 16px;max-height:calc(100vh - 170px);overflow:auto">
           <table style="border-collapse:collapse;width:100%"><tbody>${(()=>{let h='';for(let i=0;i<cfg.fields.length;i+=2){const a=cfg.fields[i],b=cfg.fields[i+1];
             const cell=f=>f?`<td style="padding:5px 8px 5px 0;white-space:nowrap;color:#33507d;font-weight:600;font-size:12px;text-align:right;width:88px">${f[1]}${f[2]==='req'?'<span style="color:#c0392b">*</span>':''}</td><td style="padding:4px 8px 4px 0">${fld(f)}</td>`:'<td></td><td></td>';
             h+=`<tr>${cell(a)}${cell(b)}</tr>`;}return h;})()}</tbody></table>
         </div>
         <div style="padding:11px 16px;border-top:1px solid #e2e8f2;display:flex;justify-content:flex-end;gap:8px">
           <button class="btn" id="ms-save" style="background:#1b6ec2;color:#fff">💾 저장</button><button class="btn" id="ms-cancel">닫기</button></div>
       </div></div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 330px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr>${ed?'<th style="width:26px"></th>':''}${cfg.cols.map(col=>`<th class="${col.cls||''}">${col.h}</th>`).join('')}${ed?'<th style="width:46px">작업</th>':''}</tr></thead>
      <tbody>${st.rows.length?st.rows.map((r,i)=>`<tr>
        ${ed?`<td class="center"><input type="checkbox" class="ms-chk" data-code="${esc(r[kf])}" ${st.sel.has(r[kf])?'checked':''}></td>`:''}
        ${cfg.cols.map((col,ci)=>`<td class="${col.cls||''}" ${col.cap?`title="${esc(r[col.k]||'')}" style="max-width:${col.cap===true?150:col.cap}px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"`:''}>${ci===0?'<b>':''}${col.fmt?col.fmt(r):esc(r[col.k]??'')}${ci===0?'</b>':''}</td>`).join('')}
        ${ed?`<td class="center"><button class="btn ms-edit" data-idx="${i}" style="padding:1px 6px;font-size:10px">수정</button></td>`:''}</tr>`).join(''):`<tr><td colspan="${cfg.cols.length+(ed?2:0)}" class="empty">조회 결과 없음${ed?' (➕신규로 등록)':''}</td></tr>`}</tbody></table></div>`;
    const g=id=>host.querySelector(id);
    g('#ms-search').onclick=()=>{st.q=g('#ms-q').value;load();};
    g('#ms-q').onkeyup=e=>{if(e.key==='Enter')g('#ms-search').click();};
    if(ed){
      g('#ms-new').onclick=async()=>{let d=Object.assign({},cfg.newDefaults||{});
        if(cfg.newcodeEp){try{d[kf]=(await (await fetch(`${API}${cfg.newcodeEp}`)).json()).code;}catch(e){}}
        st.form=d;render();};
      g('#ms-del').onclick=()=>del([...st.sel]);
      host.querySelectorAll('.ms-chk').forEach(ch=>ch.onclick=()=>{const cd=ch.dataset.code;ch.checked?st.sel.add(cd):st.sel.delete(cd);});
      host.querySelectorAll('.ms-edit').forEach(b=>b.onclick=()=>{st.form=Object.assign({_edit:1},st.rows[+b.dataset.idx]);render();});
    }
    attachResizers(host);
    if(editing){
      g('#ms-cancel').onclick=g('#ms-x').onclick=()=>{st.form=null;render();};
      g('#ms-save').onclick=save;
      host.querySelectorAll('[data-fk]').forEach(el=>{const k=el.dataset.fk;
        if(el.type==='checkbox')el.onchange=()=>{st.form[k]=el.checked?1:0;};else el.oninput=()=>{st.form[k]=el.value;};});
    }
  };
  const save=async()=>{
    for(const f of cfg.fields){if(f[2]==='req'&&!String(st.form[f[0]]??'').trim()){alert(f[1]+'은(는) 필수입니다');return;}}
    if(!String(st.form[kf]??'').trim()){alert('코드는 필수입니다');return;}
    try{const r=await fetch(`${API}${cfg.saveEp}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...st.form,user:'웹사용자'})});
      const j=await r.json();
      if(r.ok&&j.ok){st.msg=(j.mode==='insert'?'✅ 등록완료':'✅ 수정완료');st.form=null;await load();}
      else alert('저장 실패: '+(j.detail||JSON.stringify(j)));}
    catch(e){alert('저장 오류: '+e);}
  };
  const del=async(codes)=>{if(!codes.length){alert('삭제할 행을 체크하세요');return;}
    if(!confirm(codes.length+'건을 삭제하시겠습니까?'))return;
    try{const r=await fetch(`${API}${cfg.delEp}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({codes})});
      const j=await r.json();st.msg='🗑 '+j.deleted+'건 삭제완료';st.sel.clear();await load();}
    catch(e){alert('삭제 오류: '+e);}
  };
  load();
}
const MST_CFG={
  dept:{sid:'basemaster',title:'부서 마스터',keyField:'dept_code',listEp:'/api/dept/list',saveEp:'/api/dept/save',delEp:'/api/dept/delete',
    cols:[{k:'dept_code',h:'부서코드'},{k:'dept_desc',h:'부서명',cap:180},{k:'sort_key',h:'정렬',cls:'num'},{k:'fin_dept_code',h:'재무부서'},{k:'dept_from_ymd',h:'적용시작'},{k:'dept_to_ymd',h:'적용종료'},{k:'use_flag',h:'사용',cls:'center',fmt:r=>r.use_flag?'<span class="bdg ok">사용</span>':'<span class="bdg off">중지</span>'}],
    fields:[['dept_code','부서코드','text'],['dept_desc','부서명','req'],['sort_key','정렬순서','num'],['use_flag','사용여부','chk'],['dept_desch','한자명','text'],['dept_from_ymd','적용시작','text'],['dept_to_ymd','적용종료','text'],['fin_dept_code','재무부서','text'],['fin_from_ymd','재무시작','text'],['fin_to_ymd','재무종료','text'],['enterprise_dept','전사부서','text'],['wh_code','창고','text'],['remarks','비고','text']],
    newDefaults:{use_flag:1,sort_key:0}},
  line:{sid:'basemaster',title:'라인 마스터',keyField:'line_no',listEp:'/api/line/list',saveEp:'/api/line/save',delEp:'/api/line/delete',org:'nx.line_no',
    cols:[{k:'line_no',h:'라인번호',cap:140},{k:'apply_ymd',h:'적용일'},{k:'maint_day',h:'리드일',cls:'num'},{k:'maint_hhmm',h:'변경시각',cls:'center',fmt:r=>{let v=String(r.maint_hhmm||'').replace(/\D/g,'');if(!v)return '';v=v.padStart(4,'0').slice(-4);return v.slice(0,2)+':'+v.slice(2);}},{k:'link_cust_name',h:'연결거래처',cap:160,fmt:r=>esc(r.link_cust_name||r.link_cust_code||'')},{k:'cust_maint_day',h:'거래처리드',cls:'num'}],
    fields:[['line_no','라인번호','req'],['apply_ymd','적용일(YYMMDD)','text'],['maint_day','리드일','num'],['maint_hhmm','변경시각(HHMM)','text'],['link_cust_code','연결거래처코드','text'],['cust_maint_day','거래처리드','num']],
    newDefaults:{maint_day:0,maint_hhmm:'0000'}},
};

/* ===== 라인별달력 (LG 라인스케줄 매트릭스 + 엑셀 업로드) — 생산계획 가동캘린더 ===== */
function lineCalView(host){
  const API=API_BASE;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date(), mon=new Date(T); mon.setDate(T.getDate()-((T.getDay()+6)%7));
  const st={data:null,from:iso(mon),weeks:4,anchor:iso(T),msg:'',busy:false};
  const codeSty=(v)=>{const c=(v||'').trim().toUpperCase();
    if(c==='B')return 'background:#e23b3b;color:#fff';
    if(c==='A'||c==='D')return 'background:#37cde6;color:#04303a';
    if(c==='E')return 'background:#232a33;color:#fff';
    if(!c)return 'background:#eaedf1;color:#c2c8d0';
    return 'background:#f3b0dd;color:#3a0b30';};   // 특수(SKD/rac이동/CC지원)
  const load=async()=>{
    try{const r=await fetch(`${API}/api/linecal/matrix?from_ymd=${st.from}&weeks=${st.weeks}`);st.data=await r.json();}
    catch(e){st.msg='백엔드 연결 실패';}
    render();};
  const doUpload=async(f)=>{
    if(!f)return;
    if(!st.anchor){alert('기준일(적용날짜)을 입력하세요');return;}
    st.busy=true;render();
    const fd=new FormData();fd.append('file',f);fd.append('anchor_ymd',st.anchor);
    try{const r=await fetch(`${API}/api/linecal/upload`,{method:'POST',body:fd});const j=await r.json();
      if(r.ok&&j.ok){st.msg=`✅ 업로드 완료: ${j.recs}건·특수일 ${j.events} (${j.date_from}~${j.date_to})`;
        // 업로드 기준일 주 월요일로 창 이동
        const a=new Date(j.anchor);a.setDate(a.getDate()-((a.getDay()+6)%7));st.from=iso(a);await load();}
      else{alert('업로드 실패: '+(j.detail||JSON.stringify(j)));}}
    catch(e){alert('업로드 오류: '+e);}
    st.busy=false;render();};
  const render=()=>{
    const ed=(typeof PERM!=='undefined')?PERM.canEdit('basemaster'):true;
    const d=st.data;
    host.innerHTML=`
     ${ed?`<div id="lc-drop" style="border:2px dashed #8fb4d6;border-radius:9px;padding:12px 14px;background:#f4f9fe;display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:8px">
        <span style="font-size:20px">📤</span>
        <b>LG 라인스케줄 엑셀</b>을 여기로 <b>드래그&드롭</b> 하거나
        <button class="btn" id="lc-pick">📁 파일 선택</button>
        <input type="file" id="lc-file" accept=".xlsx,.xls" style="display:none">
        <span style="margin-left:auto"></span>
        <label class="tl">기준일(적용날짜)</label><input class="inp" type="date" id="lc-anchor" value="${st.anchor}" style="width:150px">
        ${st.busy?'<span style="color:#1c47a0">⏳ 처리중…</span>':''}
      </div>`:`<div class="page-sub">🔒 업로드는 수정권한 필요 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</div>`}
     <div class="toolbar" style="gap:6px">
       <label class="tl">시작주(월)</label><input class="inp" type="date" id="lc-from" value="${st.from}" style="width:150px">
       <label class="tl">기간</label><select class="inp" id="lc-weeks" style="width:auto"><option value="4" ${st.weeks==4?'selected':''}>4주</option><option value="6" ${st.weeks==6?'selected':''}>6주</option><option value="8" ${st.weeks==8?'selected':''}>8주</option></select>
       <button class="btn" id="lc-go">🔍 조회</button>
       <span class="page-sub" style="margin:0 0 0 8px">B=<b style="color:#e23b3b">잔업3h</b> · A=<b style="color:#0aa">잔업2h</b> · E=잔업없음 · 빈칸=휴무</span>
       <div class="spacer"></div><span class="rowcount">${d?d.from+'~'+d.to:''}</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.includes('실패')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 340px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      ${d?`<table class="tbl" style="font-size:11px;border-collapse:collapse">
        <thead>
         <tr><th style="position:sticky;left:0;background:#eef2f7;z-index:2">구분</th><th>라인</th><th>No.</th><th>진도</th>
           ${d.dates.map(x=>`<th class="center" style="min-width:26px;${x.dow==='토'?'color:#2a6ad6':(x.dow==='일'?'color:#d63a3a':'')}">${x.mon}/${x.day}<br><span style="font-weight:400">${x.dow}</span></th>`).join('')}</tr>
         <tr><th colspan="4" style="position:sticky;left:0;background:#fff7e0;z-index:2;text-align:right;font-weight:600">특수일 ▶</th>
           ${d.dates.map(x=>`<td class="center" title="${esc((x.events||[]).join(','))}" style="font-size:9px;background:${x.events&&x.events.length?'#ffe9a8':'#fafbfc'};max-width:26px;overflow:hidden">${(x.events||[]).map(e=>esc(e.slice(0,2))).join('')}</td>`).join('')}</tr>
        </thead>
        <tbody>${d.lines.length?d.lines.map(L=>`<tr>
          <td style="position:sticky;left:0;background:#fff;white-space:nowrap">${esc(L.gubun)}</td>
          <td class="center"><b>${esc(L.line_no)}</b></td><td class="center">${esc(L.model_no)}</td><td class="center">${esc(L.jindo)}</td>
          ${d.dates.map(x=>{const v=L.cells[x.ymd]||'';return `<td class="center" title="${esc(x.ymd)} ${esc(v)}" style="${codeSty(v)};font-size:10px;padding:2px">${esc(v)}</td>`;}).join('')}
        </tr>`).join(''):`<tr><td colspan="${4+d.dates.length}" class="empty">데이터 없음 — 엑셀을 업로드하세요</td></tr>`}</tbody></table>`
       :`<div class="empty" style="padding:30px">불러오는 중…</div>`}</div>`;
    const g=id=>host.querySelector(id);
    g('#lc-go').onclick=()=>{st.from=g('#lc-from').value;st.weeks=+g('#lc-weeks').value;load();};
    if(ed){
      const drop=g('#lc-drop'),fi=g('#lc-file');
      g('#lc-pick').onclick=()=>fi.click();
      g('#lc-anchor').onchange=()=>{st.anchor=g('#lc-anchor').value;};
      fi.onchange=()=>{if(fi.files[0]){autoAnchor(fi.files[0].name);doUpload(fi.files[0]);}};
      drop.ondragover=e=>{e.preventDefault();drop.style.background='#e3f0ff';};
      drop.ondragleave=()=>{drop.style.background='#f4f9fe';};
      drop.ondrop=e=>{e.preventDefault();drop.style.background='#f4f9fe';const f=e.dataTransfer.files[0];if(f){autoAnchor(f.name);doUpload(f);}};
    }
  };
  const autoAnchor=(name)=>{const m=(name||'').match(/(20\d{6})/);if(m){const s=m[1];st.anchor=`${s.slice(0,4)}-${s.slice(4,6)}-${s.slice(6,8)}`;}};
  load();
}

/* ===== 근무달력/파트별달력 매트릭스 (nx.work_calendar/part_calendar) — 기본조회+수정 ===== */
const WS_STY={'1':{t:'잔2',c:'#2f9e55'},'2':{t:'정상',c:'#3aa76a'},'5':{t:'잔3',c:'#1f7a44'},'6':{t:'잔4',c:'#155c33'},'7':{t:'4h',c:'#6f9e52'},'3':{t:'일',c:'#e05a5a'},'4':{t:'휴',c:'#aeb6c2'}};
const WS_OPTS=[['','—'],['2','정상'],['1','잔업2h'],['5','잔업3h'],['6','잔업4h'],['7','4h근무'],['3','일요일'],['4','휴무']];
function wcalView(host,kind){
  const API=API_BASE;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date(),mon=new Date(T);mon.setDate(T.getDate()-((T.getDay()+6)%7));
  const st={data:null,from:iso(mon),weeks:4,edit:false,edits:{},cellEdit:null,msg:''};
  const cellSty=v=>{const w=WS_STY[(v||'').trim()];return w?`background:${w.c};color:#fff`:'background:#f1f3f6;color:#b8c0cc';};
  const cellTxt=v=>{const w=WS_STY[(v||'').trim()];return w?w.t:'';};
  const load=async()=>{try{const r=await fetch(`${API}/api/wcal/matrix?kind=${kind}&from_ymd=${st.from}&weeks=${st.weeks}`);st.data=await r.json();}catch(e){st.msg='백엔드 연결 실패';}render();};
  const val=(row,ymd)=>{const k=row.ent+'|'+ymd;return (k in st.edits)?st.edits[k]:(row.cells[ymd]||'');};
  const save=async()=>{
    const cells=Object.keys(st.edits).map(k=>{const[ent,ymd]=k.split('|');return{ent,ymd,ws:st.edits[k]};});
    if(!cells.length){st.edit=false;render();return;}
    try{const r=await fetch(`${API}/api/wcal/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,cells,user:'웹사용자'})});
      const j=await r.json();if(r.ok&&j.ok){st.msg=`✅ ${j.saved}건 저장`;st.edits={};st.edit=false;await load();}else alert('저장실패: '+(j.detail||''));}
    catch(e){alert('저장오류: '+e);}};
  const render=()=>{
    const ed=(typeof PERM!=='undefined')?PERM.canEdit('basemaster'):true;
    const d=st.data;
    host.innerHTML=`
     <div class="toolbar" style="gap:6px;flex-wrap:wrap">
       <label class="tl">시작주(월)</label><input class="inp" type="date" id="wc-from" value="${st.from}" style="width:150px">
       <label class="tl">기간</label><select class="inp" id="wc-weeks" style="width:auto"><option value="4" ${st.weeks==4?'selected':''}>4주</option><option value="6" ${st.weeks==6?'selected':''}>6주</option><option value="8" ${st.weeks==8?'selected':''}>8주</option></select>
       <button class="btn" id="wc-go">🔍 조회</button>
       ${st.edit?`<button class="btn" id="wc-save" style="background:#1b6ec2;color:#fff">💾 저장</button><button class="btn" id="wc-cancel">취소</button>`
         :(ed?`<button class="btn" id="wc-edit" style="background:#1c7c3a;color:#fff">✎ 수정</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음</span>`)}
       <span class="page-sub" style="margin:0 0 0 8px">정상/잔업=<b style="color:#2f9e55">근무</b> · <b style="color:#e05a5a">일</b> · <b style="color:#8a95a5">휴</b> ${st.edit?'· <b>셀 클릭→선택</b>':''}</span>
       <div class="spacer"></div><span class="rowcount">${d?d.from+'~'+d.to:''}</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.includes('실패')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 320px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      ${d?`<table class="tbl" style="font-size:11px;border-collapse:collapse">
        <thead><tr><th style="position:sticky;left:0;background:#dfe7f2;z-index:2;min-width:120px">${kind==='work'?'근무팀':'파트'}</th>
          ${d.dates.map(x=>`<th class="center" style="min-width:44px;${x.dow==='토'?'background:#ffe0b0':(x.dow==='일'?'background:#ffd0d0':'')}">${x.mon}/${String(x.day).padStart(2,'0')}<br><span style="font-weight:400">${x.dow}</span></th>`).join('')}</tr></thead>
        <tbody>${d.rows.map(row=>`<tr>
          <td style="position:sticky;left:0;background:${row.common?'#3d6fc0':(row.indent?'#fff':'#eef3fb')};${row.common?'color:#fff;font-weight:700':(row.indent?'':'font-weight:700')};white-space:nowrap;text-align:${row.indent?'left':'center'};padding-left:${(row.indent||0)*18+8}px">${esc(row.name)}</td>
          ${d.dates.map(x=>{const v=val(row,x.ymd),ck=row.ent+'|'+x.ymd;
            if(st.edit&&st.cellEdit===ck){return `<td class="center" style="padding:0"><select class="wc-sel" data-k="${esc(ck)}" style="width:100%;font-size:10px">${WS_OPTS.map(o=>`<option value="${o[0]}" ${o[0]===v?'selected':''}>${o[1]}</option>`).join('')}</select></td>`;}
            return `<td class="center ${st.edit?'wc-cell':''}" data-k="${esc(ck)}" title="${esc((d.decode&&d.decode[v])||'')}" style="${cellSty(v)};font-size:10px;padding:2px;${st.edit?'cursor:pointer':''}">${esc(cellTxt(v))}</td>`;}).join('')}
        </tr>`).join('')}</tbody></table>`:`<div class="empty" style="padding:30px">불러오는 중…</div>`}</div>`;
    const g=id=>host.querySelector(id);
    g('#wc-go').onclick=()=>{st.from=g('#wc-from').value;st.weeks=+g('#wc-weeks').value;st.edits={};st.cellEdit=null;load();};
    if(st.edit){
      g('#wc-save').onclick=save;
      g('#wc-cancel').onclick=()=>{st.edit=false;st.edits={};st.cellEdit=null;render();};
      host.querySelectorAll('.wc-cell').forEach(td=>td.onclick=()=>{st.cellEdit=td.dataset.k;render();
        const sel=host.querySelector('.wc-sel');if(sel){sel.focus();sel.onchange=()=>{st.edits[sel.dataset.k]=sel.value;st.cellEdit=null;render();};sel.onblur=()=>{st.cellEdit=null;render();};}});
    }else if(ed){const eb=g('#wc-edit');if(eb)eb.onclick=()=>{st.edit=true;render();};}
    attachResizers(host);
  };
  load();
}

/* ================= 품질(QUALITY) 모듈 ================= */
/* 공용 읽기전용 그리드(라이브 레거시 조회 / IQC 조회). cfg={listEp,buildQS,cols,dateLabel,filters,days,filt0,sum,onRow} */
function qcRead(host, cfg){
  const API=API_BASE;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date(), back=cfg.days||30;
  const st={F:Object.assign({from:iso(new Date(T.getFullYear(),T.getMonth(),1)),to:iso(T)},cfg.filt0||{}),
            data:{rows:[],cnt:0}, loading:false, msg:'', sel:null, sub:null};
  const load=async()=>{st.loading=true;st.sub=null;render();
    try{const r=await fetch(`${API}${cfg.listEp}?`+new URLSearchParams(cfg.buildQS(st.F)));st.data=await r.json();st.msg='';}
    catch(e){st.msg='백엔드 연결 실패 — uvicorn app:app --port 8010';st.data={rows:[],cnt:0};}
    st.loading=false;render();};
  const pickRow=async(r)=>{if(!cfg.onRow)return;st.sel=r;st.sub={loading:true};render();
    try{st.sub=await cfg.onRow(r);}catch(e){st.sub={rows:[],err:1};}render();};
  const render=()=>{
    const d=st.data;
    host.innerHTML=`
     <div class="toolbar">
       <label class="tl">${cfg.dateLabel||'기간'}</label>
       <input class="inp" type="date" id="qr-from" value="${st.F.from}"> ~ <input class="inp" type="date" id="qr-to" value="${st.F.to}">
       ${qfFields(cfg.filters,st.F,'qr-f-')}
       <button class="btn" id="qr-search">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">${_wnf(d.cnt||0)}건${cfg.sum?(' · '+cfg.sum(d)):''}</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(st.msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - ${cfg.onRow?430:330}px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:11px"><thead><tr>${cfg.cols.map(col=>`<th class="${col.cls||''}">${col.h}</th>`).join('')}</tr></thead>
      <tbody>${st.loading?spinRow(cfg.cols.length):((d.rows&&d.rows.length)?d.rows.map((r,i)=>`<tr class="qr-row${st.sel===r?' sel':''}" data-i="${i}" ${cfg.onRow?'style="cursor:pointer"':''}>
        ${cfg.cols.map(col=>`<td class="${col.cls||''}" ${col.title?`title="${esc(r[col.title]||'')}"`:''} ${col.cap?'style="max-width:150px;overflow:hidden;text-overflow:ellipsis"':''}>${col.fmt?col.fmt(r):esc(r[col.k]??'')}</td>`).join('')}
       </tr>`).join(''):`<tr><td colspan="${cfg.cols.length}" class="empty">조회 결과 없음</td></tr>`)}</tbody></table></div>
     ${cfg.onRow?`<div style="margin-top:8px">${st.sub?(st.sub.loading?'<div class="page-sub">상세 조회중…</div>':cfg.subView(st.sub,st.sel)):'<div class="page-sub" style="color:#8aa0bd">※ 행을 클릭하면 검사 상세치수가 표시됩니다.</div>'}</div>`:''}
     <style>.qr-row.sel{background:#e8f0ff}.qr-row:hover{background:#eef4ff}</style>`;
    const g=id=>host.querySelector(id);
    const doSearch=()=>{st.F.from=g('#qr-from').value;st.F.to=g('#qr-to').value;qfRead(host,cfg.filters,st.F,'qr-f-');load();};
    g('#qr-search').onclick=doSearch;
    qfBind(host,cfg.filters,st.F,'qr-f-',doSearch);
    if(cfg.onRow)host.querySelectorAll('.qr-row').forEach(el=>el.onclick=()=>pickRow(d.rows[+el.dataset.i]));
  };
  load();
}
const _d8iso=s=>{s=''+(s||'');return s.length===8?s.slice(0,4)+'-'+s.slice(4,6)+'-'+s.slice(6,8):(s.length===6?'20'+s.slice(0,2)+'-'+s.slice(2,4)+'-'+s.slice(4,6):s);};
const _d8disp=s=>{s=''+(s||'');return s.length===8?s.slice(2,4)+'/'+s.slice(4,6)+'/'+s.slice(6,8):_wymd(s);};

/* 품질 ①: 품질불량관리 (w_qa_input_025) — QA_T_ERROR(라이브) ↔ nx.qc_error(신규편집) */
// 불량구분/작업처/색깔 코드→이름 (레거시 dw_qa_input_020 정본)
const QC_TAG=[{v:'1',t:'LQC불량'},{v:'2',t:'고객사불량'},{v:'3',t:'IQC불량'},{v:'4',t:'초품불량'},{v:'5',t:'OQC불량'},{v:'8',t:'가공'},{v:'A',t:'자주순차'},{v:'9',t:'기타'}];
const QC_WORK=[{v:'P2',t:'가공'},{v:'P1',t:'용접'},{v:'D1',t:'직납'}];
const QC_COLOR=[{v:'1',t:'검정'},{v:'2',t:'회색'},{v:'3',t:'파랑'}];
const QC_YN=[{v:'0',t:'아니오'},{v:'1',t:'예'}];
const QC_BIZ=[{v:'DGZ',t:'DGZ'},{v:'DMZ',t:'DMZ'}];
const QC_PGREG=[{v:'내부용',t:'내부용'},{v:'보고용',t:'보고용'}];
const _pgreg=v=>v==='1'?'전산':(v==='0'||v===''?'':esc(v));  // 레거시1/0 vs nx 내부용/보고용

/* ===== 레거시 스타일 기준일자 위젯(재사용): ‹ YY/MM/DD › 📅 =====
   여러 레거시 조회화면(pr_outside 계열 등) 공용. 표시=YY/MM/DD, 내부값=YYYY-MM-DD(기존 로직 호환).
   사용: 1) HTML에 legacyDateHTML(id, isoValue) 삽입  2) draw 후 bindLegacyDate(container, id, ()=>현재iso, (newIso)=>{반영+재조회})
   ‹/› = ±1일, 📅/날짜클릭 = 달력선택. onSet 콜백에서 값갱신+load() 하면 자동 재조회. */
function _isoAddDays(iso,n){var d=new Date((iso||'')+'T00:00:00');if(isNaN(d.getTime()))return iso;d.setDate(d.getDate()+n);var p=function(x){return String(x).padStart(2,'0');};return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate());}
function _isoToYYMMDD(iso){var s=(iso||'').split('-');return s.length===3?(s[0].slice(2)+'/'+s[1]+'/'+s[2]):(iso||'');}
function legacyDateHTML(id,iso){
  return '<span class="ldf" style="display:inline-flex;align-items:center;gap:0;border:1px solid var(--line-2,#c9d3e0);border-radius:6px;padding:0 1px;background:#fff;vertical-align:middle;height:26px">'
    +'<button type="button" id="'+id+'-prev" title="전일" style="border:0;background:transparent;cursor:pointer;font-size:16px;line-height:1;padding:2px 7px;color:#33507d">‹</button>'
    +'<span id="'+id+'-disp" title="클릭하면 달력" style="min-width:78px;text-align:center;font-family:monospace;font-size:13px;cursor:pointer;user-select:none">'+esc(_isoToYYMMDD(iso))+'</span>'
    +'<button type="button" id="'+id+'-next" title="익일" style="border:0;background:transparent;cursor:pointer;font-size:16px;line-height:1;padding:2px 7px;color:#33507d">›</button>'
    +'<label title="달력" style="cursor:pointer;position:relative;display:inline-flex;align-items:center;padding:0 4px">📅'
      +'<input type="date" id="'+id+'-cal" value="'+esc(iso||'')+'" style="position:absolute;left:0;top:0;width:100%;height:100%;opacity:0;cursor:pointer">'
    +'</label></span>';
}
function bindLegacyDate(root,id,getIso,onSet){
  var qy=function(s){return root.querySelector(s);};
  var prev=qy('#'+id+'-prev'),next=qy('#'+id+'-next'),cal=qy('#'+id+'-cal'),disp=qy('#'+id+'-disp');
  if(prev)prev.onclick=function(){onSet(_isoAddDays(getIso(),-1));};
  if(next)next.onclick=function(){onSet(_isoAddDays(getIso(),1));};
  if(cal)cal.onchange=function(e){if(e.target.value)onSet(e.target.value);};
  if(disp)disp.onclick=function(){try{cal.showPicker();}catch(err){cal.focus();cal.click();}};
}
// 조회 그리드 전체 컬럼(레거시 순서, 전부 이름)
const qcCols=[
  {h:'구분',k:'tag_nm',cls:'center'},
  {h:'고객사라인',k:'cust_line',cls:'center'},
  {h:'사업부',k:'division',cls:'center'},
  {h:'전산등록',cls:'center',fmt:r=>_pgreg(r.pg_reg)},
  {h:'불량일자',cls:'center',fmt:r=>_wymd(r.error_ymd)},
  {h:'P/No',fmt:r=>`<b>${esc(r.item_code)}</b>`},
  {h:'품명',k:'item_desc',cap:1,title:'item_desc'},
  {h:'작업처',k:'work_nm',cls:'center'},
  {h:'생산파트',k:'part_nm',cls:'center'},
  {h:'생산설비',k:'mach_nm',cap:1,title:'mach_nm'},
  {h:'협력사',k:'partner_nm',cap:1,title:'partner_nm'},
  {h:'검사자',k:'inspector',cls:'center'},
  {h:'원인자',k:'error_member',cls:'center'},
  {h:'불량항목1',k:'ei1'},{h:'불량항목2',k:'ei2'},{h:'불량항목3',k:'ei3'},
  {h:'불량내용',cap:1,title:'error_desc',fmt:r=>`<span style="color:${r.color==='2'?'#888':(r.color==='3'?'#1a4fd0':'#111')};font-weight:600">${esc(r.error_desc)}</span>`},
  {h:'Lot',cls:'num',fmt:r=>_wnf(r.lot_qty)},
  {h:'불량수량',cls:'num',fmt:r=>`<b style="color:#c0392b">${_wnf(r.error_qty)}</b>`},
  {h:'실불량',cls:'num',fmt:r=>_wnf(r.real_qty)},
  {h:'원인',k:'error_cause',cap:1,title:'error_cause'},
  {h:'진행상황',k:'progress',cap:1,title:'progress'},
  {h:'수몰여부',cls:'center',fmt:r=>r.water_flag?'✔':''},
  {h:'재검사',cls:'center',fmt:r=>r.reinsp_flag?'✔':''},
  {h:'완료여부',cls:'center',fmt:r=>r.finish_flag?'✔':''},
];
const _all=o=>[{v:'',t:'전체'},...o];
const qcFilters=[{k:'tag',label:'불량구분',type:'select',opts:_all(QC_TAG)},{k:'cust_line',label:'고객사라인',type:'auto',optKind:'line',width:120},
  {k:'division',label:'사업부',type:'select',opts:_all(QC_BIZ)},{k:'item',label:'품번',width:120},
  {k:'work',label:'작업처',type:'select',opts:_all(QC_WORK)},{k:'partner',label:'협력사',type:'auto',optKind:'partner',width:140},
  {k:'finish',label:'완료여부',type:'select',opts:[{v:'',t:'전체'},{v:'1',t:'완료'},{v:'0',t:'미완료'}]}];
const qcQS=(F,src)=>({from_ymd:F.from,to_ymd:F.to,tag:F.tag||'',cust_line:F.cust_line||'',division:F.division||'',
  item:F.item||'',work:F.work||'',partner:F.partner||'',finish:F.finish||'',src});

/* 품질 ②: 시방변경관리 (w_qa_spec) — QA_T_SPEC_REV(라이브) ↔ nx.qc_spec_rev(신규편집) */
const _atypeNm=v=>({'1':'즉시적용','2':'재고소진후','3':'지정일'}[String(v||'').trim()]||String(v||'').trim());

/* ================= 로그인 ================= */
// 헤더 우측 사용자 표시 + 로그아웃 (로그인 사용자 실시간 반영)
function updateHeaderUser(){
  const el=document.querySelector('.hd-user'); if(!el)return;
  const u=PERM.currentUser();
  el.innerHTML=`<span class="avatar">${esc((u.nm||'?').slice(0,1))}</span> <span>${esc(u.nm||'')}님</span>`
    +`<span class="muted" style="margin:0 8px">${esc(u.dept||u.partner||'')}${PERM.isAdmin()?' · 전권':''}</span>`
    +`<button id="btnLogout" class="btn" style="padding:2px 10px;font-size:12px">로그아웃</button>`;
  const lo=el.querySelector('#btnLogout'); if(lo)lo.onclick=doLogout;
}
function doLogout(){ if(!confirm('로그아웃 하시겠습니까?'))return;
  sessionStorage.removeItem('perm_authed'); location.reload(); }
