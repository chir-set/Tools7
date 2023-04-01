import logging
import os
from typing import Annotated, Optional

import vtk

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from slicer.parameterNodeWrapper import (
    parameterNodeWrapper,
    WithinRange,
)

from slicer import vtkMRMLScalarVolumeNode


#
# ArteryPartsSegmentation
#

class ArteryPartsSegmentation(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Artery parts segmentation"  # TODO: make this more human readable by adding spaces
        self.parent.categories = ["Utilities"]  # TODO: set categories (folders where the module shows up in the module selector)
        self.parent.dependencies = []  # TODO: add here list of module names that this module requires
        self.parent.contributors = ["Saleem Edah-Tally [Surgeon] [Hobbyist developer]"]  # TODO: replace with "Firstname Lastname (Organization)"
        # TODO: update with short description of the module and a link to online module documentation
        self.parent.helpText = """
Segment a contrasted diseased artery in three parts inside a Shape::Tube node.
See more information in <a href="href="https://github.com/chir-set/Tools7/ArteryPartsSegmentation/">module documentation</a>.
"""
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
"""


#
# ArteryPartsSegmentationParameterNode
#

@parameterNodeWrapper
class ArteryPartsSegmentationParameterNode:
    # inputShape: slicer.vtkMRMLMarkupsShapeNode # Fails
    #inputVolume: slicer.vtkMRMLScalarVolumeNode
    #outputSegmentation: slicer.vtkMRMLSegmentationNode
    pass

#
# ArteryPartsSegmentationWidget
#

class ArteryPartsSegmentationWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/ArteryPartsSegmentation.ui'))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = ArteryPartsSegmentationLogic()

        # Whatever value is set in designer, minimum is shown as 99.0.
        self.ui.lumenIntensityRangeWidget.minimumValue = 200.0
        self.ui.lumenIntensityRangeWidget.maximumValue = 450.0
        
        self.ui.optionsCollapsibleButton.setChecked(False)
        
        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # Buttons
        self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)
        # rangeChanged(double, double) fails.
        self.ui.lumenIntensityRangeWidget.connect('minimumValueChanged(double)', lambda value: self.onIntensityRangeChanged(value, self.ui.lumenIntensityRangeWidget.maximumValue))
        self.ui.lumenIntensityRangeWidget.connect('maximumValueChanged(double)', lambda value: self.onIntensityRangeChanged(self.ui.lumenIntensityRangeWidget.minimumValue, value))
        self.ui.previewToolButton.connect('clicked(bool)', self.onPreview)
        self.ui.softCalcificationCheckBox.connect('clicked(bool)', self.onAccountForSoftCalcification)
        self.ui.extrusionGroupBox.connect('clicked(bool)', self.onExtrusionKernelSize)

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()
        
        # Keep track of these as they are used in many places.
        self.TubeSegmentID = ""
        self.LumenSegmentID = ""
        self.SegmentEditorWidget = None
        self.SplitVolumeNode = None

        if not slicer.app.testingEnabled():
            try:
                self.installExtensionFromServer(("SegmentEditorExtraEffects", "ExtraMarkups"))
            except Exception as e:
                slicer.util.errorDisplay("Failed to install extension: "+str(e))
                import traceback
                traceback.print_exc()
        
    def installExtensionFromServer(self, extensions):
        # https://slicer.readthedocs.io/en/latest/developer_guide/script_repository.html#download-and-install-extension
        em = slicer.app.extensionsManagerModel()
        em.interactive = False
        metadataRetrieved = False
        
        extensionInstalled = False
        for extensionName in extensions:
            if not em.isExtensionInstalled(extensionName):
                if not metadataRetrieved:
                    # This is a real problem when network is off, and a privacy concern; do it here.
                    result = em.updateExtensionsMetadataFromServer(True, True)
                    if (not result):
                        raise ValueError("Could not update metadata from server.")
                    metadataRetrieved = True
                reply = slicer.util.confirmYesNoDisplay(f"{extensionName} must be installed. Do you want to install it now ?")
                if (not reply):
                    raise ValueError(f"This module cannot be used without {extensionName}.")

                if not em.downloadAndInstallExtensionByName(extensionName, True, True):
                    raise ValueError(f"Failed to install {extensionName} extension.")
                else:
                    extensionInstalled = True
        if extensionInstalled:
            reply = slicer.util.confirmYesNoDisplay("An extension has been installed from server.\n\nSlicer must be restarted. Do you want to restart now ?")
            if reply:
                slicer.util.restart()

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

    def setParameterNode(self, inputParameterNode: Optional[ArteryPartsSegmentationParameterNode]) -> None:
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

    def onApplyButton(self) -> None:
        """
        Run processing when user clicks "Apply" button.
        """
        with slicer.util.tryWithErrorDisplay("Failed to compute results.", waitCursor=True):
            if not self.checkNodes():
                return

            self.ui.previewToolButton.setChecked(False)
            self.exitPreview()
            
            shapeNode = self.ui.inputShapeSelector.currentNode()
            volumeNode = self.ui.inputVolumeSelector.currentNode()
            segmentationNode = self.ui.outputSegmentationSelector.currentNode()
            lumenIntensityMin = self.ui.lumenIntensityRangeWidget.minimumValue
            lumenIntensityMax = self.ui.lumenIntensityRangeWidget.maximumValue
            accountForSoftCalcification = self.ui.softCalcificationCheckBox.isChecked()
            extrusionKernelSize = 0.0
            if self.ui.extrusionGroupBox.isChecked():
                extrusionKernelSize = self.ui.extrusionKernelSizeSpinBox.value
            
            self.logic.process(shapeNode, volumeNode, segmentationNode,
                               lumenIntensityMin, lumenIntensityMax,
                               accountForSoftCalcification, extrusionKernelSize)
    
    """
    Use the 'Threshold' effect to preview the lumen. The intensity range can be
    adjusted using the slider. Mouse dragging in slice views is not taken into
    account. The effect itself is never applied.
    """
    def onPreview(self) -> None:
        button = self.ui.previewToolButton
        # Clean everything if we exit preview mode.
        if not button.isChecked():
            self.exitPreview()
            return
        if not self.checkNodes():
            return
        
        shapeNode = self.ui.inputShapeSelector.currentNode()
        volumeNode = self.ui.inputVolumeSelector.currentNode()
        segmentationNode = self.ui.outputSegmentationSelector.currentNode()
        
        # Create slicer.modules.SegmentEditorWidget
        slicer.modules.segmenteditor.widgetRepresentation()
        self.SegmentEditorWidget = slicer.modules.SegmentEditorWidget.editor
        seWidget = self.SegmentEditorWidget
        seWidget.setSegmentationNode(segmentationNode)
        seWidget.setSourceVolumeNode(volumeNode)
        segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(volumeNode)
        
        # Crop the volume to the inside of the Tube using 'Split volume'.
        tubePolyData = shapeNode.GetCappedTubeWorld()
        segmentationNode.CreateClosedSurfaceRepresentation()
        self.TubeSegmentID = segmentationNode.AddSegmentFromClosedSurfaceRepresentation(tubePolyData, "Tube")
        seWidget.mrmlSegmentEditorNode().SetSelectedSegmentID(self.TubeSegmentID)
        
        intensityRange = volumeNode.GetImageData().GetScalarRange()
        seWidget.setActiveEffectByName("Split volume")
        effect = seWidget.activeEffect()
        # Fill with an intensity that does not exist in the volume, to avoid space outside the Tube later.
        effect.setParameter("FillValue", intensityRange[0] - 1)
        effect.setParameter("ApplyToAllVisibleSegments", 0)
        effect.self().onApply()
        seWidget.setActiveEffectByName(None)
        
        # Get the split volume. 'Split volume' effect does not provide it.
        allScalarVolumeNodes = slicer.mrmlScene.GetNodesByClass("vtkMRMLScalarVolumeNode")
        self.SplitVolumeNode = allScalarVolumeNodes.GetItemAsObject(allScalarVolumeNodes.GetNumberOfItems() - 1)
        splitVolumeNode = self.SplitVolumeNode
        seWidget.setSourceVolumeNode(splitVolumeNode)
        segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(splitVolumeNode)
        
        # The tube segment passed to 'Split volume' is no longer needed.
        if segmentationNode.GetSegmentation().GetSegment(self.TubeSegmentID):
            segmentationNode.GetSegmentation().RemoveSegment(self.TubeSegmentID)
        self.TubeSegmentID = ""
        
        # Create a segment to preview the lumen in slice views using 'Threshold' effect.
        self.LumenSegmentID = segmentationNode.GetSegmentation().AddEmptySegment("LumenPreview")
        seWidget.mrmlSegmentEditorNode().SetSelectedSegmentID(self.LumenSegmentID)
        seWidget.setActiveEffectByName("Threshold")
        effect = seWidget.activeEffect()
        effect.setParameter("MinimumThreshold", str(self.ui.lumenIntensityRangeWidget.minimumValue))
        effect.setParameter("MaximumThreshold", str(self.ui.lumenIntensityRangeWidget.maximumValue))
        # Don't apply, just a preview to get intensity range.
        
        # Reparent subject hierarchy items.
        shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
        shSplitVolumeId = shNode.GetItemByDataNode(splitVolumeNode)
        shSplitVolumeFolderId = shNode.GetItemParent(shSplitVolumeId) # To be removed.
        shSplitVolumeStudyId = shNode.GetItemParent(shSplitVolumeFolderId) # Is root scene ID for NRRD files.
        shSegmentationId = shNode.GetItemByDataNode(segmentationNode)
        shNode.SetItemParent(shSplitVolumeId, shSplitVolumeStudyId)
        shNode.SetItemParent(shSegmentationId, shSplitVolumeStudyId)
        if shNode.GetItemLevel(shSplitVolumeFolderId) == "Folder":
            shNode.RemoveItem(shSplitVolumeFolderId)
    
    # Remove all temporary objects.
    def exitPreview(self) -> None:
        segmentationNode = self.ui.outputSegmentationSelector.currentNode()
        # Terminate any active effect.
        if self.SegmentEditorWidget:
            self.SegmentEditorWidget.setActiveEffectByName(None)
            self.SegmentEditorWidget = None
        if segmentationNode and segmentationNode.GetSegmentation().GetSegment(self.TubeSegmentID):
            segmentationNode.GetSegmentation().RemoveSegment(self.TubeSegmentID)
            self.TubeSegmentID = ""
        if segmentationNode and segmentationNode.GetSegmentation().GetSegment(self.LumenSegmentID):
            segmentationNode.GetSegmentation().RemoveSegment(self.LumenSegmentID)
            self.LumenSegmentID = ""
        if self.SplitVolumeNode:
            slicer.mrmlScene.RemoveNode(self.SplitVolumeNode)
            self.SplitVolumeNode = None
    
    # Tune the active 'Threshold' effect, used for preview only.
    def onIntensityRangeChanged(self, min, max) -> None:
        if not self.SegmentEditorWidget:
            return
        seWidget = self.SegmentEditorWidget
        seWidget.setActiveEffectByName("Threshold")
        effect = seWidget.activeEffect()
        effect.setParameter("MinimumThreshold", str(min))
        effect.setParameter("MaximumThreshold", str(max))
    
    def onAccountForSoftCalcification(self, value) -> None:
        if value:
            self.ui.extrusionGroupBox.setChecked(True)
    
    def onExtrusionKernelSize(self, value) -> None:
        if self.ui.softCalcificationCheckBox.isChecked():
            self.ui.extrusionGroupBox.setChecked(True)
    
    def showStatusMessage(self, message, timeout = 3000) -> None:
        slicer.util.showStatusMessage(message, timeout)
        slicer.app.processEvents()
    
    def checkNodes(self) -> None:
        shapeNode = self.ui.inputShapeSelector.currentNode()
        if not shapeNode:
            self.showStatusMessage("No shape node selected.")
            return False
        if shapeNode.GetShapeName() != slicer.vtkMRMLMarkupsShapeNode.Tube:
            self.showStatusMessage("Shape node is not a Tube.")
            return False
        if shapeNode.GetNumberOfUndefinedControlPoints():
            self.showStatusMessage("Shape node has undefined control points.")
            return False
        if shapeNode.GetNumberOfControlPoints() < 4:
            self.showStatusMessage("Shape node has less than 4 control points.")
            return False
        volumeNode = self.ui.inputVolumeSelector.currentNode()
        if not volumeNode:
            self.showStatusMessage("No volume node selected.")
            return False
        
        segmentationNode = self.ui.outputSegmentationSelector.currentNode()
        if not segmentationNode:
            segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
            segmentationNode.CreateDefaultDisplayNodes()
            self.ui.outputSegmentationSelector.setCurrentNode(segmentationNode)
        return True
        
#
# ArteryPartsSegmentationLogic
#

class ArteryPartsSegmentationLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self) -> None:
        """
        Called when the logic class is instantiated. Can be used for initializing member variables.
        """
        ScriptedLoadableModuleLogic.__init__(self)

    def getParameterNode(self):
        return ArteryPartsSegmentationParameterNode(super().getParameterNode())

    def process(self,
                shapeNode,
                volumeNode: slicer.vtkMRMLScalarVolumeNode,
                segmentationNode: slicer.vtkMRMLSegmentationNode,
                lumenIntensityMin: float = 200.0,
                lumenIntensityMax: float = 450.0,
                accountForSoftCalcification = False,
                extrusionKernelSize = 0.0) -> None:

        if not shapeNode or not volumeNode or not segmentationNode:
            raise ValueError("Invalid input or output nodes.")
        if shapeNode.GetShapeName() != slicer.vtkMRMLMarkupsShapeNode.Tube:
            raise ValueError("Shape node is not a Tube.")
        if shapeNode.GetNumberOfUndefinedControlPoints():
            raise ValueError("Shape node has undefined control points.")
        if shapeNode.GetNumberOfControlPoints() < 4:
            raise ValueError("Shape node has less than 4 control points.")

        import time
        startTime = time.time()
        logging.info('Processing started')

        # Create slicer.modules.SegmentEditorWidget
        slicer.modules.segmenteditor.widgetRepresentation()
        seWidget = slicer.modules.SegmentEditorWidget.editor
        seWidget.setSegmentationNode(segmentationNode)
        seWidget.setSourceVolumeNode(volumeNode)
        segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(volumeNode)
        
        # Use OverwriteNone to preserve alien segments.
        seWidget.mrmlSegmentEditorNode().SetMaskMode(slicer.vtkMRMLSegmentationNode.EditAllowedEverywhere)
        seWidget.mrmlSegmentEditorNode().SourceVolumeIntensityMaskOff()
        seWidget.mrmlSegmentEditorNode().SetOverwriteMode(seWidget.mrmlSegmentEditorNode().OverwriteNone)
        
        # Crop the volume to the inside of the Tube using 'Split volume'.
        tubePolyData = shapeNode.GetCappedTubeWorld()
        segmentationNode.CreateClosedSurfaceRepresentation()
        tubeSegmentID = segmentationNode.AddSegmentFromClosedSurfaceRepresentation(tubePolyData, "Tube")
        seWidget.mrmlSegmentEditorNode().SetSelectedSegmentID(tubeSegmentID)
        
        intensityRange = volumeNode.GetImageData().GetScalarRange()
        seWidget.setActiveEffectByName("Split volume")
        effect = seWidget.activeEffect()
        # Fill with an intensity that does not exist in the volume, to avoid space outside the Tube later.
        effect.setParameter("FillValue", intensityRange[0] - 1)
        effect.setParameter("ApplyToAllVisibleSegments", 0)
        effect.self().onApply()
        seWidget.setActiveEffectByName(None)
        
        # Get the split volume. 'Split volume' effect does not provide it.
        allScalarVolumeNodes = slicer.mrmlScene.GetNodesByClass("vtkMRMLScalarVolumeNode")
        splitVolumeNode = allScalarVolumeNodes.GetItemAsObject(allScalarVolumeNodes.GetNumberOfItems() - 1)
        # Use the split volume.
        segmentationNode.GetSegmentation().RemoveSegment(tubeSegmentID)
        seWidget.setSourceVolumeNode(splitVolumeNode)
        segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(splitVolumeNode)
        
        # Create Lumen segment first.
        segmentID = "Lumen"
        if segmentationNode.GetSegmentation().GetSegment(segmentID):
            segmentationNode.GetSegmentation().RemoveSegment(segmentID)
        """
        Specified colours are badly handled. In slice views, it is not the
        expected colour. In the segment editor colour column, and in the 3D
        view, it's always white.
        """
        #lumenSegmentID = segmentationNode.GetSegmentation().AddEmptySegment(segmentID, "", (216.0, 101.0, 79.0))    
        lumenSegmentID = segmentationNode.GetSegmentation().AddEmptySegment(segmentID)
        seWidget.mrmlSegmentEditorNode().SetSelectedSegmentID(lumenSegmentID)
        seWidget.setActiveEffectByName("Threshold")
        effect = seWidget.activeEffect()
        effect.setParameter("MinimumThreshold", str(lumenIntensityMin))
        effect.setParameter("MaximumThreshold", str(lumenIntensityMax))
        effect.self().onApply()
        seWidget.setActiveEffectByName(None)
        
        """
        Threshold effect will include 'soft' calcification, the intensities of
        which are in the lumen intensity range. Hairy extrusions may connect
        them to the lumen. Break these.
        """
        if accountForSoftCalcification or (extrusionKernelSize > 0.0):
            import SegmentEditorSmoothingEffect
            seWidget.setActiveEffectByName("Smoothing")
            effect = seWidget.activeEffect()
            effect.setParameter("SmoothingMethod", SegmentEditorSmoothingEffect.MORPHOLOGICAL_OPENING)
            effect.setParameter("KernelSizeMm", str(extrusionKernelSize))
            effect.self().onApply()
            seWidget.setActiveEffectByName(None)
        
        """
        The 'soft' calcification is usually islands on the artery's wall. Remove
        them so that they are later rightly segmented as calcification.
        Caveat : an artery with an obliterated portion cannot be fully segmented
        in parts with this effect, only one part of the lumen will remain.
        Very badly diseased arteries with too much 'soft' calcification may be
        also bad candidates for this approach.
        """
        if accountForSoftCalcification:
            seWidget.setActiveEffectByName("Islands")
            effect = seWidget.activeEffect()
            effect.setParameter("Operation", "KEEP_LARGEST_ISLAND")
            effect.self().onApply()
            seWidget.setActiveEffectByName(None)
        
        """
        Threshold the calcification. On request, try to include the 'soft' calcification
        too. Their intensities are within the intensity range of the lumen, so
        we segment outside all other segments.
        """
        seWidget.mrmlSegmentEditorNode().SetMaskMode(slicer.vtkMRMLSegmentationNode.EditAllowedOutsideAllSegments)
        seWidget.mrmlSegmentEditorNode().SourceVolumeIntensityMaskOff()
        seWidget.mrmlSegmentEditorNode().SetOverwriteMode(seWidget.mrmlSegmentEditorNode().OverwriteNone)
        
        segmentID = "Calcification"
        if segmentationNode.GetSegmentation().GetSegment(segmentID):
            segmentationNode.GetSegmentation().RemoveSegment(segmentID)
        #calcifiedLesionSegmentID = segmentationNode.GetSegmentation().AddEmptySegment(segmentID, "", (241.0, 214.0, 145.0))
        calcifiedLesionSegmentID = segmentationNode.GetSegmentation().AddEmptySegment(segmentID)
        seWidget.mrmlSegmentEditorNode().SetSelectedSegmentID(calcifiedLesionSegmentID)
        seWidget.setActiveEffectByName("Threshold")
        effect = seWidget.activeEffect()
        # 2.0 seems a good minimal, may be optimized later, or given a UI widget.
        minimumThresholdIntensity = lumenIntensityMax + 1
        if accountForSoftCalcification:
            # Grab some intensities that overlap with those of the lumen.
            minimumThresholdIntensity = (lumenIntensityMin + lumenIntensityMax) / 2.0
        effect.setParameter("MinimumThreshold", str(minimumThresholdIntensity))
        effect.setParameter("MaximumThreshold", str(intensityRange[1]))
        effect.self().onApply()
        seWidget.setActiveEffectByName(None)
        """
        It is probable that the calcification segment will need an extrusion
        smoothing too if it *predominates much* on soft lesion.
        Manual cleaning with the brush may be helpful too.
        """
        
        # Let everything else be soft lesion, or simply patches of the wall.
        seWidget.mrmlSegmentEditorNode().SetMaskMode(slicer.vtkMRMLSegmentationNode.EditAllowedEverywhere)
        seWidget.mrmlSegmentEditorNode().SourceVolumeIntensityMaskOff()
        seWidget.mrmlSegmentEditorNode().SetOverwriteMode(seWidget.mrmlSegmentEditorNode().OverwriteNone)
        
        segmentID = "Soft lesion"
        if segmentationNode.GetSegmentation().GetSegment(segmentID):
            segmentationNode.GetSegmentation().RemoveSegment(segmentID)
        #softLesionSegmentID = segmentationNode.GetSegmentation().AddEmptySegment(segmentID, "", (47.0, 150.0, 103.0))
        softLesionSegmentID = segmentationNode.GetSegmentation().AddEmptySegment(segmentID)
        seWidget.mrmlSegmentEditorNode().SetSelectedSegmentID(softLesionSegmentID)
        seWidget.setActiveEffectByName("Threshold")
        effect = seWidget.activeEffect()
        effect.setParameter("MinimumThreshold", str(intensityRange[0]))
        # Leave lumenIntensityMin to the lumen.
        effect.setParameter("MaximumThreshold", str(lumenIntensityMin - 1))
        effect.self().onApply()
        seWidget.setActiveEffectByName(None)
        """
        It is probable that the soft lesion segment will need an extrusion
        smoothing too if it *predominates much* on calcification.
        Manual cleaning with the brush may be helpful too.
        """
        
        # Reparent subject hierarchy items.
        shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
        shSplitVolumeId = shNode.GetItemByDataNode(splitVolumeNode)
        shSplitVolumeFolderId = shNode.GetItemParent(shSplitVolumeId) # To be removed.
        shSplitVolumeStudyId = shNode.GetItemParent(shSplitVolumeFolderId) # Is root scene ID for NRRD files.
        shSegmentationId = shNode.GetItemByDataNode(segmentationNode)
        shNode.SetItemParent(shSplitVolumeId, shSplitVolumeStudyId)
        shNode.SetItemParent(shSegmentationId, shSplitVolumeStudyId)
        if shNode.GetItemLevel(shSplitVolumeFolderId) == "Folder":
            shNode.RemoveItem(shSplitVolumeFolderId)
        # Remove temporary volume and get things back.
        slicer.mrmlScene.RemoveNode(splitVolumeNode)
        seWidget.setSourceVolumeNode(volumeNode)
        segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(volumeNode)

        stopTime = time.time()
        logging.info(f'Processing completed in {stopTime-startTime:.2f} seconds')


#
# ArteryPartsSegmentationTest
#

class ArteryPartsSegmentationTest(ScriptedLoadableModuleTest):

    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here.
        """
        self.setUp()
        self.test_ArteryPartsSegmentation1()

    def test_ArteryPartsSegmentation1(self):
        self.delayDisplay("Starting the test")

        self.delayDisplay('Test passed')
