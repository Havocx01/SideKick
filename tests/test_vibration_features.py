import numpy as np
import pytest

from app.features.vibration import FEATURE_KINDS, featureSchema, extractVibration


def test_zero_and_constant_bursts_have_finite_defined_features():
    for value in (0., 3.):
        result = extractVibration(np.full((32768, 2), value))
        assert len(result) == 2 * len(FEATURE_KINDS)
        assert all(np.isfinite(list(result.values())))
        for axis in ('horizontal', 'vertical'):
            assert result[f'{axis}_rms'] == value
            assert result[f'{axis}_kurtosis'] == 0
            assert result[f'{axis}_crest_factor'] == (1 if value else 0)
            assert result[f'{axis}_peak_to_peak'] == 0
            assert sum(result[f'{axis}_band_{band}_energy'] for band in ('low', 'mid', 'high')) == 0


def test_sine_bands_and_parseval_match_known_energy():
    time = np.arange(32768) / 25600
    samples = np.column_stack([2*np.sin(2*np.pi*400*time), np.sin(2*np.pi*2000*time)])
    result = extractVibration(samples)
    assert result['horizontal_rms'] == pytest.approx(np.sqrt(2), abs=1e-12)
    assert result['horizontal_band_low_energy'] == pytest.approx(2., abs=1e-12)
    assert result['vertical_band_mid_energy'] == pytest.approx(.5, abs=1e-12)
    assert result['horizontal_kurtosis'] == pytest.approx(1.5, abs=1e-12)
    assert result['vertical_crest_factor'] == pytest.approx(np.sqrt(2), abs=1e-12)
    for index, axis in enumerate(('horizontal', 'vertical')):
        energy = sum(result[f'{axis}_band_{band}_energy'] for band in ('low', 'mid', 'high'))
        assert energy == pytest.approx(samples[:, index].var(), abs=1e-12)


@pytest.mark.parametrize('length', [255, 256])
def test_one_sided_power_handles_even_and_odd_lengths(length):
    samples = np.random.default_rng(7).normal(size=(length, 2))
    result = extractVibration(samples)
    for index, axis in enumerate(('horizontal', 'vertical')):
        energy = sum(result[f'{axis}_band_{band}_energy'] for band in ('low', 'mid', 'high'))
        assert energy == pytest.approx(samples[:, index].var(), rel=1e-12)


def test_channels_and_recordings_are_independent_and_inputs_unchanged():
    samples = np.random.default_rng(8).normal(size=(32768, 2))
    saved = samples.copy()
    result = extractVibration(samples)
    changed = samples.copy()
    changed[:, 1] *= 5
    after = extractVibration(changed)
    assert all(result[name] == after[name] for name in result if name.startswith('horizontal_'))
    extractVibration(np.full((32768, 2), 20.))
    assert extractVibration(samples) == result
    np.testing.assert_array_equal(samples, saved)


def test_schema_covers_every_feature_with_source_channel_and_units():
    schema = featureSchema()
    result = extractVibration(np.ones((20, 2)))
    assert set(schema) == set(result)
    for name, info in schema.items():
        assert info['source_channel'] in ('horizontal', 'vertical')
        assert name.startswith(info['source_channel'] + '_')
        assert info['unit'] and info['definition']


@pytest.mark.parametrize('samples', [np.zeros(20), np.zeros((1, 2)), np.zeros((20, 3)), np.full((20, 2), np.nan), np.full((20, 2), np.inf)])
def test_invalid_bursts_are_rejected(samples):
    with pytest.raises(ValueError):
        extractVibration(samples)


def test_sampling_rate_must_cover_the_declared_bands():
    with pytest.raises(ValueError, match='sampling'):
        extractVibration(np.zeros((20, 2)), samplingHz=8000)
