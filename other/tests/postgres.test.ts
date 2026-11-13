import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {Worker} from 'node:worker_threads';
import {DB} from '../shared/core.js';
test('PostgreSQL independent connections serialize read-modify-write transactions and roll back failed writes',{skip:!process.env.GTT_PG_CONFIG},async()=>{
  const dir=mkdtempSync(join(tmpdir(),'gtt-postgres-concurrency-')),path=join(dir,'control.db'),db=new DB(path,'control');
  try {
    db.run("INSERT INTO control_counters VALUES('pg-concurrency',0)");
    await Promise.all([1,2].map(()=>new Promise<void>((ok,fail)=>{
      const worker=new Worker(new URL('./postgres-writer.js',import.meta.url),{workerData:{path}});
      worker.on('message',message=>message.ok?ok():fail(Error(message.error)));
      worker.on('error',fail);
      worker.on('exit',code=>{if(code)fail(Error('Writer exited '+code));});
    })));
    assert.equal(db.get("SELECT value FROM control_counters WHERE name='pg-concurrency'").value,40);
    assert.throws(()=>db.tx(()=>{
      db.run("UPDATE control_counters SET value=999 WHERE name='pg-concurrency'");
      db.run("INSERT INTO control_counters VALUES('pg-concurrency',5)");
    }));
    assert.equal(db.get("SELECT value FROM control_counters WHERE name='pg-concurrency'").value,40);
  } finally{db.close();rmSync(dir,{recursive:true,force:true});}
});
