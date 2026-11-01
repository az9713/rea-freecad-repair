"""Small original-app UI. Every accepted rebind is an ordinary FreeCAD undo step."""
import html
import json
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets
from . import freecad_adapter as adapter


def _error(error):
    QtWidgets.QMessageBox.warning(Gui.getMainWindow(), 'TopoIntent', str(error))


def _reference():
    selected = Gui.Selection.getSelection()
    if len(selected) != 1 or 'CaptureJSON' not in selected[0].PropertiesList:
        raise ValueError('Select exactly one TopoIntentReference in the model tree')
    return selected[0]


class CaptureCommand:
    def GetResources(self):
        return {'MenuText': 'Capture boundary-face intent',
                'ToolTip': 'Select one outer planar face. Declare invariant intervals and capture it.'}

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        try:
            selection = Gui.Selection.getSelectionEx()
            if len(selection) != 1 or len(selection[0].SubElementNames) != 1:
                raise ValueError('Select exactly one outer planar face in the 3D view')
            selection = selection[0]
            ref = selection.SubElementNames[0]
            if not ref.startswith('Face'):
                raise ValueError('A face selection is required')
            dialog = QtWidgets.QDialog(Gui.getMainWindow())
            dialog.setWindowTitle('Declare design-intent limits')
            form = QtWidgets.QFormLayout(dialog)
            form.addRow(QtWidgets.QLabel('All limits are ratios relative to this captured shape.\n'
                                         'These numerical limits do not prove full design intent.'))
            inputs = {}
            for key, label, value in [('area_ratio_min', 'Minimum face-area ratio', .25),
                                      ('area_ratio_max', 'Maximum face-area ratio', 4),
                                      ('volume_ratio_min', 'Minimum volume ratio', .5),
                                      ('volume_ratio_max', 'Maximum volume ratio', 2)]:
                box = QtWidgets.QDoubleSpinBox()
                box.setRange(.000001, 1000000)
                box.setDecimals(6)
                box.setValue(value)
                inputs[key] = box
                form.addRow(label, box)
            buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            form.addRow(buttons)
            if dialog.exec() != QtWidgets.QDialog.Accepted:
                return
            feature = adapter.create_capture(selection.Object, ref,
                                              **{k: v.value() for k, v in inputs.items()})
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(feature)
        except Exception as error:
            _error(error)


class AnalyzeCommand:
    def GetResources(self):
        return {'MenuText': 'Explain and preview validated repair',
                'ToolTip': 'Select a captured reference; compare current geometry and accept a unique rebind'}

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        try:
            feature = _reference()
            result = adapter.analyze(feature)
            dialog = QtWidgets.QDialog(Gui.getMainWindow())
            dialog.setWindowTitle('TopoIntent: ' + result['status'])
            dialog.resize(900, 560)
            dialog.setStyleSheet('QDialog,QLabel,QCheckBox {background:#14212b;color:#edf3f6;}'
                                 'QTableWidget,QTextBrowser {background:#0c151d;color:#edf3f6;gridline-color:#304553;}'
                                 'QHeaderView::section {background:#233a4b;color:#b8dcef;padding:7px;border:0;}'
                                 'QPushButton {background:#274b62;color:#edf3f6;padding:9px;border:1px solid #62839a;}'
                                 'QPushButton:disabled {color:#718490;background:#1c2b35;}')
            layout = QtWidgets.QVBoxLayout(dialog)
            summary = ('Original: {baseline_ref} | candidate: {candidate}\n'
                       'Volume ratio: {volume_ratio:.5g} | topology delta: {topology_delta}\n'
                       '{explanation}').format(**result)
            layout.addWidget(QtWidgets.QLabel(summary))
            changes = result['parameter_changes']
            if changes:
                layout.addWidget(QtWidgets.QLabel('Recorded parameter difference: ' + ', '.join(
                    '{}: {} -> {}'.format(k, v['before'], v['now']) for k, v in changes.items())))
            table = QtWidgets.QTableWidget(len(result['face_decisions']), 4)
            table.setHorizontalHeaderLabels(['Face', 'Area ratio', 'Decision', 'Predicate evidence'])
            table.verticalHeader().hide()
            table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            table.horizontalHeader().setStretchLastSection(True)
            table.setColumnWidth(0, 80)
            table.setColumnWidth(1, 105)
            table.setColumnWidth(2, 115)
            for row, decision in enumerate(result['face_decisions']):
                values = [decision['ref'], '{:.5g}'.format(decision['area_ratio']),
                          'Pass' if decision['accepted'] else 'Reject',
                          '; '.join(decision['reasons']) or 'Every declared face predicate satisfied']
                for column, value in enumerate(values):
                    table.setItem(row, column, QtWidgets.QTableWidgetItem(value))
                table.setRowHeight(row, 44)
            layout.addWidget(table)
            details = QtWidgets.QCheckBox('Show the complete machine-readable evidence')
            layout.addWidget(details)
            text = QtWidgets.QTextBrowser()
            text.setHtml('<pre>' + html.escape(json.dumps(result, indent=2)) + '</pre>')
            text.setMaximumHeight(230)
            text.hide()
            details.toggled.connect(text.setVisible)
            layout.addWidget(text)
            controls = QtWidgets.QHBoxLayout()
            preview = QtWidgets.QPushButton('Highlight candidate')
            accept = QtWidgets.QPushButton('Accept reference repair')
            close = QtWidgets.QPushButton('Close')
            can_accept = result['status'] == 'unique'
            preview.setEnabled(can_accept)
            accept.setEnabled(can_accept)

            def highlight():
                Gui.Selection.clearSelection()
                Gui.Selection.addSelection(feature.Source, result['candidate'])

            def commit():
                try:
                    adapter.repair_reference(feature, result)
                    dialog.accept()
                except Exception as error:
                    _error(error)

            preview.clicked.connect(highlight)
            accept.clicked.connect(commit)
            close.clicked.connect(dialog.reject)
            for button in (preview, accept, close):
                controls.addWidget(button)
            layout.addLayout(controls)
            dialog.exec()
        except Exception as error:
            _error(error)


class ProbeCommand:
    def GetResources(self):
        return {'MenuText': 'Probe an isolated box counterfactual',
                'ToolTip': 'Try a Part::Box dimension in a separate transient document; preserve the source'}

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        try:
            feature = _reference()
            parameter, ok = QtWidgets.QInputDialog.getItem(Gui.getMainWindow(), 'Counterfactual',
                                                         'Part::Box dimension', ['Length', 'Width', 'Height'], 2, False)
            if not ok:
                return
            value, ok = QtWidgets.QInputDialog.getDouble(Gui.getMainWindow(), 'Counterfactual',
                                                        'Trial value (mm)', 12, .000001, 1000000, 6)
            if not ok:
                return
            result = adapter.probe_box(feature, parameter, value)
            message = QtWidgets.QMessageBox(Gui.getMainWindow())
            message.setWindowTitle('Isolated counterfactual result')
            message.setText('Status: ' + result['status'] + '\nOriginal document geometry was preserved.')
            message.setDetailedText(json.dumps(result, indent=2))
            message.exec()
        except Exception as error:
            _error(error)


def register():
    Gui.addCommand('TopoIntent_Capture', CaptureCommand())
    Gui.addCommand('TopoIntent_Analyze', AnalyzeCommand())
    Gui.addCommand('TopoIntent_Probe', ProbeCommand())
