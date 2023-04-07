import os
import unittest
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
import logging

#
# TemplateROICrop : see notes below
#
TITLE = "Template ROI Crop"
class TemplateROICrop(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = TITLE
    self.parent.categories = ["Utilities"]
    self.parent.dependencies = []
    self.parent.contributors = ["Saleem Edah-Tally [Surgeon] [Hobbyist developer]"] # replace with "Firstname Lastname (Organization)"
    self.parent.helpText = """
Crops a volume based on a saved template ROI. See more information in <a href="https://github.com/chir-set/Tools7/TemplateROICrop">module documentation</a>
"""
    self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc.
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
""" # replace with organization, grant and thanks.
#
# TemplateROICropWidget
#

class TemplateROICropWidget(ScriptedLoadableModuleWidget):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    # Instantiate and connect widgets ...

    #
    # Parameters Area
    #
    parametersCollapsibleButton = ctk.ctkCollapsibleButton()
    parametersCollapsibleButton.text = "Parameters"
    self.layout.addWidget(parametersCollapsibleButton)

    # Layout within the dummy collapsible button
    parametersFormLayout = qt.QFormLayout(parametersCollapsibleButton)
    #version = qt.QLabel(TITLE + ' - version 2')
    #parametersFormLayout.addRow(version)

    #
    # input volume selector
    #
    self.inputSelector = slicer.qMRMLNodeComboBox()
    self.inputSelector.nodeTypes = ["vtkMRMLScalarVolumeNode"]
    self.inputSelector.selectNodeUponCreation = True
    self.inputSelector.addEnabled = False
    self.inputSelector.removeEnabled = True
    self.inputSelector.renameEnabled = True
    self.inputSelector.noneEnabled = False
    self.inputSelector.showHidden = False
    self.inputSelector.showChildNodeTypes = False
    self.inputSelector.setMRMLScene( slicer.mrmlScene )
    self.inputSelector.setToolTip( "Pick the input to the algorithm." )
    parametersFormLayout.addRow("Input Volume: ", self.inputSelector)
    
    #
    # output volume selector
    #
    self.outputSelector = slicer.qMRMLNodeComboBox()
    self.outputSelector.nodeTypes = ["vtkMRMLScalarVolumeNode"]
    self.outputSelector.selectNodeUponCreation = False
    self.outputSelector.addEnabled = False
    self.outputSelector.removeEnabled = True
    self.outputSelector.renameEnabled = True
    self.outputSelector.noneEnabled = True
    self.outputSelector.showHidden = False
    self.outputSelector.showChildNodeTypes = False
    self.outputSelector.setMRMLScene( slicer.mrmlScene )
    self.outputSelector.setToolTip( "Pick the output to the algorithm." )
    parametersFormLayout.addRow("Output Volume: ", self.outputSelector)
    
    #
    # Remember template ROIs.
    # To delete items, edit $HOME/.config/NA-MIC/Slicer.ini @[ctkPathLineEdit]
    #
    
    self.ROITemplateSelector = ctk.ctkPathLineEdit()
    self.ROITemplateSelector.filters = ctk.ctkPathLineEdit.Files
    self.ROITemplateSelector.settingKey = 'ROITemplateFile'
    self.ROITemplateSelector.nameFilters = ['ROI files (*.mrk.json)']
    self.ROITemplateSelector.retrieveHistory()
    parametersFormLayout.addRow("ROI template:", self.ROITemplateSelector)
    self.saveROIButton = qt.QPushButton("Remember selected ROI")
    parametersFormLayout.addRow(self.saveROIButton)

    #
    # We want to go to Volume Rendering after cropping
    #
    self.gotoVRButton = qt.QPushButton("Go to Volume Rendering")
    self.gotoVRButton.enabled = False
    parametersFormLayout.addRow(self.gotoVRButton)

    #
    # Apply Button
    #
    self.applyButton = qt.QPushButton("Apply")
    self.applyButton.toolTip = "Run the algorithm."
    self.applyButton.enabled = True
    parametersFormLayout.addRow(self.applyButton)

    # connections
    self.applyButton.connect('clicked(bool)', self.onApplyButton)
    self.inputSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelect)
    self.gotoVRButton.connect('clicked(bool)', self.onGoToVR)
    # https://github.com/SlicerIGT/SlicerIGT/blob/master/Guidelet/GuideletLib/Guidelet.py
    #self.ROITemplateSelector.connect('currentPathChanged(QString)', self.onPathChanged)
    self.saveROIButton.connect('clicked(bool)', self.onSaveROI)

    # Add vertical spacer
    self.layout.addStretch(1)

  def cleanup(self):
    pass

  def onSelect(self):
    self.gotoVRButton.enabled = False
    self.outputSelector.setCurrentNode(None)
    
  def onApplyButton(self):
    self.gotoVRButton.enabled = False
    logic = TemplateROICropLogic()
    outputVolumeNodeID = logic.run(self.inputSelector.currentNode(), self.ROITemplateSelector.currentPath)
    self.outputSelector.setCurrentNodeID(outputVolumeNodeID)
    self.gotoVRButton.enabled = True
    
  def onGoToVR(self):
    mainWindow = slicer.util.mainWindow()
    mainWindow.moduleSelector().selectModule('VolumeRendering')
  
  # Slicer hangs when a combobox item is selected !!!
  # def onPathChanged(self):
  #  self.ROITemplateSelector.addCurrentPathToHistory()

  def onSaveROI(self):
    self.ROITemplateSelector.addCurrentPathToHistory()

#
# TemplateROICropLogic
#

class TemplateROICropLogic(ScriptedLoadableModuleLogic):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget.
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def run(self, inputVolume, ROITemplateSelectorPath):
    """
    Run the actual algorithm
    """
    if inputVolume is None:
        return False
    """
    Add Data no longer loads DICOM series rightly
    See : 
    https://discourse.slicer.org/t/dicom-volume-orientation-may-be-bad/10068/1
    https://discourse.slicer.org/t/python-how-to-centre-volume-on-load/10220/1
    """
    volumesLogic = slicer.modules.volumes.logic()
    volumesLogic.CenterVolume(inputVolume)
    
    # https://www.slicer.org/wiki/Documentation/Nightly/ScriptRepository
    displayNode = inputVolume.GetDisplayNode()
    displayNode.AutoWindowLevelOff()
    # CT-Bones
    displayNode.SetWindow(1000)
    displayNode.SetLevel(400)
    
    roi=slicer.util.loadMarkups(ROITemplateSelectorPath)
    return self.basicCropVolume(inputVolume, roi)
    """
    TODO: Prevent the file path from being added to the recent history list. Or delete the entry. Perhaps Slicer should prevent duplicate entries in that list.
    """

  def basicCropVolume(self, inputVolume, roi, interpolate = False):
    cropLogic = slicer.modules.cropvolume.logic()
    cvpn = slicer.vtkMRMLCropVolumeParametersNode()

    cvpn.SetROINodeID(roi.GetID())
    cvpn.SetInputVolumeNodeID(inputVolume.GetID())
    cvpn.SetVoxelBased(not interpolate)
    cropLogic.Apply(cvpn)
    roi.SetDisplayVisibility(False)
    
    outputVolumeNodeID = cvpn.GetOutputVolumeNodeID()
    #https://www.slicer.org/wiki/Documentation/4.3/Developers/Python_scripting
    views = slicer.app.layoutManager().sliceViewNames()
    for view in views:
        view_logic = slicer.app.layoutManager().sliceWidget(view).sliceLogic()
        view_cn = view_logic.GetSliceCompositeNode()
        view_cn.SetBackgroundVolumeID(outputVolumeNodeID)
        view_logic.FitSliceToAll()
    
    return outputVolumeNodeID


class TemplateROICropTest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setUp(self):
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    slicer.mrmlScene.Clear(0)

  def runTest(self):
    """Run as few or as many tests as needed here.
    """
    self.setUp()
    self.test_TemplateROICrop1()

  def test_TemplateROICrop1(self):
    """ Ideally you should have several levels of tests.  At the lowest level
    tests should exercise the functionality of the logic with different inputs
    (both valid and invalid).  At higher levels your tests should emulate the
    way the user would interact with your code and confirm that it still works
    the way you intended.
    One of the most important features of the tests is that it should alert other
    developers when their changes will have an impact on the behavior of your
    module.  For example, if a developer removes a feature that you depend on,
    your test should break so they know that the feature is needed.
    """

    self.delayDisplay("Starting the test")
    #
    # first, get some data
    #
    import urllib
    downloads = (
        ('http://slicer.kitware.com/midas3/download?items=5767', 'FA.nrrd', slicer.util.loadVolume),
        )

    for url,name,loader in downloads:
      filePath = slicer.app.temporaryPath + '/' + name
      if not os.path.exists(filePath) or os.stat(filePath).st_size == 0:
        logging.info('Requesting download %s from %s...\n' % (name, url))
        urllib.urlretrieve(url, filePath)
      if loader:
        logging.info('Loading %s...' % (name,))
        loader(filePath)
    self.delayDisplay('Finished with download and loading')

    volumeNode = slicer.util.getNode(pattern="FA")
    logic = TemplateROICropLogic()
    self.assertIsNotNone( logic.hasImageData(volumeNode) )
    self.delayDisplay('Test passed!')

"""
USAGE : Save a known ROI, having a distinct object name, in a *.acsv file first.
        This should be done in a loaded volume. We plan to load more volumes of the same type routinely. Close the reference volume.
        
        In a production workflow :
        Select a volume of the same type, known to be bigger than the ROI.
        Select a template ROI.
        Apply to crop the volume.
        Example: CT scan from chest to feet. Template ROI from diaphragm to ankle. Template ROI for the aorto-iliac segment.
        
        Big DICOM volume sample with my useful ROIs :
        https://mega.nz/#!UEtAmYgS!gyHsEM-_fV2FNn99jiil3fM0BB4Z9vuWs6IZxsxr81c
        
        DISCLAIMER
        This module suits my particular needs.
        I don't really know Python. Code from different sources have been glued together.
        I just have a hobbyist C++ superficial experience.
"""
