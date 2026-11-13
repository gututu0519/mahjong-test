const { projectRoot, clientRoot, diagnostics, formattedFixture } = require('./layout.cjs');
// Restore supplied original response byte-for-byte after checking the baseline backup.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const hash = b => crypto.createHash('sha256').update(b).digest('hex');
const target = 'shared/984721902a/996b5422dd.27a51.js';
const read = p => fs.readFileSync(path.join(clientRoot, p));
const original = read('fixtures/original-shared-response.js');
const before = read(target);
const backup = fs.readFileSync(path.join(diagnostics, 'backup', target));
if (hash(original) !== 'caf80681943be7e1250d495bbdee2e07d5e4e9dae2c65fad882d2eaf7358aa58') throw Error('Source changed; review before restoring');
if (!before.equals(backup) && !before.equals(original)) throw Error('Current file differs from baseline and source; refusing overwrite');
fs.writeFileSync(path.join(clientRoot, target), original);
if (!read(target).equals(original)) throw Error('Restore verification failed');
const record = { target, backup: 'diagnostics/mahjong-ways2/backup/' + target, source: 'clients/mahjong-ways2/fixtures/original-shared-response.js', beforeSha256: hash(before), afterSha256: hash(original), bytes: original.length };
fs.writeFileSync(path.join(diagnostics, 'restore.json'), JSON.stringify(record, null, 2));
console.log(record);
