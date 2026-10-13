#!/usr/bin/env python3
"""Read saved test settings; --run-dc additionally measures the original baseline.

The exported script is data. Only validated literal DC/settings calls may be
applied to an isolated OCEAN session, with the selected Corner taking precedence.
--read-node-context reuses the successful OP cache and reads absolute port voltages.
"""
import argparse
import hashlib
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


def focused_op_script(psf, paths, init, table):
    """Read only target device OP; node/waveform inventory is not needed here."""
    return 'load('+json.dumps(str(init))+')\nstFocusTargets=list('+ ' '.join(json.dumps(p) for p in paths)+')\n'+r'''
procedure(stFocusName(value)
  let((result)
    result=""
    foreach(part parseString(value "./\\")
      result=strcat(result if(equal(result "") then "" else ".") part))
    result
  )
)
procedure(stFocusTargetP(value)
  let((name found)
    name=stFocusName(value)
    foreach(prefix stFocusTargets
      when(or(equal(name prefix) and(strlen(name)>strlen(prefix)
        equal(substring(name 1 strlen(prefix)) prefix)
        equal(substring(name strlen(prefix)+1 1) "."))) found=t))
    found
  )
)
procedure(stFocusScalar(value)
  cond((numberp(value) value)
       (drIsWaveform(value)
         let((vec result)
           vec=drGetWaveformYVec(value)
           when(equal(drVectorLength(vec) 1) result=drGetElem(vec 0))
           if(numberp(result) then result else nil)))
       (t nil))
)
procedure(stFocusRead()
  let((port result decoded scalar params devices hits total)
    printf("ST_OP_STAGE=OPEN_RESULTS\n")
    unless(openResults(__PSF__) error("Cannot open saved PSF"))
    printf("ST_OP_RESULTS=%L\n" results())
    unless(selectResult('dcOpInfo) error("dcOpInfo result unavailable"))
    port=outfile(__TABLE__)
    unless(port error("Cannot create focused OP table"))
    fprintf(port "kind\tsignal\tparameter\tvalue\tstatus\n")
    total=0
    foreach(kind dataTypes()
      params=outputParams(kind)
      devices=outputs(?type kind ?map nil)
      hits=0
      foreach(device devices
        when(stFocusTargetP(device)
          hits=hits+1 total=total+1
          printf("ST_OP_TARGET device=%s type=%s\n" device kind)
          fprintf(port "device\t%s\t\t%s\tMETA\n" device kind)
          foreach(param params
              result=errset(pv(device param ?result 'dcOpInfo) nil)
              scalar=nil
              when(result
                decoded=errset(stFocusScalar(car(result)) nil)
                when(decoded scalar=car(decoded)))
              if(numberp(scalar) then
                fprintf(port "op\t%s\t%s\t%.17g\tOK\n" device param float(scalar))
              else
                fprintf(port "op\t%s\t%s\t\t%s\n" device param if(result then "NON_NUMERIC" else "READ_ERROR"))
                printf("ST_OP_VALUE device=%s param=%s status=%s type=%L\n"
                  device param if(result then "NON_NUMERIC" else "READ_ERROR") if(result then type(car(result)) else nil))
              )
          )
        )
      )
      printf("ST_OP_TYPE type=%s outputs=%d matched=%d\n" kind length(devices) hits))
    close(port)
    printf("ST_OP_STAGE=TARGETS_COMPLETE matched=%d\n" total)
    t
  )
)
result=errset(stFocusRead() t)
when(and(result car(result))
  port=outfile(__MARKER__) fprintf(port "OK\n") close(port))
exit()
'''.replace('__PSF__',json.dumps(str(psf))).replace('__TABLE__',json.dumps(str(table))).replace(
        '__MARKER__',json.dumps(str(table.parent/'runtime.done')))


def summarize_op(rows, paths):
    """Keep native names and per-device evidence; only map the known saturation alias."""
    records={}
    for row in rows:
        if set(row)!={'kind','signal','parameter','value','status'}:
            raise ValueError('invalid focused OP row schema')
        if row['kind']=='device':
            if row['status']!='META' or row['parameter'] or not row['value']:
                raise ValueError('invalid focused OP device metadata')
        elif row['kind']!='op' or row['status'] not in ('OK','NON_NUMERIC','READ_ERROR') or not row['parameter']:
            raise ValueError('invalid focused OP row')
        signal=cb.canonical(row['signal'])
        if not any(signal==p or signal.startswith(p+'.') for p in paths): continue
        record=records.setdefault(signal,dict(signal=signal,device_type='UNKNOWN',raw={},conflicts=[]))
        if row['kind']=='device':
            if record['device_type'] not in ('UNKNOWN',row['value']): record['conflicts'].append('device_type')
            record['device_type']=row['value']
        else:
            parameter=row['parameter']; item=dict(value=row['value'],status=row['status'])
            if parameter in record['raw'] and record['raw'][parameter]!=item:
                previous=record['raw'][parameter]; same_number=False
                if previous['status']==item['status']=='OK':
                    try:
                        a,b=float(previous['value']),float(item['value'])
                        same_number=math.isfinite(a) and math.isfinite(b) and a==b
                    except (TypeError,ValueError): pass
                if not same_number: record['conflicts'].append(parameter)
            else: record['raw'][parameter]=item
    targets=[]; values_lines=[]; details=[]; inventories=[]
    shown={'id','ids','vgs','vds','vbs','ves','vth','vdsat','vdssat','gm','gds','region',
           'vdst','vgst','vest','vgdt','vget','vdet','vgt'}
    for name,prefix in zip(cb.TARGETS,paths):
        devices=[]
        for signal,record in sorted(records.items()):
            if signal!=prefix and not signal.startswith(prefix+'.'): continue
            raw=record['raw']; numeric={}; invalid=[]
            for parameter,item in raw.items():
                if item['status']!='OK': continue
                try: value=float(item['value'])
                except (TypeError,ValueError): invalid.append(parameter); continue
                if not math.isfinite(value): invalid.append(parameter); continue
                numeric[parameter]=value
            normalized=dict(numeric); sources={k:k for k in numeric}; conflicts=list(record['conflicts'])
            # Reference: Maau IsVdsatSignal; BSIM-CMG uses vdssat. Never substitute vdst or vgs-vth.
            if 'vdsat' not in normalized and 'vdssat' in numeric:
                normalized['vdsat']=numeric['vdssat']; sources['vdsat']='vdssat'
            elif 'vdsat' in numeric and 'vdssat' in numeric and numeric['vdsat']!=numeric['vdssat']:
                conflicts.append('vdsat/vdssat')
            missing=sorted({'vgs','vds','vdsat'}-normalized.keys())
            if not {'id','ids'}.intersection(normalized): missing.append('id|ids')
            device=dict(record,normalized=normalized,sources=sources,invalid=invalid,missing=missing,
                        conflicts=sorted(set(conflicts)),complete=not missing and not conflicts)
            devices.append(device)
            values_lines.append('OP_TARGET '+name+' signal='+signal+' type='+record['device_type']+' '+
                                ' '.join(k+'='+str(v) for k,v in sorted(normalized.items()) if k in shown))
            details.append('OP_FIELD_SOURCES '+name+' signal='+signal+' '+
                           ' '.join(k+'='+sources[k] for k in ('id','ids','vgs','vds','vdsat') if k in sources))
            details.append('OP_PARAMETER_COUNTS '+name+' signal='+signal+' listed='+str(len(raw))+
                           ' numeric='+str(len(numeric))+' nonnumeric='+str(sum(i['status']!='OK' for i in raw.values())))
            if missing:
                details.append('OP_MISSING '+name+' signal='+signal+' fields='+','.join(missing))
                details.append('OP_SAT_STATUS '+name+' '+ ' '.join(
                    k+'='+('INVALID_NUMERIC' if k in invalid else raw.get(k,{}).get('status','NOT_LISTED'))
                    for k in ('vdsat','vdssat')))
                names=sorted(raw)
                for offset in range(0,len(names),18):
                    inventories.append('OP_AVAILABLE '+name+' signal='+signal+' '+','.join(names[offset:offset+18]))
            if conflicts: details.append('OP_CONFLICT '+name+' signal='+signal+' fields='+','.join(sorted(set(conflicts))))
            if invalid: details.append('OP_INVALID '+name+' signal='+signal+' parameters='+','.join(sorted(invalid)))
        complete_count=sum(d['complete'] for d in devices)
        complete=complete_count==1 and not any(d['conflicts'] for d in devices)
        targets.append(dict(target=name,devices=devices,complete_device_count=complete_count,complete=complete))
        if not devices:
            values_lines.append('OP_TARGET '+name+' status=NOT_FOUND')
            details.append('OP_MISSING '+name+' fields=device,id|ids,vgs,vds,vdsat')
        elif complete_count>1: details.append('OP_AMBIGUOUS '+name+' complete_devices='+str(complete_count))
    return dict(read_complete=True,required_fields_complete=all(t['complete'] for t in targets),
                targets=targets,lines=values_lines+details+inventories)


def baseline_op(bound, output, psf, body, state):
    from preflight_cascode_bench import analyze
    from op_provider import parse_deck
    declared=parse_deck(bound['text'])['parameters']; settings=dict(bound['settings'])
    settings['variables']={k:v for k,v in settings['variables'].items() if k in declared}
    _,ctx=analyze(bound['text'],bound['cfg']['source_cell'],settings)
    work=output/'baseline_op'; work.mkdir(); table=work/'values.tsv'
    paths=[cb.canonical(ctx['core_path']+'.'+name) for name in cb.TARGETS]
    script=focused_op_script(psf,paths,bound['pinned']['init'],table)
    action=work/'runtime.ocn'; action.write_text(script)
    (work/'cds.lib').write_text('INCLUDE '+json.dumps(str(bound['cds']))+'\n')
    env=dict(bound['env'],ST_BATCH_PSF_TABLE=str(table))
    cb.command([cb.executable(env,'ST_OCEAN_BIN','ocean'),'-nograph','-restore',str(action)],work,env,180,work/'ocean.log')
    if not (work/'runtime.done').is_file() or (work/'runtime.done').read_text().strip()!='OK': raise ValueError('OP completion marker missing')
    rows=cb.table(table)
    cb.save(output/'baseline_op.json',rows)
    report=summarize_op(rows,paths)
    cb.save(output/'baseline_op_report.json',report)
    state.update(report); body+=report['lines']
    if not report['required_fields_complete']:
        raise ValueError('required signed OP incomplete; all target values and gaps reported above')


def simulation_evidence(output, selected):
    bad=[]; commands=[]
    for directory in ('baseline_run','baseline_generated','baseline_results'):
        for path in (output/directory).rglob('*'):
            if path.suffix not in ('.log','.out') or not path.is_file(): continue
            for line in path.read_text(errors='replace').splitlines():
                if re.search(r'ERROR\s*\(|\*Error\*|FATAL|terminated prematurely',line): bad.append(line[:500])
                if 'Command line:' in line or re.search(r'\+\+?aps\b|\+mt=',line): commands.append(line.strip())
    if bad: raise ValueError('; '.join(bad[:4]))
    check_launch(selected,'\n'.join(commands))
    info=list((output/'baseline_results').rglob('dcOpInfo.info'))
    if len(info)!=1 or not info[0].stat().st_size: raise ValueError('nonempty DC operating point PSF missing')
    psf=info[0].parent
    if not any((psf/n).is_file() and (psf/n).stat().st_size for n in ('dcOp.dc','dc.dc')): raise ValueError('nonempty DC result missing')
    return psf,['LAUNCH_EVIDENCE '+line[:1000] for line in dict.fromkeys(commands)][:8]


def failure_details(output):
    details=['NATIVE_ERROR '+v for v in cb.brief_errors(output)[:8]]
    for name in ('baseline_op/ocean.log','baseline_run/ocean.log','baseline_netlist/ocean.log'):
        path=output/name
        if path.is_file():
            details.append('LOG_TAIL '+name)
            details+=['LOG '+line[:700] for line in path.read_text(errors='replace').splitlines()[-15:]]
    return details


def file_digest(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''): digest.update(chunk)
    return digest.hexdigest()


def psf_fingerprint(psf):
    return {str(path.relative_to(psf)):file_digest(path) for path in sorted(psf.rglob('*')) if path.is_file()}


def completed_baseline(batch):
    candidates=[]
    for path in batch.glob('dc_review_ports_*/baseline_status.json'):
        state=json.loads(path.read_text())
        if state.get('converged') is True: candidates.append((path.stat().st_mtime_ns,path.parent))
    if not candidates: raise ValueError('no converged baseline exists in this batch')
    candidates.sort(reverse=True)
    if len(candidates)>1 and candidates[0][0]==candidates[1][0]: raise ValueError('latest converged baseline is ambiguous')
    baseline=candidates[0][1].resolve()
    if baseline.parent!=batch.resolve(): raise ValueError('baseline must be inside the selected batch')
    return baseline


def validated_baseline(args,body):
    bound=cb.inputs(args); batch=Path(args.batch)
    if not batch.is_absolute() or not (batch/'status.json').is_file(): raise ValueError('existing absolute batch is required')
    baseline=completed_baseline(batch)
    body+=['BASELINE_DIR='+str(baseline),'SELECTED_CORNER='+bound['settings']['corner'],
        'TEMPERATURE='+str(bound['settings']['temperature'])]
    forms=json.loads((baseline/'settings_forms.json').read_text())
    if forms!=extract_forms((baseline/'saved_test.ocn').read_text()): raise ValueError('saved settings cache differs from native export')
    selected,_=dc_settings(forms,body)
    definitions=cb.literal_files((baseline/'definition_files.txt').read_text())
    if definitions:
        recorded=baseline/'baseline_definition_hashes.json'
        if not recorded.is_file() or json.loads(recorded.read_text())!={p:cb.digest(p) for p in definitions}:
            raise ValueError('Definition Files lack unchanged historical fingerprints; cannot reuse this baseline')
    bound['fixed'].update({p:cb.digest(p) for p in definitions})
    exports=list((baseline/'baseline_generated').rglob('input.scs'))
    if len(exports)!=1: raise ValueError('saved baseline config netlist missing or ambiguous')
    actual=exports[0]
    if (baseline/'baseline_run/runtime.done').read_text().strip()!='OK': raise ValueError('saved baseline run marker is invalid')
    text=(baseline/'baseline_run.scs').read_text()
    if text!=actual.read_text(): raise ValueError('saved baseline netlist differs from actual simulation deck')
    for cached in ('baseline_netlist.scs','baseline_run.scs'):
        if circuit_shape((baseline/cached).read_text(),actual.parent,definitions)!=circuit_shape(bound['text'],bound['origin'],definitions):
            raise ValueError('saved baseline circuit/model/variables differ from confirmed config')
    body+=effective_controls(text,selected,bound['settings']['temperature'])
    psf,launch=simulation_evidence(baseline,selected); body+=launch
    bound['fixed'].update({str(p):file_digest(p) for p in (
        baseline/'settings_forms.json',baseline/'saved_test.ocn',baseline/'definition_files.txt',
        baseline/'baseline_status.json',baseline/'baseline_netlist.scs',baseline/'baseline_run.scs',actual)})
    cb.unchanged(bound)
    return bound,baseline,psf


def resolve_instance_nodes(text, path):
    """Resolve only this hierarchy, preserving exact net names and global zero."""
    from op_provider import parse_deck
    deck=parse_deck(text); instances=deck['top']; bindings={}; scope=''
    for index,part in enumerate(path.split('.')):
        found=[i for i in instances if i['name']==part]
        if len(found)!=1: raise ValueError('missing or ambiguous exact instance: '+path)
        inst=found[0]
        nodes=[bindings.get(n,n if n in deck['globals'] or not scope else scope+'.'+n) for n in inst['nodes']]
        full=scope+'.'+part if scope else part
        result=dict(inst,path=full,nodes=nodes)
        if index==len(path.split('.'))-1: return result
        definition=deck['definitions'].get(inst['master'])
        if definition is None or len(definition['ports'])!=len(nodes):
            raise ValueError('hierarchy port binding unavailable: '+full)
        bindings=dict(zip(definition['ports'],nodes));scope=full;instances=definition['instances']
    raise ValueError('empty instance path')


def node_request(bound,batch):
    from preflight_cascode_bench import analyze
    from op_provider import parse_deck
    from read_maestro_setup import read_records
    records_path=batch/'native_records.json'; native_path=batch/'native/report.tsv'
    status=json.loads((batch/'status.json').read_text())
    if any(status.get('states',{}).get(k)!='COMPLETE' for k in ('native','unchanged')):
        raise ValueError('original batch native evidence was not complete')
    records=read_records(native_path.read_text())
    if records!=json.loads(records_path.read_text()): raise ValueError('native CDF cache differs from original report')
    bound['fixed'].update({str(p):file_digest(p) for p in (batch/'status.json',records_path,native_path)})
    catalog=cb.table(bound['session']/'before/device_catalog.tsv')
    inventory=cb.table(bound['session']/'before/mos_inventory.tsv')
    deck=parse_deck(bound['text']);settings=dict(bound['settings'])
    settings['variables']={k:v for k,v in settings['variables'].items() if k in deck['parameters']}
    _,context=analyze(bound['text'],bound['cfg']['source_cell'],settings)
    root=context['core_path']; core=resolve_instance_nodes(bound['text'],root)
    ports=deck['definitions'][core['master']]['ports']
    if len(ports)!=len(core['nodes']) or len(set(ports))!=len(ports): raise ValueError('core port binding conflict')
    request=dict(core_path=root,core_ports=dict(zip(ports,core['nodes'])),targets={},voltage_sources=[])
    def record(kind,target,name):
        rows=[r for r in records if (r['kind'],r['scope'],r['name'])==(kind,target,name)]
        if len(rows)!=1 or rows[0]['status']!='OK': raise ValueError('required native CDF evidence missing: '+target+'/'+name)
        return rows[0]['raw_value']
    for target in cb.TARGETS:
        inv=[r for r in inventory if r['instance']==target]
        if len(inv)!=1: raise ValueError('current target inventory ambiguous: '+target)
        masters=[r for r in catalog if r['master']==inv[0]['master']]
        if len(masters)!=1: raise ValueError('target catalog master ambiguous: '+target)
        master=masters[0]
        for key in ('oa_library','oa_cell','oa_view'):
            if json.loads(record('source',target,key))!=(master.get(key) or 'symbol'):
                raise ValueError('native target master differs from inventory: '+target+'/'+key)
        order=record('cdf_mapping',target,'termOrder').strip()
        if not (order.startswith('(') and order.endswith(')')): raise ValueError('non-literal native termOrder: '+target)
        atom=r'"(?:\\.|[^"\\])*"|[^\s()"]+'
        if re.sub(atom,'',order[1:-1]).strip():
            raise ValueError('native termOrder must be a flat literal list: '+target)
        tokens=re.findall(atom,order[1:-1])
        names=[json.loads(t) if t.startswith('"') else t for t in tokens]
        if len(names)!=4 or set(names)!={'D','G','S','B'}: raise ValueError('unsupported or ambiguous native D/G/S/B termOrder: '+target)
        inst=resolve_instance_nodes(bound['text'],root+'.'+target)
        if len(inst['nodes'])!=len(names): raise ValueError('native terminal/netlist count conflict: '+target)
        if json.loads(record('cdf_value',target,'model'))!=inst['master']:
            raise ValueError('native target model differs from netlist: '+target)
        request['targets'][target]=dict(path=inst['path'],master=inst['master'],terminals=dict(zip(names,inst['nodes'])))
    for source in context['sources']:
        if source['master']=='vsource':
            inst=resolve_instance_nodes(bound['text'],source['path'])
            request['voltage_sources'].append(dict(path=inst['path'],nodes=inst['nodes']))
    request['nodes']=sorted(set(request['core_ports'].values()) | {n for t in request['targets'].values() for n in t['terminals'].values()} |
                            {n for s in request['voltage_sources'] for n in s['nodes']})
    return request


def cached_target_op(bound,baseline,request,psf_hashes):
    candidates=list(baseline.glob('op_review_*/op_read_status.json'))
    if not candidates: raise ValueError('a successful --read-op-only cache is required')
    candidates.sort(key=lambda p:p.stat().st_mtime_ns,reverse=True)
    if len(candidates)>1 and candidates[0].stat().st_mtime_ns==candidates[1].stat().st_mtime_ns:
        raise ValueError('latest OP cache is ambiguous')
    status_path=candidates[0];cache=status_path.parent;status=json.loads(status_path.read_text())
    if not all(status.get(k) is True for k in ('op_complete','op_required_fields_complete','psf_unchanged','converged')):
        raise ValueError('latest OP cache is not a complete successful read; no fallback')
    if (cache/'baseline_op/runtime.done').read_text().strip()!='OK': raise ValueError('cached OP native marker invalid')
    paths=[cb.canonical(request['targets'][t]['path']) for t in cb.TARGETS]
    rows=json.loads((cache/'baseline_op.json').read_text())
    if rows!=cb.table(cache/'baseline_op/values.tsv'): raise ValueError('cached OP rows differ from native table')
    report=summarize_op(rows,paths)
    if not report['required_fields_complete'] or report!=json.loads((cache/'baseline_op_report.json').read_text()):
        raise ValueError('cached OP normalization mismatch or incomplete fields')
    if json.loads((cache/'psf_before_sha256.json').read_text())!=psf_hashes:
        raise ValueError('PSF differs from the successful cached OP read')
    for rel in ('op_read_status.json','baseline_op.json','baseline_op_report.json','psf_before_sha256.json','baseline_op/values.tsv','baseline_op/runtime.done'):
        p=cache/rel;bound['fixed'][str(p)]=file_digest(p)
    values={}
    for target in report['targets']:
        dev=next(d for d in target['devices'] if d['complete'])
        # Terminal differences of an internal subdevice are not the macro ports.
        if dev['signal']!=cb.canonical(request['targets'][target['target']]['path']):
            raise ValueError('target OP resolves to an internal subdevice; external port mapping needs explicit proof')
        values[target['target']]=dev['normalized']
    return values,cache


def node_context_script(psf,request,init,table):
    q=json.dumps
    return ('load('+q(str(init))+')\nstNodeNames=list('+ ' '.join(q(n) for n in request['nodes'] if n!='0')+')\n'
        +'stNodeSources=list('+ ' '.join(q(s['path']+':') for s in request['voltage_sources'])+')\n'+r'''
procedure(stNodeScalar(value)
  cond((numberp(value) value)
       (drIsWaveform(value)
         let((vec result)
           vec=drGetWaveformYVec(value)
           when(equal(drVectorLength(vec) 1) result=drGetElem(vec 0))
           if(numberp(result) then result else nil)))
       (t nil))
)
procedure(stNodeWrite(port kind name)
  let((result decoded scalar)
    result=errset(getData(name) nil)
    when(result
      decoded=errset(stNodeScalar(car(result)) nil)
      when(decoded scalar=car(decoded)))
    if(numberp(scalar) then
      fprintf(port "%s\t%s\t%.17g\tOK\n" kind name float(scalar))
    else
      fprintf(port "%s\t%s\t\t%s\n" kind name if(result then "NON_NUMERIC" else "READ_ERROR")))
  )
)
procedure(stNodeCurrentP(name)
  let((found)
    foreach(prefix stNodeSources
      when(and(strlen(name)>strlen(prefix) equal(substring(name 1 strlen(prefix)) prefix)) found=t))
    found
  )
)
procedure(stNodeRead()
  let((port signals)
    unless(openResults(__PSF__) error("Cannot open saved PSF"))
    unless(selectResult('dcOp) error("dcOp node result unavailable"))
    signals=outputs(?map nil)
    port=outfile(__TABLE__)
    unless(port error("Cannot create node table"))
    fprintf(port "kind\tsignal\tvalue\tstatus\n")
    foreach(name stNodeNames
      if(member(name signals) then stNodeWrite(port "node" name)
      else fprintf(port "node\t%s\t\tMISSING\n" name)))
    foreach(name signals when(stNodeCurrentP(name) stNodeWrite(port "current" name)))
    close(port)
    t
  )
)
result=errset(stNodeRead() t)
when(and(result car(result))
  port=outfile(__MARKER__) fprintf(port "OK\n") close(port))
exit()
'''.replace('__PSF__',q(str(psf))).replace('__TABLE__',q(str(table))).replace('__MARKER__',q(str(table.parent/'runtime.done'))))


def summarize_nodes(rows,request,cached):
    values={'0':0.0};issues=[];seen=set();currents=[]
    for row in rows:
        if set(row)!={'kind','signal','value','status'} or row['status'] not in ('OK','MISSING','NON_NUMERIC','READ_ERROR'):
            raise ValueError('invalid node table schema/status')
        kind,name=row['kind'],row['signal'];key=(kind,name)
        if kind=='node':
            if name not in request['nodes'] or name=='0': raise ValueError('unrequested node in table: '+name)
        elif kind=='current':
            if not any(name.startswith(s['path']+':') and len(name)>len(s['path'])+1 for s in request['voltage_sources']):
                raise ValueError('unrequested voltage-source current: '+name)
        else: raise ValueError('invalid node row kind')
        value=None; status=row['status']
        if status=='OK':
            try: value=float(row['value'])
            except (TypeError,ValueError): status='INVALID_NUMERIC'
            if value is not None and not math.isfinite(value): status='INVALID_NUMERIC'
        if key in seen:
            status='DUPLICATE'; values.pop(name,None)
        seen.add(key)
        if kind=='current': currents.append(dict(signal=name,value=value if status=='OK' else None,status=status));continue
        if status=='OK' and not any(i['signal']==name for i in issues): values[name]=value
        else: issues.append(dict(signal=name,status=status));values.pop(name,None)
    for name in request['nodes']:
        if name not in values and not any(i['signal']==name for i in issues): issues.append(dict(signal=name,status='MISSING_ROW'))
    report=dict(complete=not issues,node_issues=issues,reference_zero='Spectre node 0',targets={},
                core_ports={port:dict(node=n,value=values.get(n)) for port,n in request['core_ports'].items()},
                voltage_source_currents=currents,total_supply_current_binding_ready=False,cgg_complete=True,optional_op_fields_missing={})
    for name,target in request['targets'].items():
        volts={term:values.get(node) for term,node in target['terminals'].items()}
        diff={}; delta={};op=cached[name]
        if all(v is not None for v in volts.values()):
            diff={k:volts[t]-volts['S'] for k,t in (('vgs','G'),('vds','D'),('vbs','B'))}
            delta={raw:diff[key]-op[raw] for key,raw in (('vgs','vgst'),('vds','vdst'),('vbs','vest')) if raw in op}
        if 'cgg' not in op: report['cgg_complete']=False
        report['optional_op_fields_missing'][name]=[k for k in ('region','reversed') if k not in op]
        report['targets'][name]=dict(terminal_nodes=target['terminals'],terminal_voltages=volts,
            terminal_differences=diff,cached_op=op,terminal_difference_minus_native=delta)
    return report


def read_node_context(args):
    body=[];output=None;error=None;converged=False;unchanged=False;cache_ok=False;report={}
    print('BASELINE_CONTEXT=START',flush=True)
    try:
        if args.timeout<=0: raise ValueError('timeout must be positive')
        bound,baseline,psf=validated_baseline(args,body);converged=True
        before=psf_fingerprint(psf)
        request=node_request(bound,Path(args.batch))
        cached,cache=cached_target_op(bound,baseline,request,before);cache_ok=True
        body.append('OP_CACHE_DIR='+str(cache));cb.unchanged(bound)
        output=Path(tempfile.mkdtemp(prefix='node_context_',dir=str(baseline)))
        body.append('OUTPUT_DIR='+str(output))
        cb.save(output/'node_request.json',request);cb.save(output/'psf_before_sha256.json',before)
        work=output/'node_read';work.mkdir();table=work/'values.tsv'
        (work/'cds.lib').write_text('INCLUDE '+json.dumps(str(bound['cds']))+'\n')
        action=work/'runtime.ocn';action.write_text(node_context_script(psf,request,bound['pinned']['init'],table))
        env=dict(bound['env'],ST_NODE_REQUEST=str(output/'node_request.json'),ST_NODE_TABLE=str(table))
        try:
            cb.command([cb.executable(env,'ST_OCEAN_BIN','ocean'),'-nograph','-restore',str(action)],work,env,args.timeout,work/'ocean.log')
            if (work/'runtime.done').read_text().strip()!='OK': raise ValueError('node completion marker invalid')
            report=summarize_nodes(cb.table(table),request,cached);cb.save(output/'node_context.json',report)
            for name,t in report['targets'].items():
                body.append('NODE_TARGET '+name+' '+' '.join(k+'='+('MISSING' if v is None else str(v)) for k,v in t['terminal_voltages'].items()))
                body.append('NODE_NETS '+name+' '+' '.join(k+'='+v for k,v in t['terminal_nodes'].items()))
                body.append('PORT_DIFFERENCES '+name+' '+' '.join(k+'='+str(v) for k,v in t['terminal_differences'].items()))
                body.append('PORT_MINUS_NATIVE '+name+' '+' '.join(k+'='+str(v) for k,v in t['terminal_difference_minus_native'].items()))
                body.append('CACHED_OP_AUX '+name+' '+' '.join(k+'='+str(t['cached_op'].get(k,'NOT_AVAILABLE')) for k in ('cgg','region','reversed','vgs','vds','vgst','vdst','vdsat')))
            body+=['OPTIONAL_OP_MISSING '+name+' fields='+','.join(fields) for name,fields in report['optional_op_fields_missing'].items() if fields]
            body+=['CORE_PORT '+k+' node='+v['node']+' value='+str(v['value']) for k,v in report['core_ports'].items()]
            body+=['VSOURCE_CURRENT_CANDIDATE '+r['signal']+' value='+str(r['value'])+' status='+r['status'] for r in report['voltage_source_currents']]
            body+=['NODE_ISSUE '+i['signal']+' status='+i['status'] for i in report['node_issues']]
            if not report['complete']: raise ValueError('required node voltages incomplete; all targets reported')
            if not report['cgg_complete']: raise ValueError('cached target cgg missing; node voltages retained')
        finally:
            unchanged=before==psf_fingerprint(psf);cb.unchanged(bound)
            if not unchanged: raise ValueError('PSF changed during node read')
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as caught:
        error=' '.join(str(caught).split())[:800];body.append('ISSUE '+error)
        if output is not None:
            log=output/'node_read/ocean.log'
            if log.is_file(): body+=['NODE_LOG '+s[:700] for s in log.read_text(errors='replace').splitlines()[-12:]]
    summary=['CHECKER=cascode-node-context-v1','RESULT='+('BASELINE_CONTEXT_READ_OK' if error is None else 'INCOMPLETE'),
        'SPECTRE_RERUN=false','BASELINE_DC='+('CONVERGED' if converged else 'NOT_REVALIDATED'),
        'OP_CACHE_REUSED='+str(cache_ok).lower(),'NODE_READ='+('COMPLETE' if report.get('complete') else 'INCOMPLETE')]
    summary+=body[:155]+['SUMMARY_OMITTED_LINES='+str(max(0,len(body)-155)),
        'CACHED_CGG_COMPLETE='+str(report.get('cgg_complete',False)).lower(),
        'PSF_UNCHANGED='+str(unchanged).lower(),'TOTAL_SUPPLY_CURRENT_BINDING_READY=false',
        'SIMULATION_PROFILE_READY=false','PDK_ELECTRICAL_RULES_READY=false','ELECTRICAL_VERIFIED=false',
        'VBIAS_GENERATED=false','RAW_DETAILS_REMAIN_ON_SERVER=true']
    if output is not None:
        cb.save(output/'node_read_status.json',dict(error=error,node_complete=report.get('complete',False),psf_unchanged=unchanged,op_cache_reused=cache_ok))
        (output/'summary.txt').write_text('\n'.join(summary)+'\n')
    print('\n'.join(summary));return 0 if error is None else 2


def read_existing_op(args):
    body=[]; output=None; error=None; converged=False; psf_unchanged=False; op_state={}
    print('REUSE_BASELINE=START',flush=True)
    try:
        bound,baseline,psf=validated_baseline(args,body);converged=True
        before=psf_fingerprint(psf)
        output=Path(tempfile.mkdtemp(prefix='op_review_',dir=str(baseline)))
        body.append('OUTPUT_DIR='+str(output))
        cb.save(output/'psf_before_sha256.json',before)
        print('REUSE_BASELINE=COMPLETE\nBASELINE_OP=START',flush=True)
        try: baseline_op(bound,output,psf,body,op_state)
        finally:
            psf_unchanged=before==psf_fingerprint(psf)
            cb.unchanged(bound)
            if not psf_unchanged: raise ValueError('saved PSF changed during OP read')
        print('BASELINE_OP=COMPLETE',flush=True)
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as caught:
        error=' '.join(str(caught).split())[:1000]; body+=['ISSUE '+error]
        if output is not None: body+=failure_details(output)
    summary=['CHECKER=cascode-saved-op-v3','RESULT='+('BASELINE_READ_OK' if error is None else 'INCOMPLETE'),
        'SPECTRE_RERUN=false','BASELINE_REUSED='+str(converged).lower(),
        'BASELINE_DC='+('CONVERGED' if converged else 'NOT_REVALIDATED'),
        'OP_READ='+('COMPLETE' if op_state.get('read_complete') else 'INCOMPLETE'),
        'OP_REQUIRED_FIELDS_COMPLETE='+str(op_state.get('required_fields_complete',False)).lower(),
        'OP_SCOPE=I21_I105_all_available_device_parameters']
    summary+=body[:150]+['SUMMARY_OMITTED_LINES='+str(max(0,len(body)-150)),
        'SAVED_SETTINGS_APPLIED_TO_BASELINE='+str(converged).lower(),'PSF_UNCHANGED='+str(psf_unchanged).lower(),
        'SIMULATION_PROFILE_READY=false','PDK_ELECTRICAL_RULES_READY=false','ELECTRICAL_VERIFIED=false',
        'VBIAS_GENERATED=false','RAW_DETAILS_REMAIN_ON_SERVER=true']
    if output is not None:
        cb.save(output/'op_read_status.json',dict(error=error,converged=converged,op_complete=error is None,op_read_complete=op_state.get('read_complete',False),
            op_required_fields_complete=op_state.get('required_fields_complete',False),psf_unchanged=psf_unchanged))
        (output/'summary.txt').write_text('\n'.join(summary)+'\n')
    print('\n'.join(summary)); return 0 if error is None else 2


def run_baseline(bound, output, forms, timeout):
    body=['SELECTED_CORNER='+bound['settings']['corner'],'TEMPERATURE='+str(bound['settings']['temperature']),
        'SAVED_FORM_COUNT='+str(len(forms)), 'OUTPUT_DIR='+str(output),
        'JOB_POLICY_ERROR_PRESENT='+str(any('ASSEMBLER-1944' in v for v in cb.brief_errors(output))).lower()]
    converged=False; launched=False; error=None; op_state={}
    try:
        diagnostics=[]
        try: selected,details=dc_settings(forms,diagnostics)
        finally: body+=diagnostics
        body+=['SAVED_DC '+s for s in details]
        definitions=cb.literal_files((output/'definition_files.txt').read_text())
        bound['fixed'].update({p:cb.digest(p) for p in definitions})
        cb.save(output/'baseline_definition_hashes.json',{p:cb.digest(p) for p in definitions})
        body+=['DEFINITION_FILES_COUNT='+str(len(definitions)), 'NON_DC_ANALYSES_SKIPPED=true']
        cb.unchanged(bound)
        print('BASELINE_NETLIST=START',flush=True)
        body+=ocean_stage(bound,output,selected,definitions,'netlist',180)
        print('BASELINE_NETLIST=COMPLETE',flush=True)
        print('BASELINE_RUN=START',flush=True); launched=True
        ocean_stage(bound,output,selected,definitions,'run',timeout)
        psf,launch=simulation_evidence(output,selected); body+=launch
        converged=True; print('BASELINE_RUN=COMPLETE',flush=True)
        print('BASELINE_OP=START',flush=True); baseline_op(bound,output,psf,body,op_state)
        cb.unchanged(bound); print('BASELINE_OP=COMPLETE',flush=True)
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as caught:
        error=' '.join(str(caught).split())[:1000]
        body+=['ISSUE '+error]+failure_details(output)
    summary=['CHECKER=cascode-saved-dc-v4','RESULT='+('BASELINE_READ_OK' if error is None else 'INCOMPLETE'),
        'BASELINE_RUN_REQUESTED='+str(launched).lower(),'BASELINE_DC='+('CONVERGED' if converged else 'NOT_COMPLETED'),
        'OP_READ='+('COMPLETE' if op_state.get('read_complete') else 'INCOMPLETE'),
        'OP_REQUIRED_FIELDS_COMPLETE='+str(op_state.get('required_fields_complete',False)).lower()]
    summary+=body[:155]+['SUMMARY_OMITTED_LINES='+str(max(0,len(body)-155)),
        'SAVED_SETTINGS_APPLIED_TO_BASELINE='+str(converged).lower(),
        'SIMULATION_PROFILE_READY=false','PDK_ELECTRICAL_RULES_READY=false','ELECTRICAL_VERIFIED=false',
        'VBIAS_GENERATED=false','RAW_DETAILS_REMAIN_ON_SERVER=true']
    cb.save(output/'baseline_status.json',dict(error=error,converged=converged,op_complete=error is None,op_read_complete=op_state.get('read_complete',False),
        op_required_fields_complete=op_state.get('required_fields_complete',False),electrical_verified=False))
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
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--run-dc', action='store_true', help='apply saved DC settings and measure original circuit only')
    mode.add_argument('--read-op-only', action='store_true', help='read targets from the latest converged baseline without simulation')
    mode.add_argument('--read-node-context', action='store_true', help='read absolute port voltages and reuse successful OP cache without simulation')
    parser.add_argument('--dc-timeout', type=int, default=600)
    args = parser.parse_args()
    if args.read_op_only: return read_existing_op(args)
    if args.read_node_context: return read_node_context(args)
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
