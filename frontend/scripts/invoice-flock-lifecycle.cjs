// Component lifecycle regression in an isolated DOM/router-free harness.
// Actual desktop / narrow viewport appearance is verified separately in browser.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const ts = require(path.join(root,'frontend/node_modules/typescript'));
const code = ts.transpileModule(fs.readFileSync(path.join(root,'frontend/src/components/InvoiceCursorFlock.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2020}}).outputText;

function harness({coarse=false,reduced=false}={}) {
  const effects=[],ticks=new Set(),tweens=[],observers=[],media=[];
  const target=()=>({listeners:new Map(),addEventListener(k,v){this.listeners.set(k,v)},removeEventListener(k){this.listeners.delete(k)}});
  let draws=0,clears=0;
  const ctx={clearRect(){clears++},setTransform(){},drawImage(){draws++}};
  const section=Object.assign(target(),{dataset:{loadedCount:'0',failedCount:'0'},getBoundingClientRect:()=>({left:240,top:100,width:1000,height:800})});
  const canvas={width:0,height:0,getContext:()=>ctx};
  const doc=Object.assign(target(),{hidden:false});
  const win=Object.assign(target(),{devicePixelRatio:3,requestAnimationFrame:f=>(f(),1),cancelAnimationFrame(){},matchMedia(query){const m=Object.assign(target(),{matches:query.includes('reduced')?reduced:coarse});media.push(m);return m;}});
  class Observer {constructor(fn){this.fn=fn;this.disconnected=false;observers.push(this)} observe(){} disconnect(){this.disconnected=true}}
  class Img {constructor(){this.naturalWidth=900;this.naturalHeight=1100} set src(value){this.url=value;this.onload?.()}}
  const gsap={ticker:{add:f=>ticks.add(f),remove:f=>ticks.delete(f)},to(obj,opts){const t={obj,opts,isPaused:false,killed:false,paused(v){this.isPaused=v;return this},kill(){this.killed=true}};tweens.push(t);return t}};
  let refIndex=0;
  const module={exports:{}};
  const requireMock=name=>name==='react'?{useEffect:f=>effects.push(f),useRef:()=>({current:refIndex++===0?section:canvas})}:name==='react/jsx-runtime'?{jsx:()=>null,jsxs:()=>null}:name==='gsap'?{__esModule:true,default:gsap}:null;
  vm.runInNewContext(code,{module,exports:module.exports,require:requireMock,window:win,document:doc,Image:Img,ResizeObserver:Observer,IntersectionObserver:Observer});
  module.exports.InvoiceCursorFlock();
  const cleanup=effects[0]();
  const view=visible=>observers[1].fn([{isIntersecting:visible}]);
  const finish=()=>{const t=tweens.at(-1);t.obj.intensity=t.opts.intensity;t.opts.onComplete?.()};
  const point={pointerType:'mouse',clientX:800,clientY:350};
  return {section,canvas,win,doc,media,observers,ticks,tweens,view,finish,point,cleanup,draws:()=>draws,clears:()=>clears};
}

const checks=[];
function test(name,fn){fn();checks.push({name,status:'passed'})}
test('six artworks load in stable slots and offscreen canvas never starts a ticker',()=>{const h=harness();assert.equal(h.section.dataset.loadedCount,'6');assert.equal(h.ticks.size,0);assert.equal(h.canvas.width,2000);assert.equal(h.canvas.height,1600);h.cleanup()});
test('pointer enters and leaves: reveal draws artwork then releases ticker',()=>{const h=harness();h.view(true);h.section.listeners.get('pointerenter')(h.point);h.finish();assert.equal(h.ticks.size,1);for(const f of h.ticks)f(0,16);assert.ok(h.draws()>0);h.section.listeners.get('pointerleave')();h.finish();assert.equal(h.ticks.size,0);assert.equal(h.section.dataset.flockState,'idle');h.cleanup()});
test('offscreen / hidden pauses animation and coming back resumes it',()=>{const h=harness();h.view(true);h.section.listeners.get('pointerenter')(h.point);h.finish();assert.equal(h.ticks.size,1);h.view(false);assert.equal(h.ticks.size,0);h.view(true);assert.equal(h.ticks.size,1);h.doc.hidden=true;h.doc.listeners.get('visibilitychange')();assert.equal(h.ticks.size,0);h.doc.hidden=false;h.doc.listeners.get('visibilitychange')();assert.equal(h.ticks.size,1);h.cleanup()});
for(const mode of ['coarse','reduced'])test(mode+' mode draws a static center gallery without running a ticker',()=>{const h=harness({[mode]:true});h.view(true);assert.equal(h.section.dataset.flockMode,'static');assert.equal(h.ticks.size,0);assert.ok(h.draws()>0);h.section.listeners.get('pointermove')({...h.point,pointerType:'touch'});assert.equal(h.tweens.length,0);h.cleanup()});
test('unmount removes all animation callbacks, observers and event listeners',()=>{const h=harness();h.view(true);h.section.listeners.get('pointerenter')(h.point);h.cleanup();assert.equal(h.ticks.size,0);assert.ok(h.observers.every(o=>o.disconnected));assert.equal(h.section.listeners.size,0);assert.equal(h.win.listeners.size,0);assert.equal(h.doc.listeners.size,0);assert.ok(h.media.every(m=>m.listeners.size===0));assert.ok(h.tweens.every(t=>t.killed))});
const report={scope:'Isolated component lifecycle harness, not a touch-device or browser-emulation test',passed:checks.length,checks};
console.log(JSON.stringify(report));
