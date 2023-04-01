cmake_minimum_required(VERSION 3.16.3...3.19.7 FATAL_ERROR)

project(Tools7)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://github.com/chir-set/Tools7")
set(EXTENSION_CATEGORY "Utilities")
set(EXTENSION_CONTRIBUTORS "Saleem Edah-Tally ([Surgeon] [Hobbyist developer])")
set(EXTENSION_DESCRIPTION "Modules useful to me; they won't meet the requirements of the official Slicer Extension Index.")
set(EXTENSION_ICONURL "https://github.com/chir-set/Tools7/Tools7.png")
set(EXTENSION_SCREENSHOTURLS "https://www.example.com/Slicer/Extensions/Tools7/Screenshots/1.png")
set(EXTENSION_DEPENDS "NA") # Specified as a list or "NA" if no dependencies

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(TemplateROICrop)
add_subdirectory(FlipViewPoint)
add_subdirectory(Silhouette)
add_subdirectory(BodyIsolation)
add_subdirectory(ArteryPartsSegmentation)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
