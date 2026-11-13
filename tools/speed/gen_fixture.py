"""Deterministic invented PSI116 workload; never reads an input file."""
import argparse
import random
from pathlib import Path


def generate(seed=116, branches=41, owners=89, blocked=40, nodes=1654):
    if branches < 1 or owners < 1 or blocked < 0 or nodes < 6*(owners+blocked):
        raise ValueError('Invalid fixture dimensions')
    rng = random.Random(seed)
    # Each short owner is bounded by an independent PIPE and FLAN. A long
    # connecting PIPE separates neighbouring assemblies in the same branch.
    assignments = [[] for _ in range(branches)]
    for i in range(owners):
        assignments[i % branches].append((i, False))
    for i in range(blocked):
        assignments[i % branches].append((i, True))
    counts = [6*len(a) for a in assignments]
    extra = nodes - sum(counts)
    for i in range(extra//2):
        counts[i % branches] += 2
    if extra % 2:
        counts[-1] += 1
    number = 0
    result = ['<PipeStressExport xmlns="http://aveva.com/pipeStress116.xsd">']
    for b, items in enumerate(assignments):
        result.append(f'<Branch><Branchname>SYNTH-{b:03d}</Branchname>')
        x, y = 0, b*10000
        made = 0
        def node(kind, ref, endpoint, pos, extra='', positive=True):
            nonlocal number, made
            number += 1
            made += 1
            result.append(f'<Node><NodeNumber>{number if positive else -1}</NodeNumber>'
                          f'<ComponentType>{kind}</ComponentType><ComponentRefNo>{ref}</ComponentRefNo>'
                          f'<Endpoint>{endpoint}</Endpoint><Position>{pos} {y} 0</Position>'
                          f'<OutsideDiameter>100</OutsideDiameter>{extra}</Node>')
        for i, is_blocked in items:
            prefix = f'{"BLOCK" if is_blocked else "SHORT"}-{i:03d}'
            length = rng.randint(1, 6)
            node('PIPE', prefix+'-P', 1, x)
            node('PIPE', prefix+'-P', 2, x+200)
            node('GASK', prefix, 1, x+200, '<Restraint>X</Restraint>' if is_blocked else '', False)
            node('RIGID', prefix, 2, x+200+length)
            node('FLAN', prefix+'-F', 1, x+200+length, positive=False)
            node('RIGID', prefix+'-F', 2, x+286+length)
            x += 286+length
        while made+2 <= counts[b]:
            ref = f'FILL-{b}-{made}'
            node('PIPE', ref, 1, x)
            x += 500
            node('PIPE', ref, 2, x)
        if made < counts[b]:
            node('BRAN', f'BOUNDARY-{b}', 1, x, '<ConnectionType>CLOS</ConnectionType>', False)
        result.append('</Branch>')
    result.append('</PipeStressExport>')
    return ('\n'.join(result)+'\n').encode('utf-8')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--seed', type=int, default=116)
    p.add_argument('--branches', type=int, default=41)
    p.add_argument('--owners', type=int, default=89)
    p.add_argument('--blocked', type=int, default=40)
    p.add_argument('--nodes', type=int, default=1654)
    a = p.parse_args()
    with a.output.open('xb') as f:
        f.write(generate(a.seed, a.branches, a.owners, a.blocked, a.nodes))


if __name__ == '__main__':
    main()
