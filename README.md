# Openshift operator-sdk downstream automation

This repo contains scripts and configuration for automatically merging and tracking upstream
operator-sdk branches to a downstream clone.

## To use:

First, create your downstream repo. Ensure you have a branch named `downstream-changes`, which
contains changes that you would like to be merged into every discovered branch. This includes
a `.gitignore`, as some files are ignored upstream that are required downstream. Once your
downstream repo is set up, run the following commands:

```bash
$ pip3 install -r requirements.txt
$ cp bot_config.yaml.example bot_config.yaml
$ vim bot_config.yaml # Add the desired values
$ python3 merge.py
```
