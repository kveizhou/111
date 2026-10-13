#!/usr/bin/env python3
"""Read already located PDK sources. Standalone; no scan, EDA or rule application."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile
import time

MAX_BYTES=2*1024*1024
SOURCE_NAMES={'res_calc.il','libInit.il'}
TOKENS=re.compile(r'rhrpo_[23]t_ckt|ralpa_ckt|n18_ckt(?:_tp)?|p18_ckt(?:_tp)?|HiEPDK_LL_CB|np2_Mos_LL_CB',re.I)
RULES=re.compile(r'maxAbs|reliab|breakdown|rating|current.?density|electromig|[vV](?:gs|ds|gb)(?:max|Max)|max.?[vV]oltage|耐压|可靠性|额定',re.I)


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def json_read(path):
    if path.stat().st_size>32*1024*1024:raise ValueError('cache JSON exceeds limit: '+str(path))
    return json.loads(path.read_text())


def newest(paths):
    paths=sorted(paths,key=lambda p:(p.stat().st_mtime_ns,str(p)),reverse=True)
    if not paths:raise ValueError('required saved evidence missing')
    if len(paths)>1 and paths[0].stat().st_mtime_ns==paths[1].stat().st_mtime_ns:
        raise ValueError('ambiguous newest saved evidence')
    return paths[0]


def inputs(session,batch):
    status_path=newest(batch.glob('dc_review_ports_*/runtime_bridge_*/bridge_status.json'))
    status=json_read(status_path);bridge=status_path.parent
    if status.get('error') or status.get('bundle_error') or status.get('cache_match') is not True or status.get('psf_unchanged') is not True:
        raise ValueError('latest runtime bridge is not accepted')
    bundle_path=bridge/'bundle/baseline_bundle.json';bundle=json_read(bundle_path)
    if digest(bundle_path)!=bundle_path.with_suffix('.sha256').read_text().strip():raise ValueError('Bundle changed')
    if Path(bundle['session']).resolve()!=session or bundle.get('dependency_policy')!='native-site':
        raise ValueError('session or native-site context mismatch')
    evidence_path=newest(bridge.parent.glob('pdk_evidence_*/evidence.json'));evidence=json_read(evidence_path)
    if evidence.get('schema')!='cascode-pdk-evidence-v2' or Path(evidence['accepted_bridge']).resolve()!=bridge.resolve():
        raise ValueError('latest PDK evidence is not v2 or refers to another accepted bridge')
    fingerprints={str(Path(k).resolve()):v for k,v in evidence.get('source_cache_sha256',{}).items()}
    if str(bundle_path) not in fingerprints or str(status_path) not in fingerprints:
        raise ValueError('PDK evidence lacks accepted cache fingerprints')
    for name,expected in fingerprints.items():
        path=Path(name)
        if path.stat().st_size>32*1024*1024 or digest(path)!=expected:raise ValueError('source cache changed: '+name)
    return bridge,evidence_path,evidence


def read_source(path, hit_lines, byte_limit=MAX_BYTES):
    record=dict(path=str(path),hit_lines=sorted(set(hit_lines)))
    try:
        if not path.is_file():return dict(record,status='MISSING')
        if path.stat().st_size>byte_limit:return dict(record,status='SIZE_LIMIT',size=path.stat().st_size)
        # Bound the actual read as well as the stat check.
        with path.open('rb') as stream:raw=stream.read(byte_limit+1)
        if len(raw)>byte_limit:return dict(record,status='SIZE_LIMIT',size=len(raw))
        record.update(sha256=hashlib.sha256(raw).hexdigest(),size=len(raw))
        try:text=raw.decode('utf-8')
        except UnicodeDecodeError:return dict(record,status='OPAQUE',reason='non-UTF8; no decode/decrypt attempted')
        if any(ord(c)<32 and c not in '\r\n\t' for c in text) or re.search(r'(?im)^\s*(?:#|\.)?protect\b',text):
            return dict(record,status='OPAQUE',reason='binary/protected marker; not interpreted')
        return dict(record,status='TEXT',text=text)
    except OSError as error:return dict(record,status='UNREADABLE',reason=str(error))


def direct_callback_paths(record):
    if record['status']!='TEXT' or Path(record['path']).name!='libInit.il':return []
    # Only literal load(strcat(libPath "...")) entries from the known initializer.
    # No execution, expression evaluation, include closure or recursion.
    base=Path(record['path']).parent.resolve();paths=[]
    for suffix in re.findall(r'\bload\s*\(\s*strcat\s*\(\s*libPath\s+"([^"\n]+)"\s*\)\s*\)',record['text']):
        if not re.search(r'callback|_CB\.',suffix,re.I):continue
        candidate=(base/suffix.lstrip('/')).resolve()
        if base not in candidate.parents:continue
        if candidate.suffix.lower() not in ('.il','.ils','.ile'):continue
        if candidate not in paths:paths.append(candidate)
    return paths


def excerpts(record):
    if record['status']!='TEXT':return []
    lines=record['text'].splitlines();ranges=[]
    is_calc=Path(record['path']).name=='res_calc.il'
    for i,line in enumerate(lines):
        if TOKENS.search(line) or RULES.search(line) or i+1 in record['hit_lines']:
            # res_calc hits may be trailing branch comments: preserve the preceding body.
            before,after=(125,15) if is_calc and TOKENS.search(line) else (8,16)
            start,end=max(0,i-before),min(len(lines),i+after+1)
            while ranges and start<=ranges[-1][1]:
                old_start,old_end=ranges.pop();start=min(start,old_start);end=max(end,old_end)
            ranges.append((start,end))
    if not ranges and Path(record['path']).suffix=='.ile':ranges=[(0,min(30,len(lines)))]
    return [dict(first=start+1,last=end,lines=lines[start:end]) for start,end in ranges]


def run(args):
    started=time.monotonic();session=Path(args.session).resolve();batch=Path(args.batch).resolve()
    bridge,evidence_path,evidence=inputs(session,batch)
    roots=[Path(p).resolve() for p in evidence.get('search_roots',[])]
    selected={}
    for hit in evidence.get('search',{}).get('hits',[]):
        path=Path(hit['path']).resolve()
        if path.name in SOURCE_NAMES and any(path==r or r in path.parents for r in roots):
            selected.setdefault(path,[]).append(int(hit['line']))
    if not selected:raise ValueError('no previously located PDK source file in latest evidence')
    if len(selected)>12:raise ValueError('ambiguous source set exceeds 12 files; select evidence first')
    output=Path(tempfile.mkdtemp(prefix='pdk_sources_',dir=str(bridge.parent)))
    records=[read_source(path,lines) for path,lines in sorted(selected.items(),key=lambda x:str(x[0]))]
    paths=set(selected)
    for record in list(records):
        for path in direct_callback_paths(record):
            if path in paths:continue
            if len(paths)>=20:raise ValueError('direct callback source limit exceeded; no recursive search performed')
            paths.add(path);records.append(read_source(path,[]))
    issues=[]
    for index,record in enumerate(records):
        if record['status'] in ('MISSING','UNREADABLE','SIZE_LIMIT'):issues.append(record['path']+': '+record['status'])
        if record['status']=='TEXT':
            text=record.pop('text');saved=output/('%02d_%s.txt'%(index,Path(record['path']).name));saved.write_text(text)
            record['text_copy']=str(saved)
            record['excerpts']=excerpts(dict(record,text=text))
    report=dict(schema='cascode-pdk-sources-v1',evidence=str(evidence_path),evidence_sha256=digest(evidence_path),
        accepted_bridge=str(bridge),targets=evidence.get('targets',{}),files=records,issues=issues,
        source_cache_sha256=evidence['source_cache_sha256'],native_executions=0,recursive_search=False,
        rules_applied=False,electrical_rules_ready=False)
    (output/'sources.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    summary=['CHECKER=cascode-pdk-sources-v1','RESULT='+('INCOMPLETE' if issues else 'PDK_SOURCES_READ_OK'),
        'OUTPUT_DIR='+str(output),'NATIVE_EXECUTIONS=0','SPECTRE_RERUN=false','OCEAN_RERUN=false',
        'VIRTUOSO_RERUN=false','RECURSIVE_SEARCH=false','SOURCE_FILE_COUNT='+str(len(records))]
    for name,target in report['targets'].items():
        master=target.get('master',{})
        summary.append('TARGET '+name+' '+json.dumps({k:master.get(k) for k in ('oa_library','oa_cell','model_name')},ensure_ascii=False))
    printed=0;omitted=0
    for record in records:
        summary.append('SOURCE '+json.dumps({k:v for k,v in record.items() if k not in ('excerpts','hit_lines')},ensure_ascii=False))
        for part in record.get('excerpts',[]):
            summary.append('TEXT_BEGIN '+record['path']+' line='+str(part['first']))
            for number,line in enumerate(part['lines'],part['first']):
                if printed<650:
                    summary.append(str(number)+': '+line);printed+=1
                else:omitted+=1
            summary.append('TEXT_END')
    summary += ['ISSUE '+issue for issue in issues]
    summary += ['SUMMARY_OMITTED_LINES='+str(omitted),'OPAQUE_FILE_COUNT='+str(sum(r['status']=='OPAQUE' for r in records)),
        'READ_SECONDS=%.3f'%(time.monotonic()-started),'RULES_APPLIED=false','PDK_ELECTRICAL_RULES_READY=false',
        'VBIAS_GENERATED=false','DETAILS_FILE='+str(output/'sources.json'),'RAW_DETAILS_REMAIN_ON_SERVER=true']
    (output/'summary.txt').write_text('\n'.join(summary)+'\n');print('\n'.join(summary))
    return 2 if issues else 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session',required=True);parser.add_argument('--batch',required=True)
    args=parser.parse_args()
    try:return run(args)
    except (OSError,ValueError,KeyError,TypeError) as error:
        print('CHECKER=cascode-pdk-sources-v1\nRESULT=INCOMPLETE\nISSUE '+str(error));return 2


if __name__=='__main__':raise SystemExit(main())
