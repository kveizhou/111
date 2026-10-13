#!/usr/bin/env python3
"""Read saved test solver settings into fresh server-local evidence.

Exports an OCEAN script as data; never loads that script or runs Spectre.
Reads the base test settings, keeping the selected Corner cache unchanged.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_cascode_batch as cb

SETTINGS = {'analysis', 'option', 'envOption', 'temp', 'ic', 'nodeset'}


def skip_literal(text, pos):
    """Skip a string or comment without interpreting its contents."""
    if text[pos] == ';':
        end = text.find('\n', pos)
        return len(text) if end < 0 else end + 1
    if text.startswith('/*', pos):
        end = text.find('*/', pos + 2)
        if end < 0:
            raise ValueError('unclosed saved script comment')
        return end + 2
    pos += 1
    while pos < len(text):
        if text[pos] == '\\':
            pos += 2
        elif text[pos] == '"':
            return pos + 1
        else:
            pos += 1
    raise ValueError('unclosed saved script string')


def extract_forms(text):
    """Return complete setting calls; skip comments/strings and never evaluate."""
    forms = []
    pos = 0
    while pos < len(text):
        if text[pos] in (';', '"') or text.startswith('/*', pos):
            pos = skip_literal(text, pos)
            continue
        match = re.match(r'[A-Za-z_][A-Za-z0-9_]*', text[pos:])
        if not match:
            pos += 1
            continue
        start = pos
        pos += len(match.group())
        if match.group() not in SETTINGS:
            continue
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos == len(text) or text[pos] != '(':
            continue
        depth = 0
        while pos < len(text):
            if text[pos] in (';', '"') or text.startswith('/*', pos):
                pos = skip_literal(text, pos)
                continue
            if text[pos] == '(':
                depth += 1
            elif text[pos] == ')':
                depth -= 1
                if depth == 0:
                    pos += 1
                    forms.append(text[start:pos])
                    break
            pos += 1
        else:
            raise ValueError('unclosed saved setting')
    return forms


def native_action(bound):
    selection = bound['data']['selection']
    identity = ' '.join(json.dumps(selection[k]) for k in ('bench_library', 'bench_cell', 'setup_view'))
    test = json.dumps(bound['settings']['test_name'])
    return '''load(getShellEnvVar("ST_SKILL_INIT"))
let((stReviewSetup stReviewTest stReviewResult stReviewOceanPort stReviewDonePort)
  stReviewResult=errset(prog( ()
    stReviewSetup=maeOpenSetup(%s ?mode "r")
    unless(stReviewSetup error("Cannot open saved setup read-only"))
    stReviewTest=maeGetTestSession(%s ?session stReviewSetup)
    unless(stReviewTest error("Cannot read saved test"))
    stReviewOceanPort=asiOpenOceanScript(getShellEnvVar("ST_REVIEW_OCEAN"))
    unless(stReviewOceanPort error("Cannot open OCEAN export port"))
    unless(asiWriteOceanScript(stReviewOceanPort stReviewTest ?noRun t ?fullKey t)
      error("Cannot export saved test settings"))
    asiCloseOceanScript(stReviewOceanPort)
    stReviewOceanPort=nil
    stReviewDonePort=outfile(getShellEnvVar("ST_REVIEW_DONE"))
    unless(stReviewDonePort error("Cannot write completion marker"))
    fprintf(stReviewDonePort "OK\\n")
    close(stReviewDonePort)
    stReviewDonePort=nil
    t
  ) t)
  when(stReviewOceanPort errset(asiCloseOceanScript(stReviewOceanPort) t))
  when(stReviewDonePort close(stReviewDonePort))
  unless(and(stReviewResult car(stReviewResult)) printf("ST_REVIEW_FAILED\\n"))
)
exit()
''' % (identity, test)


def render(body, count, error, diagnostics=()):
    head = ['CHECKER=cascode-dc-evidence-v2', 'RESULT=' + ('READ_OK' if error is None else 'INCOMPLETE'),
            'SPECTRE_RERUN=false', 'READ_SCOPE=saved_base_test_settings']
    if error is not None:
        head += ['SAVED_TEST_READ_INCOMPLETE=' + ' '.join(str(error).split())[:500]]
        head += ['NATIVE_ERROR ' + item for item in diagnostics]
    footer = ['SAVED_FORM_COUNT=' + str(count)]
    if error is None:
        footer += ['SAVED_TEST_SCRIPT_READ_OK', 'SAVED_SETTINGS_CAPTURED_NOT_APPLIED=true',
                   'FIXED_INPUTS_UNCHANGED=true']
    footer += ['ELECTRICAL_VERIFIED=false', 'VBIAS_GENERATED=false', 'RAW_DETAILS_REMAIN_ON_SERVER=true']
    budget = max(0, 190 - 2 - len(head) - len(footer) - 1)
    chosen = body[:budget]
    return head + chosen + ['SUMMARY_OMITTED_LINES=' + str(len(body) - len(chosen))] + footer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('session', 'maestro-read', 'preflight', 'batch'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--timeout', type=int, default=180)
    args = parser.parse_args()
    output = None
    body = []
    count = 0
    error = None
    diagnostics = []
    print('READ_SAVED_SETTINGS=START', flush=True)
    try:
        batch = Path(args.batch)
        if args.timeout <= 0 or not batch.is_absolute() or not (batch / 'status.json').is_file():
            raise ValueError('batch directory must exist and be absolute; timeout must be positive')
        bound = cb.inputs(args)
        output = Path(tempfile.mkdtemp(prefix='dc_review_ports_', dir=str(batch)))
        body.append('SELECTED_CORNER=' + bound['settings']['corner'])
        (output / 'read.il').write_text(native_action(bound))
        (output / 'cds.lib').write_text('INCLUDE ' + json.dumps(str(bound['cds'])) + '\n')
        saved = output / 'saved_test.ocn'
        done = output / 'done'
        env = dict(bound['env'], ST_REVIEW_OCEAN=str(saved), ST_REVIEW_DONE=str(done))
        cb.command([cb.executable(env, 'ST_VIRTUOSO_BIN', 'virtuoso'), '-nograph', '-replay',
                    str(output / 'read.il'), '-log', str(output / 'virtuoso.log')],
                   output, env, args.timeout, output / 'launcher.log')
        if not saved.is_file() or not saved.stat().st_size or not done.is_file():
            raise ValueError('saved test export is incomplete')
        if done.read_text().strip() != 'OK':
            raise ValueError('saved test completion marker is invalid')
        forms = extract_forms(saved.read_text())
        if not forms:
            raise ValueError('no saved analysis/options found in export')
        cb.unchanged(bound)
        (output / 'settings_forms.json').write_text(json.dumps(forms, ensure_ascii=False, indent=2) + '\n')
        for block in forms:
            flat = ' '.join(block.split())
            for offset in range(0, len(flat), 1000):
                prefix = 'SAVED_TEST ' if offset == 0 else 'SAVED_TEST_CONT '
                body.append(prefix + flat[offset:offset + 1000])
        body.append('JOB_POLICY_ERROR_PRESENT=' + str(any(
            'ASSEMBLER-1944' in item for item in cb.brief_errors(output))).lower())
        count = len(forms)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as caught:
        error = caught
        if output is not None:
            diagnostics = cb.brief_errors(output)
    print('READ_SAVED_SETTINGS=' + ('COMPLETE' if error is None else 'INCOMPLETE'), flush=True)
    summary = render(body, count, error, diagnostics)
    if output is not None:
        (output / 'summary.txt').write_text('\n'.join(summary) + '\n')
    print('\n'.join(summary))
    return 0 if error is None else 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('RESULT=INTERRUPTED\nELECTRICAL_VERIFIED=false\nVBIAS_GENERATED=false')
        sys.exit(130)
