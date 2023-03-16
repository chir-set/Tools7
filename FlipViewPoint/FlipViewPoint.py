import os
import unittest
import logging
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

#
# FlipViewPoint
#

class FlipViewPoint(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Rotate and flip slice views"  # TODO: make this more human readable by adding spaces
    self.parent.categories = ["Utilities"]  # TODO: set categories (folders where the module shows up in the module selector)
    self.parent.dependencies = []  # TODO: add here list of module names that this module requires
    self.parent.contributors = ["Saleem Edah-Tally [Surgeon] [Hobbyist developer]"]  # TODO: replace with "Firstname Lastname (Organization)"
    # TODO: update with short description of the module and a link to online module documentation
    self.parent.helpText = """
Rotate slice views or flip by 180°.
See more information in <a href="https://github.com/chir-set/FlipViewPoint">module documentation</a>.
"""
    # TODO: replace with organization, grant and thanks
    self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
"""

class FlipViewPointWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent=None):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.__init__(self, parent)
    VTKObservationMixin.__init__(self)  # needed for parameter node observation
    self.logic = None
    self._parameterNode = None
    self._updatingGUIFromParameterNode = False

  def setup(self):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer).
    # Additional widgets can be instantiated manually and added to self.layout.
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/FlipViewPoint.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    # Create logic class. Logic implements all computations that should be possible to run
    # in batch mode, without a graphical user interface.
    self.logic = FlipViewPointLogic()

    # Connections

    self.ui.xAxisRadioButton.connect("clicked()", self.onXAxisRadioButton)
    self.ui.yAxisRadioButton.connect("clicked()", self.onYAxisRadioButton)
    self.ui.zAxisRadioButton.connect("clicked()", self.onZAxisRadioButton)
    self.ui.flipPushButton.connect('clicked(bool)', self.onFlipButton)
    self.ui.angleSliderWidget.connect("valueChanged(double)", self.onAngleSliderWidget)
    self.ui.restorePushButton.connect('clicked(bool)', self.onRestoreButton)
    
  def onXAxisRadioButton(self):
    sliceNode = self.ui.sliceNodeSelector.currentNode()
    self.logic.setAxis(sliceNode, "X")
    self.ui.angleSliderWidget.setValue(0.0)

  def onYAxisRadioButton(self):
    sliceNode = self.ui.sliceNodeSelector.currentNode()
    self.logic.setAxis(sliceNode, "Y")
    self.ui.angleSliderWidget.setValue(0.0)
    
  def onZAxisRadioButton(self):
    sliceNode = self.ui.sliceNodeSelector.currentNode()
    self.logic.setAxis(sliceNode, "Z")
    self.ui.angleSliderWidget.setValue(0.0)
    
  def onFlipButton(self):
    sliceNode = self.ui.sliceNodeSelector.currentNode()
    self.logic.flip(sliceNode)

  def onAngleSliderWidget(self):
    sliceNode = self.ui.sliceNodeSelector.currentNode()
    if sliceNode is None:
        return
    angle = self.ui.angleSliderWidget.value
    self.logic.rotate(sliceNode, angle)
    
  def onRestoreButton(self):
    self.logic.restoreViews()
    self.ui.angleSliderWidget.setValue(0.0)

#
# FlipViewPointLogic
#

class FlipViewPointLogic(ScriptedLoadableModuleLogic):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget.
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self):
    """
    Called when the logic class is instantiated. Can be used for initializing member variables.
    """
    ScriptedLoadableModuleLogic.__init__(self)
    self.currentAxis = "Y"
    
  def setAxis(self, sliceNode, axis):
    if sliceNode is None:
        return;
    self.currentAxis = axis
    attributeName = "current" + axis + "Rotation"
    sliceNode.SetAttribute(attributeName, "0.0")

  #https://www.slicer.org/wiki/Documentation/Nightly/ScriptRepository#Change_slice_orientation
  def flip(self, sliceNode):
    if sliceNode is None:
        return;
    SliceToRAS = sliceNode.GetSliceToRAS()
    transform=vtk.vtkTransform()
    transform.SetMatrix(SliceToRAS)
    if self.currentAxis == "X":
        transform.RotateX(180)
    elif self.currentAxis == "Y":
        transform.RotateY(180)
    elif self.currentAxis == "Z":
        transform.RotateZ(180)
    else:
        msg = "Unknown axis."
        slicer.util.showStatusMessage(msg, 3000)
        raise ValueError(msg)
    
    SliceToRAS.DeepCopy(transform.GetMatrix())
    sliceNode.UpdateMatrices()

  def calculateDifferentialAngle(self, sliceNode, angle):
    currentRotation = 0.0
    attributeName = "current" + self.currentAxis + "Rotation"
    if sliceNode is None:
        return (attributeName, currentRotation)
    if sliceNode.GetAttribute(attributeName):
        currentRotation = float(sliceNode.GetAttribute(attributeName))
    return (attributeName, (angle - currentRotation))
  
  def rotate(self, sliceNode, angle):
    if sliceNode is None:
        return
    labelledAngle = self.calculateDifferentialAngle(sliceNode, angle)
    SliceToRAS = sliceNode.GetSliceToRAS()
    transform=vtk.vtkTransform()
    transform.SetMatrix(SliceToRAS)
    if self.currentAxis == "X":
        transform.RotateX(labelledAngle[1])
    elif self.currentAxis == "Y":
        transform.RotateY(labelledAngle[1])
    elif self.currentAxis == "Z":
        transform.RotateZ(labelledAngle[1])
    else:
        msg = "Unknown axis."
        slicer.util.showStatusMessage(msg, 3000)
        raise ValueError(msg)
    
    SliceToRAS.DeepCopy(transform.GetMatrix())
    sliceNode.UpdateMatrices()
    sliceNode.SetAttribute(labelledAngle[0], str(angle))
    
  def restoreViews(self):
    views = slicer.app.layoutManager().sliceViewNames()
    for view in views:
        sliceNode = slicer.app.layoutManager().sliceWidget(view).mrmlSliceNode()
        sliceNode.SetOrientationToDefault()
        for axis in ("X", "Y", "Z"):
            attributeName = "current" + axis + "Rotation"
            sliceNode.SetAttribute(attributeName, "0.0")

#
# FlipViewPointTest
#

class FlipViewPointTest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setUp(self):
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    slicer.mrmlScene.Clear()

  def runTest(self):
    """Run as few or as many tests as needed here.
    """
    self.setUp()
    self.test_FlipViewPoint1()

  def test_FlipViewPoint1(self):
    """
    """
