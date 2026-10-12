#!/usr/bin/env python3
"""Read saved Maestro settings without saving, netlisting or simulating the design."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
MARKER = 'ST_MAESTRO_SETUP_READ_COMPLETE'
PREFIX = 'ST_MAE_RECORD\t'
MAX_LINES = 190

# AXL setup objects are opaque handles: access them through axlGet* APIs,
# never through OA getq/->. Model/variable expressions remain raw evidence.
ACTION = r'''load(getShellEnvVar("ST_SKILL_INIT"))
procedure(stMaeRecord(port kind scope name result)
  if(result then
    fprintf(port "ST_MAE_RECORD\t%s\t%L\t%L\tOK\t%L\n" kind scope name car(result))
    car(result)
  else
    fprintf(port "ST_MAE_RECORD\t%s\t%L\t%L\tREAD_ERROR\tnil\n" kind scope name)
    nil
  )
)
procedure(stMaeVariables(port handle kind scope database globals)
  let((names name result variable)
    names=stMaeRecord(port strcat(kind "_list") scope "names" errset(cadr(axlGetVars(handle)) t))
    foreach(name names
      result=errset(axlGetVar(handle name) t)
      if(and(result car(result)) then
        variable=car(result)
        stMaeRecord(port kind scope name errset(axlGetVarValue(variable) t))
        ; A test variable's checkbox is stored on the global variable.
        ; axlGetEnabled(testVariable) always returns t for that case.
        if(equal(kind "test_variable") then
          when(member(name globals)
            stMaeRecord(port "test_variable_global_override_enabled" scope name
              errset(axlGetEnabledGlobalVarPerTest(database name scope) t)))
        else
          stMaeRecord(port strcat(kind "_enabled") scope name errset(axlGetEnabled(variable) t))
        )
      else
        stMaeRecord(port kind scope name nil)
      )
    )
    names
  )
)
procedure(stMaeRead(port)
  let((library cell view lib setup database tests testName test toolArgs designLibrary designCell designView
        testSession result corners cornerName corner models modelName model globals)
    library=getShellEnvVar("ST_MAE_LIBRARY")
    cell=getShellEnvVar("ST_MAE_CELL")
    view=getShellEnvVar("ST_MAE_VIEW")
    lib=ddGetObj(library)
    unless(and(lib ddGetObj(library cell view)) error("Requested registered Maestro view is unavailable"))
    stMaeRecord(port "meta" "setup" "library" list(library))
    stMaeRecord(port "meta" "setup" "cell" list(cell))
    stMaeRecord(port "meta" "setup" "view" list(view))
    stMaeRecord(port "meta" "setup" "registered_library_path" list(lib->readPath))
    setup=maeOpenSetup(library cell view ?mode "r")
    unless(setup error("Cannot open requested Maestro setup for reading"))
    database=axlGetMainSetupDB(setup)
    unless(database error("Cannot read Maestro setup database"))
    globals=stMaeVariables(port database "global_variable" "setup" database nil)
    tests=cadr(axlGetTests(database))
    unless(and(listp(tests) tests) error("Saved Maestro setup contains no readable tests"))
    foreach(testName tests
      unless(stringp(testName) error("Unproven Maestro test name representation"))
      test=axlGetTest(database testName)
      unless(test error("Cannot read saved Maestro test"))
      stMaeRecord(port "test" testName "test_name" list(testName))
      toolArgs=axlGetTestToolArgs(test)
      unless(listp(toolArgs) error("Cannot read actual test design arguments"))
      stMaeRecord(port "test" testName "tool_args" list(toolArgs))
      designLibrary=cadr(assoc("lib" toolArgs))
      designCell=cadr(assoc("cell" toolArgs))
      designView=cadr(assoc("view" toolArgs))
      unless(and(stringp(designLibrary) stringp(designCell) stringp(designView)
                 not(equal(designLibrary "")) not(equal(designCell "")) not(equal(designView "")))
        error("Saved test design Library/Cell/View cannot be proven"))
      stMaeRecord(port "test" testName "design_library" list(designLibrary))
      stMaeRecord(port "test" testName "design_cell" list(designCell))
      stMaeRecord(port "test" testName "design_view" list(designView))
      stMaeRecord(port "test" testName "enabled" errset(axlGetEnabled(test) t))
      stMaeRecord(port "test" testName "all_global_variables_disabled" errset(axlGetAllVarsDisabled(test) t))
      result=errset(maeGetTestSession(testName ?session setup) t)
      if(and(result car(result)) then
        testSession=car(result)
        stMaeRecord(port "test" testName "simulator" errset(asiGetSimName(testSession) t))
        stMaeRecord(port "test" testName "models" errset(asiGetModelLibSelectionList(testSession) t))
      else
        stMaeRecord(port "test" testName "test_session" nil)
      )
      stMaeVariables(port test "test_variable" testName database globals)
    )
    corners=stMaeRecord(port "meta" "setup" "corners" errset(cadr(axlGetCorners(database)) t))
    foreach(cornerName corners
      result=errset(axlGetCorner(database cornerName) t)
      if(and(result car(result)) then
        corner=car(result)
        stMaeRecord(port "corner" cornerName "enabled" errset(axlGetEnabled(corner) t))
        stMaeVariables(port corner "corner_variable" cornerName database globals)
        models=stMaeRecord(port "corner" cornerName "model_names" errset(cadr(axlGetModels(corner)) t))
        foreach(modelName models
          result=errset(axlGetModel(corner modelName) t)
          if(and(result car(result)) then
            model=car(result)
            stMaeRecord(port "corner_model_file" cornerName modelName errset(axlGetModelFile(model) t))
            stMaeRecord(port "corner_model_section" cornerName modelName errset(axlGetModelSection(model) t))
            stMaeRecord(port "corner_model_enabled" cornerName modelName errset(axlGetEnabled(model) t))
          else
            stMaeRecord(port "corner_model_file" cornerName modelName nil)
          )
        )
      else
        stMaeRecord(port "corner" cornerName "handle" nil)
      )
    )
    t
  )
)
let((result port)
  result=errset(
    prog( ()
      port=outfile(getShellEnvVar("ST_MAESTRO_REPORT"))
      unless(port error("Cannot create Maestro evidence report"))
      stMaeRead(port)
      fprintf(port "ST_MAESTRO_SETUP_READ_COMPLETE\n")
      close(port)
      port=nil
      t
    ) t)
  when(port close(port))
  unless(and(result car(result)) printf("ST_MAESTRO_SETUP_READ_FAILED\n"))
)
exit()
'''


def skill_value_complete(text):
    """Check one printed expression, without evaluating any SKILL from the report."""
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()"]+', text)
    if not tokens or ''.join(tokens) != re.sub(r'\s+', '', text):
        # Whitespace inside quoted strings is significant and must be retained.
        covered = re.sub(r'"(?:\\.|[^"\\])*"|[()]|[^\s()"]+', '', text)
        if not tokens or covered.strip(): return False
    depth, roots = 0, 0
    for token in tokens:
        if token == ')':
            depth -= 1
            if depth < 0: return False
        else:
            if depth == 0: roots += 1
            if token == '(': depth += 1
    return depth == 0 and roots == 1


def read_records(text):
    lines = text.splitlines()
    if not lines or lines[-1] != MARKER or lines.count(MARKER) != 1:
        raise ValueError('native report completion marker missing or ambiguous')
    records = []
    for line in lines[:-1]:
        if line.startswith(PREFIX):
            parts = line.split('\t', 5)
            if len(parts) != 6 or parts[4] not in ('OK', 'READ_ERROR'):
                raise ValueError('malformed Maestro report record')
            scope, name = json.loads(parts[2]), json.loads(parts[3])
            if not isinstance(scope, str) or not isinstance(name, str):
                raise ValueError('invalid Maestro record identity')
            records.append({'kind': parts[1], 'scope': scope, 'name': name,
                            'status': parts[4], 'raw_value': parts[5]})
        elif records:
            # Some %L list renderings span lines. Preserve them in full locally.
            records[-1]['raw_value'] += '\n' + line
        else:
            raise ValueError('unexpected text before Maestro report records')
    if any(not skill_value_complete(record['raw_value']) for record in records):
        raise ValueError('malformed or incomplete printed Maestro value')
    return records


def string_field(records, kind, scope, name):
    matches = [r for r in records if (r['kind'], r['scope'], r['name']) == (kind, scope, name)]
    if len(matches) != 1 or matches[0]['status'] != 'OK':
        raise ValueError('missing/ambiguous actual setup identity or test design')
    value = json.loads(matches[0]['raw_value'])
    if not isinstance(value, str) or not value:
        raise ValueError('empty/non-string actual setup identity or test design')
    return value


def verify_report(records, args):
    for name, expected in [('library', args.bench_lib), ('cell', args.bench_cell), ('view', args.setup_view)]:
        if string_field(records, 'meta', 'setup', name) != expected:
            raise ValueError('reported Maestro setup differs from requested setup')
    registered = Path(string_field(records, 'meta', 'setup', 'registered_library_path'))
    if not registered.is_absolute() or registered.resolve() != Path(args.expected_library_path).resolve():
        raise ValueError('registered library path differs from the supplied actual repository library')
    tests = [r['scope'] for r in records if r['kind'] == 'test' and r['name'] == 'test_name']
    if not tests or len(tests) != len(set(tests)):
        raise ValueError('no unique saved tests were read')
    for test in tests:
        if string_field(records, 'test', test, 'test_name') != test:
            raise ValueError('saved test identity differs')
        for name in ('design_library', 'design_cell', 'design_view'):
            string_field(records, 'test', test, name)
    return len(tests)


def compact(value, limit=450):
    value = ' '.join(value.split())
    return value if len(value) <= limit else value[:limit] + ' ... [DISPLAY_SHORTENED; full value on server]'


def summary(records, status, tests):
    errors = sum(r['status'] == 'READ_ERROR' for r in records)
    # Show design/model identities and Corner overrides before long variable lists.
    def priority(record):
        kind = record['kind']
        return 0 if kind == 'meta' else 1 if kind == 'test' else 2 if kind.startswith('corner') else 3 if kind.startswith('global') else 4
    ordered = sorted(records, key=priority)
    head = ['READER=maestro-setup-v1', 'RESULT=' + status, 'READ_ONLY=true',
            'TEST_COUNT=' + str(tests), 'READ_ERRORS=' + str(errors), 'SETTINGS_RECORDS=' + str(len(records))]
    tail = ['SIMULATION_PROFILE_READY=false', 'ELECTRICAL_VERIFIED=false', 'RAW_DETAILS_REMAIN_ON_SERVER=true']
    budget = MAX_LINES - len(head) - len(tail) - 3
    chosen = ordered[:budget]
    shortened = any(len(' '.join(r['raw_value'].split())) > 450 for r in chosen)
    body = [compact(r['kind'] + ' [' + r['scope'] + '] ' + r['name'], 220) +
            '=' + compact(r['raw_value']) + (' [READ_ERROR]' if r['status'] != 'OK' else '') for r in chosen]
    return head + body + ['SUMMARY_TRUNCATED=' + str(len(chosen) != len(ordered) or shortened).lower(),
        'SUMMARY_OMITTED_RECORDS=' + str(len(ordered) - len(chosen)),
        'MAESTRO_SETUP_READ_OK' if status == 'READ_OK' else 'MAESTRO_SETUP_READ_PARTIAL'] + tail


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('session', 'bench-lib', 'bench-cell', 'setup-view', 'expected-library-path', 'output'):
        parser.add_argument('--' + flag, required=True)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--timeout', type=int, default=300)
    args = parser.parse_args()
    output = None
    try:
        session = Path(args.session).resolve()
        requested_output = Path(args.output).expanduser()
        expected = Path(args.expected_library_path)
        if not requested_output.is_absolute() or not expected.is_absolute() or not expected.is_dir():
            raise ValueError('output must be new and absolute; expected library path must be an existing absolute directory')
        if requested_output.exists(): raise ValueError('evidence directory already exists; choose a new directory')
        if args.timeout <= 0: raise ValueError('timeout must be positive')
        for value in (args.bench_lib, args.bench_cell, args.setup_view):
            if not value or any(ch in value for ch in '/\t\r\n\0'):
                raise ValueError('invalid requested OA identity')
        from site_data import read_json, verify_site_inputs
        from standalone import environment
        manifest = session / 'analysis/standalone_inputs/provider_inputs.json'
        inputs = read_json(manifest); verify_site_inputs(inputs)
        config_path = session / 'session.conf'
        initial_config = config_path.read_bytes(); initial_manifest = manifest.read_bytes()
        config = dict(line.split('=', 1) for line in initial_config.decode().splitlines() if '=' in line and not line.startswith('#'))
        cds = Path(config['cds_lib'])
        if not cds.is_absolute() or not cds.is_file() or cds.name != 'cds.lib':
            raise ValueError('actual source session cds.lib is unavailable')
        initial_cds = cds.read_bytes()
        requested_output.mkdir(parents=True, exist_ok=False)
        output = requested_output
        action = output / 'read_maestro.il'; action.write_text(ACTION, encoding='utf-8')
        selection = {'session': str(session), 'cds_lib': str(cds), 'bench_library': args.bench_lib,
            'bench_cell': args.bench_cell, 'setup_view': args.setup_view,
            'expected_library_path': str(expected.resolve()), 'read_only': True,
            'session_config_sha256': hashlib.sha256(initial_config).hexdigest(),
            'cds_lib_sha256': hashlib.sha256(initial_cds).hexdigest()}
        (output / 'selection.json').write_text(json.dumps(selection, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        if args.prepare_only:
            print('SKILL_INPUT_PREPARED=true\nNATIVE_EXECUTION=false\nSIMULATION_PROFILE_READY=false')
            return 0
        executable = shutil.which(os.environ.get('ST_VIRTUOSO_BIN') or 'virtuoso')
        if not executable: raise ValueError('Virtuoso executable unavailable')
        env = environment(inputs, manifest); env.pop('ST_PREPARED_JSON_FILE', None)
        env.update({'ST_MAE_LIBRARY': args.bench_lib, 'ST_MAE_CELL': args.bench_cell,
            'ST_MAE_VIEW': args.setup_view, 'ST_MAESTRO_REPORT': str(output / 'maestro_report.tsv')})
        with (output / 'launcher.log').open('x', encoding='utf-8') as log:
            result = subprocess.run([executable, '-nograph', '-replay', str(action), '-log', str(output / 'virtuoso.log')],
                cwd=str(cds.parent), env=env, stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout)
        verify_site_inputs(inputs)
        if config_path.read_bytes() != initial_config or manifest.read_bytes() != initial_manifest or cds.read_bytes() != initial_cds:
            raise ValueError('source session inputs changed during reading')
        if result.returncode:
            (output / 'summary.txt').write_text('RESULT=INCOMPLETE\nNATIVE_EXIT_CODE=' + str(result.returncode) + '\n')
            print('RESULT=INCOMPLETE\nNATIVE_EXIT_CODE=' + str(result.returncode) + '\nRAW_DETAILS_REMAIN_ON_SERVER=true')
            return 70
        records = read_records((output / 'maestro_report.tsv').read_text(encoding='utf-8'))
        tests = verify_report(records, args)
        status = 'PARTIAL' if any(r['status'] == 'READ_ERROR' for r in records) else 'READ_OK'
        (output / 'maestro_read.json').write_text(json.dumps({'result': status, 'selection': selection,
            'records': records, 'simulation_profile_ready': False}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        rendered = '\n'.join(summary(records, status, tests)) + '\n'
        (output / 'summary.txt').write_text(rendered, encoding='utf-8')
        print(rendered, end='')
        return 0 if status == 'READ_OK' else 2
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        if output is not None:
            (output / 'status.json').write_text(json.dumps({'result': 'INCOMPLETE', 'reason': str(error)}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('RESULT=INCOMPLETE\nREASON=INPUT_OR_NATIVE_READ_FAILED\nRAW_DETAILS_REMAIN_ON_SERVER=true')
        return 70 if output is not None else 2


if __name__ == '__main__':
    sys.exit(main())
