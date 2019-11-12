#!/usr/bin/env python3

import os
import argparse

import yaml

import git
from github import Github

DEFAULT_CONFIG_FILE = 'bot_config.yaml'
REQUIRED_CONFIG_FIELDS = {
    'upstream': str,
    'downstream': str,
    'branches': dict
}
OPTIONAL_CONFIG_FIELDS = {
    'overlay_branch': str,
    'always_overlay': list,
    'exit_on_error': bool,
    'no_push': bool,
    'no_issue': bool,
    'assignees': list,
}


def main():
    gh_client, config = load_config(parse_args())

    upstream = gh_client.get_repo(config['upstream'])
    downstream = gh_client.get_repo(config['downstream'])

    local_repo = clone_repo(downstream, upstream.name)
    set_remote(local_repo, 'upstream', upstream.ssh_url)

    for upstream_branch, downstream_branch in config['branches'].items():
        try:
            checkout(local_repo, upstream_branch, downstream_branch)

            if config.get('overlay_branch'):
                if merge_overlay(local_repo, config['overlay_branch'], downstream_branch in config['always_overlay']):
                    push(local_repo, upstream_branch, downstream_branch, config.get('no_push'))

            if merge_upstream(local_repo, upstream_branch, downstream_branch):
                push(local_repo, upstream_branch, downstream_branch, config.get('no_push'))

        except git.exc.GitCommandError as e:
            if config.get('exit_on_error'):
                raise
            if not config.get('no_issue'):
                file_github_issue(gh_client, e, local_repo, upstream, downstream, upstream_branch, downstream_branch, config['assignees'])
            else:
                print(f"Not filing an issue for exception:\n{e}")
            cleanup(local_repo)

    return 0


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", "-c", help="Path to configuration file", default=DEFAULT_CONFIG_FILE)
    parser.add_argument("--upstream", "-u", help="The upstream github repository")
    parser.add_argument("--downstream", "-d", help="The downstream github repository")
    parser.add_argument("--downstream-branch", "-D", help="The downstream branch")
    parser.add_argument("--upstream-branch", "-U", help="The upstream branch")
    parser.add_argument("--overlay-branch", "-o", help="The downstream branch to overlay on all branches from upstream")
    parser.add_argument("--always-overlay", "-a", help="Comma separated list of branches to always apply the overlay branch to")
    parser.add_argument("--exit-on-error", "-e", help="If true, exits on error without cleaning the git repository or filing an issue", action="store_true")
    parser.add_argument("--no-push", "-np", help="If true, does not do a git push after a successful merge", action="store_true")
    parser.add_argument("--no-issue", "-no", help="If true, does not file a github issue on error", action="store_true")
    args = parser.parse_args()
    config = {
        "config": args.config,
    }
    if args.exit_on_error:
        config['exit_on_error'] = args.exit_on_error
    if args.no_push:
        config['no_push'] = args.no_push
    if args.no_issue:
        config['no_issue'] = args.no_issue
    if args.downstream:
        config['downstream'] = args.downstream
    if args.upstream:
        config['upstream'] = args.upstream
    if args.overlay_branch:
        config['overlay_branch'] = args.overlay_branch
    if args.always_overlay:
        config['always_overlay'] = args.always_overlay.split(',')
    if args.downstream_branch or args.upstream_branch:
        if not args.downstream_branch and args.upstream_branch:
            raise ValueError("If overriding the upstream/downstream branches, both --upstream-branch and --downstream-branch must be provided")
        config['branches'] = {
            args.upstream_branch: args.downstream_branch
        }
    return config


def load_config(overrides):
    print(f"Loading config from {overrides['config']}")
    with open(overrides['config'], 'r') as f:
        config = yaml.safe_load(f.read())
    access_token = config.get('github_access_token', os.environ.get('GITHUB_ACCESS_TOKEN'))
    if access_token:
        print("Creating github client with provided access token")
        gh_client = Github(access_token)
    else:
        print("Creating anonymous github client")
        gh_client = Github()

    config.update(overrides)
    if not config.get('assignees'):
        config['assigness'] = []
    if not config.get('always_overlay'):
        config['always_overlay'] = []

    def validate_field(name, desired, value):
        if not isinstance(value, desired):
            raise ValueError(f'{name} must be of type {desired}, not {type(value)}')

    for field, type_ in REQUIRED_CONFIG_FIELDS.items():
        if not config.get(field):
            raise ValueError(f'{field} is required, please add it to your {overrides["config"]}')
        validate_field(field, type_, config[field])

    for field, type_ in OPTIONAL_CONFIG_FIELDS.items():
        if field in config:
            validate_field(field, type_, config[field])

    return gh_client, config


def clone_repo(repo, name):
    try:
        cloned_repo = git.Repo.clone_from(repo.ssh_url, name)
    except git.exc.GitCommandError:
        cloned_repo = git.Repo(name)
    return cloned_repo


def set_remote(repo, remote_name, remote_url):
    if not getattr(repo.remotes, remote_name, None):
        git.Remote.add(repo, remote_name, remote_url)
    getattr(repo.remotes, remote_name).fetch()


def checkout(repo, from_branch, to_branch):
    """ Checks out the branch, merges it with the base configuration if it doesn't already exist,
        updates static files and commits the changes
    """
    try:
        repo.branches[to_branch]
        repo.git.execute(['git', 'checkout', f'{to_branch}'])
    except IndexError:
        repo.git.execute(['git', 'checkout', f'{repo.remotes.upstream.name}/{from_branch}'])
        repo.git.execute(['git', 'checkout', '-b', f'{to_branch}'])


def merge_overlay(repo, overlay_branch, force_overlay):
    try:
        sentinel = os.path.join(repo.working_dir, f'.{overlay_branch}_merged')
        if not os.path.exists(sentinel) or force_overlay:
            repo.git.execute(['git', 'merge', f'origin/{overlay_branch}', '--allow-unrelated-histories', '--squash', '--strategy', 'recursive', '-X', 'theirs'])
            with open(sentinel, 'w') as f:
                f.write('True')
            merge_message = f"Merged origin/{overlay_branch} and added sentinel"
            repo.git.execute(['git', 'add', '--all'])
            repo.git.execute(['git', 'commit', '-m', merge_message])
            print(merge_message)
            return True
    except git.exc.GitCommandError as e:
        if 'nothing to commit, working tree clean' in e.stdout:
            print(f'Nothing to do, downstream/{overlay_branch} has no changes not present in downstream/{repo.active_branch.name}')
        else:
            raise
    return False


def merge_upstream(repo, from_branch, to_branch):
    try:
        repo.git.execute(['git', 'merge', f'{repo.remotes.upstream.name}/{from_branch}', '--no-commit'])
        repo.git.execute(['go', 'mod', 'vendor'])
        repo.git.execute(['go', 'run', './hack/image/ansible/scaffold-ansible-image.go'])
        repo.git.execute(['git', 'checkout', 'origin/downstream-changes', '.gitignore'])
        repo.git.execute(['git', 'add', '--all'])
        merge_message = f"Merge remote-tracking branch '{repo.remotes.upstream.name}/{from_branch}' into {to_branch}"
        repo.git.execute(['git', 'commit', '-m', merge_message])
        print(merge_message)
        return True
    except git.exc.GitCommandError as e:
        if 'nothing to commit, working tree clean' in e.stdout:
            print(f'Nothing to do, upstream/{from_branch} has no changes not present in downstream/{to_branch}')
        else:
            raise
    return False


def push(repo, from_branch, to_branch, no_push):
    if no_push is True:
        print("Skipping push to downstream/{downstream_branch}")
    else:
        repo.git.execute(['git', 'push', f'{repo.remotes.origin.name}', f'{to_branch}'])
        print(f'Successfully pushed upstream/{from_branch} to downstream/{to_branch}')


def cantfail(func):
    def inner(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f'{func.__name__} failed with exception: {e}')
    return inner


@cantfail
def cleanup(repo):
    repo.git.execute(['git', 'merge', '--abort'])
    repo.git.execute(['git', 'reset', '--hard', 'HEAD'])
    repo.git.execute(['git', 'clean', '-f'])


@cantfail
def file_github_issue(client, error, local_repo, upstream, downstream, from_branch, to_branch, assignees):
    issue_title = f'Error merging upstream/{from_branch} into {to_branch}'

    for issue in downstream.get_issues(state='open'):
        if issue.title == issue_title:
            print(f'An open issue titled "{issue_title}" already exists ({issue.html_url}), skipping..."')
            # No need to double up
            return

    issue_body = f"""## Merge failure

upstream: {upstream.html_url}/tree/{from_branch}
downstream: {downstream.html_url}/tree/{to_branch}
command: `{' '.join(error.command)}`

status: `{error.status}`

stdout:
```
{error.stdout.strip()}
```
stderr:
```
{error.stderr.strip()}
```

### Additional debug

```
$ git status
{local_repo.git.execute(['git', 'status'])}

$ ls -lah
{local_repo.git.execute(['ls', '-lah'])}

$ git diff
{local_repo.git.execute(['git', 'diff'])}
```
"""
    issue = downstream.create_issue(
        issue_title,
        body=issue_body,
        assignees=assignees
    )
    print(f'Merging upstream/{from_branch} to downstream/{to_branch} failed - Created issue {issue.html_url}')


if __name__ == '__main__':
    main()
