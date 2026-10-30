export type Range = [number, number];
export const EPOCH_COLOURS=['#3e7769','#b08a42','#587ca6','#a76679','#7e6da3','#588e9f','#ad673d','#628143'];
export const DEFAULT_MAX_WAVELENGTH=22;

export function defaultWavelengthRange(bounds:Range):Range {
  return [bounds[0],Math.min(bounds[1],DEFAULT_MAX_WAVELENGTH)];
}

function quantile(sorted:number[],q:number):number {
  const p=q*(sorted.length-1),i=Math.floor(p);
  return sorted[i]+(sorted[Math.min(i+1,sorted.length-1)]-sorted[i])*(p-i);
}

/** A typical within-epoch range, independent of isolated spikes or epoch brightness. */
export function automaticEpochSpacing(epochs:Iterable<number[]>):number {
  const widths:number[]=[],levels:number[]=[];
  for(const values of epochs){
    const sorted=values.filter(Number.isFinite).sort((a,b)=>a-b);
    if(!sorted.length)continue;
    widths.push(quantile(sorted,.9)-quantile(sorted,.1));
    levels.push(Math.abs(quantile(sorted,.5)));
  }
  if(!widths.length)return 1;
  const width=quantile(widths.sort((a,b)=>a-b),.5);
  const level=quantile(levels.sort((a,b)=>a-b),.5);
  return Math.max(1e-9,(width||level||1)*1.1);
}

/** Display limits only: never change, clip, or delete spectral samples. */
export function fluxExtent(values:number[],central=false):Range|null {
  const finite=values.filter(Number.isFinite);
  if(!finite.length)return null;
  if(central&&finite.length>=10){
    const sorted=finite.slice().sort((a,b)=>a-b);
    return [quantile(sorted,.01),quantile(sorted,.99)];
  }
  let low=Infinity,high=-Infinity;for(const v of finite){low=Math.min(low,v);high=Math.max(high,v)}
  return [low,high];
}

/** Display-only median smoothing, within each continuous run. Nulls split runs. */
export function smoothedFluxExtent(runs:Iterable<(number|null)[]>):Range|null {
  const smoothed:number[]=[];
  for(const run of runs){
    let finite:number[]=[];
    const flush=()=>{
      for(let i=0;i<finite.length;i++){
        const window=finite.slice(Math.max(0,i-3),i+4).sort((a,b)=>a-b);
        smoothed.push(quantile(window,.5));
      }
      finite=[];
    };
    for(const value of run){if(value!==null&&Number.isFinite(value))finite.push(value);else flush()}
    flush();
  }
  return fluxExtent(smoothed,true);
}

export function zoomRange(range:Range,factor:number,anchor=.5):Range {
  const a=Math.max(0,Math.min(1,anchor)),center=range[0]+a*(range[1]-range[0]);
  const width=(range[1]-range[0])*Math.max(.01,Math.min(100,factor));
  return [center-a*width,center+(1-a)*width];
}

export function panRange(range:Range,fraction:number):Range {
  const shift=(range[1]-range[0])*fraction;return [range[0]+shift,range[1]+shift];
}

export function boundedRange(range:Range,bounds:Range):Range {
  const width=range[1]-range[0];if(width>=bounds[1]-bounds[0])return [...bounds];
  const low=Math.max(bounds[0],Math.min(bounds[1]-width,range[0]));return [low,low+width];
}

export function selectedRange(range:Range,from:number,to:number):Range {
  const a=Math.max(0,Math.min(1,Math.min(from,to))),b=Math.max(0,Math.min(1,Math.max(from,to)));
  return [range[0]+a*(range[1]-range[0]),range[0]+b*(range[1]-range[0])];
}
