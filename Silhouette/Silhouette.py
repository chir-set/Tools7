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
# Silhouette
#

class Silhouette(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Silhouette"  # TODO: make this more human readable by adding spaces
        self.parent.categories = ["Utilities"]  # TODO: set categories (folders where the module shows up in the module selector)
        self.parent.dependencies = []  # TODO: add here list of module names that this module requires
        self.parent.contributors = ["Saleem Edah-Tally [Surgeon] [Hobbyist developer]"]  # TODO: replace with "Firstname Lastname (Organization)"
        # TODO: update with short description of the module and a link to online module documentation
        self.parent.helpText = """
Create an outline model of a segment.
See more information in <a href="href="https://github.com/chir-set/Tools7/Silhouette/">module documentation</a>.
"""
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
"""

#
# SilhouetteParameterNode
#

@parameterNodeWrapper
class SilhouetteParameterNode:
    # inputSegmentation: slicer.vtkMRMLSegmentationNode # Doesn't work.
    outputModel: slicer.vtkMRMLModelNode

#
# SilhouetteWidget
#

class SilhouetteWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/Silhouette.ui'))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = SilhouetteLogic()

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

    def setParameterNode(self, inputParameterNode: Optional[SilhouetteParameterNode]) -> None:
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
        
        segmentationNode = self.ui.segmentSelector.currentNode()
        if segmentationNode is None:
            self.showStatusMessage("Segmentation node is None.")
            return
        segmentID = self.ui.segmentSelector.currentSegmentID()
        if segmentID is None or segmentID == "" :
            self.showStatusMessage("Segment ID is None or empty.")
            return
        modelNode = self.ui.modelSelector.currentNode()
        if modelNode is None:
            modelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode")
            modelNode.CreateDefaultDisplayNodes()
        self.logic.process(segmentationNode, segmentID, modelNode)
        self.ui.modelSelector.setCurrentNode(modelNode)
#
# SilhouetteLogic
#

class SilhouetteLogic(ScriptedLoadableModuleLogic):
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
        return SilhouetteParameterNode(super().getParameterNode())

    def process(self, segmentationNode, segmentID, outputModelNode) -> None:
        import time
        startTime = time.time()
        logging.info('Processing started')
        
        if not segmentationNode:
            logging.info("Segmentation node is None.")
            return
        if not segmentID or segmentID == "":
            logging.info("Segment ID is None or empty.")
            return
        if not segmentationNode.GetSegmentation().GetSegment(segmentID):
            logging.info("Segment ID is missing in the segmentation node.")
            return
        if not outputModelNode:
            logging.info("Provide an output model node.")
            return

        camera = slicer.util.getNode("Camera")
        # Create slicer.modules.SegmentEditorWidget
        slicer.modules.segmenteditor.widgetRepresentation()
        editor = slicer.modules.SegmentEditorWidget.editor
        
        segmentation = editor.segmentationNode()
        if not segmentation.CreateClosedSurfaceRepresentation():
            logging.info("Could not create closed surface representation.")
            return
        segmentPolyData = vtk.vtkPolyData()
        segmentation.GetClosedSurfaceRepresentation(segmentID, segmentPolyData)
        if segmentPolyData.GetNumberOfPoints() == 0:
            logging.info("Segment polydata is empty.")
            return
        
        silhouette = vtk.vtkPolyDataSilhouette()
        silhouette.SetCamera(camera.GetCamera())
        silhouette.SetInputData(segmentPolyData)
        silhouette.Update()
        
        if outputModelNode.GetPolyData():
            outputModelNode.GetPolyData().Initialize() # Destructive
        outputModelNode.SetPolyDataConnection(silhouette.GetOutputPort())
        segmentName = segmentation.GetSegmentation().GetSegment(segmentID).GetName()
        modelName = segmentation.GetName() + "_" + segmentName
        outputModelNode.SetName(modelName)
        
        modelColor = outputModelNode.GetDisplayNode().GetColor()
        segmentColor = segmentation.GetSegmentation().GetSegment(segmentID).GetColor()
        silhouetteColor = [1.0 - segmentColor[0], \
            1.0 - segmentColor[1], \
            1.0 - segmentColor[2]]
        outputModelNode.GetDisplayNode().SetColor(silhouetteColor)

        stopTime = time.time()
        logging.info(f'Processing completed in {stopTime-startTime:.2f} seconds')


#
# SilhouetteTest
#

class SilhouetteTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """ Do whatever is needed to reset the state - typically a scene clear will be enough.
        """
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here.
        """
        self.setUp()
        self.test_Silhouette1()

    def test_Silhouette1(self):
        pass
