cmake_minimum_required(VERSION 3.18.0)

project(MAS_tests)

SET(CMAKE_CXX_STANDARD 20)
SET(CMAKE_CXX_STANDARD_REQUIRED ON)

option(BUILD_SHARED_LIBS      "Build tests"    ON)
option(BUILD_TESTS      "Build tests"    OFF)
option(BUILD_EXAMPLES   "Build examples" OFF)

include(FetchContent)

# House test framework is Catch2 (v3, Catch2WithMain). The binary is run
# DIRECTLY (./MAS_tests); no ctest registration on purpose.
FetchContent_Declare(Catch2
        GIT_REPOSITORY https://github.com/catchorg/Catch2.git
        GIT_TAG  tags/v3.8.1)

# jsoncons: header-only JSON library whose jsonschema extension implements
# JSON Schema draft 2020-12 NATIVELY — including $ref with sibling keywords
# and unevaluatedProperties, which the PSMA schemas rely on (the wire-subtype
# discriminators and the sealed allOf-extension objects). It replaces
# pboettch/json-schema-validator (draft-07 only, unevaluatedProperties
# silently ignored) and the lower_draft202012_ref_siblings() shim the tests
# used to need. Pinned to an exact release tag — never a branch.
set(JSONCONS_BUILD_TESTS OFF CACHE BOOL "" FORCE)
FetchContent_Declare(jsoncons
        GIT_REPOSITORY https://github.com/danielaparker/jsoncons.git
        GIT_TAG  tags/v1.8.1)

FetchContent_MakeAvailable(Catch2 jsoncons)

SET(CMAKE_CXX_FLAGS "-Wall -Wextra")

file(GLOB MAS_sources
    "tests/*.cpp")

add_executable(MAS_tests ${MAS_sources})
# jsoncons' schema evaluator is header-only template code: without optimization
# the ~18k-record NDJSON sweep runs ~15x slower. Force -O2 on this target so the
# suite stays fast even when no CMAKE_BUILD_TYPE is set.
target_compile_options(MAS_tests PRIVATE -O2)
# Include dirs come from the imported targets (jsoncons, Catch2::Catch2WithMain)
# — never hardcode ${CMAKE_BINARY_DIR}/_deps paths, they break when
# FETCHCONTENT_SOURCE_DIR_* redirects a dependency.
target_link_libraries(MAS_tests PRIVATE jsoncons Catch2::Catch2WithMain)
