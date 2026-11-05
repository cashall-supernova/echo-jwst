import assert from 'node:assert/strict';
import {imageAvailability,latestActivity,latestImageGroups,latestObservation,latestPublicRelease,compareImageDates} from '../lib/latest-images.ts';
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

// A new SN with pre-explosion images must outrank an older public release.
const ahvu={...sn,name:'SN2026ahvu',firstIndexedAt:'2026-11-04T16:02:09Z',
 observations:[{...image('ahvu-2024',60620,60620),firstIndexedAt:'2026-11-04T16:02:09Z'}]};
const newImages={...sn,name:'older-SN-with-new-images',firstIndexedAt:'2025-10-30T12:00:00Z',
 observations:[image('old-image',60000),{...image('new-image',61000,61000),firstIndexedAt:'2026-11-05T16:00:00Z'}]};
const ordered=[recentlyReleased,ahvu,newImages,waiting].sort((a,b)=>compareImageDates(a,b,'recent'));
assert.deepEqual(ordered.map(o=>o.name),['older-SN-with-new-images','SN2026ahvu','recent-release','waiting']);
assert.equal(latestActivity(ahvu).reason,'SN added');
assert.equal(latestActivity(newImages).reason,'New image match');
assert.equal(latestActivity({...ahvu,updatedAt:'2026-11-20T00:00:00Z'}).date,'2026-11-04');
assert.equal(latestActivity(waiting).date,null); // proprietary observation dates are not new public images
assert.equal(latestActivity({...waiting,firstIndexedAt:'invalid'}).date,null);
assert.equal(latestActivity({...waiting,firstIndexedAt:'2026-11-05T12:00:00Z'}).reason,'SN added');
const groupsByActivity=latestImageGroups([recentlyReleased,ahvu,newImages]);
assert.deepEqual(groupsByActivity.map(g=>g.images[0].id),['new-image','ahvu-2024','recent-release','old-image']);
assert.equal(latestImageGroups([ahvu,recentlyReleased],'released')[0].sn.name,'recent-release');
assert.equal(latestImageGroups([ahvu,recentlyReleased],'observed')[0].sn.name,'SN2026ahvu');
const laterSameDay={...ahvu,name:'later-same-day',firstIndexedAt:'2026-11-04T18:00:00Z'};
assert.equal([ahvu,laterSameDay].sort((a,b)=>compareImageDates(a,b,'recent'))[0].name,'later-same-day');
console.log('Recent activity: new SN with old images, new matches, stable dates, group-specific activity and alternative sorts passed');
