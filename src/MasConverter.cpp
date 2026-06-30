#include "MasConverter.hpp"
#include "MAS.hpp"        // quicktype-generated typed structs (build/MAS.hpp)
#include "Dimension.hpp"  // PEAS::resolve_dimensional_values

#include <stdexcept>
#include <vector>
#include <string>
#include <cmath>
#include <algorithm>

namespace MAS {

using nlohmann::json;

namespace {

// One magnetic component carrying the ideal coupled-inductor design (magnetizingInductance +
// turnsRatios + the winding coupling K). The CIAS emitter reads these to expand into L (per winding)
// + K. The coupling is decided HERE (the magnetic family owns equiv-circuit modeling, decisions 2/5);
// CIAS only emits the carried value. See compute_coupling().
json make_magnetic_atom(double lp, const std::vector<double>& turnsRatios, double coupling) {
    json ratios = json::array();
    for (double n : turnsRatios) ratios.push_back(json{{"nominal", n}});

    json atom;
    atom["magnetic"] = json::object();
    atom["inputs"]["designRequirements"]["magnetizingInductance"]["nominal"] = lp;
    atom["inputs"]["designRequirements"]["turnsRatios"] = ratios;
    atom["inputs"]["designRequirements"]["coupling"] = coupling;
    return atom;
}

// Ideal-seed winding coupling K for the coupled-inductor model. If the design specifies a leakage
// inductance, derive K from it (primary-referred leakage Llk = Lp*(1 - K^2) => K = sqrt(1 - Llk/Lp));
// otherwise use 0.9999. 0.9999 is also the conditioning CEILING: perfect coupling K=1 makes the
// coupled-L matrix singular (det = Lp*Ls*(1-K^2) = 0) and blows up ngspice whenever the transformer is
// in series with another inductor (every bridge/resonant topology), so even a near-zero specified
// leakage is clamped to 0.9999. (Real designed magnetics use the MKF_MODEL subcircuit instead, whose
// coupling comes from the actual leakage — this path is the pre-sourcing ideal seed only.)
double compute_coupling(const DesignRequirements& dr, double lp) {
    double k = 0.9999;
    auto llkOpt = dr.get_leakage_inductance();
    if (llkOpt && !llkOpt->empty() && lp > 0) {
        double llk = PEAS::resolve_dimensional_values((*llkOpt)[0]);
        if (llk > 0 && llk < lp) k = std::min(k, std::sqrt(1.0 - llk / lp));
    }
    return k;
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

    if (fidelity.origin == Origin::DATASHEET)
        throw std::runtime_error(
            "MAS DATASHEET origin (per-winding inductance from datasheetInfo) is not yet "
            "implemented (Phase 4)");

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
    } else {
        auto dr = peas.at("inputs").at("designRequirements").get<DesignRequirements>();
        const double lp = PEAS::resolve_dimensional_values(dr.get_magnetizing_inductance());
        atomData = make_magnetic_atom(lp, turnsRatios, compute_coupling(dr, lp));
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
