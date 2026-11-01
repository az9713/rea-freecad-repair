"""FreeCAD document adapter. Imports FreeCAD lazily so the core runs anywhere."""
import json
import math
from .core import Capture, Face, Snapshot, capture_boundary, diagnose, require_current_unique


def snapshot(shape):
    if shape.isNull():
        raise ValueError('Source has no shape')
    bounds = shape.BoundBox
    faces = []
    for i, face in enumerate(shape.Faces, 1):
        surface = type(face.Surface).__name__
        center = face.CenterOfMass
        # Surface normalAt is evaluated on the face, preserving orientation.
        u0, u1, v0, v1 = face.ParameterRange
        normal = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
        faces.append(Face('Face' + str(i), surface, float(face.Area),
                          (center.x, center.y, center.z), (normal.x, normal.y, normal.z)))
    value = Snapshot(tuple(faces), (bounds.XMin, bounds.YMin, bounds.ZMin),
                     (bounds.XMax, bounds.YMax, bounds.ZMax), float(shape.Volume),
                     bool(shape.isValid()), len(shape.Solids), len(shape.Edges))
    value.validate()
    return value


def load_capture(feature):
    return Capture.from_dict(json.loads(feature.CaptureJSON))


def box_parameters(source):
    if source.TypeId != 'Part::Box':
        return None
    return {key: float(getattr(source, key).Value) for key in ('Length', 'Width', 'Height')}


class ReferenceProxy:
    """A reviewable face reference; invalid intent clears its visible output."""
    def __init__(self, feature):
        feature.Proxy = self

    def execute(self, feature):
        import Part
        try:
            result = diagnose(load_capture(feature), snapshot(feature.Source.Shape))
            refs = list(feature.Support[1])
            if result['status'] != 'unique' or refs != [result['candidate']]:
                feature.Shape = Part.Shape()
                feature.Status = 'Review required: ' + result['status']
            else:
                feature.Shape = feature.Source.Shape.getElement(refs[0]).copy()
                feature.Status = 'Validated reference: ' + refs[0]
        except Exception as error:
            feature.Shape = Part.Shape()
            feature.Status = 'Review required: ' + str(error)

    def dumps(self):
        return None

    def loads(self, state):
        return None


def create_capture(source, ref, **ranges):
    doc = source.Document
    if not doc.UndoMode:
        raise ValueError('Document undo must be enabled before transactional capture')
    capture = capture_boundary(source.Name, snapshot(source.Shape), ref, **ranges)
    doc.openTransaction('Capture TopoIntent boundary face')
    try:
        feature = doc.addObject('Part::FeaturePython', 'TopoIntentReference')
        feature.addProperty('App::PropertyLink', 'Source', 'TopoIntent')
        feature.addProperty('App::PropertyLinkSub', 'Support', 'TopoIntent')
        feature.addProperty('App::PropertyString', 'CaptureJSON', 'TopoIntent')
        feature.addProperty('App::PropertyString', 'BaselineParameters', 'TopoIntent')
        feature.addProperty('App::PropertyString', 'Status', 'TopoIntent')
        feature.Source = source
        feature.Support = (source, [ref])
        feature.CaptureJSON = json.dumps(capture.to_dict(), sort_keys=True)
        feature.BaselineParameters = json.dumps(box_parameters(source))
        feature.setEditorMode('CaptureJSON', 1)
        feature.setEditorMode('BaselineParameters', 1)
        feature.setEditorMode('Status', 1)
        ReferenceProxy(feature)
        doc.recompute()
        if feature.Shape.isNull():
            raise ValueError('Capture did not produce a valid reference face')
        doc.commitTransaction()
        return feature
    except Exception:
        doc.abortTransaction()
        raise


def analyze(feature):
    result = diagnose(load_capture(feature), snapshot(feature.Source.Shape))
    result['source_name'] = feature.Source.Name
    result['parameters_before'] = json.loads(feature.BaselineParameters)
    result['parameters_now'] = box_parameters(feature.Source)
    before, now = result['parameters_before'], result['parameters_now']
    result['parameter_changes'] = ({key: {'before': value, 'now': now[key]}
                                   for key, value in before.items() if value != now[key]}
                                  if before and now else {})
    result['support_at_preview'] = list(feature.Support[1])
    return result


def repair_reference(feature, preview, consumer=None, property_name='Support'):
    """Rebind ONE LinkSub atomically; stale/ambiguous/invalid inputs never mutate.

    Default consumer is the in-app reference feature. Advanced callers may supply
    a native consumer's single LinkSub property, e.g. a face attachment. Lists,
    multiple subelements and cross-document references are intentionally rejected.
    """
    consumer = consumer or feature
    doc = feature.Document
    if not doc.UndoMode:
        raise ValueError('Document undo must be enabled before transactional repair')
    if consumer.Document is not doc:
        raise ValueError('Cross-document repair is unsupported')
    if consumer.getTypeIdOfProperty(property_name) != 'App::PropertyLinkSub':
        raise ValueError('Only a single LinkSub property is supported')
    prior = getattr(consumer, property_name)
    prior_refs = list(prior[1])
    if prior[0] is not feature.Source or len(prior_refs) != 1:
        raise ValueError('Consumer must reference one face of the captured source')
    candidate = require_current_unique(load_capture(feature), snapshot(feature.Source.Shape), preview)
    if consumer is feature and prior_refs != preview.get('support_at_preview'):
        raise ValueError('Reference changed after preview; analyze again')
    doc.openTransaction('Validated TopoIntent reference repair')
    try:
        setattr(consumer, property_name, (feature.Source, [candidate]))
        doc.recompute()
        if 'Invalid' in list(consumer.State):
            raise ValueError('Consumer recompute failed')
        if hasattr(consumer, 'Shape'):
            if consumer.Shape.isNull() or not consumer.Shape.isValid():
                raise ValueError('Consumer output shape is null or invalid')
        # Re-evaluate the source after the consumer recompute, catching dependency
        # effects that alter the geometry used for the accepted candidate.
        require_current_unique(load_capture(feature), snapshot(feature.Source.Shape), preview)
        doc.commitTransaction()
        return candidate
    except Exception:
        doc.abortTransaction()
        doc.recompute()
        raise


def probe_box(feature, parameter, trial_value):
    """Counterfactual on a separate transient document, never on the user's source.

    Part::Box only: general feature-history cloning would imply semantics this
    release cannot validate. The source placement and other box dimensions persist.
    """
    import FreeCAD as App
    source = feature.Source
    values = box_parameters(source)
    if values is None or parameter not in ('Length', 'Width', 'Height'):
        raise ValueError('Counterfactual probes currently support Part::Box dimensions only')
    if not math.isfinite(trial_value) or trial_value <= 0:
        raise ValueError('Trial dimension must be positive and finite')
    fingerprint = snapshot(source.Shape).fingerprint()
    source_doc = source.Document
    sandbox = App.newDocument('TopoIntentCounterfactual')
    try:
        box = sandbox.addObject('Part::Box', 'TrialBox')
        for key, value in values.items():
            setattr(box, key, value)
        box.Placement = source.Placement
        setattr(box, parameter, trial_value)
        sandbox.recompute()
        result = diagnose(load_capture(feature), snapshot(box.Shape))
        result['counterfactual'] = {'parameter': parameter, 'current': values[parameter],
                                    'trial': trial_value, 'isolated_document': True}
        return result
    finally:
        App.closeDocument(sandbox.Name)
        App.setActiveDocument(source_doc.Name)
        if snapshot(source.Shape).fingerprint() != fingerprint:
            raise RuntimeError('Source unexpectedly changed during isolated probe')
