"""Create only the project's Free Render service; keep credentials out of output."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import Settings
from psycopg.conninfo import conninfo_to_dict

REPOSITORY = 'https://github.com/Uzair-Ibrahim/The-Daily-Minds'
NAME = 'the-daily-mind'


def main():
    settings = Settings()
    values = {'DATABASE_BACKEND': 'postgres', 'DATABASE_URL': settings.database_url.get_secret_value(),
              'DATABASE_SCHEMA': 'daily_mind', 'SUPABASE_AUTH_ENABLED': 'true',
              'SUPABASE_URL': settings.supabase_url, 'SUPABASE_PUBLISHABLE_KEY': settings.supabase_publishable_key,
              'STORY_SEMANTIC_ENABLED': 'false', 'CREDIT_SEARCH_CONFIRMED_FREE': 'false',
              'LLM_PROVIDER': 'none', 'DAILY_GENERATION_ENABLED': 'true', 'LOG_LEVEL': 'INFO'}
    if not all(values[key] for key in ['DATABASE_URL', 'SUPABASE_URL', 'SUPABASE_PUBLISHABLE_KEY']):
        raise RuntimeError('Configure the required connection values privately in .env first.')
    executable = shutil.which('render')
    if not executable and os.name == 'nt':
        installed = Path(os.environ['LOCALAPPDATA']) / 'Microsoft/WinGet/Packages'
        candidates = list(installed.glob('Render.CLI_*/render.exe'))
        executable = str(candidates[0]) if candidates else None
    if not executable:
        raise RuntimeError('Install the official Render CLI and run render login first.')

    def run(arguments):
        result = subprocess.run([executable, *arguments, '--output', 'json'], capture_output=True, text=True, timeout=90)
        if result.returncode:
            message = result.stderr or result.stdout or 'Render CLI request failed.'
            for value in [*values.values(), conninfo_to_dict(values['DATABASE_URL']).get('password', '')]:
                if value:
                    message = message.replace(value, '[REDACTED]')
            raise RuntimeError(message[:1200])
        return json.loads(result.stdout)

    services = run(['services'])
    matches = [item.get('service', item) for item in services
               if item.get('service', item).get('repo', '').rstrip('/') == REPOSITORY
               and item.get('service', item).get('name') == NAME]
    if len(matches) > 1:
        raise RuntimeError('Multiple project services exist; inspect before creating another.')
    if matches:
        service = matches[0]
        if service.get('serviceDetails', {}).get('plan') != 'free':
            raise RuntimeError('Existing service is not Free. No change was made.')
        created = False
    else:
        arguments = ['services', 'create', '--name', NAME, '--type', 'web_service', '--runtime', 'docker',
                     '--repo', REPOSITORY, '--branch', 'main', '--region', 'singapore', '--plan', 'free',
                     '--num-instances', '1', '--health-check-path', '/health', '--auto-deploy=false', '--confirm']
        for key, value in values.items():
            arguments.extend(['--env-var', f'{key}={value}'])
        response = run(arguments)
        service = response.get('service', response)
        created = True
    record = {'service_id': service['id'], 'url': service.get('serviceDetails', {}).get('url'),
              'plan': service.get('serviceDetails', {}).get('plan'), 'created': created,
              'dashboard_url': service.get('dashboardUrl'), 'name': service.get('name')}
    if record['plan'] != 'free':
        raise RuntimeError('Free plan could not be confirmed; stop and inspect the service.')
    (ROOT / 'artifacts').mkdir(exist_ok=True)
    (ROOT / 'artifacts/render-service.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        print(str(error) if isinstance(error, RuntimeError) else 'Render CLI request timed out; inspect services before retrying.')
        raise SystemExit(1)
