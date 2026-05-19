# Shared: Registry Fetch

Resolve the skill registry source. Try sources in order — stop at the first successful one.

## 1a. All configured registries (preferred)

Fetch from ALL configured registries in `~/.prism/registries.json`, merge results, and tag each skill with its source registry name:

```python
python3 -c "
import json, os, sys
import urllib.request, urllib.error
reg_path = os.path.expanduser('~/.prism/registries.json')
cache_dir = os.path.expanduser('~/.prism/cache')
try:
    with open(reg_path) as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    data = {'registries': []}
# Fall back to config.json migration
if not data.get('registries'):
    cfg_path = os.path.expanduser('~/.prism/config.json')
    try:
        with open(cfg_path) as f:
            cfg = json.load(f)
        url = cfg.get('registry_url', '')
        if url:
            data = {'registries': [{'name': 'default', 'url': url, 'token': ''}]}
    except: pass
all_skills = []
registry_reached = False
for reg in data.get('registries', []):
    name = reg['name']
    url = reg['url'].rstrip('/')
    token = os.environ.get('REGISTRY_TOKEN', reg.get('token', ''))
    cache_path = os.path.join(cache_dir, f'{name}.json')
    cached = None
    stored_etag = None
    try:
        if os.path.exists(cache_path):
            with open(cache_path) as f:
                cached = json.load(f)
            stored_etag = cached.get('_etag')
    except: pass
    try:
        headers = {'User-Agent': 'Prism/1.0'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        if stored_etag:
            headers['If-None-Match'] = stored_etag
        req = urllib.request.Request(f'{url}/api/skills/registry', headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                fetched = json.loads(resp.read().decode())
                new_etag = resp.headers.get('ETag')
            if fetched.get('skills'):
                os.makedirs(cache_dir, exist_ok=True)
                cache_data = dict(fetched)
                if new_etag:
                    cache_data['_etag'] = new_etag
                tmp = cache_path + '.tmp'
                with open(tmp, 'w') as f: json.dump(cache_data, f)
                os.rename(tmp, cache_path)
        except urllib.error.HTTPError as e:
            if e.code == 304 and cached is not None:
                fetched = cached  # 304 Not Modified — use cache
            else:
                raise
        registry_reached = True
        for s in fetched.get('skills', []):
            s['_registry'] = name
            all_skills.append(s)
    except Exception as e:
        print(f'Warning: could not reach {name}: {e}', file=sys.stderr)
        if cached:
            registry_reached = True
            for s in cached.get('skills', []):
                s['_registry'] = name
                all_skills.append(s)
if all_skills:
    print(json.dumps(all_skills))
elif registry_reached:
    print('REGISTRY_EMPTY')
else:
    print('NO_REGISTRIES')
"
```

If the result is valid JSON (an array of skills), use it as the skills list. Each skill has a `_registry` field indicating its source.

If the result is `REGISTRY_EMPTY`, the registry was reached but has no skills yet. Skip fallback sources and proceed to the calling skill's next step.

If the result is `NO_REGISTRIES`, no registry was configured or reachable. Proceed to fallback sources below.

## 1b. Local skill-registry.json (fallback)

Check if `skill-registry.json` exists in the current project directory:

```bash
test -f skill-registry.json && echo "FOUND" || echo "NOT_FOUND"
```

If found, read it and use its `skills` array. Note in the output: "Using local skill-registry.json (no remote registry configured or reachable)."

## 1c. Local _analysis/ skills (fallback)

Check if `_analysis/extracted_skills_codebase/` has skill directories with `plugin.json`:

```bash
ls _analysis/extracted_skills_codebase/*/plugin.json 2>/dev/null | head -20
```

If found, build a temporary registry from the local `plugin.json` files:

```python
python3 << 'PYEOF'
import json, os

base = "_analysis/extracted_skills_codebase"
skills = []
for name in sorted(os.listdir(base)):
    plugin_path = os.path.join(base, name, "plugin.json")
    if os.path.isfile(plugin_path):
        with open(plugin_path) as f:
            skills.append(json.load(f))
print(f"Built local registry from {len(skills)} extracted skill(s)")
PYEOF
```

Note in the output: "Using local extracted skills (no remote registry or skill-registry.json available)."

## 1d. No source available

If none of the above sources are available, tell the user:

> **No skill registry available.** Options:
> 1. Add a registry: `prism registry add NAME --url URL --token TOKEN`
> 2. Place `skill-registry.json` in the project root
> 3. Run `/extract-skills` (Claude Code) or `@extract-skills` (Cursor) to create local skills

Then stop.
