#!/usr/bin/env python3

import os
import yaml

import git
from github import Github

CONFIG_FILE = 'bot_config.yaml'
REQUIRED_CONFIG_FIELDS = {
    'upstream': str,
    'downstream': str,
    'branches': dict
}


def main():
    gh_client, config = load_config()

    upstream = gh_client.get_repo(config['upstream'])
    downstream = gh_client.get_repo(config['downstream'])

    local_repo = clone_repo(downstream, upstream.name)
    set_remote(local_repo, 'upstream', upstream.ssh_url)

    for upstream_branch, downstream_branch in config['branches'].items():
        try:
            checkout_and_merge(local_repo, upstream_branch, downstream_branch, local_repo.remotes.upstream, local_repo.remotes.origin)
            local_repo.git.execute(['git', 'push', f'{local_repo.remotes.origin.name}', f'{downstream_branch}'])
            print(f'Successfully pushed upstream/{upstream_branch} to downstream/{downstream_branch}')
        except git.exc.GitCommandError as e:
            if 'nothing to commit, working tree clean' in e.stdout:
                print(f'Nothing to do, upstream/{upstream_branch} has no changes not present in downstream/{downstream_branch}')
                continue
            file_github_issue(gh_client, e, local_repo, upstream, downstream, upstream_branch, downstream_branch, config['assignees'])

    return 0


def load_config():
    with open(CONFIG_FILE, 'r') as f:
        config = yaml.safe_load(f.read())
    access_token = config.get('github_access_token', os.environ.get('GITHUB_ACCESS_TOKEN'))
    if access_token:
        print("Creating github client with provided access token")
        gh_client = Github(access_token)
    else:
        print("Creating anonymous github client")
        gh_client = Github()

    for field, type_ in REQUIRED_CONFIG_FIELDS.items():
        if not config.get(field):
            raise ValueError(f'{field} is required, please add it to your {CONFIG_FILE}')
        config_type = type(config[field])
        if not isinstance(config[field], type_):
            raise ValueError(f'{field} must be of type {type_}, not {config_type}')
    if not config.get('assignees'):
        config['assigness'] = []

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


def checkout_and_merge(repo, from_branch, to_branch, from_remote, to_remote):
    """ Checks out the branch, merges it with the base configuration if it doesn't already exist,
        updates static files and commits the changes
    """
    try:
        repo.branches[to_branch]
        repo.git.execute(['git', 'checkout', f'{to_branch}'])
    except IndexError:
        setup_new_branch(repo, from_branch, to_branch, from_remote)

    merge_carried_changes(repo)

    merge_and_commit(repo, from_branch, to_branch, from_remote)


def setup_new_branch(repo, from_branch, to_branch, from_remote):
    repo.git.execute(['git', 'checkout', f'{from_remote.name}/{from_branch}'])
    repo.git.execute(['git', 'checkout', '-b', f'{to_branch}'])


def merge_carried_changes(repo):
    sentinel = os.path.join(repo.working_dir, '.downstream_merged')
    if not os.path.exists(sentinel):
        repo.git.execute(['git', 'merge', f'origin/downstream-changes', '--allow-unrelated-histories', '--squash', '--strategy', 'recursive', '-X', 'theirs'])
        with open(sentinel, 'w') as f:
            f.write('True')
        merge_message = "Merged origin/downstream-changes and added sentinel"
        repo.git.execute(['git', 'add', '--all'])
        repo.git.execute(['git', 'commit', '-m', merge_message])
        print(merge_message)


def merge_and_commit(repo, from_branch, to_branch, from_remote):
    repo.git.execute(['git', 'merge', f'{from_remote.name}/{from_branch}', '--no-commit'])
    repo.git.execute(['go', 'mod', 'vendor'])
    repo.git.execute(['go', 'run', './hack/image/ansible/scaffold-ansible-image.go'])
    repo.git.execute(['git', 'checkout', 'origin/downstream-changes', '.gitignore'])
    repo.git.execute(['git', 'add', '--all'])
    merge_message = f"Merge remote-tracking branch '{from_remote.name}/{from_branch}' into {to_branch}"
    repo.git.execute(['git', 'commit', '-m', merge_message])
    print(merge_message)


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
    issue_title = f'Error merging upstream {from_branch} into {to_branch}'

    for issue in downstream.get_issues(state='open'):
        if issue.title == issue_title:
            print(f'An open issue titled "{issue_title}" already exists, skipping..."')
            # No need to double up
            return

    issue_body = f"""## Merge failure

upstream: `{upstream.html_url}/tree/{from_branch}`
downstream: `{downstream.html_url}/tree/{to_branch}`
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
    downstream.create_issue(
        issue_title,
        body=issue_body,
        assignees=assignees
    )


if __name__ == '__main__':
    main()
