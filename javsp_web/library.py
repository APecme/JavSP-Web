"""Overview combines scrape history with the actual bound media libraries."""
import re
import copy
from . import media, task_store
from .avatars import avatar_directory


def studio_prefix(identifier):
    match = re.search(r'(?<![A-Za-z])[A-Za-z]+', str(identifier or ''))
    return match[0].upper() if match else ''


def _keys(item, by, libraries):
    if by == 'producer':
        return [studio_prefix(item.get('progress', {}).get('metadata', {}).get('dvdid'))]
    if by == 'library':
        return list(dict.fromkeys((item.get('library_keys') or []) + task_store._group_values(item, by, libraries)))
    return task_store._group_values(item, by, libraries)


def _folder(item):
    return task_store.normalize_path(item.get('progress', {}).get('output', {}).get('save_dir'))


def _identifier(item):
    value = str(item.get('progress', {}).get('metadata', {}).get('dvdid') or '').strip().upper()
    fc2 = re.fullmatch(r'FC2[-_ ]*(?:PPV[-_ ]*)?(\d+)', value)
    return 'FC2-' + fc2[1] if fc2 else value


def _mount_relative(folder):
    # Ignore only one container mount component, retaining category and the full
    # film directory. A bare ID or filename is insufficient evidence of identity.
    if not folder.startswith('/') or folder.startswith('//'):
        return ''
    parts = folder.strip('/').split('/')
    return '/'.join(parts[1:]) if len(parts) >= 4 and all(parts) else ''


def _merge_keys(item, movie):
    item['library_keys'] = list(dict.fromkeys(item.get('library_keys', []) + movie.get('library_keys', [])))
    reference = movie.get('media_reference')
    if reference:
        item.setdefault('media_reference', reference)
        refs = item.setdefault('media_references', [item['media_reference']])
        if reference not in refs:
            refs.append(reference)


def _collection(libraries):
    local = task_store.page(limit=1000000000, view='overview')
    remote, errors = media.catalog_movies()
    items, aliases, histories = [], {}, {}
    # Repeated scrapes of the same input and preset can rename the output folder
    # after translation. Keep one representative and every task ID/folder alias.
    for item in sorted(copy.deepcopy(local['items']), key=lambda x: (x.get('status') == 'succeeded', str(x.get('created_at') or ''), str(x.get('id') or '')), reverse=True):
        folder, identifier = _folder(item), _identifier(item)
        source = task_store.normalize_path(item.get('input_directory'))
        key = (source, item.get('preset_id') or item.get('preset_name'), identifier, folder.rsplit('/', 1)[0])
        existing = histories.get(key) if source and folder and identifier else None
        if existing is not None:
            existing['task_ids'] = list(dict.fromkeys(existing.get('task_ids', [existing['id']]) + item.get('task_ids', [item['id']])))
            aliases[existing['id']].add(folder)
        else:
            items.append(item)
            aliases[item['id']] = {folder} if folder else set()
            if source and folder and identifier:
                histories[key] = item
    paths, relative = {}, {}
    by_id = {item['id']: item for item in items}
    for item in items:
        for folder in aliases[item['id']]:
            paths.setdefault(folder, set()).add(item['id'])
            suffix = _mount_relative(folder)
            if suffix and _identifier(item):
                relative.setdefault((_identifier(item), suffix), set()).add(item['id'])
    mappings, seen_remote, occupied = media.list_path_mappings(), {}, {}
    for movie in copy.deepcopy(remote):
        ref = movie.get('media_reference') or {}
        remote_key = (ref.get('server_id'), ref.get('item_id'))
        if all(remote_key) and remote_key in seen_remote:
            _merge_keys(seen_remote[remote_key], movie)
            continue
        folder = _folder(movie)
        matches = set()
        for candidate in media._local_roots(folder, mappings):
            matches.update(paths.get(task_store.normalize_path(candidate), set()))
        if not matches and _identifier(movie):
            matches = relative.get((_identifier(movie), _mount_relative(folder)), set())
        target = by_id[next(iter(matches))] if len(matches) == 1 else None
        if target is not None:
            current = target.get('media_reference') or {}
            slot = (target['id'], ref.get('server_id'), folder)
            if ((current and current.get('server_id') != ref.get('server_id'))
                    or (slot in occupied and occupied[slot] != ref.get('item_id'))
                    or (_identifier(target) and _identifier(movie) and _identifier(target) != _identifier(movie))):
                target = None
        if target is None:
            target = movie
            items.append(target)
        else:
            occupied[slot] = ref.get('item_id')
        _merge_keys(target, movie)
        if all(remote_key):
            seen_remote[remote_key] = target
    return items, local['metrics'], errors


def overview_groups(by, offset, limit, query, libraries, actress_scope='existing'):
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
    if by == 'actress':
        for portrait in avatar_directory().values():
            if portrait.get('source') != 'gfriends':
                continue
            name = str(portrait.get('name') or '').strip()
            if not name:
                continue
            if actress_scope == 'all':
                groups.setdefault(name, {'key': name, 'name': name, 'count': 0, 'covers': []})
            if name in groups:
                groups[name]['avatar_id'] = portrait['id']
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
