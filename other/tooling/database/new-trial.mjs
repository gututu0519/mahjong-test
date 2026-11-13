import pg from 'pg';
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {root} from './inventory.mjs';
const path=resolve(root,'gateway/instance/data/postgres-migration.json'), c=JSON.parse(readFileSync(path,'utf8'));
const {databaseSettings}=await import('./settings.mjs');const settings=databaseSettings();
const client=new pg.Client({...settings.connection,database:'postgres'});await client.connect();
try {
  const trial=settings.database+'_trial_'+Date.now();
  await client.query('CREATE DATABASE "'+trial+'" TEMPLATE template0');
  c.previousTrials=[...(c.previousTrials??[]),c.trial];c.trial=trial;
  writeFileSync(path,JSON.stringify(c,null,2)+'\n',{mode:0o600});
  console.log('Created fresh rehearsal database '+trial+'; earlier rehearsals retained.');
} finally {await client.end();}
