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

from scipy.optimize import least_squares
import numpy as np
#
# MarkupsToSurface
#

class MarkupsToSurface(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Markups to surface"  # TODO: make this more human readable by adding spaces
        self.parent.categories = ["Utilities"]  # TODO: set categories (folders where the module shows up in the module selector)
        self.parent.dependencies = []  # TODO: add here list of module names that this module requires
        self.parent.contributors = ["Saleem Edah-Tally [Surgeon] [Hobbyist developer]"]  # TODO: replace with "Firstname Lastname (Organization)"
        # TODO: update with short description of the module and a link to online module documentation
        self.parent.helpText = """
Create models and segments from markups nodes.
See more information in <a href="href="https://github.com/chir-set/Tools7/MarkupsToSurface/">module documentation</a>.
"""
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
"""

#
# MarkupsToSurfaceParameterNode
#

@parameterNodeWrapper
class MarkupsToSurfaceParameterNode:
    pass


#
# MarkupsToSurfaceWidget
#

class MarkupsToSurfaceWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/MarkupsToSurface.ui'))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = MarkupsToSurfaceLogic()

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # Buttons
        self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)
        self.ui.inputSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.onMarkupsChanged)
        
        self.ui.resultLineEdit.setVisible(False)
        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()
        
        if not slicer.app.testingEnabled():
            try:
                self.installExtensionFromServer(["ExtraMarkups"])
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

    def setParameterNode(self, inputParameterNode: Optional[MarkupsToSurfaceParameterNode]) -> None:
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
        inputMarkups = self.ui.inputSelector.currentNode()
        if inputMarkups is None:
            self.showStatusMessage("Provide an input markups node.")
            return
        
        outputModel = self.ui.outputModelSelector.currentNode()
        outputSegmentation = self.ui.outputSegmentationSelector.currentNode()
        if outputModel is None and outputSegmentation is None:
            self.showStatusMessage("Provide at least a model or a segmentation node to hold the output surface.")
            return
        
        with slicer.util.tryWithErrorDisplay("Failed to compute results.", waitCursor=True):
                
            result = self.logic.process(inputMarkups, outputModel, outputSegmentation)
            if result and inputMarkups.IsTypeOf("vtkMRMLMarkupsFiducialNode"):
                centre = (round(result[0][0], 3), round(result[0][1], 3), round(result[0][2], 3))
                tipText = "Centre: " + str(result[0]) + "\n\nRadius: " + str(result[1])
                text = "Centre: " + str(centre) + "; Radius: " + str(round(result[1], 3))
                self.ui.resultLineEdit.setText(text)
                self.ui.resultLineEdit.setVisible(True)
                self.ui.resultLineEdit.setToolTip(tipText)
            else:
                self.ui.resultLineEdit.clear()
                self.ui.resultLineEdit.setVisible(False)
                self.ui.resultLineEdit.setToolTip(None)

    def showStatusMessage(self, message, timeout = 3000) -> None:
        slicer.util.showStatusMessage(message, timeout)
        slicer.app.processEvents()
    
    def onMarkupsChanged(self, node) -> None:
        self.ui.resultLineEdit.clear()
        self.ui.resultLineEdit.setVisible(False)
        self.ui.resultLineEdit.setToolTip(None)
    
#
# MarkupsToSurfaceLogic
#

class MarkupsToSurfaceLogic(ScriptedLoadableModuleLogic):
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
        return MarkupsToSurfaceParameterNode(super().getParameterNode())

    def process(self,
                inputMarkups: slicer.vtkMRMLMarkupsNode,
                outputModel: slicer.vtkMRMLModelNode = None,
                outputSegmentation: slicer.vtkMRMLSegmentationNode = None) -> None:
        
        if inputMarkups is None:
            logging.error("Provide an input markups node.")
            return None
        if outputModel is None and outputSegmentation is None:
            logging.error("Provide at least a model or a segmentation node to hold the output surface.")
            return None
        
        import time
        startTime = time.time()
        logging.info('Processing started')
        
        if outputModel and outputModel.GetNumberOfDisplayNodes() == 0:
            outputModel.CreateDefaultDisplayNodes()
        if outputSegmentation and outputSegmentation.GetNumberOfDisplayNodes() == 0:
            outputSegmentation.CreateDefaultDisplayNodes()
        
        if inputMarkups.IsTypeOf("vtkMRMLMarkupsROINode"):
            # Account for transforms.
            node = slicer.vtkMRMLMarkupsROINode.SafeDownCast(inputMarkups)
            bounds = [ 0.0, 0.0, 0.0, 0.0, 0.0, 0.0 ]
            node.GetObjectBounds(bounds)
            matrix = node.GetObjectToWorldMatrix()
            cube = vtk.vtkCubeSource()
            cube.SetCenter(node.GetCenter())
            cube.SetBounds(bounds)
            cube.Update()
            
            transform = vtk.vtkTransform()
            transform.SetMatrix(matrix)
            filter = vtk.vtkTransformPolyDataFilter()
            filter.SetInputConnection(cube.GetOutputPort())
            filter.SetTransform(transform)
            filter.Update()
            
            if outputModel:
                outputModel.SetPolyDataConnection(filter.GetOutputPort())
            if outputSegmentation:
                segmentName = "Segment_" + node.GetName()
                outputSegmentation.CreateClosedSurfaceRepresentation()
                if outputSegmentation.GetSegmentation().GetSegment(segmentName):
                    outputSegmentation.GetSegmentation().RemoveSegment(segmentName)
                outputSegmentation.AddSegmentFromClosedSurfaceRepresentation(filter.GetOutput(), segmentName)
            return None
        elif inputMarkups.IsTypeOf("vtkMRMLMarkupsShapeNode"):
            node = slicer.vtkMRMLMarkupsShapeNode.SafeDownCast(inputMarkups)
            nodePolyData = node.GetShapeWorld()
            if node.GetShapeName() == slicer.vtkMRMLMarkupsShapeNode.Tube:
                nodePolyData = node.GetCappedTubeWorld()
            
            if outputModel:
                outputModel.SetAndObservePolyData(nodePolyData)
                
            if outputSegmentation:
                """
                1. Disk and Ring will appear nicely as long as they are not 'binary
                labelmap'. When 'Show 3D' button is disabled and enabled again,
                they just don't show up, too thin.
                2. Didn't find an equivalent of SetAndObservePolyData()
                for segments. They update in 3D views only when control points
                or interaction handles are moved. We must hit 'Apply' button
                again for slice views. Let go.'
                """
                segmentName = "Segment_" + node.GetName()
                outputSegmentation.CreateClosedSurfaceRepresentation()
                if outputSegmentation.GetSegmentation().GetSegment(segmentName):
                    outputSegmentation.GetSegmentation().RemoveSegment(segmentName)
                outputSegmentation.AddSegmentFromClosedSurfaceRepresentation(nodePolyData, segmentName)
            return None
        elif inputMarkups.IsTypeOf("vtkMRMLMarkupsFiducialNode"):
            """
            A special case : create a sphere from cloud points, because of :
            https://discourse.slicer.org/t/how-i-can-find-the-center-of-the-humeroulnar-joint-using-3d-slicer/27779
            Source : 
            https://github.com/thompson318/scikit-surgery-sphere-fitting/blob/master/sksurgeryspherefitting/algorithms/sphere_fitting.py
            """
            node = slicer.vtkMRMLMarkupsFiducialNode.SafeDownCast(inputMarkups)
            
            markupsPositions = slicer.util.arrayFromMarkupsControlPoints(node)
            numberOfControlPoints = node.GetNumberOfControlPoints()
            center0 = np.mean(markupsPositions, 0)
            radius0 = np.linalg.norm(np.amin(markupsPositions,0)-np.amax(markupsPositions,0))/2.0
            fittingResult = self._fit_sphere_least_squares(markupsPositions[:,0], markupsPositions[:,1], markupsPositions[:,2], [center0[0], center0[1], center0[2], radius0])
            centerX = centerY = centerZ = radius = 0.0
            [centerX, centerY, centerZ, radius] = fittingResult["x"]
            
            sphere = vtk.vtkSphereSource()
            sphere.SetPhiResolution(45)
            sphere.SetThetaResolution(45)
            sphere.SetCenter(centerX, centerY, centerZ)
            sphere.SetRadius(radius)
            sphere.Update()
            
            if outputModel:
                outputModel.SetPolyDataConnection(sphere.GetOutputPort())
                
            if outputSegmentation:
                segmentName = "Segment_" + node.GetName()
                outputSegmentation.CreateClosedSurfaceRepresentation()
                if outputSegmentation.GetSegmentation().GetSegment(segmentName):
                    outputSegmentation.GetSegmentation().RemoveSegment(segmentName)
                outputSegmentation.AddSegmentFromClosedSurfaceRepresentation(sphere.GetOutput(), segmentName)
            return [(centerX, centerY, centerZ), radius]
        else:
            logging.error("Input object is not managed.")
            
        stopTime = time.time()
        logging.info(f'Processing completed in {stopTime-startTime:.2f} seconds')

    def _fit_sphere_least_squares(self, x_values, y_values, z_values, initial_parameters, bounds=((-np.inf, -np.inf, -np.inf, -np.inf),(np.inf, np.inf, np.inf, np.inf))):
        return least_squares(self._calculate_residual_sphere, initial_parameters, bounds=bounds, method="trf", jac="3-point", args=(x_values, y_values, z_values))


    def _calculate_residual_sphere(self, parameters, x_values, y_values, z_values):
        #extract the parameters
        x_centre, y_centre, z_centre, radius = parameters
        #use np's sqrt function here, which works by element on arrays
        distance_from_centre = np.sqrt((x_values - x_centre)**2 + (y_values - y_centre)**2 + (z_values - z_centre)**2)
        return distance_from_centre - radius

#
# MarkupsToSurfaceTest
#

class MarkupsToSurfaceTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        self.test_MarkupsToSurface1()

    def test_MarkupsToSurface1(self):
        self.delayDisplay("Starting the test")

        self.delayDisplay('Test passed')
