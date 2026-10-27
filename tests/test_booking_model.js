const assert = require('node:assert/strict');
const {selectBookings, roomStatusKind, alertLabel} = require('../web/booking_model.js');
const rows = [
  {key:'old', room:'Linux',status:'หมดเวลา',start:'09:00',end:'12:00'},
  {key:'future',room:'Linux',status:'จองแล้ว',start:'19:00',end:'20:00'},
  {key:'active',room:'Linux',status:'กำลังใช้ห้อง',start:'16:00',end:'19:00'},
  {key:'recent',room:'iOS',status:'หมดเวลา',start:'13:00',end:'16:00'}
];
assert.deepEqual(selectBookings(rows).map(r=>r.key), ['active','future','recent','old']);
assert.deepEqual(selectBookings(rows,'all','ครบเวลาแล้ว').map(r=>r.key), ['recent','old']);
assert.equal(roomStatusKind({status_kind:'red',status:'ส่งเสียงไม่สำเร็จ'}),'red');
assert.equal(alertLabel({alert:'ส่งเสียงไม่สำเร็จ'}),'! ส่งเสียงไม่สำเร็จ');
assert.equal(alertLabel({alert:'ส่งเสียงแล้ว'}),'✓ ส่งเสียงแล้ว');
assert.equal(alertLabel({alert:'ข้าม · ไม่พบสถานะใช้'}),'– ข้าม · ไม่พบสถานะใช้');
assert.equal(rows[0].key,'old');
console.log('PASS: priority, filter, outcome icons, failure status, immutable input');
