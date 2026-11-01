import copy
import math
import unittest
from dataclasses import replace
from topointent.core import Face, Snapshot, Capture, capture_boundary, diagnose, require_current_unique


def fixture(height=10, top_ref='Face6'):
    faces = (Face('Face1', 'Plane', 100, (0, 5, height / 2), (-1, 0, 0)),
             Face('Face2', 'Plane', 100, (10, 5, height / 2), (1, 0, 0)),
             Face('Face3', 'Plane', 100, (5, 0, height / 2), (0, -1, 0)),
             Face('Face4', 'Plane', 100, (5, 10, height / 2), (0, 1, 0)),
             Face('Face5', 'Plane', 100, (5, 5, 0), (0, 0, -1)),
             Face('Face6', 'Plane', 100, (5, 5, height), (0, 0, 1)))
    if top_ref != 'Face6':
        faces = tuple(replace(f, ref=top_ref if f.ref == 'Face6' else 'Face6' if f.ref == top_ref else f.ref) for f in faces)
    return Snapshot(faces, (0, 0, 0), (10, 10, height), 100 * height, True, 1, 12)


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture()
        self.capture = capture_boundary('Box', self.base, 'Face6')

    def test_renumbered_face_and_height_change_preserve_relational_intent(self):
        result = diagnose(self.capture, fixture(12, 'Face2'))
        self.assertEqual(result['status'], 'unique')
        self.assertEqual(result['candidate'], 'Face2')
        self.assertTrue(result['reference_change_required'])
        self.assertFalse(result['old_ref_still_satisfies_intent'])
        self.assertAlmostEqual(result['volume_ratio'], 1.2)

    def test_roundtrip_capture(self):
        restored = Capture.from_dict(self.capture.to_dict())
        self.assertEqual(diagnose(restored, self.base)['status'], 'unique')

    def test_split_coplanar_faces_are_ambiguous_and_no_candidate_chosen(self):
        split = replace(self.base, faces=self.base.faces[:-1] + (
            Face('Face6', 'Plane', 50, (2.5, 5, 10), (0, 0, 1)),
            Face('Face7', 'Plane', 50, (7.5, 5, 10), (0, 0, 1))))
        result = diagnose(self.capture, split)
        self.assertEqual(result['status'], 'ambiguous')
        self.assertIsNone(result['candidate'])
        with self.assertRaises(ValueError):
            require_current_unique(self.capture, split, result)

    def test_excess_volume_rejected_even_with_unique_face_match(self):
        result = diagnose(self.capture, fixture(100))
        self.assertEqual(result['status'], 'invalid')
        self.assertIn('Volume ratio', result['failures'][0])

    def test_invalid_shape_and_multiple_solids_rejected(self):
        for change in ({'valid': False}, {'solids': 2}):
            self.assertEqual(diagnose(self.capture, replace(self.base, **change))['status'], 'invalid')

    def test_stale_preview_rejected(self):
        current = fixture(12, 'Face2')
        preview = diagnose(self.capture, current)
        with self.assertRaisesRegex(ValueError, 'Stale preview'):
            require_current_unique(self.capture, fixture(13, 'Face2'), preview)

    def test_changed_design_intent_invalidates_preview(self):
        preview = diagnose(self.capture, self.base)
        changed = replace(self.capture, intent=replace(self.capture.intent, area_ratio_min=.5))
        with self.assertRaisesRegex(ValueError, 'Stale capture'):
            require_current_unique(changed, self.base, preview)

    def test_derived_ratio_overflow_rejected(self):
        tiny = replace(self.base, volume=1e-320)
        capture = capture_boundary('Tiny', tiny, 'Face6')
        with self.assertRaisesRegex(ValueError, 'Non-finite derived'):
            diagnose(capture, self.base)

    def test_nonfinite_geometry_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.assertRaises(ValueError):
                diagnose(self.capture, replace(self.base, volume=value))
            faces = (replace(self.base.faces[0], center=(value, 0, 0)),) + self.base.faces[1:]
            with self.assertRaises(ValueError):
                diagnose(self.capture, replace(self.base, faces=faces))

    def test_duplicate_refs_and_degenerate_bounds_rejected(self):
        with self.assertRaises(ValueError):
            diagnose(self.capture, replace(self.base, faces=self.base.faces + (self.base.faces[0],)))
        with self.assertRaises(ValueError):
            diagnose(self.capture, replace(self.base, maximum=(0, 10, 10)))

    def test_unsupported_curves_and_tilted_faces_refused(self):
        for face in (replace(self.base.faces[-1], surface='Cylinder'),
                     replace(self.base.faces[-1], normal=(.1, 0, 1))):
            with self.assertRaises(ValueError):
                capture_boundary('Box', replace(self.base, faces=self.base.faces[:-1] + (face,)), 'Face6')

    def test_inverted_and_nonfinite_limits_rejected(self):
        for changes in ({'area_ratio_min': 2, 'area_ratio_max': 1}, {'tolerance': .1},
                        {'volume_ratio_max': math.inf}, {'area_ratio_min': -1}):
            with self.assertRaises(ValueError):
                capture_boundary('Box', self.base, 'Face6', **changes)

    def test_old_face_can_exist_but_fail_intent(self):
        current = fixture(12, 'Face2')
        result = diagnose(self.capture, current)
        old = next(f for f in result['face_decisions'] if f['ref'] == 'Face6')
        self.assertFalse(old['accepted'])
        self.assertTrue(old['reasons'])

    def test_no_match_never_returns_best_effort(self):
        current = replace(self.base, faces=self.base.faces[:-1])
        result = diagnose(self.capture, current)
        self.assertEqual(result['status'], 'no_match')
        self.assertIsNone(result['candidate'])


if __name__ == '__main__':
    unittest.main()
