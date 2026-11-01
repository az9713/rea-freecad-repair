import FreeCADGui as Gui


class TopoIntentWorkbench(Gui.Workbench):
    MenuText = 'TopoIntent'
    ToolTip = 'Explain boundary-face changes; repair only uniquely validated references'

    def Initialize(self):
        from topointent.gui import register
        register()
        commands = ['TopoIntent_Capture', 'TopoIntent_Analyze', 'TopoIntent_Probe']
        self.appendToolbar('TopoIntent', commands)
        self.appendMenu('TopoIntent', commands)

    def GetClassName(self):
        return 'Gui::PythonWorkbench'


Gui.addWorkbench(TopoIntentWorkbench())
