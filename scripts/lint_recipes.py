"""The lint of the recipes of the profile, for just lint.

just install writes a module file for the profile: its settings, an import of base.just and of the recipe file of
each tool that the project has, and a recipe verify that runs the verify steps of those tools. So the module file of
each tool alone must parse, and the module file of all the tools together. just parses each one with just --summary,
in a temporary folder, as module_text of the installer of jnterfaces writes it, without the shell line of jlog.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parent.parent
NAME = 'typescript'


def module(profile, tools):
    """The module file that just install writes for the tools TOOLS of PROFILE."""
    lines = ['set positional-arguments', "set working-directory := '../..'", '']
    files = [profile.get('base', {}).get('recipes')] + [profile['tools'][tool].get('recipes') for tool in tools]
    lines += [f"import '{NAME}/{file}'" for file in dict.fromkeys(f for f in files if f)]
    steps = [step for tool in tools for step in profile['tools'][tool].get('verify', [])]
    # A step with arguments is a dependency with arguments: fmt --check becomes (fmt "--check").
    deps = ' '.join(step if ' ' not in step else '(' + step.split(' ')[0] + ' '
                    + ' '.join(json.dumps(arg) for arg in step.split(' ')[1:]) + ')' for step in steps)
    lines += ['', f'verify: {deps}'.rstrip()] if steps else ['', 'verify:', '    @true']
    return '\n'.join(lines) + '\n'


def parses(folder, text):
    """None when just parses the module file TEXT next to the recipe folder FOLDER, else the error of just."""
    with tempfile.TemporaryDirectory() as temp:
        just = Path(temp) / '.agents/just'
        just.mkdir(parents=True)
        (just / NAME).symlink_to(folder)
        (just / f'{NAME}.just').write_text(text)
        run = subprocess.run(['just', '--justfile', str(just / f'{NAME}.just'), '--summary'], capture_output=True,
                             text=True, check=False)
        return None if run.returncode == 0 else (run.stderr or run.stdout).strip()


def main(repo=REPO):
    """Check the recipe files of the profile in REPO. Returns 1 on a problem, else 0."""
    profile = json.loads((repo / 'profile.json').read_text())
    folder = repo / '.agents/just' / NAME
    base = folder / profile['base']['recipes']
    tools = profile['tools']
    named = {folder / tool['recipes'] for tool in tools.values() if tool.get('recipes')}
    problems = []
    for path in sorted(set(folder.glob('*.just')) - named - {base}):
        problems.append(f'{path.relative_to(repo)}: no tool of profile.json names it')
    for path in sorted(named | {base}):
        if not path.is_file():
            problems.append(f'profile.json names {path.relative_to(repo)}, which is not there')
    if not problems:
        for tool in tools:
            error = parses(folder, module(profile, [tool]))
            if error:
                problems.append(f'the tool {tool} alone: {error}')
        error = parses(folder, module(profile, list(tools)))
        if error:
            problems.append(f'all the tools together: {error}')
    for problem in problems:
        print(f'lint-recipes: {problem}', file=sys.stderr)
    if not problems:
        print(f'lint-recipes: the module file of each of the {len(tools)} tools parses, alone and with all of them')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
