// Minimal dependency-free unit tests for mas_to_cias (ideal coupled-inductor leaf).
#include "MasConverter.hpp"
#include "Fidelity.hpp"
#include <nlohmann/json.hpp>
#include <cmath>
#include <iostream>

using nlohmann::json;
using PEAS::Fidelity;

#include <catch2/catch_test_macros.hpp>
#define CHECK_MSG(cond, ...) do { INFO(__VA_ARGS__); CHECK(cond); } while (0)
#define CHECK_THROWS_MSG(expr, ...) do { INFO(__VA_ARGS__); CHECK_THROWS(expr); } while (0)

static double atom_lp(const json& leaf) {
    return leaf.at("components").at(0).at("data").at("inputs").at("designRequirements")
               .at("magnetizingInductance").at("nominal").get<double>();
}
static const json& atom_ratios(const json& leaf) {
    return leaf.at("components").at(0).at("data").at("inputs").at("designRequirements").at("turnsRatios");
}

TEST_CASE("MAS mas_to_cias", "[mas]") {
    // ideal flyback transformer: Lp = 1mH, one secondary, n = 4
    json doc = json::parse(R"({
        "magnetic": {},
        "inputs": { "designRequirements": {
            "magnetizingInductance": { "nominal": 1e-3 },
            "turnsRatios": [ { "nominal": 4.0 } ] } }
    })");
    json leaf = MAS::mas_to_cias(doc, Fidelity(Fidelity::Origin::REQUIREMENTS));

    // 2-winding transformer -> 4 winding terminals, ONE magnetic component (coupling stays inside it)
    CHECK_MSG(leaf.at("ports").size() == 4, "ideal: 4 winding terminals (1 pri + 1 sec)");
    CHECK_MSG(leaf.at("ports").at(0).at("name") == "primary_start", "ideal: port[0]=primary_start");
    CHECK_MSG(leaf.at("ports").at(2).at("name") == "secondary1_start", "ideal: port[2]=secondary1_start");
    CHECK_MSG(leaf.at("components").size() == 1, "ideal: ONE magnetic component (not L+L+K edges)");
    CHECK_MSG(leaf.at("components").at(0).at("name") == "T", "ideal: component T");
    CHECK_MSG(atom_lp(leaf) == 1e-3, "ideal: Lp from magnetizingInductance (1mH)");
    CHECK_MSG((atom_ratios(leaf).size() == 1 && atom_ratios(leaf).at(0).at("nominal") == 4.0),
          "ideal: turnsRatios carried (n=4)");
    CHECK_MSG(leaf.at("connections").size() == 4, "ideal: 4 winding nets");

    // two-secondary transformer -> 6 terminals
    json doc2 = json::parse(R"({
        "magnetic": {},
        "inputs": { "designRequirements": {
            "magnetizingInductance": { "minimum": 0.9e-3, "maximum": 1.1e-3 },
            "turnsRatios": [ { "nominal": 4.0 }, { "nominal": 2.0 } ] } }
    })");
    json leaf2 = MAS::mas_to_cias(doc2, Fidelity(Fidelity::Origin::REQUIREMENTS));
    CHECK_MSG(leaf2.at("ports").size() == 6, "two-secondary: 6 terminals");
    CHECK_MSG(atom_lp(leaf2) == 1e-3, "two-secondary: Lp resolves (min+max)/2 = 1mH");

    // DATASHEET without a bound part / MKF_MODEL without an exported subcircuit must throw
    bool d1 = false, d2 = false;
    try { MAS::mas_to_cias(doc, Fidelity(Fidelity::Origin::DATASHEET)); } catch (const std::exception&) { d1 = true; }
    try { MAS::mas_to_cias(doc, Fidelity(Fidelity::Origin::MKF_MODEL)); } catch (const std::exception&) { d2 = true; }
    CHECK_MSG(d1, "DATASHEET origin without manufacturerInfo throws");
    CHECK_MSG(d2, "MKF_MODEL origin without spiceSubcircuit throws");
}

static const json& atom_dr(const json& leaf) {
    return leaf.at("components").at(0).at("data").at("inputs").at("designRequirements");
}

TEST_CASE("MAS mas_to_cias leakage forwarding (ABT #171)", "[mas]") {
    // The CIAS emitter derives K from the ATOM's leakageInductance — mas_to_cias must forward it.
    json doc = json::parse(R"({
        "magnetic": {},
        "inputs": { "designRequirements": {
            "magnetizingInductance": { "nominal": 1e-3 },
            "turnsRatios": [ { "nominal": 4.0 } ],
            "leakageInductance": [ { "nominal": 2e-6 } ] } }
    })");
    json leaf = MAS::mas_to_cias(doc, Fidelity(Fidelity::Origin::REQUIREMENTS));
    const json& dr = atom_dr(leaf);
    CHECK_MSG(dr.contains("leakageInductance"), "ideal: leakageInductance forwarded to the atom");
    CHECK_MSG(dr.at("leakageInductance").at(0).at("nominal") == 2e-6,
              "ideal: forwarded leakage value intact");
    CHECK_MSG(!dr.contains("coupling"), "ideal: no schema-illegal 'coupling' field on the atom");

    // Absent leakage -> field omitted (emitter renders its near-ideal capped K).
    json doc2 = json::parse(R"({
        "magnetic": {},
        "inputs": { "designRequirements": {
            "magnetizingInductance": { "nominal": 1e-3 },
            "turnsRatios": [ { "nominal": 4.0 } ] } }
    })");
    json leaf2 = MAS::mas_to_cias(doc2, Fidelity(Fidelity::Origin::REQUIREMENTS));
    CHECK_MSG(!atom_dr(leaf2).contains("leakageInductance"), "ideal: no leakage stated -> none fabricated");
}

TEST_CASE("MAS mas_to_cias DATASHEET origin (ABT #170)", "[mas]") {
    const Fidelity real(Fidelity::Origin::DATASHEET);

    // Transformer part: datasheet magnetizing L + stated ratio + leakage override the seed's numbers.
    json xfmr = json::parse(R"({
        "magnetic": { "manufacturerInfo": { "name": "ACME", "datasheetInfo": {
            "part": { "partNumber": "X-1" },
            "electrical": [ { "subtype": "transformer",
                              "inductance": { "nominal": 2e-3 },
                              "turnsRatios": [ { "nominal": 5.0 } ],
                              "leakageInductance": { "nominal": 8e-6 } } ] } } },
        "inputs": { "designRequirements": {
            "magnetizingInductance": { "nominal": 1e-3 },
            "turnsRatios": [ { "nominal": 4.0 } ] } }
    })");
    json leaf = MAS::mas_to_cias(xfmr, real);
    CHECK_MSG(leaf.at("ports").size() == 4, "datasheet xfmr: ports still follow the circuit wiring");
    const json& dr = atom_dr(leaf);
    CHECK_MSG(dr.at("magnetizingInductance").at("nominal") == 2e-3,
              "datasheet xfmr: L from datasheetInfo (2mH), not the 1mH seed");
    CHECK_MSG(dr.at("turnsRatios").at(0).at("nominal") == 5.0,
              "datasheet xfmr: turns ratio from datasheetInfo (5), not the seed (4)");
    CHECK_MSG(dr.at("leakageInductance").at(0).at("nominal") == 8e-6,
              "datasheet xfmr: leakage forwarded for the emitter's K");

    // Coupled inductor: one per-winding L, no stated ratios -> equal windings (ratio 1);
    // couplingCoefficient k converts to leakage via Llk = Lp*(1-k^2).
    json cpl = json::parse(R"({
        "magnetic": { "manufacturerInfo": { "name": "ACME", "datasheetInfo": {
            "part": { "partNumber": "X-2" },
            "electrical": [ { "subtype": "coupledInductor",
                              "inductance": { "nominal": 47e-6 },
                              "couplingCoefficient": 0.995 } ] } } },
        "inputs": { "designRequirements": {
            "magnetizingInductance": { "nominal": 47e-6 },
            "turnsRatios": [ { "nominal": 1.0 } ] } }
    })");
    json cleaf = MAS::mas_to_cias(cpl, real);
    const json& cdr = atom_dr(cleaf);
    CHECK_MSG(cdr.at("magnetizingInductance").at("nominal") == 47e-6, "datasheet coupled: per-winding L");
    CHECK_MSG(cdr.at("turnsRatios").at(0).at("nominal") == 1.0,
              "datasheet coupled: equal windings -> derived ratio 1");
    const double llk = cdr.at("leakageInductance").at(0).at("nominal").get<double>();
    CHECK_MSG(std::fabs(llk - 47e-6 * (1.0 - 0.995 * 0.995)) < 1e-12,
              "datasheet coupled: k=0.995 -> Llk = Lp*(1-k^2)");

    // Single-winding inductor slot (no turnsRatios in the seed) realized by an `inductor` entry.
    json ind = json::parse(R"({
        "magnetic": { "manufacturerInfo": { "name": "ACME", "datasheetInfo": {
            "part": { "partNumber": "X-3" },
            "electrical": [ { "subtype": "inductor", "inductance": { "nominal": 100e-6 } } ] } } },
        "inputs": { "designRequirements": {
            "magnetizingInductance": { "nominal": 90e-6 } } }
    })");
    json ileaf = MAS::mas_to_cias(ind, real);
    CHECK_MSG(ileaf.at("ports").size() == 2, "datasheet inductor: 2 terminals");
    CHECK_MSG(atom_dr(ileaf).at("magnetizingInductance").at("nominal") == 100e-6,
              "datasheet inductor: L from datasheetInfo");

    // Wrong-shape data throws: no qualifying entry, ratio-count mismatch, missing inductance.
    json cmcOnly = xfmr;
    cmcOnly["magnetic"]["manufacturerInfo"]["datasheetInfo"]["electrical"] =
        json::array({ json::parse(R"({ "subtype": "commonModeChoke" })") });
    CHECK_THROWS_MSG(MAS::mas_to_cias(cmcOnly, real), "no transformer/coupledInductor entry throws");

    json mismatch = xfmr;
    mismatch["magnetic"]["manufacturerInfo"]["datasheetInfo"]["electrical"][0]["turnsRatios"] =
        json::array({ json{{"nominal", 5.0}}, json{{"nominal", 2.0}} });
    CHECK_THROWS_MSG(MAS::mas_to_cias(mismatch, real), "ratio-count/wiring mismatch throws");

    json noL = xfmr;
    noL["magnetic"]["manufacturerInfo"]["datasheetInfo"]["electrical"][0].erase("inductance");
    CHECK_THROWS_MSG(MAS::mas_to_cias(noL, real), "missing inductance throws");
}
