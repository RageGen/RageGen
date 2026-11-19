"""Public GitHub data only. No hosted card service or scraped HTML."""
import json, os, time, urllib.request, urllib.error
from datetime import datetime, timezone
from collections import Counter

def request(path):
    headers = {'User-Agent': 'retro-profile-local-renderer', 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if token:
        headers['Authorization'] = 'Bearer '+token
    req = urllib.request.Request('https://api.github.com'+path, headers=headers)
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=12) as res:
                return json.load(res)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429,500,502,503,504) or attempt:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            if attempt:
                raise
        time.sleep(1)

def collect(username):
    from urllib.parse import quote
    name = quote(username, safe='')
    print('Fetching public GitHub profile…', flush=True)
    profile = request('/users/'+name)
    repos = []
    page = 1
    while True:
        batch = request(f'/users/{name}/repos?type=owner&per_page=100&page={page}&sort=full_name')
        repos.extend(r for r in batch if not r.get('private'))
        if len(batch)<100:
            break
        page += 1
    from repo_metrics import collect_metrics
    from pathlib import Path
    metrics=collect_metrics(repos,Path(__file__).resolve().parent/'.cache/git')
    for kind,key in [('issue','issues'),('pr','prs')]:
        result=request('/search/issues?q='+quote(f'author:{username} type:{kind} is:public',safe='')+'&per_page=1')
        if result.get('incomplete_results'):
            raise ValueError('GitHub returned incomplete search statistics')
        metrics[key]=result['total_count']
    return {'metrics':metrics,'username': username, 'fetched_at': datetime.now(timezone.utc).isoformat(), 'profile': profile, 'repositories': repos}

def values(snapshot):
    profile, repos = snapshot['profile'], snapshot['repositories']
    created = datetime.fromisoformat(profile['created_at'].replace('Z','+00:00'))
    days = (datetime.now(timezone.utc)-created).days
    langs = Counter(r['language'] for r in repos if r.get('language') and not r.get('fork'))
    return {
        'username': profile['login'], 'name': profile.get('name') or profile['login'],
        'location': profile.get('location') or '—', 'company': profile.get('company') or '—',
        'bio': profile.get('bio') or '—', 'blog': profile.get('blog') or '—',
        'email': profile.get('email') or '—', 'twitter': profile.get('twitter_username') or '—',
        'created': created.date().isoformat(), 'uptime': f'{days//365} years, {days%365} days',
        'repos': str(profile['public_repos']), 'followers': str(profile['followers']),
        'following': str(profile['following']), 'gists': str(profile['public_gists']),
        'stars': str(sum(r.get('stargazers_count',0) for r in repos)),
        'forks': str(sum(r.get('forks_count',0) for r in repos)),
        'languages': ', '.join(k for k,_ in langs.most_common(4)) or '—',
        **{key: (f"{snapshot['metrics'][key]:,}" if key in snapshot.get('metrics',{}) else 'N/A') for key in ['commits','prs','issues','loc','additions','deletions']},
    }
