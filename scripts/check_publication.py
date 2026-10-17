"""Scan exact Git index blobs without printing secret values."""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.config import Settings


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def main():
    settings = Settings()
    secrets = [value.get_secret_value() for value in
               (settings.exa_api_key, settings.tavily_api_key, settings.llm_api_key)
               if value.get_secret_value()]
    files = [name for name in git("ls-files", "-z").decode().split("\0") if name]
    if not files:
        print('No indexed files to scan.', file=sys.stderr)
        return True
    findings = []
    reviewed_fixtures = []
    patterns = {
        "private-key": rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        "github-token": rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})",
        "aws-access-key": rb"(?:AKIA|ASIA)[A-Z0-9]{16}",
        "openai-token": rb"sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}",
        "personal-email": rb"[\w.+-]+@(?:gmail|hotmail|outlook|yahoo)\.com",
        "local-user-path": rb"(?i)[A-Z]:[/\\]+Users[/\\]+[^/\\\s]+",
        "credential-url": rb"https?://[^\s/:]+:[^\s/@]+@",
    }
    for name in files:
        path = Path(name)
        if (any(part in {'.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache',
                             'dist', 'build', 'data', 'artifacts', 'checkpoints', '.agents', '.codex'}
                for part in path.parts)
            or path.name.startswith('.env') and path.name != '.env.example'
            or re.search(r'\.(?:db|sqlite3?|pem|key|webm|mp4|png|zip)(?:-|$)', name)):
            findings.append({"file": name, "rule": "private-or-generated-path"})
        content = git("show", ":" + name)
        for secret in secrets:
            if secret.encode() in content:
                findings.append({"file": name, "rule": "configured-secret"})
        for rule, pattern in patterns.items():
            for match in re.finditer(pattern, content):
                if (name == 'tests/test_evidence.py' and rule == 'credential-url'
                    and match.group() == b'https://' + b'user:secret@'):
                    reviewed_fixtures.append({"file": name, "rule": rule,
                                              "reason": "Reserved example.org URL rejection fixture"})
                    continue
                findings.append({"file": name, "line": content[:match.start()].count(b'\n') + 1,
                                 "rule": rule})
        if name == '.env.example':
            for line in content.decode().splitlines():
                if re.match(r'^\s*\w*(?:KEY|TOKEN|PASSWORD|SECRET)\s*=', line):
                    if line.split('=', 1)[1].strip() not in {'', '""', "''"}:
                        findings.append({"file": name, "rule": "nonempty-example-secret"})
    print(json.dumps({"files_scanned": len(files), "findings": findings,
                      "reviewed_test_fixtures": reviewed_fixtures}, indent=2))
    return bool(findings)


if __name__ == '__main__':
    raise SystemExit(main())
