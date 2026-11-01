"""REAL FreeCAD/OCC integration, launched with scripts/run_portable.ps1.

Unlike unit fixtures, these create actual BRep solids, documents, transactions and
persisted FCStd examples. A missing FreeCAD runtime is an error, never a mock pass.
"""
import json
import hashlib
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(os.environ['TOPOINTENT_ROOT']).resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
import FreeCAD as App
import Part
from topointent import freecad_adapter as adapter
from topointent.core import diagnose
from integration_helpers import FailingConsumer

results = []
output = ROOT / 'artifacts'
output.mkdir(exist_ok=True)


def check(name, action):
    try:
        details = action()
        results.append({'name': name, 'passed': True, 'details': details})
        print('PASS', name)
    except Exception:
        results.append({'name': name, 'passed': False, 'traceback': traceback.format_exc()})
        print('FAIL', name, traceback.format_exc())


def document(name):
    doc = App.newDocument(name)
    doc.UndoMode = 1
    return doc


def top_ref(shape):
    return next(f.ref for f in adapter.snapshot(shape).faces if f.surface == 'Plane' and f.normal[2] > .999)


def isolated_runtime_paths():
    home = Path(App.getUserAppDataDir()).resolve()
    resource = Path(App.getResourceDir()).resolve()
    assert home.is_relative_to(ROOT), 'FreeCAD user data directory escapes project'
    assert resource.is_relative_to(ROOT), 'FreeCAD runtime resources escape project'
    return {'user_data': home.relative_to(ROOT).as_posix(),
            'runtime_resources': resource.relative_to(ROOT).as_posix()}


def height_and_counterfactual():
    doc = document('BoxCounterfactual')
    try:
        box = doc.addObject('Part::Box', 'OriginalBox')
        box.Length = box.Width = box.Height = 10
        doc.recompute()
        captured = adapter.create_capture(box, top_ref(box.Shape))
        box.Height = 12
        doc.recompute()
        before = adapter.snapshot(box.Shape).fingerprint()
        result = adapter.analyze(captured)
        assert result['status'] == 'unique', result
        assert result['parameter_changes']['Height'] == {'before': 10., 'now': 12.}
        probe = adapter.probe_box(captured, 'Height', 10.)
        assert abs(probe['volume_ratio'] - 1) < 1e-9
        assert adapter.snapshot(box.Shape).fingerprint() == before
        assert float(box.Height.Value) == 12.
        assert App.ActiveDocument.Name == doc.Name
        doc.saveAs(str(output / 'box-counterfactual.FCStd'))
        return {'current_volume_ratio': result['volume_ratio'],
                'counterfactual_volume_ratio': probe['volume_ratio'], 'source_preserved': True}
    finally:
        App.closeDocument(doc.Name)


def reordered_fixture():
    doc = document('TopologyRenumber')
    solid = Part.makeBox(10, 10, 10)
    source = doc.addObject('Part::Feature', 'SourceSolid')
    source.Shape = solid
    doc.recompute()
    capture = adapter.create_capture(source, top_ref(solid))
    old_ref = capture.Support[1][0]
    for offset in range(1, len(solid.Faces)):
        changed = Part.makeSolid(Part.makeShell(solid.Faces[offset:] + solid.Faces[:offset]))
        if changed.isValid() and top_ref(changed) != old_ref:
            doc.openTransaction('Controlled BRep face-order counterexample')
            source.Shape = changed
            doc.recompute()
            doc.commitTransaction()
            return doc, source, capture
    App.closeDocument(doc.Name)
    raise AssertionError('Could not construct an actual valid renumbered BRep fixture')


def rebind_and_undo():
    doc, source, capture = reordered_fixture()
    try:
        old_ref = capture.Support[1][0]
        result = adapter.analyze(capture)
        assert result['status'] == 'unique' and result['reference_change_required'], result
        assert capture.Shape.isNull(), 'Unreviewed output should be cleared when the old reference violates intent'
        doc.saveAs(str(output / 'renumber-before-review.FCStd'))
        new_ref = adapter.repair_reference(capture, result)
        assert capture.Support[1] == [new_ref]
        assert capture.Shape.isValid() and not capture.Shape.isNull()
        assert abs(capture.Shape.CenterOfMass.z - 10) < 1e-9
        doc.saveAs(str(output / 'renumber-after-repair.FCStd'))
        doc.undo()
        doc.recompute()
        assert capture.Support[1] == [old_ref], 'Undo must restore the original binding'
        return {'before': old_ref, 'after': new_ref, 'undo_restored_binding': True,
                'kernel_valid': source.Shape.isValid()}
    finally:
        App.closeDocument(doc.Name)


def split_ambiguity():
    doc = document('AmbiguousSplit')
    try:
        source = doc.addObject('Part::Feature', 'SourceSolid')
        source.Shape = Part.makeBox(10, 10, 10)
        doc.recompute()
        capture = adapter.create_capture(source, top_ref(source.Shape))
        # Deliberately retain coplanar faces after Boolean fusion: two valid top
        # candidates are a real geometric ambiguity, not a synthetic JSON mock.
        left = Part.makeBox(5, 10, 10)
        right = Part.makeBox(5, 10, 10, App.Vector(5, 0, 0))
        source.Shape = left.fuse(right)
        doc.recompute()
        result = adapter.analyze(capture)
        assert result['status'] == 'ambiguous', result
        prior = tuple(capture.Support[1])
        try:
            adapter.repair_reference(capture, result)
            raise AssertionError('Ambiguous repair unexpectedly accepted')
        except ValueError:
            pass
        assert tuple(capture.Support[1]) == prior
        doc.saveAs(str(output / 'ambiguous-split-refused.FCStd'))
        return {'candidates': result['candidates'], 'repair_refused': True,
                'kernel_valid': source.Shape.isValid(), 'solids': len(source.Shape.Solids)}
    finally:
        App.closeDocument(doc.Name)


def stale_preview():
    doc, source, capture = reordered_fixture()
    try:
        result = adapter.analyze(capture)
        source.Shape = source.Shape.translated(App.Vector(0, 0, 1))
        doc.recompute()
        # FreeCAD's own topological-naming layer may update a LinkSub during the
        # edit. The rejected repair must not mutate the post-edit binding.
        prior = list(capture.Support[1])
        try:
            adapter.repair_reference(capture, result)
            raise AssertionError('Stale preview unexpectedly accepted')
        except ValueError as error:
            assert 'Stale preview' in str(error), str(error)
        assert list(capture.Support[1]) == prior
        return {'stale_refused_without_rebinding': True}
    finally:
        App.closeDocument(doc.Name)


def rollback_failed_consumer():
    doc, source, capture = reordered_fixture()
    try:
        preview = adapter.analyze(capture)
        obj = doc.addObject('Part::FeaturePython', 'DeliberatelyFailingConsumer')
        obj.addProperty('App::PropertyLinkSub', 'Support')
        prior = list(capture.Support[1])
        obj.Support = (source, prior)
        FailingConsumer(obj, preview['candidate'])
        doc.recompute()
        try:
            adapter.repair_reference(capture, preview, obj)
            raise AssertionError('Invalid consumer output unexpectedly committed')
        except ValueError as error:
            assert 'null or invalid' in str(error), str(error)
        assert list(obj.Support[1]) == prior, 'Aborted transaction did not restore consumer binding'
        assert not obj.Shape.isNull(), 'Rollback did not restore valid consumer output'
        return {'failed_recompute_rolled_back': True, 'original_binding': prior}
    finally:
        App.closeDocument(doc.Name)


def serialization_roundtrip():
    path = output / 'box-counterfactual.FCStd'
    doc = App.openDocument(str(path))
    try:
        ref = next(o for o in doc.Objects if 'CaptureJSON' in o.PropertiesList)
        ref.touch()
        doc.recompute()
        result = adapter.analyze(ref)
        assert result['status'] == 'unique'
        assert not ref.Shape.isNull()
        return {'restored_proxy': type(ref.Proxy).__name__, 'status': result['status']}
    finally:
        App.closeDocument(doc.Name)


try:
    check('project_isolated_native_runtime_paths', isolated_runtime_paths)
    check('real_box_height_and_isolated_counterfactual', height_and_counterfactual)
    check('real_brep_renumber_repair_and_native_undo', rebind_and_undo)
    check('real_boolean_split_ambiguity_refused', split_ambiguity)
    check('real_stale_preview_refused', stale_preview)
    check('failed_consumer_recompute_rolls_back_binding', rollback_failed_consumer)
    check('FCStd_save_open_proxy_roundtrip', serialization_roundtrip)
finally:
    report = {'runtime': 'FreeCAD + OpenCASCADE, not mocked', 'freecad_version': list(App.Version()),
              'passed': sum(r['passed'] for r in results), 'total': len(results), 'results': results}
    report['tested_files'] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                              for name in ['topointent/core.py', 'topointent/freecad_adapter.py',
                                           'tests/integration_freecad.py', 'tests/integration_helpers.py']}
    (output / 'integration-results.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('TOPOINTENT_INTEGRATION', report['passed'], '/', report['total'])
    if report['passed'] != report['total']:
        raise RuntimeError('FreeCAD integration failed; inspect artifacts/integration-results.json')
