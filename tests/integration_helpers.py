"""Importable proxy for native undo serialization; no test entrypoint side effects."""
import Part


class FailingConsumer:
    def __init__(self, obj, fail_ref):
        self.fail_ref = fail_ref
        obj.Proxy = self

    def execute(self, obj):
        ref = obj.Support[1][0]
        obj.Shape = Part.Shape() if ref == self.fail_ref else obj.Support[0].Shape.getElement(ref)
