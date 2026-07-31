#!/usr/bin/env python3
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
checks={'regionalliga':34,'u23':30,'u21':30,'u19':30}
failed=[]
for key,minimum in checks.items():
    data=json.loads((ROOT/'data'/f'{key}.json').read_text(encoding='utf-8'))
    count=len(data.get('games',[]))
    print(f'{key}: {count} Termine (Minimum {minimum})')
    if count<minimum: failed.append(f'{key}: nur {count}/{minimum}')
# Cup must not be silently discarded when present in source data.
rl=json.loads((ROOT/'data'/'regionalliga.json').read_text(encoding='utf-8'))
print('Brandenburg-Pokal-Termine:', sum('pokal' in str(g.get('competition','')).lower() for g in rl.get('games',[])))
if failed:
    print('Release-Pruefung fehlgeschlagen: '+'; '.join(failed), file=sys.stderr)
    sys.exit(1)
