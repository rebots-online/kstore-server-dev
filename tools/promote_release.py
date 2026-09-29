#!/usr/bin/env python3
"""Publish a cleared public source revision into a private release repository.

Run in the development checkout. No production working tree is edited.
Production subsequently pulls the printed private commit with --ff-only.
"""
import argparse
import json
import os
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--production-remote', required=True)
    parser.add_argument('--branch', default='master')
    parser.add_argument('--cleared-for-production', action='store_true', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    def source(*parts):
        return subprocess.check_output(['git','-C',str(root),*parts])
    commit = source('rev-parse',args.source_commit+'^{commit}').decode().strip()
    if source('status','--porcelain').strip():
        raise SystemExit('Commit source changes before promotion')
    if source('rev-parse','HEAD').decode().strip()!=commit:
        raise SystemExit('Check out the cleared source commit before promotion')
    subprocess.run([str(root/'.venv/bin/python'),'-m','unittest','discover','-s','tests'],cwd=root,check=True)
    staging = root/'.release';staging.mkdir(exist_ok=True)
    repo=staging/'private-promotion.git'
    if not repo.exists(): subprocess.run(['git','init','--bare',str(repo)],check=True)
    def private(*parts, **kwargs):
        return subprocess.check_output(['git','--git-dir='+str(repo),*parts],**kwargs)
    private('fetch',args.production_remote,args.branch)
    parent=private('rev-parse','FETCH_HEAD').decode().strip()
    index=staging/'promotion.index'
    env=dict(os.environ,GIT_INDEX_FILE=str(index))
    private('read-tree',parent,env=env)
    entries=source('ls-tree','-r','-z',commit).split(b'\0')
    for entry in entries:
        if not entry:continue
        info,name=entry.split(b'\t',1); mode,kind,blob=info.split()
        if kind!=b'blob':raise SystemExit('Public release must not contain nested gitlinks')
        content=source('cat-file','blob',blob.decode())
        obj=private('hash-object','-w','--stdin',input=content).decode().strip()
        private('update-index','--add','--cacheinfo',mode.decode(),obj,name.decode(),env=env)
    metadata=json.dumps({'public_source_commit':commit,'private_parent':parent,'tests':'unittest discover -s tests','cleared_for_production':True},indent=2).encode()+b'\n'
    obj=private('hash-object','-w','--stdin',input=metadata).decode().strip()
    private('update-index','--add','--cacheinfo','100644',obj,'RELEASE-PROVENANCE.json',env=env)
    tree=private('write-tree',env=env).decode().strip()
    release=private('commit-tree',tree,'-p',parent,input=('Promote cleared public source '+commit+'\n').encode()).decode().strip()
    private('push',args.production_remote,release+':refs/heads/'+args.branch)
    actual=private('ls-remote',args.production_remote,'refs/heads/'+args.branch).decode().split()[0]
    if actual!=release:raise SystemExit('Remote changed; do not activate without reconciliation')
    print(json.dumps({'public_source_commit':commit,'private_release_commit':release,'production_activation':'not performed'}))

if __name__=='__main__':main()
