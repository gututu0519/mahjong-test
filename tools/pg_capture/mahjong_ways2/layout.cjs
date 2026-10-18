const path = require('node:path');
const projectRoot = path.resolve(__dirname, '../../..');
module.exports = {
  projectRoot,
  clientRoot: path.join(projectRoot, 'clients/mahjong-ways2'),
  diagnostics: path.join(projectRoot, 'diagnostics/mahjong-ways2'),
  formattedFixture: path.join(projectRoot, 'server/tests/fixtures/pg-client/formatted-index.js'),
};
