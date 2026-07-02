#include <catch2/catch_test_macros.hpp>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <string>
#include <vector>
#include "TestUtils.hpp"

using mas_test::json;
using mas_test::load_json_file;
using mas_test::make_validator;
using mas_test::mas_root;
using mas_test::validate_report;

namespace {

std::string ReplaceAll(std::string str, const std::string& from, const std::string& to)
{
    size_t start_pos = 0;
    while ((start_pos = str.find(from, start_pos)) != std::string::npos) {
        str.replace(start_pos, from.length(), to);
        start_pos += to.length(); // Handles case where 'to' is a substring of 'from'
    }
    return str;
}

bool validate_single_schema(const std::string& validator_path, const std::vector<std::filesystem::path>& files)
{
    try {
        mas_test::json_schema validator = [&] {
            try {
                return make_validator(validator_path);
            }
            catch (const std::exception& e) {
                std::cerr << "Could not compile schema " << validator_path << ": " << e.what() << "\n";
                throw;
            }
        }();

        for (const auto& file_path : files) {
            json jf = load_json_file(file_path.string());
            if (!validate_report(validator, jf, std::cerr, file_path.string())) {
                std::cerr << "Validation of " << file_path << " failed\n";
                return false;
            }
        }
        return true;
    }
    catch (std::exception& e) {
        std::cerr << "Could not open and parse " << validator_path << ": " << e.what() << "\n";
        return false;
    }
}

std::map<std::string, std::vector<std::filesystem::path>> group_samples_by_schema(const std::string& samples)
{
    // Sample fixtures whose schema no longer lives in MAS: the schema
    // consolidation retired the MAS mirror of operatingPointExcitation; the
    // canonical schema lives in PEAS (mirrors scripts/validate-fixtures.py).
    // Keys are the naive samples->schemas path, values are relative to the
    // MAS repo root.
    static const std::pair<std::string, std::string> moved_schemas[] = {
        {"schemas/inputs/operatingPointExcitation.json", "../PEAS/schemas/inputs/operatingPointExcitation.json"},
    };

    std::map<std::string, std::vector<std::filesystem::path>> files_by_schema;

    for (auto const& dir_entry : std::filesystem::recursive_directory_iterator(samples)) {
        auto path = dir_entry.path();
        if (path.string().ends_with(".json")) {
            auto validator_path = path.parent_path().string() + ".json";
            validator_path = ReplaceAll(validator_path, "samples", "schemas");
            for (const auto& moved : moved_schemas) {
                if (validator_path.ends_with(moved.first)) {
                    validator_path = mas_root() + moved.second;
                    break;
                }
            }
            files_by_schema[validator_path].push_back(path);
        }
    }
    return files_by_schema;
}

void validate_ndjson(const std::string& validator_path, const std::string& database)
{
    try {
        mas_test::json_schema validator = [&] {
            try {
                return make_validator(validator_path);
            }
            catch (const std::exception& e) {
                std::cerr << "Could not compile schema " << validator_path << ": " << e.what() << "\n";
                throw;
            }
        }();

        try {
            std::ifstream ndjson_file(database);
            std::string myline;
            size_t line_number = 0;

            while (std::getline(ndjson_file, myline)) {
                line_number++;
                json jf = json::parse(myline);

                const std::string context = database + ":" + std::to_string(line_number);
                if (!validate_report(validator, jf, std::cerr, context)) {
                    std::cerr << "Validation failed for " << context << "\n";
                    CHECK(false); // fails
                    break;
                }
            }
        }
        catch (std::exception& e) {
            std::cerr << "Could not open and parse " << database << ": " << e.what() << "\n";
            CHECK(false); // fails
            return;
        }
    }
    catch (std::exception& e) {
        std::cerr << "Could not open and parse " << validator_path << ": " << e.what() << "\n";
        CHECK(false); // fails
        return;
    }
}

void check_valid_ndjson(const std::string& database)
{
    try {
        std::ifstream ndjson_file(database);
        std::string myline;

        while (std::getline(ndjson_file, myline)) {
            json jf = json::parse(myline);
        }
    }
    catch (std::exception& e) {
        std::cerr << "Could not open and parse " << database << ": " << e.what() << "\n";
        CHECK(false); // fails
        return;
    }
}

void validate_sample_group(const std::string& samples_dir)
{
    auto groups = group_samples_by_schema(samples_dir);
    CHECK(!groups.empty());
    for (const auto& [schema, files] : groups) {
        INFO("schema: " << schema);
        CHECK(validate_single_schema(schema, files));
    }
}

} // namespace

TEST_CASE("Samples_Magnetic_Bobbin", "[samples]")
{
    validate_sample_group(mas_root() + "samples/magnetic/bobbin/");
}

TEST_CASE("Samples_Magnetic_Coil", "[samples]")
{
    validate_sample_group(mas_root() + "samples/magnetic/coil/");
}

TEST_CASE("Samples_Magnetic_Core", "[samples]")
{
    validate_sample_group(mas_root() + "samples/magnetic/core/");
}

TEST_CASE("Samples_Magnetic_Wire", "[samples]")
{
    validate_sample_group(mas_root() + "samples/magnetic/wire/");
}

TEST_CASE("Samples_Magnetic_Insulation", "[samples]")
{
    validate_sample_group(mas_root() + "samples/magnetic/insulation/");
}

TEST_CASE("Samples_Inputs", "[samples]")
{
    validate_sample_group(mas_root() + "samples/inputs/");
}

TEST_CASE("CoreShapes", "[data]")
{
    auto data_file_path = mas_root() + "data/core_shapes.ndjson";
    auto schema_file_path = mas_root() + "schemas/magnetic/core/shape.json";
    validate_ndjson(schema_file_path, data_file_path);
}

TEST_CASE("Bobbins", "[data]")
{
    auto data_file_path = mas_root() + "data/bobbins.ndjson";
    auto schema_file_path = mas_root() + "schemas/magnetic/bobbin.json";
    validate_ndjson(schema_file_path, data_file_path);
}

TEST_CASE("CoreMaterials", "[data]")
{
    auto data_file_path = mas_root() + "data/core_materials.ndjson";
    auto schema_file_path = mas_root() + "schemas/magnetic/core/material.json";
    validate_ndjson(schema_file_path, data_file_path);
}

TEST_CASE("Advanced_Materials", "[data]")
{
    auto data_file_path = mas_root() + "data/advanced_core_materials.ndjson";
    check_valid_ndjson(data_file_path);
}

TEST_CASE("Wires", "[data]")
{
    auto data_file_path = mas_root() + "data/wires.ndjson";
    auto schema_file_path = mas_root() + "schemas/magnetic/wire.json";
    validate_ndjson(schema_file_path, data_file_path);
}

TEST_CASE("Insulation", "[data]")
{
    auto data_file_path = mas_root() + "data/insulation_materials.ndjson";
    auto schema_file_path = mas_root() + "schemas/magnetic/insulation/material.json";
    validate_ndjson(schema_file_path, data_file_path);
}

TEST_CASE("WireMaterials", "[data]")
{
    auto data_file_path = mas_root() + "data/wire_materials.ndjson";
    auto schema_file_path = mas_root() + "schemas/magnetic/wire/material.json";
    validate_ndjson(schema_file_path, data_file_path);
}

TEST_CASE("CoreStock", "[data]")
{
    auto data_file_path = mas_root() + "data/cores_stock.ndjson";
    auto schema_file_path = mas_root() + "schemas/magnetic/core.json";
    validate_ndjson(schema_file_path, data_file_path);
}

TEST_CASE("Cores", "[data]")
{
    auto data_file_path = mas_root() + "data/cores.ndjson";
    auto schema_file_path = mas_root() + "schemas/magnetic/core.json";
    validate_ndjson(schema_file_path, data_file_path);
}

namespace {

// A schema-valid solid round wire, shaped like the records in
// data/wires.ndjson.
json valid_round_wire()
{
    return json::parse(R"({
        "name": "Round 0.01 - Grade 1",
        "standardName": "0.01 mm",
        "type": "round",
        "material": "copper",
        "manufacturerInfo": {"name": "Elektrisola"},
        "numberConductors": 1,
        "standard": "IEC 60317",
        "conductingDiameter": {"nominal": 0.00001},
        "outerDiameter": {"minimum": 0.000012, "maximum": 0.0000165}
    })");
}

} // namespace

// Draft 2020-12 regression: `unevaluatedProperties: false` in the wire
// subtype schemas seals the object across the `$ref: ./basicWire.json`
// boundary. The retired draft-07 validator (pboettch) silently ignored the
// keyword, so a typo'd extra key was accepted; the 2020-12 validator must
// reject it — matching Python's Draft202012Validator.
TEST_CASE("Wire_UnevaluatedProperties_RejectsTypoKey", "[schema-2020-12]")
{
    auto wire_validator = make_validator(mas_root() + "schemas/magnetic/wire.json");

    json good = valid_round_wire();
    CHECK(validate_report(wire_validator, good, std::cerr, "valid round wire"));

    json typo = valid_round_wire();
    typo["tolerence"] = 0.1; // typo'd extra key inside the sealed object
    CHECK(!wire_validator.is_valid(typo));

    // The extra key must also be rejected against the subtype schema
    // directly, not just via the union.
    auto round_validator = make_validator(mas_root() + "schemas/magnetic/wire/round.json");
    CHECK(!round_validator.is_valid(typo));
}

// Draft 2020-12 regression: the wire-union discriminators are `$ref` with
// sibling keywords (properties/required/unevaluatedProperties plus the
// if/{type:const}/then:true/else:false conditional). Under draft-07 the
// siblings were ignored and every wire matched all five oneOf branches;
// natively evaluated, a record must match EXACTLY the branch its `type`
// names — with no schema-lowering shim involved.
TEST_CASE("Wire_Union_Discriminator_ExactlyOneBranch", "[schema-2020-12]")
{
    const json round = valid_round_wire();

    // The union accepts the round record (oneOf: exactly one branch).
    auto wire_validator = make_validator(mas_root() + "schemas/magnetic/wire.json");
    CHECK(validate_report(wire_validator, round, std::cerr, "round wire vs wire.json"));

    // Branch by branch: only round.json matches.
    const std::string subtypes[] = {"round", "foil", "rectangular", "litz", "planar"};
    int matches = 0;
    for (const auto& subtype : subtypes) {
        auto branch_validator = make_validator(mas_root() + "schemas/magnetic/wire/" + subtype + ".json");
        const bool valid = branch_validator.is_valid(round);
        INFO("subtype branch: " << subtype);
        CHECK(valid == (subtype == "round"));
        if (valid) {
            matches++;
        }
    }
    CHECK(matches == 1);

    // A type:planar record carrying round-only fields matches no branch.
    json planar_with_round_fields = json::parse(R"({
        "type": "planar",
        "conductingDiameter": {"nominal": 0.00001}
    })");
    CHECK(!wire_validator.is_valid(planar_with_round_fields));
}
