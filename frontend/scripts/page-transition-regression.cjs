// Local deterministic tests of the actual component; no production routes or data.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const ts = require(path.join(root, 'frontend/node_modules/typescript'));
const filename = path.join(root, 'frontend/src/components/PageTransitions.tsx');
const js = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
}).outputText;
const tick = async () => { for (let i = 0; i < 5; i++) await Promise.resolve(); };

function harness({ unsupported = false, reduced = false, throwCapture = false } = {}) {
  const refs = [], effects = [], layouts = [], listeners = new Map(), timers = new Map();
  const pushes = [], scrolls = [], transitions = [];
  let refIndex = 0, effectIndex = 0, layoutIndex = 0, timerId = 0, pathname = '/';
  let context, nextLayouts = [], nextEffects = [];
  const router = { push: (href, options) => pushes.push({ href, options }) };
  function effect(kind, callback, deps) {
    const list = kind === 'layout' ? layouts : effects;
    const index = kind === 'layout' ? layoutIndex++ : effectIndex++;
    const old = list[index];
    if (!old || deps.some((v, i) => v !== old.deps[i])) {
      (kind === 'layout' ? nextLayouts : nextEffects).push(() => {
        old?.cleanup?.();
        list[index] = { deps, cleanup: callback() };
      });
    }
  }
  const react = {
    createContext: () => (context = { Provider: {}, value: null }),
    useContext: c => c.value,
    startTransition: fn => fn(),
    useCallback: fn => fn,
    useRef: value => refs[refIndex++] ?? (refs[refIndex - 1] = { current: value }),
    useLayoutEffect: (fn, deps) => effect('layout', fn, deps),
    useEffect: (fn, deps) => effect('effect', fn, deps),
  };
  const win = {
    location: new URL('http://localhost:3105/'),
    matchMedia: () => ({ matches: reduced }),
    scrollTo: options => scrolls.push(options),
    setTimeout: (fn, ms) => { const id = ++timerId; timers.set(id, { fn, ms }); return id; },
    clearTimeout: id => timers.delete(id),
    addEventListener: (name, fn) => listeners.set(name, fn),
    removeEventListener: name => listeners.delete(name),
  };
  const doc = unsupported ? {} : { startViewTransition: callback => {
    if (throwCapture) throw new Error('capture unavailable');
    let complete, fail, updated = false, skipped = false, animated = false;
    const finished = new Promise((resolve, reject) => { complete = resolve; fail = reject; });
    const settle = () => { if (updated && (skipped || animated)) complete(); };
    const transition = {
      ready: Promise.resolve(), finished,
      skipTransition() { skipped = true; settle(); },
      get skipped() { return skipped; },
      runUpdate() { Promise.resolve().then(callback).then(() => { updated = true; settle(); }, fail); },
      finishAnimation() { animated = true; settle(); },
    };
    transitions.push(transition);
    return transition;
  } };
  const module = { exports: {} };
  const dependencies = {
    react,
    'react/jsx-runtime': { jsx: (type, props) => ({ type, props }) },
    'next/link': { default: () => null },
    'next/navigation': { useRouter: () => router, usePathname: () => pathname },
  };
  vm.runInNewContext(js, {
    exports: module.exports, module, URL, window: win, document: doc,
    require: name => { assert(name in dependencies, name); return dependencies[name]; },
  }, { filename });
  function render(next = pathname) {
    pathname = next;
    win.location = new URL(next, win.location);
    refIndex = effectIndex = layoutIndex = 0;
    nextLayouts = []; nextEffects = [];
    const result = module.exports.PageTransitions({ children: null });
    context.value = result.props.value;
    nextLayouts.forEach(fn => fn()); nextEffects.forEach(fn => fn());
    return result.props.value;
  }
  render();
  return {
    navigate: href => context.value(href), render, pushes, scrolls, transitions, timers,
    back: () => listeners.get('popstate')?.(),
    unmount: () => effects.forEach(e => e.cleanup?.()),
    timeout: () => { for (const [id, timer] of timers) { timers.delete(id); assert.equal(timer.ms, 4000); timer.fn(); } },
    link: props => module.exports.TransitionLink(props),
  };
}

const results = [];
async function check(name, fn) { await fn(); results.push({ name, status: 'passed' }); }
(async () => {
  await check('commit waits for the new path and resets long-page scroll', async () => {
    const h = harness(); h.navigate('/history'); assert.equal(h.pushes.length, 0);
    h.transitions[0].runUpdate(); await tick(); assert.equal(h.pushes[0].href, '/history');
    assert.equal(h.pushes[0].options.scroll, false); assert.equal(h.scrolls.length, 0);
    h.render('/history'); await tick(); assert.equal(h.scrolls[0].top, 0); assert.equal(h.timers.size, 0);
    h.transitions[0].finishAnimation(); await tick(); h.navigate('/ask'); assert.equal(h.transitions.length, 2);
  });
  await check('rapid repeated clicks keep only the first active destination', async () => {
    const h = harness(); h.navigate('/history'); h.navigate('/ask');
    assert.equal(h.transitions.length, 1); h.transitions[0].runUpdate(); await tick();
    h.navigate('/dashboard'); assert.equal(h.pushes.length, 1); assert.equal(h.pushes[0].href, '/history');
  });
  await check('Back before the update callback cancels stale push and unlocks navigation', async () => {
    const h = harness(); h.navigate('/history'); h.back(); h.navigate('/ask');
    assert.equal(h.transitions[0].skipped, true);
    h.transitions[0].runUpdate(); await tick(); assert.equal(h.pushes.length, 0);
    h.transitions[1].runUpdate(); await tick(); assert.equal(h.pushes.length, 1); assert.equal(h.pushes[0].href, '/ask');
    h.navigate('/dashboard'); assert.equal(h.transitions.length, 2);
  });
  await check('Back after push removes snapshot and preserves browser scroll restoration', async () => {
    const h = harness(); h.navigate('/history'); h.transitions[0].runUpdate(); await tick();
    h.back(); h.render('/batches/previous'); await tick();
    assert.equal(h.transitions[0].skipped, true); assert.equal(h.timers.size, 0); assert.equal(h.scrolls.length, 0);
    h.navigate('/ask'); assert.equal(h.transitions.length, 2);
  });
  await check('unmount before update does not push a stale route', async () => {
    const h = harness(); h.navigate('/history'); h.unmount(); h.transitions[0].runUpdate(); await tick();
    assert.equal(h.pushes.length, 0);
  });
  await check('four-second timeout releases snapshot and late route still scrolls to top', async () => {
    const h = harness(); h.navigate('/history'); h.transitions[0].runUpdate(); await tick();
    h.timeout(); await tick(); assert.equal(h.transitions[0].skipped, true); assert.equal(h.timers.size, 0);
    h.render('/history'); assert.equal(h.scrolls[0].top, 0); h.navigate('/ask'); assert.equal(h.transitions.length, 2);
  });
  await check('a new navigation after timeout supersedes the old scroll target', async () => {
    const h = harness(); h.navigate('/history'); h.transitions[0].runUpdate(); await tick(); h.timeout(); await tick();
    h.navigate('/ask'); h.transitions[1].runUpdate(); await tick(); h.render('/ask'); await tick();
    assert.equal(h.scrolls.length, 1); h.render('/history'); assert.equal(h.scrolls.length, 1);
  });
  for (const [name, options] of [['unsupported browser', { unsupported: true }], ['reduced motion', { reduced: true }], ['capture exception', { throwCapture: true }]]) {
    await check(`${name} uses the normal Next navigation`, async () => {
      const h = harness(options); h.navigate('/history'); assert.equal(h.transitions.length, 0);
      assert.equal(h.pushes[0].href, '/history'); assert.equal(h.pushes[0].options, undefined);
    });
  }
  await check('cross-page fragments and same-path queries preserve Next scrolling semantics', async () => {
    const h = harness(); h.navigate('/history#failed'); h.navigate('/?filter=all');
    assert.equal(h.transitions.length, 0); assert.equal(h.pushes.length, 2);
    assert(h.pushes.every(p => p.options === undefined));
  });
  await check('modified clicks, download, external and current-page links are not intercepted', async () => {
    const cases = [
      { ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { altKey: true }, { button: 1 },
      { target: '_blank' }, { download: true }, { href: 'https://example.com/' }, { href: '/' }, { defaultPrevented: true },
    ];
    for (const data of cases) {
      const h = harness(); let prevented = false;
      const event = {
        button: 0, defaultPrevented: false, ...data,
        currentTarget: { href: new URL(data.href ?? '/history', 'http://localhost:3105').href, target: data.target ?? '', hasAttribute: key => key === 'download' && !!data.download },
        preventDefault() { prevented = true; },
      };
      h.link({ href: data.href ?? '/history' }).props.onClick(event);
      assert.equal(prevented, false); assert.equal(h.transitions.length, 0);
    }
  });
  const output = {
    scope: 'Deterministic component regression with mocked React/router/DOM lifecycle. Not visual/browser acceptance.',
    source: path.relative(root, filename), checked_at: new Date().toISOString(),
    passed: results.length, checks: results,
  };
  console.log(JSON.stringify(output, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
