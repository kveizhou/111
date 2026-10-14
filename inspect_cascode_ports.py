#!/usr/bin/env python3
"""Inspect a retained failed baseline export. No EDA, writes, or port changes.

May run inside scripts/ or as a standalone uploaded file with --engine.
Exit 0 means evidence read, NOT that the circuit or the port check passed.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True


def emit(key, value):
    if isinstance(value, bool): value = str(value).lower()
    elif isinstance(value, (dict, list)): value = json.dumps(value, ensure_ascii=True, sort_keys=True)
    print(key + '=' + str(value), flush=True)


def newest(paths, label):
    paths = list(paths)
    if not paths: raise ValueError('no retained ' + label)
    return max(paths, key=lambda p: (p.stat().st_mtime_ns, str(p)))


def inspect(candidate, engine):
    candidate = Path(candidate).resolve()
    emit('CANDIDATE_DIR', candidate)
    raw = candidate / 'work/analysis/baseline_op/raw_op'
    export_log = newest(raw.glob('st-op-simulation.*/export_dut.log'), 'baseline export log under ' + str(raw))
    simulation = export_log.parent
    emit('SIMULATION_DIR', simulation)
    records = {}

    def read(path):
        path = Path(path)
        data = path.read_bytes()
        records[str(path)] = hashlib.sha256(data).hexdigest()
        return data.decode('utf-8')

    config = json.loads(read(candidate / 'inputs.json'))
    profile = json.loads(read(config['profile']))
    bundle = json.loads(read(profile['validated_baseline_bundle']))
    source = bundle['source_subckt']
    emit('SOURCE_SUBCKT', source)
    emit('EXPORT_LOG_TAIL', read(export_log).splitlines()[-8:])
    dut = simulation / 'dut_oa'
    physical = read(dut / 'ports.txt').splitlines()
    emit('OA_PORTS', physical)
    script = read(dut / 'runtime.ocn')
    designs = re.findall(r'^\s*design\(([^\n]*)\)\s*$', script, re.M)
    if len(designs) != 1: raise ValueError('expected one actual design() in ' + str(dut / 'runtime.ocn'))
    design = [json.loads(v) for v in re.findall(r'"(?:[^"\\]|\\.)*"', designs[0])]
    if len(design) != 3: raise ValueError('cannot read actual design library/cell/view')
    emit('ACTUAL_OA_DESIGN', design)
    emit('NATIVE_EXPORT_MARKER', read(dut / 'runtime.done').strip())
    site = Path(engine).resolve() / 'server/site'
    pinned = json.loads(read(candidate / 'work/analysis/standalone_inputs/provider_inputs.json')).get('file_sha256', {})
    for filename in ('op_provider.py', 'cadence_runtime.py'):
        read(site / filename)
    matches = all(pinned.get(str(site / f)) == records[str(site / f)]
                  for f in ('op_provider.py', 'cadence_runtime.py'))
    emit('PARSER_MATCHES_SESSION', matches)
    sys.path.insert(0, str(site))
    from op_provider import parse_deck
    from cadence_runtime import wrap_dut
    bench = parse_deck(read(simulation / 'bench.scs'))
    if source not in bench['definitions']: raise ValueError('source subckt missing from retained bench: ' + source)
    expected = bench['definitions'][source]['ports']
    emit('BENCH_PORTS', expected)
    emit('OA_PORT_COUNT', len(physical))
    emit('BENCH_PORT_COUNT', len(expected))
    emit('OA_ONLY', sorted(set(physical) - set(expected)))
    emit('BENCH_ONLY', sorted(set(expected) - set(physical)))
    emit('OA_DUPLICATES', [k for k, v in Counter(physical).items() if v > 1])
    emit('BENCH_DUPLICATES', [k for k, v in Counter(expected).items() if v > 1])
    emit('RAW_PORT_SET_MATCH', len(set(physical)) == len(physical) and set(physical) == set(expected))
    emit('RAW_PORT_ORDER_MATCH', physical == expected)
    generated = list((dut / 'generated').rglob('input.scs'))
    emit('GENERATED_INPUT_COUNT', len(generated))
    if len(generated) != 1: raise ValueError('generated input.scs missing or ambiguous')
    emit('GENERATED_INPUT', generated[0])
    text = read(generated[0])
    # The current production code is replayed entirely in memory. No output
    # netlist is written, even when wrap_dut accepts the retained data.
    if matches:
        try:
            wrap_dut(text, design[1], physical, expected, bundle.get('variables', {}))
            emit('WRAP_REPLAY_PASSED', True)
        except (ValueError, KeyError) as error:
            emit('WRAP_REPLAY_PASSED', False)
            emit('REPLAY_ERROR', str(error))
    else:
        emit('WRAP_REPLAY_PASSED', 'NOT_REPLAYED_CODE_DIFFERS_FROM_SESSION')
    try:
        actual = parse_deck(text)
        header = actual['definitions'].get(design[1])
        emit('EXPORTED_DUT_HEADER_PORTS', header['ports'] if header else 'NO_HEADER_TOP_LEVEL_EXPORT')
        nodes = {n for instance in actual['top'] for n in instance['nodes']}
        emit('TOP_LEVEL_INSTANCE_COUNT', len(actual['top']))
        emit('BENCH_PORTS_SEEN_IN_TOP_NODES', [p for p in expected if p in nodes])
        emit('BENCH_PORTS_NOT_SEEN_IN_TOP_NODES', [p for p in expected if p not in nodes])
        emit('TOP_NODE_MATCH_IS_CONNECTIVITY_PROOF', False)
    except ValueError as error:
        emit('EXPORTED_DECK_PARSE_ISSUE', str(error))
    # Prevent reading a mixture of files while a new generate is active.
    for path, digest in records.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError('evidence changed during read: ' + path)
    emit('EVIDENCE_UNCHANGED', True)
    emit('EVIDENCE_FILE_COUNT', len(records))
    emit('RESULT', 'PORT_EVIDENCE_READ_OK')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--batch', help='select latest candidate by its run_status.json')
    source.add_argument('--candidate', help='read one explicit candidate')
    parser.add_argument('--engine', default=str(Path(__file__).resolve().parents[1]),
                        help='installed st-engine-maau directory; required for a standalone upload')
    args = parser.parse_args()
    emit('CHECKER', 'cascode-port-evidence-v1')
    emit('NATIVE_EXECUTIONS', 0)
    emit('SPECTRE_RERUN', False)
    emit('OCEAN_RERUN', False)
    emit('SOURCE_FILES_WRITTEN', False)
    try:
        candidate = Path(args.candidate) if args.candidate else newest(
            Path(args.batch).resolve().glob('candidate_*/run_status.json'), 'candidate run_status.json').parent
        return inspect(candidate, args.engine)
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
        emit('RESULT', 'INCOMPLETE')
        emit('ISSUE', str(error))
        return 2
    finally:
        emit('EXPERIMENTAL_DC_READY', False)
        emit('PUBLISHED', False)


if __name__ == '__main__': raise SystemExit(main())
