"""Fixed features from one completed two-axis vibration recording."""
import numpy as np

AXES = ('horizontal', 'vertical')
FEATURE_KINDS = ('rms', 'kurtosis', 'crest_factor', 'peak_to_peak', 'band_low_energy', 'band_mid_energy', 'band_high_energy')


def featureSchema(samplingHz=25600):
    definitions = {
        'rms': ('source units', 'Square root of mean squared raw acceleration.'),
        'kurtosis': ('dimensionless', 'Population central fourth moment / variance squared; zero for constant recordings.'),
        'crest_factor': ('dimensionless', 'Maximum absolute raw acceleration / RMS; zero for an all-zero recording.'),
        'peak_to_peak': ('source units', 'Maximum raw acceleration minus minimum raw acceleration.'),
        'band_low_energy': ('source units squared', 'Mean-centered one-sided spectral energy in [0, 1000) Hz.'),
        'band_mid_energy': ('source units squared', 'Mean-centered one-sided spectral energy in [1000, 5000) Hz.'),
        'band_high_energy': ('source units squared', f'Mean-centered one-sided spectral energy in [5000, {samplingHz/2:g}] Hz.'),
    }
    return {f'{axis}_{kind}': {'source_channel': axis, 'unit': unit, 'definition': definition}
        for axis in AXES for kind, (unit, definition) in definitions.items()}


def extractVibration(samples, samplingHz=25600):
    values = np.asarray(samples, dtype=float)
    if values.ndim != 2 or values.shape[1] != 2 or len(values) < 2 or not np.isfinite(values).all():
        raise ValueError('A vibration recording needs at least two finite samples on each of two axes')
    if not np.isfinite(samplingHz) or samplingHz <= 10000:
        raise ValueError('The sampling rate must exceed 10000 Hz for the declared bands')
    centered = values - values.mean(axis=0)
    variance = np.mean(centered**2, axis=0)
    rms = np.sqrt(np.mean(values**2, axis=0))
    kurtosis = np.divide(np.mean(centered**4, axis=0), variance**2, out=np.zeros(2), where=variance > 0)
    crest = np.divide(np.max(np.abs(values), axis=0), rms, out=np.zeros(2), where=rms > 0)
    power = np.abs(np.fft.rfft(centered, axis=0))**2 / len(values)**2
    if len(values) % 2:
        power[1:] *= 2
    else:
        power[1:-1] *= 2
    frequencies = np.fft.rfftfreq(len(values), d=1/samplingHz)
    bands = [power[frequencies < 1000].sum(axis=0), power[(frequencies >= 1000) & (frequencies < 5000)].sum(axis=0),
        power[frequencies >= 5000].sum(axis=0)]
    features = [rms, kurtosis, crest, np.ptp(values, axis=0), *bands]
    result = {f'{axis}_{kind}': float(feature[index]) for index, axis in enumerate(AXES)
        for kind, feature in zip(FEATURE_KINDS, features, strict=True)}
    if not np.isfinite(list(result.values())).all():
        raise ValueError('Vibration feature extraction produced non-finite values')
    return result
