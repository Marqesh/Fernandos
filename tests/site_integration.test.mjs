import test from 'node:test';
import assert from 'node:assert/strict';
import {previewRaceData, loadOfficialRaceData, seasonStatusRows} from '../site_integration.js';

const mock = {
  schema_version:1, season:2027, generated_at:'2026-10-31T15:00:00Z',
  races: Array.from({length:30}, (_,i) => ({
    id:`race-${i}-2027`,key:`race-${i}`,year:2027, name:`Race ${i}`,
    aliases:i===0?['Volta a Figueira']:[],
    startlist:{status:'not_published',riders:[]},
    startlist_availability:'awaiting_2027_startlist',
  }))
};
const riders=Array.from({length:12},(_,i)=>({bib:i+1,name:`Rider ${i}`,team:'Alpha'}));

test('Read-only preview matches diacritic alias and preserves local race',()=>{
  const local={id:'internal-99',year:2027,name:'Volta a Figueira', draft_picks:[{rider_name:'Favorite Name'}]};
  const out=previewRaceData([local],mock)[0];
  assert.equal(out.matched,true);
  assert.equal(out.status,'not_published');
  assert.equal(out.startlistReady,false);
  assert.strictEqual(out.race,local);
  assert.deepEqual(local.draft_picks,[{rider_name:'Favorite Name'}]);
});

test('2026 local race is never matched to 2027',()=>{
  const out=previewRaceData([{id:'race-0-2027',year:2026,name:'Volta a Figueira'}],mock)[0];
  assert.equal(out.status,'unmatched');
});

test('only verified 2027 rider list is shown',()=>{
  const f=structuredClone(mock);
  f.races[0].startlist={status:'published',edition_year:2026,riders};
  assert.equal(previewRaceData([{id:'race-0-2027',year:2027}],f)[0].startlistReady,false);
  f.races[0].startlist.edition_year=2027;
  assert.equal(previewRaceData([{id:'race-0-2027',year:2027}],f)[0].importedRiders.length,12);
});

test('affected picks flagged but never deleted',()=>{
  const f=structuredClone(mock);
  f.races[0].startlist={status:'published',edition_year:2027,riders};
  const local={id:'race-0-2027',year:2027,draft_picks:[{rider_name:'Old Favourite'}]};
  const out=previewRaceData([local],f)[0];
  assert.deepEqual(out.affectedPicks,['old-favourite']);
  assert.equal(local.draft_picks.length,1);
});

test('feed format validation stops wrong seasons and duplicates',async()=>{
  const load=async data=>loadOfficialRaceData(undefined,async()=>({ok:true,json:async()=>data}));
  assert.equal((await load(mock)).races.length,30);
  await assert.rejects(load({...mock,season:2026}));
  const dup=structuredClone(mock);dup.races[1].id=dup.races[0].id;
  await assert.rejects(load(dup));
});

test('season status rows never include unverified riders',()=>{
  const f=structuredClone(mock);
  f.races[0].startlist={status:'published',edition_year:2026,riders};
  assert.equal(seasonStatusRows(f)[0].riders,0);
});
