#!/usr/bin/env python3
"""Join a complete two-player game to an explicitly compiled inhabited bootstrap.

Only local custody and existing admitted APIs are used. No PDS requests or posts.
The fixed authored moves are an example match, never a Python game evaluator.
"""
import argparse
import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT/path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


bootstrap = module('table_journey_bootstrap','scripts/bootstrap.py')
table = module('table_journey_protocol','game/table/protocol.py')
client = module('table_journey_client','game/table/client.py')
SEATS = ['did:plc:aaaaaaaaaaaaaaaaaaaaaaaa','did:plc:bbbbbbbbbbbbbbbbbbbbbbbb']
# Authored original 11x11 match; all ten rounds agree with the original Rust core.
# Coordinates and exact states: game/automatafl/original-opening-qualification.json.
MATCH = [((104, 71), (0, 3)), ((71, 60), (17, 18)),
         ((60, 49), (16, 17)), ((49, 38), (11, 22)),
         ((15, 13), (90, 91)), ((13, 12), (90, 91)),
         ((90, 91), (96, 95)), ((12, 11), (90, 91)),
         ((11, 0), (90, 91)), ((0, 1), (90, 91))]

def immutable_private(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    raw = bootstrap.canonical(value)+b'\n'
    try:
        fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError:
        if path.read_bytes()!=raw:
            raise ValueError('custody preimage changed: '+str(path))
        return value
    with os.fdopen(fd,'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    directory=os.open(path.parent,os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return value


def run(directory):
    directory=Path(directory).expanduser().resolve()
    manifest=bootstrap.loads((directory/'manifest.json').read_bytes())
    if manifest.get('runtime',{}).get('name')!='compiled':
        raise ValueError('table journey requires an explicitly compiled bootstrap; no implicit runtime migration')
    if bootstrap.canonical(manifest['runtime'])!=bootstrap.canonical(bootstrap.history.runtime('compiled')):
        raise ValueError('bootstrap compiled runtime pins changed; restore or migrate explicitly')
    desk=bootstrap.desk_module.Desk(directory/'world.json',directory/'artifacts',profile='compiled')
    target=manifest['table']
    custody=directory/'table-journey'
    completed=custody/'report.json'
    if completed.exists():
        report=bootstrap.loads(completed.read_bytes())
        if desk.inspect(target)!=report['finalRoot']:
            raise ValueError('completed table root changed; inspect existing evidence')
        return report
    custody.mkdir(exist_ok=True,mode=0o700)
    before_path=custody/'cafe-before.json'
    before=(bootstrap.loads(before_path.read_bytes()) if before_path.exists() else
            immutable_private(before_path,bootstrap.inspect_view(directory)))
    program=table.protocol(target)
    bootstrap.preserve_lowering(directory,bootstrap.canonical(program))
    events=[]

    def step(key, make_request, expected='committed'):
        request_path=custody/'requests'/(key+'.json')
        request=(bootstrap.loads(request_path.read_bytes()) if request_path.exists() else
                 immutable_private(request_path,make_request()))
        reply=desk.exchange(request)
        immutable_private(custody/'receipts'/(key+'.json'),reply)
        if reply.get('kind')!=expected:
            raise RuntimeError(key+': '+str(reply))
        events.append({'turn':key,'kind':reply['kind']})
        return reply

    step('install',lambda:{'op':'reprogram','object':target,'principal':manifest['participants'][0],
        'intent':'table-journey:install','expected':desk.inspect(target),
        'protocol':program,'state':program['initial']})
    step('seat-law',lambda:{'op':'law','object':target,'principal':'local-operator',
        'intent':'table-journey:seat-law','expected':desk.inspect(target),'law':table.law(*SEATS)})

    def invoke(key, command, input, seat=0, expected='committed'):
        return step(key,lambda:{'op':'invoke','object':target,'principal':SEATS[seat],
            'intent':'table-journey:'+key,'expected':desk.inspect(target),
            'command':command,'input':input},expected)

    rounds=[]
    for number,moves in enumerate(MATCH):
        private=custody/'private'/('round-'+str(number)+'.json')
        pair=(bootstrap.loads(private.read_bytes()) if private.exists() else immutable_private(private,
              [client.prepare(target,number,seat,*move) for seat,move in enumerate(moves)]))
        for seat in (0,1):
            invoke(f'{number}-commit-{seat}','commit'+str(seat),pair[seat]['commit'],seat)
        if number==len(MATCH)-1:
            invoke('late-wrong-reveal','reveal1',{**pair[1]['reveal'],'nonce':'f'*64},1,'refused')
        for seat in (0,1):
            invoke(f'{number}-reveal-{seat}','reveal'+str(seat),pair[seat]['reveal'],seat)
        resolved=invoke(f'{number}-resolve','resolve',{'round':number})
        rounds.append(client.public_view(resolved['data']['root']))
    final=desk.inspect(target)
    if final['state']['game']['winner']!=1 or final['state']['round']!=len(MATCH):
        raise RuntimeError('authored match did not finish with the qualified game result')
    after=bootstrap.inspect_view(directory)
    if after!=before:
        raise RuntimeError('table match unexpectedly changed the source-bound cafe view')
    report={'format':'delvetalk-inhabited-table-journey-v1','runtime':'compiled',
            'database':str(directory/'world.json'),'object':target,'seats':SEATS,
            'events':events,'rounds':rounds,'finalRoot':final,
            'cafeBefore':before,'cafeAfter':after,
            'scope':'local authored match; no external delivery'}
    return immutable_private(completed,report)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path,help='existing bootstrap created with --profile compiled')
    args=parser.parse_args()
    report=run(args.directory)
    print(bootstrap.desk_module.world.wire_dumps({'object':report['object'],
        'rounds':len(report['rounds']),'view':client.public_view(report['finalRoot']),
        'report':str(args.directory/'table-journey/report.json')}))


if __name__=='__main__':
    main()
