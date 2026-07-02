# Reference implementation — build instructions

These instructions cover the C++ reference binding (`MAS.hpp`) and its
test harness, which are what live in this repository alongside the
schema. Conforming implementations of the MAS specification need not
follow this build; they need only consume MAS documents that validate
against `schemas/MAS.json`.

## Dependencies

Fetched automatically by CMake `FetchContent` (network needed on the first
configure only), each pinned to an exact release tag — never a branch:

- [Catch2](https://github.com/catchorg/Catch2) `v3.8.1` — test framework.
  The test binary is run directly (`./MAS_tests`); no ctest registration.
- [jsoncons](https://github.com/danielaparker/jsoncons) `v1.8.1` —
  header-only JSON library whose `jsonschema` extension implements JSON
  Schema **draft 2020-12 natively**, including `$ref` with sibling keywords
  (the wire-subtype discriminators) and `unevaluatedProperties` (the sealed
  allOf-extension objects). It replaced pboettch/json-schema-validator
  (draft-07 only) and the draft-07 lowering shim the tests used to carry,
  so the C++ binding now enforces the same semantics as Python's
  `Draft202012Validator` (`scripts/validate-*.py`).

The tests need the sibling schema repos (`PEAS`, `CAS`, `SAS`, `RAS`,
`CIAS`) checked out alongside MAS: cross-repo `$ref`s use
`https://psma.com/<repo>/...` `$id` URIs which `tests/TestUtils.hpp`
resolves to `../<REPO>/schemas/` on disk.

## Build steps

1. Create a build directory:

    ```
    $ mkdir build && cd build
    ```

2. Configure the CMake project (Using Ninja in this example):

    ```
    $ cmake .. -G "Ninja"
    ```

4. Build it:

    ```
    $ cmake --build .
    ```

5. Run the application:

    ```
    $ ./MAS_tests
    ```
6. Create Python package

    ```
    python3 -m pip install -e ../ -vvv
    ```


wget -O - https://apt.kitware.com/keys/kitware-archive-latest.asc 2>/dev/null | sudo apt-key add -
sudo apt-add-repository 'deb https://apt.kitware.com/ubuntu/ bionic main'
sudo apt install cmake
sudo apt install ninja-build
npm install -g quicktype
sudo add-apt-repository -y ppa:ubuntu-toolchain-r/test
sudo apt install -y gcc-11 g++-11
sudo update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-11 10
sudo update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-11 10

sudo apt-get install libglfw3-dev libgles2-mesa-dev
export GIT_LFS_SKIP_SMUDGE=1


quicktype -l c++ -s schema ./schemas/MAS.json -S ./schemas/magnetic.json -S ./schemas/magnetic/core.json -S ./schemas/magnetic/coil.json -S ./schemas/utils.json -S ../PEAS/schemas/utils.json -S ../PEAS/schemas/inputs/operatingConditions.json -S ../PEAS/schemas/inputs/operatingPointExcitation.json -S ./schemas/magnetic/core/gap.json -S ./schemas/magnetic/core/shape.json -S ./schemas/magnetic/core/material.json -S ./schemas/magnetic/insulation/material.json -S ./schemas/magnetic/insulation/wireCoating.json -S ./schemas/magnetic/bobbin.json -S ./schemas/magnetic/core/piece.json -S ./schemas/magnetic/core/spacer.json -S ./schemas/magnetic/wire/basicWire.json -S ./schemas/magnetic/wire/round.json -S ./schemas/magnetic/wire/rectangular.json -S ./schemas/magnetic/wire/foil.json -S ./schemas/magnetic/wire/planar.json -S ./schemas/magnetic/wire/litz.json -S ./schemas/magnetic/wire/material.json -S ./schemas/magnetic/wire.json -S ./schemas/utils.json -S ../PEAS/schemas/utils.json -S ../PEAS/schemas/inputs/operatingConditions.json -S ../PEAS/schemas/inputs/operatingPointExcitation.json -S ./schemas/magnetic/insulation/wireCoating.json -S ./schemas/magnetic/insulation/material.json -S ./schemas/inputs.json -S ./schemas/outputs.json -S ./schemas/outputs/coreLossesOutput.json -S ./schemas/inputs/designRequirements.json -S ./schemas/inputs/operatingPoint.json -S ./schemas/inputs/operatingConditions.json -S ./schemas/inputs/operatingPointExcitation.json -S ./schemas/inputs/topologies/flyback.json -S ./schemas/inputs/topologies/currentTransformer.json -S ./schemas/inputs/topologies/buck.json -S ./schemas/inputs/topologies/isolatedBuck.json -S ./schemas/inputs/topologies/isolatedBuckBoost.json -S ./schemas/inputs/topologies/boost.json -S ./schemas/inputs/topologies/pushPull.json -S ./schemas/inputs/topologies/forward.json -o build/MAS.hpp --namespace MAS --source-style single-source --type-style pascal-case --member-style underscore-case --enumerator-style upper-underscore-case --no-boost

generate-schema-doc --config expand_buttons=true schemas/MAS.json mas_documentation.html