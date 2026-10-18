#!/usr/bin/env python3
"""Build public/index.html from data/news.db (static; client-side date/week navigation)."""
import json, os, sqlite3
import dedupe, settings
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
JST = timezone(timedelta(hours=9))
DAYS = 14
HOT = settings.HOT_TAGS

def main():
    os.makedirs(os.path.join(BASE, "data"), exist_ok=True)
    con = sqlite3.connect(os.path.join(BASE, "data", "news.db"))
    since = (datetime.now(timezone.utc) - timedelta(days=DAYS)).isoformat()
    cols = {r[1] for r in con.execute("PRAGMA table_info(news)")}
    og = "og_image" if "og_image" in cols else "NULL"
    rows = con.execute(f"SELECT id,title,url,source,category,published_at,summary,tags,on_board,{og} FROM news "
                       "WHERE published_at>=? ORDER BY published_at DESC", (since,)).fetchall() if cols else []
    if settings.CATEGORIES:
        CATS = OrderedDict((c[0], c[1]) for c in settings.CATEGORIES)
        colors = {c[0]: (c[2] if len(c) > 2 else "#64748b") for c in settings.CATEGORIES}
    else:  # no settings.json: categories as found in the data
        found = sorted({r[4] for r in rows if r[4]}); CATS = OrderedDict((k, k) for k in found)
        colors = {k: "#64748b" for k in found}
    catcss = "".join(f".c-{k}{{background:{v}}}" for k, v in colors.items())
    items = []; seen = {}
    for i, t, u, s, c, p, sm, tg, ob, im in rows:
        # defensive dedupe (newest-first rows): same normalized URL, or same normalized title within 3 days
        tk, uk = dedupe.norm_title(t, s), dedupe.norm_url(u)
        dt = datetime.fromisoformat(p)
        hit = seen.get("u:" + uk) or (len(tk) >= 8 and seen.get("t:" + tk))
        if hit and ("u:" + uk in seen or abs((hit[1] - dt).days) <= dedupe.TITLE_WINDOW_DAYS):
            x = hit[0]
            if c != x["c"] and c not in x["cs"]: x["cs"].append(c)
            if ob: x["b"] = 1
            if not x["im"] and im and os.path.exists(os.path.join(BASE, "public", im)): x["im"] = im
            continue
        if im and not os.path.exists(os.path.join(BASE, "public", im)): im = None
        d = datetime.fromisoformat(p).astimezone(JST)
        tgl = [x for x in (tg or "").split(",") if x]
        it = {"id": i, "t": t, "u": u, "s": s or "", "c": c, "d": d.strftime("%Y-%m-%d"),
              "h": d.strftime("%H:%M"), "sm": sm or "", "tg": [x for x in tgl if not x.startswith("cat:")], "b": 1 if ob else 0, "im": im or "",
              "cs": [x[4:] for x in tgl if x.startswith("cat:") and x[4:] != c]}
        items.append(it); seen["u:" + uk] = (it, dt)
        if len(tk) >= 8: seen.setdefault("t:" + tk, (it, dt))
    days = len({x["d"] for x in items})
    data = json.dumps({"items": items, "cats": CATS, "hot": HOT}, ensure_ascii=False).replace("</", "<\\/")
    btns = '<button class="on" data-f="all">すべて</button>' + "".join(f'<button data-f="{k}">{v}</button>' for k, v in CATS.items()) \
         + '<button data-f="multi">🔧マルチツール</button>'
    now = datetime.now(JST)
    page = TPL.replace("%%CATCSS%%", catcss).replace("%%BTNS%%", btns).replace("%%DATA%%", data) \
              .replace("%%UPD%%", f"更新 {now:%m/%d %H:%M} JST · {len(items)}件<span class=\"rng\"> / {DAYS}日</span>")
    os.makedirs(os.path.join(BASE, "public"), exist_ok=True)
    open(os.path.join(BASE, "public", "index.html"), "w", encoding="utf-8").write(page)
    print(f"wrote public/index.html ({len(items)} items (from {len(rows)} rows), {days} days)")

TPL = r"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>ニュースタイムライン</title>
<link rel="icon" type="image/svg+xml" href="favicon.svg"><style>
:root{--bg:#f7f7f8;--fg:#1d1d1f;--card:#fff;--mut:#6b7280;--bd:#e5e7eb;--ac:#2563eb;--red:#dc2626;--blue:#2563eb;--pane:rgba(255,255,255,.82);--soft:#eef2ff}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--fg:#e6e6e6;--card:#171a21;--mut:#9aa3af;--bd:#262b36;--ac:#60a5fa;--red:#f87171;--blue:#60a5fa;--pane:rgba(15,17,21,.82);--soft:#1e293b}}
html{overflow-anchor:none}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 system-ui,-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif}
.hd{position:relative;z-index:6;background:var(--pane);backdrop-filter:saturate(1.6) blur(10px);-webkit-backdrop-filter:saturate(1.6) blur(10px);border-bottom:1px solid var(--bd)}
.hd .in{max-width:860px;margin:0 auto;padding:8px 16px;display:flex;align-items:baseline;gap:12px}
.hd h1{font-size:16px;margin:0;font-weight:700;white-space:nowrap}.hd h1 .hi{width:1.15em;height:1.15em;vertical-align:-.2em;margin-right:.3em;color:currentColor}.hd .upd{margin-left:auto;color:var(--mut);font-size:11.5px;text-align:right}
button{border:1px solid var(--bd);background:var(--card);color:var(--fg);border-radius:999px;padding:4px 12px;cursor:pointer;font-size:13px;font-family:inherit}
button.on{background:var(--ac);color:#fff;border-color:var(--ac)}
.wk{position:-webkit-sticky;position:sticky;top:0;z-index:5;background:var(--pane);backdrop-filter:saturate(1.6) blur(12px);-webkit-backdrop-filter:saturate(1.6) blur(12px);border-bottom:1px solid var(--bd);box-shadow:0 4px 14px rgba(0,0,0,.06);margin-bottom:8px;transform:translateZ(0)}
@media (prefers-color-scheme:dark){.wk{box-shadow:0 4px 16px rgba(0,0,0,.4)}}
.panel{max-width:860px;margin:0 auto;padding:8px 16px 8px}
.ph{display:flex;align-items:center;gap:8px;margin:0 2px 10px}
.ml{font-size:12px;font-weight:700;color:var(--mut);margin:0 0 4px 36px;letter-spacing:.04em}
.row{display:flex;align-items:center;gap:4px}.row .vp{flex:1;min-width:0}
.arr{flex:none;width:32px;height:32px;padding:0;font-size:18px;line-height:1;transition:background .2s,transform .1s}.arr:active{transform:scale(.92)}.sl{font-size:12px;color:var(--mut)}
.ctl{margin-left:auto;display:flex;gap:6px}.ctl button{height:32px;min-width:32px;padding:0 10px;font-size:13px;transition:background .2s,transform .1s}
.ctl button:active{transform:scale(.94)}.ctl .arr{font-size:18px;line-height:1;padding:0}
#today[disabled]{opacity:.4;cursor:default}
.vp{position:relative;overflow:hidden;touch-action:pan-y}
.days{display:grid;grid-template-columns:repeat(7,1fr);gap:4px;position:relative}
.pill{position:absolute;top:0;bottom:0;left:0;border-radius:12px;background:var(--ac);box-shadow:0 4px 14px rgba(37,99,235,.35);transition:transform .32s cubic-bezier(.3,.7,.2,1),width .32s,opacity .2s;z-index:0;pointer-events:none}
.day{position:relative;z-index:1;border:0;background:transparent;border-radius:12px;padding:6px 0 7px;display:flex;flex-direction:column;align-items:center;gap:1px;line-height:1.15;transition:color .25s,background .2s}
.day:hover{background:var(--soft)}.day.on:hover{background:transparent}
.day .wd{font-size:11px;color:var(--mut);font-weight:600}.day .dd{font-size:24px;font-weight:800;font-variant-numeric:tabular-nums}
.day .bar{width:60%;height:4px;border-radius:2px;background:var(--bd);overflow:hidden;margin-top:3px}.day .bar i{display:block;height:100%;background:var(--ac);border-radius:2px;transition:width .3s}
.day .n{font-size:10px;color:var(--mut);font-variant-numeric:tabular-nums}
.day.zero .dd{opacity:.4}.day.sun .wd,.day.sun .dd{color:var(--red)}.day.sat .wd,.day.sat .dd{color:var(--blue)}
.day.today::after{content:"";position:absolute;top:5px;right:calc(50% - 22px);width:5px;height:5px;border-radius:50%;background:var(--red)}.day.today.on::after{background:#fff}
.day.on .wd,.day.on .dd,.day.on .n{color:#fff}.day.on .bar{background:rgba(255,255,255,.35)}.day.on .bar i{background:#fff}
.day:focus-visible{outline:2px solid var(--ac);outline-offset:2px}
nav{display:flex;gap:6px;flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;-webkit-overflow-scrolling:touch;margin-top:8px;padding-bottom:1px}nav::-webkit-scrollbar{display:none}nav button{flex:none}nav button{transition:background .2s,color .2s}
.cnt{font-size:13px;color:var(--mut);margin:8px 2px 0}
main{max-width:860px;margin:0 auto;padding:4px 16px 40px}
ul{list-style:none;margin:0;padding:0}.item{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:10px 14px;margin:8px 0}
.item a{color:var(--fg);text-decoration:none;font-weight:600}.item a:hover{color:var(--ac)}
.item p{margin:4px 0 0;color:var(--mut);font-size:13px}.meta{font-size:12px;color:var(--mut);display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.cat{border-radius:4px;padding:0 6px;color:#fff;font-size:11px}%%CATCSS%%
.tags{margin-top:4px}.tag{font-size:11px;border:1px solid var(--bd);border-radius:4px;padding:0 5px;margin-right:4px;color:var(--mut)}
.tag.hot{border-color:#ef4444;color:#ef4444}.board{color:#eab308}small{color:var(--mut);font-size:10px;float:right}
.empty{text-align:center;color:var(--mut);padding:48px 16px;background:var(--card);border:1px dashed var(--bd);border-radius:12px;margin-top:12px}
.empty .ic{font-size:40px}
@media (max-width:480px){.hd .rng{display:none}.hd .upd{white-space:nowrap}.ml{margin-left:28px}.arr{width:26px;height:26px;font-size:16px}.row{gap:2px}.day.today::after{top:4px;right:calc(50% - 15px);width:4px;height:4px}.hd h1{font-size:14px}.hd .upd{font-size:10.5px}.panel{padding:6px 10px 7px}.day .dd{font-size:19px}.day .wd{font-size:10px}.days{gap:2px}main{padding:4px 10px 40px}}
.wk{transition:margin-bottom .22s ease}.wk .panel{transition:padding .22s ease}
.ml,nav,.day .bar,.day .n{transition:max-height .22s ease,opacity .18s ease,margin .22s ease,transform .22s ease;overflow:hidden}
.ml{max-height:20px}nav{max-height:44px}.day .bar{max-height:4px}.day .n{max-height:14px}
.day{transition:padding .22s ease,color .25s,background .2s}
.wk.cp .panel{padding-top:5px;padding-bottom:5px}
.wk.cp .ml,.wk.cp nav,.wk.cp .day .bar,.wk.cp .day .n{max-height:0;opacity:0;margin-top:0;margin-bottom:0;transform:translateY(-4px);pointer-events:none}
.wk.cp .day{padding:4px 0 5px}
.wk.notr,.wk.notr *{transition:none!important}
@media (prefers-reduced-motion:reduce){.wk,.wk *{transition:none!important}}
@media (prefers-reduced-motion:reduce){.pill,.day,.day .bar i,nav button,.ctl button{transition:none!important}}
.item{position:relative;height:260px;padding:0;overflow:hidden;display:flex;flex-direction:column;justify-content:flex-end;background:linear-gradient(160deg,var(--card),var(--soft))}
.item .ov{position:relative;padding:60px 16px 12px}.item a{font-size:16px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.item:not(.img) a::after{content:"";position:absolute;inset:0;z-index:1}
.item .ov p{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.item .tags{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.item .meta{flex-wrap:nowrap;overflow:hidden;white-space:nowrap}
@media (max-width:480px){.item .ov{padding:48px 12px 10px}.item a{font-size:15px}}
.item.img{position:relative;padding:0;overflow:hidden;height:260px;display:flex;flex-direction:column;justify-content:flex-end;border:0;background:#222;box-shadow:0 2px 10px rgba(0,0,0,.18)}
.item.img .bg{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:0}
.item.img .pb{position:absolute;left:0;right:0;bottom:0;height:75%;z-index:1;pointer-events:none}
.item.img .pb i{position:absolute;inset:0}
.item.img .pb i:nth-child(1){backdrop-filter:blur(1px);-webkit-backdrop-filter:blur(1px);mask-image:linear-gradient(to bottom,transparent 0%,#000 20%,#000 40%,transparent 60%);-webkit-mask-image:linear-gradient(to bottom,transparent 0%,#000 20%,#000 40%,transparent 60%)}
.item.img .pb i:nth-child(2){backdrop-filter:blur(3px);-webkit-backdrop-filter:blur(3px);mask-image:linear-gradient(to bottom,transparent 20%,#000 40%,#000 60%,transparent 80%);-webkit-mask-image:linear-gradient(to bottom,transparent 20%,#000 40%,#000 60%,transparent 80%)}
.item.img .pb i:nth-child(3){backdrop-filter:blur(7px);-webkit-backdrop-filter:blur(7px);mask-image:linear-gradient(to bottom,transparent 40%,#000 60%,#000 80%,transparent 100%);-webkit-mask-image:linear-gradient(to bottom,transparent 40%,#000 60%,#000 80%,transparent 100%)}
.item.img .pb i:nth-child(4){backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);mask-image:linear-gradient(to bottom,transparent 60%,#000 80%);-webkit-mask-image:linear-gradient(to bottom,transparent 60%,#000 80%)}
.item.img .pb b{position:absolute;inset:0;background:linear-gradient(to bottom,rgba(0,0,0,0) 0%,rgba(0,0,0,.35) 40%,rgba(0,0,0,.78) 100%)}
.item.img .ov{position:relative;z-index:2;padding:60px 16px 12px;color:#fff;text-shadow:0 1px 3px rgba(0,0,0,.5)}
.item.img a{color:#fff;font-size:16px}.item.img a:hover{color:#bfdbfe}.item.img a::after{content:"";position:absolute;inset:0;z-index:1}
.item.img .ov>*{position:relative}.item.img .meta,.item.img .ov p,.item.img small{color:rgba(255,255,255,.85)}
.item.img .ov p{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.item.img .tag{color:#fff;border-color:rgba(255,255,255,.45);background:rgba(0,0,0,.2)}.item.img .tag.hot{border-color:#fca5a5;color:#fecaca}
.item.img .board{color:#fde047}.item.img .cat{text-shadow:none}
@media (prefers-color-scheme:dark){.item.img{box-shadow:0 2px 12px rgba(0,0,0,.5);outline:1px solid var(--bd)}}
@media (max-width:480px){.item,.item.img{height:220px}.item.img .ov{padding:48px 12px 10px}.item.img a{font-size:15px}}
</style></head><body>
<header class="hd"><div class="in"><h1><i data-lucide="receipt-text" class="hi"></i>ニュースタイムライン</h1><div class="upd">%%UPD%%</div></div></header>
<div id="sent" style="height:1px;margin-bottom:-1px"></div><section class="wk" id="wk"><div class="panel"><div class="ml" id="ml"></div>
<div class="row"><button class="arr" id="prev" aria-label="前の週">‹</button><div class="vp" id="vp"></div><button class="arr" id="next" aria-label="次の週">›</button></div><nav id="cats">%%BTNS%%</nav><div class="cnt" id="cnt" hidden></div></div></section><main id="list"></main>
<script id="news-data" type="application/json">%%DATA%%</script>
<script>
(()=>{
const D=JSON.parse(document.getElementById('news-data').textContent),WD='日月火水木金土';
const byDay={};D.items.forEach(x=>(byDay[x.d]=byDay[x.d]||[]).push(x));
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const tokyoToday=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
const parse=s=>{const[y,m,d]=s.split('-').map(Number);return new Date(Date.UTC(y,m-1,d))};
const fmt=dt=>dt.toISOString().slice(0,10);
const add=(s,n)=>{const d=parse(s);d.setUTCDate(d.getUTCDate()+n);return fmt(d)};
const valid=s=>/^\d{4}-\d{2}-\d{2}$/.test(s)&&!isNaN(parse(s))&&fmt(parse(s))===s;
let sel=tokyoToday(),cat='all',weekStart;
const monday=s=>add(s,-((parse(s).getUTCDay()+6)%7));
const match=x=>cat==='all'||x.c===cat||(x.cs||[]).includes(cat)||(cat==='multi'&&x.tg.some(t=>D.hot.includes(t)));
const RM=matchMedia('(prefers-reduced-motion: reduce)');const anim=()=>!RM.matches&&!!Element.prototype.animate;
const vp=document.getElementById('vp');let grid=null,listTok=0;
function label(){const a=parse(weekStart),b=parse(add(weekStart,6));const y1=a.getUTCFullYear(),y2=b.getUTCFullYear(),m1=a.getUTCMonth()+1,m2=b.getUTCMonth()+1;
 document.getElementById('ml').textContent=y1!==y2?`${y1}年${m1}月 – ${y2}年${m2}月`:m1!==m2?`${y1}年 ${m1}月 – ${m2}月`:`${y1}年 ${m1}月`;
}
function buildGrid(){const g=document.createElement('div');g.className='days';g.innerHTML='<div class="pill"></div>';const t=tokyoToday();
 for(let i=0;i<7;i++){const s=add(weekStart,i),d=parse(s),w=d.getUTCDay();const b=document.createElement('button');
  b.className='day'+(s===t?' today':'')+(w===0?' sun':w===6?' sat':'');b.dataset.d=s;b.title=s;
  b.innerHTML=`<span class="wd">${WD[w]}</span><span class="dd">${d.getUTCDate()}</span><span class="bar"><i></i></span><span class="n"></span>`;
  b.onclick=()=>go(s);g.appendChild(b)}return g}
function updateGrid(g,instant){g=g||grid;const ds=[...g.querySelectorAll('.day')],ns=ds.map(b=>(byDay[b.dataset.d]||[]).filter(match).length),mx=Math.max(1,...ns);
 ds.forEach((b,i)=>{const n=ns[i];b.classList.toggle('zero',!n);b.classList.toggle('on',b.dataset.d===sel);b.setAttribute('aria-pressed',b.dataset.d===sel);
  b.querySelector('.bar i').style.width=(n?Math.max(8,n/mx*100):0)+'%';b.querySelector('.n').textContent=n?n+'件':'–'});
 const p=g.querySelector('.pill'),on=ds.find(b=>b.dataset.d===sel);if(instant)p.style.transition='none';
 if(on){p.style.opacity=1;p.style.width=on.offsetWidth+'px';p.style.transform=`translateX(${on.offsetLeft}px)`}else p.style.opacity=0;
 if(instant){p.offsetWidth;p.style.transition=''}label()}
function setWeek(ws,dir){if(ws===weekStart&&grid){updateGrid();return}weekStart=ws;const old=grid;grid=buildGrid();vp.appendChild(grid);updateGrid(grid,true);
 if(old){if(dir&&anim()){old.style.position='absolute';old.style.inset='0';old.style.width='100%';
   const o={duration:300,easing:'cubic-bezier(.3,.7,.2,1)'};
   old.animate([{transform:'translateX(0)',opacity:1},{transform:`translateX(${-dir*40}%)`,opacity:0}],o).onfinish=()=>old.remove();
   grid.animate([{transform:`translateX(${dir*40}%)`,opacity:0},{transform:'translateX(0)',opacity:1}],o)}else old.remove()}}
function listHTML(){const L=(byDay[sel]||[]).filter(match),tot=(byDay[sel]||[]).length;
 document.getElementById('cnt').textContent=`この日の記事: ${L.length}件`+(cat!=='all'?`（全${tot}件中）`:'');
 if(!L.length)return `<div class="empty"><div class="ic">🗓️</div><p>${tot?'このカテゴリの記事はこの日にはありません':'この日の記事はありません'}</p><p style="font-size:13px">別の日付やカテゴリを選んでみてください</p></div>`;
 return '<ul>'+L.map(x=>{const chips=x.tg.map(t=>`<span class="tag${D.hot.includes(t)?' hot':''}">${esc(t)}</span>`).join('');
  const inner=`<div class="meta"><time>${x.h}</time><span class="cat c-${esc(x.c)}">${esc(D.cats[x.c]||x.c)}</span><span class="src">${esc(x.s)}</span>${x.b?'<span class="board">★ボード</span>':''}</div>`+
  `<a href="${esc(x.u)}" target="_blank" rel="noopener">${esc(x.t)}</a>${x.sm?`<p>${esc(x.sm)}</p>`:''}${chips?`<div class="tags">${chips}</div>`:''}<small>#${x.id}</small>`;
  if(x.im)return `<li class="item img" data-cat="${esc(x.c)}"><img class="bg" src="${esc(x.im)}" alt="" loading="lazy" decoding="async" onerror="this.closest('li').classList.remove('img');this.nextElementSibling.remove();this.remove()"><div class="pb"><i></i><i></i><i></i><i></i><b></b></div><div class="ov">${inner}</div></li>`;
  return `<li class="item" data-cat="${esc(x.c)}"><div class="ov">${inner}</div></li>`}).join('')+'</ul>'}
function renderList(fade){const m=document.getElementById('list'),tok=++listTok;
 if(!fade||!anim()){m.getAnimations().forEach(a=>a.cancel());m.innerHTML=listHTML();return}
 const out=m.animate([{opacity:getComputedStyle(m).opacity,transform:'none'},{opacity:0,transform:'translateY(-4px)'}],{duration:150,easing:'ease-in',fill:'forwards'});
 out.onfinish=()=>{if(tok!==listTok)return;m.innerHTML=listHTML();out.cancel();
  [m.querySelector('.empty'),...m.querySelectorAll('.item')].filter(Boolean).forEach((el,i)=>{if(i>12)return;
   el.animate([{opacity:0,transform:'translateY(10px)'},{opacity:1,transform:'none'}],{duration:280,delay:i*35,easing:'cubic-bezier(.2,.7,.2,1)',fill:'backwards'})})}}
function toTop(){const m=document.getElementById('list'),h=document.querySelector('.wk').offsetHeight,y=m.getBoundingClientRect().top+scrollY-h-8;
 if(scrollY>y+1)scrollTo({top:y,behavior:anim()?'smooth':'auto'})}
function go(s,fade=true){if(s===sel&&grid&&weekStart===monday(s))return;const ws=monday(s),dir=grid&&ws!==weekStart?(ws>weekStart?1:-1):0;sel=s;
 if(location.hash!=='#'+s)history.replaceState(null,'','#'+s);setWeek(ws,dir);updateGrid();const f=fade&&!!grid;if(f)toTop();renderList(f)}
const shift=n=>{setWeek(add(weekStart,7*n),n)};
document.getElementById('prev').onclick=()=>shift(-1);document.getElementById('next').onclick=()=>shift(1);
let tx=null,ty=0;vp.addEventListener('touchstart',e=>{tx=e.touches[0].clientX;ty=e.touches[0].clientY},{passive:true});
vp.addEventListener('touchend',e=>{if(tx==null)return;const dx=e.changedTouches[0].clientX-tx,dy=e.changedTouches[0].clientY-ty;tx=null;if(Math.abs(dx)>50&&Math.abs(dx)>Math.abs(dy)*1.5)shift(dx<0?1:-1)},{passive:true});
document.querySelectorAll('#cats button').forEach(b=>b.onclick=()=>{if(b.dataset.f===cat)return;document.querySelectorAll('#cats button').forEach(x=>x.classList.toggle('on',x===b));cat=b.dataset.f;updateGrid();toTop();renderList(true)});
addEventListener('resize',()=>grid&&updateGrid(grid,true));
const wk=document.getElementById('wk');let cpOn=false,mb0=null;
function setCompact(on){if(on===cpOn)return;cpOn=on;if(mb0==null)mb0=parseFloat(getComputedStyle(wk).marginBottom)||0;
 if(on){wk.classList.add('notr');const H=wk.offsetHeight;wk.classList.add('cp');const Hc=wk.offsetHeight;wk.classList.remove('cp');wk.offsetHeight;wk.classList.remove('notr');
  wk.style.marginBottom=(mb0+H-Hc)+'px';wk.classList.add('cp')}
 else{wk.classList.remove('cp');wk.style.marginBottom=''}
 requestAnimationFrame(()=>grid&&updateGrid(grid,true))}
if('IntersectionObserver' in window)new IntersectionObserver(es=>{const e=es[es.length-1];setCompact(!e.isIntersecting&&e.boundingClientRect.top<0)}).observe(document.getElementById('sent'));
addEventListener('resize',()=>{if(cpOn){cpOn=false;wk.classList.add('notr');wk.classList.remove('cp');wk.style.marginBottom='';wk.offsetHeight;wk.classList.remove('notr');setCompact(true)}});
const fromHash=()=>{const h=decodeURIComponent(location.hash.slice(1));return valid(h)?h:null};
window.addEventListener('hashchange',()=>{const h=fromHash();if(h&&h!==sel)go(h)});
sel=fromHash()||tokyoToday();go(sel,false);
})();
</script><script src="https://cdn.jsdelivr.net/npm/lucide@1.59.0/dist/umd/lucide.min.js"></script><script>lucide.createIcons();</script>
</body></html>"""

if __name__ == "__main__":
    main()
