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
    # AN UNFETCHED GIT-LFS FILE IS A THREE-LINE STUB, and the old guard only skipped the first of
    # them ('version https://...'), so the second ('oid sha256:...') reached json.loads and came
    # back as a raw JSONDecodeError with no hint of the real cause. Detect the stub itself and say
    # what is wrong. ABT #1019.
    adv = 'data/advanced_core_materials.ndjson'
    with open(adv, 'rb') as fh:
        if fh.read(42) == b'version https://git-lfs.github.com/spec/v1':
            # 0, not 1: the data is ABSENT, not invalid, and failing the whole run because an
            # LFS file was never fetched would be noise. But the line is deliberately loud --
            # a validation that silently reports nothing is indistinguishable from one that
            # passed, which is the trap this script fell into for the caller above.
            print(f"SKIP {adv}: unfetched git-lfs pointer, not data -- the advanced materials "
                  f"were NOT validated. Run `git lfs pull` to check them.")
            return 0
    for line in open(adv):
        line=line.strip()
        if not line: continue
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

def validate_core_references():
    """Every catalogue core must resolve its shape and material by NAME OR ALIAS.

    Schema validation cannot see this: a core's `shape` is a free string, so a record that
    names a shape nobody defines is schema-valid and still unloadable. On 2026-09-10 commit
    a25fec9 rewrote four shape records to add dimensions and dropped their nine aliases; nine
    Micrometals cores in cores.ndjson kept naming one of them ('PQ 27.3/14.5A'), every
    validator here stayed green, and MKF surfaced it as CORE_SHAPE_NOT_FOUND in ten tests two
    days later. This is the check that would have failed in that commit."""
    shapes=[json.loads(l) for l in open('data/core_shapes.ndjson') if l.strip()]
    shape_names={s['name'] for s in shapes}|{a for s in shapes for a in (s.get('aliases') or [])}
    material_names={json.loads(l)['name'] for l in open('data/core_materials.ndjson') if l.strip()}
    rc=0
    for name in ('cores','cores_stock'):
        n=bad=0; first=None
        for line in open(f'data/{name}.ndjson'):
            line=line.strip()
            if not line: continue
            n+=1
            fd=json.loads(line).get('functionalDescription',{})
            shape=fd.get('shape'); material=fd.get('material')
            problems=[]
            if isinstance(shape,str) and shape not in shape_names:
                problems.append(f"shape '{shape}' is neither a core_shapes name nor an alias")
            if isinstance(material,str) and material not in material_names:
                problems.append(f"material '{material}' is not in core_materials")
            if problems:
                bad+=1; first=first or f"'{json.loads(line).get('name')}': {problems[0]}"
        status='OK ' if bad==0 else 'FAIL'
        if bad: rc=1
        print(f'  {status} {name+"(refs)":18} {n-bad}/{n} resolve' + (f'  e.g. {first}' if bad else ''))
    return rc

rc |= validate_core_references()
sys.exit(rc)
