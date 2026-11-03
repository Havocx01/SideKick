from pathlib import Path

import pytest
from dotenv import dotenv_values

from app.config import Settings
from app.hosted import HostedAccess
from scripts.create_hosted_login import createConfig, main


def test_generated_hosted_configuration_contains_no_plaintext_password(tmp_path, capsys):
    output = tmp_path / '.env.hosted'
    assert main(['--owner', 'adam', '--origin', 'https://sidekick.test', '--output', str(output), '--generate']) == 0
    password = output.with_name('.env.hosted.password').read_text().strip()
    assert len(password) >= 32
    assert password not in output.read_text() and password not in capsys.readouterr().out
    values = dotenv_values(output)
    settings = Settings(mode=values['SIDEKICK_MODE'], artifacts_dir=tmp_path / 'artifacts', hosted_owner=values['SIDEKICK_HOSTED_OWNER'],
        hosted_origin=values['SIDEKICK_HOSTED_ORIGIN'], hosted_password_hash=values['SIDEKICK_HOSTED_PASSWORD_HASH'])
    token, status = HostedAccess(settings).login('adam', password)
    assert status == 200 and token
    assert values['SIDEKICK_ASSISTANT_LIVE_ENABLED'] == values['SIDEKICK_HOSTED_MAX_CALLS'] == '0'


def test_hosted_setup_preserves_existing_files_and_rejects_insecure_origins(tmp_path):
    output = tmp_path / '.env.hosted'
    output.write_text('preserve')
    with pytest.raises(FileExistsError):
        createConfig('adam', 'https://sidekick.test', output, generate=True)
    assert output.read_text() == 'preserve'
    other = tmp_path / '.env.other'
    with pytest.raises(ValueError, match='HTTPS'):
        createConfig('adam', 'http://sidekick.test', other, generate=True)
    assert not other.exists() and not other.with_name('.env.other.password').exists()


def test_hosted_image_requires_auth_while_default_image_remains_demo():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / 'Dockerfile').read_text()
    assert dockerfile.rsplit('FROM ', 1)[1].strip() == 'demo AS public'
    assert 'FROM demo AS hosted' in dockerfile
    assert 'python scripts/check_hosted_config.py && exec uvicorn' in dockerfile
    from scripts import check_hosted_config as check
    from unittest.mock import patch
    with patch.object(check, 'get_settings', return_value=Settings(mode='full')):
        with pytest.raises(ValueError, match='configured owner'):
            check.main()
