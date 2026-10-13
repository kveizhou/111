#!/usr/bin/env python3
"""Read saved test settings; --run-dc additionally measures the original baseline.

The exported script is data. Only validated literal DC/settings calls may be
applied to an isolated OCEAN session, with the selected Corner taking precedence.
"""
import argparse
import json
import math
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


def native_action(bound, definitions=False):
    selection = bound['data']['selection']
    identity = ' '.join(json.dumps(selection[k]) for k in ('bench_library', 'bench_cell', 'setup_view'))
    test = json.dumps(bound['settings']['test_name'])
    script = '''load(getShellEnvVar("ST_SKILL_INIT"))
let((stReviewSetup stReviewTest stReviewResult stReviewOceanPort stReviewDonePort stReviewDefinitionPort)
  stReviewResult=errset(prog( ()
    stReviewSetup=maeOpenSetup(%s ?mode "r")
    unless(stReviewSetup error("Cannot open saved setup read-only"))
    stReviewTest=maeGetTestSession(%s ?session stReviewSetup)
    unless(stReviewTest error("Cannot read saved test"))
    __DEFINITIONS__
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
  when(stReviewDefinitionPort close(stReviewDefinitionPort))
  when(stReviewDonePort close(stReviewDonePort))
  unless(and(stReviewResult car(stReviewResult)) printf("ST_REVIEW_FAILED\\n"))
)
exit()
''' % (identity, test)
    extra = '''stReviewDefinitionPort=outfile(getShellEnvVar("ST_REVIEW_DEFINITIONS"))
    unless(stReviewDefinitionPort error("Cannot create Definition Files evidence"))
    fprintf(stReviewDefinitionPort "%L\\n" asiGetEnvOptionVal(stReviewTest "definitionFiles"))
    close(stReviewDefinitionPort)
    stReviewDefinitionPort=nil''' if definitions else ''
    return script.replace('__DEFINITIONS__', extra)


def literal_call(form):
    """Parse only literal OCEAN settings, never an arbitrary saved expression."""
    chunks=[]; pos=0
    while pos<len(form):
        if form[pos] in (';', '"') or form.startswith('/*',pos):
            end=skip_literal(form,pos)
            chunks.append(form[pos:end] if form[pos]=='"' else ' '*(end-pos)); pos=end
        else: chunks.append(form[pos]); pos+=1
    clean=''.join(chunks)
    pattern = r'"(?:\\.|[^"\\])*"|\?[A-Za-z_]\w*|\x27[A-Za-z_]\w*|[A-Za-z_]\w*|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|[()]'
    matches = list(re.finditer(pattern, clean)); end = 0
    def syntax_error(start, stop):
        offset=start+re.search(r'\S',clean[start:stop]).start()
        context=json.dumps(form[max(0,offset-35):offset+45],ensure_ascii=True)
        return ValueError('unsupported saved setting syntax offset='+str(offset)+
            ' codepoint=U+%04X'%ord(clean[offset])+' context='+context)
    for match in matches:
        if clean[end:match.start()].strip(): raise syntax_error(end,match.start())
        end = match.end()
    if clean[end:].strip(): raise syntax_error(end,len(clean))
    tokens = [m.group() for m in matches]; pos = 0
    def value(depth=0):
        nonlocal pos
        if depth > 30 or pos >= len(tokens): raise ValueError('incomplete or nested saved setting')
        token = tokens[pos]; pos += 1
        if token in ('(', 'list'):
            if token == 'list':
                if pos >= len(tokens) or tokens[pos] != '(': raise ValueError('invalid literal list')
                pos += 1
            items=[]
            while pos < len(tokens) and tokens[pos] != ')': items.append(value(depth+1))
            if pos == len(tokens): raise ValueError('unclosed literal list')
            pos += 1
            return items
        if token.startswith('"'):
            json.loads(token)
            return token
        if token[0] in "?'" or token in ('nil','t') or re.fullmatch(r'[-+0-9.eE]+',token): return token
        raise ValueError('nonliteral saved setting: '+token)
    if len(tokens)<3 or tokens[1]!='(': raise ValueError('invalid setting call')
    name=tokens[0]; pos=2; args=[]
    while pos<len(tokens) and tokens[pos]!=')': args.append(value())
    if pos!=len(tokens)-1: raise ValueError('unclosed or trailing saved call')
    return name,args


def dc_settings(forms, diagnostics=None):
    selected=[]; dc=[]; details=[]; failed=0
    if diagnostics is None: diagnostics=[]
    allowed={'anaName','saveOppoint','write','oppoint','maxiters','maxsteps','annotate','threshold','detail','sort'}
    for index,form in enumerate(forms,1):
        # A skipped analysis is never copied to OCEAN: its parameter language
        # (e.g. a quoted transient table) must not constrain a DC-only probe.
        kind=re.match(r"^\s*analysis\s*\(\s*'([A-Za-z_]\w*)(?=\s|\))",form)
        if kind and kind[1]!='dc':
            diagnostics.append('SKIPPED_NON_DC index='+str(index)+' analysis='+kind[1])
            continue
        label=re.match(r'^\s*([A-Za-z_]\w*)',form)
        name=label[1] if label else 'unknown'
        try:
            name,args=literal_call(form)
            if name=='analysis':
                if not args or args[0]!="'dc": raise ValueError('unrecognized literal analysis type')
                if len(args)%2!=1: raise ValueError('malformed DC settings')
                for key,val in zip(args[1::2],args[2::2]):
                    if not isinstance(key,str) or not key.startswith('?') or key[1:] not in allowed:
                        raise ValueError('DC sweep or unsupported setting: '+str(key))
                    if key in ('?maxiters','?maxsteps'):
                        raw=json.loads(val) if isinstance(val,str) and val.startswith('"') else val
                        if not isinstance(raw,str) or not raw.isdigit() or int(raw)<=0: raise ValueError('invalid DC iteration setting')
                        details.append(key[1:]+'='+raw)
                    if key=='?write' and val not in ('nil','"spectre.dc"'):
                        raise ValueError('saved DC write path requires explicit isolated mapping')
                dc.append(form); selected.append(form)
            elif name in ('option','envOption'):
                if len(args)%2: raise ValueError('malformed saved option pairs')
                issues=[]; seen={}
                for key,val in zip(args[::2],args[1::2]):
                    if not isinstance(key,str) or not key.startswith(("'",'?')): raise ValueError('invalid option key')
                    key=key.lstrip("?'")
                    if key in seen: issues.append('duplicate saved option key='+key+' values='+str(seen[key])+','+str(val))
                    seen[key]=val
                    if key.lower() in ('usercmdlineoption','drmscmd','recover','checkpoint','restart','savestate','readic','readns') and val not in ('nil','""'):
                        issues.append('saved external command/state key='+key+' value='+str(val)+' requires explicit support')
                if issues: raise ValueError('; '.join(issues))
                selected.append(form)
            elif name in ('ic','nodeset'):
                selected.append(form)
            elif name!='temp': raise ValueError('unsupported setting: '+name)
        except ValueError as error:
            failed+=1
            diagnostics.append('FAILED_SAVED_FORM index='+str(index)+' name='+name+' issue='+
                ' '.join(str(error).split())[:700])
    if len(dc)!=1:
        failed+=1; diagnostics.append('FAILED_SAVED_DC_COUNT count='+str(len(dc))+' expected=1')
    if failed: raise ValueError('saved settings validation failed; issue_groups='+str(failed))
    return selected,details


def circuit_shape(text, origin, definitions=()):
    """Compare physical contents, excluding only analysis/save/options controls."""
    from op_provider import parse_deck, resolve_includes
    deck=parse_deck(resolve_includes(text,origin))
    def instances(items):
        return sorted((i['name'],i['master'],i['nodes'],' '.join(i['tail'].split())) for i in items)
    groups={k:(v['ports'],v['parameters'],instances(v['instances'])) for k,v in deck['definitions'].items()}
    control=re.compile(r'^\S+\s+(?:options|info|dc|tran|stb|ac|noise|pz|xf)\b')
    rest=[]; owned={i['line'] for i in deck['top']}
    for v in deck['definitions'].values(): owned.update(i['line'] for i in v['instances'])
    for n,line in enumerate(deck['lines']):
        s=line.strip()
        if n in owned or not s or s.startswith('//'): continue
        if re.match(r'^(?:subckt|ends|parameters|global|simulator|save)\b',s) or control.match(s): continue
        if s in ['include '+json.dumps(p) for p in definitions]: continue
        rest.append(' '.join(s.split()))
    return dict(globals=sorted(deck['globals']),parameters=deck['parameters'],top=instances(deck['top']),groups=groups,other=rest)


def saved_values(selected):
    dc={}; options={}; turbo={}
    for form in selected:
        name,args=literal_call(form)
        if name=='analysis': pairs=zip(args[1::2],args[2::2]); target=dc
        elif name=='option':
            pairs=zip(args[::2],args[1::2]); target=turbo if '?categ' in args else options
        else: continue
        for key,val in pairs:
            if isinstance(val,str): target[key.lstrip("?'")]=json.loads(val) if val.startswith('"') else val
    return dc,options,turbo


def effective_controls(text, selected, temperature):
    """Prove the exported DC controls, not just the requested OCEAN calls."""
    from op_provider import lines, ASSIGN
    dc,requested,_=saved_values(selected); actual={}; analyses=[]; evidence=[]
    for line in lines(text):
        match=re.match(r'^\s*\S+\s+(options|dc|tran|stb|ac|noise|pz|xf)\b(.*)',line)
        if not match: continue
        kind,tail=match.groups(); values=dict(ASSIGN.findall(tail))
        if kind=='options': actual.update(values)
        else: analyses.append((kind,values)); evidence.append('EFFECTIVE_ANALYSIS '+line.strip()[:1000])
    if len(analyses)!=1 or analyses[0][0]!='dc': raise ValueError('export must contain exactly one DC analysis and no other analyses')
    for key in ('maxiters','maxsteps'):
        if key in dc and analyses[0][1].get(key)!=str(dc[key]): raise ValueError('exported DC setting not applied: '+key)
    # These scalar solver options map directly into Spectre simulatorOptions.
    required={k:v for k,v in requested.items() if k in ('reltol','vabstol','iabstol','tnom','gmin','rforce','pivrel','scale','scalem')}
    required['temp']=temperature
    for key,val in required.items():
        if key not in actual or not math.isclose(float(actual[key]),float(val),rel_tol=1e-12,abs_tol=0):
            raise ValueError('exported solver option not applied: '+key+' expected='+str(val)+' actual='+str(actual.get(key)))
    evidence.append('EFFECTIVE_OPTIONS '+' '.join(k+'='+actual[k] for k in required))
    return evidence


def check_launch(selected, logs):
    _,_,turbo=saved_values(selected)
    if turbo.get('uniMode')!='APS': raise ValueError('only saved APS launch is supported by this baseline probe')
    if not re.search(r'\+\+?aps(?:\b|=)',logs): raise ValueError('APS launch evidence missing')
    if turbo.get('errorLevel'):
        level=str(turbo['errorLevel']).lower()
        if not re.search(r'\+\+?aps='+re.escape(level)+r'\b',logs,re.I):
            raise ValueError('APS accuracy launch evidence missing: '+level)
    if turbo.get('mtOption')=='Manual' and not re.search(r'\+mt='+re.escape(str(turbo.get('numThreads')))+r'\b',logs):
        raise ValueError('manual thread-count launch evidence missing')


def baseline_script(bound, output, selected, definitions, run=False):
    settings=bound['settings']; q=json.dumps
    script='load('+q(str(bound['pinned']['init']))+')\n'
    script+='envSetVal("asimenv.startup" "projectDir" \'string '+q(str(output/'baseline_generated'))+')\n'
    script+='simulator(\'spectre)\ndesign('+ ' '.join(q(settings['design'][k]) for k in ('lib','cell','view')) +')\n'
    script+='\n'.join(selected)+'\n'
    script+='modelFile('+ ' '.join("'("+q(m['model_file'])+' '+q(m['section_name'])+')' for m in settings['models'])+')\n'
    if definitions: script+='definitionFile('+ ' '.join(q(p) for p in definitions)+')\n'
    for key,val in settings['variables'].items(): script+='desVar('+q(key)+' '+q(val)+')\n'
    script+='envOption(\'analysisOrder list("dc"))\ntemp('+str(settings['temperature'])+')\n'
    script+="hostMode('local)\nresultsDir("+q(str(output/'baseline_results'))+")\n"
    script+="saveOption('save \"all\")\nsaveOption('currents \"all\")\nsaveOption('subcktprobelvl \"99\")\n"
    script+='createNetlist(?display nil)\n'
    if run: script+='run()\n'
    return script


def ocean_stage(bound, output, selected, definitions, stage, timeout):
    work=output/('baseline_'+stage); work.mkdir(); marker=work/'runtime.done'
    script=baseline_script(bound,output,selected,definitions,stage=='run')
    action=work/'runtime.ocn'
    action.write_text('procedure(stSavedDcAction()\n'+script+'\nt)\nresult=errset(stSavedDcAction() t)\n'
        'when(and(result car(result)) p=outfile('+json.dumps(str(marker))+') fprintf(p "OK\\n") close(p))\nexit()\n')
    (work/'cds.lib').write_text('INCLUDE '+json.dumps(str(bound['cds']))+'\n')
    env=dict(bound['env'],ST_BASELINE_STAGE=stage,ST_BASELINE_ROOT=str(output),
        ST_BASELINE_GENERATED=str(output/'baseline_generated'),ST_BASELINE_RESULTS=str(output/'baseline_results'),ST_BASELINE_MARKER=str(marker))
    cb.command([cb.executable(env,'ST_OCEAN_BIN','ocean'),'-nograph','-restore',str(action)],work,env,timeout,work/'ocean.log')
    if not marker.is_file() or marker.read_text().strip()!='OK': raise ValueError(stage+' completion marker missing')
    exports=list((output/'baseline_generated').rglob('input.scs'))
    if len(exports)!=1: raise ValueError('baseline config export missing or ambiguous')
    path=exports[0]; text=path.read_text()
    if circuit_shape(text,path.parent,definitions)!=circuit_shape(bound['text'],bound['origin'],definitions):
        raise ValueError('baseline physical circuit/model/variables differ from confirmed config export')
    controls=effective_controls(text,selected,bound['settings']['temperature'])
    (output/('baseline_'+stage+'.scs')).write_text(text)
    cb.unchanged(bound)
    return controls


def baseline_op(bound, output, psf):
    from preflight_cascode_bench import analyze
    from op_provider import parse_deck
    declared=parse_deck(bound['text'])['parameters']; settings=dict(bound['settings'])
    settings['variables']={k:v for k,v in settings['variables'].items() if k in declared}
    _,ctx=analyze(bound['text'],bound['cfg']['source_cell'],settings)
    work=output/'baseline_op'; work.mkdir(); table=work/'values.tsv'
    paths=[cb.canonical(ctx['core_path']+'.'+name) for name in cb.TARGETS]
    script=cb.psf_action(str(psf),paths,bound['pinned']['init'],table)
    script=script.replace("selectResult('dcOp)","cond((member('dcOp results()) selectResult('dcOp)) (member('dc results()) selectResult('dc)) (t error(\"No single DC result\")))")
    action=work/'runtime.ocn'; action.write_text(script)
    (work/'cds.lib').write_text('INCLUDE '+json.dumps(str(bound['cds']))+'\n')
    env=dict(bound['env'],ST_BATCH_PSF_TABLE=str(table))
    cb.command([cb.executable(env,'ST_OCEAN_BIN','ocean'),'-nograph','-restore',str(action)],work,env,180,work/'ocean.log')
    if not (work/'runtime.done').is_file() or (work/'runtime.done').read_text().strip()!='OK': raise ValueError('OP completion marker missing')
    rows=cb.table(table); result=[]
    for name,prefix in zip(cb.TARGETS,paths):
        by_device={}
        for row in rows:
            if row['kind']!='op' or row['status']!='OK': continue
            path=cb.canonical(row['signal'])
            if path!=prefix and not path.startswith(prefix+'.'): continue
            val=float(row['value'])
            if not math.isfinite(val): raise ValueError('nonfinite target OP')
            values=by_device.setdefault(path,{})
            if row['parameter'] in values and values[row['parameter']]!=val: raise ValueError('conflicting target OP')
            values[row['parameter']]=val
        complete=[(p,v) for p,v in by_device.items() if {'vgs','vds','vdsat'}.issubset(v) and {'id','ids'}.intersection(v)]
        if not complete: raise ValueError('required signed OP missing for '+name)
        for path,values in complete: result.append('OP_TARGET '+name+' signal='+path+' '+' '.join(k+'='+str(v) for k,v in sorted(values.items())))
    cb.save(output/'baseline_op.json',rows)
    return result


def run_baseline(bound, output, forms, timeout):
    body=['SELECTED_CORNER='+bound['settings']['corner'],'TEMPERATURE='+str(bound['settings']['temperature']),
        'SAVED_FORM_COUNT='+str(len(forms)), 'OUTPUT_DIR='+str(output),
        'JOB_POLICY_ERROR_PRESENT='+str(any('ASSEMBLER-1944' in v for v in cb.brief_errors(output))).lower()]
    converged=False; launched=False; error=None
    try:
        diagnostics=[]
        try: selected,details=dc_settings(forms,diagnostics)
        finally: body+=diagnostics
        body+=['SAVED_DC '+s for s in details]
        definitions=cb.literal_files((output/'definition_files.txt').read_text())
        bound['fixed'].update({p:cb.digest(p) for p in definitions})
        body+=['DEFINITION_FILES_COUNT='+str(len(definitions)), 'NON_DC_ANALYSES_SKIPPED=true']
        cb.unchanged(bound)
        print('BASELINE_NETLIST=START',flush=True)
        body+=ocean_stage(bound,output,selected,definitions,'netlist',180)
        print('BASELINE_NETLIST=COMPLETE',flush=True)
        print('BASELINE_RUN=START',flush=True); launched=True
        ocean_stage(bound,output,selected,definitions,'run',timeout)
        bad=[]; commands=[]
        for path in output.rglob('*'):
            if path.suffix not in ('.log','.out') or not path.is_file() or 'baseline' not in str(path.relative_to(output)): continue
            text=path.read_text(errors='replace')
            for line in text.splitlines():
                if re.search(r'ERROR\s*\(|\*Error\*|FATAL|terminated prematurely',line): bad.append(line[:500])
                if 'Command line:' in line or re.search(r'\+\+?aps\b|\+mt=',line): commands.append('LAUNCH_EVIDENCE '+line.strip()[:1000])
        body+=commands[:8]
        if bad: raise ValueError('; '.join(bad[:4]))
        check_launch(selected,'\n'.join(commands))
        info=list((output/'baseline_results').rglob('dcOpInfo.info'))
        if len(info)!=1 or not info[0].stat().st_size: raise ValueError('nonempty DC operating point PSF missing')
        psf=info[0].parent
        if not any((psf/n).is_file() and (psf/n).stat().st_size for n in ('dcOp.dc','dc.dc')): raise ValueError('nonempty DC result missing')
        converged=True; print('BASELINE_RUN=COMPLETE',flush=True)
        print('BASELINE_OP=START',flush=True); body+=baseline_op(bound,output,psf)
        cb.unchanged(bound); print('BASELINE_OP=COMPLETE',flush=True)
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as caught:
        error=' '.join(str(caught).split())[:1000]
        body+=['ISSUE '+error]+['NATIVE_ERROR '+v for v in cb.brief_errors(output)[:8]]
        logs=[p for p in output.rglob('*') if p.is_file() and p.suffix in ('.log','.out') and 'baseline' in str(p.relative_to(output))]
        for path in sorted(logs)[:3]:
            body.append('LOG_TAIL '+str(path.relative_to(output)))
            body+=['LOG '+line[:700] for line in path.read_text(errors='replace').splitlines()[-12:]]
    summary=['CHECKER=cascode-saved-dc-v2','RESULT='+('BASELINE_READ_OK' if error is None else 'INCOMPLETE'),
        'BASELINE_RUN_REQUESTED='+str(launched).lower(),'BASELINE_DC='+('CONVERGED' if converged else 'NOT_COMPLETED')]
    summary+=body[:155]+['SUMMARY_OMITTED_LINES='+str(max(0,len(body)-155)),
        'SAVED_SETTINGS_APPLIED_TO_BASELINE='+str(error is None).lower(),
        'SIMULATION_PROFILE_READY=false','PDK_ELECTRICAL_RULES_READY=false','ELECTRICAL_VERIFIED=false',
        'VBIAS_GENERATED=false','RAW_DETAILS_REMAIN_ON_SERVER=true']
    cb.save(output/'baseline_status.json',dict(error=error,converged=converged,op_complete=error is None,electrical_verified=False))
    (output/'baseline_summary.txt').write_text('\n'.join(summary)+'\n')
    print('\n'.join(summary))
    return 0 if error is None else 2


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
    parser.add_argument('--run-dc', action='store_true', help='apply saved DC settings and measure original circuit only')
    parser.add_argument('--dc-timeout', type=int, default=600)
    args = parser.parse_args()
    output = None
    body = []
    count = 0
    error = None
    diagnostics = []
    print('READ_SAVED_SETTINGS=START', flush=True)
    try:
        batch = Path(args.batch)
        if min(args.timeout,args.dc_timeout) <= 0 or not batch.is_absolute() or not (batch / 'status.json').is_file():
            raise ValueError('batch directory must exist and be absolute; timeout must be positive')
        bound = cb.inputs(args)
        output = Path(tempfile.mkdtemp(prefix='dc_review_ports_', dir=str(batch)))
        body.append('SELECTED_CORNER=' + bound['settings']['corner'])
        (output / 'read.il').write_text(native_action(bound,args.run_dc))
        (output / 'cds.lib').write_text('INCLUDE ' + json.dumps(str(bound['cds'])) + '\n')
        saved = output / 'saved_test.ocn'
        done = output / 'done'
        env = dict(bound['env'], ST_REVIEW_OCEAN=str(saved), ST_REVIEW_DONE=str(done))
        if args.run_dc: env['ST_REVIEW_DEFINITIONS']=str(output/'definition_files.txt')
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
    if error is None and args.run_dc:
        return run_baseline(bound,output,forms,args.dc_timeout)
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
