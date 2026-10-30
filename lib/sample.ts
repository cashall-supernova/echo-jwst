// Low-redshift Hubble-law estimate only; no peculiar-velocity/frame correction.
export const HUBBLE_CONSTANT = 70;
export const distanceMpc = (z:number):number|null => Number.isFinite(z)&&z>0?299792.458*z/HUBBLE_CONSTANT:null;
export const distanceLabel = (z:number):string => {const d=distanceMpc(z);return d===null?'Unavailable':d<0.1?'<0.1':d.toFixed(1)};
export function subtypeLabel(value:string):string {
 return (value||'Unspecified').trim().replace(/^II P(?=$|[ ?])/,'IIP').replace(/^II L(?=$|[ ?])/,'IIL').replace(/^Ic BL$/,'Ic-BL').replace(/^BL-Ic$/,'Ic-BL').replace(/ (?:Pec|pec)(?=$|[ ?])/,'-pec').replace(/-pec\.$/,'-pec');
}
export function typeFamily(value:string):string {
 const t=subtypeLabel(value);
 if(t==='Candidate')return 'Candidate';
 if(t.includes('/')||t.includes('?'))return 'ambiguous';
 if(t.startsWith('II'))return 'II';
 if(t.startsWith('Ia'))return 'Ia';
 if(t.startsWith('Ib'))return 'Ib';
 if(t.startsWith('Ic'))return 'Ic';
 return 'other';
}
