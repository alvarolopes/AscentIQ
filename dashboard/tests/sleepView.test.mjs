import test from 'node:test';
import assert from 'node:assert/strict';
import {sleepDays,sleepAverage,sleepDuration} from '../web/src/sleepView.js';

test('calendar preserves missing nights and excludes them from averages',()=>{
  const rows=sleepDays([{date:'2026-09-29',duration_minutes:514},{date:'2026-10-01',duration_minutes:446}], '2026-09-29','2026-10-01');
  assert.equal(rows.length,3);
  assert.equal(rows[1].recorded,false);
  assert.equal(rows[1].hours,null);
  assert.deepEqual(sleepAverage(rows,'duration_minutes'),{value:480,count:2});
});
test('missing scores remain unknown; recorded zero participates in averages',()=>{
  assert.deepEqual(sleepAverage([{score:null},{score:0},{score:80}],'score'),{value:40,count:2});
  assert.deepEqual(sleepAverage([{score:null}],'score'),{value:null,count:0});
  assert.equal(sleepDuration(464),'7h44');
  assert.equal(sleepDuration(null),'Sem dado');
});
test('filters reject reversed dates and preserve score-only nights',()=>{
  assert.deepEqual(sleepDays([],'2026-10-02','2026-10-01'),[]);
  const rows=sleepDays([{date:'2026-10-01',score:75}], '2026-10-01','2026-10-01');
  assert.equal(rows[0].recorded,true);
  assert.equal(rows[0].hours,null);
});
