"""The rule of the commit gates for the API pages of the typescript profile: is_api(path).

The gate of agent_gest_git_skills loads this file from the parent commit and calls is_api on each changed path,
for the alias @api of required.txt. It runs with the standard library only, on Python 3.9 or later, under
python -I -B, in the top of the repository, and it writes nothing. It reads git with git show and git ls-files.

is_api is True when the path is a source file of the API pages, as api-check of the tool api reads them. The project
needs the tool api and the docs role, as .agents/stack.json records them. Otherwise is_api is False for every path.
The entry comes from the TypeScript sections of the key api of docs/_smalldocs.yml, or else from the default of
api-check: the index of src, or each code file in src. From an entry file, the rule follows the relative imports and
re-exports, so a file that the entry reaches counts. An entry folder holds files that count. Test files, declaration
files, the files of .agents/generated.txt of the parent commit and the files of the tool folders never count. A
config that the rule cannot read gives False for every path.
"""
import json
import os
import posixpath
import re
import subprocess

RECORD = '.agents/stack.json'
DOCS_CONFIG = 'docs/_smalldocs.yml'
GENERATED = '.agents/generated.txt'
CODE = ('.ts', '.tsx', '.mts', '.cts')
DECLARATIONS = ('.d.ts', '.d.mts', '.d.cts')
TESTS = tuple('.test' + suffix for suffix in CODE)
TOOL_FOLDERS = ('.agents/', '.claude/', '.codex/')
ENTRIES = ('src/index.ts', 'src/index.tsx', 'src/index.mts', 'src/index.cts')
SOURCE = 'src'
# A relative module name after from, or in import "...", import("...") and require("..."), as TypeScript writes it.
SPECIFIER = re.compile(r'''(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)['"](\.{1,2}/[^'"]*|\.{1,2})['"]''')
# The endings that a relative module name can stand for, as moduleResolution node16 and bundler resolve them.
ENDINGS = {'.js': ('.ts', '.tsx'), '.jsx': ('.tsx',), '.mjs': ('.mts',), '.cjs': ('.cts',)}
# The key of a YAML pair, plain or in quotes, and its colon.
PAIR = re.compile(r'''("[^"]*"|'[^']*'|[^\s'"\[\]{}#,&*!|>-][^:]*?|-[^\s:][^:]*?)\s*:(?:\s+|$)''')
# The YAML that the rule does not read: anchors, aliases, tags and block scalars.
UNREAD = ('&', '*', '!', '|', '>', '%', '@', '`')
NULLS = ('', '~', 'null', 'Null', 'NULL')

_CACHE = {}


def _read(path):
    """The text of the file PATH, or None when it cannot be read."""
    try:
        with open(path, encoding='utf-8', errors='replace') as handle:
            return handle.read()
    except OSError:
        return None


def _git(*args):
    """The output of git ARGS, or None when git fails. It takes no optional lock, so it writes no index."""
    try:
        run = subprocess.run(['git', *args], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                             env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'), check=False)
    except OSError:
        return None
    return run.stdout if run.returncode == 0 else None


def _code(path):
    """True when PATH, relative to the top, is a code file that can feed the API pages."""
    return (path.endswith(CODE) and not path.endswith(DECLARATIONS) and not path.endswith(TESTS)
            and not path.startswith(TOOL_FOLDERS) and 'node_modules' not in path.split('/')[:-1])


def _generated():
    """The files that the patterns of .agents/generated.txt of the parent commit name, as steps.py reads them: git
    matches each pattern as a pathspec with the magic word glob. Raises ValueError when git cannot read a pattern."""
    text = _git('show', 'HEAD:./' + GENERATED) or ''
    patterns = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith('#')]
    if not patterns:
        return set()
    out = _git('ls-files', '-z', '--cached', '--others', '--exclude-standard', '--',
               *[':(glob)' + pattern.lstrip('/') for pattern in patterns])
    if out is None:
        raise ValueError('git cannot read the patterns of ' + GENERATED)
    return set(filter(None, out.split('\0')))


def _uncomment(text):
    """TEXT without its YAML comment: a # outside quotes, at the start or after a space."""
    quote = ''
    for i, char in enumerate(text):
        if quote:
            quote = '' if char == quote else quote
        elif char in '"\'' and (i == 0 or text[i - 1] in ' \t[{,:'):
            quote = char
        elif char == '#' and (i == 0 or text[i - 1] in ' \t'):
            return text[:i]
    return text


def _depth(text):
    """The number of flow brackets that TEXT opens and does not close, outside quotes."""
    depth, quote = 0, ''
    for i, char in enumerate(text):
        if quote:
            quote = '' if char == quote else quote
        elif char in '"\'' and (i == 0 or text[i - 1] in ' \t[{,:'):
            quote = char
        elif char in '[{':
            depth += 1
        elif char in ']}':
            depth -= 1
    return depth


def _lines(text):
    """The lines of the YAML TEXT that hold data, as pairs of indent and text, without comments. A flow list or map
    over several lines becomes one line."""
    lines = []
    for raw in text.splitlines():
        line = _uncomment(raw.rstrip('\r')).rstrip()
        if not line.strip() or line in ('---', '...'):
            continue
        indent = len(line) - len(line.lstrip())
        if '\t' in line[:indent]:
            raise ValueError('a tab in the indent')
        if lines and _depth(lines[-1][1]) > 0:
            lines[-1] = (lines[-1][0], lines[-1][1] + ' ' + line.strip())
        else:
            lines.append((indent, line.strip()))
    if lines and _depth(lines[-1][1]) != 0:
        raise ValueError('a flow list or map that does not close')
    return lines


def _scalar(text):
    """The YAML scalar TEXT without its quotes, or None for a null."""
    text = text.strip()
    if text[:1] in ('"', "'"):
        if len(text) < 2 or text[-1] != text[0]:
            raise ValueError(text)
        return text[1:-1].replace("''", "'") if text[0] == "'" else text[1:-1]
    if text.startswith(UNREAD):
        raise ValueError(text)
    return None if text in NULLS else text


def _flow(text):
    """The items of a YAML flow list or map TEXT, such as [a, b] or {a: 1}, as a list of strings, split at the commas
    that are not in quotes or in brackets."""
    items, depth, quote, start = [], 0, '', 0
    for i, char in enumerate(text):
        if quote:
            quote = '' if char == quote else quote
        elif char in '"\'' and (i == 0 or text[i - 1] in ' \t[{,:'):
            quote = char
        elif char in '[{':
            depth += 1
        elif char in ']}':
            depth -= 1
        elif char == ',' and depth == 0:
            items.append(text[start:i])
            start = i + 1
    items.append(text[start:])
    return [item.strip() for item in items if item.strip()]


def _value(text):
    """A YAML value TEXT on one line: a flow list as a list, a flow map as a dict, or a scalar."""
    text = text.strip()
    if text.startswith('['):
        if not text.endswith(']'):
            raise ValueError(text)
        return [_value(item) for item in _flow(text[1:-1])]
    if text.startswith('{'):
        if not text.endswith('}'):
            raise ValueError(text)
        out = {}
        for item in _flow(text[1:-1]):
            pair = PAIR.match(item + ' ')
            if not pair:
                raise ValueError(item)
            out[_scalar(pair.group(1))] = _value(item[pair.end():])
        return out
    return _scalar(text)


def _is_item(text):
    """True when the line TEXT starts an item of a block list."""
    return text == '-' or text.startswith(('- ', '-\t'))


def _item(lines):
    """The YAML value of the list item LINES: a value on one line, or a block."""
    if not lines:
        return None
    if len(lines) == 1 and not PAIR.match(lines[0][1]) and not _is_item(lines[0][1]):
        return _value(lines[0][1])
    return _block(lines, lines[0][0])


def _block(lines, indent):
    """The YAML block of LINES, pairs of indent and text, that starts at INDENT: a list of items or a map."""
    if _is_item(lines[0][1]):
        items = []
        for depth, text in lines:
            if depth == indent and _is_item(text):
                content = text[1:]
                spaces = len(content) - len(content.lstrip())
                items.append([(indent + 1 + spaces, content.strip())] if content.strip() else [])
            elif depth > indent:
                items[-1].append((depth, text))
            else:
                raise ValueError(text)
        return [_item(item) for item in items]
    out = {}
    i = 0
    while i < len(lines):
        depth, text = lines[i]
        pair = PAIR.match(text)
        if not pair or depth != indent:
            raise ValueError(text)
        key, rest = _scalar(pair.group(1)), text[pair.end():].strip()
        inner = []
        i += 1
        # A block list under a key can have the indent of the key, as PyYAML writes it.
        while i < len(lines) and (lines[i][0] > indent or not rest and lines[i][0] == indent
                                  and _is_item(lines[i][1]) and (not inner or inner[0][0] == indent)):
            inner.append(lines[i])
            i += 1
        if rest and inner:
            raise ValueError(text)
        out[key] = _value(rest) if rest else (_block(inner, inner[0][0]) if inner else None)
    return out


def _api_settings():
    """The value of the key api of docs/_smalldocs.yml, or None when the file or the key is not there.

    It reads the subset of YAML that the configs of smalldocs use: maps, lists, flow lists and flow maps over one or
    more lines, plain or quoted scalars, and comments. Anything else raises ValueError. As with PyYAML, the last key
    api counts.
    """
    text = _read(DOCS_CONFIG)
    if text is None:
        return None
    lines = _lines(text)
    value = None
    for i, (depth, line) in enumerate(lines):
        pair = PAIR.match(line)
        if depth == 0 and pair and _scalar(pair.group(1)) == 'api':
            inner = []
            for after in lines[i + 1:]:
                if after[0] == 0 and not _is_item(after[1]):
                    break
                inner.append(after)
            value = _block([(0, line)] + inner, 0)['api']
    return value


def _relative(path):
    """The entry PATH of the docs config, relative to the top, as steps.py resolves it, or None when it is outside."""
    full = os.path.realpath(os.path.join('docs', path))
    relative = os.path.relpath(full, os.path.realpath('.')).replace(os.sep, '/')
    return None if relative == '..' or relative.startswith('../') else relative


def _entries(generated):
    """The entry paths of the API, relative to the top. Raises ValueError when the config cannot be read."""
    settings = _api_settings()
    sections = settings if isinstance(settings, list) else [settings]
    typescript = [section for section in sections if isinstance(section, dict)
                  and section.get('language') == 'typescript']
    entries = []
    for section in typescript:
        entry = section.get('entry')
        for path in (entry if isinstance(entry, list) else [entry]):
            if isinstance(path, str) and path and _relative(path):
                entries.append(_relative(path))
    if entries:
        return entries
    # Without a TypeScript section, or with no entry in it, the entry is the default of api-check.
    for index in ENTRIES:
        if os.path.isfile(index) and index not in generated:
            return [index]
    return [SOURCE]


def _resolve(origin, name):
    """The code file, relative to the top, that the relative module NAME in the file ORIGIN names, or None."""
    base = posixpath.normpath(posixpath.join(posixpath.dirname(origin), name))
    stem, ending = posixpath.splitext(base)
    tries = [stem + new for new in ENDINGS.get(ending, ())] + [base + suffix for suffix in CODE]
    tries += [posixpath.join(base, 'index' + suffix) for suffix in CODE] + [base]
    for path in tries:
        if _code(path) and os.path.isfile(path):
            return path
    return None


def _reached(entries):
    """The code files that ENTRIES reach: an entry folder holds them, and an entry file reaches the files of its
    relative imports and re-exports, and theirs."""
    found, folders, todo = set(), [], []
    for entry in entries:
        if entry == '.':
            folders.append('')
        elif os.path.isdir(entry):
            folders.append(entry.rstrip('/') + '/')
        else:
            todo.append(entry)
    while todo:
        path = todo.pop()
        if path in found:
            continue
        found.add(path)
        for name in SPECIFIER.findall(_read(path) or ''):
            target = _resolve(path, name)
            if target and target not in found:
                todo.append(target)
    return found, folders


def _rule():
    """The files and the folders of the API, from the current state of the project, computed once. None when the
    project has no API to check, or when its config cannot be read."""
    if 'rule' not in _CACHE:
        rule = None
        try:
            with open(RECORD, encoding='utf-8') as handle:
                record = json.load(handle)
            tools = record.get('tools') if isinstance(record, dict) else None
            choices = record.get('choices') if isinstance(record, dict) else None
            on = (isinstance(tools, list) and 'typescript:api' in tools and isinstance(choices, dict)
                  and choices.get('docs') is True)
            if on:
                generated = _generated()
                files, folders = _reached(_entries(generated))
                rule = (files, folders, generated)
        except (OSError, ValueError, KeyError, TypeError, IndexError, RecursionError):
            rule = None
        _CACHE['rule'] = rule
    return _CACHE['rule']


def is_api(path):
    """True when PATH, relative to the top of the repository, is a source file of the API pages."""
    try:
        path = str(path).replace('\\', '/')
        if posixpath.isabs(path):
            path = os.path.relpath(path, os.path.realpath('.')).replace(os.sep, '/')
        path = posixpath.normpath(path)
        if not _code(path) or path.startswith('../'):
            return False
        rule = _rule()
        if rule is None:
            return False
        files, folders, generated = rule
        if path in generated:
            return False
        return path in files or any(path.startswith(folder) for folder in folders)
    except Exception:  # noqa: BLE001 - a rule of the gate must never stop the gate
        return False
