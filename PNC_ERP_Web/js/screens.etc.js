/* ===== PNC ERP screens.etc.js — 협력사/경영/시스템 SCREEN (app.js 분할, 순수이동) ===== */

/* 시스템관리 > 마감관리 — 일/월마감 현황(잠금상태) + 실행·취소. 실제 마감은 쓰기라 운영DB(읽기전용)엔 불가 → 신규DB/백엔드에서 */
SCREEN.close=(c)=>{
  const API=API_BASE;
  c.innerHTML=`<div class="page-title">🔒 마감관리</div><div class="empty" style="padding:40px">${SPIN}마감현황 라이브 로딩…</div>`;
  (async()=>{
  let cs=[], asof='', cur='';
  try{const r=await fetch(`${API}/api/live/closestatus`);if(!r.ok)throw 0;const j=await r.json();
    cs=j.rows||[];const a=(''+(j.asof||'')).trim();asof=a.length>=6?`20${a.slice(0,2)}-${a.slice(2,4)}-${a.slice(4,6)}`:'';cur=j.curym||'';}
  catch(e){cs=DB.closeStatus||[];asof=DB.closeAsof||'2026-07-18';cur=DB.curYm||'2607';}
  const ymN=y=>{y=(''+(y||''));return y.length>=4?(2000+ +y.slice(0,2))*12 + +y.slice(2,4):null;};
  const prevYm=ymN(cur)-1;   // 직전월(정상 마감 기준)
  const fmtYm=y=>{y=(''+(y||''));return y.length>=4?`20${y.slice(0,2)}-${y.slice(2,4)}`:'-';};
  const fmtYmd=y=>{y=(''+(y||''));return y.length>=6?`20${y.slice(0,2)}/${y.slice(2,4)}/${y.slice(4,6)}`:'-';};
  const stat=r=>{
    if(!r.last||r.last==='None'||r.last==='nan'||r.last==='NaT')return{t:'미마감',cls:'bad',behind:'—'};
    if(r.ctype==='월'){const b=prevYm-ymN(r.last); return b<=0?{t:'정상',cls:'ok',behind:'0'}:{t:`지연 ${b}개월`,cls:'bad',behind:b};}
    // 일마감: 기준일 근처면 정상
    const a=(''+asof).replace(/-/g,'').slice(2); return r.last>=(''+(+a-3))?{t:'정상',cls:'ok',behind:'0'}:{t:'지연',cls:'bad',behind:'—'};
  };
  const nBad=cs.filter(r=>stat(r).cls==='bad').length;
  c.innerHTML=`
   <div class="page-title">🔒 마감관리</div>
   <div class="page-sub">일/월 마감 현황 및 실행 · 기준일 ${esc(asof)} · <b>마감 = 잠금</b>(마감된 기간의 전표는 수정·삭제 불가, 소급분은 당월 소급조정)</div>
   ${nBad?`<div class="summary-bar" style="border-color:#e0b4b4;background:#fdf3f3"><div class="s-item neg">⚠ 미마감/지연 ${nBad}건 — 마감 프로세스 점검 필요 (예: 생산·영업 월마감이 2025.2에 멈춤)</div></div>`:''}
   <div class="grid-wrap" style="max-height:340px;overflow:auto;margin-bottom:14px"><table class="tbl fit"><thead>
     <tr><th>영역</th><th class="center">마감유형</th><th class="center">최종 마감</th><th class="center">상태</th><th>원본 테이블</th><th class="center">실행</th><th class="center">마감취소</th></tr></thead>
     <tbody>${cs.map(r=>{const s=stat(r);const disp=r.ctype==='월'?fmtYm(r.last):fmtYmd(r.last);
       return `<tr><td><b>${esc(r.name||r.domain)}</b></td><td class="center">${esc(r.ctype)}마감</td><td class="center">${(r.last&&r.last!=='None')?esc(disp):'<span style="color:#c0392b">없음</span>'}</td>
        <td class="center"><span class="badge ${s.cls==='ok'?'b-green':'b-red'}">${esc(s.t)}</span></td>
        <td><code>${esc(r.tbl)}</code></td>
        <td class="center"><button class="btn xs act" data-run="${esc(r.name)}|${esc(r.ctype)}">마감 실행</button></td>
        <td class="center"><button class="btn xs ghost act" data-cancel="${esc(r.name)}|${esc(r.ctype)}">취소</button></td></tr>`;}).join('')}</tbody></table></div>
   <div class="page-sub" style="font-weight:700;margin:6px 0">수동 마감 실행</div>
   <div class="toolbar">
     <label class="tl">일마감 대상일</label><input type="date" class="inp" id="dday" value="${nowCD()}" style="min-width:135px">
     <button class="btn" id="runday">일마감 실행</button><button class="btn ghost" id="canday">일마감 취소</button>
     <span style="width:18px"></span>
     <label class="tl">월마감 대상월</label><input type="month" class="inp" id="dmon" value="${nowCM()}" style="min-width:120px">
     <button class="btn" id="runmon">월마감 실행</button><button class="btn ghost" id="canmon">월마감 취소</button>
   </div>
   <div class="page-sub" style="font-weight:700;margin:16px 0 6px">일자별 마감 캘린더</div>
   <div class="toolbar" style="border:none;padding:0;margin-bottom:8px">
     <label class="tl">조회월</label><input type="month" class="inp" id="calm" value="${nowCM()}" style="min-width:120px">
     <span style="font-size:12px;color:var(--muted)">🟩 마감완료 · ⬜ 미마감 · 파란테두리=오늘 · 날짜 클릭 시 일마감 실행/취소</span>
   </div>
   <div class="grid-wrap" style="overflow:auto;border:none"><table class="cal"><thead><tr>${['일','월','화','수','목','금','토'].map(d=>`<th>${d}</th>`).join('')}</tr></thead><tbody id="calbody"></tbody></table></div>
   <div class="page-sub" style="margin-top:12px;color:var(--muted)">※ 마감 실행/취소는 <b>쓰기 작업</b>입니다. 현재 운영 DB(PARTNER_ERP)는 <b>읽기 전용</b>이라 실제 실행은 차세대 ERP 신규 DB(또는 백엔드) 연결 후 활성화됩니다. 이 화면은 현재 마감 상태를 <b>가시화</b>합니다.</div>`;
  // 일마감 캘린더
  const dailyRow=cs.find(r=>r.ctype==='일')||{}; const dLast=(''+(dailyRow.last||'')).trim();  // 예 260717
  const dCloseYmm=dLast.length>=6?dLast.slice(0,4):'', dCloseDay=dLast.length>=6?+dLast.slice(4,6):0;
  const asofYmd=(''+asof).replace(/-/g,'').slice(2);  // 260718
  const renderCal=ym=>{
    const [Y,M]=ym.split('-').map(Number); const ymm=String(Y).slice(2)+String(M).padStart(2,'0');
    const first=new Date(Y,M-1,1).getDay(), days=new Date(Y,M,0).getDate();
    let cells=[]; for(let i=0;i<first;i++)cells.push('<td class="empty"></td>');
    for(let d=1;d<=days;d++){
      const ymd=ymm+String(d).padStart(2,'0');
      let closed;
      if(ymm<dCloseYmm)closed=true; else if(ymm===dCloseYmm)closed=(d<=dCloseDay); else closed=false;
      const future=ymd>asofYmd, today=ymd===asofYmd;
      const dow=(first+d-1)%7; const cls=[dow===0?'sun':'',dow===6?'sat':'',closed?'closed':(future?'future':'open'),today?'today':''].filter(Boolean).join(' ');
      const mk=closed?'<div class="mk">🟩 마감</div>':(future?'':'<div class="mk">⬜ 미마감</div>');
      cells.push(`<td class="${cls}" ${future?'':`data-day="${ymd}"`}><span class="dn">${d}</span>${mk}</td>`);
    }
    while(cells.length%7)cells.push('<td class="empty"></td>');
    let html=''; for(let i=0;i<cells.length;i+=7)html+='<tr>'+cells.slice(i,i+7).join('')+'</tr>';
    c.querySelector('#calbody').innerHTML=html;
    c.querySelectorAll('.cal td[data-day]').forEach(td=>td.onclick=()=>{const y=td.dataset.day;const isC=td.classList.contains('closed');
      ph(`${'20'+y.slice(0,2)}/${y.slice(2,4)}/${y.slice(4,6)} 일마감을 ${isC?'취소':'실행'}합니다.`);});
  };
  c.querySelector('#calm').onchange=e=>renderCal(e.target.value);
  renderCal(nowCM());
  const ph=(msg)=>alert(msg+'\n\n※ 마감은 쓰기 작업이라 운영DB(읽기전용)에선 실행할 수 없습니다.\n차세대 ERP 신규 DB/백엔드 연결 후 활성화됩니다.');
  c.querySelectorAll('[data-run]').forEach(b=>b.onclick=()=>{const[n,t]=b.dataset.run.split('|');ph(`[${n}] ${t}마감을 실행합니다.`);});
  c.querySelectorAll('[data-cancel]').forEach(b=>b.onclick=()=>{const[n,t]=b.dataset.cancel.split('|');ph(`[${n}] ${t}마감을 취소(재개방)합니다.`);});
  c.querySelector('#runday').onclick=()=>ph(`${c.querySelector('#dday').value} 일마감을 실행합니다.`);
  c.querySelector('#canday').onclick=()=>ph(`${c.querySelector('#dday').value} 일마감을 취소합니다.`);
  c.querySelector('#runmon').onclick=()=>ph(`${c.querySelector('#dmon').value} 월마감을 실행합니다.`);
  c.querySelector('#canmon').onclick=()=>ph(`${c.querySelector('#dmon').value} 월마감을 취소합니다.`);
  attachResizers(c);
  })();
};

/* 시스템관리 > 권한관리 — master-detail: 우 사용자리스트 클릭 → 좌 그 사용자의 부문별/프로그램별 조회·수정 그리드 */
SCREEN.perm=(c)=>{
  const progs=allPrograms();
  const users0=getUsers();
  let selUid=(users0.find(u=>!(u.roles||[]).includes('시스템관리자'))||users0[0]||{}).id;
  const draw=()=>{
    const users=getUsers();
    c.innerHTML=`
      <div class="page-title">🔑 권한관리</div>
      <div class="page-sub">오른쪽 <b>사용자 클릭</b> → 왼쪽에 그 사용자의 <b>부문별·프로그램별 조회/수정 권한</b> · 시스템관리자=전권(설정불가) · <b>조회 해제 시 그 메뉴는 사이드바에서 숨김</b> · 기본=조회O·수정X · 저장(브라우저 임시)</div>
      <div style="display:flex;gap:14px;align-items:flex-start">
        <div style="flex:0 0 340px;width:340px">
          <div class="sum-box" style="margin-bottom:8px"><span class="k">사용자</span> <b id="ucnt">${users.length}</b> 명 <span style="color:var(--muted);font-size:12px">(클릭하여 선택)</span></div>
          <div class="toolbar" style="margin-bottom:6px"><input class="inp" id="q" placeholder="이름·ID·부서 검색" style="width:100%"></div>
          <div class="grid-wrap" style="max-height:560px;overflow:auto"><div id="ulist"></div></div>
        </div>
        <div style="flex:1 1 auto;min-width:0" id="detail"></div>
      </div>`;
    const renderList=()=>{
      const q=(c.querySelector('#q').value||'').toLowerCase();
      const vis=users.filter(u=>!q||(''+u.id+u.nm+(u.dept||'')+(u.partner||'')).toLowerCase().includes(q));
      c.querySelector('#ucnt').textContent=vis.length;
      c.querySelector('#ulist').innerHTML=vis.map(u=>{const adm=(u.roles||[]).includes('시스템관리자');const on=u.id===selUid;
        return `<div class="urow" data-uid="${esc(u.id)}" style="padding:8px 10px;border-bottom:1px solid var(--line);cursor:pointer;${on?'background:#eef4ff;border-left:3px solid var(--brand,#2a6df4)':'border-left:3px solid transparent'}">
          <div style="font-weight:600">${esc(u.nm)} <span style="color:#bbb;font-weight:400;font-size:12px">${esc(u.id)}</span>${adm?' <span class="badge">전권</span>':''}${PERM.userId===u.id?' <span class="badge" style="background:#2e7d32;color:#fff;border:none">로그인</span>':''}</div>
          <div style="font-size:11px;color:var(--muted)">${esc(u.type||'')}·${esc(u.dept||u.partner||'-')} · ${esc((u.roles||[]).join('/')||'-')}</div></div>`;}).join('')||`<div class="empty" style="padding:24px">해당 사용자 없음</div>`;
      c.querySelectorAll('.urow').forEach(r=>r.onclick=()=>{selUid=r.dataset.uid;renderList();renderDetail();});
    };
    const renderDetail=()=>{
      const box=c.querySelector('#detail');
      const u=users.find(x=>x.id===selUid);
      if(!u){box.innerHTML='<div class="empty" style="padding:60px">오른쪽에서 사용자를 선택하세요.</div>';return;}
      const admin=(u.roles||[]).includes('시스템관리자');
      const pm=PERM.perms[selUid]=PERM.perms[selUid]||{};
      // ★역할(부서) 기본권한 반영 — 실제 로그인 시 권한과 동일하게 표시(자재는 자재만 체크)
      const roleHas=(sid)=>(u.roles||[]).some(r=>(ROLE_MOD[r]||[]).includes(_sid2mod(sid)));
      const effView=(sid)=>admin||(pm[sid]&&pm[sid].view!==undefined?pm[sid].view:roleHas(sid));
      const effEdit=(sid)=>admin||(pm[sid]&&pm[sid].edit!==undefined?pm[sid].edit:roleHas(sid));
      const nv=progs.filter(p=>effView(p.id)).length;
      const ne=progs.filter(p=>effEdit(p.id)).length;
      box.innerHTML=`
        <div class="sum-box" style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
          <b style="font-size:15px">${esc(u.nm)}</b>
          <span style="color:var(--muted);font-size:12px">${esc(u.id)} · ${esc(u.type||'')}·${esc(u.dept||u.partner||'-')} · 역할 ${esc((u.roles||[]).join('/')||'-')}</span>
          <span style="margin-left:auto"><span class="k">조회</span> <b id="dnv">${nv}</b> · <span class="k">수정</span> <b id="dne">${ne}</b> / 전체 ${progs.length}</span>
        </div>
        <div class="toolbar">
          ${admin?'<span class="badge">시스템관리자 = 전권(설정 불가)</span>':`<button class="btn" id="psave">💾 저장</button>`}
          <div class="spacer"></div>
          <button class="btn ${PERM.userId===selUid?'':'ghost'}" id="plogin">${PERM.userId===selUid?'✅ 현재 로그인':'🔓 이 사용자로 로그인'}</button></div>
        <div class="grid-wrap" style="max-height:500px;overflow:auto"><table class="tbl fit"><thead><tr><th>부문</th><th>프로그램</th><th class="center" style="width:64px">조회</th><th class="center" style="width:64px">수정</th></tr></thead><tbody id="ptb"></tbody></table></div>`;
      const rendGrid=()=>{
        let html='';
        MODULES.forEach(m=>{const subs=m.subs||[];subs.forEach((s,idx)=>{const v=effView(s.id),e=effEdit(s.id);
          html+=`<tr>${idx===0?`<td rowspan="${subs.length}" style="background:#fafbff;font-weight:600;vertical-align:top;white-space:nowrap">${esc(m.nm)}</td>`:''}
            <td><b>${esc(s.nm)}</b> <span style="color:#ccc;font-size:11px">${esc(s.id)}</span></td>
            <td class="center"><input type="checkbox" data-p="${s.id}" data-a="view" ${v?'checked':''} ${admin?'disabled':''}></td>
            <td class="center"><input type="checkbox" data-p="${s.id}" data-a="edit" ${e?'checked':''} ${admin?'disabled':''}></td></tr>`;});});
        box.querySelector('#ptb').innerHTML=html;
        if(!admin)box.querySelectorAll('#ptb input').forEach(cb=>cb.onchange=()=>{const pid=cb.dataset.p,a=cb.dataset.a;pm[pid]=pm[pid]||{};pm[pid][a]=cb.checked;if(a==='edit'&&cb.checked)pm[pid].view=true;if(a==='view'&&!cb.checked)pm[pid].edit=false;rendGrid();updCnt();});
      };
      const updCnt=()=>{box.querySelector('#dnv').textContent=progs.filter(p=>effView(p.id)).length;box.querySelector('#dne').textContent=progs.filter(p=>effEdit(p.id)).length;};
      rendGrid();
      box.querySelector('#plogin').onclick=()=>{PERM.setUser(selUid);try{buildTree();updateHeaderUser();}catch(_){}renderList();renderDetail();};
      if(!admin){
        box.querySelector('#psave').onclick=async(ev)=>{const bt=ev.target;const t0=bt.textContent;bt.textContent='저장중…';bt.disabled=true;
          let ok=false;try{const r=await PERM.savePerms();ok=!r||r.ok!==false&&(r.status?r.ok:true);}catch(_){ok=false;}
          if(PERM.userId===selUid){try{buildTree();}catch(_){}}bt.textContent=t0;bt.disabled=false;
          alert(ok?u.nm+' 권한 저장 완료 — 서버 반영(전 PC 동일 적용).':u.nm+' 권한 로컬 저장됨(서버 저장 실패 — 네트워크 확인).');};
      }
    };
    c.querySelector('#q').onkeyup=renderList;
    renderList(); renderDetail();
  };
  draw();
};

/* 시스템관리 > 사용자관리 — 계정(ID/PW/이름/구분/부서/직책/역할복수/협력사/이메일/연락처/상태) */
SCREEN.users=(c)=>{
  const lsu='perm_users';
  const load=()=>getUsers();
  let users=load(), editMode=false;
  const CT=['내부','협력사'], ST=['사용','정지'];
  const cols=[{f:'id',h:'ID'},{f:'pw',h:'비밀번호',pw:1},{f:'nm',h:'이름'},{f:'type',h:'구분',sel:CT},{f:'dept',h:'부서'},{f:'pos',h:'직책'},{f:'roles',h:'역할',roles:1},{f:'partner',h:'협력사'},{f:'email',h:'이메일'},{f:'tel',h:'연락처'},{f:'status',h:'상태',sel:ST}];
  const draw=()=>{
    c.innerHTML=`
     <div class="page-title">👤 사용자관리</div>
     <div class="page-sub">계정 · 필수: <b>ID·비밀번호·이름·구분·역할</b> · 내부직원 ~60명 + 협력사 · <span class="neg">비번은 프로토타입 평문(실서비스 bcrypt 해시 예정)</span> · 프로그램별 조회/수정 권한은 「권한관리」 · ✎수정 시 편집</div>
     <div class="toolbar"><input class="inp" id="q" placeholder="ID·이름·부서·협력사">
       ${editMode?`<button class="btn" id="add">➕ 추가</button><button class="btn" id="save">💾 저장</button><button class="btn ghost" id="cancel">✖ 취소</button>`:(PERM.canEdit('users')?`<button class="btn" id="edit">✎ 수정</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc(PERM.label())})</span>`)}
       <div class="spacer"></div><span class="rowcount" id="cnt"></span></div>
     <div class="grid-wrap" style="max-height:520px;overflow:auto"><table class="tbl fit"><thead><tr>${cols.map(cc=>`<th>${cc.h}</th>`).join('')}${editMode?'<th class="center">삭제</th>':''}</tr></thead><tbody id="tb"></tbody></table></div>`;
    const disp=(cc,u)=>{ if(cc.pw)return '••••'; if(cc.roles)return (u.roles||[]).map(r=>`<span class="badge">${esc(r)}</span>`).join(' '); return esc(''+(u[cc.f]||'')); };
    const editCell=(cc,u,i)=>{
      if(cc.sel)return `<select data-i="${i}" data-f="${cc.f}">${cc.sel.map(o=>`<option ${u[cc.f]===o?'selected':''}>${esc(o)}</option>`).join('')}</select>`;
      if(cc.roles)return `<div style="min-width:150px">${ROLES.map(r=>`<label style="margin-right:6px;white-space:nowrap;font-size:11px"><input type="checkbox" data-i="${i}" data-role="${esc(r)}" ${(u.roles||[]).includes(r)?'checked':''}>${esc(r)}</label>`).join('')}</div>`;
      return `<input data-i="${i}" data-f="${cc.f}" value="${esc(''+(u[cc.f]||''))}" style="width:${cc.f==='email'?150:95}px">`;
    };
    const rend=()=>{
      const q=(c.querySelector('#q').value||'').toLowerCase();
      const vis=users.map((u,i)=>({u,i})).filter(({u})=>!q||(''+u.id+u.nm+u.dept+u.partner).toLowerCase().includes(q));
      c.querySelector('#tb').innerHTML=vis.map(({u,i})=>`<tr>${cols.map(cc=>`<td>${editMode?editCell(cc,u,i):disp(cc,u)}</td>`).join('')}${editMode?`<td class="center"><button class="btn xs ghost" data-del="${i}">✕</button></td>`:''}</tr>`).join('')||`<tr><td colspan="${cols.length+1}" class="empty">없음</td></tr>`;
      if(editMode){
        c.querySelectorAll('#tb input[data-f],#tb select[data-f]').forEach(el=>el.onchange=()=>{users[+el.dataset.i][el.dataset.f]=el.value;});
        c.querySelectorAll('#tb input[data-role]').forEach(el=>el.onchange=()=>{const u=users[+el.dataset.i];u.roles=u.roles||[];const r=el.dataset.role;if(el.checked){if(!u.roles.includes(r))u.roles.push(r);}else u.roles=u.roles.filter(x=>x!==r);});
        c.querySelectorAll('[data-del]').forEach(b=>b.onclick=()=>{users.splice(+b.dataset.del,1);rend();});
      }
      c.querySelector('#cnt').textContent=`${users.length}명 (내부 ${users.filter(u=>u.type==='내부').length}·협력사 ${users.filter(u=>u.type==='협력사').length}) · ${editMode?'✎수정중':'읽기전용'}`;
    };
    if(editMode){
      c.querySelector('#add').onclick=()=>{users.push({id:'',pw:'1234',nm:'',type:'내부',dept:'',pos:'',roles:['조회전용'],partner:'',email:'',tel:'',status:'사용'});rend();};
      c.querySelector('#save').onclick=async()=>{localStorage.setItem(lsu,JSON.stringify(users));
        let sv=false;try{const r=await PERM.saveUsersToServer(users);sv=!!(r&&(await r.json()).ok);}catch(e){}
        editMode=false;draw();alert(sv?'저장되었습니다 (전 PC 공통 — 모든 PC에서 로그인 가능).':'로컬 저장됨(서버 저장 실패 — 백엔드 확인 필요).');};
      c.querySelector('#cancel').onclick=()=>{users=load();editMode=false;draw();};
    } else if(c.querySelector('#edit')) c.querySelector('#edit').onclick=()=>{editMode=true;draw();};
    c.querySelector('#q').onkeyup=rend;
    rend();
  };
  draw();
};
SCREEN.setinreq=(c)=>{
  const API=API_BASE;
  const pad=n=>String(n).padStart(2,"0");
  const iso=d=>`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
  const yy=s=>s?s.slice(2).replace(/-/g,""):"";
  const addd=(s,n)=>{const d=new Date(s);d.setDate(d.getDate()+n);return iso(d);};
  const now=new Date();
  const ST={"00":"요청","10":"발행","20":"출발","30":"입고대기","40":"검사중","90":"입고완료","99":"반품"};
  const STCOL={"00":"#8aa0bd","10":"#2e86de","20":"#e67e22","30":"#f39c12","40":"#9b59b6","90":"#27ae60","99":"#c0392b"};
  const badge=s=>`<span style="padding:2px 7px;border-radius:4px;font-size:11px;background:${STCOL[s]||"#8aa0bd"};color:#fff">${ST[s]||s}</span>`;
  let st={rows:[],custs:[],cust:"",base:iso(now),period:2,jiknab:4,qty:{},chk:{},groups:[],sortKey:"",sortDir:1,loading:false};
  const load=async()=>{
    st.loading=true;draw();
    const to=addd(st.base,Math.max(+st.period||2,+st.jiknab||4)-1);
    try{const r=await fetch(`${API}/api/setin/list?cust=${encodeURIComponent(st.cust)}&fr=${yy(st.base)}&to=${yy(to)}&limit=2000`);
      const j=await r.json();st.rows=j.rows||[];st.custs=j.custs||[];st.qty={};st.chk={};}
    catch(e){st.rows=[];st.custs=[];}
    st.loading=false;draw();
  };
  const issue=async(cancel)=>{
    const items=[];
    (st.groups||[]).forEach(g=>{if(st.chk[g.key])g.rows.forEach(r=>items.push({sheet:r.sheet_no,qty:r.input_req_qty}));});
    if(!items.length)return alert("발행할 도번을 체크하세요.");
    try{const r=await fetch(`${API}/api/setin/issue`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({items,cancel:cancel?1:0})});
      const j=await r.json();
      if(!cancel&&j.barcode){try{const iv=await(await fetch(`${API}/api/setin/invoice?barcode=${j.barcode}`)).json();openInvoice(iv);}catch(e){}}
      alert(`${j.action} 완료: ${j.count}건`);await load();}
    catch(e){alert("실패: "+e.message);}
  };
  const openInvoice=(iv)=>{
    const bc=_barcodeDataURL(iv.raw);
    const party=p=>`<table class="pt"><tr><td class="k">등록번호</td><td>${esc(p.biz)}</td></tr><tr><td class="k">상 호</td><td>${esc(p.nm)}</td></tr><tr><td class="k">대 표 자</td><td>${esc(p.owner)}</td></tr><tr><td class="k">주 소</td><td>${esc(p.addr)}</td></tr><tr><td class="k">TEL</td><td>${esc(p.tel)}</td></tr><tr><td class="k">Fax</td><td>${esc(p.fax)}</td></tr></table>`;
    const items=iv.rows.map((x,i)=>`<tr><td>${i+1}</td><td>${esc(x.doban)}</td><td>${esc(x.jado)}</td><td class="l">${esc(x.nm)}</td><td class="r">${won(x.qty)}</td><td>${x.insp==="1"?"유검사":""}</td><td></td></tr>`).join("");
    const copy=title=>`<div class="cp"><div class="tt">거 래 명 세 표</div><div class="sb">${title}</div>
      <div class="mt"><span>출고일자 : ${esc(iv.ymd)}</span><span>PAGE:1/1</span></div>
      <table class="pi"><tr><td class="vl">공급자</td><td>${party(iv.supplier)}</td><td class="vl">공급<br>받는자</td><td>${party(iv.buyer)}</td></tr></table>
      <table class="it"><thead><tr><th>No.</th><th>Assy P/No.</th><th>하위 P/No.</th><th>품명</th><th>수량</th><th>검사</th><th>비고</th></tr></thead>
      <tbody>${items}<tr class="tot"><td colspan="4" class="r">합 계</td><td class="r">${won(iv.total)}</td><td></td><td></td></tr></tbody></table>
      <div class="ft"><div class="bc"><img src="${bc}"><div class="bt">${esc(iv.barcode)}</div></div>
        <table class="sp"><tr><td>자재팀</td><td>품질팀</td></tr><tr><td class="bx"></td><td class="bx"></td></tr></table></div></div>`;
    const w=window.open("","_blank","width=1240,height=880");
    if(!w)return alert("팝업 차단됨 — 팝업 허용 후 다시 발행하세요.");
    w.document.write(`<html><head><title>거래명세표 ${esc(iv.barcode)}</title><meta charset="utf-8"><style>
      body{font-family:'맑은 고딕',Malgun Gothic,sans-serif;margin:8px;font-size:11px;color:#000}
      .wrap{display:flex;gap:10px}.cp{flex:1;border:1.5px solid #000;padding:6px}
      .tt{text-align:center;font-size:20px;font-weight:700;letter-spacing:5px}.sb{text-align:center;font-size:12px;margin:1px 0 3px}
      .mt{display:flex;justify-content:space-between;font-size:11px;margin:2px 0}
      table{border-collapse:collapse;width:100%}.pi td{border:1px solid #000;padding:1px 3px;vertical-align:middle}
      .vl{width:16px;text-align:center;font-weight:700;background:#f2f2f2;font-size:10px;line-height:1.1}
      .pt{border:none}.pt td{border:none;padding:1px 3px}.pt .k{width:54px;background:#f7f7f7;font-weight:600;white-space:nowrap}
      .it th,.it td{border:1px solid #000;padding:2px 4px;text-align:center}.it .l{text-align:left}.it .r{text-align:right}
      .it thead th{background:#eaeaea}.tot td{font-weight:700;background:#f7f7f7}
      .ft{display:flex;justify-content:space-between;align-items:flex-end;margin-top:6px}
      .bc img{height:56px;display:block}.bt{font-family:monospace;font-size:13px;font-weight:700;margin-top:2px}
      .sp{width:210px}.sp td{border:1px solid #000;text-align:center;padding:2px}.sp .bx{height:40px}
      @media print{.noprint{display:none}}</style></head>
      <body><div class="noprint" style="margin-bottom:6px"><button onclick="window.print()">🖨️ 인쇄</button> <button onclick="window.close()">닫기</button></div>
      <div class="wrap">${copy("공급자")}${copy("공급받는자")}</div></body></html>`);
    w.document.close();
  };
  const dlab=d=>d?`${+d.slice(2,4)}/${+d.slice(4,6)}`:"";  // 260727→7/27
  const draw=()=>{
    // ── 도번 단위 그룹화 + 일자별 생산계획 ──
    const gm={};
    st.rows.forEach(r=>{const k=(r.in_cust_code||"")+"|"+r.item_code;
      if(!gm[k])gm[k]={key:k,cust:r.in_cust_code,custnm:r.custnm||r.in_cust_code,doban:r.item_code,itemnm:r.itemnm,jadolist:r.jadolist||"",jcnt:r.jcnt,insp:r.insp_flag,status:r.status,req:0,daily:{},rows:[]};
      const gg=gm[k];gg.req+=(+r.input_req_qty||0);gg.daily[r.input_ymd]=(gg.daily[r.input_ymd]||0)+(+r.input_req_qty||0);gg.rows.push(r);
      if(r.status!=="00")gg.status=r.status;});
    st.groups=Object.values(gm);
    if(st.sortKey){const k=st.sortKey,d=st.sortDir||1;st.groups.sort((a,b)=>{const x=a[k],y=b[k],nx=parseFloat(x),ny=parseFloat(y);if(x!=null&&y!=null&&!isNaN(nx)&&!isNaN(ny))return (nx-ny)*d;return String(x==null?"":x).localeCompare(String(y==null?"":y),"ko")*d;});}
    const days=[...new Set(st.rows.map(r=>r.input_ymd))].sort();
    const chkn=st.groups.filter(g=>st.chk[g.key]).length;
    const totreq=st.groups.reduce((a,g)=>a+g.req,0);
    const totdel=st.groups.reduce((a,g)=>a+(+((st.qty[g.key]!=null?st.qty[g.key]:g.req))||0),0);
    // 자도번 축약: 앞번호(마지막 -세그먼트 제외)가 같으면 -[1,2,3]로 묶음
    const jl=s=>{const a=(s||"").split(",").filter(Boolean);if(!a.length)return "";const m={};a.forEach(cd=>{const g2=cd.match(/^(.*)-([^-]+)$/);if(g2){(m[g2[1]]=m[g2[1]]||[]).push(g2[2]);}else{m[cd]=m[cd]||[];}});return Object.entries(m).map(([b,t])=>t.length?b+"-["+t.join(",")+"]":b).join(" · ");};
    c.innerHTML=`
     <div class="page-title">🧾 거래명세서 발행</div>
     <div class="page-sub">협력사가 요청수량에 <b>납품수량 입력 → 완성분 체크 → 송장발행</b> · 여러 도번을 하나의 <b>SET바코드</b>로 묶어 거래명세표 인쇄 · 우측=일자별 생산계획 · 레거시 <code>w_pr_outside_420</code></div>
     <div class="toolbar">
       <label class="tl">협력사</label>
       <select class="inp" id="si-cust" style="width:auto"><option value="">전체</option>
         ${st.custs.map(o=>`<option value="${esc(o.code)}" ${st.cust===o.code?"selected":""}>${esc(o.nm||o.code)} (${o.n})</option>`).join("")}</select>
       <label class="tl" style="margin-left:8px">기준일자</label><input class="inp" type="date" id="si-base" value="${esc(st.base)}">
       <label class="tl" style="margin-left:8px">기간(협력사)</label><input class="inp" id="si-period" value="${esc(st.period)}" style="width:44px;text-align:center">일
       <label class="tl" style="margin-left:6px">직납</label><input class="inp" id="si-jiknab" value="${esc(st.jiknab)}" style="width:44px;text-align:center">일
       <button class="btn" id="si-go">🔍 조회</button>
       <button class="btn" id="si-issue" style="background:#2e86de;color:#fff">🧾 송장발행 (${chkn})</button>
       <button class="btn" id="si-cancel">발행취소</button>
       ${st.loading?'<span style="color:var(--muted)">조회중…</span>':""}
     </div>
     <div class="panel"><div class="panel-h">요청 목록 — 완성된 것만 체크 후 [송장발행]</div><div class="panel-b" style="padding:0">
       <div class="grid-wrap" style="max-height:560px;overflow:auto"><table class="tbl" style="white-space:nowrap"><thead><tr>
         <th class="center"><input type="checkbox" id="si-all"></th><th data-key="custnm">작업처</th><th data-key="doban">도번</th><th data-key="itemnm">품명</th><th class="center">구분</th><th data-key="jadolist">자도번 LIST</th>
         <th class="num">LOT수량</th><th class="num">자재수량</th><th class="num">완료수량</th><th class="num" data-key="req">요청수량</th><th class="num" style="width:56px">납품수량</th>
         ${days.map(d=>`<th class="num">${dlab(d)}</th>`).join("")}<th class="center" data-key="insp">검사</th><th class="center" data-key="status">상태</th></tr></thead>
       <tbody>${st.groups.map(g=>{const ed=(g.status==="00"||g.status==="10");return `<tr>
         <td class="center"><input type="checkbox" class="si-ck" data-k="${esc(g.key)}" ${st.chk[g.key]?"checked":""} ${ed?"":"disabled"}></td>
         <td>${esc(g.custnm)}</td><td><b>${esc(g.doban)}</b></td>
         <td class="cap" style="max-width:150px;overflow:hidden;text-overflow:ellipsis" title="${esc(g.itemnm||"")}">${esc(g.itemnm||"")}</td>
         <td class="center">세트입고</td>
         <td><div style="max-width:250px;max-height:46px;overflow-y:auto;white-space:normal;word-break:break-all;line-height:1.3" title="${esc(jl(g.jadolist))}">${esc(jl(g.jadolist))}</div></td>
         <td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num qty">${won(g.req)}</td>
         <td class="num" style="background:#eafaea;width:56px"><input class="inp si-qty" data-k="${esc(g.key)}" value="${st.qty[g.key]!=null?st.qty[g.key]:g.req}" style="width:48px;text-align:right;background:#eafaea" ${ed?"":"disabled"}></td>
         ${days.map(d=>`<td class="num" style="${g.daily[d]?"background:#fff8d6":""}">${g.daily[d]?won(g.daily[d]):""}</td>`).join("")}
         <td class="center">${g.insp==="1"?'<span class="bdg sagub">검사</span>':"-"}</td>
         <td class="center">${badge(g.status)}</td></tr>`;}).join("")||`<tr><td colspan="${11+days.length+2}" style="padding:16px;color:var(--muted)">조회 결과 없음 (기준일자·기간 확인)</td></tr>`}
       <tr class="grandtot"><td></td><td>합계</td><td>${st.groups.length}건</td><td></td><td></td><td></td><td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">${won(totreq)}</td><td class="num">${won(totdel)}</td>${days.map(d=>`<td class="num">${won(st.groups.reduce((a,g)=>a+(g.daily[d]||0),0))}</td>`).join("")}<td></td><td></td></tr>
       </tbody></table></div></div></div>`;
    const g=id=>c.querySelector(id);
    g("#si-cust").onchange=e=>st.cust=e.target.value;
    g("#si-base").onchange=e=>st.base=e.target.value;
    g("#si-period").oninput=e=>st.period=e.target.value;
    g("#si-jiknab").oninput=e=>st.jiknab=e.target.value;
    g("#si-go").onclick=load;
    g("#si-issue").onclick=()=>issue(false);
    g("#si-cancel").onclick=()=>issue(true);
    const all=g("#si-all");if(all)all.onclick=e=>{st.groups.forEach(gg=>{if(gg.status==="00"||gg.status==="10")st.chk[gg.key]=e.target.checked;});draw();};
    c.querySelectorAll(".si-ck").forEach(x=>x.onchange=e=>{st.chk[e.target.dataset.k]=e.target.checked;const b=c.querySelector("#si-issue");if(b)b.textContent=`🧾 송장발행 (${st.groups.filter(gg=>st.chk[gg.key]).length})`;});
    c.querySelectorAll(".si-qty").forEach(x=>x.oninput=e=>{st.qty[e.target.dataset.k]=e.target.value;});
    // UI규칙7: 모든 컬럼 우측경계 드래그=너비조절 + data-key 컬럼 더블클릭=정렬
    c.querySelectorAll("thead th").forEach(th=>{addResizer(th);const k=th.dataset.key;if(k){th.style.cursor="pointer";th.title="더블클릭하여 정렬 · 우측 경계 드래그로 너비조절";th.ondblclick=()=>{st.sortDir=(st.sortKey===k&&st.sortDir===1)?-1:1;st.sortKey=k;draw();};}});
  };
  load();
};

/* 협력사 > 거래명세서 발행 (레거시 w_pr_outside_420) — 레거시 SP_LIVE 라이브 직독 + 510창 완료배분.
   전 컬럼(Line No·자도번LIST·사급·LOT·계획·완료·요청·납품/포장/SERIAL/HEAT 입력·출하/생산실적·세트/입고대기/ASSY재고·일자별).
   완료수량=출하+완제품재고+세트/입고대기 재고배분(도번 공유풀). 발행=nx.deliv_issue 기록(라이브 미기록·하드룰). */
SCREEN.deliv420=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const dcol=s=>(s&&(''+s).length===6)?`${+((''+s).slice(2,4))}/${+((''+s).slice(4,6))}`:s;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  const ST={"00":"요청","10":"발행","90":"발행완료"}, STC={"00":"#8aa0bd","10":"#2e86de","90":"#27ae60"};
  let F={cust:'',from:iso(T),days:5,item:'',part:'',sort:'doban',deliv:{},pack:{},serial:{},heat:{},chk:{}}, data={dates:[],rows:[],cnt:0,sum:{}}, custs=[], loading=false, busy=false, msg='';
  const toOf=()=>_isoAddDays(F.from,Math.max(1,(+F.days||5))-1);
  // ── 스티커/프린터 설정(localStorage 저장) — 레거시 스티커설정=라벨규격·프린터설정=프린터선택 대응 ──
  const LBLKEY='deliv420_label';
  const LBL=Object.assign({w:100,h:50,copies:1,printer:'(브라우저 인쇄 대화상자에서 선택)'},
    (()=>{try{return JSON.parse(localStorage.getItem(LBLKEY)||'{}');}catch(e){return {};}})());
  const saveLbl=()=>{try{localStorage.setItem(LBLKEY,JSON.stringify(LBL));}catch(e){}};
  const fetchInvoice=async(bc)=>{
    const r=await fetch(`${API}/api/partner/deliv420/invoice?barcode=${encodeURIComponent(bc)}`);
    if(!r.ok){let m='발행 명세 조회 실패';try{m=(await r.json()).detail||m;}catch(e){}throw new Error(m);}
    return r.json();};
  const loadCusts=async()=>{try{const r=await fetch(`${API}/api/partner/workcenters?src=legacy`);custs=(await r.json()).rows||[];}catch(e){custs=[];}};
  const load=async()=>{
    if(loading)return;                              // 중복요청 가드
    if(!F.cust){msg='협력사(자도번작업처)를 먼저 선택하세요.';data={dates:[],rows:[],cnt:0,sum:{}};draw();return;}
    loading=true;msg='';draw();
    const qs=new URLSearchParams({cust:F.cust,from_ymd:F.from,to_ymd:toOf(),item:F.item,matcode:F.part});
    try{const r=await fetch(`${API}/api/partner/deliv420?${qs}`);data=await r.json();F.deliv={};F.pack={};F.serial={};F.heat={};F.chk={};}
    catch(e){msg='백엔드 연결 실패';data={dates:[],rows:[],cnt:0,sum:{}};}
    loading=false;draw();};
  // 선택행(체크·납품수량>0) 수집
  const collect=(rows)=>{const items=[];rows.forEach(r=>{if(F.chk[r.assy]){const dv=Number(F.deliv[r.assy]!=null?F.deliv[r.assy]:r.deliv)||0;
    items.push({assy:r.assy,deliver_qty:dv,pack_qty:Number(F.pack[r.assy]!=null?F.pack[r.assy]:r.pack)||0,serial_no:F.serial[r.assy]||'',heat_no:F.heat[r.assy]||''});}});return items;};
  const issue=async(rows)=>{
    if(busy)return; const items=collect(rows); if(!items.length)return alert('완성분(체크)을 선택하고 납품수량을 확인하세요.');
    busy=true;
    try{
      const pv=await(await fetch(`${API}/api/partner/deliv420/issue`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cust:F.cust,from_ymd:F.from,to_ymd:toOf(),items,preview:1})})).json();
      if(!pv.ok){alert(pv.msg||'발행 불가');return;}
      if(!confirm(`발행 미리보기\n건수 ${pv.count} · 총 납품수량 ${nf(pv.total_qty)}\n\n확정 발행할까요? (nx.deliv_issue 기록 · 라이브 미기록)`))return;
      const rr=await(await fetch(`${API}/api/partner/deliv420/issue`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cust:F.cust,from_ymd:F.from,to_ymd:toOf(),items,preview:0})})).json();
      if(!rr.ok){alert(rr.msg||'발행 실패');return;}
      alert(`발행 완료 · 바코드 ${rr.barcode} · ${rr.count}건 · 납품 ${nf(rr.total_qty)}\n(nx.deliv_issue 기록)`);
      // ★발행 후 자동 팝업 — 거래명세표 + 스티커 라벨(레거시 ue_save 후 인쇄 흐름)
      if(rr.barcode){try{const iv=await fetchInvoice(rr.barcode);openDelivInvoice(iv);openSticker(iv);}
        catch(e){alert('발행은 완료됐으나 인쇄 팝업 실패: '+e.message+'\n[거래명세표]/[스티커] 버튼으로 발행번호 '+rr.barcode+' 재출력 가능합니다.');}}
      await load();
    }catch(e){alert('발행 오류: '+e.message);}finally{busy=false;}
  };
  const cancelIssue=async()=>{const bc=prompt('발행취소할 바코드 번호를 입력하세요');if(!bc)return;
    try{const rr=await(await fetch(`${API}/api/partner/deliv420/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({barcode:bc.trim()})})).json();
      alert(rr.ok?`취소 ${rr.cancelled}건`:(rr.msg||'실패'));await load();}catch(e){alert('오류: '+e.message);}};
  // ── 거래명세표 인쇄 (레거시 dw_pr_outside_020_p1 서식 · 공급자=협력사/공급받는자=당사 · SET바코드 Code39) ──
  const openDelivInvoice=(iv)=>{
    if(!iv||!iv.rows||!iv.rows.length)return alert('발행 명세가 없습니다.');
    const bc=_barcodeDataURL(iv.code);          // Code39: *SET+발행번호*
    const party=p=>`<table class="pt"><tr><td class="k">등록번호</td><td>${esc(p.biz)}</td></tr><tr><td class="k">상 호</td><td>${esc(p.nm)}</td></tr><tr><td class="k">대 표 자</td><td>${esc(p.owner)}</td></tr><tr><td class="k">주 소</td><td>${esc(p.addr)}</td></tr><tr><td class="k">업태/종목</td><td>${esc((p.btype||'')+(p.bkind?' / '+p.bkind:''))}</td></tr><tr><td class="k">TEL</td><td>${esc(p.tel)}</td></tr></table>`;
    const items=iv.rows.map((x,i)=>`<tr><td>${i+1}</td><td>${esc(x.doban)}</td><td class="l">${esc(x.nm)}</td><td class="l">${esc(x.spec)}</td><td class="r">${nf(x.qty)}</td><td>${esc(x.unit)}</td><td>${esc(x.serial)}</td><td>${esc(x.heat)}</td></tr>`).join('');
    const copy=title=>`<div class="cp"><div class="tt">거 래 명 세 표</div><div class="sb">(${title} 보관용)</div>
      <div class="mt"><span>발행일자 : ${esc(iv.ymd)}</span><span>발행번호 : ${esc(iv.barcode)}</span><span>PAGE:1/1</span></div>
      <table class="pi"><tr><td class="vl">공급자</td><td>${party(iv.supplier)}</td><td class="vl">공급<br>받는자</td><td>${party(iv.buyer)}</td></tr></table>
      <table class="it"><thead><tr><th>No.</th><th>도번(P/No.)</th><th>품명</th><th>규격</th><th>수량</th><th>단위</th><th>SERIAL-NO</th><th>HEAT-NO</th></tr></thead>
      <tbody>${items}<tr class="tot"><td colspan="4" class="r">합 계</td><td class="r">${nf(iv.total)}</td><td colspan="3"></td></tr></tbody></table>
      <div class="ft"><div class="bc"><img src="${bc}"><div class="bt">${esc(iv.barcode)}</div></div>
        <table class="sp"><tr><td>인수자</td><td>담당자</td></tr><tr><td class="bx"></td><td class="bx"></td></tr></table></div></div>`;
    const w=window.open('','_blank','width=1240,height=900');
    if(!w)return alert('팝업 차단됨 — 팝업 허용 후 다시 시도하세요.');
    w.document.write(`<html><head><title>거래명세표 ${esc(iv.barcode)}</title><meta charset="utf-8"><style>
      body{font-family:'맑은 고딕',Malgun Gothic,sans-serif;margin:8px;font-size:11px;color:#000}
      .wrap{display:flex;gap:10px}.cp{flex:1;border:1.5px solid #000;padding:6px}
      .tt{text-align:center;font-size:20px;font-weight:700;letter-spacing:5px}.sb{text-align:center;font-size:12px;margin:1px 0 3px}
      .mt{display:flex;justify-content:space-between;font-size:11px;margin:2px 0}
      table{border-collapse:collapse;width:100%}.pi td{border:1px solid #000;padding:1px 3px;vertical-align:middle}
      .vl{width:16px;text-align:center;font-weight:700;background:#f2f2f2;font-size:10px;line-height:1.1}
      .pt{border:none}.pt td{border:none;padding:1px 3px}.pt .k{width:60px;background:#f7f7f7;font-weight:600;white-space:nowrap}
      .it th,.it td{border:1px solid #000;padding:2px 4px;text-align:center}.it .l{text-align:left}.it .r{text-align:right}
      .it thead th{background:#eaeaea}.tot td{font-weight:700;background:#f7f7f7}
      .ft{display:flex;justify-content:space-between;align-items:flex-end;margin-top:6px}
      .bc img{height:56px;display:block}.bt{font-family:monospace;font-size:13px;font-weight:700;margin-top:2px}
      .sp{width:210px}.sp td{border:1px solid #000;text-align:center;padding:2px}.sp .bx{height:40px}
      @media print{.noprint{display:none}}</style></head>
      <body><div class="noprint" style="margin-bottom:6px"><button onclick="window.print()">🖨️ 인쇄</button> <button onclick="window.close()">닫기</button></div>
      <div class="wrap">${copy('공급자')}${copy('공급받는자')}</div></body></html>`);
    w.document.close();
  };
  // ── 스티커(라벨) 인쇄 — 도번당 1매(설정 매수만큼) · 필드: 거래처·발행일자·도번·품명·규격·수량·SERIAL·HEAT·발행번호 + Code39 바코드 ──
  const openSticker=(iv)=>{
    if(!iv||!iv.rows||!iv.rows.length)return alert('발행 명세가 없습니다.');
    const bc=_barcodeDataURL(iv.code);
    const cp=Math.max(1,Math.min(20,+LBL.copies||1));
    const labels=[];iv.rows.forEach(x=>{for(let k=0;k<cp;k++)labels.push(x);});
    const cell=x=>`<div class="lbl">
      <div class="hd"><span class="cu">${esc(iv.custnm)}</span><span class="dt">${esc(iv.ymd)}</span></div>
      <div class="do">${esc(x.doban)}</div>
      <div class="nm" title="${esc(x.nm)}">${esc(x.nm)}${x.spec?' · '+esc(x.spec):''}</div>
      <div class="rw"><span>수량 <b>${nf(x.qty)}</b> ${esc(x.unit)}</span><span>발행번호 ${esc(iv.raw)}</span></div>
      <div class="rw"><span>SERIAL ${esc(x.serial||'-')}</span><span>HEAT ${esc(x.heat||'-')}</span></div>
      <div class="bc"><img src="${bc}"><div class="bt">${esc(iv.barcode)}</div></div></div>`;
    const w=window.open('','_blank','width=760,height=900');
    if(!w)return alert('팝업 차단됨 — 팝업 허용 후 다시 시도하세요.');
    w.document.write(`<html><head><title>스티커 ${esc(iv.barcode)} (${labels.length}매)</title><meta charset="utf-8"><style>
      @page{size:${(+LBL.w||100)}mm ${(+LBL.h||50)}mm;margin:0}
      body{font-family:'맑은 고딕',Malgun Gothic,sans-serif;margin:0;color:#000;background:#e9edf3}
      .lbl{width:${(+LBL.w||100)}mm;height:${(+LBL.h||50)}mm;box-sizing:border-box;padding:3mm;border:1px dashed #999;background:#fff;margin:6px auto;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden}
      .hd{display:flex;justify-content:space-between;font-size:10px;font-weight:600;border-bottom:1px solid #000;padding-bottom:1px}
      .do{font-size:17px;font-weight:800;letter-spacing:.5px;margin-top:1mm}
      .nm{font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .rw{display:flex;justify-content:space-between;font-size:10px;margin-top:.5mm}.rw b{font-size:12px}
      .bc{text-align:center;margin-top:1mm}.bc img{height:12mm;max-width:100%}.bt{font-family:monospace;font-size:11px;font-weight:700}
      @media print{.noprint{display:none}.lbl{border:none;margin:0;page-break-after:always}}</style></head>
      <body><div class="noprint" style="text-align:center;padding:6px"><button onclick="window.print()">🖨️ 스티커 인쇄 (${labels.length}매 · ${(+LBL.w||100)}×${(+LBL.h||50)}mm)</button> <button onclick="window.close()">닫기</button> <span style="font-size:11px;color:#555">프린터: ${esc(LBL.printer)}</span></div>
      ${labels.map(cell).join('')}</body></html>`);
    w.document.close();
  };
  // ── 스티커설정(라벨규격·매수) / 프린터설정 — 경량 모달 ──
  const closeModal=()=>{const m=document.getElementById('d4-modal');if(m)m.remove();};
  const openModal=(html)=>{closeModal();const d=document.createElement('div');d.id='d4-modal';
    d.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:9999;display:flex;align-items:center;justify-content:center';
    d.innerHTML=`<div style="background:#fff;border-radius:10px;padding:18px 20px;min-width:320px;box-shadow:0 10px 40px rgba(0,0,0,.3);font-size:13px">${html}</div>`;
    d.onclick=e=>{if(e.target===d)closeModal();};document.body.appendChild(d);return d;};
  const openLabelSetup=()=>{
    const d=openModal(`<div style="font-weight:700;font-size:15px;margin-bottom:10px">🏷️ 스티커 라벨 설정</div>
      <label class="tl">라벨 규격</label>
      <select id="ml-preset" class="inp" style="width:100%;margin:4px 0 10px">
        <option value="">직접 입력</option><option value="100x50">100 × 50 mm</option><option value="100x30">100 × 30 mm</option>
        <option value="90x40">90 × 40 mm</option><option value="70x40">70 × 40 mm</option><option value="60x40">60 × 40 mm</option></select>
      <div style="display:flex;gap:8px;margin-bottom:10px">
        <div><label class="tl">가로(mm)</label><input id="ml-w" class="inp" value="${esc(LBL.w)}" style="width:80px;text-align:right"></div>
        <div><label class="tl">세로(mm)</label><input id="ml-h" class="inp" value="${esc(LBL.h)}" style="width:80px;text-align:right"></div>
        <div><label class="tl">도번당 매수</label><input id="ml-c" class="inp" value="${esc(LBL.copies)}" style="width:70px;text-align:right"></div></div>
      <div style="text-align:right"><button class="btn" id="ml-cancel">취소</button> <button class="btn" id="ml-save" style="background:#2e86de;color:#fff">저장</button></div>`);
    const q=id=>d.querySelector(id);
    q('#ml-preset').onchange=e=>{const v=e.target.value;if(v){const [w,h]=v.split('x');q('#ml-w').value=w;q('#ml-h').value=h;}};
    q('#ml-cancel').onclick=closeModal;
    q('#ml-save').onclick=()=>{LBL.w=Math.max(20,+q('#ml-w').value||100);LBL.h=Math.max(15,+q('#ml-h').value||50);
      LBL.copies=Math.max(1,Math.min(20,+q('#ml-c').value||1));saveLbl();closeModal();
      alert(`스티커 라벨 설정 저장 — ${LBL.w}×${LBL.h}mm · 도번당 ${LBL.copies}매`);};
  };
  const openPrinterSetup=()=>{
    const d=openModal(`<div style="font-weight:700;font-size:15px;margin-bottom:8px">🖨️ 프린터 설정</div>
      <div style="font-size:12px;color:#555;line-height:1.5;margin-bottom:10px">웹 환경에서는 실제 프린터 선택이 <b>브라우저 인쇄 대화상자</b>에서 이루어집니다(스티커=라벨 프린터, 거래명세표=일반 프린터 지정).<br>아래는 화면 표시용 프린터 이름입니다.</div>
      <label class="tl">프린터 이름(표시용)</label><input id="mp-name" class="inp" value="${esc(LBL.printer)}" style="width:100%;margin:4px 0 12px">
      <div style="text-align:right"><button class="btn" id="mp-cancel">취소</button> <button class="btn" id="mp-save" style="background:#2e86de;color:#fff">저장</button></div>`);
    d.querySelector('#mp-cancel').onclick=closeModal;
    d.querySelector('#mp-save').onclick=()=>{LBL.printer=d.querySelector('#mp-name').value.trim()||'(브라우저 인쇄 대화상자에서 선택)';saveLbl();closeModal();};
  };
  // 발행번호(바코드) 입력받아 거래명세표/스티커 재출력
  const reprint=async(kind)=>{const bc=prompt('발행번호(바코드)를 입력하세요');if(!bc)return;
    try{const iv=await fetchInvoice(bc.trim());(kind==='sticker'?openSticker:openDelivInvoice)(iv);}
    catch(e){alert('출력 실패: '+e.message);}};
  // 인쇄 뷰(뼈대): 자재부품표 = 체크 도번의 자도번LIST / 빈양식 = 서식만
  const printView=(rows,blank)=>{
    const sel=blank?[]:rows.filter(r=>F.chk[r.assy]); if(!blank&&!sel.length)return alert('출력할 도번(체크)을 선택하세요.');
    const custName=(custs.find(w=>w.cc===F.cust)||{}).nm||F.cust;
    const body=blank?Array.from({length:15}).map((_,i)=>`<tr><td>${i+1}</td><td></td><td></td><td></td><td></td><td></td></tr>`).join('')
      :sel.map((r,i)=>`<tr><td>${i+1}</td><td>${esc(r.assy)}</td><td class="l">${esc(r.nm||'')}</td><td class="l">${esc(r.mat_list||'')}</td><td class="r">${nf(F.deliv[r.assy]!=null?F.deliv[r.assy]:r.deliv)}</td><td>${esc(F.serial[r.assy]||'')}</td></tr>`).join('');
    const w=window.open('','_blank','width=1000,height=800'); if(!w)return alert('팝업 차단됨 — 허용 후 다시 시도.');
    w.document.write(`<html><head><title>${blank?'자재부품표(빈양식)':'자재부품표'} ${esc(custName)}</title><meta charset="utf-8">
      <style>body{font-family:'맑은 고딕',Malgun Gothic,sans-serif;margin:12px;font-size:12px}h2{text-align:center;letter-spacing:4px}
      table{border-collapse:collapse;width:100%}th,td{border:1px solid #000;padding:3px 5px;text-align:center}.l{text-align:left}.r{text-align:right}
      thead th{background:#eee}@media print{.np{display:none}}</style></head><body>
      <div class="np" style="margin-bottom:8px"><button onclick="window.print()">🖨️ 인쇄</button> <button onclick="window.close()">닫기</button></div>
      <h2>자 재 부 품 표</h2><div style="margin:4px 0">협력사: ${esc(custName)} · 출력일: ${iso(new Date())}${blank?' · (빈양식)':''}</div>
      <table><thead><tr><th>No</th><th>도번(ASSY)</th><th>품명</th><th>자도번 LIST</th><th>납품수량</th><th>SERIAL-NO</th></tr></thead><tbody>${body}</tbody></table>
      </body></html>`); w.document.close();
  };
  const draw=()=>{
    const dates=data.dates||[];
    let rows=(data.rows||[]).slice();
    // 정렬 토글: 도번별 / 시간별(라인→도번)
    if(F.sort==='time') rows.sort((a,b)=>String(a.line||'').localeCompare(String(b.line||''),'ko')||String(a.assy).localeCompare(String(b.assy),'ko'));
    else rows.sort((a,b)=>String(a.workcenter||'').localeCompare(String(b.workcenter||''),'ko')||String(a.assy).localeCompare(String(b.assy),'ko'));
    const custOpts=custs.map(w=>`<option value="${esc(w.nm||w.cc)}"></option>`).join('');
    const custName=(custs.find(w=>w.cc===F.cust)||{}).nm||'';
    const itS=new Map(); rows.forEach(r=>{if(r.assy&&!itS.has(r.assy))itS.set(r.assy,r.nm||'');});
    const itemOpts=[...itS].slice(0,500).map(([v,n])=>`<option value="${esc(v)}">${esc(n)}</option>`).join('');
    const ptS=new Set(); rows.forEach(r=>(r.mat_list||'').split(/[,\r\n]/).forEach(x=>{const m=x.split('{')[0].split('[')[0].trim();if(m)ptS.add(m);}));
    const partOpts=[...ptS].sort().slice(0,500).map(v=>`<option value="${esc(v)}"></option>`).join('');
    const FIX=23;
    const S=data.sum||{};
    const badge=s=>`<span style="padding:1px 5px;border-radius:3px;font-size:10px;background:${STC[s]||'#8aa0bd'};color:#fff">${ST[s]||s}</span>`;
    // 일자셀=완료/계획+색(가공4주간 동일 표준): 생산완료 노랑·출하완료 주황·키팅완료 녹
    const dcell=(r,d)=>{const pl=Number((r.days&&r.days[d])||0),dn=Number((r.donedays&&r.donedays[d])||0),bg=(r.colors&&r.colors[d])||'';if(!pl&&!dn)return '<td class="num" style="color:#dfe6ef">·</td>';
      return `<td class="num" style="white-space:nowrap${bg?';background:'+bg:''}">${nf(dn)}/${nf(pl)}</td>`;};
    const gPlan={},gDone={};rows.forEach(r=>dates.forEach(d=>{gPlan[d]=(gPlan[d]||0)+Number((r.days&&r.days[d])||0);gDone[d]=(gDone[d]||0)+Number((r.donedays&&r.donedays[d])||0);}));
    const chkn=rows.filter(r=>F.chk[r.assy]).length;
    // ★table-layout:fixed + colgroup — 조회 후에도 컬럼폭 고정(auto 재계산 방지). CW=23개 고정컬럼 + 일자.
    const CW=[28,86,38,96,120,400,38,48,48,48,48,46,46,46,74,74,54,54,54,54,54,38,52], DW=48;
    const totalW=CW.reduce((a,b)=>a+b,0)+dates.length*DW;
    const colg=`<colgroup>${CW.map(w=>`<col style="width:${w}px">`).join('')}${dates.map(()=>`<col style="width:${DW}px">`).join('')}</colgroup>`;
    const grand=rows.length?`<tr class="grandtot"><td class="center"><b>계</b></td><td colspan="6">${nf(data.cnt)}건</td><td class="num"><b>${nf(S.lot||0)}</b></td><td class="num"><b>${nf(S.plan||0)}</b></td><td class="num" style="color:#1c7c3a"><b>${nf(S.done||0)}</b></td><td class="num"><b>${nf(S.req||0)}</b></td><td class="num"><b>${nf(S.issued||0)}</b></td><td colspan="11"></td>${dates.map(d=>`<td class="num" style="white-space:nowrap"><b>${nf(gDone[d]||0)}/${nf(gPlan[d]||0)}</b></td>`).join('')}</tr>`:'';
    c.innerHTML=`
     <div class="page-title">🧾 거래명세서 발행 <span style="font-size:12px;color:var(--muted);font-weight:400">레거시 w_pr_outside_420 · 라이브 직독 · 발행=nx</span></div>
     <div class="page-sub">완료된 도번 <b>체크 → 납품/포장/SERIAL/HEAT 입력 → [납품처리]</b>(발행은 <b>nx.deliv_issue</b>에만 기록, 라이브 미기록). 완료수량=출하+완제품재고+세트/입고대기 재고배분(도번 공유풀). 요청수량=계획−완료−발행분.
       <span style="margin-left:6px;font-size:11px">일자셀=<b>완료/계획</b> · <span style="background:#ffff00;padding:0 5px;border-radius:3px">생산완료</span> <span style="background:#fac090;padding:0 5px;border-radius:3px">출하완료</span> <span style="background:#669900;color:#fff;padding:0 5px;border-radius:3px">키팅완료</span></span>${data.note?'<br>ℹ '+esc(data.note):''}</div>
     <div class="toolbar">
       <label class="tl">협력사</label><input class="inp" id="d4-cust" list="d4l-cust" value="${esc(custName)}" placeholder="거래처명 입력" autocomplete="off" style="width:170px"><datalist id="d4l-cust">${custOpts}</datalist>
       <label class="tl" style="margin-left:6px">기준일자</label>${legacyDateHTML('d4-base',F.from)}
       <label class="tl" style="margin-left:6px">기간</label><input class="inp" id="d4-days" value="${esc(F.days)}" style="width:40px;text-align:center">일
       <button class="btn" id="d4-search">🔍 조회</button>
       <button class="btn" id="d4-issue" style="background:#2e86de;color:#fff" ${busy?'disabled':''}>📦 납품처리 (${chkn})</button>
       <button class="btn" id="d4-cancel">발행취소</button>
       <button class="btn" id="d4-prt">🖨️ 자재부품표</button>
       <button class="btn" id="d4-blank">빈양식</button>
       <button class="btn" id="d4-invoice" title="발행번호로 거래명세표 재출력">🧾 거래명세표</button>
       <button class="btn" id="d4-sticker" title="발행번호로 스티커(바코드) 재출력">🏷️ 스티커</button>
       <button class="btn" id="d4-lblset" title="라벨 규격·매수 설정">⚙️ 스티커설정</button>
       <button class="btn" id="d4-prnset" title="프린터 설정">🖨 프린터설정</button>
       ${loading?'<span style="color:var(--muted)">조회중…</span>':''}
     </div>
     <div class="toolbar" style="margin-top:2px">
       <label class="tl">도번</label><input class="inp" id="d4-item" list="d4l-item" value="${esc(F.item)}" style="width:130px" placeholder="도번(ASSY)/품명" autocomplete="off"><datalist id="d4l-item">${itemOpts}</datalist>
       <label class="tl">자도번</label><input class="inp" id="d4-part" list="d4l-part" value="${esc(F.part)}" style="width:130px" placeholder="자도번" autocomplete="off"><datalist id="d4l-part">${partOpts}</datalist>
       <label class="tl" style="margin-left:8px">정렬</label>
       <select class="inp" id="d4-sort" style="width:auto"><option value="doban" ${F.sort==='doban'?'selected':''}>도번별</option><option value="time" ${F.sort==='time'?'selected':''}>시간별</option></select>
       <div class="spacer"></div><span class="rowcount">${nf(data.cnt||0)}건 · 완료 <b>${nf(S.done||0)}</b>/계획 ${nf(S.plan||0)} · 발행 ${nf(S.issued||0)}</span>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 320px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:11px;white-space:nowrap;table-layout:fixed;width:${totalW}px">${colg}<thead><tr>
       <th class="center"><input type="checkbox" id="d4-all"></th><th>자도번작업처</th><th class="center">Line</th><th>도번</th><th>품명</th><th>자도번 LIST</th><th class="center">사급</th>
       <th class="num">LOT</th><th class="num">계획</th><th class="num">완료</th><th class="num">요청</th><th class="num">발행</th>
       <th class="num">납품</th><th class="num">포장</th><th>SERIAL-NO</th><th>HEAT-NO</th>
       <th class="num">출하실적</th><th class="num">생산실적</th><th class="num">세트재고</th><th class="num">입고대기</th><th class="num">ASSY재고</th><th class="center">검사</th><th class="center">상태</th>
       ${dates.map(d=>`<th class="num">${dcol(d)}</th>`).join('')}</tr></thead>
      <tbody>${loading?spinRow(FIX+dates.length):(rows.length?(rows.map((r)=>{const ed=(r.status!=='90'&&Number(r.req)>0);const dv=(F.deliv[r.assy]!=null?F.deliv[r.assy]:r.deliv);const pk=(F.pack[r.assy]!=null?F.pack[r.assy]:r.pack);return `<tr>
        <td class="center"><input type="checkbox" class="d4-ck" data-k="${esc(r.assy)}" ${F.chk[r.assy]?'checked':''} ${ed?'':'disabled'}></td>
        <td><b>${esc(r.workcenter||'')}</b></td><td class="center">${esc(r.line||'')}</td>
        <td><b>${esc(r.assy)}</b></td>
        <td class="bcap" title="${esc(r.nm||'')} ${esc(r.spec||'')}" style="max-width:140px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm||'')}</td>
        <td><div style="width:100%;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.mat_list||'')}">${esc(r.mat_list||'')}</div></td>
        <td class="center">${r.sagub_list?'<span class="bdg sagub" style="font-size:10px" title="'+esc(r.sagub_list)+'">사급</span>':''}</td>
        <td class="num">${nf(r.lot)}</td><td class="num">${nf(r.plan)}</td>
        <td class="num" style="color:#1c7c3a"><b>${nf(r.done)}</b></td>
        <td class="num"><b>${nf(r.req)}</b></td>
        <td class="num" style="color:#27ae60">${r.issued?nf(r.issued):''}</td>
        <td class="num" style="background:#eafaea;padding:1px 2px"><input class="inp d4-dv" data-k="${esc(r.assy)}" value="${dv}" ${ed?'':'disabled'} style="width:40px;min-width:0;height:24px;text-align:right;background:#eafaea;padding:1px 3px;font-size:11px"></td>
        <td class="num" style="background:#eafaea;padding:1px 2px"><input class="inp d4-pk" data-k="${esc(r.assy)}" value="${pk}" ${ed?'':'disabled'} style="width:40px;min-width:0;height:24px;text-align:right;background:#eafaea;padding:1px 3px;font-size:11px"></td>
        <td style="background:#eafaea;padding:1px 2px"><input class="inp d4-sn" data-k="${esc(r.assy)}" value="${esc(F.serial[r.assy]||'')}" ${ed?'':'disabled'} style="width:70px;min-width:0;height:24px;background:#eafaea;padding:1px 3px;font-size:11px"></td>
        <td style="background:#eafaea;padding:1px 2px"><input class="inp d4-hn" data-k="${esc(r.assy)}" value="${esc(F.heat[r.assy]||'')}" ${ed?'':'disabled'} style="width:70px;min-width:0;height:24px;background:#eafaea;padding:1px 3px;font-size:11px"></td>
        <td class="num" style="color:#2e86de">${nf(r.sale)}</td><td class="num" style="color:#8e44ad">${nf(r.prod)}</td>
        <td class="num">${nf(r.iset_stk)}</td><td class="num">${nf(r.ireq)}</td><td class="num">${nf(r.assy_stock)}</td>
        <td class="center">${r.insp==='1'?'<span class="bdg sagub">검사</span>':''}</td>
        <td class="center">${badge(r.status)}</td>
        ${dates.map(d=>dcell(r,d)).join('')}</tr>`;}).join('')+grand):`<tr><td colspan="${FIX+dates.length}" class="empty">협력사·기준일자 선택 후 조회하세요.</td></tr>`)}</tbody></table></div>`;
    const g=id=>c.querySelector(id);
    const sync=()=>{const cn=g('#d4-cust').value.trim();F.cust=(custs.find(w=>(w.nm||w.cc)===cn)||{}).cc||(cn?F.cust:'');
      F.days=g('#d4-days').value||5;F.item=g('#d4-item').value.trim();F.part=g('#d4-part').value.trim();};
    bindLegacyDate(c,'d4-base',()=>F.from,(v)=>{F.from=v;});
    g('#d4-search').onclick=()=>{sync();load();};
    ['#d4-cust','#d4-item','#d4-part','#d4-days'].forEach(id=>{const el=g(id);if(el)el.onkeyup=e=>{if(e.key==='Enter'){sync();load();}};});
    g('#d4-sort').onchange=e=>{F.sort=e.target.value;draw();};
    g('#d4-issue').onclick=()=>issue(rows);
    g('#d4-cancel').onclick=cancelIssue;
    g('#d4-prt').onclick=()=>printView(rows,false);
    g('#d4-blank').onclick=()=>printView(rows,true);
    g('#d4-invoice').onclick=()=>reprint('invoice');
    g('#d4-sticker').onclick=()=>reprint('sticker');
    g('#d4-lblset').onclick=openLabelSetup;
    g('#d4-prnset').onclick=openPrinterSetup;
    const all=g('#d4-all');if(all)all.onclick=e=>{rows.forEach(r=>{if(r.status!=='90'&&Number(r.req)>0)F.chk[r.assy]=e.target.checked;});draw();};
    c.querySelectorAll('.d4-ck').forEach(x=>x.onchange=e=>{F.chk[e.target.dataset.k]=e.target.checked;const b=g('#d4-issue');if(b)b.textContent=`📦 납품처리 (${rows.filter(r=>F.chk[r.assy]).length})`;});
    c.querySelectorAll('.d4-dv').forEach(x=>x.oninput=e=>{F.deliv[e.target.dataset.k]=e.target.value;});
    c.querySelectorAll('.d4-pk').forEach(x=>x.oninput=e=>{F.pack[e.target.dataset.k]=e.target.value;});
    c.querySelectorAll('.d4-sn').forEach(x=>x.oninput=e=>{F.serial[e.target.dataset.k]=e.target.value;});
    c.querySelectorAll('.d4-hn').forEach(x=>x.oninput=e=>{F.heat[e.target.dataset.k]=e.target.value;});
    c.querySelectorAll('thead th').forEach(th=>addResizer(th));
  };
  loadCusts().then(draw);
};

/* 협력사 > 자재세트입고관리 (레거시 w_pu_stock_140) — SET바코드 스캔/장부입고 → 세트입고 실적 + 자도번 재고파생(TAG='S'). 반품포함. */
SCREEN.setstock=(c)=>{
  const API=API_BASE;
  const pad=n=>String(n).padStart(2,"0");
  const iso=d=>`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
  const yy=s=>s?s.slice(2).replace(/-/g,""):"";
  const now=new Date();
  const won=v=>(v==null||v==='')?'<span style="color:#c9d1dc">-</span>':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:2});
  const STAT={"00":"요청","10":"발행","20":"출발","30":"입고대기","40":"검사중","90":"입고완료","99":"반품"};
  const scol=s=>({"90":"#1f7a3d","30":"#c67d00","40":"#c67d00","99":"#c0392b"}[s]||"#586174");
  let st={rows:[],cust:"",item:"",fr:iso(new Date(now.getFullYear(),now.getMonth(),1)),to:iso(now),
          scan:"",info:null,mode:"bc",manual:"",sortKey:"",sortDir:1,loading:false,busy:false};
  const load=async()=>{st.loading=true;draw();
    try{const r=await fetch(`${API}/api/setstock/list?fr=${yy(st.fr)}&to=${yy(st.to)}&cust=${encodeURIComponent(st.cust)}&item=${encodeURIComponent(st.item)}`);
      const j=await r.json();st.rows=j.rows||[];}catch(e){st.rows=[];}
    st.loading=false;draw();};
  const doScan=async()=>{if(!st.scan)return;st.info=null;
    try{const r=await fetch(`${API}/api/setstock/scan?barcode=${encodeURIComponent(st.scan)}`);
      if(!r.ok)throw new Error((await r.json()).detail||r.status);st.info=await r.json();}catch(x){alert(x.message);st.info=null;}
    draw();};
  const doReceive=async()=>{if(st.busy)return;
    const bc=st.mode==="bc"?st.scan:st.manual;if(!bc)return alert(st.mode==="bc"?"SET바코드를 스캔하세요.":"장부입고 번호를 입력하세요.");
    if(!window.confirm(`SET바코드 ${bc}\n입고처리 → 세트입고 실적 기록 + 입고완료분 자도번 재고파생. 진행?`))return;
    st.busy=true;draw();
    try{const r=await fetch(`${API}/api/setstock/receive`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({barcode:bc,tag:st.mode==="bc"?"2":"3",manual:st.mode==="manual"?st.manual:""})});
      const j=await r.json();if(!r.ok)throw new Error(j.detail||r.status);
      alert(`입고완료 — ${j.received}건 처리, 자도번 재고파생 ${j.ledger_posted}행 (${j.barcode})`);st.scan="";st.info=null;st.manual="";await load();}catch(x){alert("입고처리 실패: "+x.message);}
    st.busy=false;draw();};
  const draw=()=>{
    if(st.sortKey){const k=st.sortKey,d=st.sortDir||1;st.rows.sort((a,b)=>{const x=a[k],y=b[k],nx=parseFloat(x),ny=parseFloat(y);if(x!=null&&y!=null&&!isNaN(nx)&&!isNaN(ny))return(nx-ny)*d;return String(x==null?"":x).localeCompare(String(y==null?"":y),"ko")*d;});}
    const totq=st.rows.reduce((a,r)=>a+(+r.maint_qty||0),0);
    const inf=st.info;
    c.innerHTML=`
     <div class="page-title">📦 자재세트입고관리</div>
     <div class="page-sub">협력사 세트 <b>SET바코드 스캔/장부입고</b> → 세트입고 실적 + 입고완료분 <b>자도번 재고파생</b>(TAG='S') · 검사품=입고대기 · 레거시 <code>w_pu_stock_140</code></div>
     <div class="panel" style="border:2px solid #2e86de"><div class="panel-h">세트 입고처리</div><div class="panel-b">
       <div class="toolbar" style="flex-wrap:wrap;gap:8px">
         <label class="tl"><input type="radio" name="sm" ${st.mode==="bc"?"checked":""} id="m-bc"> SET바코드</label>
         <label class="tl"><input type="radio" name="sm" ${st.mode==="manual"?"checked":""} id="m-man"> 장부입고(수동)</label>
         ${st.mode==="bc"
           ?`<input class="inp" id="sc-bc" value="${esc(st.scan)}" placeholder="SET바코드 스캔/입력" style="width:200px"><button class="btn" id="sc-go">🔍 송장조회</button>`
           :`<input class="inp" id="sc-man" value="${esc(st.manual)}" placeholder="장부입고 SET바코드 번호" style="width:200px">`}
         <button class="btn" id="sc-recv" style="background:#27ae60;color:#fff" ${st.busy?"disabled":""}>${st.busy?"처리중…":"📥 입고처리"}</button>
       </div>
       ${inf?`<div style="margin-top:8px;padding:10px;background:var(--soft);border-radius:6px;font-size:13px">
         <b>협력사:</b> ${esc(inf.custnm||inf.cust)} · <b>SET바코드:</b> SET${esc(inf.barcode)} · <b>도번 ${inf.rows.length}종</b>
         <table class="tbl" style="margin-top:6px;white-space:nowrap"><thead><tr><th>도번</th><th>품명</th><th class="num">수량</th><th class="center">자도번수</th><th class="center">상태</th><th class="center">검사</th></tr></thead>
         <tbody>${inf.rows.map(r=>`<tr><td><b>${esc(r.item_code)}</b></td><td class="cap" style="max-width:200px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.itemnm||"")}">${esc(r.itemnm||"")}</td><td class="num">${won(r.qty)}</td><td class="center">${r.jcnt}</td><td class="center" style="color:${scol(r.status)}">${STAT[r.status]||r.status}</td><td class="center">${r.insp==='1'?'검사품':'-'}</td></tr>`).join("")}</tbody></table>
         <div style="margin-top:4px;color:var(--muted);font-size:11px">일반=입고완료(90)→자도번 재고파생 · 검사품=입고대기(30, 검사후 파생)</div></div>`:""}
     </div></div>
     <div class="panel"><div class="panel-h">세트입고 실적 ${st.loading?"(조회중…)":`(${st.rows.length}건)`}</div><div class="panel-b" style="padding:0">
       <div class="toolbar" style="padding:8px 10px">
         <label class="tl">입고기간</label><input class="inp" type="date" id="f-fr" value="${esc(st.fr)}"> ~ <input class="inp" type="date" id="f-to" value="${esc(st.to)}">
         <label class="tl" style="margin-left:8px">도번</label><input class="inp" id="f-item" value="${esc(st.item)}" placeholder="도번" style="width:130px">
         <button class="btn" id="f-go">🔍 조회</button></div>
       <div class="grid-wrap" style="max-height:440px;overflow:auto"><table class="tbl" style="white-space:nowrap"><thead><tr>
         <th data-key="maint_ymd">입고일자</th><th class="num" data-key="maint_seq">SEQ</th><th data-key="custnm">협력사</th><th data-key="item_code">도번</th><th data-key="itemnm">품명</th>
         <th class="num" data-key="maint_qty">입고수량</th><th data-key="sheet_no">SET바코드</th><th class="center" data-key="status">상태</th><th class="center" data-key="derived_flag">재고파생</th><th>구분</th></tr></thead>
       <tbody>${st.rows.map(r=>{const ret=(+r.maint_qty<0);return `<tr>
         <td>${esc(r.maint_ymd)}</td><td class="num">${r.maint_seq}</td><td>${esc(r.custnm||r.cust_code)}</td>
         <td><b>${esc(r.item_code)}</b></td><td class="cap" style="max-width:180px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.itemnm||"")}">${esc(r.itemnm||"")}</td>
         <td class="num qty" style="color:${ret?"#c0392b":"#1f7a3d"}">${won(r.maint_qty)}</td>
         <td>${r.sheet_no?"SET"+esc(r.sheet_no):(r.manual_sheet_no?esc(r.manual_sheet_no)+"(수동)":"")}</td>
         <td class="center" style="color:${scol(r.status)}">${STAT[r.status]||r.status}</td>
         <td class="center">${r.derived_flag==='1'?'✅':'—'}</td><td>${r.maint_tag==='3'?'장부':r.maint_tag==='2'?'바코드':ret?'반품':esc(r.maint_tag)}</td></tr>`;}).join("")||'<tr><td colspan="10" style="padding:16px;color:var(--muted)">입고 실적 없음</td></tr>'}
       <tr class="grandtot"><td colspan="5" class="center">합계 ${st.rows.length}건</td><td class="num">${won(totq)}</td><td colspan="4"></td></tr>
       </tbody></table></div></div></div>`;
    const g=id=>c.querySelector(id);
    g("#m-bc").onclick=()=>{st.mode="bc";draw();};g("#m-man").onclick=()=>{st.mode="manual";draw();};
    if(st.mode==="bc"){const b=g("#sc-bc");b.oninput=x=>st.scan=x.target.value;b.onkeydown=x=>{if(x.key==="Enter")doScan();};g("#sc-go").onclick=doScan;}
    else{g("#sc-man").oninput=x=>st.manual=x.target.value;}
    g("#sc-recv").onclick=doReceive;
    g("#f-fr").onchange=x=>st.fr=x.target.value;g("#f-to").onchange=x=>st.to=x.target.value;g("#f-item").oninput=x=>st.item=x.target.value;g("#f-go").onclick=load;
    c.querySelectorAll("thead th").forEach(th=>{addResizer(th);const k=th.dataset.key;if(k){th.style.cursor="pointer";th.title="더블클릭 정렬·경계드래그 너비조절";th.ondblclick=()=>{st.sortDir=(st.sortKey===k&&st.sortDir===1)?-1:1;st.sortKey=k;draw();};}});
  };
  load();
};
SCREEN.sagubadjust=(c)=>{
  const API=API_BASE;
  const pad=n=>String(n).padStart(2,"0");
  const iso=d=>`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
  const yy=s=>s?s.slice(2).replace(/-/g,""):"";
  const now=new Date();
  const won=v=>(v==null||v==='')?'<span style="color:#c9d1dc">-</span>':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:2});
  let st={hrows:[],hcusts:[],hcust:"",hmat:"",hsign:"",hsortKey:"",hsortDir:1,hloading:false,
          rows:[],custs:[],cust:"",mat:"",fr:iso(new Date(now.getFullYear(),now.getMonth(),1)),to:iso(now),
          sortKey:"",sortDir:1,edit:null,loading:false};
  const loadHold=async()=>{st.hloading=true;draw();
    try{const r=await fetch(`${API}/api/sagub/holding/list?cust=${encodeURIComponent(st.hcust)}&mat=${encodeURIComponent(st.hmat)}&sign=${st.hsign}`);
      const j=await r.json();st.hrows=j.rows||[];st.hcusts=j.custs||[];}catch(e){st.hrows=[];}
    st.hloading=false;draw();};
  const load=async()=>{st.loading=true;draw();
    try{const r=await fetch(`${API}/api/sagub/adjust/list?fr=${yy(st.fr)}&to=${yy(st.to)}&cust=${encodeURIComponent(st.cust)}&mat=${encodeURIComponent(st.mat)}`);
      const j=await r.json();st.rows=j.rows||[];st.custs=j.custs||[];}catch(e){st.rows=[];}
    st.loading=false;draw();};
  const save=async()=>{const e=st.edit;if(!e.cust_code||!e.mat_code)return alert("사급업체·자도번을 입력하세요.");
    if(e.maint_qty===""||isNaN(+e.maint_qty))return alert("수정수량(숫자)을 입력하세요.");
    try{const r=await fetch(`${API}/api/sagub/adjust/save`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(e)});
      if(!r.ok)throw new Error((await r.json()).detail||r.status);st.edit=null;await load();}catch(x){alert("저장 실패: "+x.message);}};
  const del=async(id)=>{if(!confirm("이 조정 전표를 삭제할까요?"))return;
    try{await fetch(`${API}/api/sagub/adjust/delete`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id})});await load();}catch(x){alert("삭제 실패");}};
  const draw=()=>{
    if(st.hsortKey){const k=st.hsortKey,d=st.hsortDir||1;st.hrows.sort((a,b)=>{const x=a[k],y=b[k],nx=parseFloat(x),ny=parseFloat(y);if(x!=null&&y!=null&&!isNaN(nx)&&!isNaN(ny))return(nx-ny)*d;return String(x==null?"":x).localeCompare(String(y==null?"":y),"ko")*d;});}
    if(st.sortKey){const k=st.sortKey,d=st.sortDir||1;st.rows.sort((a,b)=>{const x=a[k],y=b[k],nx=parseFloat(x),ny=parseFloat(y);if(x!=null&&y!=null&&!isNaN(nx)&&!isNaN(ny))return(nx-ny)*d;return String(x==null?"":x).localeCompare(String(y==null?"":y),"ko")*d;});}
    const htotq=st.hrows.reduce((a,r)=>a+(+r.STOCK_QTY||0),0);
    const totq=st.rows.reduce((a,r)=>a+(+r.maint_qty||0),0);
    const e=st.edit;
    c.innerHTML=`
     <div class="page-title">🛠️ 협력사사급재고관리</div>
     <div class="page-sub">메인=<b>협력사 보유 사급재고 현황</b>(우리가 보낸 사급품 중 미회수 잔량, 정본 레거시 <code>PU_T_SAGUB_STOCK</code> RO) · 잔량=Σ사급출고−Σ(완성/세트입고×BOM소요) · 부가=<b>재고조정</b>(실사± <code>nx.sagub_maint</code>)</div>
     <div class="toolbar">
       <label class="tl">사급업체</label>
       <select class="inp" id="h-cust"><option value="">전체</option>${st.hcusts.map(o=>`<option value="${esc(o.code)}" ${st.hcust===o.code?"selected":""}>${esc(o.nm||o.code)}</option>`).join("")}</select>
       <label class="tl" style="margin-left:8px">자도번</label><input class="inp" id="h-mat" value="${esc(st.hmat)}" placeholder="자도번/품명" style="width:150px">
       <label class="tl" style="margin-left:8px">보유수량</label>
       <select class="inp" id="h-sign"><option value="">전체</option><option value="1" ${st.hsign==="1"?"selected":""}>(+)보유</option><option value="-1" ${st.hsign==="-1"?"selected":""}>(−)마이너스</option><option value="0" ${st.hsign==="0"?"selected":""}>0</option></select>
       <button class="btn" id="h-go">🔍 조회</button>
     </div>
     <div class="panel"><div class="panel-h">협력사 보유 사급재고 ${st.hloading?"(조회중…)":`(${st.hrows.length}건)`} · <span style="font-weight:400;color:var(--muted)">라이브 정본(읽기전용)</span></div><div class="panel-b" style="padding:0">
       <div class="grid-wrap" style="max-height:400px;overflow:auto"><table class="tbl" style="white-space:nowrap"><thead><tr>
         <th data-key="custnm">사급업체</th><th data-key="MAT_CODE">자도번</th><th data-key="matnm">품명</th><th class="center" data-key="item_class">구분</th>
         <th class="num" data-key="STOCK_QTY">보유재고</th><th class="num" data-key="REF_STOCK_QTY">참조수량</th><th data-key="upd_user">최종수정자</th><th data-key="upd_dt">최종수정일시</th><th data-key="upd_win">갱신프로그램</th></tr></thead>
       <tbody>${st.hrows.map(r=>`<tr>
         <td>${esc(r.custnm||r.CUST_CODE)}</td><td><b>${esc(r.MAT_CODE)}</b></td>
         <td class="cap" style="max-width:170px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.matnm||"")}">${esc(r.matnm||"")}</td>
         <td class="center">${r.item_class==='J'?'관리(중량)':'일반'}</td>
         <td class="num qty" style="color:${(+r.STOCK_QTY<0)?"#c0392b":"#1f7a3d"}">${won(r.STOCK_QTY)}</td>
         <td class="num">${r.REF_STOCK_QTY==null?'':won(r.REF_STOCK_QTY)}</td>
         <td>${esc(r.upd_user||"")}</td><td>${esc(String(r.upd_dt||"").slice(0,19).replace("T"," "))}</td>
         <td class="cap" style="max-width:130px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.upd_win||"")}">${esc(r.upd_win||"")}</td></tr>`).join("")||`<tr><td colspan="9" style="padding:16px;color:var(--muted)">${st.hloading?"":"보유 사급재고 없음"}</td></tr>`}
       <tr class="grandtot"><td colspan="4" class="center">합계 ${st.hrows.length}건</td><td class="num">${won(htotq)}</td><td colspan="4"></td></tr>
       </tbody></table></div></div></div>
     <div class="toolbar" style="margin-top:12px">
       <label class="tl">📋 재고조정 &nbsp;수정기간</label><input class="inp" type="date" id="sa-fr" value="${esc(st.fr)}"> ~ <input class="inp" type="date" id="sa-to" value="${esc(st.to)}">
       <label class="tl" style="margin-left:8px">사급업체</label>
       <select class="inp" id="sa-cust"><option value="">전체</option>${st.custs.map(o=>`<option value="${esc(o.code)}" ${st.cust===o.code?"selected":""}>${esc(o.nm||o.code)}</option>`).join("")}</select>
       <label class="tl" style="margin-left:8px">자도번</label><input class="inp" id="sa-mat" value="${esc(st.mat)}" placeholder="자도번(코드/이름)" style="width:150px">
       <button class="btn" id="sa-go">🔍 조회</button>
       <button class="btn" id="sa-add" style="background:#2e86de;color:#fff">➕ 조정추가</button>
     </div>
     ${e?`<div class="panel" style="border:2px solid #2e86de"><div class="panel-h">${e.id?"수정":"신규"} 조정 전표</div><div class="panel-b">
       <div class="toolbar" style="flex-wrap:wrap;gap:8px">
         <label class="tl">사급업체<span style="color:red">*</span></label><input class="inp" id="e-cust" value="${esc(e.cust_code||"")}" placeholder="업체코드" style="width:90px">
         <label class="tl">자도번<span style="color:red">*</span></label><input class="inp" id="e-mat" value="${esc(e.mat_code||"")}" placeholder="자도번" style="width:150px">
         <label class="tl">수정수량<span style="color:red">*</span></label><input class="inp" id="e-qty" value="${esc(e.maint_qty??"")}" placeholder="음수 가능" style="width:100px;text-align:right">
         <label class="tl">비고</label><input class="inp" id="e-rmk" value="${esc(e.remarks||"")}" placeholder="사유" style="width:200px">
         <button class="btn" id="e-save" style="background:#27ae60;color:#fff">💾 저장</button>
         <button class="btn" id="e-cancel">취소</button>
       </div><div style="font-size:11px;color:var(--muted);margin-top:4px">* 필수. 실사 조정(음수=차감). 조정은 nx 원장 기록(컷오버 후 재고 반영).</div></div></div>`:""}
     <div class="panel"><div class="panel-h">재고조정 내역 ${st.loading?"(조회중…)":""}</div><div class="panel-b" style="padding:0">
       <div class="grid-wrap" style="max-height:360px;overflow:auto"><table class="tbl" style="white-space:nowrap"><thead><tr>
         <th data-key="custnm">업체명</th><th data-key="maint_ymd">수정일자</th><th class="num" data-key="maint_seq">수정SEQ</th><th class="center">수정구분</th>
         <th data-key="mat_code">자도번</th><th data-key="matnm">품명</th><th class="num" data-key="maint_qty">수정수량</th><th data-key="remarks">비고</th>
         <th data-key="insert_user_id">작업자</th><th>작업일시</th><th class="center">관리</th></tr></thead>
       <tbody>${st.rows.map(r=>`<tr>
         <td>${esc(r.custnm||r.cust_code)}</td><td>${esc(r.maint_ymd)}</td><td class="num">${r.maint_seq}</td><td class="center">재고조정</td>
         <td><b>${esc(r.mat_code)}</b></td><td class="cap" style="max-width:160px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.matnm||"")}">${esc(r.matnm||"")}</td>
         <td class="num qty" style="color:${(+r.maint_qty<0)?"#c0392b":"#1f7a3d"}">${won(r.maint_qty)}</td><td class="cap" style="max-width:160px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.remarks||"")}">${esc(r.remarks||"")}</td>
         <td>${esc(r.insert_user_id)}</td><td>${esc(String(r.insert_datetime||"").slice(0,19).replace("T"," "))}</td>
         <td class="center"><button class="btn xs sa-ed" data-id="${r.id}">수정</button> <button class="btn xs sa-del" data-id="${r.id}">삭제</button></td></tr>`).join("")||'<tr><td colspan="11" style="padding:16px;color:var(--muted)">조정 내역 없음 — [조정추가]로 등록</td></tr>'}
       <tr class="grandtot"><td colspan="6" class="center">합계 ${st.rows.length}건</td><td class="num">${won(totq)}</td><td colspan="4"></td></tr>
       </tbody></table></div></div></div>`;
    const g=id=>c.querySelector(id);
    g("#h-cust").onchange=x=>st.hcust=x.target.value; g("#h-mat").oninput=x=>st.hmat=x.target.value;
    g("#h-sign").onchange=x=>st.hsign=x.target.value; g("#h-go").onclick=loadHold;
    g("#sa-fr").onchange=x=>st.fr=x.target.value; g("#sa-to").onchange=x=>st.to=x.target.value;
    g("#sa-cust").onchange=x=>st.cust=x.target.value; g("#sa-mat").oninput=x=>st.mat=x.target.value;
    g("#sa-go").onclick=load; g("#sa-add").onclick=()=>{st.edit={cust_code:st.cust||st.hcust||"",mat_code:"",maint_qty:"",remarks:""};draw();};
    if(e){g("#e-cust").oninput=x=>e.cust_code=x.target.value.trim();g("#e-mat").oninput=x=>e.mat_code=x.target.value.trim();
      g("#e-qty").oninput=x=>e.maint_qty=x.target.value;g("#e-rmk").oninput=x=>e.remarks=x.target.value;
      g("#e-save").onclick=save;g("#e-cancel").onclick=()=>{st.edit=null;draw();};}
    c.querySelectorAll(".sa-ed").forEach(x=>x.onclick=()=>{const r=st.rows.find(v=>v.id==x.dataset.id);st.edit={id:r.id,cust_code:r.cust_code,mat_code:r.mat_code,maint_qty:r.maint_qty,remarks:r.remarks||""};draw();});
    c.querySelectorAll(".sa-del").forEach(x=>x.onclick=()=>del(+x.dataset.id));
    c.querySelectorAll("thead th").forEach(th=>{addResizer(th);const k=th.dataset.key;if(!k)return;th.style.cursor="pointer";th.title="더블클릭 정렬·경계드래그 너비조절";
      const isHold=!!(th.closest("table")&&th.closest("table").querySelector("[data-key='STOCK_QTY']"));
      th.ondblclick=()=>{if(isHold){st.hsortDir=(st.hsortKey===k&&st.hsortDir===1)?-1:1;st.hsortKey=k;}else{st.sortDir=(st.sortKey===k&&st.sortDir===1)?-1:1;st.sortKey=k;}draw();};});
  };
  loadHold(); load();
};

/* ===== 협력사: 모델BOM 관리 (w_pr_master_060/020) — 모델→도번(신규모델 등록) ===== */
SCREEN.modelbom=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const ymd=s=>(s&&(''+s).length===6&&s!=='000000'&&s!=='999999')?`${(''+s).slice(0,2)}/${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:(s==='999999'?'~':(s==='000000'?'상시':(s||'')));
  let by='model', q='', slist=[], sel='', data={rows:[]}, loading=false, searching=false, msg='', editMode=false, erows=[];
  const search=async()=>{searching=true;draw();
    try{const r=await fetch(`${API}/api/modelbom/search?q=${encodeURIComponent(q)}&by=${by}`);slist=(await r.json()).rows||[];}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010';slist=[];}searching=false;draw();};
  const load=async(code)=>{sel=code;editMode=false;loading=true;draw();
    const p=by==='item'?`item=${encodeURIComponent(code)}`:`model=${encodeURIComponent(code)}`;
    try{const r=await fetch(`${API}/api/modelbom/get?${p}`);data=await r.json();}catch(e){data={rows:[]};}loading=false;draw();};
  const startEdit=()=>{editMode=true;erows=data.rows.filter(r=>r.src==='nx').map(r=>({...r}));if(!erows.length)erows=[{item:'',use_qty:1,from:'',to:'',remarks:''}];draw();};
  const addRow=()=>{erows.push({item:'',use_qty:1,from:'',to:'',remarks:''});draw();};
  const save=async()=>{
    try{const r=await fetch(`${API}/api/modelbom/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:sel,rows:erows})});
      const j=await r.json();if(j.ok){alert(`모델BOM 저장 완료 — ${j.count}건 (nx 신규등록)`);load(sel);return;}alert('저장 실패: '+(j.detail||JSON.stringify(j)));}
    catch(e){alert('저장 실패: '+e);}};
  const draw=()=>{
    const R=data.rows||[];
    const canW=(typeof PERM!=='undefined')?PERM.canEdit('modelbom'):true;   // 수정권한 게이트(규칙#16)
    c.innerHTML=`
     <div class="page-title">🧬 모델BOM 관리 <span style="font-size:12px;color:var(--muted);font-weight:400">LG모델 → 우리 도번 매핑 (편성 커버리지)</span></div>
     <div class="page-sub">LG 모델번호를 우리 ASSY 도번으로 매핑. 편성(협력사계획)이 이 매핑으로 모델→도번을 전개. 조회=<code>PR_M_MODEL_BOM</code>(라이브) ∪ <code>nx.model_bom</code>(신규등록). 미매핑 신규모델을 여기서 등록.</div>
     <div style="display:flex;gap:14px;align-items:flex-start">
      <div style="flex:0 0 300px">
       <div class="toolbar"><select class="inp" id="mb-by"><option value="model"${by==='model'?' selected':''}>모델→도번</option><option value="item"${by==='item'?' selected':''}>도번→모델(역)</option></select>
         <input class="inp" id="mb-q" value="${esc(q)}" placeholder="${by==='item'?'도번':'모델'} 검색" style="width:150px"><button class="btn" id="mb-search">🔍</button></div>
       <div class="grid-wrap" style="max-height:calc(100vh - 240px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
        <table class="tbl" style="font-size:12px"><thead><tr><th>${by==='item'?'도번':'모델'}</th><th class="num">${by==='item'?'모델수':'도번수'}</th></tr></thead>
        <tbody>${searching?spinRow(2):(slist.length?slist.map(s=>`<tr class="mb-row${sel===s.code?' sel':''}" data-c="${esc(s.code)}" style="cursor:pointer"><td><b>${esc(s.code)}</b></td><td class="num">${s.n}</td></tr>`).join(''):`<tr><td colspan="2" class="empty">검색</td></tr>`)}</tbody></table>
       </div>
      </div>
      <div style="flex:1;min-width:0">
       ${sel?`<div class="toolbar"><span style="font-weight:700;color:#1c47a0">${esc(sel)}</span>
         <div class="spacer"></div>${(by==='model'&&canW)?(editMode?`<button class="btn" id="mb-add">＋행추가</button><button class="btn" id="mb-save" style="background:#1c47a0;color:#fff">💾 저장</button><button class="btn ghost" id="mb-cancel">✖ 취소</button>`:`<button class="btn" id="mb-edit">✎ 신규등록/수정(nx)</button>`):(by==='model'?`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</span>`:'')}</div>
        <div class="grid-wrap" style="max-height:calc(100vh - 250px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
         ${(!editMode)?`<table class="tbl" style="font-size:12px"><thead><tr>${by==='item'?'<th>모델</th>':''}<th>도번</th><th>품명</th><th class="num">사용수량</th><th>유효시작</th><th>유효종료</th><th>작업장/업체</th><th>소스</th></tr></thead>
          <tbody>${loading?spinRow(7):(R.length?R.map(r=>`<tr>${by==='item'?`<td><b>${esc(r.model)}</b></td>`:''}<td><b>${esc(r.item)}</b></td><td class="bcap" title="${esc(r.nm)}" style="max-width:160px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td><td class="num">${r.use_qty}</td><td class="center">${ymd(r.from)}</td><td class="center">${ymd(r.to)}</td><td class="center">${esc(r.wc)}</td><td class="center"><span style="font-size:10px;color:${r.src==='nx'?'#1c7c3a':'#888'}">${r.src==='nx'?'nx등록':'라이브'}</span></td></tr>`).join(''):`<tr><td colspan="${by==='item'?8:7}" class="empty">매핑 없음 — ${by==='model'?'신규등록/수정(nx)으로 추가':''}</td></tr>`)}</tbody></table>`
         :`<table class="tbl" style="font-size:12px"><thead><tr><th>도번</th><th class="num">사용수량</th><th>유효시작(YYMMDD)</th><th>유효종료</th><th>비고</th><th>삭제</th></tr></thead>
          <tbody>${erows.map((r,i)=>`<tr><td><input class="ce" data-i="${i}" data-k="item" value="${esc(r.item||'')}" placeholder="도번" style="width:130px"></td>
           <td><input class="ce" type="number" step="any" data-i="${i}" data-k="use_qty" value="${r.use_qty??1}" style="width:60px"></td>
           <td><input class="ce" data-i="${i}" data-k="from" value="${esc(r.from||'')}" placeholder="상시" style="width:90px"></td>
           <td><input class="ce" data-i="${i}" data-k="to" value="${esc(r.to||'')}" placeholder="~무기한" style="width:90px"></td>
           <td><input class="ce" data-i="${i}" data-k="remarks" value="${esc(r.remarks||'')}" style="width:120px"></td>
           <td class="center"><span class="mb-del" data-i="${i}" style="cursor:pointer;color:#c0392b">✖</span></td></tr>`).join('')}</tbody></table>`}
        </div>
        ${editMode?`<div class="page-sub" style="margin-top:6px;color:#8aa0bd">※ 라이브(PR_M_MODEL_BOM)는 읽기전용. 신규모델·추가매핑만 nx.model_bom에 저장되며 편성이 즉시 반영합니다.</div>`:''}`
       :`<div class="empty" style="margin-top:40px">좌측에서 ${by==='item'?'도번':'모델'}을 선택하세요.</div>`}
      </div>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <style>.mb-row.sel{background:#e8f0ff}.mb-row:hover{background:#eef4ff}</style>`;
    const g=id=>c.querySelector(id);
    g('#mb-by').onchange=e=>{by=e.target.value;slist=[];sel='';data={rows:[]};draw();};
    g('#mb-search').onclick=()=>{q=g('#mb-q').value;search();};
    g('#mb-q').onkeyup=e=>{if(e.key==='Enter'){q=e.target.value;search();}};
    c.querySelectorAll('.mb-row').forEach(el=>el.onclick=()=>load(el.dataset.c));
    const ed=g('#mb-edit');if(ed)ed.onclick=startEdit;
    const ad=g('#mb-add');if(ad)ad.onclick=addRow;
    const sv=g('#mb-save');if(sv)sv.onclick=save;
    const cx=g('#mb-cancel');if(cx)cx.onclick=()=>{editMode=false;draw();};
    c.querySelectorAll('.mb-del').forEach(el=>el.onclick=()=>{erows.splice(+el.dataset.i,1);draw();});
    c.querySelectorAll('.ce').forEach(el=>el.oninput=()=>{const i=+el.dataset.i,k=el.dataset.k;erows[i][k]=(el.type==='number')?(el.value===''?null:+el.value):el.value;});
  };
  draw();
};

/* ===== 협력사 ①: 협력사계획현황 (w_pr_outside_040) — nx.plan_part 편성결과 ===== */
SCREEN.partnerplan=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const dcol=s=>(s&&(''+s).length===6)?`${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:s;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  let F={from:iso(T),days:31,wc:'',part:'',assy:'',line:'',gubun:'외주',src:'legacy'};
  let data={dates:[],rows:[],cnt:0,sum_qty:0,note:''}, wcs=[], loading=false, msg='';
  let rowsCur=[];   // ★헤더 더블클릭 정렬용 영속 행배열(enableSort가 in-place 정렬, tbody만 재렌더)
  const toOf=()=>_isoAddDays(F.from,Math.max(1,(+F.days||31))-1);
  const loadWc=async()=>{try{const r=await fetch(`${API}/api/partner/workcenters?src=${F.src}`);wcs=(await r.json()).rows||[];}catch(e){wcs=[];}};
  const load=async()=>{
    if(loading)return;                              // 중복요청 가드
    if(!F.wc){msg='협력사(자도번작업처)를 먼저 선택하세요. (전체 조회는 무거워 협력사 지정 후 조회합니다)';data={dates:[],rows:[],cnt:0,sum_qty:0,note:''};draw();return;}
    loading=true;msg='';draw();
    const qs=new URLSearchParams({from_ymd:F.from,to_ymd:toOf(),wc:F.wc,part:F.part,assy:F.assy,line:F.line,gubun:F.gubun,src:F.src});
    try{const r=await fetch(`${API}/api/partner/planstatus?${qs}`);data=await r.json();msg='';}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';data={dates:[],rows:[],cnt:0,sum_qty:0};}
    loading=false;draw();};
  // 레거시 도번-level(자도번LIST) / nx 자도번-level 를 동일 컬럼으로 정규화
  const norm=(r,i)=>({seq:r.seq||i+1, wc:r.wc, wcnm:r.wcnm||r.wc, line:r.line||'', workcenter:r.workcenter||'',
     assy:r.assy||'', jado:r.part||'', sagub:!!r.sagub, lot:(r.lot!=null?r.lot:null),
     matq:(r.matq!=null?r.matq:r.tot), doneq:(r.doneq!=null?r.doneq:null), reqq:(r.reqq!=null?r.reqq:null),
     nm:r.nm||'', spec:r.spec||'', days:r.days||{}, donedays:r.donedays||{}, colors:r.colors||{}, tot:r.tot||0, alloc_note:r.alloc_note||''});
  const draw=()=>{
    const dates=data.dates||[];
    rowsCur=(data.rows||[]).map(norm);
    rowsCur.forEach(r=>dates.forEach(d=>{r['d_'+d]=Number((r.days&&r.days[d])||0);}));   // ★일자(피벗) 정렬용 합성 숫자키
    const rows=rowsCur;
    const pnAssy=new Set(),pnLine=new Set(),pnPart=new Set();
    rows.forEach(r=>{if(r.assy)pnAssy.add(r.assy);if(r.line)pnLine.add(r.line);if(r.jado)pnPart.add((r.jado||'').split('{')[0]);});
    const pnAssyOpts=[...pnAssy].slice(0,400).map(v=>`<option value="${esc(v)}"></option>`).join('');
    const pnLineOpts=[...pnLine].map(v=>`<option value="${esc(v)}"></option>`).join('');
    const pnPartOpts=[...pnPart].slice(0,400).map(v=>`<option value="${esc(v)}"></option>`).join('');
    const wcOpts=wcs.map(w=>`<option value="${esc(w.nm||w.cc)}"></option>`).join('');
    const wcName=(wcs.find(w=>w.cc===F.wc)||{}).nm||'';
    const nn=v=>(v==null?'-':nf(v));
    // 합계행
    const frac=!!data.frac;   // 협력사 지정 시 일자셀=완료/계획+색(가공4주간 동일)
    const sMat=rows.reduce((a,r)=>a+Number(r.matq||0),0), sReq=rows.reduce((a,r)=>a+Number(r.reqq||0),0);
    const gDay={},gDone={}; rows.forEach(r=>dates.forEach(d=>{gDay[d]=(gDay[d]||0)+Number((r.days&&r.days[d])||0);gDone[d]=(gDone[d]||0)+Number((r.donedays&&r.donedays[d])||0);}));
    // 일자셀 렌더: frac=완료/계획+색, 아니면 계획수량
    const dcell=(r,d)=>{const pl=Number((r.days&&r.days[d])||0);if(!frac)return `<td class="num"${pl?'':' style="color:#dfe6ef"'}>${pl?nf(pl):'·'}</td>`;
      const dn=Number((r.donedays&&r.donedays[d])||0),bg=(r.colors&&r.colors[d])||'';if(!pl&&!dn)return '<td class="num" style="color:#dfe6ef">·</td>';
      return `<td class="num" style="white-space:nowrap${bg?';background:'+bg:''}">${nf(dn)}/${nf(pl)}</td>`;};
    const FIX=12;
    const gcell=d=>frac?`<td class="num" style="white-space:nowrap"><b>${nf(gDone[d]||0)}/${nf(gDay[d]||0)}</b></td>`:`<td class="num"><b>${nf(gDay[d]||0)}</b></td>`;
    const grandRow=rows.length?`<tr class="grandtot"><td class="center"><b>계</b></td><td class="center" style="color:#33507d">${nf(data.cnt||rows.length)}건</td><td colspan="6"></td><td class="num"><b>${nf(sMat)}</b></td><td class="num">-</td><td class="num"><b>${nf(sReq)}</b></td><td></td>${dates.map(d=>gcell(d)).join('')}</tr>`:'';
    const rowTr=r=>`<tr>
        <td class="num" style="color:#8aa0bd">${r.seq}</td>
        <td><b>${esc(r.wcnm)}</b>${r.alloc_note?` <span class="bdg" style="font-size:9px;background:#eaf3ff;color:#1c47a0;border:1px solid #bcd;border-radius:6px;padding:0 4px" title="조달 프로파일 발주업체 배분 반영">${esc(r.alloc_note)}</span>`:''}</td><td class="center">${esc(r.line)}</td><td>${esc(r.workcenter)}</td>
        <td><b>${esc(r.assy)}</b></td>
        <td><div style="width:400px;max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.jado)}">${esc(r.jado)}</div></td>
        <td class="center">${r.sagub?'<span class="bdg sagub" style="font-size:10px">사급</span>':''}</td>
        <td class="num">${nn(r.lot)}</td><td class="num"><b>${nn(r.matq)}</b></td>
        <td class="num" style="color:#1c7c3a" title="완료수량 = 출하실적 + 완제품재고 배분 + 세트/입고대기 재고배분 (레거시 SP+510창, 도번 공유풀). 협력사(외주) 지정 시 표시.">${nn(r.doneq)}</td>
        <td class="num">${nn(r.reqq)}</td>
        <td class="bcap" title="${esc(r.nm)} ${esc(r.spec)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}${r.spec?' <span style="color:var(--muted)">'+esc(r.spec)+'</span>':''}</td>
        ${dates.map(d=>dcell(r,d)).join('')}</tr>`;
    const bodyHTML=()=>loading?spinRow(FIX+dates.length):(rowsCur.length?(rowsCur.map(rowTr).join('')+grandRow):`<tr><td colspan="${FIX+dates.length}" class="empty">조회 결과 없음 — 자도번작업처/기준일자/기간을 확인하세요.</td></tr>`);
    c.innerHTML=`
    <style>
      /* ★페이지 본문(창) 세로 스크롤 금지 — 그리드만 내부 스크롤. 헤더=sticky top, 합계행=sticky bottom(CLAUDE.md §3) */
      .pn-grid thead th{position:sticky;top:0;z-index:3;background:#eef2f8}
      .pn-grid tr.grandtot td{position:sticky;bottom:0;z-index:2;background:#f0f4fb;box-shadow:0 -1px 0 var(--line-2,#c9d3e0)}
    </style>
    <div style="display:flex;flex-direction:column;height:100%">
     <div style="flex:0 0 auto">
     <div class="page-title">📋 협력사계획현황 <span style="font-size:12px;color:var(--muted);font-weight:400">4주간 계획수량 — 자도번작업처·도번·자도번LIST·일자별 (당김 반영)</span></div>
     <div class="page-sub">레거시 <code>w_pr_outside_410</code> 4주간 계획수량 컬럼 동일(1:1 대조용). 당김=<code>PR_M_LINE_NO.CUST_MAINT_DAY</code>(회사근무일, 협력사계획 SP가 <code>part_plan_ymd</code>에 반영). 첫 일자컬럼=기준일 이전 누적. ${F.src==='legacy'?'🔴 <b>레거시 라이브</b>(PR_T_PLAN_PART_MAT) 직독':'🟢 우리편성(nx.plan_part_mat)'}</div>
     <div class="toolbar">
       <label class="tl">소스</label>
       <select class="inp" id="pn-src" style="width:auto">
         <option value="legacy" ${F.src==='legacy'?'selected':''}>레거시 라이브 (당김반영)</option>
         <option value="nx" ${F.src==='nx'?'selected':''}>우리편성 (nx)</option></select>
       <label class="tl" style="margin-left:8px">기준일자</label>${legacyDateHTML('pn-base',F.from)}
       <label class="tl" style="margin-left:8px">기간</label><input class="inp" id="pn-days" value="${esc(F.days)}" style="width:42px;text-align:center">일
       <label class="tl" style="margin-left:8px">자도번작업처</label><input class="inp" id="pn-wc" list="pnl-wc" value="${esc(wcName)}" placeholder="거래처명 입력" autocomplete="off" style="width:180px"><datalist id="pnl-wc">${wcOpts}</datalist>
       <button class="btn" id="pn-search">🔍 조회</button>
     </div>
     <div class="toolbar" style="margin-top:2px">
       <label class="tl">자도번</label><input class="inp" id="pn-part" list="pnl-part" value="${esc(F.part)}" style="width:120px" placeholder="자도번" autocomplete="off"><datalist id="pnl-part">${pnPartOpts}</datalist>
       <label class="tl">도번</label><input class="inp" id="pn-assy" list="pnl-assy" value="${esc(F.assy)}" style="width:120px" placeholder="도번(ASSY)" autocomplete="off"><datalist id="pnl-assy">${pnAssyOpts}</datalist>
       <label class="tl">라인</label><input class="inp" id="pn-line" list="pnl-line" value="${esc(F.line)}" style="width:60px" placeholder="라인" autocomplete="off"><datalist id="pnl-line">${pnLineOpts}</datalist>
       <div class="spacer"></div><span class="rowcount">${nf(data.cnt)}건 · 자재수량합 <b>${nf(data.sum_qty)}</b> · 일자 ${dates.length}</span>
     </div>
     ${frac?`<div class="page-sub" style="font-size:11px">일자셀=<b>완료/계획</b> · 색: <span style="background:#ffff00;padding:0 5px;border-radius:3px">생산완료</span> <span style="background:#fac090;padding:0 5px;border-radius:3px">출하완료</span> <span style="background:#669900;color:#fff;padding:0 5px;border-radius:3px">키팅완료</span></div>`:''}
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     ${data.note?`<div class="page-sub" style="color:#b8860b">ℹ ${esc(data.note)}</div>`:''}
     </div>
     <div class="grid-wrap" style="flex:1 1 auto;min-height:0;overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl pn-grid" style="font-size:11px;white-space:nowrap"><thead><tr>
       <th class="num">SEQ</th><th>자도번작업처</th><th>라인</th><th>작업처</th><th>도번</th><th style="min-width:400px;width:400px">자도번LIST</th><th class="center">사급</th>
       <th class="num">LOT수량</th><th class="num">자재수량</th><th class="num">완료수량</th><th class="num">요청수량</th><th>품목정보</th>
       ${dates.map(d=>`<th class="num">${dcol(d)}</th>`).join('')}</tr></thead>
      <tbody>${bodyHTML()}</tbody></table></div>
    </div>`;
    const g=id=>c.querySelector(id);
    const syncInputs=()=>{const wn=g('#pn-wc').value.trim();F.wc=(wcs.find(w=>(w.nm||w.cc)===wn)||{}).cc||(wn?F.wc:'');F.days=g('#pn-days').value||31;F.part=g('#pn-part').value;F.assy=g('#pn-assy').value;F.line=g('#pn-line').value;};
    const ssel=g('#pn-src');if(ssel)ssel.onchange=e=>{F.src=e.target.value;F.wc='';loadWc().then(draw);};
    // 레거시 기준일자 위젯: 전일/익일/달력 → 자동 재조회
    bindLegacyDate(c,'pn-base',()=>F.from,(v)=>{F.from=v;syncInputs();load();});
    g('#pn-days').onchange=()=>{syncInputs();load();};
    g('#pn-search').onclick=()=>{syncInputs();load();};
    ['#pn-part','#pn-assy','#pn-line','#pn-wc'].forEach(id=>{const el=g(id);if(el)el.onkeyup=e=>{if(e.key==='Enter')g('#pn-search').click();};});
    // ★헤더 더블클릭 정렬(고정 12컬럼 + 일자 피벗) — tbody만 재렌더로 화살표·리사이저 보존. 합계행은 bodyHTML이 항상 맨끝에 붙임.
    if(!loading&&rowsCur.length){
      const KEYS=['seq','wcnm','line','workcenter','assy','jado','sagub','lot','matq','doneq','reqq','nm'].concat(dates.map(d=>'d_'+d));
      enableSort(c,KEYS,()=>rowsCur,()=>{const tb=c.querySelector('tbody');if(tb)tb.innerHTML=bodyHTML();});
    }
  };
  loadWc().then(draw);   // ★자동 전체조회 금지 — 협력사 선택 후 [조회]
};

/* ===== 일일 영업/매입 현황 (경영) — 조회화면(엑셀형). ① 매입/불출/실매입 by 구분 · 마감기준 · 공급가(원) ===== */
SCREEN.dailypurissue=(c)=>{
  const API=API_BASE;
  const _tod=(()=>{const d=new Date();const p=n=>(''+n).padStart(2,'0');return `${(''+d.getFullYear()).slice(2)}${p(d.getMonth()+1)}${p(d.getDate())}`;})();
  let F=null, loading=false, day=_tod;   // ★조회일 기본=오늘. 초기 자동조회 안 함 — 조회버튼/Enter로만.
  const y2d=y=>(y&&y.length===6)?`20${y.slice(0,2)}-${y.slice(2,4)}-${y.slice(4,6)}`:'';   // YYMMDD→date
  const d2y=d=>d?d.slice(2).replace(/-/g,''):'';                                             // date→YYMMDD
  const load=async(d)=>{loading=true;draw();
    try{const r=await fetch(`${API}/api/live/dailypurissue${d?('?date='+d):''}`);F=await r.json();day=F.date||d||'';}
    catch(e){F=null;}
    loading=false;draw();};
  const sec=(rows,tot,lbl,color)=>{
    let h=`<tr><td colspan="4" style="background:${color};color:#fff;font-weight:700;padding:4px 8px">${lbl}</td></tr>`;
    h+=(rows||[]).map(r=>`<tr><td style="padding-left:16px">${esc(r.gubun)}</td><td class="num">${wonI(r.cum)}</td><td class="num">${wonI(r.day)}</td><td class="num"><b>${wonI(r.tot)}</b></td></tr>`).join('');
    h+=`<tr style="background:#eef2f8;font-weight:700"><td>합계</td><td class="num">${wonI(tot.cum)}</td><td class="num">${wonI(tot.day)}</td><td class="num">${wonI(tot.tot)}</td></tr>`;
    return h;};
  const draw=()=>{
    // 매출요약 행(상반기/하반기/합계) — 0은 '-'
    const mrow=(lbl,o,bold)=>{const d=o||{h1:0,h2:0,tot:0};const z=v=>v?wonI(v):'-';return `<tr${bold?' style="font-weight:700"':''}><td>${lbl}</td><td class="num">${z(d.h1)}</td><td class="num">${z(d.h2)}</td><td class="num">${z(d.tot)}</td></tr>`;};
    c.innerHTML=`
     <div class="page-title">일일 영업/매입 현황 <span style="font-size:12px;color:var(--muted);font-weight:400">확정입고·불출 마감기준 · 구분별 누적/당일/총 · 단위 원(공급가, VAT제외)</span></div>
     <div class="toolbar">
       <label class="tl">조회일</label><input type="date" class="inp" id="dp-d" value="${y2d(day)}" style="width:150px">
       <button class="btn" id="dp-go">🔍 조회</button>
       <div class="spacer"></div>
       ${F?`<span class="rowcount">${esc(F.date||'')} 기준</span>`:''}
       <button class="btn xls" id="dp-xls">📥 엑셀</button>
     </div>
     ${loading?`<div style="padding:20px;color:#b8860b">불러오는 중…</div>`:(F?`
     <div style="display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap">
     <div style="flex:0 0 auto;width:560px;max-width:560px;min-width:340px">
     <div class="grid-wrap" style="max-height:calc(100vh - 240px);overflow:auto"><table class="tbl fit" style="min-width:520px">
       <thead><tr><th style="text-align:left">구분</th><th class="num">누적</th><th class="num">당일</th><th class="num">총</th></tr></thead>
       <tbody>
         ${sec(F.pur,F.pur_tot,'매입','#1c47a0')}
         ${sec(F.out,F.out_tot,'불출(매출)','#8a5a1a')}
         ${sec(F.net,F.net_tot,'실매입 (매입 − 불출)','#1c7c3a')}
       </tbody></table></div>
       </div>
       ${F.sales?(()=>{const CG='<colgroup><col><col style="width:130px"><col style="width:54px"></colgroup>';const TS='width:100%;table-layout:fixed;background:#fff';const SN1=3+(F.sales.hyeon_etc?1:0);return `
       <div style="flex:1;min-width:560px;display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap">
         <!-- 가운데: 매출 → 매입비율 → 사급율 (세로 스택, 엑셀형·흰배경·컬럼정렬) -->
         <div style="flex:1;min-width:280px">
           <table class="tbl" style="${TS}"><colgroup><col style="width:60px"><col><col style="width:112px"><col style="width:64px"></colgroup><tbody>
             <tr><td rowspan="${SN1}" style="text-align:center;vertical-align:middle;font-weight:700;background:#eef2f8;color:#1c47a0;border-right:2px solid #555">매출</td><td>현매출 − 절삭</td><td class="num">${wonI(F.sales.hyeon_cut)}</td><td></td></tr>
             <tr><td>현매출 − 설치</td><td class="num">${wonI(F.sales.hyeon_seol)}</td><td></td></tr>
             ${F.sales.hyeon_etc?`<tr><td>현매출 − 기타 <span style="color:var(--muted);font-size:10px">(이지링크/미분류)</span></td><td class="num">${wonI(F.sales.hyeon_etc)}</td><td></td></tr>`:''}
             <tr style="font-weight:700"><td>LG매출 합계</td><td class="num">${wonI(F.sales.lg_sales)}</td><td></td></tr>
             <tr><td rowspan="4" style="text-align:center;vertical-align:middle;font-weight:700;background:#eef2f8;color:#1c47a0;border-top:2px solid #555;border-right:2px solid #555">매입비율</td><td style="border-top:2px solid #555">매입</td><td class="num" style="border-top:2px solid #555">${wonI(F.ratio.pur)}</td><td class="num" style="border-top:2px solid #555"><b>${F.ratio.pur_pct}%</b></td></tr>
             <tr><td>실매입(조정전)</td><td class="num">${wonI(F.ratio.net)}</td><td class="num"><b>${F.ratio.net_pct}%</b></td></tr>
             <tr><td>재고조정 ${F.jaego&&F.jaego.mat_pending?'<span style="color:#c0392b;font-size:10px">(자재 제외)</span>':''}</td><td class="num" style="color:${F.jaego&&F.jaego.total<0?'#c0392b':'#1c7c3a'}">${wonI(F.jaego?F.jaego.total:0)}</td><td></td></tr>
             <tr style="font-weight:700"><td>실재고(조정후)</td><td class="num">${wonI(F.ratio.silrae)}</td><td class="num"><b>${F.ratio.silrae_pct}%</b></td></tr>
             <tr><td rowspan="5" style="text-align:center;vertical-align:middle;font-weight:700;background:#f7f1e8;color:#8a5a1a;border-top:2px solid #555;border-right:2px solid #555">사급율</td><td style="border-top:2px solid #555">원소재 매입</td><td class="num" style="border-top:2px solid #555">${wonI(F.sagubyul.osp_raw)}</td><td class="num" style="border-top:2px solid #555"><b>${F.sagubyul.raw_pct}%</b></td></tr>
             <tr><td>사급부품 매입</td><td class="num">${wonI(F.sagubyul.osp_part)}</td><td class="num"><b>${F.sagubyul.part_pct}%</b></td></tr>
             <tr><td>절삭매출</td><td class="num">${wonI(F.sagubyul.jeolsak_sales)}</td><td></td></tr>
             <tr><td>당사ERP</td><td class="num">${wonI(F.dae.dangsa)}</td><td></td></tr>
             <tr style="font-weight:700"><td>비교(차액)</td><td class="num" style="color:${F.dae.diff<0?'#c0392b':'#1c7c3a'}">${wonI(F.dae.diff)}</td><td></td></tr>
           </tbody></table>
         </div>
         <!-- 맨 오른쪽: 매출요약 (상반기/하반기/합계, 원·흰배경) -->
         ${F.maechul?`<div style="flex:1;min-width:340px">
           <div style="font-weight:700;color:#1c47a0;margin-bottom:4px">매출요약</div>
           <table class="tbl" style="${TS}"><colgroup><col><col style="width:110px"><col style="width:110px"><col style="width:110px"></colgroup><thead><tr><th style="text-align:left">구분</th><th class="num">상반기</th><th class="num">하반기</th><th class="num">합계</th></tr></thead><tbody>
             ${mrow('현매출(절삭)',F.maechul.hyeon_cut)}
             ${mrow('현매출(설치)',F.maechul.hyeon_seol)}
             ${(F.maechul.hyeon_etc&&F.maechul.hyeon_etc.tot)?mrow('현매출(기타)',F.maechul.hyeon_etc):''}
             ${mrow('현매출(합계)',F.maechul.hyeon_hab,true)}
             ${mrow('추가매출(절삭)',F.maechul.chuga_cut)}
             ${mrow('추가매출(설치)',F.maechul.chuga_seol)}
             ${mrow('총 예상매출',F.maechul.chong,true)}
             ${mrow('사급-원재료',F.maechul.sagub_raw)}
             ${mrow('사급-부품(실적)',F.maechul.sagub_part_real)}
             ${mrow('사급-부품(예상)',F.maechul.sagub_part_exp)}
             ${mrow('사급-부품(소계)',F.maechul.sagub_part,true)}
             ${mrow('사급-합계',F.maechul.sagub_hab,true)}
             ${mrow('LG 수금금액',F.maechul.lg_sugum,true)}
           </tbody></table></div>`:''}
       </div>`})():''}
       </div>`:`<div style="padding:20px;color:#8aa0bd">조회일을 선택하고 [조회]를 누르세요.</div>`)}`;
    const gd=()=>d2y(c.querySelector('#dp-d').value);
    c.querySelector('#dp-go').onclick=()=>load(gd());
    c.querySelector('#dp-d').onkeyup=e=>{if(e.key==='Enter')load(gd());};   // Enter로도 조회
    c.querySelector('#dp-xls').onclick=()=>{
      if(!F)return;
      const hd=['섹션','구분','누적','당일','총'];
      const rows=[];
      const push=(sc,list,tot)=>{(list||[]).forEach(r=>rows.push([sc,r.gubun,r.cum,r.day,r.tot]));rows.push([sc,'합계',tot.cum,tot.day,tot.tot]);};
      push('매입',F.pur,F.pur_tot);push('불출',F.out,F.out_tot);push('실매입',F.net,F.net_tot);
      if(F.sales){rows.push([]);
        rows.push(['매출','현매출-절삭',F.sales.hyeon_cut]);rows.push(['매출','현매출-설치',F.sales.hyeon_seol]);
        rows.push(['매출','현매출-기타',F.sales.hyeon_etc]);rows.push(['매출','LG매출합계',F.sales.lg_sales]);
        rows.push(['매입비율','매입/LG매출',F.ratio.pur,'',F.ratio.pur_pct+'%']);rows.push(['매입비율','실매입/LG매출',F.ratio.net,'',F.ratio.net_pct+'%']);
        rows.push(['사급율','원소재/절삭매출',F.sagubyul.osp_raw,'',F.sagubyul.raw_pct+'%']);rows.push(['사급율','부품/절삭매출',F.sagubyul.osp_part,'',F.sagubyul.part_pct+'%']);
        rows.push(['대사','당사ERP',F.dae.dangsa]);rows.push(['대사','LG전산',F.dae.lg]);rows.push(['대사','차액',F.dae.diff]);}
      downloadCSV(`일일영업매입현황_${F.date}.csv`,hd,rows);};
  };
  draw();   // ★초기엔 자동조회 안 함 — 조회일(기본 오늘) 확인 후 조회/Enter로 조회
};
