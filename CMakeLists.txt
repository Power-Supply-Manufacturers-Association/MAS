cmake_minimum_required(VERSION 3.18.0)

project(MAS_tests)

SET(CMAKE_CXX_STANDARD 20)
SET(CMAKE_CXX_STANDARD_REQUIRED ON)
SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -pthread")

SET(CMAKE_CXX_FLAGS "-Wall -Wextra -Wno-deprecated-declarations -Wno-unused-parameter -Wno-switch")

option(BUILD_SHARED_LIBS      "Build tests"    ON)
option(BUILD_TESTS      "Build tests"    OFF)
option(BUILD_EXAMPLES   "Build examples" OFF)

include(FetchContent)

# House test framework is Catch2 (v3, Catch2WithMain). The binary is run
# DIRECTLY (./MAS_tests); no ctest registration on purpose.
FetchContent_Declare(Catch2
        GIT_REPOSITORY https://github.com/catchorg/Catch2.git
        GIT_TAG  tags/v3.8.1)

FetchContent_Declare(json
        GIT_REPOSITORY https://github.com/nlohmann/json/
        GIT_TAG  tags/v3.11.2)

FetchContent_Declare(json-schema-validator
        GIT_REPOSITORY https://github.com/pboettch/json-schema-validator.git
        GIT_TAG  origin/main)

FetchContent_MakeAvailable(Catch2 json json-schema-validator)

# Patch json-schema-validator to skip duplicate schema insertions instead of throwing.
# This fixes an issue where schemas with shared $ref dependencies cause "already inserted" errors.
# Use the FetchContent-provided source dir (NOT a hardcoded ${CMAKE_BINARY_DIR}/_deps path)
# so FETCHCONTENT_SOURCE_DIR_JSON-SCHEMA-VALIDATOR redirection keeps working, and only
# rewrite the file when the unpatched line is still present (idempotent, no spurious rebuilds).
set(JSON_VALIDATOR_THROW_LINE "throw std::invalid_argument(\"schema with \" + uri.to_string() + \" already inserted\");")
file(READ "${json-schema-validator_SOURCE_DIR}/src/json-validator.cpp" JSON_VALIDATOR_CPP)
string(FIND "${JSON_VALIDATOR_CPP}" "${JSON_VALIDATOR_THROW_LINE}" JSON_VALIDATOR_THROW_POS)
if(NOT JSON_VALIDATOR_THROW_POS EQUAL -1)
    string(REPLACE
        "${JSON_VALIDATOR_THROW_LINE}"
        "return; // Skip if already inserted (patched by MAS)"
        JSON_VALIDATOR_CPP "${JSON_VALIDATOR_CPP}")
    file(WRITE "${json-schema-validator_SOURCE_DIR}/src/json-validator.cpp" "${JSON_VALIDATOR_CPP}")
endif()

SET(CMAKE_CXX_FLAGS "-Wall -Wextra")

file(GLOB MAS_sources
    "tests/*.cpp")

add_executable(MAS_tests ${MAS_sources})
# Include dirs come from the imported targets (nlohmann_json::nlohmann_json,
# Catch2::Catch2WithMain) — never hardcode ${CMAKE_BINARY_DIR}/_deps paths,
# they break when FETCHCONTENT_SOURCE_DIR_* redirects a dependency.
target_link_libraries(MAS_tests PRIVATE nlohmann_json::nlohmann_json nlohmann_json_schema_validator Catch2::Catch2WithMain)
