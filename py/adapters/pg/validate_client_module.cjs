// Register only; game dependencies and execute() are intentionally not run.
const fs = require('node:fs');
const vm = require('node:vm');
let registrations = 0;
try {
    vm.runInNewContext(fs.readFileSync(0, 'utf8'), {
        // Some supplied modules install DOM observers after System.register.
        // Model an empty page; never run observer callbacks or game execute().
        document: { querySelector() { return null; }, body: {} },
        MutationObserver: class { observe() {} disconnect() {} takeRecords() { return []; } },
        System: { register(...args) {
            if (typeof args[0] === 'string') args.shift();
            if (!Array.isArray(args[0]) || typeof args[1] !== 'function') {
                throw Error('Invalid System.register declaration');
            }
            registrations++;
        } },
    }, { timeout: 1000 });
    if (!registrations) throw Error('Expected a System.register module');
} catch (error) {
    console.error(error.message);
    process.exitCode = 1;
}
