import {test} from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {resolve,dirname} from 'node:path';
import {gatewayClientRoot} from '../../gateway/src/assets.js';
const bundle=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
test('legacy package-local Buffalo client root resolves to the unified resources tree',()=>{
  const expected=resolve(bundle,'resources/clients/buffalo-win');
  assert.equal(gatewayClientRoot(),expected);
  assert.equal(gatewayClientRoot(resolve(bundle,'clients/buffalo-win')),expected);
  if(process.platform==='win32')assert.equal(gatewayClientRoot(resolve(bundle,'clients/buffalo-win').toUpperCase()),expected);
});
test('explicit external client mounts are not silently replaced by the built-in bootstrap',()=>{
  const external=resolve(bundle,'../clients/buffalo-win');
  assert.equal(gatewayClientRoot(external),external);
  const missing=resolve(bundle,'custom-missing-mount');
  assert.equal(gatewayClientRoot(missing),missing);
});
