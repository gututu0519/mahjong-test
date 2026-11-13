import {parentPort,workerData} from 'node:worker_threads';
import {DB} from '../shared/core.js';
const db=new DB(workerData.path,'control');
try {
  for(let i=0;i<20;i++)db.tx(()=>{
    const old=db.get("SELECT value FROM control_counters WHERE name='pg-concurrency'").value;
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,2);
    db.run("UPDATE control_counters SET value=? WHERE name='pg-concurrency'",old+1);
  });
  parentPort!.postMessage({ok:true});
} catch(error: any){parentPort!.postMessage({error:error.message});}
finally{db.close();}
