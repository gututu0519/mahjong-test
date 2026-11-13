const { projectRoot, clientRoot, diagnostics, formattedFixture } = require('../layout.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(clientRoot, 'local-frame-clock.js'), 'utf8');
function setup(mock = true) {
    let next = 0;
    const frames = new Map(), timers = new Map();
    const context = {
        URL, Map, location: { href: `http://localhost:8080/?mock=${mock ? 1 : 0}` },
        document: { hidden: false, documentElement: { dataset: {} } },
        performance: { now: () => 34 },
        setTimeout: fn => { const id = ++next; timers.set(id, fn); return id; },
        clearTimeout: id => timers.delete(id),
        requestAnimationFrame: fn => { const id = ++next; frames.set(id, fn); return id; },
        cancelAnimationFrame: id => frames.delete(id),
    };
    context.window = context;
    vm.runInNewContext(source, context);
    return { context, frames, timers };
}
{
    const { context: c, frames, timers } = setup();
    const calls = [];
    const id = c.requestAnimationFrame(t => calls.push(t));
    const timeout = [...timers.values()][0];
    frames.get(id)(16);
    timeout();
    assert.deepEqual(calls, [16], 'native frame wins and fires only once');
    assert.equal(timers.size, 0);
}
{
    const { context: c, frames, timers } = setup();
    const calls = [];
    const id = c.requestAnimationFrame(t => calls.push(t));
    const native = frames.get(id);
    [...timers.values()][0]();
    native(1000);
    assert.deepEqual(calls, [34], 'fallback uses a monotonic timestamp and excludes late native callbacks');
    assert.equal(frames.size, 0);
}
{
    const { context: c, frames, timers } = setup();
    let calls = 0;
    const id = c.requestAnimationFrame(() => calls++);
    const timeout = [...timers.values()][0], native = frames.get(id);
    c.cancelAnimationFrame(id);
    timeout(); native(16);
    assert.equal(calls, 0, 'cancellation removes both scheduling paths');
    assert.equal(timers.size, 0);
}
{
    const { context: c, frames, timers } = setup();
    c.document.hidden = true;
    let calls = 0;
    const id = c.requestAnimationFrame(() => calls++);
    [...timers.values()][0]();
    assert.equal(calls, 0, 'hidden tabs do not run the fallback');
    c.document.hidden = false;
    frames.get(id)(1000);
    assert.equal(calls, 1);
}
{
    const { context: c, timers } = setup(false);
    c.requestAnimationFrame(() => {});
    assert.equal(timers.size, 0, 'non-mock launches are unchanged');
}
console.log('PASS local frame clock: native, throttled, cancellation, hidden, non-mock');
