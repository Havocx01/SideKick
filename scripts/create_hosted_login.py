"""Create a private hosted configuration without printing credentials."""
import argparse
import getpass
import os
from pathlib import Path
import secrets
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))

from app.config import Settings
from app.hosted import hashPassword


def writePrivate(path, text):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        stream.write(text)


def createConfig(owner, origin, output, *, password=None, generate=False):
    if generate == (password is not None):
        raise ValueError('Choose a supplied password or generate one')
    output = Path(output)
    passwordPath = output.with_name(output.name + '.password')
    if output.exists() or (generate and passwordPath.exists()):
        raise FileExistsError('Choose a new configuration path; existing credentials are preserved')
    password = secrets.token_urlsafe(32) if generate else password
    settings = Settings(mode='full', hosted_owner=owner, hosted_origin=origin.rstrip('/'), hosted_password_hash=hashPassword(password),
        assistant_live_enabled=False)
    lines = ['SIDEKICK_MODE=full', f'SIDEKICK_HOSTED_OWNER={settings.hosted_owner}',
        f'SIDEKICK_HOSTED_ORIGIN={settings.hosted_origin}', f'SIDEKICK_HOSTNAME={urlsplit(settings.hosted_origin).netloc}',
        f"SIDEKICK_HOSTED_PASSWORD_HASH='{settings.hosted_password_hash}'", 'SIDEKICK_ASSISTANT_LIVE_ENABLED=0',
        'SIDEKICK_HOSTED_MAX_CALLS=0', 'SIDEKICK_HOSTED_MAX_COMPLETION_TOKENS=0', 'SIDEKICK_HOSTED_MAX_SEARCHES=0',
        'SIDEKICK_HOSTED_MAX_MUTATIONS=200', 'SIDEKICK_MLFLOW=0']
    output.parent.mkdir(parents=True, exist_ok=True)
    if generate:
        writePrivate(passwordPath, password + '\n')
    writePrivate(output, '\n'.join(lines) + '\n')
    return passwordPath if generate else None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--origin', required=True, help='Public HTTPS origin, such as https://workspace.example.com.')
    parser.add_argument('--output', type=Path, default=Path('.env.hosted'))
    parser.add_argument('--generate', action='store_true', help='Save a random password beside the configuration, instead of prompting.')
    args = parser.parse_args(argv)
    password = None
    if not args.generate:
        password = getpass.getpass('Workspace password: ')
        if password != getpass.getpass('Confirm password: '):
            raise ValueError('Passwords do not match')
    passwordPath = createConfig(args.owner, args.origin, args.output, password=password, generate=args.generate)
    print(f'Configuration saved to {args.output.resolve()}')
    if passwordPath:
        print(f'Password saved privately to {passwordPath.resolve()}; store it in your password manager.')
    print('Live AI is disabled and daily paid allowances are zero. No server was deployed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
