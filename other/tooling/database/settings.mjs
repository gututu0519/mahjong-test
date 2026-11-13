import {resolve} from 'node:path';
import {root} from './inventory.mjs';
import {readPostgresConfig} from '../../runtime/server/dist/shared/config/environment.js';
export function databaseSettings() {
  const config=readPostgresConfig(resolve(root,'gateway/instance/data/postgres-migration.json'));
  return {...config,...config.connection};
}
export {readPostgresConfig};
