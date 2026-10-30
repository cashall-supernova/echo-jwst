import assert from 'node:assert/strict';
import {automaticEpochSpacing,fluxExtent,smoothedFluxExtent,defaultWavelengthRange,zoomRange,panRange,boundedRange,selectedRange} from '../lib/spectrum-view.ts';
const data=[-1000,...Array.from({length:1000},(_,i)=>i/100),1000],original=data.slice();
assert.deepEqual(fluxExtent(data),[-1000,1000]);
const focused=fluxExtent(data,true);assert.ok(focused[0]>0&&focused[1]<10);
assert.deepEqual(data,original); // Limits never alter samples, spikes included.
assert.deepEqual(fluxExtent([null,NaN,Infinity].filter(v=>v!==null)),null);
assert.deepEqual(zoomRange([0,100],.5),[25,75]);
assert.deepEqual(zoomRange([0,100],.5,0),[0,50]);
assert.deepEqual(zoomRange([0,100],.5,1),[50,100]);
assert.deepEqual(panRange([10,20],-.2),[8,18]);
assert.deepEqual(boundedRange([-5,5],[0,30]),[0,10]);
assert.deepEqual(boundedRange([25,35],[0,30]),[20,30]);
assert.deepEqual(boundedRange([-5,35],[0,30]),[0,30]);
assert.deepEqual(selectedRange([5,25],.8,.2),[9,21]);
// Offscreen long-wave noise must not influence a visible-range fit or spacing.
const spectrum=[[5,1],[6,2],[10,3],[20,2],[26,1000],[28,-1000]];
assert.deepEqual(fluxExtent(spectrum.filter(p=>p[0]<=20).map(p=>p[1])),[1,3]);
// One noisy tail must not dictate every epoch's separation, nor should a
// difference in absolute brightness be mistaken for within-epoch structure.
const quiet=Array.from({length:1001},(_,i)=>1+i/1000);
const noisy=quiet.map((v,i)=>i>950?1e6:v),quietCopy=quiet.slice(),noisyCopy=noisy.slice();
const step=automaticEpochSpacing([quiet,quiet.map(v=>v+1000),noisy]);
assert.ok(Math.abs(step-.88)<1e-10);
assert.ok(automaticEpochSpacing([quiet,noisy])<1);
assert.deepEqual(quiet,quietCopy);assert.deepEqual(noisy,noisyCopy);
assert.equal(automaticEpochSpacing([[],[NaN,Infinity]]),1);
assert.ok(automaticEpochSpacing([[0,0,0]])>0);
assert.ok(Number.isFinite(automaticEpochSpacing([[1]])));
console.log('Viewport zoom, reverse selection, pan bounds, percentile display limits, and offscreen-noise regression passed');

assert.deepEqual(defaultWavelengthRange([5,28]),[5,22]);
assert.deepEqual(defaultWavelengthRange([1,5]),[1,5]);
const broadFeature=Array.from({length:101},(_,i)=>i>=30&&i<=50?20:1);
broadFeature[10]=1e6;broadFeature[80]=-1e6;
const featureCopy=broadFeature.slice();
assert.deepEqual(smoothedFluxExtent([broadFeature]),[1,20]);
assert.deepEqual(broadFeature,featureCopy);
assert.deepEqual(smoothedFluxExtent([[1,1,null,100,100]]),[1,100]);
assert.deepEqual(smoothedFluxExtent([[1,1],[100,100]]),[1,100]);
assert.deepEqual(smoothedFluxExtent([[],[NaN,null,Infinity]]),null);
assert.deepEqual(smoothedFluxExtent([[5]]),[5,5]);
const longTail=[[5,1],[10,2],[20,3],[26,1e6],[28,-1e6]];
assert.deepEqual(smoothedFluxExtent([longTail.filter(([w])=>w<=22).map(([,v])=>v)]),[2,2]);
console.log('Default 22 µm cap and display-only median bounds reject spikes, retain broad features, preserve gaps and source data');
