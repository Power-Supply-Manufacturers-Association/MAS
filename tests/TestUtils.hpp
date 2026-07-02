#pragma once
// Shared infrastructure for the MAS C++ reference-binding tests: the
// psma.com $id -> on-disk schema resolver and the jsoncons draft-2020-12
// schema compilation helpers.
//
// The validator is jsoncons' jsonschema extension, which implements JSON
// Schema draft 2020-12 natively: $ref with sibling keywords (the wire
// subtype discriminators in schemas/magnetic/wire/*.json) and
// unevaluatedProperties (the sealed allOf-extension objects) are enforced
// without any schema rewriting. The old draft-07 lowering shim
// (lower_draft202012_ref_siblings) is gone on purpose — do not reintroduce
// it.
//
// `format` stays permissive: in draft 2020-12 `format` is an annotation,
// not an assertion, unless the format-assertion vocabulary is explicitly
// enabled. jsoncons matches that default (assertion only with
// evaluation_options().require_format_validation(true), which we do NOT
// set). PEAS shared schemas use `format` (e.g. uri); MAS schemas that $ref
// PEAS must tolerate it.
#include <fstream>
#include <ostream>
#include <string>
#include <utility>
#include <jsoncons/json.hpp>
#include <jsoncons_ext/jsonschema/jsonschema.hpp>

namespace mas_test {

using jsoncons::json;
using json_schema = jsoncons::jsonschema::json_schema<json>;

// Absolute path of the MAS repository root (tests/ lives directly under it).
inline std::string mas_root()
{
    std::string file_path = __FILE__;
    return file_path.substr(0, file_path.rfind("/")).append("/../");
}

// Parse a JSON file from disk (schemas, samples, single records).
inline json load_json_file(const std::string& path)
{
    std::ifstream f(path);
    if (!f.good()) {
        throw std::invalid_argument("could not open file " + path);
    }
    return json::parse(f);
}

// $ref resolver handed to jsoncons::jsonschema::make_json_schema.
// Maps psma.com/<repo>/<path> $id URIs to on-disk schema files. MAS schemas
// live under <repo>/schemas/; sibling families (PEAS, CAS, SAS, RAS, CIAS)
// live in adjacent repos. The $id authority sweep to psma.com/<repo>/...
// requires this mapping. jsoncons hands us the URI already resolved against
// the referencing schema's $id base, so relative refs (./basicWire.json)
// arrive as full psma.com URIs. The OS resolves any embedded ".." segments
// when the file is opened.
inline json schema_resolver(const jsoncons::uri& uri)
{
    const std::string p = uri.path();
    const std::pair<std::string, std::string> repos[] = {
        {"/mas/",  "schemas/"},
        {"/peas/", "../PEAS/schemas/"},
        {"/cas/",  "../CAS/schemas/"},
        {"/sas/",  "../SAS/schemas/"},
        {"/ras/",  "../RAS/schemas/"},
        {"/cias/", "../CIAS/schemas/"},
        {"/tbas/", "../TBAS/schemas/"},
    };
    std::string filename = mas_root() + p;
    for (const auto& repo : repos) {
        if (p.rfind(repo.first, 0) == 0) {
            filename = mas_root() + repo.second + p.substr(repo.first.size());
            break;
        }
    }
    std::ifstream lf(filename);
    if (!lf.good()) {
        throw std::invalid_argument("could not open " + uri.string() + " tried with " + filename);
    }
    return json::parse(lf);
}

// Compile a schema file into a reusable draft-2020-12 validator. Build it
// ONCE per schema and validate every record against the compiled object —
// compilation walks the whole cross-repo $ref graph and is far more
// expensive than a single validation.
inline json_schema make_validator(const std::string& schema_path)
{
    return jsoncons::jsonschema::make_json_schema(load_json_file(schema_path), schema_resolver);
}

// Validate `instance`, streaming every validation message to `err` prefixed
// with `context` (file name, line number...). Returns true when valid.
inline bool validate_report(const json_schema& schema,
                            const json& instance,
                            std::ostream& err,
                            const std::string& context)
{
    bool valid = true;
    auto reporter = [&](const jsoncons::jsonschema::validation_message& message)
        -> jsoncons::jsonschema::walk_result {
        valid = false;
        err << context << ": " << message.instance_location().string() << ": "
            << message.message() << "\n";
        return jsoncons::jsonschema::walk_result::advance;
    };
    schema.validate(instance, reporter);
    return valid;
}

} // namespace mas_test
