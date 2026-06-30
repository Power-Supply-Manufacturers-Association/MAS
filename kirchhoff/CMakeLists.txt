cmake_minimum_required(VERSION 3.15)
project(MAS_kirchhoff LANGUAGES CXX)

# Kirchhoff's MAS->CIAS converter build. SEPARATE from MAS's existing reference-binding CMakeLists.txt
# (which builds the UnitTest++ schema harness). For P1 the converter needs only the magnetic
# designRequirements, so MAS.hpp is generated from inputs/designRequirements.json. The
# DATASHEET/MKF_MODEL origins (Phase 4) will need the full MAS.hpp (MAS.json + the BUILD.md -S graph)
# and a link against MKF for export_magnetic_as_subcircuit.

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if (NOT CMAKE_CXX_COMPILER_ID STREQUAL "MSVC")
    set(CMAKE_POSITION_INDEPENDENT_CODE ON)
endif()

set(MAS_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/..")

include(FetchContent)
FetchContent_Declare(json
    GIT_REPOSITORY https://github.com/nlohmann/json.git
    GIT_TAG tags/v3.11.3)
FetchContent_MakeAvailable(json)

find_program(QUICKTYPE quicktype REQUIRED)
set(MAS_HPP "${CMAKE_CURRENT_BINARY_DIR}/MAS.hpp")
set(PEAS_SCHEMAS "${MAS_ROOT}/../PEAS/schemas")
add_custom_command(
    OUTPUT "${MAS_HPP}"
    COMMAND "${QUICKTYPE}" -l c++ -s schema
            "${MAS_ROOT}/schemas/inputs/designRequirements.json"
            -S "${MAS_ROOT}/schemas/utils.json"
            -S "${PEAS_SCHEMAS}/utils.json"
            -t MagneticDesignRequirements
            -o "${MAS_HPP}"
            --namespace MAS --source-style single-source --type-style pascal-case
            --member-style underscore-case --enumerator-style upper-underscore-case --no-boost
    DEPENDS "${MAS_ROOT}/schemas/inputs/designRequirements.json"
            "${MAS_ROOT}/schemas/utils.json"
    COMMENT "Generating MAS.hpp (magnetic designRequirements) via quicktype"
    VERBATIM)
add_custom_target(mas_generated_header DEPENDS "${MAS_HPP}")

add_library(MAS_kirchhoff STATIC "${MAS_ROOT}/src/MasConverter.cpp")
add_dependencies(MAS_kirchhoff mas_generated_header)
target_include_directories(MAS_kirchhoff PUBLIC
    "${MAS_ROOT}/src"
    "${CMAKE_CURRENT_BINARY_DIR}"
    "${MAS_ROOT}/../PEAS/src")
target_link_libraries(MAS_kirchhoff PUBLIC nlohmann_json::nlohmann_json)
target_include_directories(MAS_kirchhoff PRIVATE "${json_SOURCE_DIR}/include/nlohmann")

if (NOT EMSCRIPTEN)
    enable_testing()
    FetchContent_Declare(Catch2
        GIT_REPOSITORY https://github.com/catchorg/Catch2.git GIT_TAG v3.8.1)
    FetchContent_MakeAvailable(Catch2)
    add_executable(mas_tests test_mas_cias.cpp)
    target_link_libraries(mas_tests PRIVATE MAS_kirchhoff Catch2::Catch2WithMain)
    add_test(NAME mas_tests COMMAND mas_tests)

    option(MAS_BUILD_PYBIND "Build the PyMAS pybind11 module" ON)
    if (MAS_BUILD_PYBIND)
        FetchContent_Declare(pybind11
            GIT_REPOSITORY https://github.com/pybind/pybind11.git GIT_TAG v2.13.6)
        FetchContent_Declare(pybind11_json
            GIT_REPOSITORY https://github.com/pybind/pybind11_json.git)
        FetchContent_MakeAvailable(pybind11 pybind11_json)
        pybind11_add_module(PyMAS bindings.cpp)
        add_dependencies(PyMAS mas_generated_header)
        target_include_directories(PyMAS PRIVATE
            "${MAS_ROOT}/src" "${MAS_ROOT}/../PEAS/src"
            "${pybind11_json_SOURCE_DIR}/include")
        target_link_libraries(PyMAS PRIVATE MAS_kirchhoff)
    endif()
else()
    add_executable(libMAS libMAS.cpp)
    add_dependencies(libMAS mas_generated_header)
    target_include_directories(libMAS PRIVATE
        "${MAS_ROOT}/src" "${MAS_ROOT}/../PEAS/src")
    target_link_libraries(libMAS PRIVATE MAS_kirchhoff)
    set_target_properties(libMAS PROPERTIES SUFFIX ".wasm.js")
    target_compile_options(libMAS PRIVATE -fwasm-exceptions)
    target_link_options(libMAS PRIVATE
        -fwasm-exceptions -sWASM=1 -sALLOW_MEMORY_GROWTH -sEXPORT_ES6=1
        -sMODULARIZE=1 -sENVIRONMENT=web,node --bind)
endif()
