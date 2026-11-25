"""Project-local CLI. No flash, unlock, reset, or macro-writing command exists."""
import argparse
from datetime import datetime, timezone
import html
import json
import sys
from pathlib import Path
from .device import VialDevice
from .model import ROOT,read_json,save_json,parse_code,changes,digest
from .validation import validate
from .workflow import identity,snapshot,check_snapshot,make_candidate,apply_candidate,exclusive,recover


def render(data,path):
    check_snapshot(data)
    positions=read_json(ROOT/'firmware/positions.json')
    names={}
    for key,code in read_json(ROOT/'firmware/keycodes.json').items():
        if key.startswith('KC_') and (code not in names or len(key)<len(names[code])):
            names[code]=key
    panels=[]
    for layer,grid in enumerate(data['layout']):
        boxes=[]
        for key,p in positions.items():
            r,c=p['matrix'];code=grid[r][c]
            label=names.get(code,hex(code))
            if code==0x292c:label='Space / hold Cmd+Ctrl'
            if code==parse_code('TL_LOWR'):label='Numbers (hold)'
            if code==parse_code('TL_UPPR'):label='Symbols (hold)'
            boxes.append(f'<div class="key" style="left:{p["x"]*70}px;top:{p["y"]*65}px" title="{key}; matrix {r},{c}">{html.escape(label)}</div>')
        panels.append(f'<section><h2>Layer {layer}</h2><div class="board">'+''.join(boxes)+'</div></section>')
    content="""<!doctype html><html><meta charset="utf-8"><title>Corne keymap snapshot</title><style>body{font:15px system-ui;background:#101820;color:#eef;padding:24px}.board{position:relative;width:1100px;height:330px}.key{position:absolute;width:66px;height:58px;border:1px solid #678;border-radius:7px;display:flex;align-items:center;justify-content:center;text-align:center;font-size:10px;background:#203444}section{margin:28px 0}</style><h1>Corne keymap snapshot</h1><p>Manual reference, not live layer tracking. Labels show raw bindings; transparent keys inherit lower layers. Hover for physical positions.</p>"""+''.join(panels)
    out=Path(path);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(content)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('inspect')
    recovery=sub.add_parser('recover');recovery.add_argument('transaction')
    capture=sub.add_parser('capture');capture.add_argument('--out',default=str(ROOT/'state/live.json'))
    plan=sub.add_parser('plan');plan.add_argument('--from',dest='baseline',required=True);plan.add_argument('--set',dest='edits',action='append',nargs=3,metavar=('LAYER','POSITION','KEYCODE'),required=True);plan.add_argument('--reason',required=True);plan.add_argument('--requirement',action='append',required=True);plan.add_argument('--out',default=str(ROOT/'layouts/candidate.json'))
    check=sub.add_parser('validate');check.add_argument('file')
    diff=sub.add_parser('diff');diff.add_argument('file')
    apply=sub.add_parser('apply');apply.add_argument('file')
    restore=sub.add_parser('restore');restore.add_argument('backup');restore.add_argument('--reason',required=True)
    accept=sub.add_parser('accept');accept.add_argument('--observation',required=True)
    view=sub.add_parser('render');view.add_argument('file');view.add_argument('--out',default=str(ROOT/'build/keymap.html'))
    args=p.parse_args()
    try:
        if args.command=='inspect':
            with VialDevice(identity()) as d: result=d.identity()
        elif args.command=='capture':
            with exclusive(),VialDevice(identity()) as d: result=snapshot(d)
            save_json(args.out,result)
            result={'saved':args.out,'layout_sha256':result['layout_sha256'],'validation':validate(result['layout'])}
        elif args.command=='plan':
            result=make_candidate(read_json(args.baseline),[(int(l),key,code) for l,key,code in args.edits],args.reason,args.requirement)
            save_json(args.out,result)
            result={'saved':args.out,'changes':result['changes'],'validation':result['validation']}
        elif args.command in ('validate','render'):
            data=read_json(args.file);data=data.get('proposed',data);check_snapshot(data)
            if args.command=='render':
                render(data,args.out);result={'saved':args.out}
            else:
                result=validate(data['layout']);print(json.dumps(result,indent=2))
                return 1 if any(x['status']=='fail' for x in result) else 0
        elif args.command=='diff':
            data=read_json(args.file);check_snapshot(data['baseline']);check_snapshot(data['proposed'])
            positions={tuple(v['matrix']):k for k,v in read_json(ROOT/'firmware/positions.json').items()}
            result=[dict(x,position=positions.get((x['row'],x['col'])),before=hex(x['before']),after=hex(x['after'])) for x in changes(data['baseline']['layout'],data['proposed']['layout'])]
        elif args.command=='recover':
            result=recover(args.transaction)
        elif args.command=='apply':
            result=apply_candidate(read_json(args.file))
        elif args.command=='restore':
            desired=read_json(args.backup);check_snapshot(desired)
            with exclusive(),VialDevice(identity()) as d: live=snapshot(d)
            candidate={'schema':1,'baseline':live,'proposed':desired,'changes':changes(live['layout'],desired['layout']),'reason':args.reason,'requirement_ids':['HW-01'],'manual_result':'unverified'}
            result=apply_candidate(candidate)
        elif args.command=='accept':
            if not args.observation.strip(): raise ValueError('Record an actual user observation')
            expected=read_json(ROOT/'layouts/candidate-live.json');check_snapshot(expected)
            with exclusive(),VialDevice(identity()) as d:
                for journal in (ROOT/'state').glob('transaction-*/journal.json'):
                    if read_json(journal).get('status') in ('applying','rollback-required'):
                        raise ValueError('Resolve interrupted transactions before acceptance')
                live=snapshot(d)
                if live['layout']!=expected['layout']:raise ValueError('Device changed since application; capture and review first')
                live['acceptance']={'observation':args.observation,'accepted_at':datetime.now(timezone.utc).isoformat()}
                save_json(ROOT/'layouts/accepted.json',live);result={'saved':'layouts/accepted.json'}
        print(json.dumps(result,indent=2));return 0
    except Exception as e:
        print(f'ERROR: {e}',file=sys.stderr);return 1

if __name__=='__main__':
    raise SystemExit(main())
