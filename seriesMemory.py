"""Kézzel karbantartott sorozatmemória betöltése; a modell nem írja felül."""

import json
from pathlib import Path

DEFAULT_MEMORY_PATH = Path(__file__).with_name('series_memory.json')


def load_series_memory(path=DEFAULT_MEMORY_PATH):
    memory = json.loads(Path(path).expanduser().read_text(encoding='utf-8'))
    if not isinstance(memory, dict) or memory.get('schema_version') != 1:
        raise ValueError('Ismeretlen sorozatmemória-formátum.')
    if memory.get('status') not in ('draft', 'ready'):
        raise ValueError('A memória státusza draft vagy ready legyen.')
    if not isinstance(memory.get('names'), list) or not all(isinstance(n, str) and n.strip() for n in memory['names']):
        raise ValueError('Hibás névlista a sorozatmemóriában.')
    if not isinstance(memory.get('nicknames'), dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in memory['nicknames'].items()):
        raise ValueError('Hibás becenévlista a sorozatmemóriában.')
    if not isinstance(memory.get('relationships'), list):
        raise ValueError('Hibás kapcsolatlista a sorozatmemóriában.')
    for relationship in memory['relationships']:
        if (not isinstance(relationship, dict) or not isinstance(relationship.get('names'), list)
                or not relationship['names']
                or not all(isinstance(n, str) and n.strip() for n in relationship['names'])
                or not isinstance(relationship.get('relationship'), str)
                or not relationship['relationship'].strip()):
            raise ValueError('Hibás kapcsolat a sorozatmemóriában.')
    summary = memory.get('story_summary')
    if not isinstance(summary, str):
        raise ValueError('A történeti összefoglaló szöveg legyen.')
    if summary.strip() and not 150 <= len(summary.split()) <= 250:
        raise ValueError('A történeti összefoglaló 150–250 szavas legyen.')
    if memory['status'] == 'ready' and not summary.strip():
        raise ValueError('A kész sorozatmemóriához történeti összefoglaló is szükséges.')
    return memory
