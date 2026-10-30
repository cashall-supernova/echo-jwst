import assert from 'node:assert/strict';
import {groupEpochs,processSegment,csvText} from '../lib/spectrum-processing.ts';
const opts={bin:'samples',size:2,smooth:1,factor:1,flagged:false};
const input=[[1,2,3,0],[2,4,4,0],[3,-6,2,0],[4,-2,2,0]];
const copy=structuredClone(input);
const out=processSegment(input,opts);
assert.equal(out[0][0].flux,3);
assert.equal(out[0][0].error,2.5); // sqrt(3² + 4²) / 2
assert.equal(out[0][1].flux,-4); // Negative finite flux remains scientific data.
assert.deepEqual(input,copy);
assert.equal(out[0][0].samples,2);
assert.deepEqual(processSegment([[1,4,1,0],[2,4,null,0]],opts)[0][0].error,null);
const masked=processSegment([[1,1,1,0],[2,1000,1,1],[3,3,1,0],[4,5,1,0]],{...opts,smooth:3});
assert.equal(masked.length,2);assert.equal(masked[0][0].flux,1);assert.equal(masked[1][0].flux,4);
const gaps=processSegment([[1,1,1,0],[2,1,1,0],[100,9,1,0],[101,9,1,0]],{...opts,size:100});
assert.equal(gaps.length,2);assert.equal(gaps[0][0].flux,1);assert.equal(gaps[1][0].flux,9);
const fixed=processSegment([[1,2,1,0],[1.2,4,1,0],[1.4,6,1,0],[1.6,8,1,0]],{...opts,bin:'wavelength',size:.5});
assert.deepEqual(fixed[0].map(p=>p.samples),[3,1]);assert.equal(fixed[0][0].flux,4);
const rest=processSegment(input,{...opts,factor:2});assert.equal(rest[0][0].wave,.75);assert.equal(rest[0][0].flux,3);
const smooth=processSegment([[1,1,1,0],[2,3,1,0],[3,5,1,0]],{...opts,bin:'none',smooth:3})[0];
assert.deepEqual(smooth.map(p=>p.flux),[2,3,4]);assert.ok(Math.abs(smooth[1].error-1/Math.sqrt(3))<1e-12);
const withDq=processSegment([[1,2,1,2],[2,4,1,4]],{...opts,flagged:true})[0][0];assert.equal(withDq.dq,6);
const epochs=groupEpochs([{id:'late',start:60404},{id:'first',start:60400},{id:'day',start:60401},{id:'next',start:60402.00001},{id:'channel',start:60400.25},{id:'unknown',start:null}]);
assert.deepEqual(epochs.map(e=>e.productIds),[['first','channel','day'],['next'],['late'],['unknown']]);
assert.equal(epochs[0].end,60401); // Exactly 24h is not a new epoch.
assert.equal(csvText([['quoted "file"',null,0]]),'"quoted ""file""","","0"');
console.log('Binning, propagated errors, masks, spectral gaps, smoothing, frame, immutable inputs, and 24-hour epoch boundaries passed');
