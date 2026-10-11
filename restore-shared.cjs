// Restore supplied original response byte-for-byte after checking the baseline backup.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const hash = b => crypto.createHash('sha256').update(b).digest('hex');
const target = 'shared/984721902a/996b5422dd.27a51.js';
const read = p => fs.readFileSync(path.join(__dirname, p));
const original = read('original-response.js');
const before = read(target);
const backup = read('diagnostics/backup/' + target);
if (hash(original) !== 'caf80681943be7e1250d495bbdee2e07d5e4e9dae2c65fad882d2eaf7358aa58') throw Error('Source changed; review before restoring');
if (!before.equals(backup) && !before.equals(original)) throw Error('Current file differs from baseline and source; refusing overwrite');
fs.writeFileSync(path.join(__dirname, target), original);
if (!read(target).equals(original)) throw Error('Restore verification failed');
const record = { target, backup: 'diagnostics/backup/' + target, source: 'original-response.js', beforeSha256: hash(before), afterSha256: hash(original), bytes: original.length };
fs.writeFileSync(path.join(__dirname, 'diagnostics/restore.json'), JSON.stringify(record, null, 2));
console.log(record);
