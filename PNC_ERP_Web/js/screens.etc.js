/* ===== PNC ERP screens.etc.js — 협력사/경영/시스템 SCREEN (app.js 분할, 순수이동) ===== */

/* 시스템관리 > 마감관리 — 일/월마감 현황(잠금상태) + 실행·취소. 실제 마감은 쓰기라 운영DB(읽기전용)엔 불가 → 신규DB/백엔드에서 */
SCREEN.close=(c)=>{
  /* 시스템관리 > 마감관리 — 일/월 마감 실행·해제·현황.
     ★마감 = ①그 시점 잔량을 스냅샷으로 확정(freeze) + ②잠금(그 기간 재고이동 전표 CRUD 차단).
       정본 = nx.period_close(잠금) + nx.stock_snapshot(확정) · 백엔드 /api/close/*
       ※구 /api/live/closestatus 는 레거시 임시테이블(PU_T_MONTH_STOCK_WH_DAILY, 조회시 TRUNCATE)의
         MAX() 를 '최종마감'으로 표시해 부정확 → 사용하지 않는다. */
  const API=API_BASE;
  const DOM=[['MAT','자재'],['PRD','생산'],['SAL','영업']];
  let dom='MAT', st=null, cal=null, busy=false;
  // ★입력값은 상태로 보존 — draw() 가 innerHTML 을 통째로 다시 그리므로, 값을 DOM 에서만 읽으면
  //   마감 실행 후 대상일/대상월/조회월이 오늘·이번달로 리셋된다(게이트D에서 실제 발생).
  let dday=nowCD(), dmon=nowCM(), calm=nowCM();
  const fmtYm=y=>{y=(''+(y||''));return y.length>=4?('20'+y.slice(0,2)+'-'+y.slice(2,4)):'-';};
  const fmtYmd=y=>{y=(''+(y||''));return y.length>=6?('20'+y.slice(0,2)+'/'+y.slice(2,4)+'/'+y.slice(4,6)):'-';};
  const ymIn=v=>(''+(v||'')).slice(2).replace('-','');
  const ymdIn=v=>(''+(v||'')).slice(2).replace(/-/g,'');
  const who=()=>{try{return (PERM&&PERM.userId)||'web';}catch(e){return 'web';}};   // ★PERM 필드명은 userId — 'user' 로 읽으면 항상 'web' 이 되어 백엔드 권한게이트에 차단됨(2026-08-27 수정)
  // ★C5 권한 게이트 — 마감/해제는 회계 확정/되돌리기라 명시 권한자만. 백엔드가 최종 판정(403)하고, 여기선 오조작 방지용 UI 차단.
  // ★백엔드 _assert_can_close 와 동일 규칙(deny by default). PERM.isAdmin() 은 쓰지 않는다 —
  //   core.js currentUser() 가 미등록 사용자를 '시스템관리자'로 기본 반환(fail-open)해서 게이트가 열림.
  const canClose=()=>{try{
    const u=(typeof getUsers==='function')?getUsers().find(x=>x.id===PERM.userId):null;
    if(u&&(u.roles||[]).includes('시스템관리자'))return true;
    const pm=(PERM.perms[PERM.userId]||{})['close']; return !!(pm&&pm.edit);
  }catch(e){return false;}};
  const call=async(path,body)=>{
    if(busy)return null; busy=true;
    try{
      const r=await fetch(API+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const j=await r.json();
      if(!r.ok){alert('실패 — '+(j.detail||r.status));return null;}
      alert(j.msg||'완료'); return j;
    }catch(e){alert('통신 실패: '+e.message);return null;}
    finally{busy=false; load();}
  };
  const load=async()=>{
    try{
      const r=await fetch(API+'/api/close/status'); st=await r.json();
      const r2=await fetch(API+'/api/close/calendar?domain='+dom+'&ym='+ymIn(calm)); cal=await r2.json();
    }catch(e){ st=null; }
    draw();
  };
  const draw=()=>{
    if(!st){c.innerHTML='<div class="page-title">마감관리</div><div class="empty" style="padding:40px">마감현황을 불러오지 못했습니다 — 백엔드 확인</div>';return;}
    const asof=fmtYmd(st.asof), rows=st.rows||[];
    const domNm=(DOM.find(d=>d[0]===dom)||['',''])[1];
    let h='';
    h+='<div class="page-title">마감관리</div>';
    h+='<div class="page-sub">일/월 마감 실행·해제 · 기준일 '+esc(asof)+' · <b>마감 = 확정 + 잠금</b>(그 시점 잔량을 스냅샷으로 확정하고, 그 기간 재고이동 전표는 생성·수정·삭제 불가)</div>';
    h+='<div class="grid-wrap" style="max-height:300px;overflow:auto;margin-bottom:14px"><table class="tbl fit"><thead>';
    h+='<tr><th>영역</th><th class="center">마감유형</th><th class="center">최종 마감</th><th class="center">스냅샷</th><th class="center">마감자</th><th class="center">마감일시</th></tr></thead><tbody>';
    rows.forEach(r=>{
      const last = r.last ? esc(r.ptype==='M'?fmtYm(r.last):fmtYmd(r.last)) : '<span style="color:#c0392b">없음</span>';
      const snap = r.snap_ready ? '<span class="badge b-green">확정</span>' : '<span class="badge b-red">2단계</span>';
      h+='<tr><td><b>'+esc(r.domain_nm)+'</b></td><td class="center">'+esc(r.ptype_nm)+'</td><td class="center">'+last+'</td>'
       + '<td class="center">'+snap+'</td><td class="center">'+esc(r.user||'')+'</td>'
       + '<td class="center" style="font-size:11px">'+esc((r.dt||'').slice(0,19))+'</td></tr>';
    });
    h+='</tbody></table></div>';
    h+='<div class="page-sub" style="font-weight:700;margin:6px 0">마감 실행 / 해제</div>';
    h+='<div class="toolbar"><label class="tl">영역</label><select class="inp" id="dom">'
     + DOM.map(d=>'<option value="'+d[0]+'"'+(dom===d[0]?' selected':'')+'>'+d[1]+'</option>').join('')+'</select>';
    h+='<label class="tl" style="margin-left:8px">일마감 대상일</label><input type="date" class="inp" id="dday" value="'+dday+'" style="min-width:135px">';
    h+=canClose()?'<button class="btn" id="runday">일마감 실행</button><button class="btn ghost" id="canday">일마감 해제</button>':'<span style="color:#c0392b;font-size:12px">🔒 마감 권한 없음</span>';
    h+='<span style="width:14px"></span>';
    h+='<label class="tl">월마감 대상월</label><input type="month" class="inp" id="dmon" value="'+dmon+'" style="min-width:120px">';
    h+=(canClose()?'<button class="btn" id="runmon">월마감 실행</button><button class="btn ghost" id="canmon">월마감 해제</button>':'')+'</div>';
    h+='<div class="page-sub" style="color:var(--muted);margin:4px 0 10px">마감은 <b>순서대로</b>만 됩니다(직전 기간이 마감돼 있어야 함). 해제는 <b>최근 기간부터</b> 역순 — 후속 기간이 마감돼 있으면 거부됩니다.'
     + (st.mat_daily_max?(' · 자재 일별잔량 최신 <b>'+esc(fmtYmd(st.mat_daily_max))+'</b> (일마감은 이 데이터가 있는 날만 가능)'):'')+'</div>';
    h+='<div class="page-sub" style="font-weight:700;margin:16px 0 6px">일자별 마감 캘린더 <span style="font-weight:400;color:var(--muted)">— '+esc(domNm)+'</span></div>';
    h+='<div class="toolbar" style="border:none;padding:0;margin-bottom:8px"><label class="tl">조회월</label>'
     + '<input type="month" class="inp" id="calm" value="'+calm+'" style="min-width:120px">'
     + '<span style="font-size:12px;color:var(--muted)">마감완료 · 미마감 · 파란테두리=오늘 · 날짜 클릭 = 그 날 일마감 실행/해제</span></div>';
    h+='<div class="grid-wrap" style="overflow:auto;border:none"><table class="cal"><thead><tr>'
     + ['일','월','화','수','목','금','토'].map(d=>'<th>'+d+'</th>').join('')+'</tr></thead><tbody id="calbody"></tbody></table></div>';
    c.innerHTML=h;
    renderCal();
    const g=id=>c.querySelector(id);
    g('#dom').onchange=e=>{dom=e.target.value;load();};
    g('#dday').onchange=e=>{dday=e.target.value;};
    g('#dmon').onchange=e=>{dmon=e.target.value;};
    g('#calm').onchange=e=>{calm=e.target.value;load();};
    if(g('#runday'))g('#runday').onclick=()=>call('/api/close/run',{domain:dom,ptype:'D',period:ymdIn(dday),user:who()});
    if(g('#canday'))g('#canday').onclick=()=>{if(confirm('일마감을 해제합니다. 확정 스냅샷도 함께 제거됩니다.'))call('/api/close/cancel',{domain:dom,ptype:'D',period:ymdIn(dday),user:who()});};
    if(g('#runmon'))g('#runmon').onclick=()=>call('/api/close/run',{domain:dom,ptype:'M',period:ymIn(dmon),user:who()});
    if(g('#canmon'))g('#canmon').onclick=()=>{if(confirm('월마감을 해제합니다. 확정 스냅샷도 함께 제거됩니다.'))call('/api/close/cancel',{domain:dom,ptype:'M',period:ymIn(dmon),user:who()});};
    attachResizers(c);
  };
  const renderCal=()=>{
    const p=calm.split('-'), Y=+p[0], M=+p[1];
    const ymm=String(Y).slice(2)+String(M).padStart(2,'0');
    const closedDays=new Set((cal&&cal.closed_days)||[]), monthClosed=!!(cal&&cal.month_closed);
    const asofYmd=''+(st.asof||'');
    const first=new Date(Y,M-1,1).getDay(), days=new Date(Y,M,0).getDate();
    let cells=[]; for(let i=0;i<first;i++)cells.push('<td class="empty"></td>');
    for(let d=1;d<=days;d++){
      const ymd=ymm+String(d).padStart(2,'0');
      const closed=monthClosed||closedDays.has(ymd);
      const future=ymd>asofYmd, today=ymd===asofYmd;
      const dow=(first+d-1)%7;
      const cls=[dow===0?'sun':'',dow===6?'sat':'',closed?'closed':(future?'future':'open'),today?'today':''].filter(Boolean).join(' ');
      const mk=closed?('<div class="mk">'+(monthClosed?'월마감':'마감')+'</div>'):(future?'':'<div class="mk">미마감</div>');
      cells.push('<td class="'+cls+'" data-day="'+ymd+'"><span class="dn">'+d+'</span>'+mk+'</td>');
    }
    while(cells.length%7)cells.push('<td class="empty"></td>');
    let html=''; for(let i=0;i<cells.length;i+=7)html+='<tr>'+cells.slice(i,i+7).join('')+'</tr>';
    c.querySelector('#calbody').innerHTML=html;
    c.querySelectorAll('.cal td[data-day]').forEach(td=>td.onclick=()=>{
      const y=td.dataset.day, isC=td.classList.contains('closed');
      if(isC&&monthClosed){alert('월마감으로 잠긴 날입니다 — 월마감을 먼저 해제하세요.');return;}
      if(isC){ if(confirm(fmtYmd(y)+' 일마감을 해제합니다.'))call('/api/close/cancel',{domain:dom,ptype:'D',period:y,user:who()}); }
      else   { if(confirm(fmtYmd(y)+' 일마감을 실행합니다.'))call('/api/close/run',{domain:dom,ptype:'D',period:y,user:who()}); }
    });
  };
  c.innerHTML='<div class="page-title">마감관리</div><div class="empty" style="padding:40px">'+SPIN+'마감현황 로딩…</div>';
  load();
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
  // ★정본 = nx.app_user (2026-08-29). localStorage 는 더 이상 계정의 근거가 아니다.
  //   비밀번호는 서버가 내주지 않는다 — pw_set(설정여부)만 온다.
  const load=async()=>{try{const r=await fetch(API_BASE+'/api/perm/users');
    if(!r.ok)return null; const j=await r.json(); return Array.isArray(j.users)?j.users:null;}catch(e){return null;}};
  let users=[], editMode=false, loadErr='';
  const CT=['내부','협력사'], ST=['사용','정지'];
  const cols=[{f:'id',h:'ID'},{f:'pw',h:'비밀번호',pw:1},{f:'nm',h:'이름'},{f:'type',h:'구분',sel:CT},{f:'dept',h:'부서'},{f:'pos',h:'직책'},{f:'roles',h:'역할',roles:1},{f:'partner',h:'협력사'},{f:'email',h:'이메일'},{f:'tel',h:'연락처'},{f:'status',h:'상태',sel:ST}];
  const draw=()=>{
    c.innerHTML=`
     <div class="page-title">👤 사용자관리</div>
     <div class="page-sub">계정 정본 = <b>nx.app_user</b> · 비밀번호는 <b>PBKDF2 해시</b>로 저장되며 화면에 나오지 않습니다 ·
       <b>비밀번호를 비워두면 기존 비밀번호가 그대로 유지</b>됩니다(바꿀 때만 입력) ·
       계정을 지우려면 <b>상태를 '정지'</b>로 두세요(목록에서 빼는 것으로는 지워지지 않습니다) ·
       협력사 칸 = <b>거래처코드</b> · 프로그램별 권한은 「권한관리」${loadErr?` · <span class="neg">${esc(loadErr)}</span>`:''}</div>
     <div class="toolbar"><input class="inp" id="q" placeholder="ID·이름·부서·협력사">
       ${editMode?`<button class="btn" id="add">➕ 추가</button><button class="btn" id="save">💾 저장</button><button class="btn ghost" id="cancel">✖ 취소</button>`:(PERM.canEdit('users')?`<button class="btn" id="edit">✎ 수정</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc(PERM.label())})</span>`)}
       <div class="spacer"></div><span class="rowcount" id="cnt"></span></div>
     <div class="grid-wrap" style="max-height:520px;overflow:auto"><table class="tbl fit"><thead><tr>${cols.map(cc=>`<th>${cc.h}</th>`).join('')}${editMode?'<th class="center">삭제</th>':''}</tr></thead><tbody id="tb"></tbody></table></div>`;
    const disp=(cc,u)=>{ if(cc.pw)return u.pw_set?'설정됨':'<span class="neg">미설정</span>';
      if(cc.roles)return (u.roles||[]).map(r=>`<span class="badge">${esc(r)}</span>`).join(' ');
      return esc(''+(u[cc.f]||'')); };
    const editCell=(cc,u,i)=>{
      if(cc.sel)return `<select data-i="${i}" data-f="${cc.f}">${cc.sel.map(o=>`<option ${u[cc.f]===o?'selected':''}>${esc(o)}</option>`).join('')}</select>`;
      if(cc.roles)return `<div style="min-width:150px">${ROLES.map(r=>`<label style="margin-right:6px;white-space:nowrap;font-size:11px"><input type="checkbox" data-i="${i}" data-role="${esc(r)}" ${(u.roles||[]).includes(r)?'checked':''}>${esc(r)}</label>`).join('')}</div>`;
      if(cc.pw)return `<input data-i="${i}" data-f="pw" type="password" value="" placeholder="비우면 유지" style="width:95px">`;
      return `<input data-i="${i}" data-f="${cc.f}" value="${esc(''+(u[cc.f]||''))}" style="width:${cc.f==='email'?150:95}px">`;
    };
    const rend=()=>{
      const q=(c.querySelector('#q').value||'').toLowerCase();
      const vis=users.map((u,i)=>({u,i})).filter(({u})=>!q||(''+u.id+u.nm+u.dept+u.partner).toLowerCase().includes(q));
      c.querySelector('#tb').innerHTML=vis.map(({u,i})=>`<tr>${cols.map(cc=>`<td>${editMode?editCell(cc,u,i):disp(cc,u)}</td>`).join('')}${editMode?`<td class="center"><button class="btn xs ghost" data-del="${i}">✕</button></td>`:''}</tr>`).join('')||`<tr><td colspan="${cols.length+1}" class="empty">없음</td></tr>`;
      if(editMode){
        c.querySelectorAll('#tb input[data-f],#tb select[data-f]').forEach(el=>el.onchange=()=>{users[+el.dataset.i][el.dataset.f]=el.value;});
        c.querySelectorAll('#tb input[data-role]').forEach(el=>el.onchange=()=>{const u=users[+el.dataset.i];u.roles=u.roles||[];const r=el.dataset.role;if(el.checked){if(!u.roles.includes(r))u.roles.push(r);}else u.roles=u.roles.filter(x=>x!==r);});
        // ★목록에서 빼도 서버는 계정을 지우지 않는다(그래야 화면이 일부만 보냈을 때 계정이 증발하지 않는다).
        //   그래서 삭제 버튼은 **상태를 '정지'** 로 바꾼다 — 실제로 로그인이 막히는 방법이다.
        c.querySelectorAll('[data-del]').forEach(b=>b.onclick=()=>{const u=users[+b.dataset.del];
          u.status=(u.status==='정지')?'사용':'정지'; rend();});
      }
      c.querySelector('#cnt').textContent=`${users.length}명 (내부 ${users.filter(u=>u.type==='내부').length}·협력사 ${users.filter(u=>u.type==='협력사').length}) · ${editMode?'✎수정중':'읽기전용'}`;
    };
    if(editMode){
      c.querySelector('#add').onclick=()=>{users.push({id:'',pw:'',nm:'',type:'내부',dept:'',pos:'',roles:['조회전용'],partner:'',email:'',tel:'',status:'사용',pw_set:false});rend();};
      c.querySelector('#save').onclick=async()=>{
        let msg='';
        try{const r=await PERM.saveUsersToServer(users); const j=await r.json();
          msg=r.ok&&j.ok?`저장되었습니다 — 신규 ${j.new} · 수정 ${j.updated} · 비밀번호 변경 ${j.pw_changed}건`
                        :`저장 실패 — ${(j&&j.detail)||'백엔드 확인 필요'}`;}
        catch(e){msg='저장 실패 — 서버에 연결하지 못했습니다.';}
        editMode=false; users=(await load())||users; draw(); alert(msg);};
      c.querySelector('#cancel').onclick=async()=>{users=(await load())||users;editMode=false;draw();};
    } else if(c.querySelector('#edit')) c.querySelector('#edit').onclick=()=>{editMode=true;draw();};
    c.querySelector('#q').onkeyup=rend;
    rend();
  };
  draw();
  // 최초 진입 시 서버에서 정본을 읽는다
  (async()=>{const u=await load();
    if(u)users=u; else loadErr='서버에서 계정을 읽지 못했습니다(권한 또는 연결 확인).';
    draw();})();
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

/* ★출력 양식 3종의 정의 위치 = 여기(모듈 스코프) — 2026-08-31.
     왜 옮겼나: 종전엔 SCREEN.deliv420(발행화면) **안**에 정의하고 화면이 그려질 때
     window 에 실었다. 그래서 「거래명세표 수정」만 열고 출력하면 window.openDelivInvoice 가
     아직 undefined → 조용히 구식 단순표로 떨어졌다(사용자 지적: "수정 양식은 왜 그대로야?").
     모듈 스코프로 올리면 **파일 로드 시점에 등록**되어 어느 화면에서 부르든 같은 양식이 나온다.
   ※ esc·_barcodeDataURL 은 core.js 전역(먼저 로드됨). nf 는 여기 지역으로 둔다. */
const _fmNf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});

// ── 거래명세표 인쇄 (레거시 dw_pr_outside_020_p1 서식 · 공급자=협력사/공급받는자=당사 · SET바코드 Code39) ──
const openDelivInvoice=(iv)=>{
  if(!iv||!iv.rows||!iv.rows.length)return alert('발행 명세가 없습니다.');
  const bc=_barcodeDataURL(iv.code);          // Code39: *SET+발행번호*
  // ★레거시 거래명세표 서식(2026-08-27 실물 확인):
  //   컬럼 = No. · Assy P/No. · 하위 P/No. · 품명 · 수 량 · 검사 · 비고
  //   ·**20행 고정**(빈행 포함) · 합계행 · 하단 = SET바코드 + 자재팀/품질팀 결재란
  //   ·공급자/공급받는자 정보는 등록번호·상호·대표자·주소·TEL·Fax
  const party=p=>`<table class="pt">`
    +`<tr><td class="k">등록번호</td><td>${esc(p.biz)}</td></tr>`
    +`<tr><td class="k">상&nbsp;&nbsp;&nbsp; 호</td><td>${esc(p.nm)}</td></tr>`
    +`<tr><td class="k">대 표 자</td><td>${esc(p.owner)}</td></tr>`
    +`<tr><td class="k">주&nbsp;&nbsp;&nbsp; 소</td><td>${esc(p.addr)}</td></tr>`
    +`<tr><td class="k">TEL</td><td>${esc(p.tel)}</td></tr>`
    +`<tr><td class="k">Fax</td><td>${esc(p.fax||'')}</td></tr></table>`;
  // ★Assy 행 병합(2026-08-31 레거시 실물 대조) — 레거시는 **1행부터 하위 P/No.**가 들어간다.
  //   레거시:  14 | AJR30078601 | AJR30078601-12-1 | 대원 SUB     ← 한 줄
  //            15 |             | AJR30078601-12-2 | 대원 SUB
  //            16 |             | AJR30078601-12-3 | 대원 SUB     = 3행
  //   웹(종전): Assy 전용 행을 따로 뽑아 4행이 됐다 → 첫 하위를 Assy 행으로 끌어올려 합친다.
  //   ★백엔드 rows 는 납품표·검사성적서도 공유하므로 **출력 시점에만** 병합한다(원본 무변경).
  //   하위가 없는 도번은 종전대로 한 행(Assy 만).
  const mergeAssy=(src)=>{
    const out=[];
    for(let i=0;i<src.length;i++){
      const x=src[i], nx=src[i+1];
      if(x.doban && nx && !nx.doban && nx.sub){          // 도번행 + 뒤따르는 첫 하위행 → 한 줄
        // ★검사는 **하위(nx) 값 우선** — 이 행이 보여주는 품번이 하위 P/No. 이기 때문.
        //   레거시 실물도 -12-1 행은 공백, -12-3 행에 '유검사' 로 자도번별로 다르게 찍힌다.
        out.push(Object.assign({},nx,{doban:x.doban,insp:nx.insp||x.insp||'',note:nx.note||x.note||''}));
        i++;                                             // 첫 하위행은 소비됨
      }else out.push(x);
    }
    return out;
  };
  const _rows=mergeAssy(iv.rows||[]);
  // ★20행 초과 시 페이지 분할(2026-08-27 사용자 요청). 바코드·합계는 모든 페이지 동일.
  const ROWN=20;
  const pages=[];
  for(let s=0;s<Math.max(1,_rows.length);s+=ROWN) pages.push(_rows.slice(s,s+ROWN));
  const PN=pages.length;
  const bodyOf=(pg,pi)=>{
    const out=[];
    pg.forEach((x,i)=>{
      out.push(`<tr><td>${pi*ROWN+i+1}</td>`
        +`<td title="${esc(x.doban)}">${esc(x.doban)}</td>`
        +`<td class="l" title="${esc(x.sub||'')}">${esc(x.sub||'')}</td>`
        +`<td class="l" title="${esc(x.nm)}">${esc(x.nm)}</td><td class="r">${_fmNf(x.qty)}</td>`
        +`<td>${esc(x.insp||'')}</td><td>${esc(x.note||'')}</td></tr>`);
    });
    for(let i=pg.length;i<ROWN;i++)
      out.push(`<tr><td>${pi*ROWN+i+1}</td><td></td><td></td><td></td><td></td><td></td><td></td></tr>`);
    return out.join('');
  };
  const _sv=iv.svcmark?` <span class="svcm">[${esc(iv.svcmark)}]</span>`:'';   // ★SVC 분리표시
  const copy=(title,pg,pi)=>`<div class="cp"><div class="tt">거래명세표${_sv}</div><div class="sb">${title}</div>
    <div class="mt"><span>출고일자 : ${esc(iv.ymd)}</span><span>PAGE:${pi+1}/${PN}</span></div>
    <table class="pi"><tr><td class="vl">공<br>급<br>자</td><td>${party(iv.supplier)}</td><td class="vl">공<br>급<br>받<br>는<br>자</td><td>${party(iv.buyer)}</td></tr></table>
    <!-- ★칸 폭(2026-08-31 3차 — 실측 계산으로 확정). table-layout:fixed + width:100% 라
         colgroup 의 px 는 **비율 힌트**로만 쓰이고 실제 폭은 단 폭에 압축된다
         (창 1240 → 한 단 ≈600px · **인쇄 A4가로 ≈523px** ← 이쪽이 빡빡하므로 인쇄 기준).
         경위: 1차 품번에 23/24% 몰아줌 → 헤더 '수 량·검사·비고'와 행번호 10 이상이 잘림.
               2차 우측 칸 확대 → 이번엔 인쇄에서 품번이 부족(화면만 OK).
         3차 = 검사표기를 '유/체' **한 글자**로 줄여(사용자 확정) 확보한 여유를 품번에 준다.
         인쇄 523px 기준 필요폭 실측: No.17 · Assy 104 · 하위 115(19자 한글포함) ·
           수량 29 · 검사 21(한글1자+헤더'검사') · 비고 32 → 고정합 ≈345px, 품명 178px.
         품명은 무지정(<col>)이라 나머지를 갖고, 넘치면 ellipsis+title 툴팁(레거시도 잘린다). -->
    <table class="it"><colgroup><col style="width:5%"><col style="width:21.5%"><col style="width:23.5%"><col><col style="width:7.5%"><col style="width:6.5%"><col style="width:8%"></colgroup>
    <thead><tr><th>No.</th><th>Assy P/No.</th><th>하위 P/No.</th><th>품명</th><th>수 량</th><th>검사</th><th>비고</th></tr></thead>
    <tbody>${bodyOf(pg,pi)}<tr class="tot"><td colspan="4" class="r">합계</td><td class="r">${_fmNf(iv.total)}</td><td colspan="2"></td></tr></tbody></table>
    <div class="ft"><div class="bc"><div class="bt">${esc(iv.barcode)}</div><img src="${bc}"></div>
      <table class="sp"><tr><td>자재팀</td><td>품질팀</td></tr><tr><td class="bx"></td><td class="bx"></td></tr></table></div></div>`;
  const w=window.open('','_blank','width=1240,height=900');
  if(!w)return alert('팝업 차단됨 — 팝업 허용 후 다시 시도하세요.');
  w.document.write(`<html><head><title>거래명세표${iv.svcmark?' ['+esc(iv.svcmark)+']':''} ${esc(iv.barcode)}</title><meta charset="utf-8"><style>
    @page{size:A4 landscape;margin:6mm}
    .svcm{color:#c00;font-weight:700}
    body{font-family:'맑은 고딕',Malgun Gothic,sans-serif;margin:6px;font-size:10.5px;color:#000}
    .wrap{display:flex;gap:12px}.cp{flex:1;padding:2px}
    .tt{text-align:center;font-size:19px;font-weight:700;letter-spacing:3px;text-decoration:underline}
    .sb{text-align:center;font-size:11px;margin:2px 0 4px}
    .mt{display:flex;justify-content:space-between;font-size:10.5px;margin:2px 0}
    /* ★table-layout:fixed 필수 — 없으면 브라우저가 내용에 맞춰 폭을 재배분해
       품명이 두 줄로 깨지고 행 높이가 들쭉날쭉해진다(레거시는 전 행 균일). */
    table{border-collapse:collapse;width:100%;table-layout:fixed}
    .pi{table-layout:fixed}
    .pi td{border:1px solid #000;padding:0;vertical-align:middle}
    .pi>tbody>tr>td:nth-child(2),.pi>tbody>tr>td:nth-child(4){width:calc(50% - 15px)}
    .vl{width:15px;text-align:center;font-weight:600;font-size:10px;line-height:1.15}
    .pt{border:none;table-layout:fixed}.pt td{border:1px solid #000;padding:2px 4px;height:19px}
    .pt .k{width:56px;text-align:center;white-space:nowrap;font-size:10px}
    /* 주소는 두 줄까지 허용(레거시 동일), 나머지는 한 줄 고정 */
    .pt td:not(.k){overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .pt tr:nth-child(4) td:not(.k){white-space:normal;line-height:1.25;height:30px}
    .it th,.it td{border:1px solid #000;padding:1px 3px;text-align:center;height:18px;
      overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .it .l{text-align:left}.it .r{text-align:right}
    .it thead th{font-weight:700}
    .tot td{font-weight:700}
    .ft{display:flex;justify-content:space-between;align-items:flex-end;margin-top:4px}
    .bc{border:1.5px solid #000;padding:3px 6px;min-width:210px}
    .bc img{height:34px;display:block;width:100%}
    .bt{font-family:'맑은 고딕',monospace;font-size:12px;font-weight:700;margin-bottom:2px}
    .sp{width:200px}.sp td{border:1px solid #000;text-align:center;padding:2px;font-size:10.5px}
    .sp .bx{height:34px}
    @media print{.noprint{display:none}}</style></head>
    <body><div class="noprint" style="margin-bottom:6px"><button onclick="window.print()">🖨️ 인쇄</button> <button onclick="window.close()">닫기</button>
      <span style="margin-left:8px;color:#555;font-size:11px">${esc(iv.barcode)} · ${_rows.length}건 · ${PN}페이지</span></div>
    ${pages.map((pg,pi)=>`<div class="wrap"${pi?' style="page-break-before:always"':''}>${copy('공급자',pg,pi)}${copy('공급받는자',pg,pi)}</div>`).join('')}</body></html>`);
  w.document.close();
};
// ★거래명세표 양식 공유(2026-08-31) — 「거래명세표 수정」의 재출력도 같은 서식을 써야 한다.
//   이 함수는 SCREEN.deliv420 지역이라 다른 화면에서 못 부른다 → 전역에 실어 공유한다.
//   (양식을 복사하면 또 어긋나므로 정의는 여기 하나만 둔다)
// ── ★납품표 인쇄 (레거시 2번 출력물) — 페이지당 4장(2×2) 카드형 ──
//   레거시 실물(2026-08-27):
//     ┌──── PNC_260806_00:05  납품표 ────┐
//     │ 업체명   │ 대원산업              │
//     │ 모도번   │ AJJ76418705           │
//     │ 작업처   │ 대 원 산 업           │
//     │ 자도번   │ AJJ76418705(1)검      │
//     │ 입고셋트 │ 26                    │
//     │ 납품일   │ 26/08/27(목)          │
//     │ 입고구분 │ 세트                  │
//     │ 표준포장수│ 26        1 / 1      │
//     │ 생산계획 │ 26/08/26  LG 26/08/26 │
const openDelivNote=(iv)=>{
  if(!iv||!iv.rows||!iv.rows.length)return alert('발행 명세가 없습니다.');
  const DOW='일월화수목금토';
  const ymdD=(s)=>{const d=String(s||'').replace(/\D/g,'');
    if(d.length<8)return String(s||'');
    const dt=new Date(+d.slice(0,4),+d.slice(4,6)-1,+d.slice(6,8));
    return `${d.slice(2,4)}/${d.slice(4,6)}/${d.slice(6,8)}(${DOW[dt.getDay()]})`;};
  const nd=ymdD(iv.ymd);
  // 도번 행만(하위 자재행 제외) — 납품표는 도번 단위
  const list=iv.rows.filter(x=>x.doban);
  const jl=(x)=>{const a=(x.subs||[]).slice(0,6);return a.length?a.join('<br>'):esc(x.doban)+'(1)';};
  /* ★제목 = **당사 회사명 + 납품표**(2026-08-31 레거시 실물 대조).
       레거시: 「(주)피앤씨인더스트리   납품표」
       종전엔 iv.title(=백엔드 식별자 'PNC_260831')을 찍어 「PNC_260831  납품표」가 나왔다.
       회사명은 CM_M_COMPANY 에서 온 iv.buyer.nm(공급받는자=당사). SVC 표시는 뒤에 붙인다. */
  const _co=(iv.buyer&&iv.buyer.nm)||'(주)피앤씨인더스트리';
  const _hd=`${esc(_co)}&nbsp;&nbsp; 납품표${iv.svcmark?` <span class="svcm">[${esc(iv.svcmark)}]</span>`:''}`;
  const card=(x)=>x?`<table class="nt">
      <tr><td class="ttl" colspan="2">${_hd}</td></tr>
      <tr><th>업체명</th><td class="c">${esc(iv.custnm)}</td></tr>
      <tr><th>모도번</th><td class="c big">${esc(x.doban)}</td></tr>
      <tr><th>작업처</th><td class="c big">${esc(x.wc||iv.custnm)}</td></tr>
      <tr><th>자도번</th><td class="c sm jd">${jl(x)}</td></tr>
      <tr><th>입고셋트</th><td class="c big">${_fmNf(x.qty)}</td></tr>
      <tr><th>납품일</th><td class="c">${esc(nd)}</td></tr>
      <tr><th>입고구분</th><td class="c b">${esc(x.gubun||'세트')}</td></tr>
      <tr><th>표준포장수</th><td class="c"><span class="lf">${_fmNf(x.pack||x.qty)}</span><span class="rt">1 / 1</span></td></tr>
      <tr><th>생산계획</th><td class="c"><span class="lf">${esc(x.plan_ymd||'')}</span><span class="rt">LG ${esc(x.lg_ymd||'')}</span></td></tr>
    </table>`
    /* ★빈 카드도 출력(2026-08-31 사용자 확정) — 남는 자리를 뼈대만 있는 표로 채운다.
         현장에서 손으로 적어 쓰는 여분 양식이라 페이지가 6칸으로 항상 꽉 차야 한다.
         제목줄은 실제 카드와 동일하게 넣는다(종전 빈 카드는 제목이 비어 있었다). */
    :`<table class="nt">
      <tr><td class="ttl" colspan="2">${_hd}</td></tr>
      ${['업체명','모도번','작업처','자도번','입고셋트','납품일','입고구분','표준포장수','생산계획']
        .map(k=>`<tr><th>${k}</th><td${k==='자도번'?' class="jd"':''}>&nbsp;</td></tr>`).join('')}
    </table>`;
  // ★페이지당 6장(3행 × 2열) — 레거시 실물과 동일(2026-08-31). 종전엔 4장이었다.
  const PG=[]; for(let i=0;i<list.length;i+=6) PG.push(list.slice(i,i+6));
  if(!PG.length) PG.push([]);
  const w=window.open('','_blank','width=900,height=1000');
  if(!w)return alert('팝업 차단됨 — 팝업 허용 후 다시 시도하세요.');
  w.document.write(`<html><head><title>납품표${iv.svcmark?' ['+esc(iv.svcmark)+']':''} ${esc(iv.barcode)}</title><meta charset="utf-8"><style>
    @page{size:A4;margin:8mm}
    body{font-family:'맑은 고딕',Malgun Gothic,sans-serif;margin:0;font-size:12px;color:#000}
    /* ★레거시 실물 배치(2026-08-31): A4 세로 1장 = 3행 × 2열 = 6장.
         카드 사이는 절취 점선(레거시 동일). 빈 카드는 아예 그리지 않는다. */
    .pgw{display:grid;grid-template-columns:1fr 1fr;gap:0;page-break-inside:avoid}
    .nt{border-collapse:collapse;width:100%;table-layout:fixed;border:1.5px solid #000;
        margin:5px 8px}
    .nt th,.nt td{border:1px solid #000;padding:2px 6px;height:21px;font-size:12px}
    .nt th{width:80px;text-align:center;font-weight:700;background:#fff}
    .ttl{text-align:center;font-weight:700;font-size:13px;height:23px;border-bottom:1.5px solid #000}
    .svcm{color:#c00}
    .c{text-align:center}.big{font-size:17px;font-weight:700;letter-spacing:1px}
    .b{font-weight:700}.sm{font-size:10px}
    /* 자도번 = 위 정렬 + 넉넉한 높이(레거시는 여러 줄이 위에서부터 쌓이고 아래가 빈다) */
    .jd{height:72px;vertical-align:top;line-height:1.4;padding-top:4px}
    .lf{float:left}.rt{float:right}
    /* 절취 점선 — 세로 3분할·가로 2분할 경계 */
    .pgw{position:relative}
    .cell{position:relative}
    .cell.r{border-left:1px dashed #666}
    .cell.b2{border-bottom:1px dashed #666}
    @media print{.np{display:none}}
  </style></head><body>
    <div class="np" style="margin:0 0 10px"><button onclick="window.print()">🖨️ 인쇄</button> <button onclick="window.close()">닫기</button>
      <span style="margin-left:8px;color:#555;font-size:12px">납품표 · ${esc(iv.custnm)} · ${list.length}건 · ${PG.length}페이지</span></div>
    ${PG.map((pg,pi)=>`<div class="pgw"${pi?' style="page-break-before:always"':''}>
       ${/* ★A4 1장 = 항상 6칸. 모자라는 자리는 빈 카드로 채운다(사용자 확정 2026-08-31). */
         [0,1,2,3,4,5].map(k=>{
          const cls=['cell']; if(k%2===1)cls.push('r'); if(k<4)cls.push('b2');
          return `<div class="${cls.join(' ')}">${card(pg[k])}</div>`;}).join('')}</div>`).join('')}
    </body></html>`);
  w.document.close();
};
// ── ★출하검사성적서 인쇄 (레거시 3번 출력물) — 페이지당 2장 ──
//   ★검사품(insp='1')만 출력한다. 무검사는 성적서가 없다.
//   레거시 실물: 회사명·Assy P/NO·단품 P/NO·검사일자 / 검사방법·Lot Size·측정기명·검사원
//                / 검사항목·규격치·검사수준·X1~X5·시료수·불량수·판정
//                / 구조외관·치수(4행) / 확인내용·특이사항·IQC판정
const openInspSheet=(iv)=>{
  /* ★전 품번 출력 + 자도번마다 1장(2026-08-31 사용자 확정).
       "협력사가 자기들이 모두 검사를 하고 우리한테 입고를 한다" → 검사품 여부와 무관하게
       납품하는 전 품번에 성적서가 붙는다. 종전엔 insp==='검사' 로 걸러 대부분 0장이었다.
     ★단위 = 자도번(단품 P/NO). 레거시 실물(w_pr_outside_030 미리보기)이 자도번마다 한 장씩
       찍어 32쪽이 나온다. 종전엔 도번 1장 + subs[0] 만 써서 나머지 자도번이 빠졌다. */
  const list=[];
  (iv.rows||[]).forEach(x=>{
    if(!x.doban)return;
    const subs=(x.subs&&x.subs.length)?x.subs:[''];      // 자도번 없으면 도번 자체로 1장
    subs.forEach(s=>list.push(Object.assign({}, x, {_sub:String(s||'').split('(')[0]||x.doban})));
  });
  if(!list.length)return;
  const sheet=(x)=>`
    <table class="is">
      <tr><td class="tt" colspan="10">출 하 검 사 성 적 서${iv.svcmark?` <span class="svcm">[${esc(iv.svcmark)}]</span>`:''}</td>
          <th class="gj" rowspan="2">결<br>제</th><th>담당</th><th>Q.A팀장</th></tr>
      <tr><td class="bx"></td><td class="bx"></td></tr>
    </table>
    <table class="is2">
      <!-- ★열 폭(레거시 실물 비율): 라벨칸은 좁게, P/NO 값칸은 품번 19자가 들어가게 넓게 -->
      <colgroup><col style="width:8.5%"><col style="width:11.5%"><col style="width:9.5%"><col style="width:19%">
        <col style="width:9.5%"><col style="width:19%"><col style="width:8.5%"><col></colgroup>
      <tr><th>회사명</th><td>${esc(iv.custnm)}</td><th>Assy P/NO</th><td>${esc(x.doban)}</td>
          <th>단품 P/NO</th><td>${esc(x._sub||x.doban)}</td>
          <th>검사일자</th><td></td></tr>
      <tr><th>검사방법</th><td>보통검사</td><th>Lot Size</th><td>${_fmNf(x.qty)} EA</td>
          <th>측정기명</th><td>VC / HG / 줄자</td><th>검사원</th><td></td></tr>
    </table>
    <table class="is3">
      <!-- ★열 폭(레거시 실물 비율): 검사항목·규격치·검사수준이 넓고 X1~X5 균등, 우측 3칸 중간 -->
      <colgroup><col style="width:10%"><col style="width:12%"><col style="width:11%">
        <col style="width:8.4%"><col style="width:8.4%"><col style="width:8.4%"><col style="width:8.4%"><col style="width:8.4%">
        <col style="width:8.4%"><col style="width:8.4%"><col style="width:8.2%"></colgroup>
      <tr><th>검사항목</th><th>규격치</th><th>검사수준</th><th>X1</th><th>X2</th><th>X3</th><th>X4</th><th>X5</th><th>시료수</th><th>불량수</th><th>판정</th></tr>
      <tr><th class="v">구조외관</th><td>결함없을것</td><td>G-1 2.5</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
      ${/* ★치수 4블록(레거시 실물 대조 2026-08-31): 'S-1 2.5'·'유외치분석'은 구조외관의
           'G-1 2.5'와 **같은 열(검사수준)** 에 온다. 규격치 칸은 비운다(현장 기입).
           종전엔 규격치 칸에 넣어 열이 한 칸씩 밀려 있었다. */
        [1,2,3,4].map(()=>`
      <tr><th class="v" rowspan="2">치수</th><td></td><td>S-1 2.5</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
      <tr><td></td><td>유외치분석</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>`).join('')}
    </table>
    <table class="is4">
      <!-- ★열 폭(레거시 실물 비율): 특이사항이 가장 넓고 IQC판정·검사원은 좁은 기입칸 -->
      <colgroup><col style="width:22%"><col style="width:53%"><col style="width:13%"><col style="width:12%"></colgroup>
      <tr><th>확 인 내 용</th><th>특 이 사 항</th><th>IQC판정</th><th>검사원</th></tr>
      <tr><td class="l sm">·검사항목 지정 유/무<br>·검사항목 검사 유/무<br>·시방항목 확인 유/무<br>·4M변경&nbsp; 확인 유/무</td>
          <td class="l sm">※ 구조·외관검사 점검항목<br>&nbsp;&nbsp; Pipe 내·외부 이물없을 것(플라이트, 면부 확인)<br>
             &nbsp;&nbsp;&nbsp;&nbsp; → 합지 세척관리 확인<br>&nbsp;&nbsp; Pipe 내·외관 찍힘, 눌림, 스크래치 없을 것.</td>
          <td></td><td></td></tr>
    </table>`;
  const PG=[]; for(let i=0;i<list.length;i+=2) PG.push(list.slice(i,i+2));
  const w=window.open('','_blank','width=900,height=1100');
  if(!w)return alert('팝업 차단됨 — 팝업 허용 후 다시 시도하세요.');
  w.document.write(`<html><head><title>출하검사성적서${iv.svcmark?' ['+esc(iv.svcmark)+']':''} ${esc(iv.barcode)}</title><meta charset="utf-8"><style>
    @page{size:A4;margin:8mm}
    .svcm{color:#c00;font-weight:700;font-size:14px;letter-spacing:0}
    body{font-family:'맑은 고딕',Malgun Gothic,sans-serif;margin:0;font-size:11px;color:#000}
    /* ★A4 1장 = 성적서 2장(레거시 실물). 두 장 사이는 절취 점선(레거시 동일).
       높이 실측: 제목34 + 정보표2행38 + 검사표9행171 + 하단표2행90 ≈ 333px/장.
       A4 세로 297mm − 여백16mm = 281mm ≈ 1062px → 2장 666px + 점선여백 = 여유 있음. */
    .sh{page-break-inside:avoid}
    .sh+.sh{margin-top:16px;padding-top:16px;border-top:1px dashed #666}
    table{border-collapse:collapse;width:100%;table-layout:fixed}
    .is td,.is th,.is2 td,.is2 th,.is3 td,.is3 th,.is4 td,.is4 th{border:1px solid #000;padding:2px 4px;height:19px;text-align:center}
    .tt{font-size:17px;font-weight:700;letter-spacing:6px;height:34px;border:none;border-bottom:none}
    .is{border:none}.is td.tt{border:none}
    .gj{width:22px;font-size:10px;line-height:1.2}
    .is th{font-weight:700}
    .bx{height:26px}
    .is2 th{width:64px;font-size:10px}
    .is3 th{font-size:10px}.is3 .v{font-weight:700}
    .is4 th{height:20px}.is4 .l{text-align:left;vertical-align:top;height:70px}
    .sm{font-size:9.5px;line-height:1.45}
    @media print{.np{display:none}}
  </style></head><body>
    <div class="np" style="margin:0 0 10px"><button onclick="window.print()">🖨️ 인쇄</button> <button onclick="window.close()">닫기</button>
      <span style="margin-left:8px;color:#555;font-size:11px">출하검사성적서 · 검사품 ${list.length}건 · ${PG.length}페이지</span></div>
    ${PG.map((pg,pi)=>`<div${pi?' style="page-break-before:always"':''}>
       ${pg.map(x=>`<div class="sh">${sheet(x)}</div>`).join('')}</div>`).join('')}
    </body></html>`);
  w.document.close();
};
// ★출하검사성적서·납품표도 「거래명세표 수정」 재출력이 같은 양식을 쓰도록 전역 공유(2026-08-31)
// ── ★납품처리 1클릭 = 3종 출력 (SVC 분리) ──
//   레거시: 거래명세표 → 납품표 → 출하검사성적서 순으로 발행.
//   ★예외 — SVC(A/S용)는 같은 발행번호라도 **별도 출력물**로 분리하고 제목에 「SVC」를 표시한다.
//     판정 = 백엔드 rows[].svc (계획 LINE_NO='SVC').
const printSet=(iv)=>{
  if(!iv||!iv.rows||!iv.rows.length)return alert('발행 명세가 없습니다.');
  const pick=(f,tag)=>{
    const rs=iv.rows.filter(f); if(!rs.length)return null;
    // 합계는 도번 행만(하위 자재행은 중복 집계 방지)
    const tot=rs.filter(x=>x.doban).reduce((s,x)=>s+(Number(x.qty)||0),0);
    return Object.assign({},iv,{rows:rs,total:tot,count:rs.length,
      title:(iv.title||'')+(tag?' '+tag:''), svcmark:tag||''});
  };
  const grp=[pick(x=>!x.svc,''), pick(x=>!!x.svc,'SVC')].filter(Boolean);
  grp.forEach(g=>{ openDelivInvoice(g); openDelivNote(g); openInspSheet(g); });
};
// ★파일 로드 시점 등록 — 어느 화면에서 부르든 같은 양식이 나오게 한다.
//   (종전엔 SCREEN.deliv420 실행 시에만 등록되어 「거래명세표 수정」 단독 사용 시 누락됐다)
window.openDelivInvoice = openDelivInvoice;
window.openDelivNote    = openDelivNote;
window.openInspSheet    = openInspSheet;
window.printSet         = printSet;


/* 협력사 > 거래명세서 발행 (레거시 w_pr_outside_420) — 레거시 SP_LIVE 라이브 직독 + 510창 완료배분.
   전 컬럼(Line No·자도번LIST·사급·LOT·계획·완료·요청·납품/포장/SERIAL/HEAT 입력·출하/생산실적·세트/입고대기/ASSY재고·일자별).
   완료수량=출하+완제품재고+세트/입고대기 재고배분(도번 공유풀). 발행=nx.deliv_issue 기록(라이브 미기록·하드룰). */
SCREEN.deliv420=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const dcol=s=>(s&&(''+s).length===6)?`${+((''+s).slice(2,4))}/${+((''+s).slice(4,6))}`:s;
  // ★일자컬럼 = 레거시 420 과 동일: 일자+요일(27목), 토/일은 배경색(레거시 29토·30일 주황).
  const wlab=y=>{if(!y||(''+y).length<6)return dcol(y);const s=''+y;const dt=new Date(2000+ +s.slice(0,2),+s.slice(2,4)-1,+s.slice(4,6));return `${s.slice(4,6)}${'일월화수목금토'[dt.getDay()]}`;};
  const wkbg=y=>{if(!y||(''+y).length<6)return '';const s=''+y;const d=new Date(2000+ +s.slice(0,2),+s.slice(2,4)-1,+s.slice(4,6)).getDay();
    return d===0?' style="background:#ffd9c2"':(d===6?' style="background:#ffe9d6"':'');};
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  const ST={"00":"요청","10":"발행","90":"발행완료"}, STC={"00":"#8aa0bd","10":"#2e86de","90":"#27ae60"};
  // gubun: 'order'(주문, 기본) | 'ganpan'(일반간판) — 레거시 라디오. dnp=직납 일수. inymd=입고일자.
  // ★기준일 = 마지막 계획업로드의 일자축 첫날(planBaseIso, 2026-08-28 사용자 확정).
  //   요청수량이 계획 기준이라 당일로 잡으면 재편성 전 기준이 되어 어긋난다.
  //   ※입고일자(inymd)는 실제 입고일이므로 당일 그대로 둔다.
  let F={cust:'',from:planBaseIso(),days:2,dnp:2,inymd:iso(T),gubun:'order',item:'',part:'',sort:'doban',
         deliv:{},pack:{},serial:{},heat:{},chk:{}}, data={dates:[],rows:[],cnt:0,sum:{}}, custs=[], loading=false, busy=false, msg='';
  // ★헤더 더블클릭 정렬 + 마우스 컬럼폭 기억(2026-08-31 사용자 요청).
  //   colw[컬럼인덱스]=px — draw() 로 다시 그려도 사용자가 조절한 폭이 유지된다.
  let st={sortKey:'',sortDir:1,colw:{}};
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
    // ★gigan = 근무일 기준 기간(백엔드가 to_ymd 를 근무일로 재계산·휴무만큼 자동연장). to_ymd 는 하위호환.
    const qs=new URLSearchParams({cust:F.cust,from_ymd:F.from,to_ymd:toOf(),item:F.item,matcode:F.part,gigan:Math.max(1,+F.days||2)});
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
      const pv=await(await fetch(`${API}/api/partner/deliv420/issue`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cust:F.cust,from_ymd:F.from,to_ymd:toOf(),gigan:Number(F.days)||2,
        base_from:data.base_from||'',base_to:data.base_to||'',items,preview:1})})).json();
      if(!pv.ok){alert(pv.msg||'발행 불가');return;}
      if(!confirm(`발행 미리보기\n건수 ${pv.count} · 총 납품수량 ${nf(pv.total_qty)}\n\n확정 발행할까요? (nx.deliv_issue 기록 · 라이브 미기록)`))return;
      const rr=await(await fetch(`${API}/api/partner/deliv420/issue`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cust:F.cust,from_ymd:F.from,to_ymd:toOf(),gigan:Number(F.days)||2,
        base_from:data.base_from||'',base_to:data.base_to||'',items,preview:0})})).json();
      if(!rr.ok){alert(rr.msg||'발행 실패');return;}
      alert(`발행 완료 · 바코드 ${rr.barcode} · ${rr.count}건 · 납품 ${nf(rr.total_qty)}\n(nx.deliv_issue 기록)`);
      // ★발행 후 자동 출력 — 레거시 납품처리 1클릭 = ①거래명세표 ②납품표 ③출하검사성적서
      //   (2026-08-27 사용자 확인). ③은 검사품(insp='1')만 나온다.
      //   ★SVC(A/S용)는 예외로 **분리 출력** + 제목에 SVC 표시(레거시 동일).
      if(rr.barcode){try{const iv=await fetchInvoice(rr.barcode);
          printSet(iv);}
        catch(e){alert('발행은 완료됐으나 인쇄 팝업 실패: '+e.message+'\n[거래명세표]/[스티커] 버튼으로 발행번호 '+rr.barcode+' 재출력 가능합니다.');}}
      await load();
    }catch(e){alert('발행 오류: '+e.message);}finally{busy=false;}
  };
  const cancelIssue=async()=>{const bc=prompt('발행취소할 바코드 번호를 입력하세요');if(!bc)return;
    try{const rr=await(await fetch(`${API}/api/partner/deliv420/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({barcode:bc.trim()})})).json();
      alert(rr.ok?`취소 ${rr.cancelled}건`:(rr.msg||'실패'));await load();}catch(e){alert('오류: '+e.message);}};
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
  // 발행번호(바코드) 입력받아 재출력 — 스티커는 단독, 그 외는 3종 세트(SVC 분리)
  const reprint=async(kind)=>{const bc=prompt('발행번호(바코드)를 입력하세요');if(!bc)return;
    try{const iv=await fetchInvoice(bc.trim());(kind==='sticker'?openSticker:printSet)(iv);}
    catch(e){alert('출력 실패: '+e.message);}};
  // ★자재부품표 인쇄 — 레거시 양식(2026-08-27 사용자 확인).
  //   레거시는 가로 표가 아니라 **카드형 라벨**이다. 한 장에 3매, 매수만큼 반복.
  //     ┌──────── (주)피앤씨인더스트리  부 품 표 ────────┐
  //     │ 모도번(작업처) │                              │
  //     │ 자도번         │                              │
  //     │ 납품일 │ 년 월 일        │ 수량   │           │
  //     │ 업체명 │ 대원산업        │ 검사여부│          │
  //     │        │                 │ 검사확인│    (인)  │
  //   빈양식 = 업체명만 채우고 나머지 공란(수기 기입용).
  //   자재부품표 = 체크한 도번의 값을 채운다.
  const printView=(rows,blank)=>{
    const sel=blank?[]:rows.filter(r=>F.chk[r.assy]);
    if(!blank&&!sel.length)return alert('출력할 도번(체크)을 선택하세요.');
    const custName=(custs.find(w=>w.cc===F.cust)||{}).nm||F.cust;
    // 납품일 26년 08월 27일 (레거시 표기)
    const ymdK=(s)=>{const d=String(s||'').replace(/\D/g,'');
      return d.length>=6?`${d.slice(-6,-4)}년 ${d.slice(-4,-2)}월 ${d.slice(-2)}일`:'';};
    const card=(mo,ja,ymd,qty,insp)=>`
      <table class="pt">
        <tr><td class="ttl" colspan="4">(주)피앤씨인더스트리&nbsp; 부 품 표</td></tr>
        <tr><th class="h2">모도번<br>(작업처)</th><td class="big" colspan="3">${esc(mo||'')}</td></tr>
        <tr><th class="h">자도번</th><td class="big" colspan="3">${esc(ja||'')}</td></tr>
        <tr><th class="h">납품일</th><td class="big">${ymd?esc(ymd):'년&nbsp;&nbsp;&nbsp; 월&nbsp;&nbsp;&nbsp; 일'}</td>
            <th class="h s">수량</th><td class="big">${qty?nf(qty):''}</td></tr>
        <tr><th class="h" rowspan="2">업체명</th><td class="big" rowspan="2">${esc(custName)}</td>
            <th class="h s">검사여부</th><td class="big">${esc(insp||'')}</td></tr>
        <tr><th class="h s">검사확인</th><td class="v r">(인)</td></tr>
      </table>`;
    const ymd=ymdK(F.inymd||'');
    let cards;
    if(blank){
      cards=Array.from({length:9}).map(()=>card('','','',0,'')).join('');
    }else{
      // ★도번 1장이 아니라 **하위 자도번마다 1장**(레거시 동일).
      //   매수는 팝업으로 받는다 — 업체 배포용이라 여러 장 뽑는다.
      const n=parseInt(prompt('출력 매수(자도번 1건당)','1')||'0',10);
      if(!n||n<1)return;
      const out=[];
      sel.forEach(r=>{
        const mo=`${r.assy} (${r.workcenter||r.work_center||''})`;
        const qty=(F.deliv[r.assy]!=null?F.deliv[r.assy]:r.deliv);
        const insp=(r.insp==='1'?'검사':'무검사');
        // 자도번LIST 를 개별 자도번으로 분해(없으면 도번 자체 1장)
        const jl=(r.mat_list||'').split(',').map(s=>s.trim()).filter(Boolean);
        const list=jl.length?jl:[r.assy];
        list.forEach(ja=>{ for(let i=0;i<n;i++) out.push(card(mo,ja,ymd,qty,insp)); });
      });
      cards=out.join('');
    }
    const w=window.open('','_blank','width=900,height=1000'); if(!w)return alert('팝업 차단됨 — 허용 후 다시 시도.');
    w.document.write(`<html><head><title>${blank?'부품표(빈양식)':'부품표'} ${esc(custName)}</title><meta charset="utf-8">
      <style>
        @page{size:A4;margin:10mm}
        body{font-family:'맑은 고딕',Malgun Gothic,sans-serif;margin:0;font-size:13px}
        .pt{border-collapse:collapse;width:100%;table-layout:fixed;margin-bottom:14px;page-break-inside:avoid}
        .pt td,.pt th{border:1.5px solid #000;padding:5px 7px;height:30px}
        .ttl{text-align:center;font-weight:700;font-size:15px;border-bottom:1.5px solid #000;height:26px}
        .h{width:70px;text-align:center;font-weight:700;font-size:12px}
        .h2{width:70px;text-align:center;font-weight:700;font-size:12px;line-height:1.25}
        .s{width:80px}
        .big{text-align:center;font-weight:700;font-size:20px;letter-spacing:6px}
        .v{text-align:left}.r{text-align:right;padding-right:12px}
        @media print{.np{display:none}}
      </style></head><body>
      <div class="np" style="margin:0 0 10px"><button onclick="window.print()">🖨️ 인쇄</button> <button onclick="window.close()">닫기</button>
        <span style="margin-left:8px;color:#555;font-size:12px">${blank?'빈양식':'자재부품표'} · ${esc(custName)} · ${(cards.match(/class="pt"/g)||[]).length}매</span></div>
      ${cards}
      </body></html>`); w.document.close();
  };
  const draw=()=>{
    const dates=data.dates||[];
    let rows=(data.rows||[]).slice();
    // 정렬 토글: 도번별 / 시간별(라인→도번)
    // ★세트제외(공용품)는 **어떤 정렬에서도 맨 위**(2026-08-31 · 레거시 동일).
    const _se=(a,b)=>((a.setexc?0:1)-(b.setexc?0:1));
    // ★헤더 더블클릭 정렬이 있으면 그게 최우선(2026-08-31). 없으면 기존 토글.
    if(st.sortKey){
      const k=st.sortKey, d=st.sortDir||1;
      rows.sort((a,b)=>_se(a,b)||(()=>{const x=a[k],y=b[k],nx=parseFloat(x),ny=parseFloat(y);
        if(x!=null&&y!=null&&x!==''&&y!==''&&!isNaN(nx)&&!isNaN(ny))return (nx-ny)*d;
        return String(x==null?'':x).localeCompare(String(y==null?'':y),'ko')*d;})());
    }
    // ★기본 = **도번별**(2026-08-31 사용자 요청). 종전 'doban' 은 작업처 우선이라
    //   같은 도번이 화면 곳곳에 흩어져 보였다.
    else if(F.sort==='time') rows.sort((a,b)=>_se(a,b)||String(a.line||'').localeCompare(String(b.line||''),'ko')||String(a.assy).localeCompare(String(b.assy),'ko'));
    else if(F.sort==='wc')   rows.sort((a,b)=>_se(a,b)||String(a.workcenter||'').localeCompare(String(b.workcenter||''),'ko')||String(a.assy).localeCompare(String(b.assy),'ko'));
    else rows.sort((a,b)=>_se(a,b)||String(a.assy||'').localeCompare(String(b.assy||''),'ko')||String(a.line||'').localeCompare(String(b.line||''),'ko'));
    const custOpts=custs.map(w=>`<option value="${esc(w.nm||w.cc)}"></option>`).join('');
    const custName=(custs.find(w=>w.cc===F.cust)||{}).nm||'';
    const itS=new Map(); rows.forEach(r=>{if(r.assy&&!itS.has(r.assy))itS.set(r.assy,r.nm||'');});
    const itemOpts=[...itS].slice(0,500).map(([v,n])=>`<option value="${esc(v)}">${esc(n)}</option>`).join('');
    const ptS=new Set(); rows.forEach(r=>(r.mat_list||'').split(/[,\r\n]/).forEach(x=>{const m=x.split('{')[0].split('[')[0].trim();if(m)ptS.add(m);}));
    const partOpts=[...ptS].sort().slice(0,500).map(v=>`<option value="${esc(v)}"></option>`).join('');
    // 고정컬럼 수(빈 결과 colspan용) = 앞 16 + 일자 뒤 5 = 21.
    //   앞 16: SEQ·작업처·도번·LineNo·구분·자도번LIST·사급·LOT·자재·완료·요청·[체크]·납품·포장·검사·상태
    //   뒤  6: 입고대기·세트재고·★단품재고·생산실적·ASSY재고·출하실적
    //          (2026-08-28 일자 뒤로 이동 · 2026-08-31 단품재고 신설)
    const FIX=22;
    const S=data.sum||{};
    const badge=s=>`<span style="padding:1px 5px;border-radius:3px;font-size:10px;background:${STC[s]||'#8aa0bd'};color:#fff">${ST[s]||s}</span>`;
    // 일자셀=완료/계획+색: 생산완료 노랑·출하완료 주황·세트재고(+입고대기) 회색
    // ★회색 교정(2026-08-31): 가공4주간의 50 은 준비재고(키팅)라 녹색이지만, 협력사·거래명세서
    //   계열의 50 은 coopplan._sim510 대로 **세트재고+입고대기 배분**이다(키팅과 무관).
    // ★일자칸은 가운데 정렬(2026-08-31) — 헤더(th.center)는 가운데인데 본문만 .num(우측)이라 어긋났다
    const dcell=(r,d)=>{const pl=Number((r.days&&r.days[d])||0),dn=Number((r.donedays&&r.donedays[d])||0),bg=(r.colors&&r.colors[d])||'';if(!pl&&!dn)return '<td class="num" style="text-align:center;color:#dfe6ef">·</td>';
      return `<td class="num" style="text-align:center;white-space:nowrap${bg?';background:'+bg:''}">${nf(dn)}/${nf(pl)}</td>`;};
    const gPlan={},gDone={};rows.forEach(r=>dates.forEach(d=>{gPlan[d]=(gPlan[d]||0)+Number((r.days&&r.days[d])||0);gDone[d]=(gDone[d]||0)+Number((r.donedays&&r.donedays[d])||0);}));
    const chkn=rows.filter(r=>F.chk[r.assy]).length;
    // ★table-layout:fixed + colgroup — 조회 후에도 컬럼폭 고정(auto 재계산 방지). CW=23개 고정컬럼 + 일자.
    // ★레거시 순서(2026-08-27): SEQ·자도번작업처·작업처·도번·LineNo·구분·품명·자도번LIST·사급
    //   ·LOT·계획·완료·요청 → [체크] → 납품·포장·SERIAL·HEAT·품목정보 → 실적/재고 → 일자
    //   체크박스는 요청수량 바로 뒤(납품수량 앞) = 레거시 위치.
    //   SEQ·자도번작업처·작업처·도번·LineNo·구분·품명·자도번LIST·사급·LOT·자재·완료·요청
    //   ·[체크]·납품·포장·SERIAL·HEAT·품목정보·출하실적·생산실적·세트재고·입고대기·ASSY재고·검사·상태 = 26
    // ★SERIAL-NO·HEAT-NO·품목정보·품명 제거(2026-08-27) → 26 → 22개
    //   SEQ·자도번작업처·작업처·도번·LineNo·구분·자도번LIST·사급·LOT·자재·완료·요청
    //   ·[체크]·납품·포장·출하실적·생산실적·세트재고·입고대기·ASSY재고·검사·상태
    //   ★폭 확대(2026-08-27 사용자 요청): 헤더가 잘려 보이던 칸들
    //     SEQ 28→40 · Line No 44→62 · 납품수량 52→62 · ASSY재고 54→64
    //   ★자도번작업처 삭제(작업처와 같은 값) → 22→21개, 작업처 66→110 확대
    //   ★2026-08-28 재배치: 실적/재고 5종을 **일자 뒤로** 옮기고 검사칸을 넓혔다.
    //     앞(고정 16) = SEQ·작업처·도번·LineNo·구분·자도번LIST·사급·LOT·자재·완료·요청
    //                   ·[체크]·납품·포장·검사(38→52)·상태
    //     뒤(일자 뒤 5) = 입고대기·세트재고·생산실적·ASSY재고·출하실적
    //   ★2026-08-31: 자도번LIST 300→420 확대(여러 자도번이 잘려 툴팁 없이는 못 읽었다).
    const CW=[40,110,96,62,56,420,38,52,52,52,52,  30,  62,52,  52,52], DW=48;
    // 일자 뒤: 입고대기·세트재고·★단품재고(2026-08-31 신설)·생산실적·ASSY재고·출하실적
    const TW=[54,54,66,54,64,54];
    // ★사용자가 마우스로 조절한 폭을 기억한다(2026-08-31). 화면을 다시 그려도 유지.
    //   키 = 컬럼 인덱스. addResizer 가 <col> 을 직접 늘리므로 그 값을 st 에 저장해 복원한다.
    const _cw=(i,def)=>Number(st.colw&&st.colw[i])||def;
    const _allW=[...CW, ...dates.map(()=>DW), ...TW].map((w,i)=>_cw(i,w));
    const totalW=_allW.reduce((a,b)=>a+b,0);
    const colg=`<colgroup>${_allW.map(w=>`<col style="width:${w}px">`).join('')}</colgroup>`;
    // 합계행(2026-08-28 재배치 반영):
    //   계(1)+건수(2~7=6칸) + LOT·자재·완료·요청(8~11) + 체크(12) + 납품·포장(13~14) + 검사·상태(15~16)
    //   + 일자 + 입고대기·세트재고·생산실적·ASSY재고·출하실적(5)
    const _sumBy=f=>rows.reduce((a,r)=>a+(Number(r[f])||0),0);
    const grand=rows.length?`<tr class="grandtot"><td class="center"><b>계</b></td><td colspan="6">${nf(data.cnt)}건</td>`
      +`<td class="num"><b>${nf(S.lot||0)}</b></td><td class="num"><b>${nf(S.plan||0)}</b></td>`
      +`<td class="num" style="color:#1c7c3a"><b>${nf(S.done||0)}</b></td><td class="num"><b>${nf(S.req||0)}</b></td>`
      // ★납품수량 합계 = **체크한 행**의 합. 종전엔 발행분(S.issued)이라 무엇을 고른 건지 몰랐다.
      +`<td class="center">${(()=>{const n=rows.filter(r=>F.chk[r.assy]).length;return n?`<b style="color:#1c7c3a">${n}</b>`:'';})()}</td>`
      +`<td class="num" title="체크한 행의 납품수량 합계"><b style="color:#1c7c3a">${(()=>{
          let s=0;rows.forEach(r=>{if(F.chk[r.assy])s+=Number(F.deliv[r.assy]!=null?F.deliv[r.assy]:r.deliv)||0;});
          return s?nf(s):'';})()}</b></td><td colspan="3"></td>`
      +`${dates.map(d=>`<td class="num" style="text-align:center;white-space:nowrap"><b>${nf(gDone[d]||0)}/${nf(gPlan[d]||0)}</b></td>`).join('')}`
      +`<td class="center"><b>${nf(_sumBy('ireq'))}</b></td><td class="center"><b>${nf(_sumBy('iset_stk'))}</b></td>`
      // ★단품재고 합계 = 세트제외 행만(중복 방지 — 같은 자재가 라인별로 여러 행이라 자재당 1회)
      +`<td class="center" style="color:#c0392b"><b>${(()=>{const seen={};let s=0;
          rows.forEach(r=>{if(r.setexc&&!seen[r.assy]){seen[r.assy]=1;s+=Number(r.input_mat)||0;}});
          return s?nf(s):'';})()}</b></td>`
      +`<td class="center" style="color:#8e44ad"><b>${nf(_sumBy('prod'))}</b></td>`
      +`<td class="center"><b>${nf(_sumBy('assy_stock'))}</b></td>`
      +`<td class="center" style="color:#2e86de"><b>${nf(_sumBy('sale'))}</b></td></tr>`:'';
    // ★스크롤 1개(CLAUDE.md §3) — 화면 루트를 flex 컬럼으로, 표 영역만 스크롤.
    //   제목·안내·버튼·조건 2줄은 flex:0 0 auto 로 고정한다.
    c.style.cssText='display:flex;flex-direction:column;height:100%;min-height:0;overflow:hidden';
    c.innerHTML=`
     <div class="page-title" style="flex:0 0 auto">🧾 거래명세서 발행 <span style="font-size:12px;color:var(--muted);font-weight:400">레거시 w_pr_outside_420 · 웹편성(nx) 직독 · 발행=nx</span></div>
     <div class="page-sub" style="flex:0 0 auto;margin-bottom:6px">완료된 도번 <b>체크 → 납품/포장 입력 → [납품처리]</b>(발행은 <b>nx.deliv_issue</b>에만 기록). 완료수량=출하+완제품재고+세트/입고대기 재고배분(도번 공유풀). <b>요청수량=계획−완료</b>(발행분은 세트입고대기로 완료에 이미 포함).
       <span style="margin-left:6px;font-size:11px">일자셀=<b>완료/계획</b> · <span style="background:#ffff00;padding:0 5px;border-radius:3px">생산완료</span> <span style="background:#fac090;padding:0 5px;border-radius:3px">출하완료</span> <span style="background:#c0c0c0;padding:0 5px;border-radius:3px" title="세트재고 + 입고대기 물량이 배분된 칸 (협력사는 키팅과 무관)">세트재고</span></span>${data.note?'<br>ℹ '+esc(data.note):''}</div>
     <!-- ★레거시 w_pr_outside_420 배치(2026-08-27): 출력버튼줄 / 조건 2줄.
          기간=납품일자 기준 조회일수, 직납=직납품 별도 일수(레거시 동일 개념). -->
     <div class="toolbar">
       <button class="btn" id="d4-prt">🖨️ 자재부품표</button>
       <button class="btn" id="d4-blank">빈양식</button>
       <button class="btn" id="d4-issue" style="background:#2e86de;color:#fff" ${busy?'disabled':''}>📦 납품처리 (${chkn})</button>
       <button class="btn" id="d4-sticker" title="발행번호로 스티커(바코드) 재출력">🏷️ 스티커</button>
       <button class="btn" id="d4-invoice" title="발행번호로 거래명세표 재출력">🧾 거래명세표</button>
       <button class="btn" id="d4-cancel">발행취소</button>
       <div class="spacer"></div>
       <span class="rowcount">${nf(data.cnt||0)}건 · 완료 <b>${nf(S.done||0)}</b>/계획 ${nf(S.plan||0)} · 발행 ${nf(S.issued||0)}</span>
       ${loading?'<span style="color:var(--muted)">조회중…</span>':''}
     </div>
     <!-- ★조건문 2줄 배치(2026-08-27 — 레거시 거래명세서발행 화면 동일).
            1줄 = 기준일자 · 구분 · 기간 · 직납 · 입고일자
            2줄 = 도번 · 자도번 · 자도번작업처[코드🔍이름] · 정렬 + 조회
            라벨은 레거시처럼 회색칸(.tl)으로 폭을 맞춘다. -->
     <style>
      .d4-r{display:flex;align-items:center;gap:6px;margin-top:2px;flex-wrap:nowrap}
      .d4-r .tl{background:#eaf0f8;border:1px solid #cdd9e8;border-radius:4px;
        padding:3px 8px;font-size:12px;color:#33507d;font-weight:600;text-align:center;
        white-space:nowrap;min-width:66px}
      /* ★표 머리글 고정(2026-08-31 · CLAUDE.md §3) — 세로 스크롤해도 항상 보이게.
         종전엔 sticky 규칙이 없어 헤더가 같이 밀려 올라갔다.
         배경색 필수(투명하면 아래 행이 비쳐 보인다). */
      .d4-grid thead th{position:sticky;top:0;z-index:5;background:#eef2f8;
        box-shadow:inset 0 -1px 0 var(--line-2,#c9d3e0)}
      /* 합계행은 하단 고정 */
      .d4-grid tr.grandtot td{position:sticky;bottom:0;z-index:4;background:#eaf1fb;
        box-shadow:inset 0 1px 0 #cdd9ef}
     </style>
     <div class="toolbar d4-r">
       <label class="tl">기준일자</label>${legacyDateHTML('d4-base',F.from)}
       <label class="tl">구분</label>
       <span style="display:inline-flex;gap:10px;padding:0 4px">
         <label style="font-size:12px;display:inline-flex;align-items:center;gap:3px;cursor:pointer"><input type="radio" name="d4gb" id="d4-gb-g" value="ganpan" ${F.gubun==='ganpan'?'checked':''}>일반간판</label>
         <label style="font-size:12px;display:inline-flex;align-items:center;gap:3px;cursor:pointer"><input type="radio" name="d4gb" id="d4-gb-o" value="order" ${F.gubun!=='ganpan'?'checked':''}>주문</label></span>
       <label class="tl">기간</label><input class="inp" id="d4-days" value="${esc(F.days)}" style="width:48px;min-width:48px;text-align:center" title="납품일자 기준 조회일수"><span style="font-size:12px;color:#5a6b80">일</span>
       <label class="tl">직납</label><input class="inp" id="d4-dnp" value="${esc(F.dnp)}" style="width:48px;min-width:48px;text-align:center" title="직납품 조회일수(레거시 '직납')"><span style="font-size:12px;color:#5a6b80">일</span>
       <label class="tl" style="margin-left:10px">입고일자</label>${legacyDateHTML('d4-in',F.inymd)}
       <div class="spacer"></div>
     </div>
     <div class="toolbar d4-r">
       <label class="tl">도번</label><input class="inp" id="d4-item" list="d4l-item" value="${esc(F.item)}" style="width:130px;min-width:130px" placeholder="도번(ASSY)/품명" autocomplete="off"><datalist id="d4l-item">${itemOpts}</datalist>
       <label class="tl">자도번</label><input class="inp" id="d4-part" list="d4l-part" value="${esc(F.part)}" style="width:130px;min-width:130px" placeholder="자도번" autocomplete="off"><datalist id="d4l-part">${partOpts}</datalist>
       <!-- ★자도번작업처 = 레거시처럼 [코드][🔍][업체명] — 필수라 강조 -->
       <label class="tl" style="color:#1c47a0;background:#dceaff;border-color:#9dc0ea;min-width:88px">자도번작업처</label>
       <input class="inp" id="d4-custcode" value="${esc(F.cust)}" placeholder="코드" autocomplete="off" title="자도번작업처 코드 — 직접 입력 후 Enter" style="width:74px;min-width:74px;text-align:center;background:${F.cust?'#eaf3ff':'#fff7e6'};border:2px solid ${F.cust?'#7fa8e8':'#f0b429'};font-weight:700">
       <button class="btn" id="d4-custfind" title="업체 찾기" style="padding:0 7px;min-width:28px">🔍</button>
       <input class="inp" id="d4-cust" list="d4l-cust" value="${esc(custName)}" placeholder="거래처명" autocomplete="off" title="필수 — 협력사를 선택해야 조회됩니다" style="width:150px;min-width:150px;background:${F.cust?'#eaf3ff':'#fff7e6'};border:2px solid ${F.cust?'#7fa8e8':'#f0b429'};font-weight:600"><datalist id="d4l-cust">${custOpts}</datalist>
       <button class="btn" id="d4-search" style="margin-left:4px">🔍 조회</button>
       <!-- ★정렬 선택(2026-08-31) — 기본 도번별. 헤더 더블클릭 정렬이 있으면 그쪽이 우선. -->
       <label class="tl" style="margin-left:8px">정렬</label>
       <select class="inp" id="d4-sort" style="width:96px;min-width:96px" title="헤더를 더블클릭해도 그 컬럼으로 정렬됩니다">
         <option value="doban" ${F.sort==='doban'?'selected':''}>도번별</option>
         <option value="wc" ${F.sort==='wc'?'selected':''}>작업처별</option>
         <option value="time" ${F.sort==='time'?'selected':''}>라인별</option>
       </select>
       ${st.sortKey?`<button class="btn ghost" id="d4-sortclr" title="헤더 정렬 해제" style="padding:0 8px">정렬해제</button>`:''}
       <div class="spacer"></div>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <!-- ★flex:0 1 auto + max-height:100% (4787a13 확정) — 고정 max-height 는 표 아래 여백을 남긴다. -->
     <div class="grid-wrap" style="flex:0 1 auto;min-height:0;max-height:100%;overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl d4-grid" style="font-size:11px;white-space:nowrap;table-layout:fixed;width:${totalW}px">${colg}<thead><tr>
       <!-- ★품명·자도번작업처 제거 · 헤더 전부 가운데 정렬(2026-08-27 사용자 요청)
            자도번작업처와 작업처가 같은 값이라 작업처만 남기고 폭을 넓혔다. -->
       <!-- ★헤더 더블클릭 정렬(2026-08-31 · CLAUDE.md §3 공통규칙). data-key = 행 필드명 -->
       <th class="center">SEQ</th><th class="center" data-key="workcenter">작업처</th><th class="center" data-key="assy">도번</th><th class="center" data-key="line">Line No</th><th class="center" data-key="gubun">구분</th><th class="center" data-key="mat_list">자도번LIST</th><th class="center" data-key="sagub_list">사급</th>
       <th class="center" data-key="lot">LOT수량</th><th class="center" data-key="plan">자재수량</th><th class="center" data-key="done">완료수량</th><th class="center" data-key="req">요청수량</th>
       <th class="center"><input type="checkbox" id="d4-all"></th>
       <!-- ★SERIAL-NO·HEAT-NO·품목정보 제거(2026-08-27 사용자 요청) -->
       <th class="center">납품수량</th><th class="center">포장수량</th>
       <th class="center" data-key="insp">검사</th><th class="center" data-key="status">상태</th>
       ${dates.map(d=>`<th class="center"${wkbg(d)}>${esc(wlab(d))}</th>`).join('')}
       <!-- ★실적/재고 5종은 **일자 뒤로** 이동(2026-08-28 사용자요청).
            순서 = 입고대기 · 세트재고 · 생산실적 · ASSY재고 · 출하실적 -->
       <th class="center" data-key="ireq">입고대기</th><th class="center" data-key="iset_stk">세트재고</th>
       <!-- ★단품재고(2026-08-31 신설) — 세트제외(공용품) 행만 값이 있다.
            세트별 재고관리를 하지 않는 공용품이라 자재+생산+영업 창고 합으로 본다. -->
       <th class="center" data-key="input_mat" title="세트제외(공용품) 품목의 자재+생산+영업 창고 재고합계">단품재고</th>
       <th class="center" data-key="prod">생산실적</th><th class="center" data-key="assy_stock">ASSY재고</th><th class="center" data-key="sale">출하실적</th>
       </tr></thead>
      <tbody>${loading?spinRow(FIX+dates.length):(rows.length?(rows.map((r,ri)=>{const ed=(r.status!=='90'&&Number(r.req)>0);
        // ★납품수량은 **체크했을 때만** 채운다(2026-08-28 사용자요청).
        //   종전엔 조회 즉시 r.deliv(=요청수량 기본값)가 전 행에 찍혀 있어
        //   무엇을 고른 건지 구분이 안 됐다. 체크 → 요청수량 자동채움, 해제 → 비움.
        //   사용자가 직접 고친 값(F.deliv)은 그대로 유지한다.
        const ckd=!!F.chk[r.assy];
        const dv=ckd?(F.deliv[r.assy]!=null?F.deliv[r.assy]:r.deliv):'';
        const pk=ckd?(F.pack[r.assy]!=null?F.pack[r.assy]:r.pack):'';
        // ★세트제외 구간(맨 위)과 그 아래를 굵은 선으로 구분(2026-08-31)
        const _last=(r.setexc&&rows[ri+1]&&!rows[ri+1].setexc);
        return `<tr${_last?' style="border-bottom:2px solid #c0392b"':''}>
        <td class="num" style="color:#8aa0bd">${ri+1}</td>
        <td class="center"><b>${esc(r.workcenter||r.work_center||r.in_cust||'')}</b></td>
        <td class="center"><b>${esc(r.assy)}</b></td><td class="center">${esc(r.line||'')}</td>
        <!-- ★세트제외(공용품)는 레거시처럼 빨간 글씨로 구분(2026-08-31) -->
        <td class="center"${r.setexc?' style="color:#c0392b;font-weight:700"':''} ${r.setexc?'title="공용품 — 세트별 재고관리를 하지 않고 단품재고로 본다"':''}>${esc(r.gubun||'')}</td>
        <td><div style="width:100%;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.mat_list||'')}">${esc(r.mat_list||'')}</div></td>
        <td class="center">${r.sagub_list?'<span class="bdg sagub" style="font-size:10px" title="'+esc(r.sagub_list)+'">사급</span>':''}</td>
        <td class="num">${nf(r.lot)}</td><td class="num">${nf(r.plan)}</td>
        <td class="num" style="color:#1c7c3a"><b>${nf(r.done)}</b></td>
        <td class="num"><b>${nf(r.req)}</b></td>
        <!-- ★이미 체크된 행은 disabled 를 걸지 않는다(2026-08-28) — 걸면 해제가 안 된다.
             ed(=상태<>90 · 요청>0)는 '새로 체크할 수 있는가' 조건일 뿐이다. -->
        <td class="center"><input type="checkbox" class="d4-ck" data-k="${esc(r.assy)}" ${ckd?'checked':''} ${(ed||ckd)?'':'disabled'}></td>
        <!-- 체크된 행이면 무조건 입력 가능(ed 와 무관) -->
        <td class="num" style="background:${ckd?'#eafaea':'#f5f7fa'};padding:1px 2px"><input class="inp d4-dv" data-k="${esc(r.assy)}" value="${dv}" ${ckd?'':'disabled'} title="${ckd?'납품수량':'완성분을 체크하면 입력됩니다'}" style="width:40px;min-width:0;height:24px;text-align:right;background:${ckd?'#eafaea':'#f5f7fa'};padding:1px 3px;font-size:11px"></td>
        <td class="num" style="background:${ckd?'#eafaea':'#f5f7fa'};padding:1px 2px"><input class="inp d4-pk" data-k="${esc(r.assy)}" value="${pk}" ${ckd?'':'disabled'} style="width:40px;min-width:0;height:24px;text-align:right;background:${ckd?'#eafaea':'#f5f7fa'};padding:1px 3px;font-size:11px"></td>
        <td class="center">${r.insp==='1'?'<span class="bdg sagub">검사</span>':''}</td>
        <!-- ★상태 = **요청수량이 있는 행만** 표시(2026-08-28). 요청 0 인데 '요청' 뱃지가
             전 행에 붙어 있어 무엇이 실제 대상인지 구분이 안 됐다. -->
        <td class="center">${Number(r.req)>0?badge(r.status):''}</td>
        ${dates.map(d=>dcell(r,d)).join('')}
        <!-- ★실적/재고 5종 = 일자 뒤 · 입고대기·세트재고·생산실적·ASSY재고·출하실적 · 전부 가운데정렬 -->
        <td class="center">${nf(r.ireq)}</td>
        <td class="center">${nf(r.iset_stk)}</td>
        <!-- ★단품재고 — 세트제외(공용품) 행만 값이 있다(2026-08-31) -->
        <td class="center" style="color:#c0392b;font-weight:${r.setexc?'700':'400'}">${r.setexc?nf(r.input_mat):''}</td>
        <td class="center" style="color:#8e44ad">${nf(r.prod)}</td>
        <td class="center">${nf(r.assy_stock)}</td>
        <td class="center" style="color:#2e86de">${nf(r.sale)}</td>
        </tr>`;}).join('')+grand):`<tr><td colspan="${FIX+dates.length}" class="empty">협력사·기준일자 선택 후 조회하세요.</td></tr>`)}</tbody></table></div>`;
    const g=id=>c.querySelector(id);
    // ★자도번작업처 = [코드][🔍][업체명] 연동(2026-08-27 레거시 동일).
    const sync=()=>{const cn=g('#d4-cust').value.trim(), ccd=(g('#d4-custcode')||{value:''}).value.trim();
      const byNm=custs.find(w=>(w.nm||w.cc)===cn);
      if(byNm) F.cust=byNm.cc; else if(ccd) F.cust=ccd; else if(!cn) F.cust='';
      F.days=g('#d4-days').value||2;F.item=g('#d4-item').value.trim();F.part=g('#d4-part').value.trim();
      const dn=g('#d4-dnp');if(dn)F.dnp=dn.value||2;
      const gg=g('#d4-gb-g');F.gubun=(gg&&gg.checked)?'ganpan':'order';
      const so=g('#d4-sort');if(so)F.sort=so.value;};
    bindLegacyDate(c,'d4-base',()=>F.from,(v)=>{F.from=v;});
    bindLegacyDate(c,'d4-in',()=>F.inymd,(v)=>{F.inymd=v;});
    g('#d4-search').onclick=()=>{sync();load();};
    ['#d4-gb-g','#d4-gb-o'].forEach(id=>{const el=g(id);if(el)el.onchange=()=>{sync();load();};});
    // 정렬 드롭다운을 바꾸면 헤더 정렬은 해제한다(둘이 겹치면 헷갈린다)
    const so=g('#d4-sort');if(so)so.onchange=()=>{st.sortKey='';sync();draw();};
    const sc=g('#d4-sortclr');if(sc)sc.onclick=()=>{st.sortKey='';draw();};
    ['#d4-cust','#d4-custcode','#d4-item','#d4-part','#d4-days','#d4-dnp'].forEach(id=>{const el=g(id);if(el)el.onkeyup=e=>{if(e.key==='Enter'){sync();load();}};});
    // 코드 ↔ 업체명 양방향 채움
    const cCode=g('#d4-custcode');
    if(cCode)cCode.onchange=()=>{const w=custs.find(x=>x.cc===cCode.value.trim());if(w)g('#d4-cust').value=w.nm||w.cc;};
    const cName=g('#d4-cust');
    if(cName)cName.onchange=()=>{const w=custs.find(x=>(x.nm||x.cc)===cName.value.trim());if(w&&cCode)cCode.value=w.cc;};
    const cFind=g('#d4-custfind');
    if(cFind)cFind.onclick=()=>{if(cName){cName.focus();cName.select();}};
    g('#d4-issue').onclick=()=>issue(rows);
    g('#d4-cancel').onclick=cancelIssue;
    g('#d4-prt').onclick=()=>printView(rows,false);
    g('#d4-blank').onclick=()=>printView(rows,true);
    g('#d4-invoice').onclick=()=>reprint('invoice');
    // ★스티커설정·프린터설정 버튼은 툴바에서 뺐다(레거시 대조·2026-08-27). 기능은 유지 —
    //   스티커 버튼 우클릭 = 라벨규격/매수 설정, Shift+클릭 = 프린터 설정.
    const stk=g('#d4-sticker');
    if(stk){ stk.onclick=e=>{ if(e.shiftKey)openPrinterSetup(); else reprint('sticker'); };
             stk.oncontextmenu=e=>{ e.preventDefault(); openLabelSetup(); };
             stk.title='발행번호로 스티커 재출력 · 우클릭=스티커설정 · Shift+클릭=프린터설정'; }
    // ★전체선택 — 켤 땐 대상행(요청>0)만, 끌 땐 **체크된 것 전부** 해제한다.
    //   (해제 때도 ed 조건을 걸면 요청이 0으로 바뀐 행이 체크된 채 남는다)
    const all=g('#d4-all');
    if(all){
      const _sel=rows.filter(r=>F.chk[r.assy]).length;
      const _tgt=rows.filter(r=>r.status!=='90'&&Number(r.req)>0).length;
      all.checked=_tgt>0&&_sel>=_tgt;                 // 전부 골랐으면 체크 표시
      all.indeterminate=_sel>0&&_sel<_tgt;            // 일부만 골랐으면 중간 표시
      all.onclick=e=>{
        const on=e.target.checked;
        rows.forEach(r=>{
          if(on){ if(r.status!=='90'&&Number(r.req)>0)F.chk[r.assy]=true; }
          else  { delete F.chk[r.assy];delete F.deliv[r.assy];delete F.pack[r.assy]; }
        });
        // ★스크롤 보존 — draw()는 전체 재렌더라 그냥 부르면 맨 위로 튄다(2026-08-28).
        const gw=c.querySelector('.grid-wrap');
        const sy=gw?gw.scrollTop:0, sx=gw?gw.scrollLeft:0;
        draw();
        const gw2=c.querySelector('.grid-wrap');
        if(gw2){gw2.scrollTop=sy;gw2.scrollLeft=sx;}};
    }
    // ★체크 → 그 행의 납품/포장수량 칸을 열고 기본값(요청수량)을 채운다. 해제 → 비우고 잠근다.
    //   값이 체크 상태에 따라 달라지므로 그 행만 다시 그린다(전체 draw 는 스크롤이 튄다).
    c.querySelectorAll('.d4-ck').forEach(x=>x.onchange=e=>{
      const k=e.target.dataset.k, on=e.target.checked;
      F.chk[k]=on;
      if(!on){delete F.deliv[k];delete F.pack[k];}      // 해제 시 입력값도 초기화
      const tr=e.target.closest('tr');
      const r=rows.find(v=>v.assy===k);
      if(tr&&r){
        const dvEl=tr.querySelector('.d4-dv'), pkEl=tr.querySelector('.d4-pk');
        const bg=on?'#eafaea':'#f5f7fa';
        if(dvEl){dvEl.value=on?(F.deliv[k]!=null?F.deliv[k]:r.deliv):'';dvEl.disabled=!on;
                 dvEl.style.background=bg;dvEl.parentElement.style.background=bg;
                 dvEl.title=on?'납품수량':'완성분을 체크하면 입력됩니다';}
        if(pkEl){pkEl.value=on?(F.pack[k]!=null?F.pack[k]:r.pack):'';pkEl.disabled=!on;
                 pkEl.style.background=bg;pkEl.parentElement.style.background=bg;}
        // ★preventScroll — 그냥 focus() 하면 브라우저가 그 칸을 보이게 하려고 스크롤을 옮긴다.
        if(on&&dvEl){try{dvEl.focus({preventScroll:true});}catch(_){dvEl.focus();}dvEl.select();}
      }
      const b=g('#d4-issue');if(b)b.textContent=`📦 납품처리 (${rows.filter(r=>F.chk[r.assy]).length})`;
      // 헤더 전체선택 표시 갱신(전부/일부/없음)
      const ah=g('#d4-all');
      if(ah){const s=rows.filter(v=>F.chk[v.assy]).length,
                   t=rows.filter(v=>v.status!=='90'&&Number(v.req)>0).length;
             ah.checked=t>0&&s>=t; ah.indeterminate=s>0&&s<t;}});
    c.querySelectorAll('.d4-dv').forEach(x=>x.oninput=e=>{F.deliv[e.target.dataset.k]=e.target.value;});
    c.querySelectorAll('.d4-pk').forEach(x=>x.oninput=e=>{F.pack[e.target.dataset.k]=e.target.value;});
    c.querySelectorAll('.d4-sn').forEach(x=>x.oninput=e=>{F.serial[e.target.dataset.k]=e.target.value;});
    c.querySelectorAll('.d4-hn').forEach(x=>x.oninput=e=>{F.heat[e.target.dataset.k]=e.target.value;});
    // ★컬럼 너비 드래그 + 헤더 더블클릭 정렬(2026-08-31 사용자 요청).
    //   이 표는 table-layout:fixed + <colgroup> 이라 공용 addResizer(th.style.width)가 먹지 않는다
    //   — <col> 의 width 가 우선이므로 col 을 직접 조절하고 그 값을 st.colw 에 기억한다.
    (()=>{
      const tb=c.querySelector('.grid-wrap table.d4-grid');if(!tb)return;
      const cols=tb.querySelectorAll('colgroup col');
      tb.querySelectorAll('thead th').forEach((th,i)=>{
        const col=cols[i];if(!col)return;
        // ⚠position:relative 를 주면 CSS 의 sticky(헤더 고정)가 덮어써진다.
        //   sticky 요소도 자식 absolute 의 기준이 되므로 그대로 둔다(2026-08-31).
        // 정렬(더블클릭) — data-key 있는 헤더만
        const k=th.dataset.key;
        if(k){
          th.style.cursor='pointer';
          th.title='더블클릭 정렬 · 우측 경계 드래그로 너비조절';
          if(st.sortKey===k)th.insertAdjacentHTML('beforeend',
            `<span style="font-size:9px;margin-left:2px">${st.sortDir===1?'▲':'▼'}</span>`);
          th.ondblclick=e=>{if(e.target.classList.contains('d4-rz'))return;
            st.sortDir=(st.sortKey===k&&st.sortDir===1)?-1:1;st.sortKey=k;draw();};
        }
        // 너비 드래그 핸들
        const rz=document.createElement('div');
        rz.className='d4-rz';
        rz.style.cssText='position:absolute;top:0;right:0;width:6px;height:100%;'
          +'cursor:col-resize;user-select:none;z-index:3';
        rz.onmousedown=e=>{e.preventDefault();e.stopPropagation();
          const sx=e.pageX, sw=col.offsetWidth||parseInt(col.style.width)||60;
          const mv=ev=>{const w=Math.max(24,sw+ev.pageX-sx);
            col.style.width=w+'px';st.colw[i]=w;};
          const up=()=>{document.removeEventListener('mousemove',mv);
            document.removeEventListener('mouseup',up);
            // 표 전체폭도 다시 계산(가로스크롤 유지)
            let t=0;cols.forEach(x=>t+=parseInt(x.style.width)||0);
            if(t)tb.style.width=t+'px';};
          document.addEventListener('mousemove',mv);document.addEventListener('mouseup',up);};
        rz.ondblclick=e=>{e.stopPropagation();delete st.colw[i];draw();};   // 폭 초기화
        th.appendChild(rz);
      });
    })();
  };
  // ★계획 기준일(마지막 업로드 일자축 첫날) 반영 후 그린다 — 2026-08-28
  planBase().then(b=>{if(b&&b.iso)F.from=b.iso;}).catch(()=>{})
    .then(()=>loadCusts()).then(draw);
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
  /* ==== 수동입고(장부) 팝업 — 레거시 w_pu_stock_146 '자재세트일괄입고' ====
     거래처 + 도번별 행입력 → 저장 시 ①세트재고 ②자도번 파생 ③④사급 소진.
     ★모달은 document.body 에 렌더(§3 — .content 안에 넣으면 잘림). */
  const openManual=()=>{
    const ov=document.createElement('div');
    ov.style.cssText='position:fixed;inset:0;background:rgba(15,25,40,.45);z-index:1200;'
                    +'display:flex;align-items:center;justify-content:center';
    document.body.appendChild(ov);
    const close=()=>ov.remove();

    // scope: 'set'=세트재고만(하위 무영향) · 'all'=하위재고반영(종전 동작)
    let mst={ymd:iso(new Date()),cust:'',custnm:'',rows:[],busy:false,nextno:'',scope:'all'};
    for(let i=0;i<30;i++) mst.rows.push({item_code:'',itemnm:'',stock:null,qty:'',remark:'',direct:''});

    let custMap={};
    const paint=()=>{
      ov.innerHTML=`
       <div style="background:#fff;border-radius:10px;width:min(1080px,95vw);max-height:92vh;
                   display:flex;flex-direction:column;box-shadow:0 12px 40px rgba(0,0,0,.3)">
        <div style="flex:0 0 auto;padding:12px 16px;background:#2e86de;color:#fff;border-radius:10px 10px 0 0;
                    display:flex;justify-content:space-between;align-items:center">
          <b>📝 자재세트일괄입고 (수동입고)</b>
          <span style="font-size:12px;font-weight:400">레거시 w_pu_stock_146 · 수동입고NO ${esc(String(mst.nextno||'-'))}</span>
        </div>
        <div style="flex:0 0 auto;padding:10px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;
                    border-bottom:1px solid #dfe6ee">
          <label>입고일자 <input type="date" class="inp" id="mn-ymd" value="${esc(mst.ymd)}"
                 style="width:150px;min-width:0"></label>
          <label>거래처<span style="color:#c0392b">*</span>
            <input class="inp" id="mn-cust" list="mn-custs" value="${esc(mst.custnm)}"
                   placeholder="거래처명 일부 입력(예: 대원)"
                   style="width:220px;min-width:0;${mst.cust?'':'border-color:#e08b8b;background:#fff7f7'}"></label>
          <datalist id="mn-custs"></datalist>
          <span id="mn-cc" style="font-size:12px;${mst.cust?'color:#1f7a3d':'color:#c0392b'}">
            ${mst.cust?('✔ '+esc(mst.custnm)+' ('+esc(mst.cust)+')'):'거래처를 먼저 선택하세요'}</span>
          <!-- ★재고 반영 범위 (2026-09-01) — 둘 중 하나만 선택(같은 name 그룹).
               세트재고만 : 세트원장만 기록, 하위 자도번 재고는 건드리지 않는다
               하위재고반영: 세트 + 자도번 파생까지(종전 동작) -->
          <span style="margin-left:auto;display:inline-flex;gap:14px;align-items:center;
                       border:1px solid #dfe6ee;border-radius:6px;padding:5px 12px">
            <label style="cursor:pointer;white-space:nowrap">
              <input type="radio" name="mn-scope" value="set"
                     ${mst.scope==='set'?'checked':''}> 세트재고만 반영</label>
            <label style="cursor:pointer;white-space:nowrap">
              <input type="radio" name="mn-scope" value="all"
                     ${mst.scope==='all'?'checked':''}> 하위재고 반영</label>
          </span>
        </div>
        <div style="flex:1;min-height:0;overflow:auto;padding:0 16px">
          <table class="tbl" style="width:100%;white-space:nowrap"><thead><tr>
            <th style="width:44px">SEQ</th><th style="width:190px">도번</th><th>품명</th>
            <th style="width:110px" class="num">재고수량</th><th style="width:110px" class="num">입고수량</th>
            <th style="width:200px">비고</th><th style="width:70px" class="center">직납품</th></tr></thead>
          <tbody>${mst.rows.map((r,i)=>`<tr>
            <td class="center">${i+1}</td>
            <td><input class="inp mn-it" data-i="${i}" value="${esc(r.item_code)}"
                       placeholder="도번" style="width:100%;min-width:0"></td>
            <td class="cap" style="max-width:240px;overflow:hidden;text-overflow:ellipsis"
                title="${esc(r.itemnm||'')}">${esc(r.itemnm||'')}</td>
            <td class="num" style="color:${(+r.stock<0)?'#c0392b':'#586174'}">${r.stock==null?'':won(r.stock)}</td>
            <td><input class="inp mn-qty" data-i="${i}" value="${esc(String(r.qty))}" inputmode="numeric"
                       style="width:100%;min-width:0;text-align:right"></td>
            <td><input class="inp mn-rm" data-i="${i}" value="${esc(r.remark)}"
                       style="width:100%;min-width:0"></td>
            <td class="center" style="color:#c67d00;font-weight:600">${r.direct?'직납품':''}</td>
            </tr>`).join('')}</tbody></table>
        </div>
        <div style="flex:0 0 auto;padding:10px 16px;border-top:1px solid #dfe6ee;display:flex;gap:8px;align-items:center">
          <button class="btn" id="mn-add">＋ 행추가</button>
          <button class="btn" id="mn-del">－ 빈행삭제</button>
          <button class="btn" id="mn-xl" style="background:#1e7e34;color:#fff">📋 엑셀 붙여넣기</button>
          <span id="mn-msg" style="color:#5a6b82;font-size:12px;margin-left:8px"></span>
          <span style="margin-left:auto"></span>
          <button class="btn" id="mn-close">닫기</button>
          <button class="btn" id="mn-save" style="background:#27ae60;color:#fff"
                  ${mst.busy?'disabled':''}>${mst.busy?'저장중…':'💾 저장'}</button>
        </div>
       </div>`;

      const dl=ov.querySelector('#mn-custs');
      dl.innerHTML=Object.keys(custMap).map(n=>`<option value="${esc(n)}">${esc(custMap[n])}</option>`).join('');

      const q=id=>ov.querySelector(id);
      const msg=t=>{const m=q('#mn-msg');if(m)m.textContent=t||'';};
      q('#mn-ymd').onchange=e=>{mst.ymd=e.target.value;};
      // ★재고 반영 범위 — 라디오는 같은 name 이라 둘 중 하나만 선택된다.
      //   재렌더 없이 상태만 바꾼다(입력 중인 그리드가 초기화되지 않게).
      ov.querySelectorAll('input[name=mn-scope]').forEach(rb=>{
        rb.onchange=()=>{if(rb.checked)mst.scope=rb.value;};});
      /* 거래처 — 부분검색. '대원' → '대원산업' 자동확정(후보 1건이면) */
      const pickCust=v=>{
        const nm=String(v||'').trim();
        if(!nm){mst.custnm='';mst.cust='';return '';}
        if(custMap[nm]){mst.custnm=nm;mst.cust=custMap[nm];return '';}
        const keys=Object.keys(custMap);
        // 코드로 직접 입력한 경우
        const byCode=keys.filter(k=>custMap[k]===nm);
        if(byCode.length===1){mst.custnm=byCode[0];mst.cust=nm;return '';}
        const hit=keys.filter(k=>k.indexOf(nm)>=0);
        if(hit.length===1){mst.custnm=hit[0];mst.cust=custMap[hit[0]];return '';}
        if(hit.length>1){
          const exact=hit.filter(k=>k.startsWith(nm));
          if(exact.length===1){mst.custnm=exact[0];mst.cust=custMap[exact[0]];return '';}
          mst.custnm=nm;mst.cust='';
          return '후보 '+hit.length+'건 — '+hit.slice(0,5).join(' / ')+(hit.length>5?' …':'');
        }
        mst.custnm=nm;mst.cust='';
        return '일치하는 거래처가 없습니다.';
      };
      const applyCust=e=>{
        const warn=pickCust(e.target.value);
        mst.rows.forEach(r=>{r.stock=null;});
        paint();
        if(warn) msg(warn);
        if(mst.cust) mst.rows.forEach((r,i)=>{if(r.item_code)fetchStock(i);});
      };
      q('#mn-cust').onchange=applyCust;
      q('#mn-cust').onblur=applyCust;
      ov.querySelectorAll('.mn-it').forEach(el=>{
        el.onchange=()=>{const i=+el.dataset.i;mst.rows[i].item_code=el.value.trim();fetchStock(i);};
      });
      ov.querySelectorAll('.mn-qty').forEach(el=>{
        el.oninput=()=>{mst.rows[+el.dataset.i].qty=el.value.replace(/[^\d.-]/g,'');};
      });
      ov.querySelectorAll('.mn-rm').forEach(el=>{
        el.oninput=()=>{mst.rows[+el.dataset.i].remark=el.value;};
      });
      /* ★엑셀 붙여넣기 — 도번[탭]수량[탭]비고 여러 행을 한 번에.
         버튼(프롬프트) / 도번칸에 직접 Ctrl+V 둘 다 지원. */
      const applyPaste=(text,startRow)=>{
        const lines=String(text||'').split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
        if(!lines.length)return 0;
        let i=(startRow==null?mst.rows.findIndex(r=>!r.item_code&&!r.qty):startRow);
        if(i<0)i=mst.rows.length;
        let n=0;
        lines.forEach(ln=>{
          const c=ln.split(/\t|,|\s{2,}/).map(x=>x.trim());
          const it=(c[0]||'').replace(/^["']|["']$/g,'');
          if(!it)return;
          const qy=(c[1]||'').replace(/[^\d.-]/g,'');
          const rm=(c[2]||'');
          while(mst.rows.length<=i)mst.rows.push({item_code:'',itemnm:'',stock:null,qty:'',remark:''});
          mst.rows[i]={item_code:it,itemnm:'',stock:null,qty:qy,remark:rm};
          i++;n++;
        });
        while(mst.rows.length<i+4)mst.rows.push({item_code:'',itemnm:'',stock:null,qty:'',remark:''});
        paint();
        msg(n+'행 붙여넣기 — 재고 조회중…');
        if(mst.cust) mst.rows.forEach((r,k)=>{if(r.item_code&&r.stock==null)fetchStock(k);});
        else msg(n+'행 붙여넣기 완료 · ⚠거래처를 선택해야 재고가 표시됩니다.');
        return n;
      };
      q('#mn-xl').onclick=()=>{
        const t=window.prompt('엑셀에서 복사한 내용을 붙여넣으세요 (Ctrl+V)\n\n'
                             +'형식: 도번[탭]수량[탭]비고  — 여러 행 가능','');
        if(t) applyPaste(t,null);
      };
      /* 도번칸에 직접 Ctrl+V — 여러 줄이면 그 행부터 채운다 */
      ov.querySelectorAll('.mn-it').forEach(el=>{
        el.onpaste=ev=>{
          const t=(ev.clipboardData||window.clipboardData).getData('text')||'';
          if(!/[\t\r\n]/.test(t))return;          // 단일 셀이면 기본 동작
          ev.preventDefault();
          applyPaste(t,+el.dataset.i);
        };
      });
      q('#mn-add').onclick=()=>{for(let i=0;i<5;i++)mst.rows.push({item_code:'',itemnm:'',stock:null,qty:'',remark:''});paint();};
      q('#mn-del').onclick=()=>{mst.rows=mst.rows.filter(r=>r.item_code||r.qty);
                                while(mst.rows.length<30)mst.rows.push({item_code:'',itemnm:'',stock:null,qty:'',remark:'',direct:''});paint();};
      q('#mn-close').onclick=close;
      q('#mn-save').onclick=doSave;
      if(!mst.cust) msg('⚠ 거래처를 먼저 선택하세요(필수). 이름 일부만 입력해도 됩니다 — 예: 대원 → 대원산업');
      else msg('도번 입력 또는 엑셀 붙여넣기(도번⇥수량⇥비고) — 그 거래처의 현재 세트재고가 표시됩니다.');
    };

    /* 도번 입력 시 품명 + 현재고 (레거시 f_pu_get_set_mat_stock) */
    const fetchStock=async i=>{
      const r=mst.rows[i]; if(!r.item_code||!mst.cust){r.stock=null;return;}
      try{
        const q=new URLSearchParams({cust:mst.cust,item:r.item_code});
        const d=await fetch(`${API}/api/setstock/manual/prep?`+q).then(x=>x.json());
        const hit=(d.rows||[]).find(x=>x.item_code===r.item_code);
        r.stock=hit?hit.stock_qty:0; r.itemnm=hit?hit.itemnm:'';
        r.direct=hit&&hit.direct?'1':'';
        if(d.next_no)mst.nextno=d.next_no;
      }catch(e){ r.stock=null; }
      paint();
    };

    const doSave=async()=>{
      if(mst.busy)return;
      if(!mst.cust)return alert('거래처는 필수입니다.\n\n거래처명을 입력해 목록에서 선택하세요(예: 대원 → 대원산업).');
      const rows=mst.rows.filter(r=>r.item_code&&(+r.qty));
      if(!rows.length)return alert('입고할 도번·수량을 입력하세요.');
      const neg=rows.find(r=>+r.qty<0);
      if(neg)return alert('세트입고수량을 (-)로 처리할 수 없습니다.\n\n[자재세트재고조정] 메뉴에서 (-)로 조정하세요.');
      const tot=rows.reduce((a,r)=>a+(+r.qty||0),0);
      // ★반영 범위를 확인창에 명시 — 하위재고가 움직이는지 여부는 되돌리기 어려운 차이다.
      const setOnly=(mst.scope==='set');
      if(!window.confirm(`${mst.custnm} · ${rows.length}건 / 합계 ${won(tot)}\n\n`
                        +(setOnly
                          ? `[세트재고만 반영]\n세트재고만 기록합니다. 하위 자도번 재고는 변하지 않습니다. 진행?`
                          : `[하위재고 반영]\n세트재고 + 자도번 재고파생 + 사급소진. 진행?`)))return;
      mst.busy=true;paint();
      try{
        const body={ymd:mst.ymd.slice(2).replace(/-/g,''),cust:mst.cust,
                    scope:mst.scope,
                    user:(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹'),
                    rows:rows.map(r=>({item_code:r.item_code,qty:+r.qty,remark:r.remark}))};
        const res=await fetch(`${API}/api/setstock/manual`,{method:'POST',
                    headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        const j=await res.json();
        if(!res.ok||!j.ok)throw new Error(j.detail||JSON.stringify(j).slice(0,200));
        alert(`수동입고 완료 — 수동입고NO ${j.manual_no}\n\n`
             +`· 반영범위 ${j.scope==='set'?'세트재고만':'하위재고 반영'}\n`
             +`· 세트입고 ${j.count}건\n· 자도번 재고파생 ${j.ledger_posted}행\n`
             +`· 사급 소진 ${j.sagub_posted<0?'(오류)':j.sagub_posted+'행'}`);
        close(); await load();
      }catch(e){ alert('수동입고 실패: '+e.message); mst.busy=false; paint(); }
    };

    /* ★거래처 목록 + 수동입고NO 를 prep 한 번에서 받는다(2026-09-01).
       종전엔 `/api/base/partners` 를 불렀는데 **그런 엔드포인트가 없어 404** 였고,
       custMap 이 통째로 비어 어떤 거래처를 입력해도 "일치하는 거래처가 없습니다"가 떴다
       (실측: 케이비/2266 — DB·nx.partner 에는 정상 존재). */
    fetch(`${API}/api/setstock/manual/prep`).then(r=>r.json()).then(d=>{
      mst.nextno=d.next_no||'';
      (d.custs||[]).forEach(x=>{
        const nm=String(x.nm||'').trim(), cd=String(x.code||'').trim();
        if(nm&&cd)custMap[nm]=cd;
      });
      paint();
    }).catch(()=>paint());

    ov.onclick=e=>{if(e.target===ov)close();};
    paint();
  };

  const draw=()=>{
    if(st.sortKey){const k=st.sortKey,d=st.sortDir||1;st.rows.sort((a,b)=>{const x=a[k],y=b[k],nx=parseFloat(x),ny=parseFloat(y);if(x!=null&&y!=null&&!isNaN(nx)&&!isNaN(ny))return(nx-ny)*d;return String(x==null?"":x).localeCompare(String(y==null?"":y),"ko")*d;});}
    const totq=st.rows.reduce((a,r)=>a+(+r.maint_qty||0),0);
    const inf=st.info;
    c.innerHTML=`
     <div class="page-title">📦 자재세트입고관리</div>
     <div class="page-sub">협력사 세트 <b>SET바코드 스캔/장부입고</b> → 세트입고 실적 + 입고완료분 <b>자도번 재고파생</b>(TAG='S') · 검사품=입고대기 · 레거시 <code>w_pu_stock_140</code></div>
     <div class="panel" style="border:2px solid #2e86de"><div class="panel-h">세트 입고처리</div><div class="panel-b">
       <div class="toolbar" style="flex-wrap:wrap;gap:8px">
         <label class="tl" style="font-weight:600">SET바코드</label>
         <input class="inp" id="sc-bc" value="${esc(st.scan)}" placeholder="SET바코드 스캔/입력" style="width:200px">
         <button class="btn" id="sc-go">🔍 송장조회</button>
         <button class="btn" id="sc-recv" style="background:#27ae60;color:#fff" ${st.busy?"disabled":""}>${st.busy?"처리중…":"📥 입고처리"}</button>
         <span style="width:14px"></span>
         <button class="btn" id="sc-man" style="background:#8e44ad;color:#fff">📝 수동입고(장부)</button>
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
    {const b=g("#sc-bc");b.oninput=x=>st.scan=x.target.value;b.onkeydown=x=>{if(x.key==="Enter")doScan();};}
    g("#sc-go").onclick=doScan;
    g("#sc-recv").onclick=doReceive;
    g("#sc-man").onclick=openManual;
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

/* ===== 협력사: 사급 수불장 (탭: 사급부품·원소재·용접봉) ===== */
SCREEN.sagubledger=(c)=>{
  let tab=(c.__satab||'part');
  const set=t=>{tab=t;c.__satab=t;draw();};
  const draw=()=>{
    c.innerHTML=`<div style="display:flex;flex-direction:column;height:100%">
      <div style="flex:0 0 auto;display:flex;gap:2px;border-bottom:2px solid var(--line);padding:4px 2px 0">
        ${[['part','사급부품'],['raw','원소재'],['weld','용접봉']].map(([k,n])=>
          `<button class="btn ${tab===k?'':'ghost'}" data-t="${k}" style="border-radius:6px 6px 0 0;${tab===k?'background:#1c7c3a;color:#fff':''}">${n}</button>`).join('')}
      </div>
      <div id="sa-sub" style="flex:1;min-height:0"></div></div>`;
    c.querySelectorAll('[data-t]').forEach(b=>b.onclick=()=>set(b.dataset.t));
    const sub=c.querySelector('#sa-sub');
    (tab==='raw'?_tabRaw:tab==='weld'?_tabWeld:_tabPart)(sub);
  };
  draw();
};

const _tabPart=(c)=>{
  const API=API_BASE;
  const pad=n=>String(n).padStart(2,"0");
  const iso=d=>`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
  const yy=s=>s?s.slice(2).replace(/-/g,""):"";            // 2026-01-01 → 260101
  const won=v=>(v==null||v==='')?'<span style="color:#c9d1dc">-</span>':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:2});
  const now=new Date();
  let st={rows:[],custs:[],tot:{},cust:"",mat:"",sign:"",scope:"sent",
          fr:"2026-07-01",to:iso(now),sortKey:"",sortDir:1,loading:false,
          sel:null,detail:[],dfinal:0,dloading:false};
  const load=async()=>{st.loading=true;st.sel=null;draw();
    try{const r=await fetch(`${API}/api/sagubledger/list?cust=${encodeURIComponent(st.cust)}&mat=${encodeURIComponent(st.mat)}&fr=${yy(st.fr)}&to=${yy(st.to)}&sign=${st.sign}&scope=${st.scope}`);
      const j=await r.json();st.rows=j.rows||[];st.custs=j.custs||[];st.tot=j.tot||{};}catch(e){st.rows=[];}
    st.loading=false;draw();};
  const loadDetail=async(row)=>{st.sel=row;st.dloading=true;drawDetail();
    try{const r=await fetch(`${API}/api/sagubledger/detail?cust=${encodeURIComponent(row.cust_code)}&mat=${encodeURIComponent(row.mat_code)}&fr=${yy(st.fr)}&to=${yy(st.to)}`);
      const j=await r.json();st.detail=j.rows||[];st.dfinal=j.final_qty||0;}catch(e){st.detail=[];}
    st.dloading=false;drawDetail();};
  const detailHTML=()=>{
    if(!st.sel)return '<div class="empty" style="padding:16px;color:var(--muted)">왼쪽에서 (협력사×자도번)을 선택하면 수불이력이 표시됩니다.</div>';
    const s=st.sel;
    return `<div style="padding:6px 8px;font-size:12px;border-bottom:1px solid var(--line)"><b>${esc(s.custnm||s.cust_code)}</b> · <b>${esc(s.mat_code)}</b> <span class="cap" style="color:var(--muted)">${esc(s.matnm||"")}</span></div>
      <div class="grid-wrap" style="flex:1;min-height:0;overflow:auto"><table class="tbl" style="white-space:nowrap"><thead><tr>
        <th>일자</th><th class="center">구분</th><th class="num">전일잔량</th><th class="num">협력사입고</th><th class="num">협력사출고</th><th class="num">잔량</th></tr></thead>
      <tbody>${st.detail.map(r=>`<tr>
        <td>${esc(r.maint_ymd)}</td><td class="center">${esc(r.tagnm)}</td>
        <td class="num" style="color:var(--muted)">${won(r.prev_qty)}</td>
        <td class="num" style="color:#1f7a3d">${r.in_qty?won(r.in_qty):''}</td>
        <td class="num" style="color:#c0392b">${r.out_qty?won(r.out_qty):''}</td>
        <td class="num qty" style="color:${(+r.stock_qty<0)?'#c0392b':'#1f2d3d'}"><b>${won(r.stock_qty)}</b></td></tr>`).join("")||`<tr><td colspan="6" style="padding:14px;color:var(--muted)">${st.dloading?"조회중…":"수불 이력 없음"}</td></tr>`}
      <tr class="grandtot"><td colspan="5" class="center">최종 잔량</td><td class="num" style="color:${(+st.dfinal<0)?'#c0392b':'#1f7a3d'}"><b>${won(st.dfinal)}</b></td></tr>
      </tbody></table></div>`;};
  const drawDetail=()=>{const d=c.querySelector("#sl-detail");if(d)d.innerHTML=detailHTML();};
  const draw=()=>{
    if(st.sortKey){const k=st.sortKey,dr=st.sortDir||1;st.rows.sort((a,b)=>{const x=a[k],y=b[k],nx=parseFloat(x),ny=parseFloat(y);if(x!=null&&y!=null&&!isNaN(nx)&&!isNaN(ny))return(nx-ny)*dr;return String(x==null?"":x).localeCompare(String(y==null?"":y),"ko")*dr;});}
    const t=st.tot||{};
    c.innerHTML=`
     <div style="display:flex;flex-direction:column;height:100%">
      <div style="flex:0 0 auto">
       <div class="page-title">사급부품 수불장</div>
       <div class="page-sub">협력사 관점 <b>협력사입고(우리 창고 출고) − 협력사출고(세트입고로 재입고) = 잔량</b>. 기초 0(2026-01~) · 용접봉/은납 별도 트랙 제외 · 소진은 통일 소요엔진 산출.</div>
       <div class="toolbar" style="flex-wrap:nowrap;overflow-x:auto">
         <label class="tl">기간</label><input class="inp" type="date" id="sl-fr" value="${esc(st.fr)}" style="width:140px"> ~ <input class="inp" type="date" id="sl-to" value="${esc(st.to)}" style="width:140px">
         <label class="tl" style="margin-left:8px">협력사</label><input class="inp" id="sl-cust" list="sl-custlist" value="${esc((st.custs.find(o=>o.code===st.cust)||{}).nm||"")}" placeholder="협력사명(빈칸=전체)" style="width:150px">
         <datalist id="sl-custlist">${st.custs.map(o=>`<option value="${esc(o.nm||o.code)}">`).join("")}</datalist>
         <label class="tl" style="margin-left:8px">자도번</label><input class="inp" id="sl-mat" value="${esc(st.mat)}" placeholder="자도번/품명" style="width:140px">
         <label class="tl" style="margin-left:8px">잔량</label>
         <select class="inp" id="sl-sign"><option value="">전체</option><option value="1" ${st.sign==="1"?"selected":""}>(+)보유</option><option value="-1" ${st.sign==="-1"?"selected":""}>(−)마이너스</option><option value="0" ${st.sign==="0"?"selected":""}>0</option></select>
         <label class="tl" style="margin-left:8px">범위</label>
         <select class="inp" id="sl-scope"><option value="sent" ${st.scope==="sent"?"selected":""}>우리가 보낸 부품</option><option value="all" ${st.scope==="all"?"selected":""}>전체(소진만 포함)</option></select>
         <button class="btn" id="sl-go" style="margin-left:8px">조회</button>
       </div>
      </div>
      <div style="flex:1;min-height:0;display:flex;gap:8px;margin-top:8px">
       <div class="panel" style="flex:1.3;display:flex;flex-direction:column;min-width:0">
         <div class="panel-h" style="flex:0 0 auto">협력사·사급부품 ${st.loading?"(조회중…)":`(${st.rows.length}건)`} · 협력사입고 ${won(t.sent)} / 협력사출고 ${won(t.used)} / 잔량 <b style="color:${(+t.bal<0)?'#c0392b':'#1f7a3d'}">${won(t.bal)}</b></div>
         <div class="grid-wrap" style="flex:1;min-height:0;overflow:auto"><table class="tbl" style="white-space:nowrap"><thead><tr>
           <th data-key="custnm">협력사</th><th data-key="mat_code">자도번</th><th data-key="matnm">품명</th>
           <th class="num" data-key="sent">협력사입고</th><th class="num" data-key="used">협력사출고</th><th class="num" data-key="bal">잔량</th></tr></thead>
         <tbody>${(()=>{
           if(!st.rows.length)return `<tr><td colspan="6" style="padding:16px;color:var(--muted)">${st.loading?"":"데이터 없음 — 기간/필터를 확인하세요."}</td></tr>`;
           let o='',pc=null,s={sent:0,used:0,bal:0};
           const flush=()=>{if(pc!==null)o+=`<tr style="background:#eef2f7;font-weight:600"><td colspan="3">${esc(pc)} 소계</td><td class="num" style="color:#1f7a3d">${won(s.sent)}</td><td class="num" style="color:#c0392b">${won(s.used)}</td><td class="num"><b style="color:${s.bal<0?'#c0392b':'#1f2d3d'}">${won(s.bal)}</b></td></tr>`;};
           st.rows.forEach((r,i)=>{const cn=r.custnm||r.cust_code;if(cn!==pc){flush();pc=cn;s={sent:0,used:0,bal:0};}
             o+=`<tr class="sl-row" data-i="${i}" style="cursor:pointer;${st.sel&&st.sel.cust_code===r.cust_code&&st.sel.mat_code===r.mat_code?'background:#eef4ff':''}"><td>${esc(r.custnm||r.cust_code)}</td><td><b>${esc(r.mat_code)}</b></td><td class="cap" style="max-width:150px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.matnm||"")}">${esc(r.matnm||"")}</td><td class="num" style="color:#1f7a3d">${won(r.sent)}</td><td class="num" style="color:#c0392b">${won(r.used)}</td><td class="num qty" style="color:${(+r.bal<0)?'#c0392b':'#1f2d3d'}"><b>${won(r.bal)}</b></td></tr>`;
             s.sent+=+r.sent||0;s.used+=+r.used||0;s.bal+=+r.bal||0;});
           flush();return o;})()}
         <tr class="grandtot"><td colspan="3" class="center">합계 ${st.rows.length}건</td><td class="num">${won(t.sent)}</td><td class="num">${won(t.used)}</td><td class="num" style="color:${(+t.bal<0)?'#c0392b':'#1f7a3d'}"><b>${won(t.bal)}</b></td></tr>
         </tbody></table></div>
       </div>
       <div class="panel" style="flex:1;display:flex;flex-direction:column;min-width:0">
         <div class="panel-h" style="flex:0 0 auto">수불 이력 (running balance)</div>
         <div id="sl-detail" style="flex:1;min-height:0;display:flex;flex-direction:column;overflow:hidden">${detailHTML()}</div>
       </div>
      </div>
     </div>`;
    const g=id=>c.querySelector(id);
    g("#sl-fr").onchange=x=>st.fr=x.target.value; g("#sl-to").onchange=x=>st.to=x.target.value;
    g("#sl-cust").onchange=x=>{const v=x.target.value.trim();const m=st.custs.find(o=>(o.nm||o.code)===v);st.cust=m?m.code:"";};
    g("#sl-mat").oninput=x=>st.mat=x.target.value;
    g("#sl-sign").onchange=x=>st.sign=x.target.value; g("#sl-scope").onchange=x=>st.scope=x.target.value;
    g("#sl-go").onclick=load;
    c.querySelectorAll(".sl-row").forEach(tr=>tr.onclick=()=>{const r=st.rows[+tr.dataset.i];
      c.querySelectorAll(".sl-row").forEach(x=>x.style.background="");tr.style.background="#eef4ff";loadDetail(r);});
    c.querySelectorAll("thead th[data-key]").forEach(th=>{addResizer(th);const k=th.dataset.key;th.style.cursor="pointer";th.title="더블클릭 정렬";
      th.ondblclick=()=>{st.sortDir=(st.sortKey===k&&st.sortDir===1)?-1:1;st.sortKey=k;draw();};});
  };
  load();
};

/* ===== 원소재 탭 — 규격별 불출/소진/잔량 kg ===== */
const _tabRaw=(c)=>{
  const API=API_BASE;
  const now=new Date();
  const m2ym=s=>s?(s.slice(2,4)+s.slice(5,7)):"";           // 2026-08 → 2608
  const ym2m=s=>s&&s.length===4?("20"+s.slice(0,2)+"-"+s.slice(2)):"";
  const kg=v=>(v==null||v==='')?'<span style="color:#c9d1dc">-</span>':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:1});
  const won=v=>(v==null||v==='')?'<span style="color:#c9d1dc">-</span>':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:0});
  let st={rows:[],custs:[],tot:{},cust:"",mat:"",sign:"",to_ym:`${String(now.getFullYear()).slice(2)}${String(now.getMonth()+1).padStart(2,'0')}`,
          sortKey:"",sortDir:1,loading:false,sel:null,detail:[],dfinal:0,dloading:false};
  const load=async()=>{st.loading=true;st.sel=null;draw();
    try{const r=await fetch(`${API}/api/rawmatledger/list?cust=${encodeURIComponent(st.cust)}&to_ym=${st.to_ym}&mat=${encodeURIComponent(st.mat)}&sign=${st.sign}`);
      const j=await r.json();st.rows=j.rows||[];st.custs=j.custs||[];st.tot=j.tot||{};}catch(e){st.rows=[];}
    st.loading=false;draw();};
  const loadDetail=async(row)=>{st.sel=row;st.dloading=true;drawDetail();
    try{const r=await fetch(`${API}/api/rawmatledger/detail?cust=${encodeURIComponent(row.cust_code)}&mat=${encodeURIComponent(row.mat)}&od=${row.od}&to_ym=${st.to_ym}`);
      const j=await r.json();st.detail=j.rows||[];st.dfinal=j.final_qty||0;}catch(e){st.detail=[];}
    st.dloading=false;drawDetail();};
  const detailHTML=()=>{
    if(!st.sel)return '<div class="empty" style="padding:16px;color:var(--muted)">왼쪽에서 (협력사×규격)을 선택하면 월별 수불이 표시됩니다.</div>';
    const s=st.sel;
    return `<div style="padding:6px 8px;font-size:12px;border-bottom:1px solid var(--line)"><b>${esc(s.custnm)}</b> · <b>${esc(s.mat)} Ø${s.od}</b></div>
      <div class="grid-wrap" style="flex:1;min-height:0;overflow:auto"><table class="tbl" style="white-space:nowrap"><thead><tr>
        <th>월</th><th class="num">전월잔량</th><th class="num">불출(입고)</th><th class="num">소진(출고)</th><th class="num">잔량</th></tr></thead>
      <tbody>${st.detail.map(r=>`<tr>
        <td>${esc(r.ym)}</td><td class="num" style="color:var(--muted)">${kg(r.prev_qty)}</td>
        <td class="num" style="color:#1f7a3d">${r.in_qty?kg(r.in_qty):''}</td>
        <td class="num" style="color:#c0392b">${r.out_qty?kg(r.out_qty):''}</td>
        <td class="num qty" style="color:${(+r.stock_qty<0)?'#c0392b':'#1f2d3d'}"><b>${kg(r.stock_qty)}</b></td></tr>`).join("")||`<tr><td colspan="5" style="padding:14px;color:var(--muted)">${st.dloading?"조회중…":"수불 없음"}</td></tr>`}
      <tr class="grandtot"><td colspan="4" class="center">최종 잔량(kg)</td><td class="num" style="color:${(+st.dfinal<0)?'#c0392b':'#1f7a3d'}"><b>${kg(st.dfinal)}</b></td></tr>
      </tbody></table></div>`;};
  const drawDetail=()=>{const d=c.querySelector("#rl-detail");if(d)d.innerHTML=detailHTML();};
  const draw=()=>{
    if(st.sortKey){const k=st.sortKey,dr=st.sortDir||1;st.rows.sort((a,b)=>{const x=a[k],y=b[k],nx=parseFloat(x),ny=parseFloat(y);if(x!=null&&y!=null&&!isNaN(nx)&&!isNaN(ny))return(nx-ny)*dr;return String(x==null?"":x).localeCompare(String(y==null?"":y),"ko")*dr;});}
    const t=st.tot||{};
    c.innerHTML=`
     <div style="display:flex;flex-direction:column;height:100%">
      <div style="flex:0 0 auto">
       <div class="page-title">원소재 수불장 (동관)</div>
       <div class="page-sub">협력사 관점 <b>불출(자재불출집계표) − 소진(입고완제품×동중량, 소요엔진+협력사 협의치수) = 잔량</b>. 규격(재질·외경)별 kg · 기초0(2026-07~) · 업체별 마감기준.</div>
       <div class="toolbar" style="flex-wrap:nowrap;overflow-x:auto">
         <label class="tl">조회월(누적)</label><input class="inp" type="month" id="rl-ym" value="${esc(ym2m(st.to_ym))}" style="width:150px">
         <label class="tl" style="margin-left:8px">협력사</label><input class="inp" id="rl-cust" list="rl-custlist" value="${esc((st.custs.find(o=>o.code===st.cust)||{}).nm||"")}" placeholder="협력사명(빈칸=전체)" style="width:140px">
         <datalist id="rl-custlist">${st.custs.map(o=>`<option value="${esc(o.nm||o.code)}">`).join("")}</datalist>
         <label class="tl" style="margin-left:8px">재질</label><input class="inp" id="rl-mat" value="${esc(st.mat)}" placeholder="CU/고강도" style="width:90px">
         <label class="tl" style="margin-left:8px">잔량</label>
         <select class="inp" id="rl-sign"><option value="">전체</option><option value="1" ${st.sign==="1"?"selected":""}>(+)보유</option><option value="-1" ${st.sign==="-1"?"selected":""}>(−)마이너스</option><option value="0" ${st.sign==="0"?"selected":""}>0</option></select>
         <button class="btn" id="rl-go" style="margin-left:8px">조회</button>
       </div>
      </div>
      <div style="flex:1;min-height:0;display:flex;gap:8px;margin-top:8px">
       <div class="panel" style="flex:1.4;display:flex;flex-direction:column;min-width:0">
         <div class="panel-h" style="flex:0 0 auto">협력사·동관규격 ${st.loading?"(조회중…)":`(${st.rows.length}건)`} · 불출 ${kg(t.sent)} / 소진 ${kg(t.used)} / 잔량 <b style="color:${(+t.bal<0)?'#c0392b':'#1f7a3d'}">${kg(t.bal)}</b> kg · 정산 ${won(t.amt)}원</div>
         <div class="grid-wrap" style="flex:1;min-height:0;overflow:auto"><table class="tbl" style="white-space:nowrap"><thead><tr>
           <th data-key="custnm">협력사</th><th data-key="mat">재질</th><th class="num" data-key="od">외경Ø</th>
           <th class="num" data-key="sent">불출kg</th><th class="num" data-key="used">소진kg</th><th class="num" data-key="bal">잔량kg</th>
           <th class="num" data-key="amt">정산원</th></tr></thead>
         <tbody>${(()=>{
           if(!st.rows.length)return `<tr><td colspan="7" style="padding:16px;color:var(--muted)">${st.loading?"":"데이터 없음"}</td></tr>`;
           let o='',pc=null,s={sent:0,used:0,bal:0,amt:0};
           const flush=()=>{if(pc!==null)o+=`<tr style="background:#eef2f7;font-weight:600"><td colspan="3">${esc(pc)} 소계</td><td class="num" style="color:#1f7a3d">${kg(s.sent)}</td><td class="num" style="color:#c0392b">${kg(s.used)}</td><td class="num"><b style="color:${s.bal<0?'#c0392b':'#1f2d3d'}">${kg(s.bal)}</b></td><td class="num">${won(s.amt)}</td></tr>`;};
           st.rows.forEach((r,i)=>{const cn=r.custnm||r.cust_code;if(cn!==pc){flush();pc=cn;s={sent:0,used:0,bal:0,amt:0};}
             o+=`<tr class="rl-row" data-i="${i}" style="cursor:pointer;${st.sel&&st.sel.cust_code===r.cust_code&&st.sel.mat===r.mat&&st.sel.od===r.od?'background:#eef4ff':''}"><td>${esc(r.custnm||r.cust_code)}</td><td>${esc(r.mat)}</td><td class="num">${r.od}</td><td class="num" style="color:#1f7a3d">${kg(r.sent)}</td><td class="num" style="color:#c0392b">${kg(r.used)}</td><td class="num qty" style="color:${(+r.bal<0)?'#c0392b':'#1f2d3d'}"><b>${kg(r.bal)}</b></td><td class="num" style="color:${(+r.amt<0)?'#c0392b':'#555'}">${won(r.amt)}</td></tr>`;
             s.sent+=+r.sent||0;s.used+=+r.used||0;s.bal+=+r.bal||0;s.amt+=+r.amt||0;});
           flush();return o;})()}
         <tr class="grandtot"><td colspan="3" class="center">합계 ${st.rows.length}건</td><td class="num">${kg(t.sent)}</td><td class="num">${kg(t.used)}</td><td class="num" style="color:${(+t.bal<0)?'#c0392b':'#1f7a3d'}"><b>${kg(t.bal)}</b></td><td class="num">${won(t.amt)}</td></tr>
         </tbody></table></div>
       </div>
       <div class="panel" style="flex:1;display:flex;flex-direction:column;min-width:0">
         <div class="panel-h" style="flex:0 0 auto">월별 수불 (running balance)</div>
         <div id="rl-detail" style="flex:1;min-height:0;display:flex;flex-direction:column;overflow:hidden">${detailHTML()}</div>
       </div>
      </div>
     </div>`;
    const g=id=>c.querySelector(id);
    g("#rl-ym").onchange=x=>{st.to_ym=m2ym(x.target.value)||st.to_ym;};
    g("#rl-cust").onchange=x=>{const v=x.target.value.trim();const m=st.custs.find(o=>(o.nm||o.code)===v);st.cust=m?m.code:"";};
    g("#rl-mat").oninput=x=>st.mat=x.target.value; g("#rl-sign").onchange=x=>st.sign=x.target.value;
    g("#rl-go").onclick=load;
    c.querySelectorAll(".rl-row").forEach(tr=>tr.onclick=()=>{const r=st.rows[+tr.dataset.i];
      c.querySelectorAll(".rl-row").forEach(x=>x.style.background="");tr.style.background="#eef4ff";loadDetail(r);});
    c.querySelectorAll("thead th[data-key]").forEach(th=>{addResizer(th);const k=th.dataset.key;th.style.cursor="pointer";th.title="더블클릭 정렬";
      th.ondblclick=()=>{st.sortDir=(st.sortKey===k&&st.sortDir===1)?-1:1;st.sortKey=k;draw();};});
  };
  load();
};

/* ===== 용접봉 탭 — 협력사별 불출/소진/잔량 kg + 정산(1% 단일) ===== */
const _tabWeld=(c)=>{
  const API=API_BASE; const now=new Date();
  const m2ym=s=>s?(s.slice(2,4)+s.slice(5,7)):"";
  const ym2m=s=>s&&s.length===4?("20"+s.slice(0,2)+"-"+s.slice(2)):"";
  const kg=v=>(v==null||v==='')?'<span style="color:#c9d1dc">-</span>':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:2});
  const won=v=>(v==null||v==='')?'<span style="color:#c9d1dc">-</span>':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:0});
  let st={rows:[],custs:[],tot:{},cust:"",sign:"",to_ym:`${String(now.getFullYear()).slice(2)}${String(now.getMonth()+1).padStart(2,'0')}`,loading:false,sel:null,detail:[],dfinal:0,dloading:false};
  const load=async()=>{st.loading=true;st.sel=null;draw();
    try{const r=await fetch(`${API}/api/rawmatledger/weld?cust=${encodeURIComponent(st.cust)}&to_ym=${st.to_ym}&sign=${st.sign}`);
      const j=await r.json();st.rows=j.rows||[];st.custs=j.custs||[];st.tot=j.tot||{};}catch(e){st.rows=[];}
    st.loading=false;draw();};
  const loadDetail=async(row)=>{st.sel=row;st.dloading=true;drawDetail();
    try{const r=await fetch(`${API}/api/rawmatledger/weld/detail?cust=${encodeURIComponent(row.cust_code)}&to_ym=${st.to_ym}`);
      const j=await r.json();st.detail=j.rows||[];st.dfinal=j.final_qty||0;}catch(e){st.detail=[];}
    st.dloading=false;drawDetail();};
  const detailHTML=()=>{
    if(!st.sel)return '<div class="empty" style="padding:16px;color:var(--muted)">왼쪽에서 협력사를 선택하면 월별 수불이 표시됩니다.</div>';
    return `<div style="padding:6px 8px;font-size:12px;border-bottom:1px solid var(--line)"><b>${esc(st.sel.custnm||st.sel.cust_code)}</b> · 용접봉(1%)</div>
      <div class="grid-wrap" style="flex:1;min-height:0;overflow:auto"><table class="tbl" style="white-space:nowrap"><thead><tr>
        <th>월</th><th class="num">전월잔량</th><th class="num">불출</th><th class="num">소진</th><th class="num">잔량</th></tr></thead>
      <tbody>${st.detail.map(r=>`<tr>
        <td>${esc(r.ym)}</td><td class="num" style="color:var(--muted)">${kg(r.prev_qty)}</td>
        <td class="num" style="color:#1f7a3d">${r.in_qty?kg(r.in_qty):''}</td><td class="num" style="color:#c0392b">${r.out_qty?kg(r.out_qty):''}</td>
        <td class="num qty" style="color:${(+r.stock_qty<0)?'#c0392b':'#1f2d3d'}"><b>${kg(r.stock_qty)}</b></td></tr>`).join("")||`<tr><td colspan="5" style="padding:14px;color:var(--muted)">${st.dloading?"조회중…":"수불 없음"}</td></tr>`}
      <tr class="grandtot"><td colspan="4" class="center">최종 잔량(kg)</td><td class="num" style="color:${(+st.dfinal<0)?'#c0392b':'#1f7a3d'}"><b>${kg(st.dfinal)}</b></td></tr>
      </tbody></table></div>`;};
  const drawDetail=()=>{const d=c.querySelector("#wl-detail");if(d)d.innerHTML=detailHTML();};
  const draw=()=>{const t=st.tot||{};
    c.innerHTML=`<div style="display:flex;flex-direction:column;height:100%">
     <div style="flex:0 0 auto">
      <div class="page-sub" style="margin-top:6px">용접봉(1%) 협력사별 <b>불출 − 소진 = 잔량</b> kg + 정산(현물 62,700 / 사급 21,100). 기초0(2026-07~)·업체별 마감기준.</div>
      <div class="toolbar" style="flex-wrap:nowrap;overflow-x:auto">
        <label class="tl">조회월(누적)</label><input class="inp" type="month" id="wl-ym" value="${esc(ym2m(st.to_ym))}" style="width:150px">
        <label class="tl" style="margin-left:8px">협력사</label><input class="inp" id="wl-cust" list="wl-custlist" value="${esc((st.custs.find(o=>o.code===st.cust)||{}).nm||"")}" placeholder="협력사명(빈칸=전체)" style="width:140px">
        <datalist id="wl-custlist">${st.custs.map(o=>`<option value="${esc(o.nm||o.code)}">`).join("")}</datalist>
        <label class="tl" style="margin-left:8px">잔량</label>
        <select class="inp" id="wl-sign"><option value="">전체</option><option value="1" ${st.sign==="1"?"selected":""}>(+)보유</option><option value="-1" ${st.sign==="-1"?"selected":""}>(−)마이너스</option></select>
        <button class="btn" id="wl-go" style="margin-left:8px">조회</button>
      </div>
     </div>
     <div style="flex:1;min-height:0;display:flex;gap:8px;margin-top:8px">
      <div class="panel" style="flex:1.2;min-height:0;display:flex;flex-direction:column;min-width:0">
       <div class="panel-h" style="flex:0 0 auto">협력사 용접봉 ${st.loading?"(조회중…)":`(${st.rows.length}건)`} · 불출 ${kg(t.sent)} / 소진 ${kg(t.used)} / 잔량 <b style="color:${(+t.bal<0)?'#c0392b':'#1f7a3d'}">${kg(t.bal)}</b> kg · 정산 ${won(t.amt)}원</div>
       <div class="grid-wrap" style="flex:1;min-height:0;overflow:auto"><table class="tbl" style="white-space:nowrap"><thead><tr>
         <th>협력사</th><th class="num">불출kg</th><th class="num">소진kg</th><th class="num">잔량kg</th><th class="num">정산원</th></tr></thead>
       <tbody>${st.rows.map((r,i)=>`<tr class="wl-row" data-i="${i}" style="cursor:pointer;${st.sel&&st.sel.cust_code===r.cust_code?'background:#eef4ff':''}">
         <td>${esc(r.custnm||r.cust_code)}</td>
         <td class="num" style="color:#1f7a3d">${kg(r.sent)}</td><td class="num" style="color:#c0392b">${kg(r.used)}</td>
         <td class="num qty" style="color:${(+r.bal<0)?'#c0392b':'#1f2d3d'}"><b>${kg(r.bal)}</b></td>
         <td class="num" style="color:${(+r.amt<0)?'#c0392b':'#555'}">${won(r.amt)}</td></tr>`).join("")||`<tr><td colspan="5" style="padding:16px;color:var(--muted)">${st.loading?"":"데이터 없음"}</td></tr>`}
       <tr class="grandtot"><td class="center">합계 ${st.rows.length}건</td><td class="num">${kg(t.sent)}</td><td class="num">${kg(t.used)}</td><td class="num" style="color:${(+t.bal<0)?'#c0392b':'#1f7a3d'}"><b>${kg(t.bal)}</b></td><td class="num">${won(t.amt)}</td></tr>
       </tbody></table></div>
      </div>
      <div class="panel" style="flex:1;min-height:0;display:flex;flex-direction:column;min-width:0">
       <div class="panel-h" style="flex:0 0 auto">월별 수불 (running balance)</div>
       <div id="wl-detail" style="flex:1;min-height:0;display:flex;flex-direction:column;overflow:hidden">${detailHTML()}</div>
      </div>
     </div></div>`;
    const g=id=>c.querySelector(id);
    g("#wl-ym").onchange=x=>{st.to_ym=m2ym(x.target.value)||st.to_ym;};
    g("#wl-cust").onchange=x=>{const v=x.target.value.trim();const m=st.custs.find(o=>(o.nm||o.code)===v);st.cust=m?m.code:"";};
    g("#wl-sign").onchange=x=>st.sign=x.target.value; g("#wl-go").onclick=load;
    c.querySelectorAll(".wl-row").forEach(tr=>tr.onclick=()=>{const r=st.rows[+tr.dataset.i];
      c.querySelectorAll(".wl-row").forEach(x=>x.style.background="");tr.style.background="#eef4ff";loadDetail(r);});
  };
  load();
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
  // ★신규 모델 등록(2026-08-27) — 기존 매핑이 없는 모델은 검색으로 찾을 수 없어
  //   등록 진입점 자체가 없었다. 모델번호를 직접 입력받아 바로 편집모드로 들어간다.
  const newModel=async()=>{
    const m=(prompt('신규 등록할 LG 모델번호를 입력하세요.\n(이미 매핑이 있으면 그 내용을 불러옵니다)','')||'').trim();
    if(!m)return;
    by='model';q=m;sel=m;
    // 기존 매핑이 있으면 nx 등록분을 이어서 편집, 없으면 빈 행 하나로 시작
    try{const r=await fetch(`${API}/api/modelbom/get?model=${encodeURIComponent(m)}`);data=await r.json();}
    catch(e){data={rows:[]};}
    erows=(data.rows||[]).filter(r=>r.src==='nx').map(r=>({...r}));
    if(!erows.length)erows=[{item:'',use_qty:1,from:'',to:'',remarks:''}];
    editMode=true;draw();
    search();            // 좌측 목록 갱신(비동기 — 끝나면 draw 재호출)
  };
  const save=async()=>{
    try{const r=await fetch(`${API}/api/modelbom/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:sel,rows:erows})});
      const j=await r.json();if(j.ok){alert(`모델BOM 저장 완료 — ${j.count}건 (nx 신규등록)`);load(sel);return;}alert('저장 실패: '+(j.detail||JSON.stringify(j)));}
    catch(e){alert('저장 실패: '+e);}};
  const draw=()=>{
    const R=data.rows||[];
    const canW=(typeof PERM!=='undefined')?PERM.canEdit('modelbom'):true;   // 수정권한 게이트(규칙#16)
    c.innerHTML=`
     <div class="page-title">🧬 모델BOM 관리 <span style="font-size:12px;color:var(--muted);font-weight:400">LG모델 → 우리 도번 매핑 (편성 커버리지)</span></div>
     <div class="page-sub">LG 모델번호를 우리 ASSY 도번으로 매핑. 편성(협력사계획)이 이 매핑으로 모델→도번을 전개. 조회=<code>nx.PR_M_MODEL_BOM</code> ∪ <code>nx.model_bom</code>(신규등록). <b>미매핑 신규모델은 좌측 「＋ 신규 모델 등록」</b>으로 추가.</div>
     <div style="display:flex;gap:14px;align-items:flex-start">
      <div style="flex:0 0 300px">
       <div class="toolbar"><select class="inp" id="mb-by"><option value="model"${by==='model'?' selected':''}>모델→도번</option><option value="item"${by==='item'?' selected':''}>도번→모델(역)</option></select>
         <input class="inp" id="mb-q" value="${esc(q)}" placeholder="${by==='item'?'도번':'모델'} 검색" style="width:150px"><button class="btn" id="mb-search">🔍</button></div>
       ${canW?`<div class="toolbar" style="margin-top:2px"><button class="btn" id="mb-new" style="background:#1c7c3a;color:#fff;width:100%">＋ 신규 모델 등록</button></div>
       <div class="page-sub" style="margin:2px 0 6px;font-size:11px;color:#8aa0bd">※ 매핑이 아직 없는 모델은 검색되지 않습니다 — 위 버튼으로 모델번호를 직접 입력해 등록하세요.</div>`:''}
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
          <tbody>${loading?spinRow(7):(R.length?R.map(r=>`<tr>${by==='item'?`<td><b>${esc(r.model)}</b></td>`:''}<td><b>${esc(r.item)}</b></td><td class="bcap" title="${esc(r.nm)}" style="max-width:160px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td><td class="num">${r.use_qty}</td><td class="center">${ymd(r.from)}</td><td class="center">${ymd(r.to)}</td><td class="center">${esc(r.wc)}</td><td class="center"><span style="font-size:10px;color:${r.src==='nx'?'#1c7c3a':'#888'}">${r.src==='nx'?'nx등록':'nx기존'}</span></td></tr>`).join(''):`<tr><td colspan="${by==='item'?8:7}" class="empty">매핑 없음 — ${by==='model'?'신규등록/수정(nx)으로 추가':''}</td></tr>`)}</tbody></table>`
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
    const nw=g('#mb-new');if(nw)nw.onclick=newModel;
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
  // ★일자컬럼 = 생산화면(파트별 생산계획)과 동일 형식: 일자+요일(예 27목), 주말은 빨강.
  const wlab=y=>{if(!y||y.length<6)return dcol(y);const dt=new Date(2000+ +y.slice(0,2),+y.slice(2,4)-1,+y.slice(4,6));const dow='일월화수목금토'[dt.getDay()];return `${y.slice(4,6)}${dow}`;};
  const isWkend=y=>{if(!y||y.length<6)return false;const dt=new Date(2000+ +y.slice(0,2),+y.slice(2,4)-1,+y.slice(4,6));return dt.getDay()===0||dt.getDay()===6;};
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  // ★기본 소스=nx(우리편성). 레거시는 1:1 대조용 선택지로 남김(2026-08-27).
  // ★기준일 = **마지막 계획업로드의 일자축 첫날**(planBaseIso, 2026-08-28 사용자 확정).
  //   당일로 잡으면 업로드 전날 기준이 되어, 미출하분이 재편성되며 충당된 재고와 어긋난다.
  let F={from:planBaseIso(),days:31,wc:'',part:'',assy:'',line:'',gubun:'외주',src:'nx'};
  let data={dates:[],rows:[],cnt:0,sum_qty:0,note:''}, wcs=[], loading=false, msg='';
  /* ★일자셀 드래그 선택(2026-08-31 요청) — 준비실적처리(키팅)와 같은 '사각범위' 방식.
     조회 전용 화면이므로 쓰기는 없다. 고른 칸의 잔여(계획−완료) 합계를 배지에 보여준다.
     단순 mousemove 로 '지나간 셀'만 담으면 빠르게 끌 때 이벤트가 유실돼 중간이 빠지므로,
     시작셀~현재셀의 (행,열) 사각범위를 매 move 마다 통째로 계산한다(엑셀 감각). */
  const PN={sel:new Map()};
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
     // ★nx 소스도 레거시와 같은 그레인(도번=assy 1행) → 자도번LIST 는 그 행의 자재목록(mats). 없으면 종전 part.
     // ★nx 소스도 레거시와 같은 그레인(도번=assy 1행, 제번 합산) → 자도번LIST 는 그 도번의 자재목록(mats).
     assy:r.assy||'', jado:r.mats||r.part||'', matn:r.matn||0, wocnt:r.wocnt||0, sagub:!!r.sagub, lot:(r.lot!=null?r.lot:null),
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
      const dn=Number((r.donedays&&r.donedays[d])||0),bg=(r.colors&&r.colors[d])||'';if(!pl&&!dn)return '<td class="num pn-c" style="color:#dfe6ef">·</td>';
      // ★드래그 선택용 속성(2026-08-31) — 잔여 = 계획 − 완료
      const rem=Math.max(pl-dn,0);
      const key=[r.wc||r.wcnm||'',r.assy||'',d].join('|');
      const on=PN.sel.has(key)?' pn-on':'';
      return `<td class="num pn-c${on}" data-k="${esc(key)}" data-rem="${rem}" data-pl="${pl}" data-dn="${dn}"`
           + ` data-assy="${esc(r.assy||'')}" data-ymd="${d}"`
           + ` style="white-space:nowrap${bg?';background:'+bg:''}">${nf(dn)}/${nf(pl)}</td>`;};
    const FIX=11;   // ★품목정보 컬럼 제거(2026-08-27 사용자 요청) — 12 → 11
    const gcell=d=>frac?`<td class="num" style="white-space:nowrap"><b>${nf(gDone[d]||0)}/${nf(gDay[d]||0)}</b></td>`:`<td class="num"><b>${nf(gDay[d]||0)}</b></td>`;
    const grandRow=rows.length?`<tr class="grandtot"><td class="center"><b>계</b></td><td class="center" style="color:#33507d">${nf(data.cnt||rows.length)}건</td><td colspan="6"></td><td class="num"><b>${nf(sMat)}</b></td><td class="num">-</td><td class="num"><b>${nf(sReq)}</b></td>${dates.map(d=>gcell(d)).join('')}</tr>`:'';
    const rowTr=r=>`<tr>
        <td class="num" style="color:#8aa0bd">${r.seq}</td>
        <td><b>${esc(r.wcnm)}</b>${r.alloc_note?` <span class="bdg" style="font-size:9px;background:#eaf3ff;color:#1c47a0;border:1px solid #bcd;border-radius:6px;padding:0 4px" title="조달 프로파일 발주업체 배분 반영">${esc(r.alloc_note)}</span>`:''}</td><td class="center">${esc(r.line)}</td><td>${esc(r.workcenter)}</td>
        <td><b>${esc(r.assy)}</b></td>
        <td><div style="width:400px;max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.jado)}">${r.matn>1?`<span class="bdg" style="font-size:9px;background:#f2f6fc;color:#41597e;border:1px solid #d3dceb;border-radius:6px;padding:0 4px;margin-right:3px" title="이 도번에 걸린 자재 ${r.matn}종${r.wocnt?` · 제번 ${r.wocnt}건 합산`:''} (수량은 도번 계획수량)">${r.matn}종</span>`:''}${esc(r.jado)}</div></td>
        <td class="center">${r.sagub?'<span class="bdg sagub" style="font-size:10px">사급</span>':''}</td>
        <td class="num">${nn(r.lot)}</td><td class="num"><b>${nn(r.matq)}</b></td>
        <td class="num" style="color:#1c7c3a" title="완료수량 = 출하실적 + 완제품재고 배분 + 세트/입고대기 재고배분 (레거시 SP+510창, 도번 공유풀). 협력사(외주) 지정 시 표시.">${nn(r.doneq)}</td>
        <td class="num">${nn(r.reqq)}</td>
        ${dates.map(d=>dcell(r,d)).join('')}</tr>`;
    const bodyHTML=()=>loading?spinRow(FIX+dates.length):(rowsCur.length?(rowsCur.map(rowTr).join('')+grandRow):`<tr><td colspan="${FIX+dates.length}" class="empty">조회 결과 없음 — 자도번작업처/기준일자/기간을 확인하세요.</td></tr>`);
    // ★<style> 은 반드시 .pn-root 안에 둔다 — 탭 컨테이너(#pg-*, height:100%)의 형제로 두면
    //   블록 박스 하나가 더 쌓여 .pn-root 의 height:100% 와 합쳐져 넘치고, 그만큼 아래가 빈다.
    //   (c52de04 가 잡은 height:100% 체인이 여기서 다시 끊겼던 원인 — 2026-08-27)
    c.innerHTML=`
    <div class="pn-root" style="display:flex;flex-direction:column;height:100%">
    <style>
      /* ★페이지 본문(창) 세로 스크롤 금지 — 그리드만 내부 스크롤. 헤더=sticky top, 합계행=sticky bottom(CLAUDE.md §3) */
      .pn-grid thead th{position:sticky;top:0;z-index:3;background:#eef2f8}
      .pn-grid tr.grandtot td{position:sticky;bottom:0;z-index:2;background:#f0f4fb;box-shadow:0 -1px 0 var(--line-2,#c9d3e0)}
      /* ★그리드 세로폭 확보 — 헤더(제목·툴바·범례)를 압축하고 .content 패딩을 줄여 표에 넘김.
         ⚠음수 margin 으로 패딩을 상쇄하면 height:100% 계산이 어긋나 표 아래가 빈다 →
           .content 에 직접 padding 을 줄이고 화면 루트는 height:100% 그대로 둔다. */
      .pn-head .page-sub{margin-bottom:0}
      .pn-head .toolbar{padding:7px 11px;margin-bottom:6px;gap:7px}
      .pn-head .page-title{font-size:16px}
      /* ★높이 구조는 c52de04 확정 패턴을 그대로 쓴다: 루트 height:100% + 표 flex:1;min-height:0.
         음수 margin·JS 높이계산·부모 flex 변경은 모두 어긋난다(2026-08-27 재확인). */
      .pn-root>style{display:none}   /* flex 자식으로 공간 차지 방지 */
      /* ★전 컬럼 가운데 정렬 — 단 자도번LIST(6열)만 긴 텍스트라 좌측 유지(2026-08-27 요청).
         숫자칸(.num)도 가운데로 오되 숫자 자릿수는 tabular-nums 로 맞춘다. */
      /* ⚠app.css 의 .tbl .num{text-align:right} 보다 특정도가 높아야 이긴다(.tbl.pn-grid) */
      /* ★nth-child(12) 제거(2026-08-31) — 품목정보 컬럼을 뺀 뒤(FIX 12→11) 12번째가
         '첫 일자칸(31월)'이 되어 그 칸만 좌측 정렬로 남아 있었다. */
      table.tbl.pn-grid th, table.tbl.pn-grid td{text-align:center}
      table.tbl.pn-grid th:nth-child(6),  table.tbl.pn-grid tbody tr:not(.grandtot) td:nth-child(6){text-align:left}
      table.tbl.pn-grid .num{font-variant-numeric:tabular-nums}
      /* ★일자셀 드래그 선택 — 키팅과 동일한 파스텔 표시(배경색은 살리고 막만 덧씌움) */
      table.tbl.pn-grid td.pn-c{cursor:cell}
      table.tbl.pn-grid td.pn-c:hover{outline:2px solid #9dc0e8;outline-offset:-2px}
      table.tbl.pn-grid td.pn-on{outline:2px solid #4a86e8;outline-offset:-2px;font-weight:700;
        background-image:linear-gradient(rgba(219,234,254,.72),rgba(219,234,254,.72))}
    </style>
     <div class="pn-head" style="flex:0 0 auto">
     <div class="page-title" style="margin-bottom:4px">📋 협력사계획현황 <span style="font-size:12px;color:var(--muted);font-weight:400">4주간 계획수량 — 도번·자도번LIST·일자별 (당김 반영)</span>
       <span style="font-size:11px;font-weight:400;margin-left:8px" title="${F.src==='legacy'?'레거시 라이브 PR_T_PLAN_PART_MAT 직독. 당김=PR_M_LINE_NO.CUST_MAINT_DAY(회사근무일).':'웹 편성 결과만 사용(라이브 미참조): 계획업로드→④파트별→⑤자재소요. 기간=소요일자(part_plan_ymd·당김반영), 수량=도번 계획수량(plan_item_dtl). 그레인=레거시 w_pr_outside_410 동일(도번 1행·제번 합산).'}">${F.src==='legacy'?'🔴 <b>레거시 라이브</b>':'🟢 <b>우리편성(nx)</b>'}</span></div>
     <!-- ★조건문 2줄 배치(2026-08-27 사용자 요청 — 레거시 w_pr_outside_410 동일).
            1줄 = 소스 · 기준일자 · 기간   /   2줄 = 도번 · 자도번 · 자도번작업처 · 라인 + 조회
            레거시는 라벨을 회색칸에 넣어 폭을 맞춘다 → .tl 을 고정폭으로 정렬. -->
     <style>
      .pn-head .pn-r{display:flex;align-items:center;gap:6px;margin-bottom:4px;flex-wrap:nowrap}
      .pn-head .pn-r .tl{background:#eaf0f8;border:1px solid #cdd9e8;border-radius:4px;
        padding:3px 8px;font-size:12px;color:#33507d;font-weight:600;text-align:center;
        white-space:nowrap;min-width:74px}
     </style>
     <div class="toolbar pn-r" style="margin-top:2px">
       <label class="tl">소스</label>
       <select class="inp" id="pn-src" style="width:auto;min-width:158px">
         <option value="nx" ${F.src==='nx'?'selected':''}>우리편성 (nx)</option>
         <option value="legacy" ${F.src==='legacy'?'selected':''}>레거시 라이브 (당김반영)</option></select>
       <label class="tl">기준일자</label>${legacyDateHTML('pn-base',F.from)}
       <label class="tl">기간</label><input class="inp" id="pn-days" value="${esc(F.days)}" style="width:52px;min-width:52px;text-align:center" title="조회 기간(일). 레거시 4주간 화면 기본=31일"><span style="font-size:12px;color:#5a6b80">일</span>
       <div class="spacer"></div><span class="rowcount">${nf(data.cnt)}건 · 자재수량합 <b>${nf(data.sum_qty)}</b> · 일자 ${dates.length}</span>
     </div>
     <div class="toolbar pn-r">
       <label class="tl">도번</label><input class="inp" id="pn-assy" list="pnl-assy" value="${esc(F.assy)}" style="width:130px;min-width:130px" placeholder="도번(ASSY)" autocomplete="off"><datalist id="pnl-assy">${pnAssyOpts}</datalist>
       <label class="tl">자도번</label><input class="inp" id="pn-part" list="pnl-part" value="${esc(F.part)}" style="width:130px;min-width:130px" placeholder="자도번" autocomplete="off"><datalist id="pnl-part">${pnPartOpts}</datalist>
       <!-- ★자도번작업처 = 레거시처럼 [코드][🔍][업체명] — 필수 입력이라 강조 -->
       <label class="tl" style="color:#1c47a0;background:#dceaff;border-color:#9dc0ea;min-width:88px">자도번작업처</label>
       <input class="inp" id="pn-wccode" value="${esc(F.wc)}" placeholder="코드" autocomplete="off" title="자도번작업처 코드 — 직접 입력 후 Enter" style="width:74px;min-width:74px;text-align:center;background:${F.wc?'#eaf3ff':'#fff7e6'};border:2px solid ${F.wc?'#7fa8e8':'#f0b429'};font-weight:700">
       <button class="btn" id="pn-wcfind" title="업체 찾기" style="padding:0 7px;min-width:28px">🔍</button>
       <input class="inp" id="pn-wc" list="pnl-wc" value="${esc(wcName)}" placeholder="거래처명" autocomplete="off" title="필수 — 협력사를 선택해야 조회됩니다" style="width:150px;min-width:150px;background:${F.wc?'#eaf3ff':'#fff7e6'};border:2px solid ${F.wc?'#7fa8e8':'#f0b429'};font-weight:600"><datalist id="pnl-wc">${wcOpts}</datalist>
       <button class="btn" id="pn-search" style="margin-left:4px">🔍 조회</button>
       <div class="spacer"></div>
       <!-- ★드래그 선택 잔여합계(2026-08-31 요청) -->
       <span id="pn-selinfo" style="font-size:11.5px;color:#33507d;white-space:nowrap"></span>
     </div>
     ${(frac||msg||data.note)?`<div class="page-sub" style="font-size:11px;margin:2px 0;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
       ${frac?`<span>일자셀=<b>완료/계획</b> · <span style="background:#ffff00;padding:0 5px;border-radius:3px">생산완료</span> <span style="background:#fac090;padding:0 5px;border-radius:3px">출하완료</span> <span style="background:#c0c0c0;padding:0 5px;border-radius:3px" title="세트재고 + 입고대기 물량이 배분된 칸 (협력사는 키팅과 무관)">세트재고</span></span>`:''}
       ${msg?`<span style="color:#c0392b">⚠ ${esc(msg)}</span>`:''}
       ${data.note?`<span style="color:#b8860b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:52%" title="${esc(data.note)}">ℹ ${esc(data.note)}</span>`:''}</div>`:''}
     </div>
     <!-- ★flex:0 1 auto + max-height:100% (4787a13 확정) — flex:1 은 행이 적어도 표를 화면 끝까지
          늘려 표 아래가 흰 여백으로 남는다. 이 값이면 짧으면 내용만큼 줄고, 길면 스크롤된다. -->
     <div class="grid-wrap" style="flex:0 1 auto;min-height:0;max-height:100%;overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl pn-grid" style="font-size:11px;white-space:nowrap"><thead><tr>
       <th class="num">SEQ</th><th>자도번작업처</th><th>라인</th><th>작업처</th><th>도번</th><th style="min-width:400px;width:400px">자도번LIST</th><th class="center">사급</th>
       <th class="num">LOT수량</th><th class="num">자재수량</th><th class="num">완료수량</th><th class="num">요청수량</th>
       ${dates.map(d=>`<th class="center"${isWkend(d)?' style="color:#c0392b"':''}>${esc(wlab(d))}</th>`).join('')}</tr></thead>
      <tbody>${bodyHTML()}</tbody></table></div>
    </div>`;
    const g=id=>c.querySelector(id);

    /* ==== 일자셀 드래그 선택 — 키팅과 동일한 '사각범위' 방식(2026-08-31) ==== */
    (()=>{
      const gw=c.querySelector('.grid-wrap'); if(!gw)return;
      gw.style.userSelect='none'; gw.style.webkitUserSelect='none';
      gw.onselectstart=()=>false;
      const rcOf=td=>{const tr=td.parentElement;return {r:tr?tr.rowIndex:-1,c:td.cellIndex};};
      const cellAt=(x,y)=>{const e=document.elementFromPoint(x,y);
        return e?(e.closest('.pn-c')||null):null;};
      const paint=()=>{
        const el=c.querySelector('#pn-selinfo'); if(!el)return;
        let n=0,rem=0,pl=0,dn=0;
        PN.sel.forEach(v=>{n++;rem+=v.rem;pl+=v.pl;dn+=v.dn;});
        el.innerHTML = n
          ? `선택 <b>${n}</b>칸 · 잔여 <b style="color:#c0392b">${nf(rem)}</b>`
            + ` <span style="color:#8aa0bd">(완료 ${nf(dn)} / 계획 ${nf(pl)})</span>`
            + ` <span id="pn-selclr" style="cursor:pointer;color:#1c47a0;text-decoration:underline;margin-left:6px">해제</span>`
          : `<span style="color:#8aa0bd">일자칸을 드래그하면 잔여수량 합계가 표시됩니다</span>`;
        const cl=c.querySelector('#pn-selclr');
        if(cl)cl.onclick=()=>{PN.sel.clear();
          c.querySelectorAll('.pn-on').forEach(x=>x.classList.remove('pn-on'));paint();};
      };
      let _a=null,_cells=null,_own=null,_on=false;
      const applyRect=td=>{
        if(!_a||!_cells)return;
        const b=rcOf(td);
        const r1=Math.min(_a.r,b.r),r2=Math.max(_a.r,b.r);
        const c1=Math.min(_a.c,b.c),c2=Math.max(_a.c,b.c);
        for(const it of _cells){
          const inR=it.r>=r1&&it.r<=r2&&it.c>=c1&&it.c<=c2;
          const has=PN.sel.has(it.k);
          if(inR&&!has){PN.sel.set(it.k,it.v);it.td.classList.add('pn-on');_own.add(it.k);}
          else if(!inR&&has&&_own.has(it.k)){PN.sel.delete(it.k);it.td.classList.remove('pn-on');}
        }
        paint();};
      gw.onmousedown=ev=>{
        const st0=ev.target.closest?ev.target.closest('.pn-c'):null; if(!st0)return;
        if(ev.button!==0)return;
        ev.preventDefault();
        if(!ev.ctrlKey&&!ev.metaKey){
          PN.sel.clear(); c.querySelectorAll('.pn-on').forEach(x=>x.classList.remove('pn-on'));
        }
        _on=true; _own=new Set();
        _cells=[...c.querySelectorAll('.pn-c[data-k]')].map(x=>{const p=rcOf(x);
          return {td:x,r:p.r,c:p.c,k:x.dataset.k,
                  v:{rem:+x.dataset.rem||0,pl:+x.dataset.pl||0,dn:+x.dataset.dn||0,
                     assy:x.dataset.assy||'',ymd:x.dataset.ymd||''}};});
        _a=rcOf(st0); applyRect(st0);
      };
      gw.onmousemove=ev=>{if(!_on)return;const td=cellAt(ev.clientX,ev.clientY);if(td)applyRect(td);};
      if(!gw._pnUp){gw._pnUp=1;document.addEventListener('mouseup',()=>{_on=false;});}
      paint();
    })();
    // ★자도번작업처 = [코드][🔍][업체명] 2칸 연동(2026-08-27 레거시 동일).
    //   업체명이 목록에 있으면 그 코드를, 없으면 코드칸 입력값을 쓴다.
    const syncInputs=()=>{
      const wn=g('#pn-wc').value.trim(), wcd=(g('#pn-wccode')||{value:''}).value.trim();
      const byNm=wcs.find(w=>(w.nm||w.cc)===wn);
      if(byNm) F.wc=byNm.cc;
      else if(wcd) F.wc=wcd;                       // 코드 직접 입력
      else if(!wn) F.wc='';
      F.days=g('#pn-days').value||31;F.part=g('#pn-part').value;F.assy=g('#pn-assy').value;};
    // 코드 입력 → 업체명 자동 채움
    const wcCode=g('#pn-wccode');
    if(wcCode)wcCode.onchange=()=>{const cd=wcCode.value.trim();const w=wcs.find(x=>x.cc===cd);
      if(w)g('#pn-wc').value=w.nm||w.cc;};
    // 업체명 선택 → 코드 자동 채움
    const wcName2=g('#pn-wc');
    if(wcName2)wcName2.onchange=()=>{const w=wcs.find(x=>(x.nm||x.cc)===wcName2.value.trim());
      if(w&&wcCode)wcCode.value=w.cc;};
    const wcFind=g('#pn-wcfind');
    if(wcFind)wcFind.onclick=()=>{const el=g('#pn-wc');if(el){el.focus();el.select();}};
    const ssel=g('#pn-src');if(ssel)ssel.onchange=e=>{F.src=e.target.value;F.wc='';loadWc().then(draw);};
    // 레거시 기준일자 위젯: 전일/익일/달력 → 자동 재조회
    bindLegacyDate(c,'pn-base',()=>F.from,(v)=>{F.from=v;syncInputs();load();});
    g('#pn-days').onchange=()=>{syncInputs();load();};
    g('#pn-search').onclick=()=>{syncInputs();load();};
    ['#pn-part','#pn-assy','#pn-wc','#pn-wccode'].forEach(id=>{const el=g(id);if(el)el.onkeyup=e=>{if(e.key==='Enter')g('#pn-search').click();};});
    // ★헤더 더블클릭 정렬(고정 12컬럼 + 일자 피벗) — tbody만 재렌더로 화살표·리사이저 보존. 합계행은 bodyHTML이 항상 맨끝에 붙임.
    if(!loading&&rowsCur.length){
      const KEYS=['seq','wcnm','line','workcenter','assy','jado','sagub','lot','matq','doneq','reqq'].concat(dates.map(d=>'d_'+d));
      enableSort(c,KEYS,()=>rowsCur,()=>{const tb=c.querySelector('tbody');if(tb)tb.innerHTML=bodyHTML();});
    }
  };
  // ★계획 기준일이 아직 캐시에 없으면(첫 진입) 받아서 반영한 뒤 그린다 — 2026-08-28.
  planBase().then(b=>{if(b&&b.iso)F.from=b.iso;}).catch(()=>{})
    .then(()=>loadWc()).then(draw);   // ★자동 전체조회 금지 — 협력사 선택 후 [조회]
};

/* ===== 일일 영업/매입 현황 (경영) — 조회화면(엑셀형). ① 매입/불출/실매입 by 구분 · 마감기준 · 공급가(원) ===== */
SCREEN.dailypurissue=(c)=>{
  const API=API_BASE;
  const _ymd=(d)=>{const p=n=>(''+n).padStart(2,'0');return `${(''+d.getFullYear()).slice(2)}${p(d.getMonth()+1)}${p(d.getDate())}`;};
  const _yst=(()=>{const d=new Date();d.setDate(d.getDate()-1);return _ymd(d);})();   // ★전일(어제)
  let F=null, loading=false, day=_yst;   // ★조회일 기본=전일. 실행 시 자동조회.
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
    // 매출요약 행(당일/상반기/하반기/합계) — 0은 '-'. day=당일실적(F.today) 값(해당행만), undefined면 빈칸.
    const mrow=(lbl,o,bold,day)=>{const d=o||{h1:0,h2:0,tot:0};const z=v=>v?wonI(v):'-';return `<tr${bold?' style="font-weight:700"':''}><td>${lbl}</td><td class="num" style="background:#f2faf4">${day===undefined?'':(day?wonI(day):'-')}</td><td class="num">${z(d.h1)}</td><td class="num">${z(d.h2)}</td><td class="num">${z(d.tot)}</td></tr>`;};
    c.innerHTML=`
     <div class="page-title">📋 일일 영업/매입 현황 <span style="font-size:12px;color:var(--muted);font-weight:400">확정입고·불출 마감기준 · 구분별 누적/당일/총 · 단위 원(공급가, VAT제외)</span></div>
     <div class="page-sub">조회일 선택 → 마감월초~전일=<b>누적</b>, 조회일=<b>당일</b>, 누적+당일=<b>총</b>. 매입=확정입고(CUST_TYPE+사급원소재), 불출=자재불출, 실매입=매입−불출.</div>
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
       ${F.sales?(()=>{const CG='<colgroup><col><col style="width:130px"><col style="width:54px"></colgroup>';const TS='width:100%;table-layout:fixed;background:#fff';return `
       <div style="flex:1;min-width:560px;display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap">
         <!-- 가운데: 재료비 → 사급율 (매출은 우측 '당일 실적'으로 이동·누적매출 패널 삭제) -->
         <div style="flex:1;min-width:280px">
           <div style="font-weight:700;color:#1c47a0;margin-bottom:4px">재료비 <span style="font-weight:400;font-size:10px;color:#888">(사용 기준 · 기말 감소=사용)</span></div>
           <table class="tbl" style="${TS}"><colgroup><col><col style="width:96px"><col style="width:96px"><col style="width:96px"></colgroup>
             <thead><tr><th style="text-align:left">재고</th><th class="num">기초</th><th class="num">기말</th><th class="num">차액(사용)</th></tr></thead><tbody>
             ${(()=>{const J=F.jaego||{};const dc=v=>`color:${(v||0)<0?'#c0392b':'#1c7c3a'}`;const rw=(lb,b,c)=>`<tr><td>${lb}</td><td class="num">${wonI(b||0)}</td><td class="num">${wonI(c||0)}</td><td class="num" style="${dc((b||0)-(c||0))}">${wonI((b||0)-(c||0))}</td></tr>`;
               return rw('자재',J.base_mat,J.cur_mat)+rw('생산',J.base_prd,J.cur_prd)+rw('영업',J.base_sales,J.cur_sales)
               +`<tr style="font-weight:700;background:#eef2f8"><td>재고 합계</td><td class="num">${wonI(J.base_total)}</td><td class="num">${wonI(J.cur_total)}</td><td class="num" style="${dc((J.base_total||0)-(J.cur_total||0))}">${wonI((J.base_total||0)-(J.cur_total||0))}</td></tr>`;})()}
           </tbody></table>
           ${F.jaemat?`<div style="margin-top:6px;padding:7px 10px;background:#f0f7f0;border-radius:6px;font-size:12px;line-height:1.8">
             <div style="display:flex;justify-content:space-between"><span>원재료 매입 <span style="font-size:10px;color:#888">(매입−불출)</span></span><b>${wonI(F.jaemat.net)}</b></div>
             <div style="display:flex;justify-content:space-between"><span>＋ 재고 사용 <span style="font-size:10px;color:#888">(기초−기말)</span></span><b>${wonI(F.jaemat.use)}</b></div>
             <div style="display:flex;justify-content:space-between;border-top:1px solid #c9d6ea;margin-top:3px;padding-top:3px"><b style="color:#1c47a0">＝ 재료비</b><b style="color:#1c47a0">${wonI(F.jaemat.jaemat)}</b></div>
             <div style="display:flex;justify-content:space-between;align-items:center"><b>재료비율 <span style="font-size:10px;color:#888">(÷ LG매출)</span></b><b style="color:#c0392b;font-size:15px">${F.jaemat.jaemat_pct}%</b></div>
           </div>`:''}
           <div style="font-weight:700;color:#8a5a1a;margin:10px 0 4px">사급율 <span style="font-weight:400;font-size:10px;color:#888">(LG사급 vs 당사ERP)</span></div>
           <table class="tbl" style="${TS}">${CG}<tbody>
             ${(()=>{const D=F.dae||{};const S=F.sagubyul||{};const dr=(D.dangsa_raw||0)-(D.lg_raw||0);const dp=(D.dangsa_part||0)-(D.lg_part||0);const dc=v=>`color:${(v||0)<0?'#c0392b':'#1c7c3a'}`;return `
             <tr><td>LG사급 − 원소재</td><td class="num">${wonI(D.lg_raw||0)}</td><td class="num"><b>${S.raw_pct}%</b></td></tr>
             <tr><td style="padding-left:12px;color:#555">당사ERP − 원소재</td><td class="num">${wonI(D.dangsa_raw||0)}</td><td></td></tr>
             <tr><td style="padding-left:12px">차액</td><td class="num" style="${dc(dr)}">${wonI(dr)}</td><td></td></tr>
             <tr><td>LG사급 − 부품</td><td class="num">${wonI(D.lg_part||0)}</td><td class="num"><b>${S.part_pct}%</b></td></tr>
             <tr><td style="padding-left:12px;color:#555">당사ERP − 부품</td><td class="num">${wonI(D.dangsa_part||0)}</td><td></td></tr>
             <tr><td style="padding-left:12px">차액</td><td class="num" style="${dc(dp)}">${wonI(dp)}</td><td></td></tr>
             <tr style="font-weight:700;border-top:1px solid #dde3ea"><td>차액 합계</td><td class="num" style="${dc(D.diff)}">${wonI(D.diff||0)}</td><td></td></tr>`;})()}
           </tbody></table>
         </div>
         <!-- 맨 오른쪽: 매출요약 (상반기/하반기/합계, 원·흰배경) -->
         ${F.maechul?(()=>{const T=F.today||{};return `<div style="flex:1;min-width:400px">
           <div style="font-weight:700;color:#1c47a0;margin-bottom:4px">매출·사급 요약 <span style="font-weight:400;font-size:10px;color:#888">(당일 실적 + 상/하반기)</span></div>
           <table class="tbl" style="${TS}"><colgroup><col><col style="width:96px"><col style="width:96px"><col style="width:96px"><col style="width:96px"></colgroup><thead><tr><th style="text-align:left">구분</th><th class="num" style="background:#eaf5ea">당일</th><th class="num">상반기</th><th class="num">하반기</th><th class="num">합계</th></tr></thead><tbody>
             ${mrow('현매출(절삭)',F.maechul.hyeon_cut,false,T.hyeon_cut)}
             ${mrow('현매출(설치)',F.maechul.hyeon_seol,false,T.hyeon_seol)}
             ${(F.maechul.hyeon_etc&&F.maechul.hyeon_etc.tot)?mrow('현매출(기타)',F.maechul.hyeon_etc,false,T.hyeon_etc):''}
             ${mrow('현매출(합계)',F.maechul.hyeon_hab,true,T.sales_hab)}
             ${mrow('추가매출(절삭)',F.maechul.chuga_cut)}
             ${mrow('추가매출(설치)',F.maechul.chuga_seol)}
             ${mrow('총예상매출',F.maechul.chong,true)}
             ${mrow('사급-원재료',F.maechul.sagub_raw,false,T.sagub_raw)}
             ${mrow('사급-부품(실적)',F.maechul.sagub_part,false,T.sagub_part)}
             ${mrow('추가-사급부품(예상)',F.maechul.sagub_part_fc)}
             ${mrow('사급-부품(합계)',F.maechul.sagub_part_sum,true)}
             ${mrow('사급-합계',F.maechul.sagub_hab,true,T.sagub_hab)}
             ${mrow('LG 수금금액',F.maechul.lg_sugum,true)}
           </tbody></table></div>`;})():''}
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
      if(F.today){rows.push([]);rows.push(['당일실적','매출-절삭',F.today.hyeon_cut]);rows.push(['당일실적','매출-설치',F.today.hyeon_seol]);rows.push(['당일실적','매출-기타',F.today.hyeon_etc]);rows.push(['당일실적','매출합계',F.today.sales_hab]);rows.push(['당일실적','사급-원소재',F.today.sagub_raw]);rows.push(['당일실적','사급-부품',F.today.sagub_part]);rows.push(['당일실적','사급합계',F.today.sagub_hab]);}
      if(F.jaemat){const J=F.jaego||{};rows.push([]);const jr=(lb,b,c)=>rows.push(['재료비',lb,b,c,(b||0)-(c||0)]);
        rows.push(['재료비','재고(기초/기말/차액)','기초','기말','차액']);jr('자재',J.base_mat,J.cur_mat);jr('생산',J.base_prd,J.cur_prd);jr('영업',J.base_sales,J.cur_sales);jr('재고합계',J.base_total,J.cur_total);
        rows.push(['재료비','원재료매입(매입−불출)',F.jaemat.net]);rows.push(['재료비','재고사용(기초−기말)',F.jaemat.use]);rows.push(['재료비','재료비(=매입+사용)',F.jaemat.jaemat,'',F.jaemat.jaemat_pct+'%']);}
      if(F.sales){rows.push([]);
        rows.push(['매출','현매출-절삭',F.sales.hyeon_cut]);rows.push(['매출','현매출-설치',F.sales.hyeon_seol]);
        rows.push(['매출','현매출-기타',F.sales.hyeon_etc]);rows.push(['매출','LG매출합계',F.sales.lg_sales]);
        {const D=F.dae||{};const S=F.sagubyul||{};const dr=(D.dangsa_raw||0)-(D.lg_raw||0);const dp=(D.dangsa_part||0)-(D.lg_part||0);
          rows.push(['사급율','LG사급-원소재',D.lg_raw,'',S.raw_pct+'%']);rows.push(['사급율','당사ERP-원소재',D.dangsa_raw]);rows.push(['사급율','차액(원소재)',dr]);
          rows.push(['사급율','LG사급-부품',D.lg_part,'',S.part_pct+'%']);rows.push(['사급율','당사ERP-부품',D.dangsa_part]);rows.push(['사급율','차액(부품)',dp]);
          rows.push(['사급율','차액 합계',D.diff]);}
        if(F.maechul){const M=F.maechul;const mr=(lb,k)=>{const v=M[k]||{};rows.push(['매출요약',lb,v.h1,v.h2,v.tot]);};
          mr('현매출(절삭)','hyeon_cut');mr('현매출(설치)','hyeon_seol');mr('현매출(기타)','hyeon_etc');mr('현매출(합계)','hyeon_hab');
          mr('추가매출(절삭)','chuga_cut');mr('추가매출(설치)','chuga_seol');mr('총예상매출','chong');
          mr('사급-원재료','sagub_raw');mr('사급-부품(실적)','sagub_part');mr('추가-사급부품(예상)','sagub_part_fc');
          mr('사급-부품(합계)','sagub_part_sum');mr('사급-합계','sagub_hab');mr('LG수금금액','lg_sugum');}}
      downloadCSV(`일일영업매입현황_${F.date}.csv`,hd,rows);};
  };
  load(day);   // ★실행 시 전일자로 자동조회
};


/* ==== 거래명세표 수정 (협력사) — 레거시 w_pr_outside_030_new 이식 ====
   세트납품서 단위 납품내역 조회 + 수량수정·삭제 + 출력 3종 재발행.
   ★입고완료건은 조회·인쇄만 — 레거시 동일 메시지.
   ★원천 = 웹 자체 nx.set_input_req(+_dtl). 레거시 미러 직독 끊음(2026-08-31).
     전에는 nx.PU_T_SET_INPUT_REQ_DTL(8/28 라이브 스냅샷)을 읽어, 웹에서 발행한 건이
     이 화면에 0건으로 나왔다. 이제 「거래명세서 발행」이 쓰는 곳을 그대로 읽는다.
     자도번/사용수량/자재수량 = 발행 시 dw_6 전개로 생성된 실적(마스터 유추 아님). */
SCREEN.delivedit=(c)=>{
  const API=API_BASE;
  // ★num 은 전역이 아니다(core.js 의 num 은 _mkMagam 지역) — 여기서 선언
  const num=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:2});
  const canW=(typeof PERM!=='undefined')?PERM.canEdit('delivedit'):true;
  const _t=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
  const y6=(s)=>{const d=(''+(s||'')).replace(/\D/g,'');return d.length>=8?d.slice(2,8):d;};
  const hm=(s)=>{s=''+(s||'');return s.length>=6?`${s.slice(0,2)}:${s.slice(2,4)}:${s.slice(4,6)}`:s;};
  const d6=(s)=>{s=''+(s||'');return s.length===6?`${s.slice(0,2)}/${s.slice(2,4)}/${s.slice(4,6)}`:s;};

  let fr=_t(), to=_t(), cust='', doban='', jado='';   // ★납품기간 기본 = 당일
  let rows=[], loading=false, msg='', cnt=0, heads=0, sheets=0, editable=0;
  let outStmt=true, outTag=true, outInsp=true;
  let custs=[], dobans=[], jados=[];

  const loadCusts=async()=>{try{
    const r=await fetch(`${API}/api/delivedit/custs`);const j=await r.json();
    custs=j.rows||[];}catch(e){custs=[];}};

  // ★도번·자도번 오토컴플리트(§3) — 실제 납품내역에 있는 것만.
  //   기간·거래처가 바뀌면 후보도 그 범위로 좁혀 다시 채운다.
  const loadItems=async()=>{
    const qs=`from_ymd=${y6(fr)}&to_ymd=${y6(to)}&cust=${encodeURIComponent(cust.trim())}`;
    try{
      const [a,b]=await Promise.all([
        fetch(`${API}/api/delivedit/items?kind=doban&${qs}`).then(r=>r.json()),
        fetch(`${API}/api/delivedit/items?kind=jadoban&${qs}`).then(r=>r.json())]);
      dobans=a.rows||[];jados=b.rows||[];
    }catch(e){dobans=[];jados=[];}
  };

  const load=async()=>{loading=true;msg='';draw();
    try{
      const u=`${API}/api/delivedit/list?from_ymd=${y6(fr)}&to_ymd=${y6(to)}`
        +`&cust=${encodeURIComponent(cust.trim())}&doban=${encodeURIComponent(doban.trim())}`
        +`&jadoban=${encodeURIComponent(jado.trim())}`;
      const r=await fetch(u);if(!r.ok)throw new Error('HTTP '+r.status);
      const j=await r.json();
      rows=j.rows||[];cnt=j.cnt||0;heads=j.heads||0;sheets=j.sheets||0;editable=j.editable||0;
    }catch(e){msg='조회 실패 — '+e.message;rows=[];cnt=heads=sheets=editable=0;}
    loading=false;draw();};

  // ★입고완료건은 조회만(레거시 동일). 미입고건만 수량수정.
  const editQty=async(r)=>{
    if(!canW){alert('권한이 없습니다.');return;}
    if(r.cf==='1'){alert('입고완료건은 조회만 가능합니다.');return;}
    const v=prompt(`납품수량 수정\n\n납품서 ${r.sheet_no}${r.barcode?' · 바코드 SET'+r.barcode:''} · ${r.doban}\n${r.dnm||''}\n\n현재 ${r.set_qty}`,r.set_qty);
    if(v===null)return;
    const q=Number(v);
    if(!(q>0)){alert('납품수량은 0보다 커야 합니다.');return;}
    try{
      const res=await fetch(`${API}/api/delivedit/update`,{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({sheet_no:r.sheet_no,cc:r.cc,doban:r.doban,hms:r.hms,qty:q})});
      const j=await res.json().catch(()=>({}));
      if(!res.ok)throw new Error(j.detail||('HTTP '+res.status));
      alert(`수정되었습니다.\n\n${r.doban}  ${j.old_qty} → ${j.new_qty}\n상세 ${j.updated}행 · 헤더 ${j.head_updated}행`);
      load();
    }catch(e){alert('수정 실패\n\n'+e.message);}
  };

  const delRow=async(r)=>{
    if(!canW){alert('권한이 없습니다.');return;}
    if(r.cf==='1'){alert('입고완료건은 조회만 가능합니다.');return;}
    if(!confirm(`납품내역을 삭제하시겠습니까?\n\n납품서 ${r.sheet_no}${r.barcode?' · 바코드 SET'+r.barcode:''} · ${r.doban}\n세트수량 ${r.set_qty}\n\n※미입고분이라 발행이력도 함께 회수됩니다.`))return;
    try{
      const res=await fetch(`${API}/api/delivedit/delete`,{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({sheet_no:r.sheet_no,cc:r.cc,doban:r.doban,hms:r.hms})});
      const j=await res.json().catch(()=>({}));
      if(!res.ok)throw new Error(j.detail||('HTTP '+res.status));
      alert(`삭제되었습니다. (상세 ${j.deleted}행 · 헤더 ${j.head_deleted}행)`);
      load();
    }catch(e){alert('삭제 실패\n\n'+e.message);}
  };

  // 출력 3종 — 입고완료건도 재발행 가능(레거시 동일)
  const doPrint=async(r)=>{
    const kinds=[];
    if(outStmt)kinds.push(['stmt','거래명세서']);
    if(outTag)kinds.push(['tag','입고태그']);
    if(outInsp)kinds.push(['insp','출하검사성적서']);
    if(!kinds.length){alert('출력구분을 하나 이상 선택하세요.');return;}
    /* ★거래명세서는 발행화면과 **같은 양식**으로 낸다(2026-08-31 사용자 확정).
         재출력인데 서식이 다르면 안 된다 — 발행 = 2단 정식(공급자/공급받는자·20행 고정·
         SET바코드 Code39·자재팀/품질팀 결재란), 재출력 = 단순표 였다.
       구현: /api/partner/deliv420/invoice(발행화면과 같은 API)를 **바코드번호로** 부르고
             openDelivInvoice() 로 그린다. 양식이 한 곳에만 있어 앞으로도 어긋나지 않는다.
       ※입고태그·출하검사성적서도 같은 양식 함수(openDelivNote·openInspSheet)를 쓴다. */
    //   ★양식 함수는 screens.etc.js **로드 시점**에 window 에 실린다(모듈 스코프, 2026-08-31).
    //     종전엔 SCREEN.deliv420(발행화면)이 그려질 때만 등록돼, 수정화면만 열고 출력하면
    //     조용히 구식 단순표가 나왔다 — 그 원인은 제거됐다.
    //   ※바코드 없는 건(구 데이터)만 아래 단순표로 떨어진다. 발행분은 전부 정식 양식.
    //   ※출하검사성적서 = 자도번마다 1장(협력사가 전 품번을 검사해 붙인다 — 사용자 확정).
    if(r.barcode && typeof window.openDelivInvoice==='function'){
      let iv=null;
      try{
        const res=await fetch(`${API}/api/partner/deliv420/invoice?barcode=${encodeURIComponent(r.barcode)}`);
        const j=await res.json();
        if(!res.ok)throw new Error(j.detail||('HTTP '+res.status));
        iv=j;
      }catch(e){alert('출력 실패\n\n'+e.message);return;}
      if(outStmt){ window.openDelivInvoice(iv);
                   kinds.splice(kinds.findIndex(k=>k[0]==='stmt'),1); }
      if(outTag && typeof window.openDelivNote==='function'){
                   window.openDelivNote(iv);
                   kinds.splice(kinds.findIndex(k=>k[0]==='tag'),1); }
      if(outInsp && typeof window.openInspSheet==='function'){
                   window.openInspSheet(iv);
                   kinds.splice(kinds.findIndex(k=>k[0]==='insp'),1); }
      if(!kinds.length)return;
    }
    const secs=[];
    for(const [k,nm] of kinds){
      try{
        const u=`${API}/api/delivedit/print?sheet_no=${encodeURIComponent(r.sheet_no)}`
          +`&cc=${encodeURIComponent(r.cc)}&hms=${encodeURIComponent(r.hms)}&kind=${k}`;
        const res=await fetch(u);const j=await res.json();
        if(!res.ok)throw new Error(j.detail||('HTTP '+res.status));
        secs.push(pv(j));
      }catch(e){alert(`${nm} 출력 실패\n\n`+e.message);return;}
    }
    const w=window.open('','_blank');
    if(!w){alert('팝업이 차단되었습니다. 브라우저 설정을 확인하세요.');return;}
    w.document.write(`<!doctype html><html><head><meta charset="utf-8">
      <title>거래명세표 출력 — ${r.barcode?'SET'+esc(r.barcode):esc(r.sheet_no)}</title><style>
      @page{size:A4;margin:10mm}
      body{font-family:'맑은 고딕',Malgun Gothic,sans-serif;font-size:12px;color:#111}
      .pg{page-break-after:always}.pg:last-child{page-break-after:auto}
      h2{text-align:center;letter-spacing:6px;margin:0 0 10px}
      .hd{display:flex;gap:18px;font-size:12px;margin-bottom:8px;flex-wrap:wrap}
      table{width:100%;border-collapse:collapse;font-size:11.5px}
      th,td{border:1px solid #666;padding:3px 5px}
      th{background:#eef2f8;text-align:center}
      td.n{text-align:right;font-variant-numeric:tabular-nums}
      td.c{text-align:center}
      tfoot td{font-weight:700;background:#f6f8fc}
      </style></head><body>${secs.join('')}</body></html>`);
    w.document.close();
    setTimeout(()=>{w.focus();w.print();},350);
  };

  const pv=(j)=>`<div class="pg"><h2>${esc(j.title)}</h2>
    <div class="hd"><b>납품처</b> ${esc(j.cnm||j.cc)}
      <b>세트납품서</b> ${esc(j.sheet_no)}
      ${j.barcode?`<b>바코드</b> SET${esc(j.barcode)}`:''}
      <b>납품일자</b> ${esc(d6(j.ymd))} ${esc(hm(j.hms))}</div>
    <table><thead><tr>
      <th style="width:36px">No</th><th>도번</th><th>품명</th><th>규격</th>
      <th style="width:64px">세트수량</th><th>자도번</th><th>자재품명</th>
      <th style="width:52px">사용</th><th style="width:64px">자재수량</th>
    </tr></thead><tbody>
    ${(j.rows||[]).map((x,i)=>`<tr>
      <td class="c">${i+1}</td><td>${esc(x.doban)}</td><td>${esc(x.dnm||'')}</td>
      <td>${esc(x.dspec||'')}</td><td class="n">${num(x.set_qty)}</td>
      <td>${esc(x.jadoban||'')}</td><td>${esc(x.jnm||'')}</td>
      <td class="n">${num(x.use_qty)}</td><td class="n">${num(x.mat_qty)}</td>
    </tr>`).join('')}
    </tbody><tfoot><tr>
      <td colspan="4" class="c">합계 (${j.cnt}건)</td><td class="n">${num(j.sum_set)}</td>
      <td colspan="3"></td><td class="n">${num(j.sum_mat)}</td>
    </tr></tfoot></table></div>`;

  const draw=()=>{
    c.innerHTML=`
     <div style="display:flex;flex-direction:column;height:100%;min-height:0">
     <div class="page-title">📝 거래명세표 수정 <span style="font-size:12px;color:var(--muted);font-weight:400">세트납품 내역 수정·삭제·재출력 · nx</span></div>
     <div class="page-sub">세트납품서 단위 납품내역. <b>입고완료건은 조회·출력만 가능</b>(수정·삭제 불가) — 레거시 <code>w_pr_outside_030_new</code> 동일. 원천 <code>nx.set_input_req</code>(웹 발행분)</div>
     <div class="toolbar">
       <label class="tl">납품기간</label>
       <input type="date" class="inp" id="de-fr" value="${esc(fr)}" style="width:150px">
       <span class="mut">~</span>
       <input type="date" class="inp" id="de-to" value="${esc(to)}" style="width:150px">
       <label class="tl">자도번작업처</label>
       <input class="inp" id="de-cu" list="de-cul" value="${esc(cust)}" placeholder="거래처명/코드" style="width:170px">
       <datalist id="de-cul">${custs.map(x=>`<option value="${esc(x.nm)}">${esc(x.cc)}</option>`).join('')}</datalist>
       <label class="tl">도번</label>
       <input class="inp" id="de-do" list="de-dol" value="${esc(doban)}" placeholder="도번/품명" style="width:140px">
       <datalist id="de-dol">${dobans.map(x=>`<option value="${esc(x.code)}">${esc(x.nm||'')}</option>`).join('')}</datalist>
       <label class="tl">자도번</label>
       <input class="inp" id="de-ja" list="de-jal" value="${esc(jado)}" placeholder="자도번/품명" style="width:140px">
       <datalist id="de-jal">${jados.map(x=>`<option value="${esc(x.code)}">${esc(x.nm||'')}</option>`).join('')}</datalist>
       <button class="btn" id="de-go">🔍 조회</button>
     </div>
     <!-- ★출력구분은 둘째 줄로(2026-08-31) — 조회줄 끝에 붙이면 오른쪽이 잘려 안 보인다 -->
     <div class="toolbar" style="padding-top:0">
       <label class="tl">출력구분</label>
       <label class="ck"><input type="checkbox" id="de-o1" ${outStmt?'checked':''}> 거래명세서</label>
       <label class="ck"><input type="checkbox" id="de-o2" ${outTag?'checked':''}> 입고태그</label>
       <label class="ck"><input type="checkbox" id="de-o3" ${outInsp?'checked':''}> 출하검사성적서</label>
       <div class="spacer"></div>
       <span class="rowcount">${cnt}건 · 납품서 ${sheets} · 수정가능 <b>${editable}</b></span>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="grid-wrap de-wrap"><table class="tbl de-tbl">
      <thead><tr>
        <th style="width:74px">납품일자</th><th style="width:66px">납품일시</th>
        <th style="width:86px">세트납품서번호</th><th style="width:96px">바코드번호</th>
        <th style="width:110px">업체</th><th style="width:124px">도번</th>
        <th style="width:64px">세트수량</th><th style="width:70px">입고완료</th>
        <th style="width:38px">당일</th><th style="width:140px">자도번</th>
        <th style="width:62px">사용수량</th><th style="width:64px">자재수량</th>
        <th style="width:180px">처리</th>
      </tr></thead>
      <tbody>${loading?spinRow(13):(rows.length?rows.map(r=>{
        const f=r.first, done=r.cf==='1';
        return `<tr class="${f?'de-first':''} ${done?'de-done':''}">
        ${f?`<td class="c" rowspan="${r.span}">${esc(d6(r.ymd))}</td>
             <td class="c" rowspan="${r.span}">${esc(hm(r.hms))}</td>
             <!-- ★납품서번호는 숫자만 · 바코드번호만 SET 접두(2026-08-31 사용자 확정).
                  둘 다 SET 을 붙여 보여주다 같은 번호로 오해됐다(901208 ↔ SET700010). -->
             <td class="c" rowspan="${r.span}">${esc(r.sheet_no)}</td>
             <td class="c" rowspan="${r.span}"><b>${r.barcode?'SET'+esc(r.barcode):'<span style="color:#b8c0cc">-</span>'}</b></td>
             <td rowspan="${r.span}" title="${esc(r.cc||'')}">${esc(r.cnm||r.cc||'')}</td>
             <td rowspan="${r.span}" title="${esc(r.dnm||'')}"><b>${esc(r.doban)}</b></td>
             <td class="n" rowspan="${r.span}">${num(r.set_qty)}</td>`:''}
        <td class="c">${done?'<span class="de-bd on">입고완료</span>':'<span class="de-bd">미입고</span>'}</td>
        <td class="c">${esc(r.am_pm||'')}</td>
        <td title="${esc(r.jnm||'')}">${esc(r.jadoban||'')}</td>
        <td class="n">${num(r.use_qty)}</td>
        <td class="n">${num(r.mat_qty)}</td>
        ${f?`<td class="c" rowspan="${r.span}" style="white-space:nowrap">
          <button class="btn de-mini de-ed" data-i="${rows.indexOf(r)}" ${(done||!canW)?'disabled':''} title="${done?'입고완료건은 조회만 가능합니다':'납품수량 수정'}">✎ 수정</button>
          <button class="btn de-mini de-dl" data-i="${rows.indexOf(r)}" ${(done||!canW)?'disabled':''} title="${done?'입고완료건은 조회만 가능합니다':'삭제(발행이력까지 회수)'}">🗑 삭제</button>
          <button class="btn de-mini de-pr" data-i="${rows.indexOf(r)}" title="선택한 출력구분으로 인쇄">🖨 출력</button>
        </td>`:''}
      </tr>`;}).join('')
        :`<tr><td colspan="12" class="empty">조회 결과 없음</td></tr>`)}</tbody>
     </table></div>
     </div>
     <style>
       .de-wrap{flex:0 1 auto;min-height:0;max-height:100%;overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px;box-shadow:0 3px 12px rgba(30,45,70,.08)}
       .de-tbl{font-size:12px;white-space:nowrap;width:100%}
       .de-tbl th,.de-tbl td{padding:3px 6px;border-bottom:1px solid #e6ecf5}
       .de-tbl thead th{position:sticky;top:0;background:#dbe6f5;z-index:2;border-bottom:1px solid #9db4d4;text-align:center}
       .de-tbl td.n{text-align:right;font-variant-numeric:tabular-nums}
       .de-tbl td.c{text-align:center}
       .de-tbl tr.de-first td{border-top:1px solid #b9cbe4}
       .de-tbl tbody tr:hover td{background:#eaf2fd}
       .de-tbl tr.de-done td{background:#f7f9f7}
       .de-tbl tr.de-done:hover td{background:#eef4ee}
       .de-bd{font-size:11px;padding:1px 7px;border-radius:10px;background:#eee;color:#777}
       .de-bd.on{background:#e5f3e8;color:#2e7d32;font-weight:700}
       /* ★처리 버튼 — 파란 아이콘 3개가 구분이 안 돼 역할별 색·라벨로 분리(2026-08-31) */
       .de-mini{padding:2px 7px;font-size:11px;margin-right:3px;border-radius:4px;font-weight:600}
       .de-tbl .de-ed{background:#eaf2fd;border:1px solid #9dc0e8;color:#1c47a0}
       .de-tbl .de-dl{background:#fdeceb;border:1px solid #e8a9a4;color:#c0392b}
       .de-tbl .de-pr{background:#f2f4f7;border:1px solid #c3ccd8;color:#455}
       .de-tbl .de-ed:hover:not(:disabled){background:#dbe9fb}
       .de-tbl .de-dl:hover:not(:disabled){background:#fbdcda}
       .de-tbl .de-pr:hover:not(:disabled){background:#e6eaf0}
       .de-tbl .de-mini:disabled{background:#f5f6f8;border-color:#dde2e8;color:#b8c0cc;font-weight:400}
       .ck{display:inline-flex;align-items:center;gap:3px;font-size:12px;color:#445;margin-right:2px}
     </style>`;
    const g=(id)=>c.querySelector(id);
    // 기간·거래처가 바뀌면 도번/자도번 후보를 그 범위로 다시 채운다(포커스 유지 위해 부분갱신)
    const refill=async()=>{await loadItems();
      const dl=g('#de-dol'), jl=g('#de-jal');
      if(dl)dl.innerHTML=dobans.map(x=>`<option value="${esc(x.code)}">${esc(x.nm||'')}</option>`).join('');
      if(jl)jl.innerHTML=jados.map(x=>`<option value="${esc(x.code)}">${esc(x.nm||'')}</option>`).join('');};
    g('#de-fr').onchange=e=>{fr=e.target.value;refill();};
    g('#de-to').onchange=e=>{to=e.target.value;refill();};
    const cu=g('#de-cu');
    cu.oninput=e=>{cust=e.target.value;};
    cu.onchange=e=>{cust=e.target.value;refill();};   // 목록에서 고르면 후보 재구성
    cu.onkeyup=e=>{if(e.key==='Enter')load();};
    const dv=g('#de-do');dv.oninput=e=>{doban=e.target.value;};
    dv.onchange=e=>{doban=e.target.value;};
    dv.onkeyup=e=>{if(e.key==='Enter')load();};
    const jv=g('#de-ja');jv.oninput=e=>{jado=e.target.value;};
    jv.onchange=e=>{jado=e.target.value;};
    jv.onkeyup=e=>{if(e.key==='Enter')load();};
    g('#de-go').onclick=()=>load();
    g('#de-o1').onchange=e=>{outStmt=e.target.checked;};
    g('#de-o2').onchange=e=>{outTag=e.target.checked;};
    g('#de-o3').onchange=e=>{outInsp=e.target.checked;};
    c.querySelectorAll('.de-ed').forEach(b=>b.onclick=()=>editQty(rows[+b.dataset.i]));
    c.querySelectorAll('.de-dl').forEach(b=>b.onclick=()=>delRow(rows[+b.dataset.i]));
    c.querySelectorAll('.de-pr').forEach(b=>b.onclick=()=>doPrint(rows[+b.dataset.i]));
  };

  draw();
  Promise.all([loadCusts(),loadItems()]).then(()=>{draw();load();});
};


/* ==== 자재세트 3화면 (레거시 자재관리 메뉴) — 2026-08-29 신설 착수 ====
   자재세트입고관리(setstock)는 기존 화면. 아래 3개를 순차 구현한다. */
const _setSoon=(c,title,legacy,note)=>{
  c.innerHTML=`
   <div style="display:flex;flex-direction:column;height:100%;min-height:0">
   <div class="page-title">${title} <span style="font-size:12px;color:var(--muted);font-weight:400">준비중 · nx</span></div>
   <div class="page-sub">레거시 <code>${esc(legacy)}</code> 이식 예정. ${esc(note||'')}</div>
   <div class="grid-wrap" style="flex:0 1 auto;max-height:100%;overflow:auto;background:#fff;
        border:1px solid var(--line-2,#c9d3e0);border-radius:8px;padding:28px;text-align:center;color:#8aa0bd">
     화면 구성 작업 중입니다.
   </div>
   </div>`;
};
/* ==== 자재세트입고현황 (레거시 w_pr_input_130_part) — 2026-08-30 신설 ====
   ★자재입고진행현황(010)과 같은 구조. 차이는 행단위=도번(세트)·재고=세트재고.
     자도번은 'LIST' 로 콤마 나열. 협력사가 자기 세트 납품계획을 보는 화면.
   구분 3종: 전체(집계+상세, 클릭 펼침) / 집계 / 제번.
   ※「자재세트바코드입고」 버튼 없음 — 입고관리 화면에 이미 있음(사용자 지정). */
SCREEN.setinstat=(c)=>{
  const API=API_BASE;
  const num=n=>(+n||0).toLocaleString();
  const p2=n=>String(n).padStart(2,'0');
  const iso=d=>`${d.getFullYear()}-${p2(d.getMonth()+1)}-${p2(d.getDate())}`;
  const d2y=v=>v?v.slice(2).replace(/-/g,''):'';
  const DOW=['일','월','화','수','목','금','토'];
  const dlabel=y=>{
    const dt=new Date(+('20'+y.slice(0,2)),+y.slice(2,4)-1,+y.slice(4,6));
    return y.slice(4,6)+DOW[dt.getDay()];
  };
  const now=new Date();

  let st={ymd:iso(now),days:4,gubun:'all',jcust:'',jcustnm:'',line:'',
          wo:'',doban:'',jadoban:'',
          axis:[],all:[],rows:[],open:{},loading:false,tot:{}};
  let custMap={};

  c.innerHTML=`
   <style>
    #si2 table.grid{border-collapse:collapse;table-layout:auto}
    #si2 table.grid th,#si2 table.grid td{
      text-align:center;border:1px solid #b9c8da;padding:2px 5px;white-space:nowrap}
    #si2 table.grid thead th{background:#dce9f7;color:#24405f;font-weight:600;
      position:sticky;top:0;z-index:2;border-bottom:2px solid #8fa9c6}
    #si2 table.grid tbody tr:nth-child(even){background:#fafcfe}
    #si2 .num{font-variant-numeric:tabular-nums;text-align:right}
    #si2 .sum{background:#dbe7f5 !important;font-weight:600;cursor:pointer}
    #si2 .sum:hover{background:#cfe0f3 !important}
    /* ★근무일 칸에 배경색을 주지 않는다 — 충당 색상(살/노랑/회색)과 혼동된다.
       색은 오직 충당 결과로만 붙는다(2026-08-30 교정). */
    #si2 .day{}
    #si2 .day0{background:#f3f5f8;color:#aab6c4}   /* 휴무일 칸만 옅은 회색 */
    /* ★충당 색상 — PBL 원문 상수 그대로(partnererp.sra).
         gl_color_sale       rgb(250,192,144)  살구
         gl_color_prod_all   rgb(255,255,0)    노랑
         gl_color_mat_all    rgb(192,192,192)  밝은회색
         gl_color_prod_ready rgb(102,153,0)    진초록  ★130 전용
       ※gl_color_mat_part(진회색)은 010 전용 — 130 소스에 등장 0회. 쓰지 않는다. */
    #si2 .c-sale {background:#fac090 !important;font-weight:700}  /* 출하 */
    #si2 .c-prod {background:#ffff00 !important;font-weight:700}  /* ASSY(생산) */
    #si2 .c-mat  {background:#c0c0c0 !important;font-weight:600}  /* 세트·자재 */
    #si2 .c-ready{background:#669900 !important;color:#fff;font-weight:700} /* 생산준비 */
    #si2 .lft{text-align:left}
    /* 자도번작업처 = 이 화면의 주 조건 컬럼 — 옅게 강조 */
    #si2 .jc-col{background:#f2f7fd;color:#1c4e80;font-weight:600}
    #si2 .cap{max-width:260px;overflow:hidden;text-overflow:ellipsis}
   </style>
   <div id="si2" style="display:flex;flex-direction:column;height:100%;min-height:0">
    <div class="page-title">📋 자재세트입고현황
      <span style="font-size:12px;color:var(--muted);font-weight:400">레거시 w_pr_input_130_part · 세트재고 기준</span></div>

    <div class="toolbar" style="flex:0 0 auto;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <label>기준일자 <input type="date" class="inp" id="s2-ymd" value="${st.ymd}" style="width:145px"></label>
      <label>기간 <select class="inp" id="s2-days" style="width:80px">
        ${[1,2,3,4,5,6,7,10,14].map(n=>`<option value="${n}"${n===4?' selected':''}>${n}일</option>`).join('')}
      </select></label>
      <span style="display:inline-flex;gap:9px;align-items:center;padding:2px 10px;
            border:1px solid var(--line-2,#c9d3e0);border-radius:6px">
        <b style="font-size:12px;color:#5a6b82">구분</b>
        <label><input type="radio" name="s2g" value="all" checked> 전체</label>
        <label><input type="radio" name="s2g" value="sum"> 집계</label>
        <label><input type="radio" name="s2g" value="wo"> 제번</label>
      </span>
      <label style="display:inline-flex;align-items:center;gap:5px;padding:2px 8px;border-radius:6px;
             background:#eaf3ff;border:1px solid #9dc0e8">
        <b style="font-size:12px;color:#1c4e80">자도번작업처</b>
        <input class="inp" id="s2-jc" list="s2-custs"
               placeholder="거래처명 일부(예: 대원)" style="width:180px;min-width:0"></label>
      <datalist id="s2-custs"></datalist>
      <span id="s2-cc" style="font-size:12px;font-weight:600;color:#5a6b82"></span>
      <label>제번 <input class="inp" id="s2-wo" placeholder="제번" style="width:110px"></label>
      <label>도번 <input class="inp" id="s2-db" placeholder="도번" style="width:120px"></label>
      <label>자도번 <input class="inp" id="s2-jd" placeholder="자도번" style="width:120px"></label>
      <button class="btn primary" id="s2-go">🔍 조회</button>
      <span style="font-size:11px;color:#8aa0bd">제번·도번·자도번은 입력 즉시 필터</span>
      <button class="btn" id="s2-xl">엑셀</button>
      <span id="s2-msg" style="color:var(--muted);font-size:12px"></span>
    </div>

    <div style="flex:1;min-height:0;overflow:auto;margin-top:8px;background:#fff;
                border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="grid" id="s2-t" style="width:100%">
        <thead id="s2-h"></thead><tbody id="s2-b"></tbody><tfoot id="s2-f"></tfoot></table>
    </div>
   </div>`;

  const $=id=>c.querySelector(id);
  const msg=t=>{$('#s2-msg').textContent=t||'';};

  const pickCust=v=>{
    const nm=String(v||'').trim();
    if(!nm){st.jcustnm='';st.jcust='';return '';}
    if(custMap[nm]){st.jcustnm=nm;st.jcust=custMap[nm];return '';}
    const keys=Object.keys(custMap);
    const byCode=keys.filter(k=>custMap[k]===nm);
    if(byCode.length===1){st.jcustnm=byCode[0];st.jcust=nm;return '';}
    const hit=keys.filter(k=>k.indexOf(nm)>=0);
    if(hit.length===1){st.jcustnm=hit[0];st.jcust=custMap[hit[0]];return '';}
    if(hit.length>1){
      const ex=hit.filter(k=>k.startsWith(nm));
      if(ex.length===1){st.jcustnm=ex[0];st.jcust=custMap[ex[0]];return '';}
      st.jcustnm=nm;st.jcust='';
      return '후보 '+hit.length+'건 — '+hit.slice(0,5).join(' / ');
    }
    st.jcustnm=nm;st.jcust='';return '일치하는 거래처가 없습니다.';
  };

  /* 집계 = 작업처+라인+도번 (레거시 집계행 단위) */
  const groupKey=r=>[r.jcust,r.line,r.doban].join('|');

  /* ★로컬 필터 — 제번·도번·자도번은 서버 재조회 없이 즉시 걸린다.
     도번칸은 도번/자도번 어느 쪽을 쳐도 잡는다(레거시 운용 동일). */
  const applyLocal=()=>{
    const up=v=>String(v||'').trim().toUpperCase();
    const fw=up(st.wo), fd=up(st.doban), fj=up(st.jadoban), fc=String(st.jcust||'').trim();
    st.rows=(st.all||[]).filter(r=>{
      // ★거래처 이중안전 — 서버 파라미터가 비어도 화면에선 확실히 걸린다
      if(fc && String(r.jcust||'').trim()!==fc) return false;
      if(fw && up(r.wo).indexOf(fw)<0) return false;
      if(fd && up(r.doban).indexOf(fd)<0 && up(r.jadolist).indexOf(fd)<0) return false;
      if(fj && up(r.jadolist).indexOf(fj)<0) return false;
      return true;
    });
    // 합계 재계산
    const T={day:{},lot:0,mat:0,prod:0,sale:0};
    (st.axis||[]).forEach(a=>{T.day[a.ymd]=0;});
    st.rows.forEach(r=>{
      (st.axis||[]).forEach(a=>{T.day[a.ymd]+=(r.day[a.ymd]||0);});
      T.lot+=+r.lot||0; T.mat+=+r.mat_qty||0; T.prod+=+r.prod||0; T.sale+=+r.sale||0;
    });
    st.tot=T; st.open={};
    draw();
    msg(num(st.rows.length)+'건'+((fw||fd||fj)?` / 전체 ${num((st.all||[]).length)}`:''));
  };

  const draw=()=>{
    const A=st.axis||[];
    const dayTh=A.map(a=>`<th style="width:66px" class="${a.work?'day':'day0'}">${dlabel(a.ymd)}</th>`).join('');
    $('#s2-h').innerHTML=`<tr>
      <th style="width:40px">SEQ</th><th style="width:110px">자도번작업처</th>
      <th style="width:60px">라인</th><th style="width:70px">LG INPUT</th>
      <th style="width:100px">제번</th><th style="width:110px">작업처</th>
      <th style="width:130px">도번</th><th style="width:240px">자도번LIST</th>
      <th style="width:60px">사급</th><th style="width:80px">제번정보</th>
      <th style="width:80px">품목정보</th><th style="width:70px">당김,변경</th>
      <th style="width:70px">비고1</th>
      ${dayTh}
      <th style="width:70px">LOT수량</th><th style="width:70px">자재수량</th>
      <th style="width:70px">자재입고</th><th style="width:70px">요청수량</th>
      <th style="width:70px">생산실적</th><th style="width:70px">출하실적</th>
      <th style="width:78px">세트재고</th><th style="width:70px">단품재고</th>
      <th style="width:70px">ASSY재고</th><th style="width:150px">모델</th></tr>`;

    if(!st.rows.length){
      $('#s2-b').innerHTML=`<tr><td colspan="${24+A.length}" style="padding:24px;color:#8aa0bd">
        ${st.loading?'조회중…':'조회된 자료가 없습니다.'}</td></tr>`;
      $('#s2-f').innerHTML=''; return;
    }

    // 집계 묶기
    const grp=new Map();
    st.rows.forEach(r=>{
      const k=groupKey(r);
      let g=grp.get(k);
      if(!g){g={key:k,head:r,kids:[],day:{},lot:0,mat:0,min:0,req:0,prod:0,sale:0};grp.set(k,g);}
      g.kids.push(r);
      A.forEach(a=>{g.day[a.ymd]=(g.day[a.ymd]||0)+(r.day[a.ymd]||0);});
      g.lot+=+r.lot||0; g.mat+=+r.mat_qty||0; g.min+=+r.mat_in||0;
      g.req+=+r.req||0; g.prod+=+r.prod||0; g.sale+=+r.sale||0;
      g.sagub=(g.sagub||0)+(+r.sagub||0);
    });

    /* ★색상 — 자재입고진행현황(010)과 동일 규칙.
       살(주황)=출하실적 / 노랑=ASSY·도번고정 / 회색=생산·자재(세트) / 무색=일부·미충당.
       충당순서대로 재고를 깎고, 그 일자 소요가 '전량' 덮인 재고로만 색을 준다.
       전량 아니면 무색 + a/b 표기(레거시 동일). */
    // 등급(낮을수록 상위) — 노랑(생산) > 살(출하) > 회색(재고). 섞이면 하위색 채택.
    /* ★색상 — PBL 원문(w_pr_input_130_part.srw) 그대로. 010 과 규칙이 다르다.
         ① 출하 sale_qty     전량 → 살구(fin 6) / 일부 → 색 없음
         ② ASSY assy_stock   전량 → 노랑(fin 4) / 일부 → ★WHITE 강제(색 지움)
         ③ 세트 set_stock    전량 → 밝은회색(fin 2) / 일부 → 색 없음(fin 1)
         ④ 자재 mat_stock    전량 → 밝은회색(fin 2) / 일부 → 색 없음(fin 1)
         ⑤ 생산준비 ready    전량 & 기존 fin='1' → ★진초록(fin 1→2 승격)  ※130 전용
       ⛔gl_color_mat_part(진회색, 010 의 '자재 일부충당' 색)은 130 소스에 0회 — 쓰지 않는다.
       셀 텍스트 = (input_qty+finish_qty)/plan_qty, 충당 0 이면 계획수량만. */
    const calcFill=()=>{
      const P={sale:{},assy:{},set:{},mat:{},ready:{}};
      st.rows.forEach(x=>{
        const ks=x.wo+'|'+x.doban;
        if(P.sale[ks]===undefined)P.sale[ks]=(+x.sale||0);
        if(P.assy[x.doban]===undefined)P.assy[x.doban]=(+x.assy_stock||0);
        if(P.set[x.doban]===undefined)P.set[x.doban]=(+x.set_stock||0);
        if(P.mat[x.doban]===undefined)P.mat[x.doban]=(+x.dan_stock||0);
        if(P.ready[x.doban]===undefined)P.ready[x.doban]=(+x.ready||0);
      });
      const fill={};
      (st.axis||[]).forEach(a=>{
        st.rows.forEach(r=>{
          const need=r.day[a.ymd]||0;
          if(!need)return;
          const key=r.wo+'#'+r.doban+'#'+a.ymd;
          const ks=r.wo+'|'+r.doban, kd=r.doban;
          let left=need, done=0, cls='', fin='';

          // ① 출하 — 전량일 때만 살구
          if(left>0 && (P.sale[ks]||0)>0){
            if(P.sale[ks]>=left){P.sale[ks]-=left;done+=left;left=0;cls='c-sale';fin='6';}
          }
          // ② ASSY — 전량 노랑 / 일부는 채우되 WHITE(색 지움)
          if(left>0 && (P.assy[kd]||0)>0){
            if(P.assy[kd]>=left){P.assy[kd]-=left;done+=left;left=0;cls='c-prod';fin='4';}
            else{done+=P.assy[kd];left-=P.assy[kd];P.assy[kd]=0;cls='';fin='0';}
          }
          // ③ 세트재고 — 전량 밝은회색 / 일부는 색 없음(fin 1)
          if(left>0 && (P.set[kd]||0)>0){
            if(P.set[kd]>=left){P.set[kd]-=left;done+=left;left=0;cls='c-mat';fin='2';}
            else{done+=P.set[kd];left-=P.set[kd];P.set[kd]=0;fin='1';}
          }
          // ④ 자재재고 — 이 화면은 세트재고 기준이라 단품재고 0 고정(대표 확정).
          //    레거시 130 의 '세트입고제외품 자재재고' 단계는 제외조건 확정 후 붙인다.
          // ⑤ ★생산준비 — fin='1'(일부충당) 상태에서 그날 계획을 전량 커버하면 진초록
          if(fin==='1' && (P.ready[kd]||0)>=need){
            P.ready[kd]-=need; cls='c-ready'; fin='2';
          }
          fill[key]={done,need,cls};
        });
      });
      return fill;
    };
    // 소계 색 등급(낮을수록 상위) — 살구 > 노랑 > 진초록 > 밝은회색
    const RK={'c-sale':0,'c-prod':1,'c-ready':2,'c-mat':3};
    const RV=['c-sale','c-prod','c-ready','c-mat'];
    const FL=calcFill();
    const cellOf=(r,a)=>{
      const need=r.day[a.ymd]||0;
      if(!need) return `<td class="${a.work?'':'day0'}"></td>`;
      const f=FL[r.wo+'#'+r.doban+'#'+a.ymd]||{done:0,need,cls:''};
      // ★레거시 DW expression 그대로:
      //   if(충당>0, string(충당) + '/', '') + string(계획)
      //   → 충당분이 있으면 a/b, 없으면 계획수량만. 색과 무관하다.
      const txt=f.done>0?`${num(f.done)}/${num(need)}`:num(need);
      return `<td class="num ${f.cls||(a.work?'':'day0')}">${txt}</td>`;
    };
    const cell=cellOf;
    /* ★재고는 도번당 하나 — 같은 도번이 여러 행이면 첫 행에만 표시한다.
       (행마다 반복 찍히면 재고가 여러 개인 것처럼 보인다) */
    const seenStock=new Set();
    const tail=(r,isSum)=>{
      const k=r.doban;
      let show=true;
      if(!isSum){ if(seenStock.has(k))show=false; else seenStock.add(k); }
      return `
      <td class="num">${r.lot?num(r.lot):''}</td>
      <td class="num">${r.mat_qty?num(r.mat_qty):''}</td>
      <td class="num">${r.mat_in?num(r.mat_in):''}</td>
      <td class="num">${r.req?num(r.req):''}</td>
      <td class="num">${r.prod?num(r.prod):''}</td>
      <td class="num">${r.sale?num(r.sale):''}</td>
      <td class="num" style="color:${r.set_stock<0?'#c0392b':'#1f7a3d'};font-weight:600">${(show&&r.set_stock)?num(r.set_stock):''}</td>
      <td class="num">${(show&&r.dan_stock)?num(r.dan_stock):''}</td>
      <td class="num">${(show&&r.assy_stock)?num(r.assy_stock):''}</td>
      <td class="lft cap" title="${esc(r.model||'')}">${esc(r.model||'')}</td>`;
    };

    let h=''; let seq=0;
    grp.forEach(g=>{
      const r=g.head, op=(st.gubun==='all')&&(st.open[g.key]!==false);
      // ★레거시 동일 — 상세가 먼저, 소계는 그 '아래'(클릭하면 위로 펼쳐진다)
      if(st.gubun==='wo'||(st.gubun==='all'&&op)){
        g.kids.forEach(k=>{
          seq++;
          h+=`<tr><td>${seq}</td><td class="lft jc-col">${esc(k.jcust_nm)}</td>
            <td>${esc(k.line)}</td><td>${esc(k.hm)}</td><td>${esc(k.wo)}</td>
            <td title="${esc(k.gpc)}">${esc(k.gpc_nm||k.gpc)}</td><td>${esc(k.doban)}</td>
            <td class="lft cap" title="${esc(k.jadolist)}">${esc(k.jadolist)}</td>
            <td>${k.sagub?num(k.sagub):''}</td><td></td><td></td>
            <td>${k.pull?esc(k.pull):''}</td><td></td>
            ${A.map(a=>cell(k,a)).join('')}${tail(k)}</tr>`;
        });
      }
      if(st.gubun!=='wo'){
        h+=`<tr class="sum" data-k="${esc(g.key)}">
          <td>${st.gubun==='all'?(op?'▲':'▼'):''}</td>
          <td class="lft jc-col">${esc(r.jcust_nm)}</td><td>${esc(r.line)}</td><td></td><td></td>
          <td title="${esc(r.gpc)}">${esc(r.gpc_nm||r.gpc)}</td><td><b>${esc(r.doban)}</b></td>
          <td class="lft cap" title="${esc(r.jadolist)}">${esc(r.jadolist)}</td>
          <td>${g.sagub?num(g.sagub):''}</td><td></td><td></td><td></td><td></td>
          ${A.map(a=>{
            const v=g.day[a.ymd]||0;
            if(!v)return `<td class="${a.work?'':'day0'}"></td>`;
            // 소계 색 = 자식이 **전부 색**일 때만, 그중 가장 낮은 등급(010 동일).
            //   하나라도 무색이면 소계도 무색.
            let cls=null, done=0;
            for(const k of g.kids){
              const nd=k.day[a.ymd]||0; if(!nd)continue;
              const f=FL[k.wo+'#'+k.doban+'#'+a.ymd]||{done:0,cls:''};
              done+=f.done;
              if(!f.cls){cls='';}
              else if(cls!==''){cls=(cls==null)?f.cls:RV[Math.max(RK[cls],RK[f.cls])];}
            }
            const c=cls||'';
            return `<td class="num ${c||(a.work?'':'day0')}">${done>0?(num(done)+'/'+num(v)):num(v)}</td>`;
          }).join('')}
          <td class="num">${g.lot?num(g.lot):''}</td><td class="num">${g.mat?num(g.mat):''}</td>
          <td class="num">${g.min?num(g.min):''}</td><td class="num">${g.req?num(g.req):''}</td>
          <td class="num">${g.prod?num(g.prod):''}</td><td class="num">${g.sale?num(g.sale):''}</td>
          <td class="num" style="color:${r.set_stock<0?'#c0392b':'#1f7a3d'};font-weight:600">${r.set_stock?num(r.set_stock):''}</td>
          <td class="num">${r.dan_stock?num(r.dan_stock):''}</td>
          <td class="num">${r.assy_stock?num(r.assy_stock):''}</td>
          <td class="lft cap" title="${esc(r.model||'')}">${esc(r.model||'')}</td></tr>`;   /* 소계는 항상 표시 */
      }
    });
    $('#s2-b').innerHTML=h;

    const T=st.tot||{};
    $('#s2-f').innerHTML=`<tr style="background:#dbe7f5;font-weight:600;position:sticky;bottom:0">
      <td colspan="13">합계 ${num(st.rows.length)}건 · 집계 ${num(grp.size)}</td>
      ${A.map(a=>`<td class="num">${num((T.day||{})[a.ymd]||0)}</td>`).join('')}
      <td class="num">${num(T.lot||0)}</td><td class="num">${num(T.mat||0)}</td>
      <td colspan="2"></td>
      <td class="num">${num(T.prod||0)}</td><td class="num">${num(T.sale||0)}</td>
      <td colspan="4"></td></tr>`;

    c.querySelectorAll('#s2-b tr.sum').forEach(tr=>{
      tr.onclick=()=>{ if(st.gubun!=='all')return;
        const k=tr.dataset.k; st.open[k]=(st.open[k]===false); draw(); };
    });
  };

  const load=async()=>{
    // ★조회 직전 입력칸을 다시 읽어 거래처를 확정한다.
    //   (onblur 가 안 걸린 채 조회를 누르면 st.jcust 가 비어 전체조회가 되던 문제)
    const cv=$('#s2-jc').value.trim();
    if(cv){ const w=pickCust(cv); showCust(w);
      if(!st.jcust){ msg(w||'거래처를 확인하세요.'); return; }
    } else { st.jcust=''; st.jcustnm=''; showCust(''); }
    st.wo=$('#s2-wo').value.trim(); st.doban=$('#s2-db').value.trim();
    st.jadoban=$('#s2-jd').value.trim();
    st.loading=true; draw(); msg('조회중…');
    try{
      // ★제번·도번·자도번은 서버에 보내지 않는다 — 전체를 받아 로컬에서 즉시 필터.
      const q=new URLSearchParams({base_ymd:d2y(st.ymd),days:st.days,jcust:st.jcust});
      const d=await fetch(`${API}/api/setinstat/list?`+q).then(x=>x.json());
      st.axis=d.axis||[]; st.all=d.rows||[]; st.rows=st.all; st.open={};
      st.tot={day:d.tot_day||{},lot:d.tot_lot||0,mat:d.tot_mat||0,
              prod:d.tot_prod||0,sale:d.tot_sale||0};
      st.loading=false;
      applyLocal();          // 입력칸에 값이 있으면 즉시 반영
      return;
    }catch(e){ st.all=[]; st.rows=[]; msg('오류: '+e); }
    st.loading=false; draw();
  };

  $('#s2-ymd').onchange=e=>{st.ymd=e.target.value;};
  $('#s2-days').onchange=e=>{st.days=+e.target.value;};
  c.querySelectorAll('input[name="s2g"]').forEach(r=>r.onchange=e=>{st.gubun=e.target.value;st.open={};draw();});
  const showCust=w=>{
    const e=$('#s2-cc'), inp=$('#s2-jc');
    if(!e||!inp)return;                       // 렌더 전 호출 방어
    if(st.jcust){
      e.textContent='✔ '+st.jcustnm+' ('+st.jcust+')';
      e.style.color='#1f7a3d';
      inp.style.background='#eafaef'; inp.style.borderColor='#7cc499';
    }else if(String(inp.value||'').trim()){
      e.textContent=w||'거래처를 확인하세요';
      e.style.color='#c0392b';
      inp.style.background='#fff5f5'; inp.style.borderColor='#e08b8b';
    }else{
      e.textContent='(전체)'; e.style.color='#8aa0bd';
      inp.style.background=''; inp.style.borderColor='';
    }
  };
  const applyCust=e=>{ showCust(pickCust(e.target.value)); };
  $('#s2-jc').onchange=applyCust; $('#s2-jc').onblur=applyCust;
  /* ★타이핑 즉시 필터(150ms 디바운스). 조회 버튼을 누를 필요가 없다. */
  let _ft=null;
  const onFilter=()=>{
    st.wo=$('#s2-wo').value.trim();
    st.doban=$('#s2-db').value.trim();
    st.jadoban=$('#s2-jd').value.trim();
    clearTimeout(_ft);
    _ft=setTimeout(()=>{ if(st.all&&st.all.length)applyLocal(); },150);
  };
  ['#s2-wo','#s2-db','#s2-jd'].forEach(id=>{
    $(id).oninput=onFilter;
    $(id).onkeydown=e=>{if(e.key==='Enter'){clearTimeout(_ft);
      if(st.all&&st.all.length)applyLocal(); else load();}};
  });
  $('#s2-go').onclick=load;
  $('#s2-xl').onclick=()=>{
    if(!st.rows.length)return alert('조회된 자료가 없습니다.');   // 화면에 보이는 것만
    const A=st.axis||[];
    const hd=['자도번작업처','라인','LG INPUT','제번','작업처','도번','자도번LIST','사급',
              ...A.map(a=>dlabel(a.ymd)),'LOT수량','자재수량','자재입고','요청수량',
              '생산실적','출하실적','세트재고','단품재고','ASSY재고','모델'];
    const bd=st.rows.map(r=>[r.jcust_nm,r.line,r.hm,r.wo,(r.gpc_nm||r.gpc),r.doban,r.jadolist,r.sagub||'',
              ...A.map(a=>r.day[a.ymd]||''),r.lot,r.mat_qty,r.mat_in,r.req,
              r.prod,r.sale,r.set_stock,r.dan_stock,r.assy_stock,r.model]);
    const csv='\ufeff'+[hd,...bd].map(r=>r.map(v=>`"${String(v??'').replace(/"/g,'""')}"`).join(',')).join('\r\n');
    const a=document.createElement('a');
    a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
    a.download='자재세트입고현황.csv'; a.click();
  };

  fetch(`${API}/api/setinstat/opts`).then(r=>r.json()).then(d=>{
    let h='';
    (d.custs||[]).forEach(x=>{ if(x.name&&x.code){custMap[x.name]=x.code;
      h+=`<option value="${esc(x.name)}">${esc(x.code)}</option>`;}});
    $('#s2-custs').innerHTML=h;
    // ★기준일자 = 계획 마지막 업로드 일자(오늘 아님).
    //   오늘로 잡으면 업로드일~오늘 사이 미처리분이 첫 칸에 뭉친다.
    if(d.base_ymd && String(d.base_ymd).length===6){
      const b=String(d.base_ymd);
      st.ymd='20'+b.slice(0,2)+'-'+b.slice(2,4)+'-'+b.slice(4,6);
      const el=$('#s2-ymd'); if(el)el.value=st.ymd;
    }
    load();                         // 기준일자 확정 후 최초 조회
  }).catch(()=>{ load(); });        // opts 실패해도 오늘 기준으로 조회

  // ★초기 조회는 opts 가 기준일자(계획 업로드일)를 준 뒤에 한다 — 중복조회 방지
  showCust(''); draw();
};
// ※자재세트재고현황은 입출고현황과 동일 내용이라 만들지 않는다(2026-08-29 사용자 확정)
/* ==== 자재세트재고입출고현황 (레거시 w_pu_stock_070) — 2026-08-30 신설 ====
   좌측 = 세트거래처x세트도번 잔액 / 우측 = 일자별 전일재고-입고-출고-재고.
   ★웹 정본 nx.set_stock_maint 단독. 출고=생산실적(세트도번 단위, use_qty 곱셈 없음 — 레거시 확인). */
SCREEN.setstockio=(c)=>{
  const API=API_BASE;
  const num=n=>(+n||0).toLocaleString();
  const ymd2d=s=>s&&s.length===6?('20'+s.slice(0,2)+'-'+s.slice(2,4)+'-'+s.slice(4,6)):'';
  const d2ymd=s=>s?s.slice(2).replace(/-/g,''):'';
  const dsp=s=>s&&s.length===6?(s.slice(0,2)+'/'+s.slice(2,4)+'/'+s.slice(4,6)):'';
  const today=new Date(), p2=n=>String(n).padStart(2,'0');
  const t1=today.getFullYear()+'-'+p2(today.getMonth()+1)+'-'+p2(today.getDate());
  const t0=today.getFullYear()+'-'+p2(today.getMonth()+1)+'-01';

  let rows=[], sel=null, cur=null;

  c.innerHTML=`
   <style>
    /* 레거시 w_pu_stock_070 풍 격자 — 전 셀 가운데 정렬 + 실선 구분 */
    #si-wrap table.grid{border-collapse:collapse;table-layout:fixed}
    #si-wrap table.grid th,#si-wrap table.grid td{
      text-align:center;border:1px solid #b9c8da;padding:3px 6px;
      white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    #si-wrap table.grid thead th{
      background:#dce9f7;color:#24405f;font-weight:600;
      position:sticky;top:0;z-index:2;border-bottom:2px solid #8fa9c6}
    #si-wrap table.grid tbody tr:nth-child(even){background:#f6f9fd}
    #si-wrap table.grid tbody tr:hover{background:#eaf2fb}
    #si-wrap .num{font-variant-numeric:tabular-nums}
    #si-wrap .si-sel{background:#e6d9f2 !important}
    #si-wrap .si-base{background:#efe4f7}
    #si-wrap .si-tot td{background:#dbe7f5;font-weight:600}
    #si-wrap .si-tot2 td{background:#e9f3e4;font-weight:600}
   </style>
   <div id="si-wrap" style="display:flex;flex-direction:column;height:100%;min-height:0">
    <div class="page-title">🔁 자재세트재고입출고현황
      <span style="font-size:12px;color:var(--muted);font-weight:400">웹 정본 nx.set_stock_maint</span></div>

    <div class="toolbar" style="flex:0 0 auto;display:flex;gap:14px;align-items:center;flex-wrap:wrap">
      <label>세트거래처 <input class="inp" id="si-cust" list="si-custs" placeholder="거래처명"
             style="width:150px;min-width:0"></label>
      <datalist id="si-custs"></datalist>
      <label>도번 <input class="inp" id="si-item" placeholder="도번"
             style="width:130px;min-width:0"></label>
      <span style="display:inline-flex;gap:10px;align-items:center;padding:2px 10px;
            border:1px solid var(--line-2,#c9d3e0);border-radius:6px">
        <b style="font-size:12px;color:#5a6b82">구분</b>
        <label><input type="radio" name="si-g" value="minus"> (-)재고</label>
        <label><input type="radio" name="si-g" value="plus" checked> (+)재고</label>
        <label><input type="radio" name="si-g" value="all"> 전체</label>
      </span>
      <label>조회기간 <input type="date" class="inp" id="si-f" value="${t0}" style="width:140px;min-width:0">
        ~ <input type="date" class="inp" id="si-t" value="${t1}" style="width:140px;min-width:0"></label>
      <button class="btn primary" id="si-go">조회</button>
      <button class="btn" id="si-xl">엑셀</button>
      <span id="si-msg" style="color:var(--muted);font-size:12px"></span>
    </div>

    <div style="flex:1;min-height:0;display:flex;gap:10px;margin-top:8px">
      <!-- 좌측 잔액 -->
      <div style="flex:0 0 640px;display:flex;flex-direction:column;min-height:0;
                  border:1px solid var(--line-2,#c9d3e0);border-radius:8px;background:#fff">
        <div style="flex:1;min-height:0;overflow:auto">
          <table class="grid" id="si-l" style="width:100%">
            <thead><tr>
              <th style="width:160px">거래처명</th><th style="width:170px">세트도번</th>
              <th style="width:100px">재고수량</th><th style="width:90px">담당</th>
              <th style="width:95px">거래처코드</th></tr></thead>
            <tbody id="si-lb"></tbody>
          </table>
        </div>
        <table class="grid si-tot" style="width:100%;flex:0 0 auto;border-top:2px solid #8fa9c6">
          <tbody><tr>
            <td style="width:160px"></td>
            <td style="width:170px" id="si-cnt">0건</td>
            <td style="width:100px" class="num" id="si-sum">0</td>
            <td style="width:90px"></td><td style="width:95px"></td></tr></tbody>
        </table>
      </div>

      <!-- 우측 이력 -->
      <div style="flex:1;display:flex;flex-direction:column;min-height:0;
                  border:1px solid var(--line-2,#c9d3e0);border-radius:8px;background:#fff">
        <div id="si-hd" style="flex:0 0 auto;padding:6px 10px;background:#eef4fb;
             border-bottom:1px solid var(--line-2,#c9d3e0);font-weight:600;font-size:13px;
             display:flex;justify-content:space-between">
          <span>품목 : —</span><span></span></div>
        <div style="flex:1;min-height:0;overflow:auto">
          <table class="grid" id="si-r" style="width:100%">
            <thead><tr>
              <th style="width:100px">대상일자</th>
              <th style="width:90px">전일재고</th>
              <th style="width:90px">입고수량</th>
              <th style="width:90px">출고수량</th>
              <th style="width:90px">재고수량</th>
              <th>비고</th></tr></thead>
            <tbody id="si-rb"><tr><td colspan="6" style="text-align:center;color:#8aa0bd;padding:24px">
              좌측에서 세트도번을 선택하세요.</td></tr></tbody>
          </table>
        </div>
        <table class="grid si-tot2" style="width:100%;flex:0 0 auto;border-top:2px solid #8fa9c6">
          <tbody><tr id="si-rt">
            <td style="width:100px"></td><td class="num" style="width:90px">0</td>
            <td class="num" style="width:90px">0</td><td class="num" style="width:90px">0</td>
            <td class="num" style="width:90px">0</td><td></td></tr></tbody>
        </table>
      </div>
    </div>
   </div>`;

  const $=id=>c.querySelector(id);
  const msg=t=>{$('#si-msg').textContent=t||'';};

  /* 거래처 오토컴플리트 (§3 — 이름으로 입력, 코드는 내부매핑) */
  let custMap={};
  fetch(API+'/api/base/partners?limit=3000').then(r=>r.json()).then(d=>{
    const ls=(d.rows||d.list||d||[]);
    const dl=$('#si-custs'); let h='';
    ls.forEach(x=>{const nm=(x.cust_name||x.name||'').trim(), cd=(x.cust_code||x.code||'').trim();
      if(!nm||!cd)return; custMap[nm]=cd; h+=`<option value="${esc(nm)}">${esc(cd)}</option>`;});
    dl.innerHTML=h;
  }).catch(()=>{});

  /* ── 좌측 */
  const drawL=()=>{
    const b=$('#si-lb');
    if(!rows.length){b.innerHTML=`<tr><td colspan="5" style="text-align:center;color:#8aa0bd;padding:24px">조회된 자료가 없습니다.</td></tr>`;}
    else{
      b.innerHTML=rows.map((r,i)=>`<tr data-i="${i}" style="cursor:pointer">
        <td title="${esc(r.cust_name)}">${esc(r.cust_name)}</td>
        <td title="${esc(r.item_name||'')}">${esc(r.item_code)}</td>
        <td class="num">${num(r.stock_qty)}</td>
        <td>${esc(r.user_id||'')}</td>
        <td>${esc(r.cust_code)}</td></tr>`).join('');
      b.querySelectorAll('tr').forEach(tr=>tr.onclick=()=>pick(+tr.dataset.i,tr));
    }
    $('#si-cnt').textContent=num(rows.length)+'건';
    $('#si-sum').textContent=num(rows.reduce((s,x)=>s+(+x.stock_qty||0),0));
  };

  /* ★행 클릭 = 부분갱신(스크롤 리셋 방지, §3) */
  const pick=(i,tr)=>{
    sel=i;
    c.querySelectorAll('#si-lb tr').forEach(x=>x.classList.remove('si-sel'));
    if(tr)tr.classList.add('si-sel');
    loadDetail(rows[i]);
  };

  const loadDetail=async r=>{
    cur=r;
    const f=d2ymd($('#si-f').value), t=d2ymd($('#si-t').value);
    $('#si-hd').innerHTML=`<span>품목 : <b>${esc(r.item_code)}</b> ${esc(r.item_name||'')}</span>
      <span style="font-weight:400;color:#5a6b82">FROM일자 : ${dsp(f)||'—'} &nbsp; TO일자 : ${dsp(t)||'99/99/99'}</span>`;
    $('#si-rb').innerHTML=`<tr><td colspan="6" style="text-align:center;color:#8aa0bd;padding:18px">조회중…</td></tr>`;
    try{
      const q=new URLSearchParams({item:r.item_code,cust:r.cust_code,frm:f,to:t});
      const d=await fetch(API+'/api/setstockio/detail?'+q).then(x=>x.json());
      const rs=d.rows||[];
      let h=`<tr class="si-base">
        <td>00/00/00</td><td class="num">${num(d.base)}</td><td></td><td></td>
        <td class="num">${num(d.base)}</td><td></td></tr>`;
      h+=rs.map(x=>`<tr>
        <td>${dsp(x.ymd)}</td>
        <td class="num">${x.prev_qty?num(x.prev_qty):''}</td>
        <td class="num">${x.in_qty?num(x.in_qty):''}</td>
        <td class="num">${x.out_qty?num(x.out_qty):''}</td>
        <td class="num">${num(x.stock_qty)}</td>
        <td title="${esc(x.note||'')}">${esc(x.note||'')}</td></tr>`).join('');
      $('#si-rb').innerHTML=h||`<tr><td colspan="6" style="text-align:center;color:#8aa0bd;padding:18px">내역이 없습니다.</td></tr>`;
      $('#si-rt').innerHTML=`<td style="width:100px"></td>
        <td class="num" style="width:90px">${num(d.base)}</td>
        <td class="num" style="width:90px">${num(d.sum_in)}</td>
        <td class="num" style="width:90px">${num(d.sum_out)}</td>
        <td class="num" style="width:90px">${num(d.last)}</td>
        <td>${esc(r.item_code)} 합계</td>`;
    }catch(e){
      $('#si-rb').innerHTML=`<tr><td colspan="6" style="text-align:center;color:#c33;padding:18px">${esc(String(e))}</td></tr>`;
    }
  };

  const load=async()=>{
    const nm=$('#si-cust').value.trim();
    const cd=custMap[nm]||nm;
    const g=c.querySelector('input[name="si-g"]:checked').value;
    msg('조회중…');
    try{
      const q=new URLSearchParams({cust:cd,item:$('#si-item').value.trim(),gubun:g});
      const d=await fetch(API+'/api/setstockio/list?'+q).then(x=>x.json());
      rows=d.rows||[]; sel=null; cur=null;
      drawL();
      $('#si-rb').innerHTML=`<tr><td colspan="6" style="text-align:center;color:#8aa0bd;padding:24px">좌측에서 세트도번을 선택하세요.</td></tr>`;
      msg(num(rows.length)+'건 조회');
    }catch(e){ msg('오류: '+e); }
  };

  $('#si-go').onclick=load;
  $('#si-item').onkeydown=e=>{if(e.key==='Enter')load();};
  $('#si-cust').onchange=load;
  c.querySelectorAll('input[name="si-g"]').forEach(r=>r.onchange=load);
  $('#si-f').onchange=()=>{if(cur)loadDetail(cur);};
  $('#si-t').onchange=()=>{if(cur)loadDetail(cur);};
  $('#si-xl').onclick=()=>{
    if(!rows.length)return alert('조회된 자료가 없습니다.');
    const hd=['거래처명','세트도번','품명','재고수량','담당','거래처코드'];
    const bd=rows.map(r=>[r.cust_name,r.item_code,r.item_name||'',r.stock_qty,r.user_id||'',r.cust_code]);
    const csv='\ufeff'+[hd,...bd].map(r=>r.map(v=>`"${String(v??'').replace(/"/g,'""')}"`).join(',')).join('\r\n');
    const a=document.createElement('a');
    a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
    a.download='자재세트재고입출고현황.csv'; a.click();
  };

  load();
};
/* ==== 자재세트재고조정 (레거시 w_pu_stock_135) — 2026-08-30 신설 ====
   ★세트 계정만 움직인다 — PBL 원문 확정(sa_stock_01.pbl, dw_data::ue_save_after).
     창 소스에 dw_6·PU_T_STOCK_MAINT·set_maint_seq·SAGUB 전부 0회.
     즉 자도번(단품) 파생도, 사급 처리도 없다. 라이브 실측(tag='3' 파생 0행)과 일치.
   수정방법(레거시 dw_c1.reset_flag): '0' 가감 / '1' 변경(maint_qty − stock_qty).
   ※SERIAL-NO·HEAT-NO 는 레거시 화면에 있으나 실사용 0건이라 넣지 않는다. */
SCREEN.setstockadj=(c)=>{
  const API=API_BASE;
  const num=n=>(+n||0).toLocaleString();
  const p2=n=>String(n).padStart(2,'0');
  const iso=d=>`${d.getFullYear()}-${p2(d.getMonth()+1)}-${p2(d.getDate())}`;
  const d2y=v=>v?v.slice(2).replace(/-/g,''):'';
  const dsp=v=>v&&v.length===6?(v.slice(0,2)+'/'+v.slice(2,4)+'/'+v.slice(4,6)):'';
  const now=new Date();

  let st={fr:iso(new Date(now.getFullYear(),now.getMonth(),1)), to:iso(now),
          cust:'', custnm:'', fitem:'', hist:[], loading:false};
  let custMap={};

  c.innerHTML=`
   <style>
    #sa2 table.grid{border-collapse:collapse;table-layout:fixed}
    #sa2 table.grid th,#sa2 table.grid td{
      text-align:center;border:1px solid #b9c8da;padding:3px 6px;white-space:nowrap;
      overflow:hidden;text-overflow:ellipsis}
    #sa2 table.grid thead th{background:#dce9f7;color:#24405f;font-weight:600;
      position:sticky;top:0;z-index:2;border-bottom:2px solid #8fa9c6}
    #sa2 table.grid tbody tr:nth-child(even){background:#f6f9fd}
    #sa2 .num{font-variant-numeric:tabular-nums;text-align:right}
    #sa2 .lft{text-align:left}
   </style>
   <div id="sa2" style="display:flex;flex-direction:column;height:100%;min-height:0">
    <div class="page-title">🛠️ 자재세트재고조정
      <span style="font-size:12px;color:var(--muted);font-weight:400">레거시 w_pu_stock_135 · 장부수정</span></div>

    <div class="toolbar" style="flex:0 0 auto;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
      <label>조정일자 <input type="date" class="inp" id="a2-fr" value="${st.fr}" style="width:145px"></label>
      ~ <input type="date" class="inp" id="a2-to" value="${st.to}" style="width:145px">
      <label>거래처 <input class="inp" id="a2-cust" list="a2-custs"
             placeholder="거래처명 일부(예: 대원)" style="width:190px"></label>
      <datalist id="a2-custs"></datalist>
      <span id="a2-cc" style="font-size:12px;color:#5a6b82"></span>
      <label>도번 <input class="inp" id="a2-fi" placeholder="도번" style="width:130px"></label>
      <button class="btn primary" id="a2-go">🔍 조회</button>
      <button class="btn" id="a2-new" style="background:#27ae60;color:#fff">＋ 재고조정 등록</button>
      <button class="btn" id="a2-xl">엑셀</button>
      <span id="a2-msg" style="color:var(--muted);font-size:12px"></span>
    </div>

    <div style="flex:1;min-height:0;display:flex;flex-direction:column;margin-top:8px;
                border:1px solid var(--line-2,#c9d3e0);border-radius:8px;background:#fff">
      <div style="flex:0 0 auto;padding:5px 10px;background:#eef4fb;font-weight:600;font-size:13px;
                  border-bottom:1px solid var(--line-2,#c9d3e0)">조정 내역</div>
      <div style="flex:1;min-height:0;overflow:auto">
        <table class="grid" style="width:100%"><thead><tr>
          <th style="width:90px">조정일자</th><th style="width:50px">SEQ</th>
          <th style="width:80px">거래처코드</th><th style="width:150px">거래처명</th>
          <th style="width:160px">도번</th><th>품명</th>
          <th style="width:100px">조정수량</th><th style="width:220px">비고</th>
          <th style="width:80px">담당</th><th style="width:140px">작업일시</th>
          <th style="width:50px">취소</th></tr></thead>
        <tbody id="a2-b"></tbody></table>
      </div>
      <table class="grid" style="width:100%;flex:0 0 auto;border-top:2px solid #8fa9c6">
        <tbody><tr style="background:#dbe7f5;font-weight:600">
          <td colspan="6" id="a2-cnt">0건</td>
          <td class="num" style="width:100px" id="a2-sum">0</td>
          <td colspan="4"></td></tr></tbody>
      </table>
    </div>
   </div>`;

  const $=id=>c.querySelector(id);
  const msg=t=>{$('#a2-msg').textContent=t||'';};

  /* 거래처 부분검색 — 화면·팝업 공용 */
  const findCust=v=>{
    const nm=String(v||'').trim();
    if(!nm)return {code:'',name:'',warn:''};
    if(custMap[nm])return {code:custMap[nm],name:nm,warn:''};
    const keys=Object.keys(custMap);
    const byCode=keys.filter(k=>custMap[k]===nm);
    if(byCode.length===1)return {code:nm,name:byCode[0],warn:''};
    const hit=keys.filter(k=>k.indexOf(nm)>=0);
    if(hit.length===1)return {code:custMap[hit[0]],name:hit[0],warn:''};
    if(hit.length>1){
      const ex=hit.filter(k=>k.startsWith(nm));
      if(ex.length===1)return {code:custMap[ex[0]],name:ex[0],warn:''};
      return {code:'',name:nm,warn:'후보 '+hit.length+'건 — '+hit.slice(0,5).join(' / ')};
    }
    return {code:'',name:nm,warn:'일치하는 거래처가 없습니다.'};
  };

  const drawHist=()=>{
    const b=$('#a2-b');
    if(st.loading){b.innerHTML=`<tr><td colspan="11" style="padding:20px;color:#8aa0bd">조회중…</td></tr>`;return;}
    if(!st.hist.length){
      b.innerHTML=`<tr><td colspan="11" style="padding:24px;color:#8aa0bd">조정 내역이 없습니다.</td></tr>`;
      $('#a2-cnt').textContent='0건'; $('#a2-sum').textContent='0'; return;
    }
    b.innerHTML=st.hist.map(r=>`<tr>
      <td>${dsp(r.ymd)}</td><td>${r.seq}</td>
      <td>${esc(r.cust_code)}</td><td class="lft">${esc(r.cust_name||'')}</td>
      <td><b>${esc(r.item_code)}</b></td>
      <td class="lft" title="${esc(r.item_name||'')}">${esc(r.item_name||'')}</td>
      <td class="num" style="color:${r.qty<0?'#c0392b':'#1f7a3d'};font-weight:600">${(r.qty>0?'+':'')+num(r.qty)}</td>
      <td class="lft" title="${esc(r.remarks)}">${esc(r.remarks)}</td>
      <td>${esc(r.user_id)}</td><td>${esc(r.dt)}</td>
      <td><button class="btn a2-del" data-y="${r.ymd}" data-s="${r.seq}"
           style="padding:0 6px;color:#c0392b">✕</button></td></tr>`).join('');
    $('#a2-cnt').textContent=num(st.hist.length)+'건';
    $('#a2-sum').textContent=num(st.hist.reduce((a,x)=>a+(+x.qty||0),0));
    c.querySelectorAll('.a2-del').forEach(x=>x.onclick=()=>delAdj(x.dataset.y,x.dataset.s));
  };

  const load=async()=>{
    st.loading=true; drawHist(); msg('조회중…');
    try{
      const q=new URLSearchParams({fr:d2y(st.fr),to:d2y(st.to),
                                   cust:st.cust,item:$('#a2-fi').value.trim()});
      const d=await fetch(`${API}/api/setadj/list?`+q).then(x=>x.json());
      st.hist=d.rows||[]; msg(num(st.hist.length)+'건');
    }catch(e){ st.hist=[]; msg('오류: '+e); }
    st.loading=false; drawHist();
  };

  const delAdj=async(y,sq)=>{
    if(!window.confirm(`조정건 ${dsp(y)} / SEQ ${sq} 을(를) 취소합니다. 진행?`))return;
    try{
      const r=await fetch(`${API}/api/setadj/delete`,{method:'POST',
              headers:{'Content-Type':'application/json'},body:JSON.stringify({ymd:y,seq:+sq})});
      const j=await r.json();
      if(!r.ok||!j.ok)throw new Error(j.detail||'실패');
      msg(`조정 취소 — ${j.item_code} ${num(j.qty)}`); await load();
    }catch(e){ alert('취소 실패: '+e.message); }
  };

  /* ==== 등록 팝업 (레거시 w_pu_stock_135 등록창) ==== */
  const openAdj=()=>{
    const ov=document.createElement('div');
    ov.style.cssText='position:fixed;inset:0;background:rgba(15,25,40,.45);z-index:1200;'
                    +'display:flex;align-items:center;justify-content:center';
    document.body.appendChild(ov);
    const close=()=>ov.remove();

    const blank=()=>({item_code:'',itemnm:'',stock:null,qty:'',remark:''});
    let ms={ymd:iso(now),cust:st.cust,custnm:st.custnm,method:'add',rows:[],busy:false};
    for(let i=0;i<30;i++) ms.rows.push(blank());

    const diffOf=r=>{
      if(!r.item_code||String(r.qty).trim()==='')return null;
      const v=+r.qty; if(isNaN(v))return null;
      if(ms.method!=='set')return v;
      if(r.stock==null)return null;
      return v-(+r.stock||0);
    };

    const paint=()=>{
      ov.innerHTML=`
       <div style="background:#fff;border-radius:10px;width:min(1080px,95vw);max-height:92vh;
                   display:flex;flex-direction:column;box-shadow:0 12px 40px rgba(0,0,0,.3)">
        <div style="flex:0 0 auto;padding:12px 16px;background:#8e44ad;color:#fff;border-radius:10px 10px 0 0;
                    display:flex;justify-content:space-between;align-items:center">
          <b>🛠️ 자재세트재고조정 — 등록</b>
          <span style="font-size:12px;font-weight:400">레거시 w_pu_stock_135 · 3:장부수정</span>
        </div>
        <div style="flex:0 0 auto;padding:10px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;
                    border-bottom:1px solid #dfe6ee">
          <label>기준일자 <input type="date" class="inp" id="m2-ymd" value="${ms.ymd}" style="width:145px;min-width:0"></label>
          <label>거래처<span style="color:#c0392b">*</span>
            <input class="inp" id="m2-cust" list="a2-custs" value="${esc(ms.custnm)}"
                   placeholder="거래처명 일부(예: 대원)"
                   style="width:200px;min-width:0;${ms.cust?'':'border-color:#e08b8b;background:#fff7f7'}"></label>
          <span id="m2-cc" style="font-size:12px;${ms.cust?'color:#1f7a3d':'color:#c0392b'}">
            ${ms.cust?('✔ '+esc(ms.custnm)+' ('+esc(ms.cust)+')'):'거래처를 먼저 선택하세요'}</span>
          <label>수정구분 <select class="inp" style="width:120px;min-width:0" disabled><option>3:장부수정</option></select></label>
          <label>수정방법 <select class="inp" id="m2-mth" style="width:180px;min-width:0">
            <option value="add"${ms.method==='add'?' selected':''}>입력한수량을 가감</option>
            <option value="set"${ms.method==='set'?' selected':''}>입력한수량으로 변경</option></select></label>
        </div>
        <div style="flex:1;min-height:0;overflow:auto;padding:0 16px">
          <table class="tbl" style="width:100%;white-space:nowrap"><thead><tr>
            <th style="width:44px">SEQ</th><th style="width:180px">도번</th><th>품명</th>
            <th style="width:100px" class="num">재고수량</th>
            <th style="width:100px" class="num">${ms.method==='set'?'목표재고':'조정수량'}</th>
            <th style="width:90px" class="num">변동</th>
            <th style="width:180px">비고</th></tr></thead>
          <tbody>${ms.rows.map((r,i)=>{const d=diffOf(r);return `<tr>
            <td class="center">${i+1}</td>
            <td><input class="inp m2-it" data-i="${i}" value="${esc(r.item_code)}" placeholder="도번" style="width:100%;min-width:0"></td>
            <td class="cap" style="max-width:230px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.itemnm||'')}">${esc(r.itemnm||'')}</td>
            <td class="num" style="color:${(+r.stock<0)?'#c0392b':'#586174'}">${r.stock==null?'':num(r.stock)}</td>
            <td><input class="inp m2-qt" data-i="${i}" value="${esc(String(r.qty))}" inputmode="numeric" style="width:100%;min-width:0;text-align:right"></td>
            <td class="num" style="font-weight:600;color:${d==null?'#8aa0bd':(d<0?'#c0392b':(d>0?'#1f7a3d':'#8aa0bd'))}">${d==null?'':((d>0?'+':'')+num(d))}</td>
            <td><input class="inp m2-rm" data-i="${i}" value="${esc(r.remark)}" style="width:100%;min-width:0"></td></tr>`;}).join('')}</tbody></table>
        </div>
        <div style="flex:0 0 auto;padding:10px 16px;border-top:1px solid #dfe6ee;display:flex;gap:8px;align-items:center">
          <button class="btn" id="m2-add">＋ 행추가</button>
          <button class="btn" id="m2-clr">－ 빈행삭제</button>
          <button class="btn" id="m2-xl" style="background:#1e7e34;color:#fff">📋 엑셀 붙여넣기</button>
          <span id="m2-msg" style="color:#5a6b82;font-size:12px;margin-left:6px"></span>
          <span style="margin-left:auto"></span>
          <button class="btn" id="m2-close">닫기</button>
          <button class="btn" id="m2-save" style="background:#27ae60;color:#fff" ${ms.busy?'disabled':''}>${ms.busy?'저장중…':'💾 저장'}</button>
        </div>
       </div>`;

      const q=id=>ov.querySelector(id);
      const mmsg=t=>{const e=q('#m2-msg'); if(e)e.textContent=t||'';};
      q('#m2-ymd').onchange=e=>{ms.ymd=e.target.value;};
      q('#m2-mth').onchange=e=>{ms.method=e.target.value;paint();
        mmsg(ms.method==='set'?'변경 = 입력수량이 목표재고. 현재고 20 에 30 입력 → +10 만 기록됩니다.'
                              :'가감 = 입력수량을 그대로 더합니다. 78 → +78 · -78 → -78');};
      const applyC=e=>{
        const f=findCust(e.target.value);
        ms.cust=f.code; ms.custnm=f.name;
        ms.rows.forEach(r=>{r.stock=null;});
        paint(); if(f.warn)mmsg(f.warn);
        if(ms.cust) ms.rows.forEach((r,i)=>{if(r.item_code)fetchStock(i);});
      };
      q('#m2-cust').onchange=applyC; q('#m2-cust').onblur=applyC;
      ov.querySelectorAll('.m2-it').forEach(el=>{
        el.onchange=()=>{const i=+el.dataset.i;ms.rows[i].item_code=el.value.trim();fetchStock(i);};
        el.onpaste=ev=>{const t=(ev.clipboardData||window.clipboardData).getData('text')||'';
          if(!/[\t\r\n]/.test(t))return; ev.preventDefault(); applyPaste(t,+el.dataset.i);};
      });
      ov.querySelectorAll('.m2-qt').forEach(el=>{
        el.oninput=()=>{const i=+el.dataset.i; ms.rows[i].qty=el.value.replace(/[^\d.-]/g,'');
          const td=el.closest('tr').children[5], d=diffOf(ms.rows[i]);
          td.textContent=d==null?'':((d>0?'+':'')+num(d));
          td.style.color=d==null?'#8aa0bd':(d<0?'#c0392b':(d>0?'#1f7a3d':'#8aa0bd'));};
      });
      ov.querySelectorAll('.m2-rm').forEach(el=>{
        el.oninput=()=>{ms.rows[+el.dataset.i].remark=el.value;};
      });
      q('#m2-add').onclick=()=>{for(let i=0;i<5;i++)ms.rows.push(blank());paint();};
      q('#m2-clr').onclick=()=>{ms.rows=ms.rows.filter(r=>r.item_code||r.qty);
        while(ms.rows.length<30)ms.rows.push(blank());paint();};
      q('#m2-xl').onclick=()=>{
        const t=window.prompt('엑셀에서 복사한 내용을 붙여넣으세요 (Ctrl+V)\n\n형식: 도번[탭]수량[탭]비고','');
        if(t)applyPaste(t,null);};
      q('#m2-close').onclick=close;
      q('#m2-save').onclick=doSave;
      if(!ms.cust)mmsg('⚠ 거래처를 먼저 선택하세요(필수). 이름 일부만 입력해도 됩니다.');
    };

    const fetchStock=async i=>{
      const r=ms.rows[i];
      if(!r.item_code||!ms.cust){r.stock=null;paint();return;}
      try{
        const q=new URLSearchParams({cust:ms.cust,item:r.item_code});
        const d=await fetch(`${API}/api/setstock/manual/prep?`+q).then(x=>x.json());
        const hit=(d.rows||[]).find(x=>x.item_code===r.item_code);
        r.stock=hit?hit.stock_qty:0; r.itemnm=hit?hit.itemnm:'';
      }catch(e){ r.stock=null; }
      paint();
    };

    const applyPaste=(text,start)=>{
      const lines=String(text||'').split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
      if(!lines.length)return;
      let i=(start==null?ms.rows.findIndex(r=>!r.item_code&&!r.qty):start);
      if(i<0)i=ms.rows.length;
      let n=0;
      lines.forEach(ln=>{
        const cc=ln.split(/\t|,|\s{2,}/).map(x=>x.trim());
        const it=(cc[0]||'').replace(/^["']|["']$/g,'');
        if(!it)return;
        while(ms.rows.length<=i)ms.rows.push(blank());
        ms.rows[i]={item_code:it,itemnm:'',stock:null,
                    qty:(cc[1]||'').replace(/[^\d.-]/g,''),remark:(cc[2]||'')};
        i++;n++;
      });
      while(ms.rows.length<i+4)ms.rows.push(blank());
      paint();
      if(ms.cust)ms.rows.forEach((r,k)=>{if(r.item_code&&r.stock==null)fetchStock(k);});
    };

    const doSave=async()=>{
      if(ms.busy)return;
      if(!ms.cust)return alert('거래처는 필수입니다.\n\n거래처명 일부만 입력해도 됩니다(예: 대원 → 대원산업).');
      const src=ms.rows.filter(r=>r.item_code&&String(r.qty).trim()!=='');
      if(!src.length)return alert('조정할 도번·수량을 입력하세요.');
      const rows=[]; const skip=[];
      for(const r of src){
        let q=+r.qty||0;
        if(ms.method==='set'){
          if(r.stock==null)return alert(`재고를 아직 조회하지 못했습니다: ${r.item_code}`);
          q=(+r.qty||0)-(+r.stock||0);
          if(!q){skip.push(r.item_code);continue;}
        }
        if(!q)continue;
        rows.push({cust:ms.cust,item_code:r.item_code,qty:q,remark:r.remark});
      }
      if(!rows.length)return alert('실제 변동이 있는 행이 없습니다.'
                                  +(skip.length?`\n(현재고와 같아 제외: ${skip.slice(0,5).join(', ')})`:''));
      const tot=rows.reduce((a,r)=>a+r.qty,0);
      const detail=rows.slice(0,6).map(r=>`  · ${r.item_code} : ${r.qty>0?'+':''}${num(r.qty)}`).join('\n')
                  +(rows.length>6?`\n  … 외 ${rows.length-6}건`:'');
      if(!window.confirm(`${ms.custnm} · ${rows.length}건 / 순변동 ${num(tot)}\n`
                        +`방법: ${ms.method==='set'?'입력수량으로 변경(차액 기록)':'입력수량을 가감'}\n`
                        +detail
                        +`\n\n※세트재고만 조정됩니다 — 자도번(단품)·사급은 변동 없음(레거시 135 동일).`
                        +`\n\n진행할까요?`))return;
      ms.busy=true;paint();
      try{
        const body={ymd:d2y(ms.ymd),user:(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹'),rows};
        const r=await fetch(`${API}/api/setadj/save`,{method:'POST',
                headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        const j=await r.json();
        if(!r.ok||!j.ok)throw new Error(j.detail||JSON.stringify(j).slice(0,200));
        alert(`재고조정 완료 — ${j.count}건`);
        close();
        st.cust=ms.cust; st.custnm=ms.custnm;
        $('#a2-cust').value=ms.custnm;
        $('#a2-cc').textContent='✔ '+ms.custnm+' ('+ms.cust+')';
        $('#a2-cc').style.color='#1f7a3d';
        await load();
      }catch(e){ alert('조정 실패: '+e.message); ms.busy=false; paint(); }
    };

    ov.onclick=e=>{if(e.target===ov)close();};
    paint();
  };

  $('#a2-fr').onchange=e=>{st.fr=e.target.value;};
  $('#a2-to').onchange=e=>{st.to=e.target.value;};
  const applyCust=e=>{
    const f=findCust(e.target.value);
    st.cust=f.code; st.custnm=f.name;
    $('#a2-cc').textContent=f.code?('✔ '+f.name+' ('+f.code+')'):(f.warn||'');
    $('#a2-cc').style.color=f.code?'#1f7a3d':'#c0392b';
  };
  $('#a2-cust').onchange=applyCust; $('#a2-cust').onblur=applyCust;
  $('#a2-fi').onkeydown=e=>{if(e.key==='Enter')load();};
  $('#a2-go').onclick=load;
  $('#a2-new').onclick=openAdj;
  $('#a2-xl').onclick=()=>{
    if(!st.hist.length)return alert('조회된 자료가 없습니다.');
    const hd=['조정일자','SEQ','거래처코드','거래처명','도번','품명','조정수량','비고','담당','작업일시'];
    const bd=st.hist.map(r=>[dsp(r.ymd),r.seq,r.cust_code,r.cust_name,r.item_code,
                             r.item_name,r.qty,r.remarks,r.user_id,r.dt]);
    const csv='\ufeff'+[hd,...bd].map(r=>r.map(v=>`"${String(v??'').replace(/"/g,'""')}"`).join(',')).join('\r\n');
    const a=document.createElement('a');
    a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
    a.download='자재세트재고조정내역.csv'; a.click();
  };

  fetch(`${API}/api/base/partners?limit=3000`).then(r=>r.json()).then(d=>{
    let h='';
    (d.rows||d.list||d||[]).forEach(x=>{
      const nm=(x.cust_name||x.name||'').trim(), cd=(x.cust_code||x.code||'').trim();
      if(nm&&cd){custMap[nm]=cd;h+=`<option value="${esc(nm)}">${esc(cd)}</option>`;}
    });
    $('#a2-custs').innerHTML=h;
  }).catch(()=>{});

  drawHist(); load();
};
