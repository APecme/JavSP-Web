"""Merge source observations into one wall without inventing source metadata."""
from __future__ import annotations

import copy
import re


def merge_items(groups, sort):
    merged = {}
    for group in groups:
        for raw in group.get('items', []):
            item = copy.deepcopy(raw)
            identifier = re.sub(r'[^A-Z0-9]', '', item.get('identifier', '').upper())
            # Only merge known identifier namespaces; ambiguous source IDs stay local.
            namespace = 'fc2' if item.get('identifier', '').upper().startswith('FC2-') else 'dvd'
            trusted = re.fullmatch(r'(?:FC2[-_]\d+|[A-Z]{2,10}[-_]?\d{1,7})', item.get('identifier', '').upper())
            source_local = item.get('identifier', '').upper().startswith('JAVU-')
            key = namespace + ':' + identifier if trusted and not source_local else item['source_id'] + ':' + identifier
            observation = {'source_id': item['source_id'], 'source_name': item['source_name'],
                           'url': item['url'], 'rank': item.get('rank'), 'label': group['label'],
                           'fetched_at': group.get('fetched_at', ''), 'stale': group.get('stale', False)}
            if key not in merged:
                item.update(id=key, sources=[], actors=item.get('actors', []), tags=item.get('tags', []),
                            studio=item.get('studio', ''), seller=item.get('seller', ''),
                            score=item.get('score'), score_scale=item.get('score_scale'),
                            views=item.get('views'), favorites=item.get('favorites'),
                            comments=item.get('comments'), duration=item.get('duration', ''),
                            date_kind=item.get('date_kind', '来源日期'))
                merged[key] = item
            target = merged[key]
            if not any(s['source_id'] == observation['source_id'] for s in target['sources']):
                target['sources'].append(observation)
            if target['category'] != item['category']:
                target['category'] = 'unknown'
            for field in ('actors', 'tags'):
                target[field] = list(dict.fromkeys(target.get(field, []) + item.get(field, [])))[:20]
            for field in ('studio', 'seller', 'score', 'score_scale', 'views', 'favorites', 'comments', 'duration', 'date', 'cover'):
                if target.get(field) in (None, '', []):
                    target[field] = item.get(field)
    items = list(merged.values())
    for item in items:
        item['rank'] = min((s['rank'] for s in item['sources'] if s.get('rank')), default=None)
    if sort == 'latest':
        items.sort(key=lambda i: (i.get('date') or '', i['identifier']), reverse=True)
    else:
        # Rank-first interleave; NOT a synthetic score or nationwide sales ranking.
        items.sort(key=lambda i: (min((s['rank'] for s in i['sources'] if s.get('rank')), default=10**9),
                                  i['identifier']))
    return items
