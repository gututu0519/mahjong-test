import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,writeFileSync,readdirSync,rmSync,existsSync,renameSync,mkdirSync,copyFileSync,cpSync} from 'node:fs';
import {resolve,join,dirname} from 'node:path';
import {tmpdir} from 'node:os';
import {spawn,execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {randomBytes} from 'node:crypto';
import {artifactPath,extractArchive} from './archive.mjs';
import {digest,verifyInventory,verifyPair,safePath} from './game-bundle.mjs';
import {gameProcessEnvironment} from '../dist/shared/config/environment.js';
import {npmExecutable} from './install-dependencies.mjs';
import {encode} from '../dist/shared/core.js';

const release=resolve(process.argv[2]),record=JSON.parse(readFileSync(join(release,existsSync(join(release,'release.json'))?'release.json':'RELEASE.json'),'utf8'));
assert.ok(['game-deployment-bundle','game-component-delivery'].includes(record.kind));
const split=record.kind==='game-component-delivery';
const name=process.argv[3]??'verification.json';assert.match(name,/^[A-Za-z0-9._-]+\.json$/);
const report=join(release,name);assert.equal(existsSync(report),false);
const temp=mkdtempSync(join(tmpdir(),'gtt-game-bundle-'));
let child;
try {
  const artifact=record.artifacts[0],bytes=readFileSync(artifactPath(release,record,artifact));
  assert.equal(digest(bytes),artifact.sha256);assert.equal(bytes.length,artifact.size);
  const flat=split&&record.format===4&&record.serve.archive_root==='';
  const extractTo=flat?join(temp,safePath(record.serve.directory)):temp;
  if(flat)mkdirSync(extractTo);
  extractArchive(artifactPath(release,record,artifact),extractTo);
  const manifest=JSON.parse(readFileSync(join(split?release:temp,'RELEASE.json'),'utf8'));
  assert.equal(manifest.build_id,record.build_id);assert.equal(manifest.game,record.game);
  safePath(manifest.client.directory);safePath(manifest.serve.directory);
  if(split) {
    assert.equal(manifest.client.format,'directory');assert.equal(manifest.serve.format,'zip');
    const delivery=resolve(release,record.artifact_directory);
    const actualClient=join(delivery,manifest.client.directory);
    verifyInventory(actualClient,manifest.client.files);
    const actualServe=join(delivery,manifest.serve.directory);
    if(manifest.format===4){
      assert.equal(artifact.file,manifest.serve.directory+'.zip');
      assert.equal(artifact.sha256,manifest.serve.sha256);
      const published=join(release,'publication-bundle'),staged=join(temp,manifest.client.directory);
      const m=JSON.parse(readFileSync(join(published,'manifest.json')));
      assert.equal(m.component_version,manifest.client.release);assert.equal(m.game,manifest.game);
      assert.equal(m.prefix,`releases/${manifest.game}/${manifest.client.release}`);
      assert.equal(m.component_version.split('.')[0],manifest.serve.release.split('.')[0]);
      verifyInventory(actualClient,m.files);verifyInventory(join(published,'objects'),m.files);
      mkdirSync(staged);copyFileSync(join(published,'manifest.json'),join(staged,'manifest.json'));
      cpSync(join(published,'bootstrap'),join(staged,'bootstrap'),{recursive:true});
      cpSync(actualClient,join(staged,'objects'),{recursive:true});
    }else if(manifest.format===3) {
      assert.equal(manifest.gateway.directory,'gateway-'+manifest.client.release);
      safePath(manifest.gateway.directory);
      const gateway=join(actualServe,manifest.gateway.directory);
      verifyInventory(gateway,manifest.gateway.files);
      const privateManifest=JSON.parse(readFileSync(join(gateway,'manifest.json')));
      verifyInventory(actualClient,privateManifest.files);
      const installed=mkdtempSync(join(tmpdir(),'gtt-verified-install-'));
      try {
        execFileSync(process.execPath,[join(gateway,'install-delivery-frontend.mjs'),fileURLToPath(new URL('./install-frontend.mjs',import.meta.url)),installed],{stdio:'pipe'});
        renameSync(join(installed,manifest.client.release),join(temp,manifest.client.directory));
      } finally {rmSync(installed,{recursive:true,force:true});}
    } else verifyInventory(actualServe,[{path:manifest.serve.file,size:manifest.serve.size,sha256:manifest.serve.sha256}]);
    if(!flat){
      safePath(manifest.serve.archive_root);
      renameSync(join(temp,manifest.serve.archive_root),join(temp,manifest.serve.directory));
    }
    if(manifest.format<3)for(const file of manifest.client.files) {
      const destination=join(temp,manifest.client.directory,file.path);mkdirSync(dirname(destination),{recursive:true});copyFileSync(join(actualClient,file.path),destination);
    }
  }
  assert.deepEqual(readdirSync(temp,{withFileTypes:true}).filter(item=>item.isDirectory()).map(item=>item.name).sort(),[manifest.client.directory,manifest.serve.directory].sort());
  if(!split)verifyInventory(temp,manifest.files,['RELEASE.json']);
  const serve=join(temp,manifest.serve.directory),client=join(temp,manifest.client.directory);
  const pair=verifyPair(serve,client,manifest.game);
  assert.equal(manifest.client.directory,`${manifest.game}-client-${manifest.format===4?pair.manifest.component_version:pair.manifest.release}`);
  assert.equal(manifest.serve.directory,`${manifest.game}-serve-${pair.identity.release}`);
  assert.deepEqual(record.components.client,manifest.client);assert.deepEqual(record.components.serve,manifest.serve);
  assert.equal(digest(readFileSync(join(client,'manifest.json'))),manifest.client.manifest_sha256);
  assert.equal(digest(readFileSync(join(serve,'release-manifest.json'))),manifest.serve.source_manifest_sha256);
  verifyInventory(serve,JSON.parse(readFileSync(join(serve,'release-manifest.json'),'utf8')).files,['release-manifest.json']);
  // Negative checks: wrong game identity and changed component bytes must fail.
  assert.throws(()=>verifyPair(serve,client,'not-this-game'),/identity/);
  const clientManifestPath=join(client,'manifest.json'),clientManifestBytes=readFileSync(clientManifestPath);
  const wrongContract={...pair.manifest,client_contract:'incompatible-contract'};
  wrongContract.content_hash=digest(Buffer.from(encode({game:wrongContract.game,client_contract:wrongContract.client_contract,files:wrongContract.files,bootstrap:wrongContract.bootstrap})));
  writeFileSync(clientManifestPath,JSON.stringify(wrongContract));
  assert.throws(()=>verifyPair(serve,client,manifest.game),/contract mismatch/);
  writeFileSync(clientManifestPath,clientManifestBytes);
  const rulesPath=join(serve,'config/game.json'),rules=readFileSync(rulesPath);
  writeFileSync(rulesPath,JSON.stringify({...JSON.parse(rules),tampered:true}));
  assert.throws(()=>verifyPair(serve,client,manifest.game),/rule versions differ/);
  writeFileSync(rulesPath,rules);
  const first=pair.manifest.files[0],asset=join(client,'objects',first.path),original=readFileSync(asset);
  writeFileSync(asset,Buffer.concat([original,Buffer.from('changed')]));
  assert.throws(()=>verifyPair(serve,client,manifest.game));
  const checkedClient=split&&manifest.format>=3?join(client,'objects'):client;
  if(split)assert.throws(()=>verifyInventory(checkedClient,manifest.client.files));
  writeFileSync(asset,original);
  renameSync(asset,asset+'.missing-test');
  assert.throws(()=>verifyPair(serve,client,manifest.game));renameSync(asset+'.missing-test',asset);
  if(split) {
    const extra=join(checkedClient,'unexpected.txt');writeFileSync(extra,'not in manifest');
    assert.throws(()=>verifyInventory(checkedClient,manifest.client.files),/unlisted/);rmSync(extra);
    verifyInventory(checkedClient,manifest.client.files);
  }
  const secret=randomBytes(32).toString('hex'),key=join(temp,'probe.key');writeFileSync(key,secret,{mode:0o600});
  const envFile=join(temp,'probe.env');
  writeFileSync(envFile,`GAME_BIND=127.0.0.1\nGAME_PORT=0\nGAME_SECRET_FILE=${key.replaceAll('\\','/')}\n`,{mode:0o600});
  const environment=gameProcessEnvironment(process.env);
  for(const key of Object.keys(environment))if(key.startsWith('GAME_')||key==='GTT_RESOURCE_ROOT')delete environment[key];
  let output='';
  const port=await new Promise((ok,fail)=>{
    child=spawn(process.execPath,[pair.service.entry_point,'--env-file',envFile],{cwd:serve,env:{...environment,npm_execpath:npmExecutable()},windowsHide:true,stdio:['ignore','pipe','pipe']});
    const timer=setTimeout(()=>fail(Error('Compute probe timeout: '+output)),120000);
    const exited=code=>{clearTimeout(timer);fail(Error('Compute probe exited '+code+': '+output));};
    child.once('error',error=>{clearTimeout(timer);fail(error);});child.once('exit',exited);
    child.stderr.on('data',bytes=>output+=bytes);
    child.stdout.on('data',bytes=>{output+=bytes;const match=/listening on 127\.0\.0\.1:(\d+)/.exec(output);if(match){clearTimeout(timer);child.off('exit',exited);ok(Number(match[1]));}});
  });
  const request=async(action,value={})=>{
    const response=await fetch(`http://127.0.0.1:${port}/v1/${action}`,{method:'POST',headers:{'content-type':'application/json',authorization:'Bearer '+secret},body:JSON.stringify({...value,expected_release:pair.identity.release}),signal:AbortSignal.timeout(10000)});
    const body=await response.json();assert.equal(response.status,200,JSON.stringify(body));return body.data;
  };
  const descriptor=await request('describe');
  assert.equal(descriptor.game_id,manifest.game);assert.equal(descriptor.release,pair.identity.release);
  assert.equal(descriptor.client_contract,pair.manifest.client_contract);
  assert.equal(descriptor.ruleset_id,pair.identity.descriptor.ruleset_id);
  assert.deepEqual(descriptor.config,pair.identity.descriptor.config);
  assert.deepEqual(await request('initial',{seed:'bundle-verification'}),await request('initial',{seed:'bundle-verification'}));
  writeFileSync(report,JSON.stringify({build_id:record.build_id,game:manifest.game,node:process.version,verified_at:new Date().toISOString(),checks:['zip-sha256','exactly-two-versioned-directories','complete-file-manifest','private-public-separation','source-service-manifest','client-service-rules-match','wrong-game-and-tamper-rejected','minimal-instance-env-defaults','actual-compute-identity-release-contract','deterministic-initial-state'],scope:'Local unpack and compute probe only; not S3/CDN publication, full game or wallet acceptance.'},null,2)+'\n',{flag:'wx'});
  console.log((split?'Uncompressed client and service ZIP delivery verified: ':'Complete game bundle verified: ')+manifest.game);
} finally {
  if(child&&child.exitCode===null&&child.signalCode===null)await new Promise(ok=>{child.once('exit',ok);child.kill();});
  rmSync(temp,{recursive:true,force:true});
}
