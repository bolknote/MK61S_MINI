'use strict';
// Read the sibling repository, and emit normalized data without modifying it.
const fs = require('node:fs');
const path = require('node:path');
const root = process.argv[2];
const rows = JSON.parse(fs.readFileSync(0, 'utf8'));
const {parseLordBssGame} = require(path.join(root, 'tests/emulator/lordbss.cjs'));
const {parseProgramText} = require(path.join(root, 'tests/emulator/mk61.cjs'));
const result = rows.map(row => {
  const file = path.join(root, 'games', row.program);
  const listing = fs.readFileSync(file, 'utf8');
  const description = fs.readFileSync(path.join(root, 'games', row.description), 'utf8');
  try {
    const parsed = parseLordBssGame(file);
    const decoded = parseProgramText(parsed.programText);
    if(!decoded.codes.length) throw new Error('Empty decoded program');
    if(decoded.diagnostics.length) throw new Error(JSON.stringify(decoded.diagnostics));
    return {...row, listing, description_text:description, bytes:Array.from(decoded.codes), parse_status:'ok'};
  } catch(error) {
    return {...row, listing, description_text:description, parse_status:'rejected', parse_error:String(error.message)};
  }
});
process.stdout.write(JSON.stringify(result));
