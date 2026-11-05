/* Headless adapter for the pinned, unmodified UrqW interpreter.
 * Run: node oracle.js UPSTREAM SOURCE_UTF8 MODE [c:0|i:text|k:13 ...]
 * Game JavaScript is disabled by default. URQ_ORACLE_ADAPTATION selects only
 * a hash-pinned CC0 helper for offline adaptation comparisons. No browser UI. */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const crypto = require('crypto');
const [upstream, source, selectedMode, ...commands] = process.argv.slice(2);
if (!source) process.exit(2);
let rng = 0x61F17A35;
const random = () => {
  rng ^= rng << 13; rng ^= rng >>> 17; rng ^= rng << 5;
  return (rng >>> 0) / 4294967296;
};
const strip = text => String(text).replace(/<br\s*\/?>|<\/p>|<\/div>/gi, '\n')
  .replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&')
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"')
  .replace(/&#(\d+);/g, (_, code) => String.fromCodePoint(Number(code)));
const emit = event => process.stdout.write(JSON.stringify(event) + '\n');
const mode = selectedMode === 'urqw1' ? 'urqw' : selectedMode;
const linkCaptions = [];
const jquery = () => ({hide() {}});
jquery.each = (object, callback) => {
  for (const key of Object.keys(object)) callback(key, object[key]);
};
const context = {
  mode, manifest: {}, urqw_version: '1.1', htmlSupport: !['dosurq','ripurq'].includes(mode), files: null,
  murmurhash3_32() { return 0; }, isFloat(value) { return Number(value) === value && value % 1 !== 0; },
  console: {log() {}, error() {}}, document: {
    title: '', getElementById() { return {setAttribute() {}}; },
    getElementsByTagName() { return [{getAttribute() { return 'ru'; }}]; }
  },
  Audio: function() { this.paused = true; this.pause = () => {}; this.play = () => {}; },
  Math: Object.create(Math),
  localStorage: {setItem() {}}, Date,
  resetAudio() {}, dosColorToHex() { return ''; },
  getGameFileURL() { return ''; }, normalizeInternalPath(text) { return text; },
  Client: function() { this.render = () => {}; this.cls = () => {};
    this.clsb = () => {}; this.clsl = () => {}; this.clst = () => {};
    this.disableLink = strip; this.convertToLink = (text,id) => { linkCaptions[id]=strip(text);return text; }; },
  $: jquery,
};
context.Math.random = random;
context.Date = class FixedDate extends Date {
  constructor() { super(20000 * 86400000 + 43210 * 1000); }
  getHours() { return 12; }
  getMinutes() { return 0; }
  getSeconds() { return 10; }
};
vm.createContext(context);
const colorTools = fs.readFileSync(path.join(upstream,'js/tools.js'),'utf8');
vm.runInContext(colorTools.slice(colorTools.indexOf('var dosColorToHex'),colorTools.indexOf('var isFloat')),context);
for (const name of ['quest.js', 'rpn.js', 'parser.js', 'player/player.js', 'player/engine.js'])
  vm.runInContext(fs.readFileSync(path.join(upstream, 'js', name), 'utf8'), context,
                  {filename: name, timeout: 10000});
const adaptation = process.env.URQ_ORACLE_ADAPTATION;
if (adaptation) {
  const lock = JSON.parse(fs.readFileSync(path.join(__dirname, 'adaptations.json'), 'utf8'))[adaptation];
  if (!lock) throw Error('Unknown adaptation fixture');
  const helper = fs.readFileSync(path.join(upstream, 'games', adaptation, 'urqw/script.js'));
  if (crypto.createHash('sha256').update(helper).digest('hex') !== lock.files['urqw/script.js'])
    throw Error('Unreviewed game helper');
  vm.runInContext('window=this;', context);
  let code = helper.toString('utf8');
  if (adaptation === 'jim_from_outer_space_ru') {
    // Only its pure JSON note formatter is needed by the unmodified game.
    // DOM typography/visited-button hooks have no role in this headless oracle.
    code = code.slice(code.indexOf('window.notesList = function'), code.indexOf('// When clicked'));
  }
  vm.runInContext(code, context, {filename: adaptation + '/script.js', timeout: 1000});
} else vm.runInContext("Player.prototype.javaScript=function(){throw Error('Game JavaScript is excluded');};", context);
vm.runInContext("Player.prototype.image=function(){};Player.prototype.playMusic=function(){};", context);
const originalPrint = context.Player.prototype.print;
context.Player.prototype.print = function(text, newline) {
  originalPrint.call(this, text, newline);
  emit({event: 'text', text: strip(text), newline});
};
for (const [name, text, actions] of [['cls', true, true], ['clst', true, false],
                                   ['clsb', false, true], ['clsl', false, true]]) {
  const original = context.Player.prototype[name];
  context.Player.prototype[name] = function() {
    original.call(this); emit({event: 'clear', text, actions});
  };
}
context.Game = new context.Quest(fs.readFileSync(source, 'utf8'));
context.GlobalPlayer = new context.Player();
context.Game.init();
context.GlobalPlayer.setVar('urq_mode', mode);
context.GlobalPlayer.continue();
function dump() {
  const variables = {...context.Game.vars};
  for (const name of ['urq_mode', 'style_backcolor', 'style_textcolor']) delete variables[name];
  const actions = Object.values(context.GlobalPlayer.buttons).filter(Boolean)
    .map(action => ({id: action.id, command: action.command, caption: strip(action.desc)}));
  context.GlobalPlayer.links.forEach((command, id) => {
    if(command !== null) actions.push({id:id+32768, command, caption:linkCaptions[id] || command});
  });
  emit({event: 'state', status: context.GlobalPlayer.status, error: 0,
        pc: context.Game.position, vars: variables, items: context.Game.items, actions});
}
function execute(command) {
  if (command.startsWith('c:')) { const id=Number(command.slice(2));context.GlobalPlayer.action(id & 32767, id>=32768); }
  else if (command.startsWith('i:')) context.GlobalPlayer.inputAction(command.slice(2));
  else if (command.startsWith('k:')) context.GlobalPlayer.anykeyAction(Number(command.slice(2)));
  else if (command.startsWith('u:')) context.GlobalPlayer.useAction(command.slice(2));
  else if (command.startsWith('t:')) context.GlobalPlayer.continue();
  else process.exit(2);
  dump();
}
dump();
for (const command of commands) {
  if (command === '-') {
    require('readline').createInterface({input: process.stdin, crlfDelay: Infinity}).on('line', execute);
  } else execute(command);
}
