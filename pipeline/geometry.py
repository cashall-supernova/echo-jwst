"""Cross-match point coordinates to spherical STC-S polygons/circles.
Gnomonic projection maps great-circle polygon edges to straight lines;
RA wrap and polar coordinates are handled in Cartesian unit vectors.
This establishes metadata footprint coverage, not finite-pixel coverage.
"""
import json, re, math, collections, time
from pathlib import Path
import numpy as np
import os
ROOT=Path(os.environ.get('ECHO_WORK_DIR', str(Path(__file__).resolve().parent.parent/'work')))
ALL_IMAGING={'NIRCAM/IMAGE','MIRI/IMAGE','NIRISS/IMAGE'}
DEFINITE_NON_SN={'TDE','AGN','QSO','LBV','NOVA','VARSTAR','CV','GALAXY','LPV','IMPOSTOR','MOVER','LRN','ILRT','BE','STAR','OTHER'}
def classify(row):
 types=[x.upper().strip() for x in row['types']]
 names=[row['name']]+row['aliases']
 if any('SNR' in n.upper() for n in names) and not any(re.match(r'^SN\s?\d{3,4}[A-Za-z]*$',n) for n in names):return 'excluded'
 if 'REMOVED' in types:return 'excluded'
 if types and all(x in DEFINITE_NON_SN for x in types):return 'excluded'
 if not types or any(x in DEFINITE_NON_SN or x in ('CANDIDATE','LGRB','NT','~','PEC','RADIO','C','C-BL','LCH') or '?' in x or 'LBV' in x or '09IP' in x for x in types):return 'candidate'
 return 'classified'
def unit(ra,dec):
 r,d=np.deg2rad(np.asarray(ra)),np.deg2rad(np.asarray(dec))
 return np.column_stack([np.cos(d)*np.cos(r),np.cos(d)*np.sin(r),np.sin(d)])
def parse_region(region):
 if not isinstance(region,str):raise ValueError('missing region')
 words=region.replace(',',' ').split()
 shape=words.pop(0).upper()
 if words and words[0].upper() in ('ICRS','FK5','J2000'):words.pop(0)
 nums=np.asarray([float(x) for x in words])
 if not np.isfinite(nums).all():raise ValueError('nonfinite region')
 if shape=='CIRCLE' and len(nums)==3:return shape,nums
 if shape=='POLYGON' and len(nums)>=6 and len(nums)%2==0:return shape,nums.reshape(-1,2)
 raise ValueError('unsupported region')
def contains(region,positions):
 # MAST serializes disjoint detector footprints as adjacent POLYGON clauses.
 parts=re.findall(r'(?:POLYGON|CIRCLE)\b.*?(?=\b(?:POLYGON|CIRCLE)\b|$)',region or '',flags=re.I)
 if len(parts)>1:
  results=[contains(p,positions) for p in parts]
  return np.unique(np.concatenate(results))
 shape,xy=parse_region(region)
 if shape=='CIRCLE':
  c=unit([xy[0]],[xy[1]])[0]
  return np.flatnonzero(positions@c>=np.cos(np.deg2rad(xy[2]))-1e-14)
 vertices=unit(xy[:,0],xy[:,1])
 center=vertices.mean(axis=0);norm=np.linalg.norm(center)
 if norm<1e-12:raise ValueError('no local polygon center')
 center/=norm
 dots=vertices@center
 if min(dots)<=0:raise ValueError('polygon exceeds tangent hemisphere')
 # Convex cap around vertices also includes their minor great-circle edges.
 candidates=np.flatnonzero(positions@center>=min(dots)-1e-12)
 if not len(candidates):return candidates
 east=np.cross([0,0,1],center)
 if np.linalg.norm(east)<1e-10:east=np.cross([0,1,0],center)
 east/=np.linalg.norm(east);north=np.cross(center,east)
 vx=(vertices@east)/dots;vy=(vertices@north)/dots
 pts=positions[candidates];den=pts@center
 px=(pts@east)/den;py=(pts@north)/den
 inside=np.zeros(len(candidates),dtype=bool);boundary=np.zeros(len(candidates),dtype=bool)
 for i in range(len(vertices)):
  j=(i-1)%len(vertices);dx=vx[j]-vx[i];dy=vy[j]-vy[i]
  cross=(px-vx[i])*dy-(py-vy[i])*dx
  boundary|=(np.abs(cross)<1e-14)&(px>=min(vx[i],vx[j])-1e-12)&(px<=max(vx[i],vx[j])+1e-12)&(py>=min(vy[i],vy[j])-1e-12)&(py<=max(vy[i],vy[j])+1e-12)
  if abs(dy)>1e-18:
   inside^=((vy[i]>py)!=(vy[j]>py))&(px<dx*(py-vy[i])/dy+vx[i])
 return candidates[inside|boundary]
