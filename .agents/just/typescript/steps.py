"""The helper of the steps of the typescript profile: test, integration, coverage-check, docstring-check and
test-paths.

The recipes in this folder run it with uv and Python 3.11 or later. Its commands are coverage [MODULE], docs,
fresh NAME MODULE, ran NAME [ARG...], begin NAME [ARG...], stamp NAME, build NAME MODULE COUNT and
test-paths FILE.... NAME is test or integration, and for build also cov. MODULE is the module file of the recipes.
begin, stamp, fresh and ran tie each coverage report to the run ID JLOG_RUN of the root Justfile and to the worktree
tree, so that coverage-check reads the reports of test and integration only from the same run. coverage-check runs
diff-cover with uv. docstring-check runs eslint with npm exec, and node comes from the nodejs-wheel package, as in
the recipes.

The lists .agents/generated.txt and .agents/coverage-exclude.txt come from the parent commit, through
git show HEAD:./PATH, so a commit cannot exempt its own code. With no parent, both lists are empty. git matches
their patterns, as pathspecs with the magic word glob. Every path is relative to the current folder, the top of
the project, which can be a subfolder of the git repository.
"""
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ElementTree

DIFF_COVER = 'diff-cover==11.0.1'
NODE = ['uvx', '--quiet', '--from', 'nodejs-wheel==24.*']
# The packages of docstring-check. npm exec installs them into its cache, not into the project, because the parser
# of typescript-eslint needs a typescript older than 6.1, and the project has typescript 7.
ESLINT = ('eslint@10.14.0', 'eslint-plugin-jsdoc@65.4.0', '@typescript-eslint/parser@8.72.1', 'typescript@6.0.3')
ESLINT_CONFIG = Path(__file__).resolve().parent / 'docstring.eslint.mjs'
GENERATED = '.agents/generated.txt'
COVERAGE_EXCLUDE = '.agents/coverage-exclude.txt'
# The code files and the test files, as the keys code and tests of profile.json name them.
CODE = ('**/*.ts', '**/*.tsx', '**/*.mts', '**/*.cts')
TESTS = ('**/*.test.ts', '**/*.test.tsx', '**/*.test.mts', '**/*.test.cts')
# A declaration file holds types only, so no test runs it and it needs no JSDoc comment.
DECLARATIONS = ('.d.ts', '.d.mts', '.d.cts')
# The folders of the agents and of the installed tools, which hold no code of the project, as biome.json leaves out.
TOOL_FOLDERS = ('.agents/', '.claude/', '.codex/')
WORK = Path('.jnprofile-typescript')
REPORT = WORK / 'lcov.info'
# The build of test, which tsc writes again on each run.
BUILD = WORK / 'build'
# The integration tests, which the tool integration runs with a build and a report of their own.
INTEGRATION_FOLDER = 'tests/integration'
INTEGRATION = WORK / 'integration' / 'lcov.info'
INTEGRATION_BUILD = WORK / 'integration-build'
# The report of each run that coverage-check reads, the folder of the build of the run, and the raw data of c8.
REPORTS = {'test': REPORT, 'integration': INTEGRATION}
BUILDS = {'test': BUILD, 'cov': BUILD, 'integration': INTEGRATION_BUILD}
RAW = {'test': WORK / 'c8', 'integration': WORK / 'c8-integration'}
# The record of the installer. Its key steps names the steps of just check.
RECORD = Path('.agents/stack.json')
# The build of test-paths, inside the project, so that node finds its package.json and its node_modules.
PATHS_BUILD = WORK / 'test-paths'


def git(*args):
    """Run git with ARGS in the current folder, and return the finished process, with its output as text."""
    return subprocess.run(['git', *args], capture_output=True, text=True)


def has_parent():
    """True when HEAD names a commit, so that the next commit has a parent."""
    return git('rev-parse', '--verify', '--quiet', 'HEAD^{commit}').returncode == 0


def top():
    """The real path of the current folder, the top of the project. Every path of the steps is relative to it."""
    return Path(os.path.realpath('.'))


def parent_list(path):
    """The patterns of the list file PATH in the parent commit: one for each line that is not blank or a comment.

    A missing parent or a file that the parent does not have gives no patterns.
    """
    if not has_parent():
        return []
    run = git('show', f'HEAD:./{path}')
    if run.returncode:
        return []
    return [line.strip() for line in run.stdout.splitlines() if line.strip() and not line.strip().startswith('#')]


def listed(patterns, untracked=True):
    """The tracked files, and the untracked ones that git does not ignore, that one of PATTERNS matches, as a set.

    git matches the patterns, as pathspecs with the magic word glob, so the steps and the gate read a list in the same
    way. A * does not match a /, ** matches any number of folders, and a folder names all that it holds. A leading /
    is the top of the project.
    """
    if not patterns:
        return set()
    specs = [':(glob)' + pattern.lstrip('/') for pattern in patterns]
    run = git('ls-files', '-z', '--cached', *(['--others', '--exclude-standard'] if untracked else []), '--', *specs)
    if run.returncode:
        raise SystemExit(f'steps.py: git cannot read the patterns {patterns}: {run.stderr.strip()}')
    return set(filter(None, run.stdout.split('\0')))


def code_files(excluded):
    """The TypeScript files of the project that git tracks or does not ignore, without the test files, the declaration
    files, the files in the folders of the tools, the files in a folder node_modules and EXCLUDED.

    eslint never reads a file in a folder node_modules, and such a file is the code of a package, not of the project.
    """
    tests = listed(TESTS)
    return sorted(path for path in listed(CODE) if path not in tests and path not in excluded
                  and not path.endswith(DECLARATIONS) and not path.startswith(TOOL_FOLDERS)
                  and 'node_modules' not in path.split('/')[:-1] and Path(path).is_file())


def changed_code():
    """The changed TypeScript files against HEAD, tracked and staged or not, and the untracked ones, as two lists.

    The deleted files are left out.
    """
    specs = [':(glob)' + pattern for pattern in CODE]
    tracked = git('diff', '-z', '--name-only', '--relative', '--no-renames', '--diff-filter=d', 'HEAD', '--', *specs)
    untracked = git('ls-files', '-z', '--others', '--exclude-standard', '--', *specs)
    for run in (tracked, untracked):
        if run.returncode:
            raise SystemExit(f'steps.py: git cannot list the changed files: {run.stderr.strip()}')
    names = lambda run: sorted(set(filter(None, run.stdout.split('\0'))))
    return names(tracked), names(untracked)


def relative(path, root):
    """PATH relative to ROOT, with / between its parts, or None for a path outside ROOT."""
    full = Path(os.path.realpath(root / path))
    try:
        return full.relative_to(root).as_posix()
    except ValueError:
        return None


def read_lcov(text, root):
    """The records of the LCOV report TEXT, as a list of pairs: the path of the file relative to ROOT, or None, and
    the lines of its record.

    c8 writes the path of each file after SF:, relative to the current folder or absolute.
    """
    records, path, lines = [], None, []
    for line in text.splitlines():
        if line.startswith('SF:'):
            path, lines = relative(Path(line[3:]), root), []
        lines.append(line)
        if line == 'end_of_record':
            records.append((path, unrun_functions(lines)))
            path, lines = None, []
    return records


def unrun_functions(lines):
    """The LINES of one LCOV record, with the DA line of each function that never ran set to 0 hits.

    c8 counts a line as run when part of it runs. A one-line arrow function that no test calls, as in
    export const f = () => 1, is on a line that runs, so only its FN and FNDA lines show that it never ran. The FN
    lines and the FNDA lines come in the same order.
    """
    starts = [line[3:].split(',', 1)[0] for line in lines if line.startswith('FN:')]
    counts = [line[5:].split(',', 1)[0] for line in lines if line.startswith('FNDA:')]
    unrun = {start for start, count in zip(starts, counts) if count.strip() == '0'}
    out = []
    for line in lines:
        if line.startswith('DA:') and line[3:].split(',', 1)[0] in unrun:
            line = f'DA:{line[3:].split(",", 1)[0]},0'
        out.append(line)
    return out


def type_only_files(root):
    """The code files, relative to ROOT, whose output in the build of test holds no code: a file of types only.

    tsc drops an import of types, so no test loads such a file, and it is in no report. The source map of each
    output names its source. Lines such as export {}; and "use strict"; are no code.
    """
    plain = re.compile(r'^\s*(export \{\};|"use strict";|Object\.defineProperty\(exports, "__esModule", '
                       r'\{ value: true \}\);|//.*)?\s*$')
    found = set()
    for source_map in BUILD.rglob('*.map'):
        output = source_map.with_suffix('')
        # The map of a declaration file, from declarationMap, names a source that can hold code too.
        if output.name.endswith(DECLARATIONS):
            continue
        try:
            sources = json.loads(source_map.read_text()).get('sources', [])
            text = re.sub(r'/\*.*?\*/', '', output.read_text(), flags=re.S)
        except (OSError, ValueError, AttributeError):
            continue
        if len(sources) == 1 and all(plain.match(line) for line in text.splitlines()):
            path = relative(source_map.parent / sources[0], root)
            if path:
                found.add(path)
    return found


def kept_report(records, root, wanted):
    """The LCOV text of the records of the files in WANTED only, with the path of each file absolute.

    So the test files, the files in the folders of the tools and the files of the two lists do not count, and
    diff-cover finds each file also in a project in a subfolder of the git repository.
    """
    out = []
    for path, lines in records:
        if path in wanted:
            out += [f'SF:{root / path}' if line.startswith('SF:') else line for line in lines]
    return '\n'.join(out) + '\n'


def missed_lines(records, wanted):
    """The lines that the report has as not run, in the files of WANTED, as lines FILE:LINE."""
    found = set()
    for path, lines in records:
        if path in wanted:
            for line in lines:
                if line.startswith('DA:'):
                    number, hits = line[3:].split(',')[:2]
                    if hits.strip() == '0':
                        found.add((path, int(number)))
    return [f'{path}:{line}: no test runs this line' for path, line in sorted(found)]


def worktree_tree():
    """The tree hash of every file of the worktree, staged or not, that git does not ignore, or None on an error.

    It uses a temporary index of its own, as the spec of the commit gates says, so neither the real index nor a
    second run at the same time changes. The folder of the reports never counts. A file that git cannot index, such
    as a nested repository with no commit, gives None, and git's message goes to the error output.
    """
    WORK.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=WORK, suffix='.index')
    os.close(handle)
    index = Path(name).resolve()
    index.unlink()
    env = dict(os.environ, GIT_INDEX_FILE=str(index))
    try:
        if has_parent():
            subprocess.run(['git', 'read-tree', 'HEAD'], env=env, check=True, capture_output=True)
        # git refuses to name an ignored path, even to exclude it, so the exclude is only for a folder that git sees.
        ignored = git('check-ignore', '--quiet', '--', str(WORK)).returncode == 0
        specs = [':/'] if ignored else [':/', f':(exclude){WORK}']
        subprocess.run(['git', 'add', '-A', '--', *specs], env=env, check=True, capture_output=True)
        return subprocess.run(['git', 'write-tree'], env=env, check=True, capture_output=True,
                              text=True).stdout.strip()
    except subprocess.CalledProcessError as exc:
        print(f'steps.py: git cannot compute the worktree tree: {(exc.stderr or b"").decode(errors="replace").strip()}',
              file=sys.stderr)
        return None
    finally:
        index.unlink(missing_ok=True)
        Path(str(index) + '.lock').unlink(missing_ok=True)


def run_file(name):
    """The file that holds the run ID and the tree of the last run of NAME, test or integration, that passed."""
    return WORK / ('run.json' if name == 'test' else f'{name}-run.json')


def pending_file(name):
    """The file that holds the run ID and the tree of the run of NAME that is going on."""
    return WORK / ('run.pending' if name == 'test' else f'{name}-run.pending')


def begin(name, args):
    """Save the run ID and the worktree tree before a run of NAME, test or integration, in its pending file.

    Only a run of all the tests, with no ARGS, inside a run of just that has JLOG_RUN saves them. Any other run
    saves nothing, so the next step that needs the report runs the tests again. The old report goes, so a failed run
    leaves none. Returns the exit code, always 0.
    """
    WORK.mkdir(parents=True, exist_ok=True)
    for path in (run_file(name), pending_file(name), REPORTS[name]):
        path.unlink(missing_ok=True)
    # The raw coverage of c8, so that no old run adds to the report, also with clean: false in a .c8rc of the project.
    shutil.rmtree(RAW[name], ignore_errors=True)
    run = os.environ.get('JLOG_RUN', '')
    tree = worktree_tree() if not args and run else None
    if tree:
        pending_file(name).write_text(json.dumps({'run': run, 'tree': tree}) + '\n')
    return 0


def stamp(name):
    """After the run of NAME passed, keep the saved run as its run file when the tree did not change.

    A change to a file during the run means that the report may come from the old code, so the run is dropped.
    Returns the exit code, always 0.
    """
    try:
        saved = json.loads(pending_file(name).read_text())
    except (OSError, ValueError):
        return 0
    finally:
        pending_file(name).unlink(missing_ok=True)
    if isinstance(saved, dict) and saved.get('tree') and saved['tree'] == worktree_tree():
        # A run with no test passes and writes no report. It still counts as run, with no report.
        saved['report'] = REPORTS[name].is_file()
        run_file(name).write_text(json.dumps(saved) + '\n')
    else:
        print(f'{name}: a file changed while the tests ran, so the next step that needs them runs them again',
              file=sys.stderr)
    return 0


def same_run(name):
    """The run ID when the last run of NAME that passed comes from this run of just, JLOG_RUN, and from the current
    worktree tree, and the report that it wrote is still there. Otherwise None.

    A person can set JLOG_RUN by hand, so the tree must match too. An old run of the same tree is a valid run.
    """
    run = os.environ.get('JLOG_RUN', '')
    try:
        saved = json.loads(run_file(name).read_text())
    except (OSError, ValueError):
        saved = None
    if (run and isinstance(saved, dict) and saved.get('run') == run
            and (not saved.get('report', True) or REPORTS[name].is_file())
            and saved.get('tree') and saved['tree'] == worktree_tree()):
        return run
    return None


def recipes_of(justfile):
    """The names of the public recipes of JUSTFILE, as just --summary gives them, or an empty set on an error."""
    run = subprocess.run(['just', '--justfile', str(justfile), '--summary'], capture_output=True, text=True)
    return set(run.stdout.split()) if run.returncode == 0 else set()


def integration_counts(module):
    """True when the report of integration counts for coverage-check. The module MODULE must have the recipe
    integration, and the key steps of .agents/stack.json must name it, so that just check runs it."""
    try:
        steps = json.loads(RECORD.read_text()).get('steps')
    except (OSError, ValueError, AttributeError):
        steps = None
    return isinstance(steps, list) and 'integration' in steps and 'integration' in recipes_of(module)


def fresh(name, module):
    """True when the run of NAME in this run of just and on this tree wrote the report that coverage-check reads.

    For integration, it is also True when its report does not count, so that coverage-check does not run it.
    """
    if name == 'integration' and not integration_counts(module):
        return True
    run = same_run(name)
    what = 'tests' if name == 'test' else 'integration tests'
    if run:
        print(f'coverage-check: the {what} of this run, {run}, wrote the report, so they do not run again')
        return True
    print(f'coverage-check: no report of the {what} of this run and this tree, so they run now', flush=True)
    return False


def ran(name, args):
    """True when NAME passed before in this run of just and on this tree, and ARGS is empty. So the integration
    tests, which coverage-check can run before the step integration, run once in just check."""
    run = None if args else same_run(name)
    if run:
        print(f'{name}: it passed before in this run, {run}, on this tree, so it does not run again')
    return bool(run)


def union(paths, root):
    """The records of the LCOV reports PATHS, as read_lcov gives them, with one record for each file. A line counts
    as run when one report runs it. Each record holds only the lines DA, which are all that the steps read."""
    files = {}
    for path in paths:
        for name, lines in read_lcov(path.read_text(), root):
            if name is None:
                continue
            hits = files.setdefault(name, {})
            for line in lines:
                if line.startswith('DA:'):
                    try:
                        number, count = (int(part) for part in line[3:].split(',')[:2])
                    except ValueError:
                        continue
                    hits[number] = max(hits.get(number, 0), count)
    return [(name, [f'SF:{name}', *(f'DA:{number},{count}' for number, count in sorted(hits.items())),
                    'end_of_record'])
            for name, hits in sorted(files.items())]


def coverage(module=None):
    """Fail on each changed line of code that the tests do not run, as diff-cover against HEAD finds it.

    The report is the one of test. When integration counts, as integration_counts of MODULE says, it is the union of
    the reports of test and integration, so a line that only the integration tests run counts as run.

    The files of generated.txt and coverage-exclude.txt of the parent commit do not count, and nor do the test files.
    A line after /* c8 ignore next */ counts as run. On the first commit, every line of code must run, a limit of
    100%. A changed file that is not in the report fails too, because no test imports it. Returns the exit code.
    """
    root = top()
    excluded = listed(parent_list(GENERATED) + parent_list(COVERAGE_EXCLUDE))
    wanted = set(code_files(excluded)) - type_only_files(root)
    if has_parent():
        tracked, untracked = changed_code()
        tracked = [path for path in tracked if path in wanted]
        untracked = [path for path in untracked if path in wanted]
    else:
        tracked, untracked = [], sorted(wanted)
    changed = sorted(tracked + untracked)
    if not changed:
        print('coverage-check: no changed code')
        return 0
    names = [REPORT] + ([INTEGRATION] if module and integration_counts(module) else [])
    records = union([path for path in names if path.is_file()], root)
    if not records:
        print(f'coverage-check: there is no coverage report {" or ".join(map(str, names))}, so write tests and run '
              'just test', file=sys.stderr)
        return 1
    kept = {path for path, _ in records if path in wanted}
    code = 0
    if any(path in kept for path in tracked):
        filtered = WORK / 'kept.info'
        filtered.write_text(kept_report(records, root, wanted))
        # diff-cover names the files of the diff from the top of the git repository, and the paths of the report
        # from its current folder. So it runs at the top of the repository, which holds a project in a subfolder.
        repository = git('rev-parse', '--show-toplevel').stdout.strip() or str(root)
        sys.stdout.flush()
        code = subprocess.run(['uv', 'run', '--no-project', '--quiet', '--python', '>=3.11', '--with', DIFF_COVER,
                               'diff-cover', str(filtered.resolve()), '--compare-branch', 'HEAD',
                               '--fail-under', '100'], cwd=repository).returncode
    if not has_parent():
        print('coverage-check: the first commit, so every line of code must run in the tests', flush=True)
    # Each line of an untracked file is new, so each must run. On the first commit, each file is new.
    missed = missed_lines(records, set(untracked))
    for line in missed:
        print(line, flush=True)
    code = code or (1 if missed else 0)
    missing = [path for path in changed if path not in kept]
    for path in missing:
        print(f'{path}: a changed file that is not in the coverage report: no test imports it, or the c8 config '
              'leaves it out', flush=True)
    code = code or (1 if missing else 0)
    if code:
        print('coverage-check: write tests for the missing lines. A line that no test can run gets /* c8 ignore next '
              f'*/ above it, and a file of generated code goes in {GENERATED}, in a commit of its own before this one',
              file=sys.stderr)
    return code


def docs():
    """Fail on each class, method, function or arrow function with no JSDoc comment, exported or not, as lines
    FILE:LINE.

    eslint finds them, with only the rule jsdoc/require-jsdoc, from the config docstring.eslint.mjs next to this
    file. The config of the project does not count. The test files, the declaration files and the files of
    generated.txt of the parent commit do not count either. Returns the exit code.
    """
    files = code_files(listed(parent_list(GENERATED)))
    if not files:
        print('docstring-check: no code')
        return 0
    packages = [f'--package={package}' for package in ESLINT]
    run = subprocess.run([*NODE, 'npm', 'exec', '--yes', *packages, '--', 'eslint', '--no-config-lookup',
                          '--config', str(ESLINT_CONFIG), '--no-warn-ignored', '--format', 'json', '--', *files],
                         capture_output=True, text=True)
    try:
        results = json.loads(run.stdout)
    except ValueError:
        results = None
    if run.returncode not in (0, 1) or not isinstance(results, list):
        print(run.stdout + run.stderr, end='', file=sys.stderr)
        print(f'docstring-check: eslint failed with the exit code {run.returncode}', file=sys.stderr)
        return run.returncode or 2
    root = top()
    findings = []
    for result in results:
        path = relative(Path(result.get('filePath', '')), root) or result.get('filePath', '')
        try:
            source = Path(result.get('filePath', '')).read_text(errors='replace').splitlines()
        except OSError:
            source = []
        for message in result.get('messages', []):
            line = message.get('line', 1)
            if message.get('severity') != 2 and not message.get('fatal'):
                continue
            if message.get('ruleId') == 'jsdoc/require-jsdoc':
                # eslint 10 gives no type of node, so the finding shows the line of the item.
                text = source[line - 1].strip() if 0 < line <= len(source) else ''
                findings.append((path, line, f'no JSDoc comment: {text}'[:160]))
            else:
                findings.append((path, line, f'eslint: {message.get("message", "").strip()}'))
    for path, line, text in sorted(findings):
        print(f'{path}:{line}: {text}')
    if findings:
        print(f'docstring-check: {len(findings)} problems. Write a JSDoc comment /** ... */ for each item',
              file=sys.stderr)
        return 1
    return 0


def project_config():
    """The config of the project, as tsc --showConfig resolves it from tsconfig.json and its extends: the compiler
    options, the files that it finds, and its include and exclude, with absolute paths.

    An empty dict when tsc cannot read the config, so that the build itself shows the error.
    """
    run = subprocess.run([*NODE, 'npm', 'exec', '--', 'tsc', '--showConfig'], capture_output=True, text=True)
    try:
        config = json.loads(run.stdout)
    except ValueError:
        return {}
    return config if isinstance(config, dict) else {}


def options_of(config):
    """The compiler options of CONFIG, a dict that project_config gives."""
    options = config.get('compilerOptions', {})
    return options if isinstance(options, dict) else {}


def integration_tests():
    """The test files in the folder of the integration tests, tests/integration, that git tracks or does not ignore."""
    return sorted(path for path in listed(TESTS) if path.startswith(INTEGRATION_FOLDER + '/') and Path(path).is_file())


def leaf_config(build, config, needed):
    """The text of a tsconfig file that extends tsconfig.json and adds the integration tests of NEEDED to the files
    that CONFIG finds, or None when CONFIG already finds each of them or NEEDED has no integration test.

    The default tsconfig.json finds only src, and the integration tests are in tests/integration. tsc applies no
    exclude to the list files, so an exclude of the project does not hide them either. The file goes at the top of
    the project, next to tsconfig.json, so that each relative path and each ${configDir} of the config means what it
    means in tsconfig.json.
    """
    found = [Path(path).as_posix().removeprefix('./') for path in config.get('files', []) if isinstance(path, str)]
    extra = [path for path in needed if path.startswith(INTEGRATION_FOLDER + '/') and path not in set(found)]
    if not extra:
        return None
    return json.dumps({'extends': './tsconfig.json', 'files': [f'./{path}' for path in found + extra]}, indent=2) + '\n'


def compile_into(build, config, needed=()):
    """Compile the project with tsc into the folder BUILD, removed first, and return the finished process.

    The flags take the place of the settings of the project that would write elsewhere or write no JavaScript:
    the output, its root, which is the top of the project so that emitted() finds each file, the build info, the
    declarations, and the source maps that c8 needs. tsc writes the output also when a file has an error, so a file
    that does not build cannot hide another file. When an integration test of NEEDED is outside the files that
    tsconfig.json finds, tsc reads a config file of leaf_config, which is there only while tsc runs.
    """
    shutil.rmtree(build, ignore_errors=True)
    flags = ['--pretty', 'false', '--outDir', str(build), '--rootDir', '.', '--noEmit', 'false',
             '--emitDeclarationOnly', 'false', '--noEmitOnError', 'false',
             '--tsBuildInfoFile', str(build / 'tsconfig.tsbuildinfo'), '--sourceMap', 'true',
             '--inlineSourceMap', 'false']
    # tsc refuses a declarationDir with no declarations, so the flag goes only to a project that writes them.
    options = options_of(config)
    if options.get('declaration') or options.get('composite'):
        flags += ['--declarationDir', str(build / 'types')]
    leaf = leaf_config(build, config, needed)
    if not leaf:
        return subprocess.run([*NODE, 'npm', 'exec', '--', 'tsc', *flags], capture_output=True, text=True)
    handle, name = tempfile.mkstemp(dir='.', prefix='.jnprofile-typescript-', suffix='.tsconfig.json')
    path = Path(name)
    try:
        with os.fdopen(handle, 'w') as out:
            out.write(leaf)
        return subprocess.run([*NODE, 'npm', 'exec', '--', 'tsc', '--project', str(path), *flags],
                              capture_output=True, text=True)
    finally:
        path.unlink(missing_ok=True)


def emitted(path, build, options):
    """The path of the JavaScript file that tsc writes for the TypeScript file PATH into BUILD.

    With the option jsx set to preserve, a .tsx file becomes a .jsx file.
    """
    jsx = '.jsx' if str(options.get('jsx', '')).lower() == 'preserve' else '.js'
    for source, target in (('.mts', '.mjs'), ('.cts', '.cjs'), ('.tsx', jsx), ('.ts', '.js')):
        if path.endswith(source):
            return build / (path[:-len(source)] + target)
    return build / path


def build(name, module, given):
    """Compile the project into the build of NAME, test, cov or integration, and return the exit code.

    With the tool integration, which the recipe integration of the module MODULE shows, test and cov leave out the
    integration tests in tests/integration, and integration runs only them. Without it, test and cov run them too.
    It fails on each test file of the run that tsc writes no output for, because no test of it would run. Such a
    file is outside the include of tsconfig.json. With nothing to run, it exits with 3 when GIVEN, the count of the
    arguments of the recipe, is 0, and with 1 otherwise: tsconfig.json finds no file at all, error TS18003, or there
    is no integration test.
    """
    folder = BUILDS[name]
    tests = sorted(path for path in listed(TESTS) if not path.startswith(TOOL_FOLDERS)
                   and 'node_modules' not in path.split('/')[:-1] and Path(path).is_file())
    inside = integration_tests()
    if name == 'integration':
        if not inside:
            print(f'just integration: no integration tests yet, in {INTEGRATION_FOLDER}')
            return 3 if given == '0' else 1
        needed = inside
    elif 'integration' in recipes_of(module):
        needed = [path for path in tests if path not in inside]
    else:
        needed = tests
    config = project_config()
    options = options_of(config)
    run = compile_into(folder, config, needed)
    out = run.stdout + run.stderr
    if run.returncode and 'error TS18003' in out and not needed:
        if given == '0':
            print(f'just {name}: no code yet')
            return 3
        print(f'just {name}: tsconfig.json finds no code')
        return 1
    if run.returncode and 'error TS18003' not in out:
        print(out, end='')
        return run.returncode
    if name != 'integration' and needed != tests:
        # The integration tool runs these, so node --test finds no output of them in the build of test.
        shutil.rmtree(folder / INTEGRATION_FOLDER, ignore_errors=True)
    absent = [path for path in needed if not emitted(path, folder, options).is_file()]
    for path in absent:
        print(f'{path}: tsc writes no output for this test file, so its tests never run. Name it in the include of '
              'tsconfig.json', flush=True)
    return 1 if absent else 0


def ran_tests(report, outputs):
    """The count of the tests in the JUnit report of node that ran: a skipped or todo test does not count.

    node gives a file with no test, or a file that does not load, a case of its own with the name of the file. Such a
    case is no test that ran. Returns None when there is no report.
    """
    try:
        tree = ElementTree.parse(report)
    except (OSError, ElementTree.ParseError):
        return None
    files = {str(output.resolve()) for output in outputs}
    count = 0
    for case in tree.iter('testcase'):
        whole_file = case.get('file') in files and Path(case.get('name', '')).resolve() == Path(case.get('file'))
        if case.find('skipped') is None and not whole_file:
            count += 1
    return count


def test_paths(files):
    """Run only the test files FILES, for test-parent of the commit gates, and return the exit code.

    It exits with 0 when tests ran and passed, with 1 when a test fails or a file does not build, as a new test of
    new code on the parent commit, and with 5 when no test runs, as for a file whose tests are all skipped or todo.
    Any other code means that npm, tsc or node itself failed, or that a test ended the run. With no file, it exits
    with 5 and runs nothing.
    """
    if not files:
        print('just test-paths: no test file')
        return 5
    if not Path('node_modules').is_dir():
        install = ['ci'] if Path('package-lock.json').is_file() else ['install']
        run = subprocess.run([*NODE, 'npm', *install, '--no-audit', '--no-fund'], capture_output=True, text=True)
        if run.returncode:
            print(run.stdout + run.stderr, end='')
            print('just test-paths: npm cannot install the dependencies of the project')
            return 2
    named = [Path(path).as_posix().removeprefix('./') for path in files]
    config = project_config()
    options = options_of(config)
    run = compile_into(PATHS_BUILD, config, named)
    print(run.stdout + run.stderr, end='')
    if run.returncode and any(line.startswith(f'{path}(') for line in run.stdout.splitlines() for path in named):
        print('just test-paths: a test file does not build')
        return 1
    outputs = [emitted(path, PATHS_BUILD, options) for path in named]
    absent = [path for path, output in zip(named, outputs) if not output.is_file()]
    if absent:
        print(f'just test-paths: tsc wrote no output for {", ".join(absent)}: the include of tsconfig.json does not '
              'name it, or the project does not build')
        return 2
    with tempfile.TemporaryDirectory() as folder:
        report = Path(folder) / 'report.xml'
        # One process for all files, so a test that ends the process with process.exit leaves no report.
        run = subprocess.run([*NODE, 'node', '--test', '--test-isolation=none', '--test-reporter=spec',
                              '--test-reporter-destination=stdout', '--test-reporter=junit',
                              f'--test-reporter-destination={report}', *[str(output.resolve()) for output in outputs]],
                             capture_output=True, text=True)
        print(run.stdout + run.stderr, end='')
        ran = ran_tests(report, outputs)
    if ran is None or run.returncode not in (0, 1):
        return 2
    if run.returncode == 1:
        return 1
    return 0 if ran else 5


def main(argv):
    """Run the command of ARGV, as the docstring of the module lists them, and return its exit code."""
    if argv[:1] == ['coverage'] and len(argv) <= 2:
        return coverage(argv[1] if len(argv) == 2 else None)
    if argv == ['docs']:
        return docs()
    if argv[:1] == ['fresh'] and len(argv) == 3 and argv[1] in REPORTS:
        return 0 if fresh(argv[1], argv[2]) else 1
    if argv[:1] == ['ran'] and len(argv) >= 2 and argv[1] in REPORTS:
        return 0 if ran(argv[1], argv[2:]) else 1
    if argv[:1] == ['begin'] and len(argv) >= 2 and argv[1] in REPORTS:
        return begin(argv[1], argv[2:])
    if argv[:1] == ['stamp'] and len(argv) == 2 and argv[1] in REPORTS:
        return stamp(argv[1])
    if argv[:1] == ['test-paths']:
        return test_paths(argv[1:])
    if argv[:1] == ['build'] and len(argv) == 4 and argv[1] in BUILDS:
        return build(*argv[1:])
    print('usage: steps.py coverage [MODULE] | docs | fresh NAME MODULE | ran NAME [ARG...] | begin NAME [ARG...] | '
          'stamp NAME | build NAME MODULE COUNT | test-paths [FILE...]', file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
