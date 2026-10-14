"""Overview combines scrape history with the actual bound media libraries."""
import re
from . import media, task_store


def studio_prefix(identifier):
    match = re.search(r'(?<![A-Za-z])[A-Za-z]+', str(identifier or ''))
    return match[0].upper() if match else ''


def _keys(item, by, libraries):
    if by == 'producer':
        return [studio_prefix(item.get('progress', {}).get('metadata', {}).get('dvdid'))]
    if by == 'library':
        return list(dict.fromkeys((item.get('library_keys') or []) + task_store._group_values(item, by, libraries)))
    return task_store._group_values(item, by, libraries)


def _collection(libraries):
    local = task_store.page(limit=1000000000, view='overview')
    remote, errors = media.catalog_movies()
    import copy
    items = copy.deepcopy(local['items'])
    # Merge only exact paths. Same identifier may legitimately have multiple editions.
    paths = {}
    mappings = media.list_path_mappings()
    for item in items:
        folder = task_store.normalize_path(item.get('progress', {}).get('output', {}).get('save_dir'))
        if folder:
            paths.setdefault(folder, []).append(item)
    for movie in remote:
        folder = movie.get('progress', {}).get('output', {}).get('save_dir') or ''
        matched = []
        for candidate in media._local_roots(folder, mappings):
            matched.extend(paths.get(task_store.normalize_path(candidate), []))
        if len(matched) == 1:
            task = matched[0]
            if not task.get('media_reference') or task['media_reference'] == movie['media_reference']:
                task['library_keys'] = list(dict.fromkeys(task.get('library_keys', []) + movie['library_keys']))
                task['media_reference'] = movie['media_reference']
            else:
                items.append(movie)
        else:
            items.append(movie)
    return items, local['metrics'], errors


def overview_groups(by, offset, limit, query, libraries):
    items, metrics, errors = _collection(libraries)
    groups = {lib['key']: {'key': lib['key'], 'name': lib['name'], 'count': 0, 'covers': []} for lib in libraries} if by == 'library' else {}
    everything = {'count': len(items), 'covers': []}
    for item in items:
        cover = task_store._cover_ref(item) if item.get('cover_count') else None
        if cover and len(everything['covers']) < 9:
            everything['covers'].append(cover)
        for key in _keys(item, by, libraries):
            group = groups.setdefault(key, {'key': key, 'name': key or task_store._UNKNOWN_GROUP.get(by, '未分类'), 'count': 0, 'covers': []})
            group['count'] += 1
            if cover and len(group['covers']) < 9:
                group['covers'].append(cover)
    values = list(groups.values()) if by != 'all' else []
    if by == 'year':
        values.sort(key=lambda group: group['key'], reverse=True)
    elif by != 'library':
        values.sort(key=lambda group: (not group['key'], -group['count'], group['name'].casefold()))
    if query:
        values = [group for group in values if query.casefold() in group['name'].casefold()]
    total = len(values)
    offset = min(offset, max(0, ((total - 1) // limit) * limit))
    return {'by': by, 'groups': values[offset:offset + limit], 'total': total, 'offset': offset, 'limit': limit,
            'all': everything, 'metrics': metrics, 'warnings': errors, 'libraries_available': bool(libraries)}


def overview_page(limit, offset, libraries, group_by='', group='', query='', sort='created_at', direction='desc'):
    items, metrics, errors = _collection(libraries)
    if group_by:
        items = [item for item in items if group in _keys(item, group_by, libraries)]
    if query:
        needle = query.casefold()
        items = [item for item in items if needle in ' '.join(str(value) for value in [
            item.get('input_directory'), item.get('title'), item.get('progress', {}).get('metadata')]).casefold()]
    items.sort(key=lambda item: str(item.get('progress', {}).get('metadata', {}).get('publish_date') or '') if sort == 'publish_date'
               else str(item.get('created_at') or ''), reverse=direction != 'asc')
    total = len(items)
    offset = min(offset, max(0, ((total - 1) // limit) * limit))
    return {'items': items[offset:offset + limit], 'total': total, 'limit': limit, 'offset': offset, 'metrics': metrics, 'warnings': errors}
