"""Inspect public response field names; does not attack endpoints or recover secrets."""
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

from collect_live import API_URL


def main():
    report = {'checked_utc': datetime.now(timezone.utc).isoformat(), 'url': API_URL,
              'scope': 'One ordinary unauthenticated request to the existing public history endpoint. Field names only.'}
    try:
        response = requests.get(API_URL, params={'pageNo': 1, 'pageSize': 100}, timeout=10)
        report['http_status'] = response.status_code
        response.raise_for_status()
        payload = response.json()
        paths = set()
        def visit(value, prefix=''):
            if isinstance(value, dict):
                for key, item in value.items():
                    path = f'{prefix}.{key}' if prefix else str(key)
                    paths.add(path)
                    visit(item, path)
            elif isinstance(value, list):
                for item in value[:5]:
                    visit(item, prefix + '[]')
        visit(payload)
        report['field_paths'] = sorted(paths)
        report['possible_rng_metadata_fields'] = [p for p in sorted(paths) if any(term in p.lower() for term in ('seed', 'nonce', 'random', 'rng', 'commit', 'hash'))]
        report['conclusion'] = ('No seed, generator-state or commitment fields found in this response schema.'
                                if not report['possible_rng_metadata_fields'] else
                                'Potential metadata names found; names alone do not establish generator details or recover a seed.')
    except (requests.RequestException, ValueError) as exc:
        report['error'] = str(exc)
        report['conclusion'] = 'Could not verify the current public response schema.'
    destination = Path(__file__).resolve().parents[1] / 'results/api_rng_metadata_audit.json'
    destination.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
