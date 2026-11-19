cmake_minimum_required(VERSION 3.15)
project(pressready LANGUAGES CXX)

set(PYBIND11_FINDPYTHON ON)
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(_inkcore cpp/inkcore.cpp)
target_compile_features(_inkcore PRIVATE cxx_std_17)

if(MSVC)
  target_compile_options(_inkcore PRIVATE /W4 /O2)
else()
  target_compile_options(_inkcore PRIVATE -Wall -Wextra -O3)
endif()

install(TARGETS _inkcore DESTINATION pressready)
