"""Compare-before-write transactions, durable backups, and verified rollback."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
from .device import VialDevice
from .model import ROOT, read_json, save_json, digest, changes, shape, parse_code
from .validation import assert_valid


def sync_directory(path):
    fd=os.open(path,os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def identity():
    return read_json(ROOT / "firmware/device.json")


def snapshot(device):
    first = device.read_layout()
    second = device.read_layout()
    if first != second:
        raise RuntimeError("Keymap changed during capture; close other editors and retry.")
    if not shape(first):
        raise ValueError("Invalid live keymap dimensions")
    return {"schema": 1, "scope": "keymap-only", "captured_at": datetime.now(timezone.utc).isoformat(),
            "identity": device.identity(), "layout": first, "layout_sha256": digest(first)}


def check_snapshot(data):
    if data.get("schema") != 1 or data.get("scope") != "keymap-only" or not shape(data.get("layout")):
        raise ValueError("Unsupported snapshot schema or dimensions")
    if digest(data["layout"]) != data.get("layout_sha256"):
        raise ValueError("Snapshot content checksum mismatch")
    for k,v in identity().items():
        if data.get("identity",{}).get(k) != v:
            raise ValueError(f"Snapshot identity differs at {k}")


def make_candidate(baseline, edits, reason, requirement_ids):
    import copy,yaml
    check_snapshot(baseline)
    if not reason.strip() or not requirement_ids:
        raise ValueError("A reason and affected requirement IDs are required")
    known={x['id'] for x in yaml.safe_load((ROOT/'requirements.yaml').read_text())['requirements']}
    if set(requirement_ids)-known:
        raise ValueError("Unknown requirement ID")
    proposed=copy.deepcopy(baseline)
    positions=read_json(ROOT/'firmware/positions.json')
    touched=set()
    for layer,position,code in edits:
        if type(layer) is not int or not 0<=layer<8 or position not in positions:
            raise ValueError("Invalid layer or physical key")
        row,col=positions[position]['matrix']
        if (layer,row,col) in touched:
            raise ValueError("Duplicate edit position")
        touched.add((layer,row,col))
        proposed['layout'][layer][row][col]=parse_code(code)
    proposed['layout_sha256']=digest(proposed['layout'])
    report=assert_valid(proposed['layout'])
    delta=changes(baseline['layout'],proposed['layout'])
    check_edits(delta)
    return {'schema':1,'baseline':baseline,'proposed':proposed,'changes':delta,'reason':reason,
            'requirement_ids':requirement_ids,'validation':report,'manual_result':'unverified'}


def check_edits(delta):
    physical={tuple(x['matrix']) for x in read_json(ROOT/'firmware/positions.json').values()}
    tri={parse_code('TL_LOWR'),parse_code('TL_UPPR')}
    for change in delta:
        if (change['row'],change['col']) not in physical:
            raise ValueError("Cannot edit an absent physical switch")
        for code in (change['before'],change['after']):
            if not (0<=code<=0x52df or code in tri):
                raise ValueError(f"Keycode {code:#x} is outside the reversible ordinary binding scope")


@contextmanager
def exclusive():
    state=ROOT/'state'
    state.mkdir(exist_ok=True)
    sync_directory(state.parent)
    with (state/'device.lock').open('a') as f:
        try:
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another keyboard-lab transaction is active") from None
        yield


def apply_candidate(candidate, device_factory=VialDevice, state_root=None):
    import yaml
    known={r['id'] for r in yaml.safe_load((ROOT/'requirements.yaml').read_text())['requirements']}
    if candidate.get('schema')!=1 or not candidate.get('reason','').strip() or not candidate.get('requirement_ids') or set(candidate['requirement_ids'])-known:
        raise ValueError('Candidate requires schema, reason, and known requirement IDs')
    baseline,proposed=candidate['baseline'],candidate['proposed']
    check_snapshot(baseline);check_snapshot(proposed)
    assert_valid(proposed['layout'])
    delta=changes(baseline['layout'],proposed['layout'])
    if delta != candidate['changes']:
        raise ValueError("Candidate change list does not match its layouts")
    check_edits(delta)
    state=Path(state_root) if state_root else ROOT/'state'
    transaction=state/('transaction-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    with exclusive(),device_factory(identity()) as device:
        for old in state.glob('transaction-*/journal.json'):
            if read_json(old).get('status') in ('applying','rollback-required'):
                raise RuntimeError(f'Unresolved transaction {old.parent}; run recover before editing')
        live=snapshot(device)
        if live['layout_sha256'] != baseline['layout_sha256']:
            raise RuntimeError("Device differs from candidate baseline; capture and re-plan. No writes performed.")
        if not delta:
            return {'status':'no-op','changes':0,'snapshot':live}
        transaction.mkdir(parents=True)
        sync_directory(state)
        save_json(transaction/'before.json',live)
        save_json(transaction/'candidate.json',candidate)
        journal={'status':'applying','attempted':[],'verified':[]}
        save_json(transaction/'journal.json',journal)
        try:
            for edit in delta:
                # Journal BEFORE touching hardware: a lost reply may still mean a completed write.
                journal['attempted'].append(edit)
                save_json(transaction/'journal.json',journal)
                device.set_key(edit['layer'],edit['row'],edit['col'],edit['after'])
                journal['verified'].append(edit)
                save_json(transaction/'journal.json',journal)
            after=snapshot(device)
            if after['layout']!=proposed['layout']:
                raise RuntimeError("Whole-keymap readback differs from candidate")
            save_json(transaction/'after.json',after)
            save_json(ROOT/'layouts/candidate-live.json',after)
            journal['status']='applied-unaccepted'
            save_json(transaction/'journal.json',journal)
            return {'status':journal['status'],'changes':len(delta),'transaction':str(transaction)}
        except BaseException as failure:
            journal['failure']=str(failure)
            journal['status']='rollback-required'
            try:
                save_json(transaction/'journal.json',journal)
            except Exception as journal_error:
                journal['journal_error']=str(journal_error)
            try:
                # Reopen after transport errors; never retry an unverified write blindly.
                device.close()
                with device_factory(identity()) as recovery:
                    current=snapshot(recovery)
                    allowed={(x['layer'],x['row'],x['col']):x for x in journal['attempted']}
                    for diff in changes(live['layout'],current['layout']):
                        key=(diff['layer'],diff['row'],diff['col'])
                        if key not in allowed or diff['after']!=allowed[key]['after']:
                            raise RuntimeError("Unexpected concurrent edit; automatic rollback refused")
                    for edit in reversed(journal['attempted']):
                        l,r,c=edit['layer'],edit['row'],edit['col']
                        if current['layout'][l][r][c]!=edit['before']:
                            recovery.set_key(l,r,c,edit['before'])
                    restored=snapshot(recovery)
                    if restored['layout']!=live['layout']:
                        raise RuntimeError("Rollback readback mismatch")
                    journal['status']='rolled-back'
            except BaseException as rollback_error:
                journal['rollback_error']=str(rollback_error)
            try:
                save_json(transaction/'journal.json',journal)
            except Exception:
                pass
            raise RuntimeError(f"Apply failed ({journal['status']}); see {transaction}") from failure


def recover(transaction, device_factory=VialDevice):
    transaction=Path(transaction).resolve()
    with exclusive():
        journal=read_json(transaction/'journal.json')
        if journal.get('status') not in ('applying','rollback-required'):
            raise ValueError('Transaction does not require recovery')
        before=read_json(transaction/'before.json');check_snapshot(before)
        candidate=read_json(transaction/'candidate.json')
        check_snapshot(candidate['baseline']);check_snapshot(candidate['proposed'])
        if candidate['baseline']['layout']!=before['layout']:
            raise ValueError('Recovery baseline mismatch')
        delta=changes(before['layout'],candidate['proposed']['layout'])
        attempted=journal['attempted']
        if attempted!=delta[:len(attempted)]:
            raise ValueError('Invalid recovery journal')
        check_edits(attempted)
        allowed={(e['layer'],e['row'],e['col']):e for e in attempted}
        with device_factory(identity()) as device:
            current=snapshot(device)
            for diff in changes(before['layout'],current['layout']):
                key=(diff['layer'],diff['row'],diff['col'])
                if key not in allowed or diff['after']!=allowed[key]['after']:
                    raise RuntimeError('Unexpected concurrent edit; recovery refused')
            for edit in reversed(attempted):
                l,r,c=edit['layer'],edit['row'],edit['col']
                if current['layout'][l][r][c]!=edit['before']:
                    device.set_key(l,r,c,edit['before'])
            if snapshot(device)['layout']!=before['layout']:
                raise RuntimeError('Recovery readback mismatch')
        journal['status']='rolled-back'
        save_json(transaction/'journal.json',journal)
        return {'status':'rolled-back','transaction':str(transaction)}
