from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'javsp_web' / 'web'
DOCS = ROOT / 'docs'


def build():
    assets = ['app.js', 'app.css', 'overrides.css', 'ai.js', 'ai-markdown.js']
    inputs = [WEB / 'index.html', *(WEB / 'assets' / name for name in assets), ROOT / 'javsp_web' / 'ai.py',
              ROOT / 'vendor' / 'JavSP' / 'config.yml', DOCS / 'demo-mock.js', DOCS / 'demo.css',
              Path(__file__), *sorted((ROOT / 'javsp_web' / 'skills').glob('*/SKILL.md'))]
    revision = hashlib.sha256(b''.join(path.read_text(encoding='utf-8').encode('utf-8') for path in inputs)).hexdigest()[:12]
    tree = ast.parse((ROOT / 'javsp_web' / 'ai.py').read_text(encoding='utf-8'))
    prompt = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == 'DEFAULT_SYSTEM_PROMPT' for target in node.targets))
    settings_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'AISettings')
    settings = {}
    for field in settings_class.body:
        if not isinstance(field, ast.AnnAssign) or field.target.id == 'model_config':
            continue
        value = field.value
        if isinstance(value, ast.Call):
            value = next(keyword.value for keyword in value.keywords if keyword.arg == 'default')
        settings[field.target.id] = prompt if isinstance(value, ast.Name) else ast.literal_eval(value)
    settings.update(enabled=True, model='演示模型（固定示例回复）', base_url='https://llm.example.com/v1',
                    default_system_prompt=prompt, has_api_key=False)
    settings.pop('api_key', None)
    skills = []
    for path in sorted((ROOT / 'javsp_web' / 'skills').glob('*/SKILL.md')):
        source = path.read_text(encoding='utf-8')
        metadata = yaml.safe_load(source.split('---', 2)[1])
        skills.append({'name': metadata['name'], 'description': metadata['description'], 'source': source, 'kind': 'builtin'})
    config = yaml.safe_load((ROOT / 'vendor' / 'JavSP' / 'config.yml').read_text(encoding='utf-8'))
    config['scanner']['input_directory'] = '/video/待整理'
    config['crawler']['ai_enabled'] = True
    seed = {'version': f'demo.{revision}', 'revision': revision, 'ai': settings, 'skills': skills, 'config': config,
            'config_yaml': yaml.safe_dump(config, allow_unicode=True, sort_keys=False)}
    (DOCS / 'demo-seed.js').write_text('window.JavspDemoSeed = ' + json.dumps(seed, ensure_ascii=False) + ';\n', encoding='utf-8')
    for name in assets:
        destination = 'demo-app.js' if name == 'app.js' else name
        (DOCS / 'assets' / destination).write_bytes((WEB / 'assets' / name).read_bytes())
    document = (WEB / 'index.html').read_text(encoding='utf-8')
    document = document.replace('/assets/', 'assets/').replace('__ASSET_VERSION__', revision)
    document = document.replace('assets/app.js?', 'assets/demo-app.js?')
    document = document.replace('<title>JavSP WEB</title>', '<title>交互示例 | JavSP WEB</title>')
    document = document.replace('<body>', '<body class="demo-mode">\n<script src="demo-seed.js?v=' + revision + '"></script>\n<script src="demo-mock.js?v=' + revision + '"></script>')
    document = document.replace('<main class="main">', '<main class="main"><aside class="demo-notice" role="note"><strong>交互示例 · ' + seed['version'] + '</strong><span>使用当前程序界面与模拟数据，不连接模型、不访问影片文件。更改仅保留到刷新；请勿填写真实密钥。</span><a href="docs.html">使用教程 ↗</a></aside>')
    document = document.replace('</head>', '<link rel="stylesheet" href="demo.css?v=' + revision + '">\n</head>')
    (DOCS / 'demo.html').write_text(document, encoding='utf-8')
    print('Generated demo:', seed['version'])


if __name__ == '__main__':
    build()
