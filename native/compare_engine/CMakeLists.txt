cmake_minimum_required(VERSION 3.18)
project(pdfdiff_compare_engine LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# pybind11
include(FetchContent)
FetchContent_Declare(
  pybind11
  GIT_REPOSITORY https://github.com/pybind/pybind11.git
  GIT_TAG        v2.13.6
)
FetchContent_MakeAvailable(pybind11)

# Core library
add_library(compare_core STATIC
  src/normalizer.cpp
  src/comparator.cpp
)

target_include_directories(compare_core PUBLIC include)

# Python module
pybind11_add_module(compare_engine python/bindings.cpp)
target_link_libraries(compare_engine PRIVATE compare_core)

# Optional: install
install(TARGETS compare_engine DESTINATION .)
