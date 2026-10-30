import assert from 'node:assert/strict';
import {imageAvailability,latestImageGroups,latestObservation,latestPublicRelease,compareImageDates} from '../lib/latest-images.ts';
const image=(id,release,start=60000)=>({id,uri:id,obsId:id,publicReleaseMjd:release,start,end:start+.1,instrument:'NIRCAM/IMAGE',proposal:'8633',filter:'F200W',status:'ready'});
const sn={name:'SN2008S',aliases:[],host:'NGC 6946',observations:[image('one',61342),{...image('two',61342),filter:'F460M'},image('older',60001,61000)]};
let groups=latestImageGroups([sn]);
assert.equal(groups.length,2);
assert.equal(groups[0].images.length,2);
assert.equal(groups[0].observed,'2023-02-25');
assert.equal(groups[0].source,'release');
// A newly released old observation sorts ahead of a newer observation released earlier.
assert.equal(groups[0].images[0].id,'one');
assert.equal(imageAvailability(sn,image('missing',null)).date,null);
const watched={...sn,releaseWatch:[{obsId:'missing',status:'public',releasedAt:'2026-10-30T16:00:00Z'}]};
assert.deepEqual(imageAvailability(watched,image('missing',null)),{date:'2026-10-30',source:'confirmed'});
assert.equal(imageAvailability({...watched,releaseWatch:[{...watched.releaseWatch[0],status:'exclusive'}]},image('missing',null)).date,null);
assert.deepEqual(imageAvailability(sn,{...image('new',null),firstIndexedAt:'2026-10-30T16:00:00Z'}),{date:'2026-10-30',source:'indexed'});
groups=latestImageGroups([{...sn,observations:[image('unknown',null,62000),...sn.observations]}]);
assert.equal(groups.at(-1).source,'unknown');
console.log('Latest images: release-date ordering, epoch/filter grouping, confirmed-public fallback and unknown dates passed');

const recentlyReleased={...sn,name:'recent-release',observations:[image('recent-release',61342,60000)],releaseWatch:[{status:'exclusive',obsId:'future',start:61400,expectedRelease:62000}]};
const recentlyObserved={...sn,name:'recent-observation',observations:[image('recent-observation',61000,61000)]};
const waiting={...sn,name:'waiting',observations:[],releaseWatch:[{status:'exclusive',start:62000,releasedAt:'2027-01-01T00:00:00Z'}]};
assert.equal(latestObservation(recentlyReleased),61400);
assert.equal(latestPublicRelease(recentlyReleased).date,imageAvailability(recentlyReleased,recentlyReleased.observations[0]).date);
assert.equal(latestPublicRelease(waiting).date,null);
assert.deepEqual([waiting,recentlyObserved,recentlyReleased].sort((a,b)=>compareImageDates(a,b,'released')).map(s=>s.name),['recent-release','recent-observation','waiting']);
assert.deepEqual([recentlyObserved,recentlyReleased,waiting].sort((a,b)=>compareImageDates(a,b,'observed')).map(s=>s.name),['waiting','recent-release','recent-observation']);
console.log('Catalogue date sorts distinguish observation/release dates and exclude proprietary data from public-release ranking');
