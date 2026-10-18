const { projectRoot, clientRoot, diagnostics, formattedFixture } = require('../layout.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { spawnSync } = require('node:child_process');

const modules = {
    b4d9192613: ['fdcbe10535', '0dd866175d', '8487273957', '65d1a9fde7'],
    c03a2652ad: ['./f5fe73e9f2.508eb.js'],
    '0b68fe0fe5': ['65d1a9fde7', '0dd866175d'],
    c2fc9a6814: ['65d1a9fde7', '0dd866175d'],
    '4528468aab': ['65d1a9fde7', '0dd866175d'],
    '75d1870451': ['65d1a9fde7', '0dd866175d', './df8e923416.9a66e.json'],
};

/* 不加载缺失依赖，只验证现有模块在受限时间内完成注册且依赖声明不变。 */
const names = fs.readdirSync(path.join(clientRoot, 'shared')).filter(name =>
    fs.existsSync(path.join(clientRoot, 'shared', name, 'index.js')));
for (const name of names) {
    const expected = modules[name];
    const filename = path.join(clientRoot, 'shared', name, 'index.js');
    const transformed = spawnSync('python', ['-c',
        'import sys; from server.adapters.pg.client_modules import repair_source; sys.stdout.buffer.write(repair_source(sys.stdin.buffer.read().decode("utf-8-sig")).encode("utf-8"))'],
        { cwd: projectRoot, input: fs.readFileSync(filename), encoding: 'utf8' });
    assert.equal(transformed.status, 0, transformed.stderr);
    const source = transformed.stdout;
    for (let run = 0; run < 2; run++) {
        let calls = 0;
        let dependencies;
        vm.runInNewContext(source, {
            document: { querySelector() { return null; }, body: {} },
            MutationObserver: class { observe() {} },
            System: {
                /** 记录模块注册，防止吞掉初始化错误后产生假通过。 */
                register(value, declaration) {
                    calls++;
                    dependencies = Array.from(value);
                    assert.equal(typeof declaration, 'function');
                },
            },
        }, { filename, timeout: 1000 });
        assert.equal(calls, 1);
        if (expected) assert.deepEqual(dependencies, expected);
        else assert.ok(Array.isArray(dependencies), '新模块必须正常注册并声明依赖');
    }
    console.log('PASS', name, '首次及重复初始化均完成');
}
