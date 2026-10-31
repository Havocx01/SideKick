"""Trusted local accelerometer recordings and channel-level measurement faults."""
from dataclasses import dataclass, replace
import hashlib
import io
from pathlib import Path
import re

import numpy as np

from app.faults.inject import resolve_onset
from app.faults.scenarios import CaseApplication, ComponentApplication, fingerprint
from app.features.vibration import AXES, extractVibration, featureSchema
from app.schemas import FaultDuration, FaultKind


@dataclass(frozen=True)
class RawRecording:
    path: str
    sha256: str
    features: tuple[float, ...]
    mean: tuple[float, float]
    variance: tuple[float, float]
    extracted: tuple[float, ...]


def datasetBinding(dataset):
    frame = dataset.frame
    names = tuple(dataset.sensors)
    if not dataset.config.exclude_failure_cycle:
        raise ValueError('Raw vibration requires an excluded failure target')
    if not names or len(set(names)) != len(names) or not set(names) <= set(featureSchema()):
        raise ValueError('Raw vibration requires untransformed declared vibration feature columns')
    if not frame.columns.is_unique or not {'equipment_id', 'cycle', 'rul', 'failure_cycle', *names} <= set(frame.columns):
        raise ValueError('Raw vibration requires complete canonical feature histories')
    ids = frame.equipment_id.to_numpy()
    if not len(ids) or any(not isinstance(id, str) or not id for id in ids):
        raise ValueError('Raw vibration requires nonempty equipment identities')
    groups = [id for index, id in enumerate(ids) if index == 0 or id != ids[index-1]]
    if len(groups) != len(set(groups)):
        raise ValueError('Raw vibration histories must occupy contiguous blocks')
    digest = hashlib.sha256()
    digest.update(fingerprint({'features': names, 'config': dataset.config.as_dict()}).encode())
    for id, history in frame.groupby('equipment_id', sort=True):
        cycles = np.arange(1, len(history)+1)
        if (not np.array_equal(history.cycle.to_numpy(), cycles)
                or not np.array_equal(history.rul.to_numpy(), len(history)-cycles)
                or not np.equal(history.failure_cycle.to_numpy(), len(history)).all()):
            raise ValueError('Raw recordings must map one-to-one to complete consecutive histories')
        values = history[list(names)].to_numpy(dtype='<f8')
        if not np.isfinite(values).all():
            raise ValueError('Clean raw vibration features must be finite')
        digest.update(fingerprint({'equipment': id, 'recordings': len(history)}).encode())
        digest.update(np.ascontiguousarray(values).tobytes())
    return digest.hexdigest()


@dataclass
class RawVibrationSource:
    root: Path
    recordings: dict[str, tuple[RawRecording, ...]]
    featureNames: tuple[str, ...]
    samplingHz: float
    samplesPerRecording: int
    binding: str

    sensors = AXES

    @classmethod
    def prepare(cls, root, histories, dataset, samplingHz=25600, samplesPerRecording=32768, *, check=None):
        binding = datasetBinding(dataset)
        if (not isinstance(samplesPerRecording, int) or isinstance(samplesPerRecording, bool) or samplesPerRecording < 2
                or not np.isfinite(samplingHz) or samplingHz <= 10000):
            raise ValueError('Raw vibration sampling and burst size must match the declared feature bands')
        ids = set(dataset.frame.equipment_id)
        if not isinstance(histories, dict) or set(histories) != ids:
            raise ValueError('Raw source histories must match exactly the admitted development histories')
        root = Path(root).resolve()
        if not root.is_dir():
            raise ValueError('Choose an existing trusted local raw source directory')
        source = cls(root, {}, tuple(dataset.sensors), float(samplingHz), samplesPerRecording, binding)
        seen = set()
        for id in sorted(histories):
            rows = histories[id]
            history = dataset.frame[dataset.frame.equipment_id == id]
            if not isinstance(rows, (tuple, list)) or len(rows) != len(history):
                raise ValueError('Raw recording count differs from its complete feature history')
            records = []
            for index, row in enumerate(rows):
                if not isinstance(row, dict) or set(row) != {'path', 'sha256'} or not isinstance(row['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', row['sha256']):
                    raise ValueError('Each raw recording needs its relative path and SHA-256 checksum')
                path = source._path(row['path'])
                if path in seen:
                    raise ValueError('A raw recording cannot belong to multiple history rows')
                seen.add(path)
                record = RawRecording(row['path'], row['sha256'], (), (), (), ())
                samples = source._read(record, check=check)
                features = extractVibration(samples, source.samplingHz)
                values = history.iloc[index][list(source.featureNames)].to_numpy(dtype=float)
                expected = np.array([features[name] for name in source.featureNames])
                if not np.allclose(values, expected, rtol=1e-12, atol=1e-12):
                    raise ValueError('Clean feature values differ from their raw recording; transformed/startup references are unsupported')
                records.append(RawRecording(record.path, record.sha256, tuple(values), tuple(samples.mean(axis=0)),
                    tuple(samples.var(axis=0)), tuple(features[name] for name in featureSchema(source.samplingHz))))
            source.recordings[id] = tuple(records)
        return source

    @property
    def historyIds(self):
        return {id: fingerprint({'raw_vibration_history': 1, 'recordings': [row.sha256 for row in records]})
            for id, records in self.recordings.items()}

    @property
    def fingerprint(self):
        return fingerprint({'raw_vibration_source': 1, 'samplingHz': self.samplingHz, 'samplesPerRecording': self.samplesPerRecording,
            'featureNames': self.featureNames, 'schema': featureSchema(self.samplingHz), 'binding': self.binding,
            'recordings': {id: [{'path': row.path, 'sha256': row.sha256, 'features': row.features, 'mean': row.mean,
                'variance': row.variance, 'extracted': row.extracted}
                for row in records] for id, records in self.recordings.items()}})

    def forDataset(self, dataset):
        binding = datasetBinding(dataset)
        if set(dataset.frame.equipment_id) != set(self.recordings):
            raise ValueError('Raw source histories must match exactly the admitted development histories')
        columns = [list(featureSchema(self.samplingHz)).index(name) for name in dataset.sensors]
        recordings = {}
        for id, records in self.recordings.items():
            values = dataset.frame.loc[dataset.frame.equipment_id == id, dataset.sensors].to_numpy(dtype=float)
            expected = np.array([row.extracted for row in records])[:, columns]
            if values.shape != expected.shape or not np.allclose(values, expected, rtol=1e-12, atol=1e-12):
                raise ValueError('Clean feature values differ from the prepared raw recording; transformed/startup references are unsupported')
            recordings[id] = tuple(replace(row, features=tuple(values[index])) for index, row in enumerate(records))
        return RawVibrationSource(self.root, recordings, tuple(dataset.sensors), self.samplingHz, self.samplesPerRecording, binding)

    def _path(self, relative):
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            raise ValueError('Raw recording paths must be relative to their trusted source directory')
        path = self.root / relative
        resolved = path.resolve()
        if not resolved.is_relative_to(self.root) or path.is_symlink() or not path.is_file():
            raise ValueError('Raw recordings must be regular files inside the trusted source directory')
        return resolved

    def _read(self, record, *, check=None):
        if check is not None:
            check()
        raw = self._path(record.path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != record.sha256:
            raise ValueError('Raw recording checksum differs from its prepared source')
        if check is not None:
            check()
        samples = np.loadtxt(io.BytesIO(raw), delimiter=',', skiprows=1)
        if samples.shape != (self.samplesPerRecording, 2) or not np.isfinite(samples).all():
            raise ValueError('Raw recording must contain the declared finite two-axis sample burst')
        return samples

    def verify(self, *, check=None):
        for records in self.recordings.values():
            for record in records:
                if check is not None:
                    check()
                digest = hashlib.sha256()
                with self._path(record.path).open('rb') as stream:
                    for chunk in iter(lambda: stream.read(1024*1024), b''):
                        if check is not None:
                            check()
                        digest.update(chunk)
                if digest.hexdigest() != record.sha256:
                    raise ValueError('Raw recording checksum differs from its prepared source')

    def validate(self, dataset):
        if (tuple(dataset.sensors) != self.featureNames or set(dataset.frame.equipment_id) != set(self.recordings)
                or datasetBinding(dataset) != self.binding):
            raise ValueError('Raw source feature binding differs from the admitted development dataset')
        for id, records in self.recordings.items():
            values = dataset.frame.loc[dataset.frame.equipment_id == id, list(self.featureNames)].to_numpy(dtype=float)
            if values.shape != (len(records), len(self.featureNames)) or not np.array_equal(values, np.array([row.features for row in records])):
                raise ValueError('Raw source feature values differ from their prepared recording mapping')

    def scale(self, trainingIds, dataset):
        self.validate(dataset)
        if not trainingIds or len(set(trainingIds)) != len(trainingIds) or not set(trainingIds) <= set(self.recordings):
            raise ValueError('Raw sample scale requires unique known training histories')
        selected, scorable = [], dataset.scorable_mask()
        for id in trainingIds:
            indices = np.flatnonzero(dataset.frame.equipment_id.to_numpy() == id)
            selected.extend(record for index, record in zip(indices, self.recordings[id], strict=True) if scorable[index])
        if not selected:
            raise ValueError('Raw sample scale needs scorable training recordings')
        means = np.array([row.mean for row in selected])
        variance = np.array([row.variance for row in selected])
        total = (variance + (means-means.mean(axis=0))**2).mean(axis=0)
        if not np.isfinite(total).all() or (total < 0).any():
            raise ValueError('Prepared raw sample statistics are invalid')
        return {axis: float(np.sqrt(total[index])) for index, axis in enumerate(AXES)}

    def apply(self, equipment, rul, case, builder, config, *, rawScale, check=None):
        if equipment not in self.recordings or tuple(builder.sensors) != self.featureNames:
            raise ValueError('Raw source does not match the selected history and feature builder')
        records = self.recordings[equipment]
        if not np.array_equal(np.asarray(rul), np.arange(len(records)-1, -1, -1)):
            raise ValueError('Raw source remaining-life indices differ from the complete history')
        if set(rawScale) != set(AXES) or any(not np.isfinite(value) or value < 0 for value in rawScale.values()):
            raise ValueError('Raw source needs finite nonnegative training scales for each axis')
        values = np.array([row.features for row in records])
        plans, reasons = [], []
        for atom in case.components:
            if atom.sensor not in AXES:
                reasons.append(f'{atom.sensor}: raw accelerometer axis not present')
                continue
            injectionConfig = replace(config, base_seed=atom.seed) if atom.onset_before_failure is None else config
            onset, reason = resolve_onset(rul, atom, injectionConfig)
            if onset is None:
                reasons.append(f'{atom.sensor}: {reason}')
                continue
            stop = min(len(records), onset+atom.length) if atom.duration == FaultDuration.transient else len(records)
            if atom.kind == FaultKind.drift and rawScale[atom.sensor] <= 0:
                reasons.append(f'{atom.sensor}: no raw training variation')
                continue
            plans.append((atom, onset, stop))
        if reasons:
            return CaseApplication(None, False, (), tuple(reasons))
        held = {}
        for atom, onset, _ in plans:
            if atom.kind == FaultKind.stuck:
                previous = self._read(records[max(0, onset-1)], check=check)
                held[atom.sensor] = previous[-1, AXES.index(atom.sensor)]
        changed = {atom.sensor: False for atom, _, _ in plans}
        for index, record in enumerate(records):
            active = [(atom, onset) for atom, onset, stop in plans if onset <= index < stop]
            if not active:
                continue
            samples = self._read(record, check=check)
            for atom, onset in active:
                axis = AXES.index(atom.sensor)
                original = samples[:, axis].copy()
                if atom.kind == FaultKind.dropout:
                    samples[:, axis] = 0
                    changed[atom.sensor] = True
                elif atom.kind == FaultKind.stuck:
                    samples[:, axis] = held[atom.sensor]
                    changed[atom.sensor] |= not np.array_equal(original, samples[:, axis])
                elif atom.kind == FaultKind.drift:
                    progress = min((index-onset+1)/atom.ramp_cycles, 1.)
                    samples[:, axis] += atom.sign*atom.severity_sd*rawScale[atom.sensor]*progress
                    changed[atom.sensor] |= not np.array_equal(original, samples[:, axis])
            if check is not None:
                check()
            features = extractVibration(samples, self.samplingHz)
            for atom, _ in active:
                for column, name in enumerate(self.featureNames):
                    if name.startswith(atom.sensor + '_'):
                        values[index, column] = np.nan if atom.kind == FaultKind.dropout else features[name]
        if not all(changed.values()):
            reasons = tuple(f'{axis}: no raw readings changed' for axis, applied in changed.items() if not applied)
            return CaseApplication(None, False, (), reasons)
        applications = tuple(ComponentApplication(sensor=atom.sensor, onset_index=onset, affected_cycles=stop-onset) for atom, onset, stop in plans)
        return CaseApplication(values, True, applications, ())
