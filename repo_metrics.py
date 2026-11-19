"""Count source/configuration line changes in owned public, non-fork repos."""
from pathlib import Path
import subprocess, re
SOURCE_PATTERNS=['*.py','*.sh','*.bash','*.rs','*.js','*.jsx','*.ts','*.tsx','*.c','*.h','*.cpp','*.hpp','*.go','*.java','*.kt','*.cs','*.rb','*.php','*.swift','*.sql','*.html','*.css','*.scss','*.vue','*.svelte','*.lua','*.ps1','*.yaml','*.yml','*.toml','*.json','Dockerfile','Makefile']

SOURCE_EXCLUDES=[':(exclude)generated/**', ':(exclude)assets/github-profile.json', ':(exclude).cache/**', ':(exclude)**/node_modules/**', ':(exclude)**/vendor/**']

def git(*args):
    result=subprocess.run(['git',*args],capture_output=True,text=True,timeout=120)
    if result.returncode:
        raise OSError('Git statistics failed: '+result.stderr.strip()[:250])
    return result.stdout

def parse_numstat(text):
    added=deleted=0
    for line in text.splitlines():
        parts=line.split('\t',2)
        if len(parts)==3 and parts[0].isdigit() and parts[1].isdigit():
            added+=int(parts[0]);deleted+=int(parts[1])
    return added,deleted

def collect_metrics(repos,root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    added=deleted=commits=0;details=[]
    for repo in repos:
        if repo.get('fork') or repo.get('private') or repo.get('size',0)==0:
            continue
        name=repo['full_name'];branch=repo['default_branch']
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',name):
            raise ValueError('Invalid repository name')
        folder=root/(name.replace('/','__')+'.git')
        print('Counting default-branch history: '+name,flush=True)
        if folder.exists():
            git('-C',str(folder),'fetch','--quiet','origin',f'+refs/heads/{branch}:refs/heads/{branch}')
        else:
            git('clone','--quiet','--bare','--single-branch','--branch',branch,'https://github.com/'+name+'.git',str(folder))
        commit_count=int(git('-C',str(folder),'rev-list','--count',branch).strip())
        diff=git('-C',str(folder),'log','--first-parent','--diff-merges=first-parent','--numstat','--format=','--no-renames',branch,'--',*SOURCE_PATTERNS,*SOURCE_EXCLUDES)
        a,d=parse_numstat(diff);added+=a;deleted+=d;commits+=commit_count
        details.append({'repository':name,'commits':commit_count,'additions':a,'deletions':d})
    return {'commits':commits,'additions':added,'deletions':deleted,'loc':added-deleted,'repositories':details,'scope':'Owned public non-fork repositories, default branches; commits count reachable history (all authors). Lines count tracked source/config text including blank/comment lines, excluding generated output, the stats cache, node_modules and vendor; churn follows first-parent diffs including merge changes.'}
