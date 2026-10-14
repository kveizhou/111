#!/usr/bin/env python3
"""Read retained OA/netlist resistor groups; no native tools or binding changes."""
import argparse
from collections import defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import tempfile

sys.dont_write_bytecode=True


def emit(key,value):
    if isinstance(value,bool):value=str(value).lower()
    elif isinstance(value,(dict,list)):value=json.dumps(value,sort_keys=True)
    print(key+'='+str(value),flush=True)


def newest(paths):
    paths=list(paths)
    if not paths:raise ValueError('required retained files missing')
    return max(paths,key=lambda p:(p.stat().st_mtime_ns,str(p)))


def key(name):return re.sub(r'(?<!\\)\\([<>])',r'\1',name)


def trace_series(segments,endpoints,instances,protected):
    """Check a two-terminal chain; names and indices are not connectivity proof."""
    if len(endpoints)!=2 or key(endpoints[0])==key(endpoints[1]):
        raise ValueError('two distinct original endpoints required')
    adjacency=defaultdict(list);by_name={}
    for segment in segments:
        name=segment['name'];nodes=[key(n) for n in segment['nodes']]
        if name in by_name or len(nodes)!=2 or nodes[0]==nodes[1]:
            raise ValueError('duplicate, shorted or non-two-terminal segment')
        by_name[name]=nodes
        for node in nodes:adjacency[node].append(name)
    start,end=[key(n) for n in endpoints]
    internal=set(adjacency)-{start,end}
    if len(adjacency.get(start,[]))!=1 or len(adjacency.get(end,[]))!=1:
        raise ValueError('exported chain endpoints differ from original OA endpoints')
    if any(len(adjacency[n])!=2 for n in internal):raise ValueError('chain contains a branch or open end')
    if internal & {key(n) for n in protected}:raise ValueError('internal node is a port or global node')
    for instance in instances:
        if instance['name'] not in by_name and internal & {key(n) for n in instance['nodes']}:
            raise ValueError('internal node has external connection: '+instance['name'])
    names=[];signs=[];nodes=[start];used=set();current=start
    while current!=end:
        choices=[n for n in adjacency[current] if n not in used]
        if len(choices)!=1:raise ValueError('chain is disconnected or cyclic')
        name=choices[0];pair=by_name[name]
        signs.append(1 if pair[0]==current else -1)
        current=pair[1] if pair[0]==current else pair[0]
        used.add(name);names.append(name);nodes.append(current)
    if len(used)!=len(segments):raise ValueError('segments outside the endpoint-to-endpoint chain')
    return dict(path_nodes=nodes,path_instances=names,segment_signs=signs)


def inspect(candidate,engine):
    candidate=Path(candidate).resolve();work=candidate/'work';hashes={}
    def read(path):
        path=Path(path);raw=path.read_bytes();hashes[str(path)]=hashlib.sha256(raw).hexdigest()
        return raw.decode('utf-8')
    def data(path):return json.loads(read(path))
    def rows(path):return list(csv.DictReader(io.StringIO(read(path)),delimiter='\t'))
    site=Path(engine).resolve()/'server/site';read(site/'op_provider.py')
    sys.path.insert(0,str(site));import op_provider as op
    directory=newest((work/'analysis/baseline_op/raw_op').glob('st-op-simulation.*/export_dut.log')).parent
    binding=data(directory/'binding.json');cell=binding['dut'][1]
    oa=op.parse_deck(read(work/'before/core_before.scs'))
    native=op.parse_deck(read(directory/'dut.scs'))
    if cell not in oa['definitions'] or cell not in native['definitions']:
        raise ValueError('expected core subckt missing in retained snapshot or exported DUT')
    source=oa['definitions'][cell];exported=native['definitions'][cell]
    original={i['name']:i for i in source['instances']}
    if len(original)!=len(source['instances']):raise ValueError('duplicate OA snapshot instance')
    oa_rows=rows(directory/'oa_bindings.tsv');catalog=rows(work/'before/device_catalog.tsv')
    groups=defaultdict(list)
    for inst in exported['instances']:
        match=re.fullmatch(r'(.+)_(\d+)_res_gen',inst['name'])
        if match:groups[match[1]].append((int(match[2]),inst))
    if not groups:raise ValueError('no generated resistor group candidates at this core level')
    results=[]
    for name,children in sorted(groups.items()):
        parent=[i for i in exported['instances'] if i['name']==name]
        segments=parent+[i for _,i in sorted(children,key=lambda x:x[0])]
        baseline=original.get(name)
        report=dict(instance=name,original=baseline,segments=segments,cdf_segments=None,
                    series_graph_verified=False,issues=[])
        results.append(report);issues=report['issues']
        if len(parent)!=1:issues.append('unique original-name exported segment missing')
        if baseline is None:issues.append('original OA snapshot instance missing')
        if issues:continue
        indices=[1]+[n for n,_ in sorted(children,key=lambda x:x[0])]
        if indices!=list(range(1,len(segments)+1)):issues.append('segment numbering incomplete or duplicated')
        proof=[r for r in oa_rows if r['instance']==name]
        masters=[r for r in catalog if r['master']==baseline['master']]
        if len(proof)!=1 or len(masters)!=1:
            issues.append('unique original OA master/catalog identity missing')
        else:
            p,c=proof[0],masters[0];report['oa_identity']=p
            if (c['kind']!='resistor' or c['oa_library']!=p['oa_library'] or c['oa_cell']!=p['oa_cell'] or
                    c['terminal_names']!=p['terminal_names'] or len(p['terminal_names'].split(','))!=2):
                issues.append('original master or two-terminal order conflict')
            if any(i['master']!=p['model_name'] for i in segments):issues.append('segment model differs from original OA model')
        try:
            parameters=dict(oa['parameters']);parameters.update(source['parameters'])
            count=op.parameter_value(baseline['params']['segments'],parameters)
            if count<1 or count!=int(count):raise ValueError('CDF segments is not a positive integer')
            report['cdf_segments']=int(count)
            if int(count)!=len(segments):issues.append('actual CDF segments differs from exported count')
        except (KeyError,ValueError) as error:issues.append('CDF segment count unavailable: '+str(error))
        try:
            report.update(trace_series(segments,baseline['nodes'],exported['instances'],
                                       set(exported['ports'])|set(native['globals'])))
            report['series_graph_verified']=True
        except ValueError as error:issues.append(str(error))
    for path,digest in hashes.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('retained input changed: '+path)
    output=Path(tempfile.mkdtemp(prefix='resistor_review_',dir=str(candidate)))
    report=dict(groups=results,simulation_directory=str(directory),source_file_sha256=hashes,
                native_executions=0,production_bindings_changed=False,measurement_mapping_verified=False)
    details=output/'resistor_groups.json';details.write_text(json.dumps(report,indent=2)+'\n')
    emit('RESULT','RESISTOR_CONTEXT_READ_OK');emit('SIMULATION_DIR',directory);emit('GROUP_COUNT',len(results))
    for group in results:
        emit('RESISTOR_GROUP',{k:v for k,v in group.items() if k not in ('segments','original')})
        emit('ORIGINAL_OA',group['original'])
        variants={}
        for part in group['segments']:
            signature=json.dumps(part['params'],sort_keys=True)
            variants.setdefault(signature,[]).append(part['name'])
        emit('SEGMENT_PARAMETERS',[dict(parameters=json.loads(s),instances=names) for s,names in variants.items()])
        if not group['series_graph_verified']:
            emit('SEGMENT_CONNECTIONS',[dict(instance=i['name'],nodes=i['nodes'],model=i['master']) for i in group['segments']])
    emit('SOURCE_FILES_UNCHANGED',True);emit('DETAILS_FILE',details)
    return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--batch');choice.add_argument('--candidate')
    parser.add_argument('--engine',required=True)
    args=parser.parse_args()
    emit('CHECKER','cascode-resistor-context-v1');emit('NATIVE_EXECUTIONS',0)
    emit('SPECTRE_RERUN',False);emit('SOURCE_OA_SAVED',False)
    try:
        candidate=Path(args.candidate) if args.candidate else newest(Path(args.batch).glob('candidate_*/run_status.json')).parent
        return inspect(candidate,args.engine)
    except (OSError,ValueError,KeyError,TypeError,ImportError) as error:
        emit('RESULT','INCOMPLETE');emit('ISSUE',str(error));return 2
    finally:
        emit('PRODUCTION_BINDINGS_CHANGED',False);emit('ELECTRICAL_VERIFIED',False)


if __name__=='__main__':raise SystemExit(main())
