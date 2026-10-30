export type SpectralLine={id:string;label:string;wave:number;group:string;common:boolean};
// Approximate reference wavelengths in micrometres, not a wavelength calibration
// or an identification of emission in an individual SN. NIR: HISS reference list
// (Medler et al. 2025, https://arxiv.org/abs/2505.18507), as used in the user's
// HISS interface. MIR: Kwok et al. 2023 (https://arxiv.org/abs/2211.00038),
// DerKacy et al. 2024 (https://arxiv.org/abs/2404.17043), and the IRS Handbook,
// https://irsa.ipac.caltech.edu/data/SPITZER/docs/irs/irsinstrumenthandbook/ .
const rows:[string,string,number,string,boolean][]=[
 ['ha','Hα',.6563,'Hydrogen & helium',false],['pad','Paδ',1.0049,'Hydrogen & helium',false],
 ['pag','Paγ',1.0938,'Hydrogen & helium',true],['pab','Paβ',1.2818,'Hydrogen & helium',true],
 ['paa','Paα',1.8751,'Hydrogen & helium',true],['brd','Brδ',1.9446,'Hydrogen & helium',false],
 ['brg','Brγ',2.1655,'Hydrogen & helium',true],['he1','He I',1.0830,'Hydrogen & helium',true],
 ['he2','He I',2.0581,'Hydrogen & helium',true],
 ['ci','C I',1.0693,'Near-IR metals',false],['oi','O I',1.1287,'Near-IR metals',true],
 ['mg','Mg II',1.0927,'Near-IR metals',false],['fe1','[Fe II]',1.2570,'Near-IR metals',true],
 ['fe2','[Fe II]',1.6440,'Near-IR metals',true],['co1','Co II',1.5759,'Near-IR metals',false],
 ['co2','Co II',1.7462,'Near-IR metals',false],['co3','Co II',2.2205,'Near-IR metals',false],
 ['ni2','[Ni II]',6.636,'Mid-IR iron-group',true],['ni3','[Ni III]',7.349,'Mid-IR iron-group',true],
 ['ni4','[Ni IV]',8.405,'Mid-IR iron-group',false],['co-m2','[Co II]',10.521,'Mid-IR iron-group',false],
 ['ni-m3','[Ni III]',11.002,'Mid-IR iron-group',false],['co-m3','[Co III]',11.888,'Mid-IR iron-group',true],
 ['fe-m2','[Fe II]',17.936,'Mid-IR iron-group',false],['fe-m3','[Fe III]',22.925,'Mid-IR iron-group',true],
 ['fe-26','[Fe II]',25.988,'Mid-IR iron-group',true],
 ['ar2','[Ar II]',6.985,'Mid-IR fine structure',true],['ar3','[Ar III]',8.991,'Mid-IR fine structure',true],
 ['s4','[S IV]',10.510,'Mid-IR fine structure',false],['ne2','[Ne II]',12.814,'Mid-IR fine structure',true],
 ['ne3','[Ne III]',15.555,'Mid-IR fine structure',true],['s3','[S III]',18.713,'Mid-IR fine structure',true],
 ['o4','[O IV]',25.890,'Mid-IR fine structure',true],
 ['co-band','CO (2–0)',2.2935,'Molecules',true],['h2-s5','H₂ S(5)',6.910,'Molecules',false],
 ['h2-s3','H₂ S(3)',9.665,'Molecules',false],['h2-s1','H₂ S(1)',17.035,'Molecules',false],
];
export const SPECTRAL_LINES:SpectralLine[]=rows.map(([id,label,wave,group,common])=>({id,label,wave,group,common}));
export const LINE_GROUPS=[...new Set(SPECTRAL_LINES.map(l=>l.group))];
export const commonLineIds=()=>SPECTRAL_LINES.filter(l=>l.common).map(l=>l.id);
/** Positive expansion velocity moves reference markers blueward. Flux is untouched. */
export function markerWavelength(wave:number,z:number|null,rest:boolean,velocity:number):number|null {
 if(!Number.isFinite(wave)||wave<=0||z===null||!Number.isFinite(z)||z<=-1||!Number.isFinite(velocity)||Math.abs(velocity)>50000)return null;
 const beta=velocity/299792.458;
 return wave*Math.sqrt((1-beta)/(1+beta))*(rest?1:1+z);
}
