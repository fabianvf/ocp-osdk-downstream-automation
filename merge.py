#!/usr/bin/env python3

import yaml

import git
from github import Github

# UPSTREAM_REPO = 'operator-framework/operator-sdk'
# DOWNSTREAM_REPO = 'fabianvf/operator-sdk-downstream-test'

# DEFAULT_CONFIG = {
#     'github_access_token': os.environ.get('GITHUB_ACCESS_TOKEN'),
# }
CONFIG_FILE = 'bot_config.yaml'


def main():
    with open(CONFIG_FILE, 'r') as f:
        config = yaml.safe_load(f.read())
    gh_client = Github()
    # gh_client = Github(config['github_access_token'])
    upstream = gh_client.get_repo(config['upstream'])
    downstream = gh_client.get_repo(config['downstream'])

    local_repo = clone_repo(downstream, upstream.name)
    set_remote(local_repo, 'upstream', upstream.ssh_url)

    for upstream_branch, downstream_branch in config['branches'].items():
        checkout_and_merge(local_repo, upstream_branch, downstream_branch, local_repo.remotes.upstream, local_repo.remotes.origin)
    # TODO Push changes
    # TODO File an issue if merge/commit/push fails

    return 0


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

    try:
        merge_and_commit(repo, from_branch, to_branch, from_remote)
    except Exception as e:
        repo.git.execute(['git', 'reset', '--hard', 'HEAD'])
        repo.git.execute(['git', 'clean', '-f'])
        print(e)
    # print(repo, branch.name, from_remote, to_remote)


def setup_new_branch(repo, from_branch, to_branch, from_remote):
    repo.git.execute(['git', 'checkout', f'{from_remote.name}/{from_branch}'])
    repo.git.execute(['git', 'checkout', '-b', f'{to_branch}'])


def merge_and_commit(repo, from_branch, to_branch, from_remote):
    repo.git.execute(['git', 'merge', f'origin/downstream-changes', '--allow-unrelated-histories', '--squash', '--strategy', 'ours'])
    repo.git.execute(['git', 'merge', f'{from_remote.name}/{from_branch}', '--no-commit'])
    repo.git.execute(['go', 'mod', 'vendor'])
    repo.git.execute(['go', 'run', './hack/image/ansible/scaffold-ansible-image.go'])
    repo.git.execute(['git', 'checkout', 'origin/downstream-changes', '.gitignore'])
    repo.git.execute(['git', 'add', '--all'])
    merge_message = f"Merge remote-tracking branch '{from_remote.name}/{from_branch}' into {to_branch}"
    repo.git.execute(['git', 'commit', '-m', merge_message])
    print(merge_message)


if __name__ == '__main__':
    main()
