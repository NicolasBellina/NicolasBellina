#!/usr/bin/env python3
"""Génère les cartes du profil à partir des seules données publiques GitHub."""
import json
import os
import re
import time
from collections import Counter
from datetime import date, datetime, timedelta
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

USER = os.environ.get('GITHUB_USERNAME', 'NicolasBellina')
if not re.fullmatch(r'[A-Za-z0-9-]+', USER):
    raise ValueError('Identifiant GitHub invalide')
TODAY = datetime.now(ZoneInfo('Europe/Paris')).date()
START = date(TODAY.year, 1, 1)
OUTPUT = Path(__file__).resolve().parents[1] / 'assets'


def fetch(url, api=False):
    headers = {'User-Agent': 'github-profile-public-stats', 'Accept': 'application/vnd.github+json' if api else 'text/html'}
    # Le jeton automatique du workflow ne va qu'à l'API GitHub officielle.
    token = os.environ.get('GITHUB_TOKEN')
    if api and token:
        headers['Authorization'] = f'Bearer {token}'
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers=headers), timeout=45) as response:
                body = response.read().decode('utf-8')
            return json.loads(body) if api else body
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


class Calendar(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cells, self.days = {}, {}
        self.tooltip, self.parts = None, []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'data-date' in attrs and 'id' in attrs:
            self.cells[attrs['id']] = date.fromisoformat(attrs['data-date'])
        if tag == 'tool-tip':
            self.tooltip, self.parts = attrs.get('for'), []

    def handle_data(self, text):
        if self.tooltip is not None:
            self.parts.append(text)

    def handle_endtag(self, tag):
        if tag == 'tool-tip' and self.tooltip is not None:
            day = self.cells.get(self.tooltip)
            text = ''.join(self.parts).strip()
            count = re.match(r'([\d,]+) contributions?\b', text)
            if day is not None:
                if count:
                    self.days[day] = int(count.group(1).replace(',', ''))
                elif text.startswith('No contributions'):
                    self.days[day] = 0
                else:
                    raise ValueError(f'Calendrier GitHub non reconnu : {text}')
            self.tooltip = None


def streaks(days, today):
    end = today if days.get(today, 0) else today - timedelta(days=1)
    current = 0
    while days.get(end, 0):
        current += 1
        end -= timedelta(days=1)
    longest = run = 0
    previous = None
    for day, count in sorted(days.items()):
        run = (run + 1 if previous == day - timedelta(days=1) else 1) if count else 0
        longest = max(longest, run)
        previous = day
    return current, longest


def text(x, y, value, size=14, fill='#c9d1d9', weight=400, anchor='start'):
    return f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{escape(str(value))}</text>'


def card(title, body, height=240):
    stamp = TODAY.strftime('%d/%m/%Y')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="520" height="{height}" viewBox="0 0 520 {height}" role="img" aria-labelledby="title desc">'
            f'<title id="title">{escape(title)}</title><desc id="desc">Données publiques de {escape(USER)}, mises à jour le {stamp}.</desc>'
            '<rect width="520" height="100%" rx="12" fill="#0d1117"/><g font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif">'
            + text(24, 35, title, 19, '#58a6ff', 600) + body
            + text(24, height - 17, f'Données publiques · Mis à jour le {stamp}', 11, '#8b949e') + '</g></svg>\n')


def generate():
    profile = fetch(f'https://api.github.com/users/{USER}', api=True)
    repos = []
    page = 1
    while True:
        batch = fetch(f'https://api.github.com/users/{USER}/repos?type=owner&per_page=100&page={page}', api=True)
        repos.extend(r for r in batch if not r.get('private'))
        if len(batch) < 100:
            break
        page += 1
    owned = [r for r in repos if not r['fork']]
    languages = Counter()
    for repo in owned:
        languages.update(fetch(f"https://api.github.com/repos/{USER}/{repo['name']}/languages", api=True))
    parser = Calendar()
    parser.feed(fetch(f'https://github.com/users/{USER}/contributions?from={TODAY.year}-01-01&to={TODAY.year}-12-31'))
    days = {d: n for d, n in parser.days.items() if START <= d <= TODAY}
    if len(days) != (TODAY - START).days + 1:
        raise ValueError("Le calendrier public de l’année est incomplet.")
    total = sum(days.values())
    current, longest = streaks(days, TODAY)
    rows = [('Dépôts publics', len(repos)), ('Étoiles reçues', sum(r['stargazers_count'] for r in owned)),
            ('Forks reçus', sum(r['forks_count'] for r in owned)), ('Abonnés', profile['followers']),
            (f'Contributions en {TODAY.year}', total)]
    stats = ''.join(text(24, 72 + i * 29, label) + text(492, 72 + i * 29, value, 15, '#f0f6fc', 600, 'end') for i, (label, value) in enumerate(rows))
    top = languages.most_common(6)
    all_bytes = sum(languages.values())
    colors = {'Dart': '#00b4ab', 'Java': '#b07219', 'HTML': '#e34c26', 'Vue': '#41b883', 'JavaScript': '#f1e05a',
              'TypeScript': '#3178c6', 'CSS': '#563d7c', 'Kotlin': '#a97bff', 'Swift': '#f05138', 'Python': '#3572a5'}
    lang_body = ''
    for i, (name, count) in enumerate(top):
        x, y = 24 + (i % 2) * 248, 78 + (i // 2) * 48
        color = colors.get(name, '#8b949e')
        percent = 100 * count / all_bytes
        lang_body += f'<circle cx="{x + 5}" cy="{y - 5}" r="5" fill="{color}"/>'
        lang_body += text(x + 18, y, name, 13) + text(x + 220, y, f'{percent:.1f} %', 12, '#8b949e', anchor='end')
        lang_body += f'<rect x="{x}" y="{y + 10}" width="220" height="5" rx="2.5" fill="#21262d"/><rect x="{x}" y="{y + 10}" width="{220 * count / all_bytes:.2f}" height="5" rx="2.5" fill="{color}"/>'
    if not top:
        lang_body = text(24, 85, 'Aucun langage détecté dans les dépôts publics.')
    lang_body += text(24, 210, 'Répartition du code des dépôts publics, hors forks.', 11, '#8b949e')
    streak_body = ''
    for x, value, label in [(92, total, 'Contributions'), (260, current, 'Série actuelle'), (428, longest, f'Record de {TODAY.year}')]:
        streak_body += text(x, 103, value, 34, '#58a6ff', 700, 'middle') + text(x, 134, label, 12, anchor='middle')
    streak_body += text(260, 165, f'Séries en jours consécutifs · Année {TODAY.year}', 12, '#8b949e', anchor='middle')
    # Tout calculer avant d'écrire : une erreur réseau ne publie pas des cartes vides.
    images = {'github-stats.svg': card('Statistiques GitHub', stats),
              'top-languages.svg': card('Langages les plus utilisés', lang_body),
              'github-streak.svg': card(f'Activité GitHub · {TODAY.year}', streak_body, 215)}
    OUTPUT.mkdir(exist_ok=True)
    for filename, content in images.items():
        (OUTPUT / filename).write_text(content, encoding='utf-8')
    print(f'{len(images)} cartes générées ; {len(repos)} dépôts publics ; {total} contributions en {TODAY.year}.')


if __name__ == '__main__':
    generate()
