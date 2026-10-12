#!/usr/bin/env python3
"""Read published Source-resistor/Stack results locally; print only a bounded summary.

Raw OA exports, commands, errors and differences stay in --output. No network
client, upload, OA write, generation or electrical simulation is performed.
"""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

VERSION = 'structure-result-v1'
NUMBER = re.compile(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(meg|[fpnumkg])?', re.I)
SCALE = {'': 1, 'f': 1e-15, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6,
         'm': 1e-3, 'k': 1e3, 'meg': 1e6, 'g': 1e9}


def numeric(value):
    match = NUMBER.fullmatch(value)
    if not match:
        return None
    result = float(match[1]) * SCALE[(match[2] or '').lower()]
    return result if math.isfinite(result) else None


def equivalent(left, right):
    if left == right:
        return True
    a, b = numeric(left), numeric(right)
    return a is not None and b is not None and a == b


def pairs(path):
    result = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if '=' not in line:
            raise ValueError('invalid key/value record in ' + str(path))
        key, value = line.split('=', 1)
        if not key or key in result:
            raise ValueError('empty/duplicate key in ' + str(path))
        result[key] = value
    return result


def assignments(text):
    """Strict exporter tokens, including empty values and balanced expressions."""
    result = {}
    while text.strip():
        text = text.lstrip()
        match = re.match(r'([^\s=()]+)=', text)
        if not match:
            raise ValueError('unparsed parameter text: ' + text)
        key = match[1]; text = text[match.end():]
        end = 0
        if text.startswith('('):
            depth = 0
            for end, char in enumerate(text, 1):
                depth += (char == '(') - (char == ')')
                if depth == 0:
                    break
            if depth:
                raise ValueError('unbalanced parameter expression')
        else:
            while end < len(text) and not text[end].isspace():
                end += 1
        value, text = text[:end], text[end:]
        if key in result and not equivalent(result[key], value):
            raise ValueError('conflicting duplicate parameter: ' + key)
        result[key] = value
    return result


def parse(text):
    """Accept only the structural subset used by this project's OA exporter."""
    lines, pending = [], ''
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('//'):
            continue
        if line.startswith('+'):
            if not pending and not lines:
                raise ValueError('invalid plus continuation')
            if not pending:
                pending = lines.pop() + ' '
            line = line[1:].strip()
        line = pending + line
        if line.endswith('\\'):
            pending = line[:-1] + ' '
        else:
            lines.append(line); pending = ''
    if pending:
        raise ValueError('unterminated continuation')
    definitions, current = {}, None
    for line in lines:
        words = line.split()
        if words[0] == 'subckt':
            if current is not None or len(words) < 2 or words[1] in definitions:
                raise ValueError('invalid/duplicate subckt')
            if any('=' in pin for pin in words[2:]) or len(set(words[2:])) != len(words[2:]):
                raise ValueError('unproven/duplicate subckt ports')
            current = {'ports': words[2:], 'params': {}, 'instances': {}}
            definitions[words[1]] = current; name = words[1]
        elif words[0] == 'ends':
            if current is None or words != ['ends', name]:
                raise ValueError('unmatched ends')
            current = None
        elif words[0] == 'parameters' and current is not None:
            extra = assignments(line[len('parameters'):])
            if set(extra) & set(current['params']):
                raise ValueError('duplicate subckt parameters')
            current['params'].update(extra)
        else:
            match = re.fullmatch(r'([^\s()]+)\s*\(([^)]*)\)\s+(\S+)(.*)', line)
            if current is None or not match:
                raise ValueError('unsupported structural statement: ' + line)
            inst, nodes, master, tail = match.groups()
            if inst in current['instances']:
                raise ValueError('duplicate instance: ' + inst)
            current['instances'][inst] = {'master': master, 'nodes': nodes.split(), 'params': assignments(tail)}
    if current is not None or not definitions:
        raise ValueError('missing complete subckt')
    return definitions


def one(path, name):
    definitions = parse(Path(path).read_text(encoding='utf-8'))
    if set(definitions) != {name}:
        raise ValueError('export does not contain exactly its requested subckt')
    return definitions[name]


def record(checks, code, ok, detail=''):
    checks.append({'code': code, 'ok': bool(ok), 'detail': detail if not ok else ''})


def compare(e, a, checks, prefix, allowed=None):
    allowed = allowed or {}
    record(checks, prefix + '_PORTS', e['ports'] == a['ports'])
    record(checks, prefix + '_SUBCKT_PARAMETERS', e['params'] == a['params'])
    record(checks, prefix + '_INSTANCES', set(e['instances']) == set(a['instances']))
    for name in sorted(set(e['instances']) & set(a['instances'])):
        left, right = e['instances'][name], a['instances'][name]
        record(checks, prefix + '_MASTER', left['master'] == right['master'], name)
        record(checks, prefix + '_CONNECTIONS', left['nodes'] == right['nodes'], name)
        for key, value in left['params'].items():
            record(checks, prefix + '_PARAMETER', key in right['params'] and equivalent(value, right['params'][key]),
                   name + '.' + key + ': expected=' + repr(value) + ' actual=' + repr(right['params'].get(key)))
        for key in set(right['params']) - set(left['params']):
            record(checks, prefix + '_EXTRA_PARAMETER', key in allowed.get(name, set()), name + '.' + key)


def read_catalog(path, policy):
    with Path(path).open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    with Path(policy).open(encoding='utf-8', newline='') as stream:
        orders = {(r['oa_library'], r['oa_cell']): r['terminal_order'].split(',') for r in csv.DictReader(stream, delimiter='\t')}
    catalog = {}
    for row in rows:
        if row['master'] in catalog:
            raise ValueError('duplicate catalog master')
        names, roles = row['terminal_names'].split(','), row['terminal_roles'].split(',')
        if len(names) != len(roles) or len(set(names)) != len(names):
            raise ValueError('invalid catalog terminal mapping')
        if orders.get((row['oa_library'], row['oa_cell'])) != names:
            raise ValueError('export policy terminal order disagrees with scanned catalog')
        row['roles'] = roles
        row['cdf_names'] = {x.split(':', 1)[1] for x in row['normalized_to_cdf'].split(',') if ':' in x}
        catalog[row['master']] = row
    return catalog


def semantic(inst, catalog, translate=lambda x: ('external', x)):
    device = catalog[inst['master']]
    roles = device['roles']
    if len(roles) != len(inst['nodes']) or len(set(roles)) != len(roles):
        raise ValueError('cannot resolve physical terminals')
    return dict(zip(roles, map(translate, inst['nodes'])))


def graph_checks(cfg, baseline, root, packages, catalog, operations, checks):
    body = baseline['instances']
    used_packages = set(); targets = {op['instance'] for op in operations}
    for op in operations:
        target = op['instance']; original = body[target]
        prefix = 'R' if op['type'] == 'resistor' else 'STACK'
        matches = [(scope, cell) for scope, cell in packages.items() if target in cell['instances']]
        record(checks, prefix + '_PACKAGE', len(matches) == 1)
        if len(matches) != 1:
            continue
        scope, cell = matches[0]; used_packages.add(scope)
        wrappers = [i for i in root['instances'].values() if i['master'] == scope]
        record(checks, prefix + '_WRAPPER', len(wrappers) == 1 and len(wrappers[0]['nodes']) == len(cell['ports']))
        if len(wrappers) != 1 or len(wrappers[0]['nodes']) != len(cell['ports']):
            continue
        outer = dict(zip(cell['ports'], wrappers[0]['nodes']))
        translate = lambda net: ('external', outer[net]) if net in outer else ('local', scope, net)
        wanted = semantic(original, catalog)
        members = cell['instances']; retained = members[target]
        mos = [i for i in members.values() if catalog.get(i['master'], {}).get('kind') in ('mos', 'mos_n', 'mos_p')]
        for inst in mos:
            record(checks, prefix + '_MOS_MASTER', inst['master'] == original['master'])
            record(checks, prefix + '_MOS_PARAMETERS', set(inst['params']) == set(original['params']) and
                   all(equivalent(v, inst['params'].get(k, '\x00')) for k, v in original['params'].items()))
        try:
            if op['type'] == 'resistor':
                resistors = [i for i in members.values() if catalog.get(i['master'], {}).get('kind') == 'resistor']
                record(checks, 'R_COUNT', len(members) == 2 and len(mos) == 1 and len(resistors) == 1)
                if len(mos) != 1 or len(resistors) != 1:
                    continue
                actual = semantic(retained, catalog, translate)
                for role in set(wanted) - {'source'}:
                    record(checks, 'R_' + role.upper(), actual.get(role) == wanted[role])
                inner = actual['source']
                record(checks, 'R_SOURCE_INTERNAL', inner[0] == 'local')
                resistor = resistors[0]; ends = semantic(resistor, catalog, translate)
                record(checks, 'R_SERIES', set(ends) == {'positive', 'negative'} and
                       set(ends.values()) == {inner, wanted['source']} and inner != wanted['source'])
                record(checks, 'R_MASTER', resistor['master'] == op['resistor.master'])
                parameter = op['resistor.parameter']
                record(checks, 'R_VALUE', equivalent(op['resistor.value'], resistor['params'].get(parameter, '\x00')))
            else:
                count = int(op['stage_count'])
                record(checks, 'STACK_COUNT', len(members) == len(mos) == count)
                chain = [semantic(i, catalog, translate) for i in mos]
                record(checks, 'STACK_GATE', all(i.get('gate') == wanted['gate'] for i in chain))
                record(checks, 'STACK_BULK', all(i.get('bulk') == wanted.get('bulk') for i in chain))
                record(checks, 'STACK_DRAIN_ORIGINAL', semantic(retained, catalog, translate).get('drain') == wanted['drain'])
                node, remaining, seen, valid = wanted['drain'], list(chain), set(), True
                for index in range(count):
                    next_stages = [i for i in remaining if i.get('drain') == node]
                    if len(next_stages) != 1:
                        valid = False; break
                    stage = next_stages[0]; remaining.remove(stage); node = stage.get('source')
                    if index < count - 1:
                        if not node or node[0] != 'local' or node in seen:
                            valid = False
                        seen.add(node)
                record(checks, 'STACK_CHAIN', valid and not remaining and node == wanted['source'])
        except (KeyError, ValueError) as error:
            record(checks, prefix + '_TERMINALS', False, str(error))
    record(checks, 'PACKAGES_DISTINCT', len(used_packages) == 2)
    untouched = {k: v for k, v in body.items() if k not in targets}
    wrapper_names = {k for k, v in root['instances'].items() if v['master'] in packages}
    remaining = {k: v for k, v in root['instances'].items() if k not in wrapper_names}
    compare({'ports': baseline['ports'], 'params': baseline['params'], 'instances': untouched},
            {'ports': root['ports'], 'params': root['params'], 'instances': remaining}, checks, 'UNTOUCHED')


def summary(details):
    checks = details.get('checks', [])
    lines = ['CHECKER=' + VERSION, 'RESULT=' + details['result'],
             'VALIDATION_SCOPE=structure_only', 'EXPORTS_COMPLETED=' + str(details.get('exports_completed', 0))]
    for code in sorted({x['code'] for x in checks}):
        group = [x for x in checks if x['code'] == code]
        failed = sum(not x['ok'] for x in group)
        lines.append(code + '=' + ('FAIL' if failed else 'PASS') + ' checks=' + str(len(group)) + ' failures=' + str(failed))
    if details.get('stop_code'):
        lines.append('STOP_CODE=' + details['stop_code'])
    lines += ['FAILED_CHECKS=' + str(sum(not x['ok'] for x in checks)),
              'ELECTRICAL_VERIFIED=false', 'GUI_APPEARANCE_VERIFIED=false',
              'EXPLICIT_OA_PROPERTIES_INDEPENDENTLY_VERIFIED=false', 'RAW_DETAILS_REMAIN_ON_SERVER=true']
    if len(lines) > 190:
        lines = lines[:180] + ['SUMMARY_TRUNCATED=true', 'RESULT=' + details['result']]
    return '\n'.join(lines) + '\n'


def check(session, output, details):
    from site_data import read_json, verify_site_inputs
    from standalone import environment
    cfg = pairs(session / 'session.conf'); report = pairs(session / 'reports/validation.txt')
    manifest = session / 'analysis/standalone_inputs/provider_inputs.json'
    inputs = read_json(manifest); verify_site_inputs(inputs)
    if cfg['validation_scope'] != 'structure_only' or report.get('validation_scope') != 'structure_only':
        raise ValueError('need a structural session')
    source = {k: cfg['source_' + k] for k in ('library', 'cell', 'view')}
    target = {'library': cfg['variant_library'], 'cell': cfg['variant_cell'], 'view': 'schematic'}
    if (report.get('ok'), report.get('structural_ready'), report.get('stage'), report.get('generated_cells')) != ('true','true','complete','2'):
        raise ValueError('need a successful two-package generation report')
    for key, ref in [('source', source), ('target', target)]:
        if report.get(key) != '/'.join(ref[k] for k in ('library','cell','view')):
            raise ValueError('generation report belongs to another CellView')
    plan = read_json(session / 'materialization/plan.json')
    if any(plan['source'][k] != source[k] for k in source):
        raise ValueError('plan source identity differs from session')
    staging = target['library'] + '__STAGING'
    if plan['target']['library'] != staging or plan['target']['cell'] != target['cell'] + '__STAGING':
        raise ValueError('plan staging identity differs from session')
    generated = plan['generated_cells']
    if len(generated) != 2 or len({g['schematic']['cell'] for g in generated}) != 2:
        raise ValueError('need exactly two distinct functional packages')
    if any(g['schematic']['library'] != staging or g['schematic']['view'] != 'schematic' for g in generated):
        raise ValueError('unproven package identity')
    operations = [pairs(p) for p in sorted((session / 'changes').glob('*.conf'))]
    if len(operations) != 2 or sorted(o['type'] for o in operations) != ['resistor','stack']:
        raise ValueError('need exactly one active Source resistor and one Stack')
    if len({o['instance'] for o in operations}) != 2:
        raise ValueError('need distinct targets')
    for op in operations:
        if op['type'] == 'stack' and (op.get('gate_policy') != 'shared' or not 2 <= int(op['stage_count']) <= 100):
            raise ValueError('unproven shared-gate stack request')
        if op['type'] == 'resistor' and (numeric(op['resistor.value']) is None or numeric(op['resistor.value']) <= 0):
            raise ValueError('need a finite positive requested resistance')
    paths = [session / p for p in ('session.conf','reports/validation.txt','materialization/plan.json',
             'before/core_before.scs','expected/core_expected.scs','before/device_catalog.tsv','analysis/device_policy.tsv')]
    paths += sorted((session / 'changes').glob('*.conf'))
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    pinned = {str(p): digest(p) for p in paths}
    catalog = read_catalog(session / 'before/device_catalog.tsv', session / 'analysis/device_policy.tsv')
    baseline = one(session / 'before/core_before.scs', cfg['core_subckt'])
    for op in operations:
        inst = baseline['instances'][op['instance']]
        if catalog[inst['master']]['kind'] not in ('mos','mos_n','mos_p') or any(c in op['instance'] for c in '<>:'):
            raise ValueError('need current-layer scalar MOS targets')
    env = environment(inputs, manifest); env.pop('ST_PREPARED_JSON_FILE', None)
    (output / 'backend_runs').mkdir()
    env['ST_BACKEND_RUN_ROOT'] = str(output / 'backend_runs')
    views = [('source', source, cfg['core_subckt']), ('root', target, cfg['core_subckt'])]
    for index, g in enumerate(generated, 1):
        ref = dict(g['schematic'], library=target['library'])
        views.append(('package_' + str(index), ref, 'oa_' + ref['library'] + '__' + ref['cell']))
    actual = {}; commands = []
    for label, ref, subckt in views:
        path = output / (label + '.scs')
        command = [cfg['backend'], 'netlist', '--cds-lib', cfg['cds_lib'], '--lib', ref['library'],
                   '--cell', ref['cell'], '--view', ref['view'], '--core-subckt', subckt,
                   '--output', str(path), '--device-policy', str(session / 'analysis/device_policy.tsv')]
        commands.append(command); details['commands'] = commands
        print('READ_' + label.upper() + '=START', flush=True)
        with (output / (label + '_export.log')).open('x', encoding='utf-8') as log:
            result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
        if result.returncode:
            details['backend_exit_code'] = result.returncode
            raise RuntimeError('read-only export failed: ' + label)
        if not path.is_file() or not path.stat().st_size:
            raise ValueError('missing/empty actual export: ' + label)
        actual[subckt if label != 'source' else '__source__'] = one(path, subckt)
        details['exports_completed'] += 1
        print('READ_' + label.upper() + '=COMPLETE', flush=True)
    if any(digest(Path(p)) != h for p, h in pinned.items()):
        raise ValueError('session evidence changed during readback')
    verify_site_inputs(inputs)
    details['file_sha256'] = dict(pinned, **{str(p): digest(p) for p in output.glob('*.scs')})
    checks = details['checks']; compare(baseline, actual.pop('__source__'), checks, 'SOURCE')
    expected = parse((session / 'expected/core_expected.scs').read_text(encoding='utf-8'))
    remap = {'oa_' + g['schematic']['library'] + '__' + g['schematic']['cell']:
             'oa_' + target['library'] + '__' + g['schematic']['cell'] for g in generated}
    if len({remap.get(k,k) for k in expected}) != len(expected):
        raise ValueError('expected scope rename collision')
    expected = {remap.get(k,k): v for k,v in expected.items()}
    for cell in expected.values():
        for inst in cell['instances'].values():
            inst['master'] = remap.get(inst['master'], inst['master'])
    record(checks, 'EXPECTED_SCOPES', set(expected) == set(actual))
    allowances = {}
    for g in generated:
        scope = 'oa_' + target['library'] + '__' + g['schematic']['cell']
        allowances[scope] = {}
        for inst in g['create_instances']:
            extra = set(inst.get('allowed_extra_cdf_parameters', []))
            if not extra:
                continue
            item = expected[scope]['instances'][inst['name']]
            device = catalog[item['master']]
            if device['kind'] != 'resistor' or not extra <= device['cdf_names']:
                raise ValueError('extra-parameter approval lacks actual resistor CDF declaration')
            allowances[scope][inst['name']] = extra
    for scope in set(expected) & set(actual):
        compare(expected[scope], actual[scope], checks, 'EXPECTED', allowances.get(scope))
    for cell in actual.values():
        for inst in cell['instances'].values():
            record(checks, 'NO_STAGING_DEPENDENCY', '__STAGING' not in inst['master'])
    packages = {key: actual[key] for key in remap.values() if key in actual}
    graph_checks(cfg, baseline, actual[cfg['core_subckt']], packages, catalog, operations, checks)
    details['result'] = 'FAIL' if any(not x['ok'] for x in checks) else 'PASS'
    return 1 if details['result'] == 'FAIL' else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', required=True)
    parser.add_argument('--output', help='new server-local directory; existing directories are refused')
    args = parser.parse_args()
    output = None
    details = {'checker': VERSION, 'result': 'INCOMPLETE', 'checks': [], 'exports_completed': 0}
    status = 2
    try:
        session = Path(args.session).resolve()
        if args.output:
            requested = Path(args.output).expanduser()
            if not requested.is_absolute():
                raise ValueError('output must be a new absolute directory')
            requested.mkdir(parents=True, exist_ok=False); output = requested
        else:
            output = Path(tempfile.mkdtemp(prefix='structure_check_', dir=str(session.parent)))
        status = check(session, output, details)
    except Exception as error:
        details['result'] = 'INCOMPLETE'
        details['stop_code'] = 'BACKEND_READ_FAILED' if isinstance(error, RuntimeError) else 'INPUT_OR_PARSE_UNPROVEN'
        details['local_error'] = type(error).__name__ + ': ' + str(error)
    text = summary(details)
    if output is not None:
        try:
            (output / 'details.json').write_text(json.dumps(details, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            (output / 'summary.txt').write_text(text, encoding='utf-8')
        except OSError:
            details.update(result='INCOMPLETE', stop_code='LOCAL_REPORT_WRITE_FAILED')
            status = 2; text = summary(details)
    sys.stdout.write(text)
    return status


if __name__ == '__main__':
    sys.exit(main())
