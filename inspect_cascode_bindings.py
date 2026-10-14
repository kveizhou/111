#!/usr/bin/env python3
"""Audit retained OA/netlist bindings without running EDA or changing inputs.

Name expansion below is diagnostic only. It never supplies production bindings.
Exit 0 means evidence collected, not that a circuit or a proposed mapping passed.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import itertools
import json
from pathlib import Path
import re
import sys
import tempfile

sys.dont_write_bytecode=True


def emit(key,value):
    if isinstance(value,bool):value=str(value).lower()
    elif isinstance(value,(dict,list)):value=json.dumps(value,ensure_ascii=True,sort_keys=True)
    print(key+'='+str(value),flush=True)


def newest(paths):
    paths=list(paths)
    if not paths:raise ValueError('required retained files not found')
    return max(paths,key=lambda p:(p.stat().st_mtime_ns,str(p)))


def unescape_angles(name):
    return re.sub(r'\\([<>])',r'\1',name)


def name_candidates(name):
    # Preserve every hierarchy component. No suffix matching, case folding,
    # missing-level insertion, or deduction of master identity from model names.
    segments=[];size=1
    for part in unescape_angles(name).split('.'):
        match=re.fullmatch(r'([^<>]+)<(-?\d+):(-?\d+)>',part)
        if match:
            first,last=int(match[2]),int(match[3]);size*=abs(last-first)+1
            if size>4096:raise ValueError('diagnostic array expansion limit exceeded: '+name)
            step=1 if last>=first else -1
            segments.append([match[1]+'<'+str(n)+'>' for n in range(first,last+step,step)])
        else:segments.append([part])
    return ['.'.join(parts) for parts in itertools.product(*segments)]


def audit(leaves,root,catalogs,bindings,op):
    index=defaultdict(list);unsupported=[]
    for name,proof in bindings.items():
        try:
            for key in name_candidates(name):index[key].append((name,proof))
        except ValueError as error:unsupported.append(dict(instance=name,issue=str(error)))
    counts=Counter({k:0 for k in ('exact','escape_only_candidate','array_name_candidate',
        'ambiguous','unresolved','identity_conflict','uncatalogued_without_binding')})
    differences=[];raw_names=set();matched_keys=set()
    for leaf in leaves:
        if not leaf['path'].startswith(root+'.'):raise ValueError('leaf outside selected root')
        name=leaf['path'][len(root)+1:];raw_names.add(name)
        device=dict(leaf,output_name=name)
        key=unescape_angles(name);possible=index.get(key,[])
        if device['master'] not in catalogs and name not in bindings and not possible:
            counts['uncatalogued_without_binding']+=1;continue
        entry=dict(netlist_instance=name,model=device['master'],node_count=len(device['nodes']),
                   raw_exact_binding=name in bindings,
                   oa_candidates=[dict(p,instance=n) for n,p in possible])
        if not possible:
            status='unresolved'
            stem=re.sub(r'<[^>]*>','',key.split('.')[0])
            related=[dict(p,instance=n) for n,p in bindings.items()
                     if re.sub(r'<[^>]*>','',unescape_angles(n).split('.')[0])==stem]
            entry['related_only_not_a_match']=related[:12]
            entry['related_count']=len(related)
        elif len(possible)!=1:
            status='ambiguous'
        else:
            oa_name,proof=possible[0];matched_keys.add(key)
            status=('exact' if oa_name==name else
                    'escape_only_candidate' if unescape_angles(oa_name)==key else 'array_name_candidate')
            try:
                if proof.get('classification')=='unproven':raise ValueError('native master is unproven')
                if proof.get('model_name') and proof['model_name']!=device['master']:
                    raise ValueError('native model_name differs from exported model')
                if proof.get('classification')=='non_target':
                    if proof.get('model_name')!=device['master'] or len(proof['terminal_names'])!=len(device['nodes']):
                        raise ValueError('non-target model or terminal count differs')
                elif device['master'] in catalogs:
                    op.resolve_device(device,catalogs,{name:proof})
                else:raise ValueError('bound physical master has no matching catalog model')
            except (ValueError,KeyError) as error:
                status='identity_conflict';entry['identity_issue']=str(error)
        counts[status]+=1
        if status!='exact':entry['status']=status;differences.append(entry)
    return dict(counts=dict(counts),differences=differences,unsupported_binding_names=unsupported,
                raw_bindings_not_consumed=sorted(set(bindings)-raw_names),
                unmatched_expanded_paths=sorted(set(index)-matched_keys),
                name_hints_are_verified_bindings=False,production_bindings_changed=False)


def inspect(candidate,engine):
    candidate=Path(candidate).resolve();work=candidate/'work';records={}
    emit('CANDIDATE_DIR',candidate)
    def read(path):
        path=Path(path);data=path.read_bytes()
        records[str(path)]=hashlib.sha256(data).hexdigest()
        return data.decode('utf-8')
    def data(path):return json.loads(read(path))
    export=newest((work/'analysis/baseline_op/raw_op').glob('st-op-simulation.*/export_dut.log'))
    simulation=export.parent;emit('SIMULATION_DIR',simulation)
    binding=data(simulation/'binding.json');text=read(simulation/'simulation.scs')
    if hashlib.sha256(text.encode()).hexdigest()!=binding['simulation_sha256']:
        raise ValueError('simulation.scs differs from its binding record')
    latest_status=newest([candidate/'run_status.json']+list(candidate.glob('resume_generate_*/run_status.json')))
    status=data(latest_status)
    manifest=data(status.get('provider_manifest') or work/'analysis/standalone_inputs/provider_inputs.json')
    site=Path(engine).resolve()/'server/site';module=site/'op_provider.py';read(module)
    emit('PARSER_MATCHES_SESSION',manifest['file_sha256'].get(str(module))==records[str(module)])
    sys.path.insert(0,str(site));import op_provider as op
    configs=data(manifest['tech']);profile=data(manifest['rules'])
    found=[]
    for path in (work/'analysis/pdk_scan').glob('run_*/raw_catalog.tsv'):
        if hashlib.sha256(path.read_bytes()).hexdigest()==binding['scanned_catalog_sha256']:found.append(path)
    catalog=newest(found);read(catalog);emit('MATCHED_CATALOG',catalog)
    import csv,io
    versions={row['pdk_version'] for row in csv.DictReader(io.StringIO(read(catalog)),delimiter='\t')}
    if len(versions)!=1:raise ValueError('catalog version missing or ambiguous')
    version=next(iter(versions));tech=[c for c in configs if c['version']==version]
    if len(tech)!=1:raise ValueError('matching tech metadata missing or ambiguous')
    catalogs=op.load_scanned_catalog(catalog,tech[0],version,profile.get('validation_scope','dc_operating_point'))
    raw_bindings=simulation/'oa_bindings.tsv';read(raw_bindings)
    bindings=op.read_oa_bindings(raw_bindings)
    leaves=op.flatten_dut(text,binding['root_path'],binding['dut'][1])
    report=audit(leaves,binding['root_path'],catalogs,bindings,op)
    try:
        op.bind_physical_devices(text,binding['root_path'],binding['dut'][1],catalogs,bindings)
        report['production_replay']='PASS'
    except (ValueError,KeyError) as error:report['production_replay']=str(error)
    for path,digest in records.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:
            raise ValueError('evidence changed during read: '+path)
    report.update(simulation_directory=str(simulation),source_file_sha256=records,
                  leaf_count=len(leaves),oa_record_count=len(bindings),native_executions=0)
    output=Path(tempfile.mkdtemp(prefix='binding_review_',dir=str(candidate)))
    details=output/'binding_evidence.json'
    details.write_text(json.dumps(report,ensure_ascii=True,indent=2)+'\n')
    emit('RESULT','BINDING_EVIDENCE_READ_OK')
    emit('PRODUCTION_REPLAY',report['production_replay'])
    emit('OA_RECORD_COUNT',len(bindings));emit('NETLIST_LEAF_COUNT',len(leaves))
    emit('COUNTS',report['counts'])
    for entry in report['differences'][:16]:emit('BINDING_DIFFERENCE',entry)
    emit('SUMMARY_OMITTED_DIFFERENCES',max(0,len(report['differences'])-16))
    emit('RAW_BINDINGS_NOT_CONSUMED_COUNT',len(report['raw_bindings_not_consumed']))
    emit('UNMATCHED_EXPANDED_PATH_COUNT',len(report['unmatched_expanded_paths']))
    emit('UNMATCHED_EXPANDED_PATH_SAMPLE',report['unmatched_expanded_paths'][:12])
    emit('UNSUPPORTED_NAME_COUNT',len(report['unsupported_binding_names']))
    emit('SOURCE_FILES_UNCHANGED',True)
    emit('DETAILS_FILE',details)
    return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--batch');source.add_argument('--candidate')
    parser.add_argument('--engine',default=str(Path(__file__).resolve().parents[1]))
    args=parser.parse_args()
    emit('CHECKER','cascode-binding-evidence-v1');emit('NATIVE_EXECUTIONS',0)
    emit('SPECTRE_RERUN',False);emit('OCEAN_RERUN',False)
    emit('PRODUCTION_BINDINGS_CHANGED',False)
    try:
        candidate=Path(args.candidate) if args.candidate else newest(Path(args.batch).glob('candidate_*/run_status.json')).parent
        return inspect(candidate,args.engine)
    except (OSError,ValueError,KeyError,TypeError,ImportError) as error:
        emit('RESULT','INCOMPLETE');emit('ISSUE',str(error));return 2
    finally:
        emit('ELECTRICAL_VERIFIED',False);emit('VBIAS_GENERATED',False)


if __name__=='__main__':raise SystemExit(main())
