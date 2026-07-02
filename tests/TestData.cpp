#include <catch2/catch_test_macros.hpp>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <string>
#include <vector>
#include "TestUtils.hpp"

using json = nlohmann::json;
using nlohmann::json_schema::json_validator;
using mas_test::format_check;
using mas_test::load_schema_file;
using mas_test::lower_draft202012_ref_siblings;
using mas_test::mas_root;
using mas_test::schema_loader;

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
        json shape_schema;
        try {
            shape_schema = load_schema_file(validator_path);
        }
        catch (const std::exception& e) {
            std::cerr << "Could not open and parse schema " << validator_path << ": " << e.what() << "\n";
            return false;
        }

        json_validator validator(schema_loader, format_check);
        try {
            validator.set_root_schema(shape_schema);
        }
        catch (const std::exception& e) {
            std::cerr << "Validation of schema " << validator_path << " failed, here is why: " << e.what() << "\n";
            return false;
        }

        for (const auto& file_path : files) {
            std::ifstream json_file(file_path);
            auto jf = json::parse(json_file);
            try {
                validator.validate(jf);
            }
            catch (const std::exception& e) {
                std::cerr << "Validation of " << file_path << " failed, here is why: " << e.what() << "\n";
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
        json shape_schema;
        try {
            shape_schema = load_schema_file(validator_path);
        }
        catch (const std::exception& e) {
            std::cerr << "Could not open and parse schema " << validator_path << ": " << e.what() << "\n";
            CHECK(false); // fails
            return;
        }

        json_validator validator(schema_loader, format_check); // create validator
        try {
            validator.set_root_schema(shape_schema); // insert root-schema
        }
        catch (const std::exception& e) {
            std::cerr << "Validation of schema failed, here is why: " << e.what() << "\n";
            CHECK(false); // fails
            return;
        }

        try {
            std::ifstream ndjson_file(database);
            std::string myline;

            while (std::getline(ndjson_file, myline)) {
                json jf = json::parse(myline);

                try {
                    validator.validate(jf); // validate the document - uses the default throwing error-handler
                }
                catch (const std::exception& e) {
                    std::cerr << "Validation failed, here is why: " << e.what() << "\n";
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
