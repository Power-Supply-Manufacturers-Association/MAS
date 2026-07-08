#pragma once

// MasConverter — "generate a CIAS element (leaf) from a MAS magnetic part".
//
// MAS is the only family with THREE origins:
//   REQUIREMENTS (ideal): the coupled-inductor model from inputs.designRequirements
//       (magnetizingInductance + turnsRatios + leakageInductance).
//   DATASHEET           : the coupled-inductor model from the bound catalog part's
//       manufacturerInfo.datasheetInfo.electrical configuration entry (per-winding/magnetizing
//       inductance, stated turnsRatios, leakage or coupling coefficient).
//   MKF_MODEL           : full physical model via MKF export_magnetic_as_subcircuit, carried in
//       magnetic.modelOutputs.spiceSubcircuit by the bind step.
//
// Per the CIAS rule, a transformer is ONE multi-winding component (coupling lives INSIDE its MAS
// model, never as a CIAS edge). So the leaf has a single magnetic component "T" whose winding
// terminals are the pins primary_start/primary_end/secondary{i}_start/secondary{i}_end. The CIAS
// emitter (P2) expands that one component into L (per winding) + K when emitting SPICE, deriving
// each winding's K from the atom's leakageInductance (k_i = sqrt(1 - Llk_i/Lp), capped just below
// unity for matrix conditioning).

#include <nlohmann/json.hpp>
#include <string>
#include "Fidelity.hpp"

namespace MAS {

nlohmann::json mas_to_cias(const nlohmann::json& peas,
                           const PEAS::Fidelity& fidelity,
                           const std::string& name = "transformer");

} // namespace MAS
