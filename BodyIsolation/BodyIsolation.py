import logging
import os
from typing import Annotated, Optional

import vtk

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from slicer.parameterNodeWrapper import (
    parameterNodeWrapper,
    Default,
    WithinRange,
)

from slicer import vtkMRMLScalarVolumeNode


#
# BodyIsolation
#

class BodyIsolation(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Body isolation"  # TODO: make this more human readable by adding spaces
        self.parent.categories = ["Utilities"]  # TODO: set categories (folders where the module shows up in the module selector)
        self.parent.dependencies = []  # TODO: add here list of module names that this module requires
        self.parent.contributors = ["Saleem Edah-Tally [Surgeon] [Hobbyist developer]"]  # TODO: replace with "Firstname Lastname (Organization)"
        # TODO: update with short description of the module and a link to online module documentation
        self.parent.helpText = """
Isolate the body in common CT scans. These must be headless, with a complete skin circumference along the Z-axis.
See more information in <a href="href="https://github.com/chir-set/Tools7/BodyIsolation/">module documentation</a>.
"""
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
"""
#
# BodyIsolationParameterNode
#

@parameterNodeWrapper
class BodyIsolationParameterNode:
    inputVolume: slicer.vtkMRMLScalarVolumeNode
    keepSegmentation: Annotated[bool, Default(False)]

#
# BodyIsolationWidget
#

class BodyIsolationWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None) -> None:
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None
        self._parameterNodeGuiTag = None

    def setup(self) -> None:
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/BodyIsolation.ui'))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = BodyIsolationLogic()

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # Buttons
        self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

    def cleanup(self) -> None:
        """
        Called when the application closes and the module widget is destroyed.
        """
        self.removeObservers()

    def enter(self) -> None:
        """
        Called each time the user opens this module.
        """
        # Make sure parameter node exists and observed
        self.initializeParameterNode()

    def exit(self) -> None:
        """
        Called each time the user opens a different module.
        """
        # Do not react to parameter node changes (GUI will be updated when the user enters into the module)
        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self._parameterNodeGuiTag = None

    def onSceneStartClose(self, caller, event) -> None:
        """
        Called just before the scene is closed.
        """
        # Parameter node will be reset, do not use it anymore
        self.setParameterNode(None)

    def onSceneEndClose(self, caller, event) -> None:
        """
        Called just after the scene is closed.
        """
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        if self.parent.isEntered:
            self.initializeParameterNode()

    def initializeParameterNode(self) -> None:
        """
        Ensure parameter node exists and observed.
        """
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

        self.setParameterNode(self.logic.getParameterNode())

    def setParameterNode(self, inputParameterNode: Optional[BodyIsolationParameterNode]) -> None:
        """
        Set and observe parameter node.
        Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
        """

        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
        self._parameterNode = inputParameterNode
        if self._parameterNode:
            # Note: in the .ui file, a Qt dynamic property called "SlicerParameterName" is set on each
            # ui element that needs connection.
            self._parameterNodeGuiTag = self._parameterNode.connectGui(self.ui)

    def showStatusMessage(self, message, timeout = 3000) -> None:
        slicer.util.showStatusMessage(message, timeout)
        slicer.app.processEvents()
        
    def onApplyButton(self) -> None:
        # Create one if necessary.
        slicer.modules.segmenteditor.widgetRepresentation()
        
        volumeNode = self.ui.inputSelector.currentNode()
        if volumeNode is None:
            self.showStatusMessage("Volume node is None.")
            return
        
        with slicer.util.tryWithErrorDisplay("Failed to compute results.", waitCursor=True):
            
            splitVolumeNode = self.logic.process(volumeNode, self._parameterNode.keepSegmentation)
            self.ui.inputSelector.setCurrentNode(splitVolumeNode)
            
#
# BodyIsolationLogic
#

class BodyIsolationLogic(ScriptedLoadableModuleLogic):

    def __init__(self) -> None:
        """
        Called when the logic class is instantiated. Can be used for initializing member variables.
        """
        ScriptedLoadableModuleLogic.__init__(self)

    def getParameterNode(self):
        return BodyIsolationParameterNode(super().getParameterNode())

    def process(self, volumeNode, keepSegmentation = False) -> None:
        """
        Islands and Margin are costly, fortunately multi-threaded.
        For a 512x512x2231  volume, 16 GB RAM *may* be insufficient.
        """
        if not volumeNode:
            logging.info("Volume node is None.")
            return

        import time
        startTime = time.time()
        logging.info('Processing started') # No output anywhere.

        # Reset masking options.
        widgetEditor = slicer.modules.SegmentEditorWidget.editor
        widgetEditor.mrmlSegmentEditorNode().SetMaskMode(slicer.vtkMRMLSegmentationNode.EditAllowedEverywhere)
        widgetEditor.mrmlSegmentEditorNode().SourceVolumeIntensityMaskOff()
        widgetEditor.mrmlSegmentEditorNode().SetOverwriteMode(widgetEditor.mrmlSegmentEditorNode().OverwriteAllSegments)

        # Create a segmentation and an empty segment.
        segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", volumeNode.GetName() +  "_Body_Segmentation")
        segmentationNode.CreateDefaultDisplayNodes()
        segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(volumeNode)
        widgetEditor.setSegmentationNode(segmentationNode)
        segmentID = segmentationNode.GetSegmentation().AddEmptySegment()
        widgetEditor.mrmlSegmentEditorNode().SetSelectedSegmentID(segmentID)
        
        # Threshold from minimum intensity to -200.
        intensityRange = volumeNode.GetImageData().GetScalarRange()
        widgetEditor.setActiveEffectByName("Threshold")
        effect = widgetEditor.activeEffect()
        effect.setParameter("MinimumThreshold", str(intensityRange[0]))
        effect.setParameter("MaximumThreshold", "-200")
        effect.self().onApply()
        widgetEditor.setActiveEffectByName(None)
        
        # Remove small segments inside body (air).
        widgetEditor.setActiveEffectByName("Islands")
        effect = widgetEditor.activeEffect()
        effect.setParameter("Operation", "KEEP_LARGEST_ISLAND")
        effect.self().onApply()
        widgetEditor.setActiveEffectByName(None)
        
        # Invert segment to body circumference, hopefully distinct from table. Cables on the skin cannot be removed.
        widgetEditor.setActiveEffectByName("Logical operators")
        effect = widgetEditor.activeEffect()
        effect.setParameter("Operation", "INVERT")
        effect.self().onApply()
        widgetEditor.setActiveEffectByName(None)
        widgetEditor.setActiveEffectByName(None)
        
        # Shrink segment by 3 mm. May better isolate body circumference.
        widgetEditor.setActiveEffectByName("Margin")
        effect = widgetEditor.activeEffect()
        effect.setParameter("MarginSizeMm", "-3.0")
        effect.self().onApply()
        widgetEditor.setActiveEffectByName(None)
        
        # Keep body segment.
        widgetEditor.setActiveEffectByName("Islands") # May be more costly than the first one.
        effect = widgetEditor.activeEffect()
        effect.setParameter("Operation", "KEEP_LARGEST_ISLAND")
        effect.self().onApply()
        widgetEditor.setActiveEffectByName(None)
        
        # Restore body segment.
        widgetEditor.setActiveEffectByName("Margin")
        effect = widgetEditor.activeEffect()
        effect.setParameter("MarginSizeMm", "3.0")
        effect.self().onApply()
        widgetEditor.setActiveEffectByName(None)
        
        # We want to get rid of anything superfluous; 'Split volumes' trims to segment bounds.
        widgetEditor.setActiveEffectByName("Split volume")
        effect = widgetEditor.activeEffect()
        effect.setParameter("FillValue", intensityRange[0])
        # Not mandatory, we know there is only one segment.
        effect.setParameter("ApplyToAllVisibleSegments", 0)
        effect.self().onApply()
        widgetEditor.setActiveEffectByName(None)
        
        # Replace input volume node by contract (UI tooltip). We don't want to keep too many things around.
        inputVolumeName = volumeNode.GetName()
        slicer.mrmlScene.RemoveNode(volumeNode)
        
        # Get and show the split volume. Should this be in logic ?
        allScalarVolumeNodes = slicer.mrmlScene.GetNodesByClass("vtkMRMLScalarVolumeNode")
        splitVolumeNode = allScalarVolumeNodes.GetItemAsObject(allScalarVolumeNodes.GetNumberOfItems() - 1)
        splitVolumeNode.SetName(inputVolumeName)
        
        views = slicer.app.layoutManager().sliceViewNames()
        for view in views:
            sliceLogic = slicer.app.layoutManager().sliceWidget(view).sliceLogic()
            viewCompositeNode = sliceLogic.GetSliceCompositeNode()
            viewCompositeNode.SetBackgroundVolumeID(splitVolumeNode.GetID())
            sliceLogic.FitSliceToAll()
        
        # Reparent subject hierarchy items.
        shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
        shSplitVolumeId = shNode.GetItemByDataNode(splitVolumeNode)
        shSplitVolumeFolderId = shNode.GetItemParent(shSplitVolumeId) # To be removed.
        shSplitVolumeStudyId = shNode.GetItemParent(shSplitVolumeFolderId) # Is root scene ID for NRRD files.
        shNode.SetItemParent(shSplitVolumeId, shSplitVolumeStudyId)
        if shNode.GetItemLevel(shSplitVolumeFolderId) == "Folder":
            shNode.RemoveItem(shSplitVolumeFolderId)
        
        if (not keepSegmentation):
            slicer.mrmlScene.RemoveNode(segmentationNode)

        stopTime = time.time()
        logging.info(f'Processing completed in {stopTime-startTime:.2f} seconds')
        return splitVolumeNode

#
# BodyIsolationTest
#

class BodyIsolationTest(ScriptedLoadableModuleTest):
    
    def setUp(self):
        """ Do whatever is needed to reset the state - typically a scene clear will be enough.
        """
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here.
        """
        self.setUp()
        self.test_BodyIsolation1()

    def test_BodyIsolation1(self):
        self.delayDisplay("Starting the test")

        self.delayDisplay('Test passed')
