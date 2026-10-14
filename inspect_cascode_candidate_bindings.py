#!/usr/bin/env python3
"""Replay the latest retained *candidate* binding; never launch or approve EDA.

Exit zero means the report was read successfully, not that binding/DC passed.
The script writes only a new diagnostic directory and never changes inputs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

sys.dont_write_bytecode = True


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def newest(paths):
    paths = list(paths)
    if not paths:
        raise ValueError('required retained candidate files not found')
    return max(paths, key=lambda p: (p.stat().st_mtime_ns, str(p)))


def select_simulation(candidate):
    # Never fall back to baseline_op: the source already passed there.
    base = Path(candidate).resolve()/'work/analysis/candidates'
    return newest(base.glob('candidate_*/raw_op/st-op-simulation.*/binding.json')).parent


def emit(key, value):
    if isinstance(value, bool): value = str(value).lower()
    elif isinstance(value, (list, dict)): value = json.dumps(value, ensure_ascii=True, sort_keys=True)
    print(key+'='+str(value), flush=True)


def group_difference(parent, actual, original, bindings, catalogs, op):
    def members(items):
        return {name:d for name,d in items.items() if name == parent or op.generated_resistor_parent(name) == parent}
    old, new = members(original), members(actual)
    reasons = []
    if parent not in original: reasons.append('absent_from_baseline')
    if parent not in actual: reasons.append('parent_absent_from_candidate')
    proof = bindings.get(parent)
    if not proof: reasons.append('parent_oa_binding_missing')
    elif proof.get('classification') != 'target': reasons.append('parent_oa_binding_not_target')
    identity = None
    if proof and parent in original:
        matches = [row for row,_ in catalogs.get(original[parent]['master'], [])
                   if row['oa_library'] == proof['oa_library'] and row['oa_cell'] == proof['oa_cell']
                   and row.get('kind') == 'resistor']
        identity = len(matches) == 1 and matches[0]['terminal_names'] == proof['terminal_names']
        if not identity: reasons.append('parent_master_or_terminals_differ')
    if set(old) != set(new): reasons.append('segment_names_changed')
    # Index matching is ONLY to explain a rejected comparison; it never creates
    # production OA identities or permits these devices to be skipped.
    def by_index(items):
        result = {}
        for name in items:
            match = re.fullmatch(r'.+_(\d+)_{1,2}res_gen', name)
            index = int(match[1]) if match else 1
            result.setdefault(index, []).append(name)
        return result
    before, after = by_index(old), by_index(new)
    differences = []
    for index in sorted(set(before) | set(after)):
        a, b = before.get(index, []), after.get(index, [])
        row = dict(index=index, baseline_names=a, candidate_names=b)
        if len(a) != 1 or len(b) != 1:
            row['issue'] = 'missing_or_ambiguous_index'
            reasons.append('segment_count_or_index_changed')
        else:
            x, y = old[a[0]], new[b[0]]
            sx, sy = op.physical_signature(x), op.physical_signature(y)
            if sx[0] != sy[0]:
                row['model'] = dict(baseline=sx[0], candidate=sy[0]); reasons.append('segment_model_changed')
            if sx[1] != sy[1]:
                row['nodes'] = dict(baseline=sx[1], candidate=sy[1]); reasons.append('segment_nodes_changed')
            if sx[2] != sy[2]:
                row['parameters'] = {k:dict(baseline=sx[2].get(k), candidate=sy[2].get(k))
                    for k in sorted(set(sx[2]) | set(sy[2])) if sx[2].get(k) != sy[2].get(k)}
                reasons.append('segment_parameters_changed')
        if a != b or len(row) > 3: differences.append(row)
    # This mirrors the production check's original-node set so its failure can
    # be explained exactly, even when the candidate uses a different spelling.
    nodes = {n for d in old.values() for n in d['nodes']}
    internal = {n for n in nodes if sum(n in d['nodes'] for d in old.values()) > 1}
    names = set(old)
    def contacts(items):
        return {name:[(i,n) for i,n in enumerate(d['nodes']) if n in internal]
                for name,d in items.items() if name not in names and internal.intersection(d['nodes'])}
    old_contacts, new_contacts = contacts(original), contacts(actual)
    if old_contacts != new_contacts: reasons.append('internal_node_contacts_changed')
    if any(d['master'] != (proof or {}).get('model_name') for d in old.values()):
        reasons.append('baseline_segment_model_not_parent_model')
    return dict(parent=parent, reasons=sorted(set(reasons)), baseline_present=parent in original,
        candidate_present=parent in actual, parent_binding=proof, parent_identity_matches=identity,
        baseline_names=sorted(old), candidate_names=sorted(new), differences=differences,
        internal_contacts=dict(baseline=old_contacts, candidate=new_contacts),
        baseline_segments=old, candidate_segments=new)


def inspect(candidate, engine):
    candidate = Path(candidate).resolve(); work = candidate/'work'; hashes = {}
    def read(path):
        path = Path(path).resolve(); raw = path.read_bytes()
        hashes[str(path)] = hashlib.sha256(raw).hexdigest()
        return raw.decode('utf-8')
    def data(path): return json.loads(read(path))
    site = Path(engine).resolve()/'server/site'
    read(site/'op_provider.py'); sys.path.insert(0, str(site)); import op_provider as op
    if Path(op.__file__).resolve() != site/'op_provider.py':
        raise ValueError('loaded parser belongs to another engine')
    simulation = select_simulation(candidate)
    binding = data(simulation/'binding.json')
    text = read(simulation/'simulation.scs')
    if hashlib.sha256(text.encode()).hexdigest() != binding['simulation_sha256']:
        raise ValueError('retained simulation fingerprint changed')
    statuses = list(candidate.glob('resume_generate_*/run_status.json'))
    status = data(newest(statuses) if statuses else candidate/'run_status.json')
    provider = status.get('provider_manifest', str(work/'analysis/standalone_inputs/provider_inputs.json'))
    inputs = data(provider)
    for key in ('rules', 'tech'):
        path = Path(inputs[key]).resolve(); read(path)
        if inputs.get('file_sha256', {}).get(str(path)) != hashes[str(path)]:
            raise ValueError('retained provider '+key+' fingerprint changed')
    profile = data(inputs['rules']); configs = data(inputs['tech'])
    if profile.get('validation_scope') != 'experimental_dc':
        raise ValueError('expected experimental_dc profile')
    bundle_path = Path(profile['validated_baseline_bundle']).resolve()
    bundle = data(bundle_path)
    if read(bundle_path.with_suffix('.sha256')).strip() != hashes[str(bundle_path)]:
        raise ValueError('baseline bundle fingerprint changed')
    baseline = read(bundle['bench_netlist'])
    if hashlib.sha256(baseline.encode()).hexdigest() != bundle['bench_sha256']:
        raise ValueError('baseline Bench fingerprint changed')
    if binding['root_path'] != bundle['root_path'] or binding['corner'] != bundle['corner']:
        raise ValueError('candidate and baseline hierarchy/Corner differ')
    cfg = dict(line.split('=', 1) for line in read(work/'session.conf').splitlines() if '=' in line)
    tech = [t for t in configs if t['version'] == cfg['pdk_version']]
    if len(tech) != 1: raise ValueError('requested PDK configuration ambiguous')
    catalog = newest(p for p in (work/'analysis/pdk_scan').glob('run_*/raw_catalog.tsv')
                     if digest(p) == binding['scanned_catalog_sha256'])
    read(catalog); read(simulation/'oa_bindings.tsv')
    catalogs = op.load_scanned_catalog(catalog, tech[0], cfg['pdk_version'], 'experimental_dc')
    raw_bindings = op.read_oa_bindings(simulation/'oa_bindings.tsv')
    bindings = op.expand_physical_bindings(raw_bindings)
    root = binding['root_path']; master = binding['dut'][1]
    leaves = op.flatten_dut(text, root, master)
    old_leaves = op.flatten_dut(baseline, root, bundle['source_subckt'])
    kept, preserved = op.preserved_resistor_groups(leaves, old_leaves, root, catalogs, bindings)
    def indexed(items):
        result = {op.physical_instance_key(d['path'][len(root)+1:]):d for d in items}
        if len(result) != len(items): raise ValueError('duplicate comparison paths')
        return result
    actual, original = indexed(leaves), indexed(old_leaves)
    missing = [name for name,d in actual.items() if name not in kept and name not in bindings and d['master'] in catalogs]
    parents = sorted({op.generated_resistor_parent(name) or name for name in missing})
    groups = [group_difference(p, actual, original, bindings, catalogs, op) for p in parents]
    error = None
    try:
        op.bind_physical_devices(text, root, master, catalogs, raw_bindings,
            baseline_text=baseline, baseline_master=bundle['source_subckt'])
    except (ValueError, KeyError, TypeError) as failed:
        error = str(failed)
    for path, expected in hashes.items():
        if digest(path) != expected: raise ValueError('retained source changed while reading: '+path)
    report = dict(checker='cascode-candidate-binding-replay-v1', simulation_directory=str(simulation),
        candidate_design=binding['dut'], baseline_source=bundle['source'], root_path=root,
        binding_replay_passed=error is None, production_error=error, preserved_groups=preserved,
        missing_instances=missing, groups=groups, source_file_sha256=hashes,
        native_executions=0, production_bindings_changed=False, electrical_verified=False)
    out = Path(tempfile.mkdtemp(prefix='candidate_binding_review_', dir=str(candidate)))
    details = out/'binding_replay.json'; details.write_text(json.dumps(report, indent=2)+'\n')
    emit('RESULT', 'CANDIDATE_BINDING_EVIDENCE_READ_OK'); emit('SIMULATION_DIR', simulation)
    emit('BINDING_REPLAY', 'PASS' if error is None else 'FAIL'); emit('PRODUCTION_ERROR', error)
    emit('PRESERVED_GROUP_COUNT', len(preserved)); emit('UNBOUND_INSTANCE_COUNT', len(missing))
    emit('FAILED_GROUP_COUNT', len(groups))
    for group in groups[:24]:
        emit('GROUP', {k:group[k] for k in ('parent', 'reasons', 'baseline_present', 'candidate_present', 'parent_identity_matches')})
        emit('GROUP_COUNTS', dict(parent=group['parent'], baseline=len(group['baseline_names']), candidate=len(group['candidate_names'])))
        emit('PARENT_OA', group['parent_binding'])
        for row in group['differences'][:3]: emit('SEGMENT_DIFF', row)
        emit('OMITTED_SEGMENT_DIFFS', max(0,len(group['differences'])-3))
        if 'internal_node_contacts_changed' in group['reasons']: emit('INTERNAL_CONTACTS', group['internal_contacts'])
    emit('OMITTED_GROUPS', max(0,len(groups)-24))
    emit('SOURCE_FILES_UNCHANGED', True); emit('DETAILS_FILE', details)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', required=True)
    parser.add_argument('--candidate', required=True)
    args = parser.parse_args()
    emit('CHECKER', 'cascode-candidate-binding-replay-v1')
    emit('NATIVE_EXECUTIONS', 0); emit('SPECTRE_RERUN', False); emit('SOURCE_OA_SAVED', False)
    try:
        inspect(args.candidate, args.engine)
        return 0
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
        emit('RESULT', 'INCOMPLETE'); emit('ISSUE', str(error))
        return 2
    finally:
        emit('PRODUCTION_BINDINGS_CHANGED', False); emit('ELECTRICAL_VERIFIED', False)


if __name__ == '__main__': raise SystemExit(main())
