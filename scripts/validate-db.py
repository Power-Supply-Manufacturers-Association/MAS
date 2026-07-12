#!/usr/bin/env python3
"""Validate every record in MAS/data/*.ndjson against its schema (Python mirror of TestData.cpp Data suite).

advanced_core_materials.ndjson is special: it holds the HEAVY fields (bhCycle curves,
amplitude permeability, extra loss data) split out of core_materials.ndjson purely for
MKF load speed. Its records are name-keyed patches, so they are validated MERGED onto
their base material (replicating MKF's load_advanced_core_materials merge semantics),
never standalone."""
import json, sys, glob
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
ROOT='.'
MAP={
 'core_shapes':'schemas/magnetic/core/shape.json','bobbins':'schemas/magnetic/bobbin.json',
 'core_materials':'schemas/magnetic/core/material.json','wires':'schemas/magnetic/wire.json',
 'insulation_materials':'schemas/magnetic/insulation/material.json','wire_materials':'schemas/magnetic/wire/material.json',
 'cores_stock':'schemas/magnetic/core.json','cores':'schemas/magnetic/core.json',
}
def registry():
    res=[]
    for base in ['schemas','../PEAS/schemas']:
        for p in glob.glob(f'{base}/**/*.json',recursive=True):
            try: s=json.load(open(p))
            except: continue
            if isinstance(s,dict) and '$id' in s: res.append((s['$id'],Resource.from_contents(s)))
    return Registry().with_resources(res)

def validate_advanced_core_materials(reg):
    schema=json.load(open('schemas/magnetic/core/material.json'))
    v=Draft202012Validator(schema,registry=reg)
    base={}
    for line in open('data/core_materials.ndjson'):
        r=json.loads(line)
        base[r['name']]=r
    n=bad=0; first=None
    for line in open('data/advanced_core_materials.ndjson'):
        line=line.strip()
        if not line or line.startswith('version https'): continue
        n+=1
        patch=json.loads(line)
        b=base.get(patch.get('name'))
        if b is None:
            bad+=1; first=first or f"'{patch.get('name')}': no base material to patch (orphan)"
            continue
        merged=json.loads(json.dumps(b))  # deep copy
        if 'bhCycle' in patch:
            merged['bhCycle']=patch['bhCycle']
        contract_err=None
        for losses in ('volumetricLosses','massLosses'):
            if losses not in patch: continue
            # MKF load_advanced_core_materials throws on a losses block without a
            # non-empty "default" method list — flag it here with the same contract
            if not patch[losses].get('default'):
                contract_err=f"'{patch['name']}': {losses} without a non-empty 'default' method list"
                break
            merged.setdefault(losses,{}).setdefault('default',[]) \
                  .extend(patch[losses]['default'])
        if contract_err:
            bad+=1; first=first or contract_err
            continue
        if 'permeability' in patch and 'amplitude' in patch['permeability']:
            merged.setdefault('permeability',{})['amplitude']=patch['permeability']['amplitude']
        errs=list(v.iter_errors(merged))
        if errs:
            bad+=1
            first=first or f"'{patch['name']}': {list(errs[0].absolute_path)}: {errs[0].message[:90]}"
    status='OK ' if bad==0 else 'FAIL'
    print(f'  {status} advanced_core_materials(merged) {n-bad}/{n} valid' + (f'  e.g. {first}' if bad else ''))
    return 1 if bad else 0

reg=registry(); rc=0
for name,schema_rel in MAP.items():
    path=f'data/{name}.ndjson'
    try: schema=json.load(open(schema_rel))
    except Exception as e: print(f'SKIP {name}: {e}'); continue
    v=Draft202012Validator(schema,registry=reg)
    n=bad=0; first=None
    for line in open(path):
        line=line.strip()
        if not line or line.startswith('version https'): continue
        n+=1
        try: doc=json.loads(line)
        except: bad+=1; first=first or 'JSON parse error'; continue
        errs=list(v.iter_errors(doc))
        if errs: bad+=1; first=first or f"{list(errs[0].absolute_path)}: {errs[0].message[:90]}"
    status='OK ' if bad==0 else 'FAIL'
    if bad: rc=1
    print(f'  {status} {name:18} {n-bad}/{n} valid' + (f'  e.g. {first}' if bad else ''))
rc |= validate_advanced_core_materials(reg)
sys.exit(rc)
