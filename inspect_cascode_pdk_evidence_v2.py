#!/usr/bin/env python3
"""Find existing CDF/PDK evidence without native EDA execution or rule invention.

Standalone standard-library entry: may run outside the source checkout. A
successful collection is NOT electrical-rule acceptance. Search is deliberately
bounded and never resolves a model include closure or evaluates a CDF callback.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time


TEXT_SUFFIXES = {'.il', '.ils', '.scs', '.lib', '.mdl', '.model', '.sp', '.txt', '.md', '.json', '.csv', '.tsv'}
DOC_SUFFIXES = {'.pdf', '.doc', '.docx', '.html', '.htm'}
RULE_WORDS = re.compile(r'minVal|maxVal|choices|callback|reliab|absolute|maxAbs|vgs|vds|vgb|breakdown|rating|electromig|current.?density|power|bulk|well|nfin|wmin|wmax|lmin|lmax|\btype\s*=|耐压|可靠性|额定|合法', re.I)
GEOMETRY_SEMANTICS = {'length','width','fin','fingers','multiplier','resistance'}


def callback_text(record):
    raw = record.get('raw_value', '')
    if raw.strip() == 'nil': return None, 'nil'
    try:
        value = json.loads(raw)
        if isinstance(value, str): return value, 'decoded_string'
    except (ValueError, TypeError):
        pass
    # SKILL %L may contain escapes not recognized by JSON. Preserve everything
    # instead of guessing how to decode it or evaluating native callback code.
    return raw, 'raw_skill_literal'


def specific_search_tokens(data, resistors, records):
    tokens, namespaces = set(), set()
    masters = [item['master'] for item in data['targets'].values()] + resistors[:3]
    for master in masters:
        tokens.update(master.get(k, '') for k in ('oa_cell','model_name'))
        namespaces.update(p.lower() for p in re.split(r'[^A-Za-z0-9]+',master.get('oa_library',''))
                          if len(p)>=3 and p.lower() not in ('pdk','lib','library'))
    for item in data['targets'].values():
        tokens.update(row.get('model_name','') for row in item.get('cdf_probe', []))
    for row in records:
        if row.get('kind') != 'cdf_callback': continue
        content, _ = callback_text(row)
        for function in re.findall(r'([A-Za-z_][A-Za-z_0-9]*)\s*\(', content or ''):
            lower = function.lower()
            namespaced = any(lower.startswith(ns+'_') for ns in namespaces)
            # Positive PDK-name evidence, not an ever-growing blacklist of
            # ordinary SKILL functions such as errset/readstring/cdfFormat*.
            if namespaced or lower.endswith('_cb') or 'callback' in lower:
                tokens.add(function)
    return sorted(s for s in tokens if isinstance(s,str) and len(s)>=3 and s.lower() not in ('nil','none'))


def compact_master(master):
    result = {k:v for k,v in master.items() if k in ('oa_library','oa_cell','model_name','kind','terminal_names','terminal_roles')}
    mapping = master.get('normalized_to_cdf','')
    if isinstance(mapping,str):
        mapping = dict(item.split(':',1) for item in mapping.split(',') if ':' in item)
    result['geometry_to_cdf'] = {k:v for k,v in mapping.items() if k in GEOMETRY_SEMANTICS}
    return result


def callback_summary(records):
    groups, lines = {}, []
    callbacks = [r for r in records if r.get('kind')=='cdf_callback']
    for record in callbacks:
        text, encoding = callback_text(record)
        if text is None: continue
        key = (text,encoding,record.get('status'))
        groups.setdefault(key,[]).append(str(record.get('scope'))+':'+str(record.get('name')))
    for (text,encoding,status),targets in groups.items():
        lines += ['CALLBACK_BEGIN targets='+','.join(targets)+' status='+str(status)+' encoding='+encoding,
                  text, 'CALLBACK_END']
    complete = bool(callbacks) and all(r.get('status')=='OK' for r in callbacks)
    lines.append('CALLBACK_OUTPUT_COMPLETE='+str(complete).lower())
    return lines


def read_json(path):
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('cache JSON too large: ' + str(path))
    return json.loads(path.read_text())


def latest(paths):
    items = sorted(paths, key=lambda p: (p.stat().st_mtime_ns, str(p)), reverse=True)
    if not items:
        raise ValueError('saved acceptance cache missing')
    if len(items) > 1 and items[0].stat().st_mtime_ns == items[1].stat().st_mtime_ns:
        raise ValueError('ambiguous latest acceptance timestamp')
    return items[0]


def cached_inputs(session, batch):
    status_path = latest(batch.glob('dc_review_ports_*/runtime_bridge_*/bridge_status.json'))
    status = read_json(status_path)
    if status.get('error') or status.get('bundle_error') or status.get('cache_match') is not True or status.get('psf_unchanged') is not True:
        raise ValueError('latest acceptance is not successful; no fallback to older data')
    bridge = status_path.parent
    bundle_path = bridge/'bundle/baseline_bundle.json'
    raw = bundle_path.read_bytes()
    if bundle_path.with_suffix('.sha256').read_text().strip() != hashlib.sha256(raw).hexdigest():
        raise ValueError('saved Bundle manifest changed')
    bundle = json.loads(raw)
    if Path(bundle['session']).resolve() != session:
        raise ValueError('session differs from accepted context')
    if bundle.get('dependency_policy') != 'native-site':
        raise ValueError('expected accepted native-site context')
    data = read_json(bridge/'pdk.json')
    if not data.get('targets'):
        raise ValueError('target PDK evidence missing')
    notes = []
    native_path = batch/'native_records.json'
    native = read_json(native_path) if native_path.is_file() else []
    if not native_path.is_file():
        notes.append('native_records.json missing; cached probe retained, no native reread')
    probe_path = session/'analysis/standalone_inputs/pdk_probe.tsv'
    probe = []
    if probe_path.is_file():
        with probe_path.open(newline='') as f:
            probe = list(csv.DictReader(f, delimiter='\t'))
    else:
        notes.append('full pdk_probe.tsv missing; target probe remains in pdk.json')
    # Validate only small source-cache files actually consumed here. This is
    # discovery, so do not rehash PSF or the model tree a second time.
    fingerprints = {}
    for path in (status_path, bundle_path, bridge/'pdk.json', native_path, probe_path):
        if path.is_file():
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            expected = bundle.get('file_sha256', {}).get(str(path))
            if expected is not None and actual != expected:
                raise ValueError('bound source cache changed: ' + str(path))
            fingerprints[str(path)] = actual
    nodes = {}
    node_paths = list(bridge.parent.glob('node_context_*/node_context.json'))
    if node_paths:
        node_path = latest(node_paths)
        node = read_json(node_path)
        nodes = {k: v for k, v in node.get('core_ports', {}).items() if k in ('AVDD', 'PVDD', 'AGND')}
        fingerprints[str(node_path)] = hashlib.sha256(node_path.read_bytes()).hexdigest()
    return bridge, bundle, data, native, probe, nodes, notes, fingerprints


def search_roots(data, bundle, extra):
    paths = []
    for metadata in data.get('metadata', []):
        paths.extend(metadata.get('pdk_paths', []))
    for model in bundle.get('models', []):
        parent = Path(model['model_file']).parent
        paths.append(str(parent))
        # Include sibling documentation only at the declared model release.
        if parent.name.lower() in ('spectre', 'models', 'model', 'spice'):
            paths.append(str(parent.parent))
    paths.extend(extra)
    roots, notes = [], []
    for name in paths:
        path = Path(name).resolve()
        if not path.is_dir() or len(path.parts) < 3:
            notes.append('root unavailable or too broad: ' + str(path))
        elif path not in roots:
            roots.append(path)
    # Keep explicit roots (even descendants), with a shared file-identity set.
    return roots, notes


def search(roots, tokens, args):
    start = time.monotonic()
    hits, docs, skipped, limits = [], [], [], []
    seen, directories, visited, read_bytes = set(), set(), 0, 0
    words = sorted({s for s in tokens if isinstance(s, str) and len(s) >= 3})
    terms = '|'.join(re.escape(s) for s in words)
    related = re.compile(r'(?<![A-Za-z0-9_])(?:'+terms+r')(?![A-Za-z0-9_])', re.I) if words else None
    filename_related = re.compile(terms, re.I) if words else None
    if related is None:
        return dict(hits=[], documents=[], skipped=[], limited=True, limits=['no specific device tokens'], files_seen=0, bytes_read=0)
    pending = [(root, 0) for root in reversed(roots)]
    while pending:
        if time.monotonic() - start >= args.seconds or visited >= args.max_files:
            limits.append('time_or_file_limit'); break
        directory, depth = pending.pop()
        directory_key = str(directory.resolve())
        if directory_key in directories: continue
        directories.add(directory_key)
        try:
            with os.scandir(directory) as entries:
                # Count directory entries as well, so huge cell libraries are
                # bounded even when they contain no searchable file type.
                for entry in entries:
                    if time.monotonic() - start >= args.seconds or visited >= args.max_files:
                        limits.append('time_or_file_limit'); pending.clear(); break
                    visited += 1
                    path = Path(entry.path)
                    if entry.is_symlink():
                        skipped.append(dict(path=str(path), reason='symlink_not_followed')); continue
                    if entry.is_dir(follow_symlinks=False):
                        if depth < args.max_depth:
                            pending.append((path, depth + 1))
                        else:
                            limits.append('depth_limit: ' + str(path))
                        continue
                    if not entry.is_file(follow_symlinks=False): continue
                    resolved = str(path.resolve())
                    if resolved in seen: continue
                    seen.add(resolved)
                    suffix = path.suffix.lower()
                    if suffix in DOC_SUFFIXES:
                        docs.append(dict(path=resolved, bytes=entry.stat().st_size,
                            device_name_match=bool(filename_related.search(path.name)), content_read=False))
                        continue
                    if suffix not in TEXT_SUFFIXES: continue
                    if len(hits) >= 160:
                        limits.append('snippet_limit')
                        skipped.append(dict(path=resolved, reason='snippet_limit'))
                        continue
                    size = entry.stat().st_size
                    if size > 2 * 1024 * 1024 or read_bytes + size > args.max_bytes:
                        skipped.append(dict(path=resolved, reason='text_byte_limit', bytes=size)); continue
                    try:
                        raw = path.read_bytes(); read_bytes += len(raw)
                        text = raw.decode('utf-8')
                    except (OSError, UnicodeError) as error:
                        skipped.append(dict(path=resolved, reason=type(error).__name__)); continue
                    lines = text.splitlines()
                    device_lines = {i for i, line in enumerate(lines) if related.search(line)}
                    in_name = bool(filename_related.search(path.name))
                    if not in_name and not device_lines: continue
                    neighborhood = {i for match in device_lines for i in range(max(0,match-8),min(len(lines),match+9))}
                    file_hits = 0
                    for i, line in enumerate(lines):
                        nearby = in_name or i in neighborhood
                        if (nearby and RULE_WORDS.search(line)) or i in device_lines:
                            if len(hits) >= 160:
                                limits.append('snippet_limit'); break
                            if file_hits >= 24:
                                limits.append('per_file_snippet_limit: '+resolved); break
                            hits.append(dict(path=resolved, line=i+1, text=line[:600],
                                line_truncated=len(line)>600, candidate_only=True))
                            file_hits += 1
        except OSError as error:
            skipped.append(dict(path=str(directory), reason=type(error).__name__))
    return dict(hits=hits, documents=docs, skipped=skipped, limited=bool(limits or skipped),
        limits=sorted(set(limits)), files_seen=visited, bytes_read=read_bytes,
        elapsed_seconds=round(time.monotonic()-start, 3), model_closure_inspected=False)


def run(args):
    session, batch = Path(args.session).resolve(), Path(args.batch).resolve()
    bridge, bundle, data, native, probe, nodes, notes, fingerprints = cached_inputs(session, batch)
    target_names = set(data['targets'])
    records = [r for r in native if r.get('scope') in target_names]
    resistors = sorted((r for r in data.get('catalog', []) if r.get('kind') == 'resistor'),
                       key=lambda r: (r.get('oa_library',''),r.get('oa_cell','')))
    # Existing catalog candidates only; do not search/rank the full PDK.
    resistor_ids = {(r.get('oa_library'), r.get('oa_cell')) for r in resistors[:3]}
    resistor_probe = [r for r in probe if (r.get('oa_library'),r.get('oa_cell')) in resistor_ids]
    tokens = specific_search_tokens(data,resistors,records)
    roots, root_notes = search_roots(data, bundle, args.pdk_dir)
    print('CACHED_INPUTS=READ_OK', flush=True)
    if args.cached_only:
        print('PDK_SEARCH=SKIPPED_CACHED_ONLY',flush=True)
        found = dict(hits=[],documents=[],skipped=[],limited=True,limits=['cached_only_no_search'],files_seen=0,bytes_read=0,elapsed_seconds=0)
    else:
        print('PDK_SEARCH=START roots=' + str(len(roots)), flush=True)
        found = search(roots, tokens, args)
    if not roots:
        found['limited'] = True; found['limits'].append('no_available_pdk_roots')
    for name, expected in fingerprints.items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise ValueError('source cache changed during collection: ' + name)
    output = Path(tempfile.mkdtemp(prefix='pdk_evidence_', dir=str(bridge.parent)))
    report = dict(schema='cascode-pdk-evidence-v2', accepted_bridge=str(bridge),
        targets=data['targets'], cached_native_cdf=records, supply_candidates=nodes,
        resistor_candidates=resistors[:3], resistor_candidates_total=len(resistors),
        resistor_probe=resistor_probe, resistor_selection_confirmed=False,
        search_roots=[str(r) for r in roots], search_tokens=sorted(set(tokens)),
        cache_notes=notes+root_notes, source_cache_sha256=fingerprints, search=found,
        native_executions=0, psf_read=False, rules_applied=False, electrical_rules_ready=False)
    (output/'evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    summary = ['CHECKER=cascode-pdk-evidence-v2','RESULT=EVIDENCE_COLLECTED',
        'SPECTRE_RERUN=false','OCEAN_RERUN=false','VIRTUOSO_RERUN=false',
        'OUTPUT_DIR='+str(output), 'ACCEPTED_BRIDGE='+str(bridge)]
    for name,item in data['targets'].items():
        master = compact_master(item['master'])
        summary.append('TARGET '+name+' '+json.dumps(master,ensure_ascii=False))
        for row in item.get('cdf_probe', []):
            if row.get('parameter') in ('l','w','fw','nfin','nf','fingers','m','mr'):
                fields={k:v for k,v in row.items() if k in ('parameter','min','max','units','choices','default_value','cdf_type')}
                summary.append('CDF '+name+' '+json.dumps(fields,ensure_ascii=False))
    for row in records:
        if row.get('kind') in ('cdf_minVal','cdf_maxVal','cdf_choices') and row.get('raw_value')!='nil':
            summary.append('NATIVE_CDF '+json.dumps(row,ensure_ascii=False))
    summary += callback_summary(records)
    for row in resistors[:3]:
        preview=compact_master(row)
        summary.append('RESISTOR_CANDIDATE '+json.dumps(preview,ensure_ascii=False))
    for row in resistor_probe:
        if row.get('parameter') in ('r','m','segL','segW','segments','nfin','cktL','cktW'):
            fields={k:v for k,v in row.items() if k in ('oa_library','oa_cell','parameter','min','max','units','choices','default_value','cdf_type')}
            summary.append('RESISTOR_CDF '+json.dumps(fields,ensure_ascii=False))
    for name,item in nodes.items():summary.append('RAIL_CANDIDATE '+name+' '+json.dumps(item,ensure_ascii=False))
    summary += ['SEARCH_ROOT '+str(r) for r in roots]
    summary.append('SEARCH_TOKENS='+','.join(tokens))
    summary += ['RULE_TEXT_CANDIDATE '+json.dumps(h,ensure_ascii=False) for h in found['hits'][:12]]
    docs = sorted(found['documents'],key=lambda r:(not r['device_name_match'],r['path']))
    summary += ['DOCUMENT_CANDIDATE '+json.dumps(h,ensure_ascii=False) for h in docs[:12]]
    summary += ['SEARCH_LIMIT '+reason for reason in found['limits'][:8]]
    summary.append('SEARCH_LIMITS_OMITTED='+str(max(0,len(found['limits'])-8)))
    summary += ['SEARCH_SKIP_REASON '+reason+' count='+str(count)
                for reason,count in sorted(Counter(x['reason'] for x in found['skipped']).items())]
    summary += ['TEXT_HITS='+str(len(found['hits'])),'DOCUMENTS_FOUND='+str(len(docs)),
        'SUMMARY_OMITTED_TEXT_HITS='+str(max(0,len(found['hits'])-12)),
        'SUMMARY_OMITTED_DOCUMENTS='+str(max(0,len(docs)-12)),
        'SEARCH_LIMITED='+str(found['limited']).lower(), 'SEARCH_SKIPPED_FILES='+str(len(found['skipped'])),
        'SEARCH_SECONDS='+str(found['elapsed_seconds']) if 'elapsed_seconds' in found else 'SEARCH_SECONDS=0',
        'PDK_ELECTRICAL_RULES_READY=false','RULES_APPLIED=false','VBIAS_GENERATED=false',
        'DETAILS_FILE='+str(output/'evidence.json'),'RAW_DETAILS_REMAIN_ON_SERVER=true']
    (output/'summary.txt').write_text('\n'.join(summary)+'\n')
    print('\n'.join(summary))
    return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session',required=True);parser.add_argument('--batch',required=True)
    parser.add_argument('--pdk-dir',action='append',default=[],help='additional known PDK documentation directory')
    parser.add_argument('--cached-only',action='store_true',help='print complete cached callbacks without searching PDK files')
    parser.add_argument('--seconds',type=float,default=45)
    parser.add_argument('--max-files',type=int,default=6000)
    parser.add_argument('--max-bytes',type=int,default=32*1024*1024)
    parser.add_argument('--max-depth',type=int,default=4)
    args=parser.parse_args()
    try:
        if min(args.seconds,args.max_files,args.max_bytes)<=0 or args.max_depth<0:
            raise ValueError('positive search budgets required')
        return run(args)
    except (OSError,ValueError,KeyError,TypeError) as error:
        print('CHECKER=cascode-pdk-evidence-v2\nRESULT=INCOMPLETE\nISSUE '+str(error))
        return 2


if __name__=='__main__':raise SystemExit(main())
