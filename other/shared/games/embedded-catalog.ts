import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

// Embedded engines are loaded only by callers that actually execute them.
// Remote administration uses descriptors and registered compute services.
export function embeddedDefinitions(): any {
  return createRequire(import.meta.url)(fileURLToPath(import.meta.resolve('../migrated/py/games/catalog.js'))).definitions;
}
