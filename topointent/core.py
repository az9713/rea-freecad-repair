"""Pure, dependency-free design-intent matching. No document mutation occurs here.

This deliberately supports only axis-aligned planar boundary faces. It is not a
topological naming replacement: candidates must satisfy every declared predicate,
and multiple matches are a refusal, never an invitation to choose the nearest.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import Tuple

Vec3 = Tuple[float, float, float]


@dataclass(frozen=True)
class Face:
    ref: str
    surface: str
    area: float
    center: Vec3
    normal: Vec3


@dataclass(frozen=True)
class Snapshot:
    faces: Tuple[Face, ...]
    minimum: Vec3
    maximum: Vec3
    volume: float
    valid: bool
    solids: int
    edges: int

    def validate(self):
        values = list(self.minimum) + list(self.maximum) + [self.volume]
        if len(self.minimum) != 3 or len(self.maximum) != 3:
            raise ValueError('Expected three-dimensional bounds')
        if len({face.ref for face in self.faces}) != len(self.faces):
            raise ValueError('Duplicate face references')
        for face in self.faces:
            if len(face.center) != 3 or len(face.normal) != 3:
                raise ValueError('Expected three-dimensional face descriptors')
            values.extend([face.area, *face.center, *face.normal])
            if face.area <= 0:
                raise ValueError('Degenerate or nonpositive face area')
        if not all(math.isfinite(v) for v in values):
            raise ValueError('Non-finite geometry descriptor')
        if any(hi <= lo for lo, hi in zip(self.minimum, self.maximum)):
            raise ValueError('Degenerate bounds; solid geometry required')
        if self.volume <= 0:
            raise ValueError('Nonpositive solid volume')

    def fingerprint(self):
        payload = json.dumps(asdict(self), sort_keys=True, allow_nan=False,
                             separators=(',', ':'))
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class Intent:
    axis: int
    side: str
    normal_sign: int
    area_ratio_min: float = 0.25
    area_ratio_max: float = 4.0
    volume_ratio_min: float = 0.5
    volume_ratio_max: float = 2.0
    tolerance: float = 1e-6

    def validate(self):
        if self.axis not in (0, 1, 2) or self.side not in ('min', 'max'):
            raise ValueError('Unsupported axis/boundary intent')
        if self.normal_sign not in (-1, 1):
            raise ValueError('Normal sign must be -1 or +1')
        ratios = [self.area_ratio_min, self.area_ratio_max,
                  self.volume_ratio_min, self.volume_ratio_max, self.tolerance]
        if not all(math.isfinite(v) and v > 0 for v in ratios):
            raise ValueError('Positive finite tolerances/ratios required')
        if self.area_ratio_min > self.area_ratio_max or self.volume_ratio_min > self.volume_ratio_max:
            raise ValueError('Inverted invariant range')
        if self.tolerance >= 0.01:
            raise ValueError('Tolerance too permissive for this conservative matcher')


@dataclass(frozen=True)
class Capture:
    source_name: str
    baseline_ref: str
    baseline: Snapshot
    intent: Intent
    schema: int = 1

    def to_dict(self):
        return asdict(self)

    def fingerprint(self):
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True,
                                         allow_nan=False).encode()).hexdigest()

    @classmethod
    def from_dict(cls, value):
        if value.get('schema') != 1:
            raise ValueError('Unsupported capture schema')
        b = value['baseline']
        snapshot = Snapshot(tuple(Face(f['ref'], f['surface'], f['area'],
                                      tuple(f['center']), tuple(f['normal'])) for f in b['faces']),
                            tuple(b['minimum']), tuple(b['maximum']), b['volume'],
                            b['valid'], b['solids'], b['edges'])
        capture = cls(value['source_name'], value['baseline_ref'], snapshot,
                      Intent(**value['intent']))
        snapshot.validate()
        capture.intent.validate()
        return capture


def _normal_matches(face, intent):
    size = math.sqrt(sum(v * v for v in face.normal))
    if size == 0:
        return False
    unit = [v / size for v in face.normal]
    return (abs(unit[intent.axis] - intent.normal_sign) <= intent.tolerance and
            all(abs(v) <= intent.tolerance for i, v in enumerate(unit) if i != intent.axis))


def capture_boundary(source_name, snapshot, ref, **ranges):
    snapshot.validate()
    if not snapshot.valid or snapshot.solids != 1:
        raise ValueError('Capture requires one valid solid')
    matches = [f for f in snapshot.faces if f.ref == ref]
    if len(matches) != 1:
        raise ValueError('Selected face is not uniquely present')
    face = matches[0]
    if face.surface != 'Plane':
        raise ValueError('Only planar boundary faces are supported')
    axis = max(range(3), key=lambda a: abs(face.normal[a]))
    sign = 1 if face.normal[axis] > 0 else -1
    bound = snapshot.maximum if sign > 0 else snapshot.minimum
    intent = Intent(axis, 'max' if sign > 0 else 'min', sign, **ranges)
    intent.validate()
    scale = max(1.0, *(hi - lo for lo, hi in zip(snapshot.minimum, snapshot.maximum)))
    if not _normal_matches(face, intent) or abs(face.center[axis] - bound[axis]) > intent.tolerance * scale:
        raise ValueError('Selection is not an axis-aligned outer boundary plane')
    return Capture(source_name, ref, snapshot, intent)


def diagnose(capture, current):
    """Return an auditable match decision; never repair or rank away ambiguity."""
    capture.baseline.validate()
    capture.intent.validate()
    current.validate()
    intent = capture.intent
    baseline_faces = [f for f in capture.baseline.faces if f.ref == capture.baseline_ref]
    if len(baseline_faces) != 1:
        raise ValueError('Capture has no unique baseline face')
    old = baseline_faces[0]
    volume_ratio = current.volume / capture.baseline.volume
    if not math.isfinite(volume_ratio):
        raise ValueError('Non-finite derived volume ratio')
    failures = []
    if not current.valid:
        failures.append('OpenCASCADE shape validity failed')
    if current.solids != 1:
        failures.append('Expected exactly one solid')
    if not intent.volume_ratio_min <= volume_ratio <= intent.volume_ratio_max:
        failures.append('Volume ratio outside declared design-intent interval')
    axis = intent.axis
    boundary = (current.maximum if intent.side == 'max' else current.minimum)[axis]
    scale = max(1.0, *(hi - lo for lo, hi in zip(current.minimum, current.maximum)))
    candidates, decisions = [], []
    for face in current.faces:
        reasons = []
        if face.surface != 'Plane':
            reasons.append('surface is not Plane')
        if not _normal_matches(face, intent):
            reasons.append('normal violates orientation predicate')
        if abs(face.center[axis] - boundary) > intent.tolerance * scale:
            reasons.append('plane is not on declared outer boundary')
        ratio = face.area / old.area
        if not math.isfinite(ratio):
            raise ValueError('Non-finite derived area ratio')
        if not intent.area_ratio_min <= ratio <= intent.area_ratio_max:
            reasons.append('area ratio outside declared interval')
        if not reasons:
            candidates.append(face.ref)
        decisions.append({'ref': face.ref, 'accepted': not reasons, 'reasons': reasons,
                          'area_ratio': ratio})
    status = ('invalid' if failures else 'unique' if len(candidates) == 1 else
              'ambiguous' if len(candidates) > 1 else 'no_match')
    old_ref_passes = capture.baseline_ref in candidates
    selected = candidates[0] if status == 'unique' else None
    return {'schema': 1, 'status': status, 'candidate': selected,
            'candidates': candidates, 'failures': failures, 'face_decisions': decisions,
            'baseline_ref': capture.baseline_ref, 'old_ref_still_satisfies_intent': old_ref_passes,
            'reference_change_required': bool(selected and selected != capture.baseline_ref),
            'geometry_changed': current.fingerprint() != capture.baseline.fingerprint(),
            'current_fingerprint': current.fingerprint(),
            'capture_fingerprint': capture.fingerprint(),
            'volume_ratio': volume_ratio,
            'topology_delta': {'faces': len(current.faces) - len(capture.baseline.faces),
                               'edges': current.edges - capture.baseline.edges},
            'explanation': ('Only one face satisfies every declared predicate.' if status == 'unique' else
                            'Repair refused: geometry invalid or candidate not uniquely determined.'),
            'causality_limit': 'Descriptor comparison identifies the changed geometric condition; it does not reconstruct unrecorded edit history.'}


def require_current_unique(capture, current, preview):
    """Revalidate immediately before mutation and reject stale previews."""
    if capture.fingerprint() != preview.get('capture_fingerprint'):
        raise ValueError('Stale capture: design-intent predicates changed; analyze again')
    if current.fingerprint() != preview.get('current_fingerprint'):
        raise ValueError('Stale preview: source geometry changed; analyze again')
    result = diagnose(capture, current)
    if result['status'] != 'unique':
        raise ValueError('Repair requires exactly one validated candidate')
    if result['candidate'] != preview.get('candidate'):
        raise ValueError('Candidate differs from preview; analyze again')
    return result['candidate']
