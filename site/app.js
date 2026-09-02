<script>
const D = __DATA__;
const N = D.n, Z = D.zones, SLOTS = D.slots;
const LO = 180, HI = 2160;   // 3-36 min: vaste schaal over kaart en matrix, aan
                             // beide uiteinden geklemd zodat de hele ramp in gebruik is
let slot = "werkdag_avondspits";
let origin = 0;

const css = k => getComputedStyle(document.documentElement).getPropertyValue(k).trim();
const ramp = () => css("--ramp").split(",").map(s => s.trim());
const fmt = s => (s / 60).toFixed(s < 600 ? 1 : 0);
const tip = document.getElementById("tip");

function hex2rgb(h){ return [1,3,5].map(i => parseInt(h.substr(i,2),16)); }
function rampColor(t, steps){
  t = Math.max(0, Math.min(1, t));
  const x = t*(steps.length-1), i = Math.min(Math.floor(x), steps.length-2);
  const a = hex2rgb(steps[i]), b = hex2rgb(steps[i+1]), f = x-i;
  return `rgb(${a.map((v,k)=>Math.round(v+(b[k]-v)*f)).join(",")})`;
}
function sizeCanvas(cv, w, h){
  const r = window.devicePixelRatio || 1;
  cv.width = w*r; cv.height = h*r;
  cv.style.width = w+"px"; cv.style.height = h+"px";
  const c = cv.getContext("2d"); c.setTransform(r,0,0,r,0,0);
  return c;
}
function showTip(e, html){
  tip.innerHTML = html; tip.classList.add("on");
  tip.style.left = Math.min(e.clientX+16, innerWidth-272) + "px";
  tip.style.top  = Math.min(e.clientY+16, innerHeight-tip.offsetHeight-12) + "px";
}
const hideTip = () => tip.classList.remove("on");

/* stadsdelen: de zones staan al op gebied gesorteerd, dus de blokken zijn aaneengesloten */
const blocks = [];
Z.forEach((z,i) => {
  const last = blocks[blocks.length-1];
  if (!last || last.gebied !== z.gebied) blocks.push({gebied:z.gebied, from:i, to:i});
  else last.to = i;
});

/* ================= kaart ================= */
const rings = g => g.type === "Polygon" ? [g.coordinates[0]]
                                        : g.coordinates.map(p => p[0]);
/* Kader op de zones, niet op de stadscontour: Rotterdam heeft losse exclaves in
   het westen die de kaart anders leegtrekken. */
const zonePts = Z.map(z => rings(z.geom)).flat().flat();
const pad = 0.08;
const bb = (() => {
  const xs = zonePts.map(p => p[0]), ys = zonePts.map(p => p[1]);
  const x0=Math.min(...xs), x1=Math.max(...xs), y0=Math.min(...ys), y1=Math.max(...ys);
  const dx=(x1-x0)*pad, dy=(y1-y0)*pad;
  return {x0:x0-dx, x1:x1+dx, y0:y0-dy, y1:y1+dy};
})();
const kx = Math.cos((bb.y0+bb.y1)/2 * Math.PI/180);
const ASPECT = (bb.y1-bb.y0) / ((bb.x1-bb.x0)*kx);

/* De kaart schaalt mee met zijn kolom, zodat hij nooit buiten de kaart valt. */
let MAP_W = 900, MAP_H = 830, sc = 1, offX = 0, offY = 0;
const MPAD = 14;
function layoutMap(){
  const host = document.getElementById("mapWrap");
  MAP_W = Math.max(260, Math.min(host.clientWidth || 900, 900));
  MAP_H = Math.round(MAP_W * ASPECT);
  sc = Math.min((MAP_W-2*MPAD)/((bb.x1-bb.x0)*kx), (MAP_H-2*MPAD)/(bb.y1-bb.y0));
  offX = (MAP_W - (bb.x1-bb.x0)*kx*sc)/2;
  offY = (MAP_H - (bb.y1-bb.y0)*sc)/2;
}
const px = p => [offX + (p[0]-bb.x0)*kx*sc, offY + (bb.y1-p[1])*sc];

function tracePoly(c, geom){
  c.beginPath();
  rings(geom).forEach(r => {
    r.forEach((p,i) => { const q = px(p); i ? c.lineTo(q[0],q[1]) : c.moveTo(q[0],q[1]); });
    c.closePath();
  });
}
let mapHover = null;
function drawMap(){
  layoutMap();
  const c = sizeCanvas(document.getElementById("map"), MAP_W, MAP_H), steps = ramp();
  const surf = css("--surface-viz"), sunken = css("--sunken"), line = css("--line"),
        a2 = css("--accent-2"), ink = css("--ink"), ink3 = css("--ink-3");
  c.clearRect(0,0,MAP_W,MAP_H); c.fillStyle = surf; c.fillRect(0,0,MAP_W,MAP_H);

  tracePoly(c, D.context);
  c.fillStyle = sunken; c.fill("evenodd");
  c.strokeStyle = line; c.lineWidth = 1; c.stroke();

  const m = D.m[slot];
  Z.forEach((z,i) => {
    tracePoly(c, z.geom);
    c.fillStyle = i === origin ? a2 : rampColor((m[origin*N+i]-LO)/(HI-LO), steps);
    c.fill();
    c.strokeStyle = surf; c.lineWidth = MAP_W > 700 ? 1.2 : 0.8; c.stroke();
  });
  if (mapHover !== null){
    tracePoly(c, Z[mapHover].geom);
    c.strokeStyle = ink; c.lineWidth = 2; c.stroke();
  }
  tracePoly(c, Z[origin].geom);
  c.strokeStyle = ink; c.lineWidth = 2.5; c.stroke();

  c.font = '500 11px "IBM Plex Mono", monospace'; c.fillStyle = ink3;
  c.textAlign = "left"; c.textBaseline = "top";
  c.fillText("VERTREKZONE", MPAD, MPAD);
  c.fillStyle = a2; c.beginPath(); c.roundRect(MPAD, MPAD+18, 10, 10, 2); c.fill();
  c.fillStyle = ink3; c.textBaseline = "middle";
  c.fillText(Z[origin].naam, MPAD+16, MPAD+23);
}

function zoneAt(x, y){
  for (let i = Z.length-1; i >= 0; i--){
    for (const r of rings(Z[i].geom)){
      let inside = false;
      for (let a = 0, b = r.length-1; a < r.length; b = a++){
        const p = px(r[a]), q = px(r[b]);
        if ((p[1] > y) !== (q[1] > y) &&
            x < (q[0]-p[0])*(y-p[1])/(q[1]-p[1]) + p[0]) inside = !inside;
      }
      if (inside) return i;
    }
  }
  return null;
}
const mapEl = document.getElementById("map");
mapEl.style.cursor = "pointer";
mapEl.addEventListener("mousemove", e => {
  const r = mapEl.getBoundingClientRect();
  const i = zoneAt(e.clientX-r.left, e.clientY-r.top);
  if (i !== mapHover){ mapHover = i; drawMap(); }
  if (i === null){ hideTip(); return; }
  const k = origin*N + i;
  showTip(e, i === origin
    ? `<div class="t">${Z[i].naam}</div><div class="r"><span>vertrekzone</span><b>—</b></div>`
    : `<div class="t">${Z[origin].naam} → ${Z[i].naam}</div>
       <div class="r"><span>rijtijd</span><b>${fmt(D.m[slot][k])} min</b></div>
       <div class="r"><span>afstand</span><b>${(D.meters[k]/1000).toFixed(1)} km</b></div>
       <div class="r"><span>vrije doorstroom</span><b>${fmt(D.m.freeflow[k])} min</b></div>`);
});
mapEl.addEventListener("mouseleave", () => { mapHover = null; hideTip(); drawMap(); });
mapEl.addEventListener("click", e => {
  const r = mapEl.getBoundingClientRect();
  const i = zoneAt(e.clientX-r.left, e.clientY-r.top);
  if (i !== null) setOrigin(i);
});

function setOrigin(i){
  origin = i;
  document.getElementById("originName").textContent = Z[i].naam;
  const m = D.m[slot];
  const near = Z.map((z,j) => ({j, t:m[i*N+j]})).filter(o => o.j !== i)
                .sort((a,b) => a.t-b.t);
  const row = o => `<li><span class="z">${Z[o.j].naam}</span>
                    <span class="t">${fmt(o.t)} min</span></li>`;
  document.getElementById("rank").innerHTML =
    `<li class="hd"><span>Dichtstbij</span><span>rijtijd</span></li>` +
    near.slice(0,5).map(row).join("") +
    `<li class="hd"><span>Verst weg</span><span>rijtijd</span></li>` +
    near.slice(-3).reverse().map(row).join("");
  drawMap(); drawHeat();
}

/* ================= heatmap ================= */
const heat = document.getElementById("heat");
const PAD = 128, CELL = 8, GRID = N*CELL;
let hover = null;

function drawHeat(){
  const W = PAD+GRID+8, H = PAD+GRID+8;
  const c = sizeCanvas(heat, W, H), steps = ramp();
  const line = css("--line"), line2 = css("--line-2"), ink2 = css("--ink-2"),
        ink3 = css("--ink-3"), sunken = css("--sunken"), a2 = css("--accent-2");
  c.clearRect(0,0,W,H); c.fillStyle = css("--surface-viz"); c.fillRect(0,0,W,H);

  const m = D.m[slot];
  for (let i=0;i<N;i++) for (let j=0;j<N;j++){
    c.fillStyle = i===j ? sunken : rampColor((m[i*N+j]-LO)/(HI-LO), steps);
    c.fillRect(PAD+j*CELL, PAD+i*CELL, CELL-0.4, CELL-0.4);
  }
  c.strokeStyle = line2; c.lineWidth = 1;
  blocks.forEach(b => {
    const p = PAD + b.from*CELL + .5;
    c.beginPath(); c.moveTo(p,PAD); c.lineTo(p,PAD+GRID);
    c.moveTo(PAD,p); c.lineTo(PAD+GRID,p); c.stroke();
  });
  c.strokeStyle = line; c.strokeRect(PAD+.5, PAD+.5, GRID, GRID);

  c.font = '500 10.5px "IBM Plex Mono", monospace'; c.fillStyle = ink2;
  blocks.forEach(b => {
    const mid = PAD + (b.from + (b.to-b.from+1)/2)*CELL;
    const name = b.gebied.length > 18 ? b.gebied.slice(0,17)+"…" : b.gebied;
    c.textAlign="right"; c.textBaseline="middle"; c.fillText(name, PAD-10, mid);
    c.save(); c.translate(mid, PAD-10); c.rotate(-Math.PI/2);
    c.textAlign="left"; c.fillText(name, 0, 0); c.restore();
  });
  c.fillStyle = ink3; c.font='500 10px "IBM Plex Mono", monospace';
  c.textAlign="left"; c.textBaseline="top"; c.fillText("NAAR →", PAD, 8);
  c.save(); c.translate(14, PAD); c.rotate(-Math.PI/2);
  c.textAlign="right"; c.fillText("← VAN", 0, 0); c.restore();

  c.strokeStyle = a2; c.lineWidth = 1.5;             /* de rij die de kaart toont */
  c.strokeRect(PAD-1, PAD+origin*CELL-1, GRID+2, CELL+1);
  if (hover){
    c.strokeStyle = css("--ink"); c.lineWidth = 1.5;
    c.strokeRect(PAD+hover.j*CELL-.75, PAD, CELL+.5, GRID);
    c.strokeRect(PAD, PAD+hover.i*CELL-.75, GRID, CELL+.5);
  }
}
heat.style.cursor = "pointer";
heat.addEventListener("mousemove", e => {
  const r = heat.getBoundingClientRect();
  const j = Math.floor((e.clientX-r.left-PAD)/CELL), i = Math.floor((e.clientY-r.top-PAD)/CELL);
  if (i<0||j<0||i>=N||j>=N){ hover=null; hideTip(); drawHeat(); return; }
  hover = {i,j}; drawHeat();
  const k = i*N+j;
  showTip(e, i===j
    ? `<div class="t">${Z[i].naam} — binnen de zone</div>
       <div class="r"><span>intrazonaal</span><b>${fmt(D.m.freeflow[k])} min</b></div>
       <div class="r"><span>oppervlak</span><b>${Z[i].km2} km&sup2;</b></div>`
    : `<div class="t">${Z[i].naam} → ${Z[j].naam}</div>
       <div class="r"><span>afstand</span><b>${(D.meters[k]/1000).toFixed(1)} km</b></div>` +
      SLOTS.map(s => `<div class="r"><span>${s.label.replace(/ \(.*/,"")}</span>
        <b>${fmt(D.m[s.key][k])} min</b></div>`).join(""));
});
heat.addEventListener("mouseleave", () => { hover=null; hideTip(); drawHeat(); });
heat.addEventListener("click", e => {
  const r = heat.getBoundingClientRect();
  const i = Math.floor((e.clientY-r.top-PAD)/CELL);
  if (i>=0 && i<N) setOrigin(i);
});

/* ================= meetrooster en voortgang ================= */
const P = __PROGRESS__;
/* Kleur per soort tijdvak. De banden dragen hun naam, dus de kleur hoeft het
   onderscheid niet alleen te doen -- nodig, want drie van deze zes halen op een
   lichte ondergrond geen 3:1 contrast. */
const SOORT_KLEUR = {
  "Vroege ochtend": 4, "Ochtendspits": 1, "Dal": 2,
  "Avondspits": 3, "Avond": 0, "Middag": 5,
};
const CAT_LICHT = ["#2a78d6","#eb6834","#1baf7a","#eda100","#e87ba4","#008300"];
const CAT_DONKER = ["#3987e5","#d95926","#199e70","#c98500","#d55181","#008300"];
const donker = () => {
  const r = document.documentElement;
  if (r.dataset.theme === "dark") return true;
  if (r.dataset.theme === "light") return false;
  return matchMedia("(prefers-color-scheme: dark)").matches;
};
const catKleur = i => (donker() ? CAT_DONKER : CAT_LICHT)[i % 6];
const soortVan = key => P.slots.find(s => s.key === key).soort;

const H0 = 5.5, H1 = 23.5;      // getoonde uren
function drawSched(){
  const host = document.getElementById("schedWrap");
  const W = Math.max(280, Math.min(host.clientWidth || 900, 900));
  const L = 40, R = 10, T = 26, RIJ = 36, H = T + 7 * RIJ + 20;
  const c = sizeCanvas(document.getElementById("sched"), W, H);
  const iw = W - L - R;
  const x = h => L + (h - H0) / (H1 - H0) * iw;
  const ink = css("--ink"), ink2 = css("--ink-2"), ink3 = css("--ink-3"),
        line = css("--line"), surf = css("--surface-viz"), sunken = css("--sunken");
  c.clearRect(0, 0, W, H); c.fillStyle = surf; c.fillRect(0, 0, W, H);

  c.font = '400 10.5px "IBM Plex Mono", monospace'; c.textAlign = "center";
  c.textBaseline = "top"; c.strokeStyle = line; c.lineWidth = 1;
  for (let h = 6; h <= 23; h += 3){
    c.fillStyle = ink3; c.fillText(String(h).padStart(2,"0"), x(h), 6);
    c.beginPath(); c.moveTo(x(h) + .5, T - 4); c.lineTo(x(h) + .5, T + 7 * RIJ); c.stroke();
  }

  P.dagen.forEach((d, i) => {
    const y = T + i * RIJ;
    if (i >= 5){ c.fillStyle = sunken; c.fillRect(L, y, iw, RIJ - 6); }
    c.fillStyle = ink2; c.font = '500 11.5px "IBM Plex Mono", monospace';
    c.textAlign = "right"; c.textBaseline = "middle";
    c.fillText(d, L - 10, y + (RIJ - 6) / 2);
  });

  /* Naam bovenin de band, meetstippen op een eigen regel eronder -- anders
     lopen de stippen dwars door de tekst. */
  const KORT = {"Vroege ochtend":"Vroeg", "Ochtendspits":"Spits",
                "Avondspits":"Spits", "Middag":"Mid", "Avond":"Avond", "Dal":"Dal"};
  P.vensters.forEach(v => {
    const y = T + v.dag * RIJ, h = RIJ - 6;
    const x0 = x(Math.max(v.van, H0)), x1 = x(Math.min(v.tot, H1));
    c.fillStyle = catKleur(SOORT_KLEUR[soortVan(v.slot)]);
    c.beginPath(); c.roundRect(x0 + 1, y, Math.max(3, x1 - x0 - 2), h, 4); c.fill();
    const vol = soortVan(v.slot);
    c.font = '600 10.5px "IBM Plex Mono", monospace';
    const naam = c.measureText(vol).width + 12 < x1 - x0 ? vol : KORT[vol];
    if (c.measureText(naam).width + 10 < x1 - x0){
      c.fillStyle = "#fff"; c.textAlign = "center"; c.textBaseline = "middle";
      c.fillText(naam, (x0 + x1) / 2, y + 10);
    }
  });

  P.rooster.forEach(r => {                      // de werkelijke meetmomenten
    const y = T + r.dag * RIJ + RIJ - 6 - 7;
    c.beginPath(); c.arc(x(r.uur + P.minuut / 60), y, 2.6, 0, 7);
    c.fillStyle = surf; c.fill();
    c.strokeStyle = ink; c.lineWidth = 1; c.stroke();
  });

  c.fillStyle = ink3; c.font = '400 10.5px "IBM Plex Mono", monospace';
  c.textAlign = "left"; c.textBaseline = "top";
  c.fillText("uur", 6, 6);
}

function vulLegend(){
  const el = document.getElementById("schedLegend");
  el.innerHTML = P.soorten.map(s =>
    `<span class="lab"><span class="swatch" style="background:${catKleur(SOORT_KLEUR[s])}"></span>${s}</span>`
  ).join("") + `<span class="lab" style="margin-left:4px">
    <span class="swatch" style="background:var(--surface-viz); border:1px solid var(--ink)"></span>meetmoment</span>`;
}

function vulVoortgang(){
  const el = document.getElementById("progList");
  const volgorde = ["di–do", "maandag", "vrijdag", "weekend"];
  const soortVolgorde = ["Vroege ochtend","Ochtendspits","Dal","Avondspits","Avond","Middag"];
  let html = "";
  volgorde.forEach(g => {
    const rijen = P.slots.filter(s => s.groep === g)
      .sort((a,b) => soortVolgorde.indexOf(a.soort) - soortVolgorde.indexOf(b.soort));
    if (!rijen.length) return;
    html += `<div class="hd">${g}</div>`;
    rijen.forEach(s => {
      const pct = Math.min(100, s.dagen / s.doel_dagen * 100);
      const klaar = s.dagen >= s.doel_dagen;
      html += `<div class="row">
        <span class="lab">${s.soort}</span>
        <span class="track"><span class="fill" style="width:${pct}%"></span></span>
        <span class="n"><b>${s.dagen}</b>/${s.doel_dagen} dagen<br>
          <span style="color:var(--ink-3)">${klaar ? "klaar" : s.weken_nodig + " wk"}
          &middot; ${s.momenten}&times;</span></span>
      </div>`;
    });
  });
  el.innerHTML = html;

  const gestart = P.slots.filter(s => s.momenten > 0).length;
  document.getElementById("pMom").textContent = P.momenten_totaal;
  document.getElementById("pSlots").textContent = `${gestart}/${P.slots.length}`;
  document.getElementById("pWeek").textContent = P.vuringen_per_week;

  const traag = P.slots.slice().sort((a, b) => b.weken_nodig - a.weken_nodig)[0];
  const snel = P.slots.slice().sort((a, b) => a.weken_nodig - b.weken_nodig)[0];
  document.getElementById("progNote").innerHTML =
    `Stand op ${P.gegenereerd.replace("T", " ").slice(0, 16)}. `
    + `Wat telt zijn <b>losse dagen</b>, niet losse metingen: tien metingen op één `
    + `avond halen de ruis omlaag maar zeggen niets over hoe dinsdag van donderdag `
    + `verschilt. Nagerekend op de eerste dag data zat de klassemediaan al na één `
    + `moment binnen ongeveer 1% van de waarde uit zeven momenten &mdash; ruis is het `
    + `probleem dus niet, spreiding over dagen wel. `
    + `De dinsdag-tot-donderdag tijdvakken zijn over ${snel.weken_nodig} week rond; `
    + `<b>${traag.groep}</b> wordt maar ${traag.dagen_per_week}&times; per week gemeten `
    + `en heeft nog ${traag.weken_nodig} weken nodig. Dat bepaalt het tempo.`;
}

/* ================= NDW-dekking en kalibratieverloop ================= */
const C = __COVERAGE__;
const KH = __HISTORY__;

function drawNdw(){
  layoutMap();                                  // zelfde kader als de zonekaart
  const host = document.getElementById("ndwWrap");
  const W = Math.max(260, Math.min(host.clientWidth || 900, 900));
  const H = Math.round(W * ASPECT);
  const c = sizeCanvas(document.getElementById("ndwMap"), W, H);
  const sc2 = Math.min((W - 28) / ((bb.x1 - bb.x0) * kx), (H - 28) / (bb.y1 - bb.y0));
  const ox = (W - (bb.x1 - bb.x0) * kx * sc2) / 2;
  const oy = (H - (bb.y1 - bb.y0) * sc2) / 2;
  const px2 = (lon, lat) => [ox + (lon - bb.x0) * kx * sc2, oy + (bb.y1 - lat) * sc2];
  const surf = css("--surface-viz"), sunken = css("--sunken"), line = css("--line"),
        ink3 = css("--ink-3"), a1 = css("--accent"), a2 = css("--accent-2");
  c.clearRect(0, 0, W, H); c.fillStyle = surf; c.fillRect(0, 0, W, H);

  c.beginPath();
  rings(D.context).forEach(r => {
    r.forEach((p, i) => { const q = px2(p[0], p[1]); i ? c.lineTo(q[0], q[1]) : c.moveTo(q[0], q[1]); });
    c.closePath();
  });
  c.fillStyle = sunken; c.fill("evenodd");
  c.strokeStyle = line; c.lineWidth = 1; c.stroke();

  Z.forEach(z => {                              // parkeerzones als lichte vlekken
    c.beginPath();
    rings(z.geom).forEach(r => {
      r.forEach((p, i) => { const q = px2(p[0], p[1]); i ? c.lineTo(q[0], q[1]) : c.moveTo(q[0], q[1]); });
      c.closePath();
    });
    c.fillStyle = a1; c.globalAlpha = .14; c.fill(); c.globalAlpha = 1;
  });

  /* Stille punten eerst en klein: ze zijn er wel, maar leveren niets. */
  c.fillStyle = ink3; c.globalAlpha = .38;
  C.sites.forEach(s => { if (!s.live){
    const q = px2(s.lon, s.lat); c.fillRect(q[0] - .8, q[1] - .8, 1.6, 1.6); } });
  c.globalAlpha = 1;
  C.sites.forEach(s => { if (s.live){
    const q = px2(s.lon, s.lat);
    c.beginPath(); c.arc(q[0], q[1], 2.4, 0, 7);
    c.fillStyle = a2; c.fill();
    c.strokeStyle = surf; c.lineWidth = .8; c.stroke(); } });
}

function vulDekking(){
  document.getElementById("cvTot").textContent = C.n_totaal.toLocaleString("nl-NL");
  document.getElementById("cvLive").textContent = C.n_live;
  document.getElementById("cvDek").textContent = Math.round(C.dekking.gemiddeld * 100) + "%";
  const rijen = Object.entries(C.dekking.per_klasse)
    .sort((a, b) => b[1].aandeel_route - a[1].aandeel_route);
  document.getElementById("cvList").innerHTML = rijen.map(([k, v]) => `
    <div class="row">
      <span class="lab">${k}</span>
      <span class="track"><span class="fill" style="width:${v.dekking * 100}%"></span></span>
      <span class="n"><b>${Math.round(v.dekking * 100)}%</b> gedekt<br>
        <span style="color:var(--ink-3)">${Math.round(v.aandeel_route * 100)}% van de rit</span></span>
    </div>`).join("");
  const snelweg = C.dekking.per_klasse["snelweg"];
  const straat = C.dekking.per_klasse["gewone straat"];
  document.getElementById("cvWinst").innerHTML =
    `NDW publiceert echter een <b>tweede open feed met reistijden per traject</b>, `
    + `en die dekt de snelwegen wél. Samen komen we op <b>${C.n_live.toLocaleString("nl-NL")} `
    + `meldende punten</b> en <b>${Math.round(C.dekking.gemiddeld * 100)}% van de gereden `
    + `meters</b>, met ${Math.round(snelweg.dekking * 100)}% op de snelweg. Beide feeds `
    + `worden nu verzameld. Wat overblijft is de gewone straat: daar ligt op `
    + `${Math.round(straat.dekking * 100)}% van de meters een meetpunt, en de rest wordt `
    + `afgeleid uit de wegklasse.`;
  document.getElementById("ndwLegend").innerHTML =
    `<span class="lab"><span class="swatch" style="background:${css("--accent-2")}"></span>meldt snelheid (${C.n_live})</span>
     <span class="lab"><span class="swatch" style="background:${css("--ink-3")}; opacity:.45"></span>stil (${C.n_totaal - C.n_live})</span>
     <span class="lab"><span class="swatch" style="background:${css("--accent")}; opacity:.3"></span>parkeerzone</span>`;
}

/* Kleine grafiekjes per tijdvak: één per paneel, dus geen kleurcodering nodig. */
function drawKal(){
  const kolommen = Object.keys(KH[0].slots);
  const cols = window.innerWidth < 700 ? 2 : 3;
  const rijen = Math.ceil(kolommen.length / cols);
  const W = 980, PW = W / cols, PH = 108, H = rijen * PH + 14;
  const c = sizeCanvas(document.getElementById("kal"), W, H);
  const ink = css("--ink"), ink2 = css("--ink-2"), ink3 = css("--ink-3"),
        line = css("--line"), a1 = css("--accent");
  c.clearRect(0, 0, W, H); c.fillStyle = css("--surface-viz"); c.fillRect(0, 0, W, H);

  const alle = kolommen.flatMap(k => KH.map(v => v.slots[k].mediaan));
  const lo = 0, hi = Math.max(...alle) * 1.25;

  kolommen.forEach((k, i) => {
    const x0 = (i % cols) * PW + 14, y0 = Math.floor(i / cols) * PH + 12;
    const iw = PW - 34, ih = PH - 46;
    c.fillStyle = ink2; c.font = '600 11px "IBM Plex Mono", monospace';
    c.textAlign = "left"; c.textBaseline = "top";
    c.fillText(k.replace(/_/g, " ").replace("werkdag ", ""), x0, y0);

    c.strokeStyle = line; c.lineWidth = 1;
    c.beginPath(); c.moveTo(x0, y0 + 18 + ih + .5); c.lineTo(x0 + iw, y0 + 18 + ih + .5); c.stroke();
    c.beginPath(); c.moveTo(x0, y0 + 18.5); c.lineTo(x0 + iw, y0 + 18.5); c.stroke();
    c.fillStyle = ink3; c.font = '400 9.5px "IBM Plex Mono", monospace';
    c.textAlign = "left"; c.textBaseline = "bottom";
    c.fillText(hi.toFixed(0), x0, y0 + 17);      /* bovengrens van de schaal */
    c.textBaseline = "top"; c.fillText("0", x0, y0 + 18 + ih + 4);

    const X = j => KH.length === 1 ? x0 + 14 : x0 + j / (KH.length - 1) * iw;
    const Y = v => y0 + 18 + ih - (v - lo) / (hi - lo) * ih;
    if (KH.length > 1){
      c.strokeStyle = a1; c.lineWidth = 2; c.beginPath();
      KH.forEach((v, j) => j ? c.lineTo(X(j), Y(v.slots[k].mediaan))
                             : c.moveTo(X(j), Y(v.slots[k].mediaan)));
      c.stroke();
    }
    KH.forEach((v, j) => {
      c.beginPath(); c.arc(X(j), Y(v.slots[k].mediaan), 4, 0, 7);
      c.fillStyle = a1; c.fill();
      c.strokeStyle = css("--surface-viz"); c.lineWidth = 2; c.stroke();
    });
    const laatst = KH[KH.length - 1].slots[k].mediaan;
    c.fillStyle = ink; c.font = '600 12px "IBM Plex Mono", monospace';
    c.textAlign = "left"; c.textBaseline = "middle";
    c.fillText(laatst.toFixed(1) + " min", X(KH.length - 1) + 10, Y(laatst));
    c.fillStyle = ink3; c.font = '400 10px "IBM Plex Mono", monospace';
    c.textAlign = "left"; c.textBaseline = "top";
    c.fillText("v" + KH[KH.length - 1].versie, X(KH.length - 1) - 4, y0 + 18 + ih + 6);
  });

  const v = KH[KH.length - 1];
  document.getElementById("kalNote").innerHTML =
    `Mediane rijtijd over alle 9.702 zoneparen, per matrixversie. `
    + `Nu één versie: <b>v${v.versie}</b>, vastgelegd ${v.datum.replace("T"," ").slice(0,16)}, `
    + `met factoren uit ${v.bron === "meting" ? "metingen" : "schatting"} `
    + `(${v.toelichting}). Zodra de gemeten factoren erin gaan komt er een punt bij `
    + `en wordt het verschil zichtbaar als een lijn.`;
}

/* ================= tijdvak-keuze ================= */
const ctl = document.getElementById("slotCtl");
SLOTS.forEach(s => {
  const b = document.createElement("button");
  b.textContent = s.label.replace(/ \(.*/, "");
  b.setAttribute("aria-pressed", s.key === slot);
  b.onclick = () => {
    slot = s.key;
    [...ctl.children].forEach((x,i) => x.setAttribute("aria-pressed", SLOTS[i].key === slot));
    setOrigin(origin);
  };
  ctl.appendChild(b);
});

/* ================= statistiek ================= */
const off = []; for (let i=0;i<N;i++) for (let j=0;j<N;j++) if (i!==j) off.push(i*N+j);
const q = (a,p) => a[Math.min(a.length-1, Math.floor(a.length*p))];
const stats = SLOTS.map(s => {
  const v = off.map(k => D.m[s.key][k]/60).sort((a,b)=>a-b);
  return {label: s.label.replace(/ \(.*/,""), med:q(v,.5), p90:q(v,.9)};
});

function drawBars(){
  const c = sizeCanvas(document.getElementById("bars"), 980, 340);
  const W=980,H=340,L=52,R=16,T=54,B=52, iw=W-L-R, ih=H-T-B, max=27;
  const ink=css("--ink"), ink2=css("--ink-2"), ink3=css("--ink-3"),
        line=css("--line"), a1=css("--accent"), a2=css("--accent-2");
  c.clearRect(0,0,W,H); c.fillStyle=css("--surface-viz"); c.fillRect(0,0,W,H);
  c.strokeStyle=line; c.lineWidth=1; c.fillStyle=ink3;
  c.font='400 10.5px "IBM Plex Mono", monospace'; c.textAlign="right"; c.textBaseline="middle";
  for (let v=0; v<=max; v+=voidStep(max)){
    const y = T+ih - v/max*ih + .5;
    c.beginPath(); c.moveTo(L,y); c.lineTo(W-R,y); c.stroke(); c.fillText(v, L-10, y);
  }
  const gw = iw/stats.length, bw = Math.min(56, gw*0.3);
  stats.forEach((s,i) => {
    const cx = L + gw*i + gw/2;
    [[s.med,a1,-1],[s.p90,a2,1]].forEach(([v,col,side]) => {
      const h=v/max*ih, x=cx+side*1+(side<0?-bw:0), y=T+ih-h;
      c.fillStyle=col; c.beginPath(); c.roundRect(x,y,bw,h,[4,4,0,0]); c.fill();
      c.fillStyle=ink; c.font='600 11.5px "IBM Plex Mono", monospace';
      c.textAlign="center"; c.textBaseline="bottom"; c.fillText(v.toFixed(1), x+bw/2, y-6);
    });
    c.fillStyle=ink2; c.font='400 11px "IBM Plex Mono", monospace';
    c.textAlign="center"; c.textBaseline="top";
    const w = s.label.split(" ");
    c.fillText(w[0], cx, T+ih+12); c.fillText(w.slice(1).join(" "), cx, T+ih+27);
  });
  c.strokeStyle=css("--line-2"); c.beginPath();
  c.moveTo(L,T+ih+.5); c.lineTo(W-R,T+ih+.5); c.stroke();
  let lx=L;
  [["Mediane rit",a1],["p90 (traagste 10%)",a2]].forEach(([t,col]) => {
    c.fillStyle=col; c.beginPath(); c.roundRect(lx,18,10,10,2); c.fill();
    c.fillStyle=ink2; c.font='400 12px "IBM Plex Mono", monospace';
    c.textAlign="left"; c.textBaseline="middle"; c.fillText(t, lx+16, 23.5);
    lx += c.measureText(t).width + 44;
  });
  c.fillStyle=ink3; c.textAlign="right"; c.fillText("minuten", W-R, 23.5);
}
const voidStep = m => m <= 12 ? 2 : m <= 30 ? 5 : 10;

const ratios = off.filter(k => D.m.freeflow[k] > 0)
                  .map(k => D.m.werkdag_avondspits[k]/D.m.freeflow[k]);
function drawHist(){
  const c = sizeCanvas(document.getElementById("hist"), 980, 300);
  const W=980,H=300,L=52,R=16,T=44,B=52, iw=W-L-R, ih=H-T-B;
  const lo=1.0, hi=2.0, nb=25, bins=new Array(nb).fill(0);
  ratios.forEach(r => bins[Math.max(0,Math.min(nb-1,Math.floor((r-lo)/(hi-lo)*nb)))]++);
  const max = Math.max(...bins);
  const ink=css("--ink"), ink2=css("--ink-2"), ink3=css("--ink-3"),
        line=css("--line"), a1=css("--accent");
  c.clearRect(0,0,W,H); c.fillStyle=css("--surface-viz"); c.fillRect(0,0,W,H);
  c.strokeStyle=line; c.fillStyle=ink3;
  c.font='400 10.5px "IBM Plex Mono", monospace'; c.textAlign="right"; c.textBaseline="middle";
  for (let k=0;k<=4;k++){
    const y = T+ih - k/4*ih + .5;
    c.beginPath(); c.moveTo(L,y); c.lineTo(W-R,y); c.stroke();
    c.fillText(Math.round(max*k/4), L-10, y);
  }
  const bw = iw/nb; c.fillStyle=a1;
  bins.forEach((v,i) => { if (!v) return;
    const h=v/max*ih; c.beginPath(); c.roundRect(L+i*bw+1, T+ih-h, bw-2, h, [4,4,0,0]); c.fill(); });
  c.strokeStyle=css("--line-2"); c.beginPath();
  c.moveTo(L,T+ih+.5); c.lineTo(W-R,T+ih+.5); c.stroke();
  c.fillStyle=ink2; c.font='400 11px "IBM Plex Mono", monospace';
  c.textAlign="center"; c.textBaseline="top";
  for (let v=1.0; v<=2.001; v+=0.2) c.fillText("x"+v.toFixed(1), L+(v-lo)/(hi-lo)*iw, T+ih+12);
  const med = ratios.slice().sort((a,b)=>a-b)[Math.floor(ratios.length/2)];
  const mx = L + (med-lo)/(hi-lo)*iw;
  c.strokeStyle=css("--accent-2"); c.lineWidth=2; c.setLineDash([4,3]);
  c.beginPath(); c.moveTo(mx,T); c.lineTo(mx,T+ih); c.stroke(); c.setLineDash([]);
  c.fillStyle=ink; c.font='600 11.5px "IBM Plex Mono", monospace';
  c.textAlign="center"; c.textBaseline="bottom";
  c.fillText(`mediaan x${med.toFixed(2)}`, Math.min(Math.max(mx,L+50),W-R-50), T-8);
  c.fillStyle=ink3; c.font='400 11px "IBM Plex Mono", monospace';
  c.textAlign="left"; c.textBaseline="top"; c.fillText("zoneparen", L, 6);
}

(function(){
  const rows = off.filter(k => D.m.freeflow[k] > 300)
    .map(k => ({k, r: D.m.werkdag_avondspits[k]/D.m.freeflow[k]}))
    .sort((a,b)=>b.r-a.r).slice(0,12);
  const tb = document.querySelector("#topTable tbody");
  rows.forEach(({k,r}) => {
    const i = Math.floor(k/N), j = k%N, tr = document.createElement("tr");
    tr.innerHTML = `<td>${Z[i].naam}</td><td>${Z[j].naam}</td>
      <td class="n">${(D.meters[k]/1000).toFixed(1)}</td>
      <td class="n">${fmt(D.m.freeflow[k])}</td>
      <td class="n">${fmt(D.m.werkdag_avondspits[k])}</td>
      <td class="n"><b>x${r.toFixed(2)}</b></td>`;
    tb.appendChild(tr);
  });
})();

function renderAll(){
  vulLegend(); drawSched(); vulVoortgang();
  drawNdw(); vulDekking(); drawKal();
  document.getElementById("rampBar").style.background =
    `linear-gradient(90deg, ${ramp().join(",")})`;
  setOrigin(origin); drawBars(); drawHist();
}
/* start in het centrum: dat maakt de kaart meteen leesbaar */
origin = Math.max(0, Z.findIndex(z => z.gebied === "Rotterdam Centrum"));
renderAll();
document.fonts && document.fonts.ready.then(renderAll);
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", renderAll);
let rt; addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(renderAll, 150); });
new MutationObserver(renderAll).observe(document.documentElement,
  {attributes:true, attributeFilter:["data-theme"]});
</script>
