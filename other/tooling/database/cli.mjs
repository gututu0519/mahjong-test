import {build,repo} from '../build.mjs';
import {spawn} from 'node:child_process';
import {resolve} from 'node:path';
const [action,...args]=process.argv.slice(2);
await build();
const tool=action==='test'?'tests':action==='local'?'local-postgres':'migrate';
const child=spawn(process.execPath,[resolve(repo,'other/tooling/database',tool+'.mjs'),...(tool==='migrate'?[action]:[]),...args],{cwd:repo,stdio:'inherit'});
child.on('error',error=>{console.error(error.message);process.exitCode=1;});
child.on('exit',code=>process.exitCode=code??1);
