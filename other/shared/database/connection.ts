import { DatabaseSync as SQLite } from 'node:sqlite';
import { Worker } from 'node:worker_threads';
import { resolve } from 'node:path';
let worker: Worker | undefined, sequence = 0;
// One synchronous request at a time per JS isolate. Reuse the transport buffer;
// allocating 32 MiB for every SQL statement exhausts memory during long rounds.
let transport: SharedArrayBuffer | undefined;
let poisoned=false;
const call = (command: string, value: any = {}) => {
  if(poisoned)throw Object.assign(Error('Database worker must be restarted after an uncertain result'),{code:'DATABASE_RESULT_UNKNOWN'});
  if(!worker) {
    worker=new Worker(new URL('./worker.js', import.meta.url), {workerData:{config:process.env.GTT_PG_CONFIG}});
    worker.unref();
  }
  const buffer=transport??=new SharedArrayBuffer(32*1024*1024), state=new Int32Array(buffer,0,2);
  Atomics.store(state,0,0);Atomics.store(state,1,0);
  worker.postMessage({command,value,buffer});
  if(Atomics.wait(state,0,0,120000)==='timed-out') {
    poisoned=true;
    // The result may be committed. Never transparently retry a timed-out write.
    throw Object.assign(Error('PostgreSQL result is unknown; retry the original business request.'),{code:'DATABASE_RESULT_UNKNOWN'});
  }
  const result=JSON.parse(Buffer.from(buffer,8,Atomics.load(state,1)).toString('utf8'));
  if(result.error) throw Object.assign(Error(result.error.message),{code:result.error.code});
  return result.value;
};
/** Preserves existing synchronous callers; PostgreSQL I/O runs in a worker.
 * SQLite is only selected explicitly by absence of the PostgreSQL runtime config
 * (legacy fixtures, offline import and historical fallback).
 */
export class DatabaseSync {
  sqlite?: SQLite;
  id?: number;
  private transaction=false;
  get isTransaction() { return this.sqlite ? this.sqlite.isTransaction : this.transaction; }
  constructor(path: string, options?: any) {
    if(!process.env.GTT_PG_CONFIG) {const {kind,...sqliteOptions}=options??{};this.sqlite=new SQLite(path,sqliteOptions);return;}
    this.id=++sequence;
    call('open',{id:this.id,path:resolve(path),kind:options?.kind});
  }
  prepare(sql: string): any {
    if(this.sqlite) return this.sqlite.prepare(sql);
    const execute=(args: any[])=>{const result=call('query',{id:this.id,sql,args});this.track(sql);return result;};
    return {
      columns:()=>/^(?:\s*SELECT|\s*WITH|\s*PRAGMA)|\bRETURNING\b/i.test(sql)?[{name:'result'}]:[],
      run:(...args: any[])=>{const result=execute(args);return {changes:result.changes,lastInsertRowid:result.lastInsertRowid??0};},
      all:(...args: any[])=>execute(args).rows,
      get:(...args: any[])=>execute(args).rows[0],
    };
  }
  exec(sql: string) {
    if(this.sqlite) {this.sqlite.exec(sql);return;}
    call('exec',{id:this.id,sql});
    this.track(sql);
  }
  private track(sql: string) {if(/^\s*BEGIN\b/i.test(sql))this.transaction=true;if(/^\s*(COMMIT|ROLLBACK)\b/i.test(sql))this.transaction=false;}
  close() {if(this.sqlite)this.sqlite.close();else call('close',{id:this.id});}
}
