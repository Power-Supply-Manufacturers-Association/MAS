#pragma once
// Shared infrastructure for the MAS C++ reference-binding tests: the
// psma.com $id -> on-disk schema loader, the permissive format checker, and
// the draft-07 lowering transform every loaded schema must go through.
#include <filesystem>
#include <fstream>
#include <string>
#include <utility>
#include <nlohmann/json-schema.hpp>
#include <nlohmann/json.hpp>

namespace mas_test {

using nlohmann::json;
using nlohmann::json_uri;

// Permissive format checker. In JSON Schema draft 2020-12 `format` is an
// annotation, not an assertion, unless the format-assertion vocabulary is
// explicitly enabled. pboettch's validator otherwise throws when a `format`
// keyword is present and no checker is supplied. PEAS shared schemas use
// `format` (e.g. uri); MAS schemas that now $ref PEAS must tolerate it.
inline void format_check(const std::string&, const std::string&) {}

// Absolute path of the MAS repository root (tests/ lives directly under it).
inline std::string mas_root()
{
    std::string file_path = __FILE__;
    return file_path.substr(0, file_path.rfind("/")).append("/../");
}

// lower_draft202012_ref_siblings — REQUIRED before handing any PSMA schema to
// pboettch/json-schema-validator.
//
// pboettch implements JSON Schema draft-07, where a schema object containing
// "$ref" is REPLACED by the referenced schema: every sibling keyword next to
// "$ref" is silently IGNORED. The PSMA schemas are draft 2020-12, where $ref
// is just another applicator and siblings DO apply. The wire subtype schemas
// (schemas/magnetic/wire/{round,foil,rectangular,litz,planar}.json) rely on
// 2020-12 semantics: their root is `$ref: ./basicWire.json` plus sibling
// properties/required/unevaluatedProperties plus an
// if/{type:const}/then:true/else:false discriminator. Under raw draft-07
// evaluation each subtype collapses to plain basicWire.json, so every wire
// matches all five branches of wire.json's oneOf and validation fails with
// "more than one subschema has succeeded".
//
// The lowering rewrites, recursively through the whole document,
//     { "$ref": R, <sibling keywords> }
// into
//     { "allOf": [ { "$ref": R }, { <sibling keywords> } ] }
// which draft-07 honours (allOf members are all applied, and if/then/else are
// draft-07 keywords) and which is semantically identical under 2020-12.
// Annotation/identifier keywords ($id, $schema, $comment, title, description,
// examples, default, deprecated) and the $defs/definitions containers stay in
// place, so base-URI resolution of relative $refs and "#/$defs/..." JSON
// pointers into the document keep working.
//
// Known, accepted gap: draft-07 has no `unevaluatedProperties`, so pboettch
// ignores that keyword (weaker than Python's Draft202012Validator, which
// remains the authoritative check via scripts/validate-*.py).
inline void lower_draft202012_ref_siblings(json& node)
{
    if (node.is_array()) {
        for (auto& item : node) {
            lower_draft202012_ref_siblings(item);
        }
        return;
    }
    if (!node.is_object()) {
        return;
    }
    for (auto& element : node.items()) {
        lower_draft202012_ref_siblings(element.value());
    }
    if (!node.contains("$ref")) {
        return;
    }
    // Keywords that stay next to $ref: identifiers/annotations (no assertion
    // semantics) and the definition containers that JSON pointers target.
    static const char* keep[] = {"$ref",        "$id",     "$schema",  "$comment",
                                 "$defs",       "definitions", "title", "description",
                                 "examples",    "default", "deprecated"};
    json siblings = json::object();
    for (auto it = node.begin(); it != node.end();) {
        bool kept = false;
        for (const char* k : keep) {
            if (it.key() == k) {
                kept = true;
                break;
            }
        }
        if (kept) {
            ++it;
            continue;
        }
        siblings[it.key()] = std::move(it.value());
        it = node.erase(it);
    }
    if (siblings.empty()) {
        return;
    }
    json branches = json::array();
    branches.push_back(json{{"$ref", node.at("$ref")}});
    branches.push_back(std::move(siblings));
    node.erase("$ref");
    node["allOf"] = std::move(branches);
}

// Parse a schema file from disk and lower it for the draft-07 validator.
inline json load_schema_file(const std::string& path)
{
    std::ifstream f(path);
    if (!f.good()) {
        throw std::invalid_argument("could not open schema file " + path);
    }
    json schema = json::parse(f);
    lower_draft202012_ref_siblings(schema);
    return schema;
}

// $ref loader for pboettch's json_validator.
inline void schema_loader(const json_uri& uri, json& schema)
{
    // Map psma.com/<repo>/<path> $id URIs to on-disk schema files. MAS
    // schemas live under <repo>/schemas/; sibling families (PEAS, CAS, SAS,
    // RAS, CIAS) live in adjacent repos. The $id authority sweep to
    // psma.com/<repo>/... requires this mapping; the loader previously
    // assumed legacy /schemas/... paths. The OS resolves any embedded ".."
    // segments when the file is opened.
    const std::string p = uri.path();
    const std::pair<std::string, std::string> repos[] = {
        {"/mas/",  "schemas/"},
        {"/peas/", "../PEAS/schemas/"},
        {"/cas/",  "../CAS/schemas/"},
        {"/sas/",  "../SAS/schemas/"},
        {"/ras/",  "../RAS/schemas/"},
        {"/cias/", "../CIAS/schemas/"},
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
        throw std::invalid_argument("could not open " + uri.url() + " tried with " + filename);
    }
    lf >> schema;
    lower_draft202012_ref_siblings(schema);
}

} // namespace mas_test
