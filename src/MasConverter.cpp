#include "MasConverter.hpp"
#include "MAS.hpp"           // quicktype-generated typed structs (build/MAS.hpp)
#include "Dimension.hpp"     // PEAS::resolve_dimensional_values (typed + scalar)
#include "DimensionJson.hpp" // PEAS::resolve_dimensional_values (nlohmann::json overload)

#include <stdexcept>
#include <vector>
#include <string>
#include <algorithm>

namespace MAS {

using nlohmann::json;

namespace {

// One magnetic component carrying the coupled-inductor model (magnetizingInductance + turnsRatios +
// per-secondary leakageInductance). The CIAS emitter expands it into L (per winding) + K, deriving
// each k_i = sqrt(1 - Llk_i/Lp) from the leakage array — leakage is the CARRIED quantity, K the
// emitter's derivation (it also validates Llk < Lp and caps the emitted K just below unity so the
// coupled-L matrix never goes singular in ngspice). An absent/empty leakage array means near-ideal
// coupling (the emitter's capped k=1). `leakage` is a json array of dimensionWithTolerance entries,
// or null to omit the field.
json make_magnetic_atom(double lp, const std::vector<double>& turnsRatios, const json& leakage) {
    json ratios = json::array();
    for (double n : turnsRatios) ratios.push_back(json{{"nominal", n}});

    json atom;
    atom["magnetic"] = json::object();
    atom["inputs"]["designRequirements"]["magnetizingInductance"]["nominal"] = lp;
    atom["inputs"]["designRequirements"]["turnsRatios"] = ratios;
    if (leakage.is_array() && !leakage.empty())
        atom["inputs"]["designRequirements"]["leakageInductance"] = leakage;
    return atom;
}

// The datasheetInfo.electrical configuration entry that realizes this leaf's winding shape.
// `electrical` has one entry per connection configuration (subtype-discriminated oneOf); a converter
// transformer/coupled-inductor slot (nsec > 0 secondaries) is realized by a `transformer` or
// `coupledInductor` entry, a single-winding slot by an `inductor` entry. commonModeChoke / chipBead
// wirings are different circuit roles and never candidates here. When several entries qualify,
// narrow by a matching stated turnsRatios count; still-ambiguous data throws (the bind step must
// record which configuration was selected — no silent pick).
const json& select_datasheet_electrical(const json& electrical, size_t nsec,
                                        const std::string& name) {
    std::vector<const json*> hits;
    for (const auto& e : electrical) {
        if (!e.is_object() || !e.contains("subtype") || !e.at("subtype").is_string())
            throw std::runtime_error("MAS DATASHEET: malformed datasheetInfo.electrical entry of '" +
                                     name + "' (missing subtype discriminator)");
        const std::string st = e.at("subtype").get<std::string>();
        const bool multi = (st == "transformer" || st == "coupledInductor");
        if (nsec > 0 ? multi : st == "inductor") hits.push_back(&e);
    }
    if (hits.empty())
        throw std::runtime_error(
            "MAS DATASHEET: no " + std::string(nsec > 0 ? "transformer/coupledInductor" : "inductor") +
            " entry in datasheetInfo.electrical of '" + name + "' (" +
            std::to_string(electrical.size()) + " configuration(s) present)");
    if (hits.size() > 1) {
        // Several qualifying wirings: keep only those whose stated turnsRatios count matches the
        // circuit's winding count (selection on data, not a default).
        std::vector<const json*> narrowed;
        for (const json* e : hits)
            if (e->contains("turnsRatios") && e->at("turnsRatios").is_array()
                && e->at("turnsRatios").size() == nsec)
                narrowed.push_back(e);
        if (narrowed.size() == 1) return *narrowed[0];
        std::string names;
        for (const json* e : hits) {
            if (!names.empty()) names += ", ";
            names += e->contains("name") && e->at("name").is_string()
                         ? e->at("name").get<std::string>() : std::string("<unnamed>");
        }
        throw std::runtime_error("MAS DATASHEET: ambiguous datasheetInfo.electrical of '" + name +
                                 "' — " + std::to_string(hits.size()) +
                                 " qualifying configurations (" + names +
                                 "); the part data must disambiguate the wiring");
    }
    return *hits[0];
}

// DATASHEET origin: the coupled-inductor atom built from the bound part's
// magnetic.manufacturerInfo.datasheetInfo.electrical entry — per-winding/magnetizing inductance,
// stated turns ratios, and the leakage (or coupling coefficient, converted via Llk = Lp*(1-k^2))
// the CIAS emitter derives K from. `nsec` (the circuit's winding count, from the seed's
// designRequirements.turnsRatios) is the wiring truth the datasheet entry must realize.
json datasheet_atom(const json& peas, size_t nsec, const std::string& name) {
    const json& mag = peas.at("magnetic");
    if (!mag.contains("manufacturerInfo") || !mag.at("manufacturerInfo").is_object())
        throw std::runtime_error("MAS DATASHEET: magnetic.manufacturerInfo missing on '" + name +
                                 "' (a DATASHEET magnetic must be a bound catalog part; a designed "
                                 "core+coil magnetic needs the MKF_MODEL subcircuit export instead)");
    const json& mi = mag.at("manufacturerInfo");
    if (!mi.contains("datasheetInfo") || !mi.at("datasheetInfo").is_object()) {
        // The classic trigger: a DESIGNED magnetic (an OpenMagnetics/MKF adviser result carrying
        // core/coil + manufacturerInfo but no catalog datasheet) bound into the slot. Its real model
        // is the MKF-exported SPICE subcircuit, not a datasheet — point the user at the two ways out.
        const bool designed = mag.contains("core") || mag.contains("coil");
        throw std::runtime_error(
            "MAS DATASHEET: manufacturerInfo.datasheetInfo missing on '" + name + "'" +
            (designed ? " — this is a designed (OpenMagnetics/MKF) magnetic, not a catalog part. "
                        "Re-export it with its SPICE subcircuit (magnetic.modelOutputs."
                        "spiceSubcircuit, MKF export_magnetic_as_subcircuit) to simulate the real "
                        "model, or select the ideal model for this component."
                      : ""));
    }
    const json& di = mi.at("datasheetInfo");
    if (!di.contains("electrical") || !di.at("electrical").is_array() || di.at("electrical").empty())
        throw std::runtime_error("MAS DATASHEET: datasheetInfo.electrical missing/empty on '" + name + "'");

    const json& e = select_datasheet_electrical(di.at("electrical"), nsec, name);
    const std::string subtype = e.at("subtype").get<std::string>();

    // Per-winding (coupledInductor) / magnetizing (transformer) / plain (inductor) inductance —
    // the one datasheet value every variant states in `inductance`.
    if (!e.contains("inductance") || e.at("inductance").is_null())
        throw std::runtime_error("MAS DATASHEET: " + subtype + " entry of '" + name +
                                 "' has no inductance");
    const double lp = PEAS::resolve_dimensional_values(e.at("inductance"));

    // Turns ratios: the datasheet-stated values, count-checked against the circuit wiring. A
    // coupledInductor stating ONE per-winding inductance and no ratios has equal windings by
    // definition — ratio 1 per secondary is derived, not defaulted. A transformer without stated
    // ratios carries no such implication and throws.
    std::vector<double> ratios;
    if (e.contains("turnsRatios") && e.at("turnsRatios").is_array() && !e.at("turnsRatios").empty()) {
        for (const auto& tr : e.at("turnsRatios"))
            ratios.push_back(PEAS::resolve_dimensional_values(tr));
        if (ratios.size() != nsec)
            throw std::runtime_error("MAS DATASHEET: '" + name + "' datasheet states " +
                                     std::to_string(ratios.size()) + " turns ratio(s) but the circuit "
                                     "is wired for " + std::to_string(nsec) + " secondary winding(s)");
    } else if (nsec == 0) {
        // single-winding inductor: no ratios to state
    } else if (subtype == "coupledInductor") {
        ratios.assign(nsec, 1.0);
    } else {
        throw std::runtime_error("MAS DATASHEET: transformer entry of '" + name +
                                 "' states no turnsRatios for a " + std::to_string(nsec) +
                                 "-secondary winding");
    }

    // Leakage: forwarded per secondary for the emitter's K derivation. A stated couplingCoefficient
    // converts through the same relation the emitter inverts (Llk = Lp*(1-k^2)). Absent both, the
    // field is omitted and the emitter renders its near-ideal capped coupling.
    json leakage;
    if (nsec > 0) {
        if (e.contains("leakageInductance") && !e.at("leakageInductance").is_null()) {
            const double llk = PEAS::resolve_dimensional_values(e.at("leakageInductance"));
            leakage = json::array();
            for (size_t i = 0; i < nsec; ++i) leakage.push_back(json{{"nominal", llk}});
        } else if (e.contains("couplingCoefficient") && e.at("couplingCoefficient").is_number()) {
            const double k = e.at("couplingCoefficient").get<double>();
            if (!(k > 0.0 && k <= 1.0))
                throw std::runtime_error("MAS DATASHEET: couplingCoefficient " + std::to_string(k) +
                                         " of '" + name + "' outside (0, 1]");
            leakage = json::array();
            for (size_t i = 0; i < nsec; ++i) leakage.push_back(json{{"nominal", lp * (1.0 - k * k)}});
        }
    }

    return make_magnetic_atom(lp, ratios, leakage);
}

json winding_net(const std::string& port, const std::string& comp, const std::string& pin) {
    json endpoints = json::array();
    endpoints.push_back(json{{"component", comp}, {"pin", pin}});
    endpoints.push_back(json{{"port", port}});
    return json{{"name", port}, {"endpoints", endpoints}};
}

} // namespace

json mas_to_cias(const json& peas, const PEAS::Fidelity& fidelity, const std::string& name) {
    using Origin = PEAS::Fidelity::Origin;

    if (!peas.contains("inputs") || !peas.at("inputs").contains("designRequirements"))
        throw std::runtime_error("MAS: inputs.designRequirements missing");

    // Winding terminals are the same regardless of fidelity: primary plus one winding per turns
    // ratio. (The turns ratios also tell the CIAS emitter how many subckt ports to wire.)
    std::vector<double> turnsRatios;
    {
        const json& drj = peas.at("inputs").at("designRequirements");
        if (drj.contains("turnsRatios"))
            for (const auto& tr : drj.at("turnsRatios")) {
                // Resolve a dimensionWithTolerance entry (number or {nominal/minimum/maximum}).
                // Duty-ceiling turns ratios are emitted as {maximum}-only (no nominal), so the raw
                // .at("nominal")/.get<double>() path crashed on push-pull and any ceiling-marked ratio.
                if (tr.is_number()) { turnsRatios.push_back(tr.get<double>()); continue; }
                if (!tr.is_object()) continue;
                auto num = [&](const char* k) -> const json* {
                    return (tr.contains(k) && tr.at(k).is_number()) ? &tr.at(k) : nullptr; };
                if (const json* n = num("nominal")) turnsRatios.push_back(n->get<double>());
                else if (num("minimum") && num("maximum"))
                    turnsRatios.push_back((num("minimum")->get<double>() + num("maximum")->get<double>()) / 2.0);
                else if (const json* hi = num("maximum")) turnsRatios.push_back(hi->get<double>());
                else if (const json* lo = num("minimum")) turnsRatios.push_back(lo->get<double>());
            }
    }

    // Ports + connections: primary (w0) plus one winding per turns ratio.
    json ports = json::array();
    json connections = json::array();
    const char* comp = "T";

    ports.push_back(json{{"name", "primary_start"}});
    ports.push_back(json{{"name", "primary_end"}});
    connections.push_back(winding_net("primary_start", comp, "primary_start"));
    connections.push_back(winding_net("primary_end",   comp, "primary_end"));

    for (size_t i = 0; i < turnsRatios.size(); ++i) {
        const std::string idx = std::to_string(i + 1);
        const std::string s = "secondary" + idx + "_start";
        const std::string e = "secondary" + idx + "_end";
        ports.push_back(json{{"name", s}});
        ports.push_back(json{{"name", e}});
        connections.push_back(winding_net(s, comp, s));
        connections.push_back(winding_net(e, comp, e));
    }

    // The single atom carries the magnetic model the CIAS emitter renders:
    //  - MKF_MODEL: the MKF-exported ngspice subcircuit (real Rdc + AC ladder + magnetizing L +
    //    leakage coupling, from CircuitSimulatorExporter), carried in magnetic.modelOutputs.
    //    spiceSubcircuit by the bind step. The emitter inlines the .subckt and instantiates
    //    X<...> with the winding terminals mapped to its P<i>+/- ports.
    //  - DATASHEET: a coupled-inductor (L + K) model from the bound catalog part's
    //    manufacturerInfo.datasheetInfo.electrical configuration entry.
    //  - REQUIREMENTS (ideal): a coupled-inductor (L + K) model from designRequirements.
    json atomData;
    if (fidelity.origin == Origin::MKF_MODEL) {
        if (!peas.contains("magnetic") || !peas.at("magnetic").is_object()
            || !peas.at("magnetic").contains("modelOutputs")
            || !peas.at("magnetic").at("modelOutputs").contains("spiceSubcircuit"))
            throw std::runtime_error("MAS MKF_MODEL: magnetic.modelOutputs.spiceSubcircuit missing "
                                     "(bind step must run MKF export_magnetic_as_subcircuit)");
        json ratios = json::array();
        for (double n : turnsRatios) ratios.push_back(json{{"nominal", n}});
        atomData["magnetic"]["modelOutputs"]["spiceSubcircuit"] =
            peas.at("magnetic").at("modelOutputs").at("spiceSubcircuit");
        atomData["inputs"]["designRequirements"]["turnsRatios"] = ratios;
    } else if (fidelity.origin == Origin::DATASHEET) {
        if (!peas.contains("magnetic") || !peas.at("magnetic").is_object())
            throw std::runtime_error("MAS DATASHEET: 'magnetic' component missing from PEAS document");
        atomData = datasheet_atom(peas, turnsRatios.size(), name);
    } else {
        auto dr = peas.at("inputs").at("designRequirements").get<DesignRequirements>();
        const double lp = PEAS::resolve_dimensional_values(dr.get_magnetizing_inductance());
        // Leakage is FORWARDED verbatim (dimensionWithTolerance entries, one per secondary) — the
        // CIAS emitter derives each winding's K from it. Previously a scalar 'coupling' was written
        // here instead: not a MAS designRequirements field, and read by nothing (the specified
        // leakage silently became the emitter's near-ideal cap — e.g. the DAB useLeakageInductance
        // tank collapsed to K=0.999999). ABT #171.
        json leakage;
        const json& drj = peas.at("inputs").at("designRequirements");
        if (drj.contains("leakageInductance") && drj.at("leakageInductance").is_array()
            && !drj.at("leakageInductance").empty())
            leakage = drj.at("leakageInductance");
        atomData = make_magnetic_atom(lp, turnsRatios, leakage);
    }

    json components = json::array();
    components.push_back(json{{"name", comp}, {"data", atomData}});

    json leaf;
    leaf["name"] = name;
    leaf["ports"] = ports;
    leaf["components"] = components;
    leaf["connections"] = connections;
    return leaf;
}

} // namespace MAS
