const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const ts = require(path.join(root, 'frontend/node_modules/typescript'));
const rel = 'frontend/src/components/InvoiceMapHero.tsx';
const current = fs.readFileSync(path.join(root, rel), 'utf8');
const previous = execFileSync('git', ['show', `53a330d:${rel}`], { cwd: root, encoding: 'utf8' });
function mount(source, initialProgress = 0) {
  let gsapEffect, options, trigger;
  const nodes = new Map();
  const dependencies = {
    react: { useRef: value => ({ current: value }) },
    'react/jsx-runtime': { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
    'lenis/react': { ReactLenis: () => null },
    '@/components/InvoiceCursorFlock': { InvoiceCursorFlock: () => null },
    '@gsap/react': { useGSAP: fn => { gsapEffect = fn; } },
    gsap: { default: {
      registerPlugin: () => {},
      set: (target, values) => (Array.isArray(target) ? target : [target]).forEach(node => Object.assign(node.values, values)),
    } },
    'gsap/ScrollTrigger': { ScrollTrigger: { create: settings => {
      options = settings;
      trigger = { progress: initialProgress, kill() {} };
      // Deliberately emit no onUpdate/onRefresh here: the original failure mode.
      return trigger;
    } } },
  };
  const module = { exports: {} };
  vm.runInNewContext(ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
  }).outputText, {
    module, exports: module.exports, window: { innerHeight: 844 },
    require: name => { assert(name in dependencies, name); return dependencies[name]; },
  });
  function attach(element) {
    if (!element || typeof element !== 'object') return;
    if (Array.isArray(element)) return element.forEach(attach);
    const props = element.props;
    if (!props) return;
    const node = { values: {}, offsetHeight: props.className === 'source-invoice-content' ? 3376 : 1000 };
    if (props.className) nodes.set(props.className, node);
    if (typeof props.ref === 'function') props.ref(node);
    else if (props.ref) props.ref.current = node;
    attach(props.children);
  }
  attach(module.exports.InvoiceMapHero());
  gsapEffect();
  // The former outro is now a separately tested flock component, outside the
  // hero timeline. Compare every hero node without that unrelated empty node.
  const snapshot = () => Object.fromEntries([...nodes]
    .filter(([name]) => name !== 'source-invoice-outro')
    .map(([name, node]) => [name, node.values]));
  return {
    options, snapshot,
    update(progress) { trigger.progress = progress; options.onUpdate(trigger); },
    refresh(progress) { trigger.progress = progress; options.onRefresh(trigger); },
  };
}
function initialValues(h) {
  const s = h.snapshot();
  assert.equal(s['source-invoice-photo'].scale, 0.7);
  assert.equal(s['source-invoice-photo'].rotation, 0);
  assert.equal(s['source-invoice-photo-raw'].opacity, 1);
  assert.equal(s['source-invoice-photo-flat'].opacity, 0);
  assert.equal(s['source-invoice-grid'].opacity, 0);
  const markers = Object.entries(s).filter(([name]) => name.startsWith('source-invoice-marker '));
  assert.equal(markers.length, 12);
  for (const [, styles] of markers) assert.equal(styles.opacity, 0);
}
const h = mount(current);
initialValues(h);
h.update(0.7);
assert.equal(h.snapshot()['source-invoice-photo-flat'].opacity, 1);
h.refresh(0);
initialValues(h);
const old = mount(previous), fresh = mount(current);
const points = [0, .2, .34, .4, .42, .45, .5, .52, .54, .56, .6, .62, .7, .75, .78, .82, .85, .86, .9, 1];
for (const progress of points) {
  old.update(progress); fresh.update(progress);
  assert.equal(JSON.stringify(fresh.snapshot()), JSON.stringify(old.snapshot()), `curve at ${progress}`);
  const initialized = mount(current, progress);
  assert.equal(JSON.stringify(initialized.snapshot()), JSON.stringify(old.snapshot()), `initial position at ${progress}`);
}
const report = {
  source: rel, checked_at: new Date().toISOString(),
  scope: 'Actual component run with mocked refs, GSAP setters and ScrollTrigger lifecycle; visual return-home check remains for browser.',
  checks: {
    initial_zero_without_update_hides_all_12_markers: 'passed',
    refresh_to_zero_after_markers_visible: 'passed',
    existing_curves_unchanged: `${points.length} progress points passed against 53a330d`,
    restored_nonzero_scroll_initializes_current_progress: `${points.length} progress points passed`,
  },
};
console.log(JSON.stringify(report, null, 2));
