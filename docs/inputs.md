# Inputs

> Walk-through of the `inputs` section of a MAS document. For unit
> conventions see [`units.md`](units.md); for the standards MAS defers
> to (IEC, IEV vocabulary) see
> [`normative-references.md`](normative-references.md).

A magnetic component cannot be evaluated in isolation. A description of
the application's design requirements and the excitations applied at
each operating point is required before any output (losses, temperature
rise, inductance under bias) can be computed. The `inputs` section of a
MAS document carries that information.

The specification of the inputs is therefore divided into two parts, a list of design requirements for the magnetic to comply with, and a list of operating points, which the magnetic has to be optimized for.


```mermaid
classDiagram

class Inputs {
    
    -DesignRequirements design_requirements;
    -List~OperatingPoint~ operating_points;

    +get_*()
    +set_*()
    
}
Inputs ..> DesignRequirements : Dependency
Inputs ..> OperatingPoint : Dependency

class DesignRequirements {

    InsulationRequirements insulation;
    List<IsolationSide> isolation_sides;
    List<DimensionWithTolerance> leakage_inductance;
    DimensionWithTolerance magnetizing_inductance;
    Market market;
    MaximumDimensions maximum_dimensions;
    Double maximum_weight;
    List<ImpedanceAtFrequency> minimum_impedance;
    String name;
    DimensionWithTolerance operating_temperature;
    List<DimensionWithTolerance> stray_capacitance;
    List<TerminalType> terminal_type;
    String topology;
    List<DimensionWithTolerance> turns_ratios;
    WiringTechnology wiring_technology;

    +get_*()
    +set_*()
}

class OperatingPoint {

    -OperatingConditions conditions;
    -List~OperatingPointExcitation~ excitations_per_winding;
    -String name;

    +get_*()
    +set_*()
}

```


Additionally, as it happens in reality, one design requirement can spawn many magnetic components, or a magnetic component can comply with several design requirements. 
## Name
This name references the inputs and can be used to refer to it from any number of magnetic components or simulations. This field can contain any valid string of characters.
## Design Requirements
The design requirements represent the constraints that the designer (human or software) of the magnetic has to comply with in order to create a proper device. 

As many of the requirements don’t usually have a fixed value, providing instead a tolerance or a minimum or maximum value, all field marked as numeric requirements must be specified with the following fields, of which at least one of the numeric one is compulsory:

* Nominal: Nominal numerical value for the requirement
* Minimum: Minimum numerical value for the requirement.
* Exclude Minimum: Boolean value that indicates if the minimum value is included or not.
* Maximum: Maximum numerical value for the requirement.
* Exclude Maximum: Boolean value that indicates if the maximum value is included or not.

This object must have the following fields:

The general-purpose fields (Name, Market, Topology, Operating Temperature, Terminal Type, Maximum Weight, Maximum Dimensions) are inherited from the shared PEAS `designRequirementsBase` (`PEAS/schemas/utils.json`), which also provides the optional `role`, `allowedTechnologies`, `application` and `subApplication` fields; the magnetic-specific fields are added on top by MAS.

* Name: Reference name of the design requirements.
* Magnetizing Inductance: Numeric requirement representing the inductance that the magnetic must have in order to work.
* Turns ratios: List of numeric requirements, where each element represents the turns ratio that a secondary winding must have referred to the primary. An empty list represents a component with only the primary (a basic inductor)
* Leakage inductance (optional): List of numeric requirements, where each element represents the leakage inductance that a secondary winding must have referred to the primary.
* Stray Capacitance (optional): List of numeric requirements, where each element represents the stray capacitance that a winding must have.
* Minimum Impedance (optional): List of minimum impedances at given frequencies in the primary, where each element pairs a frequency with an impedance point.
* Isolation Sides (optional): List indicating the isolation side (`primary`, `secondary`, `tertiary`, ...) that each winding is connected to.
* Wiring Technology (optional): Technology that must be used to create the wiring. It can be one of the following:
    * `wound`
    * `printed`
    * `stamped`
    * `deposition`
* Operating Temperature (optional): Numeric requirement representing the temperature that the magnetic can reach under operating.
* Insulation requirements (optional): Field needed to calculate the insulation requirements.
    * Altitude (optional): Numeric requirement representing the altitude at which the magnetic will work, in order to calculate insulation requirements.
    * CTI (optional): Required Comparative Tracking Index group per IEC 60112. It can be one of the following:
        * `groupI` — CTI ≥ 600
        * `groupII` — 400 ≤ CTI < 600
        * `groupIIIA` — 175 ≤ CTI < 400
        * `groupIIIB` — 100 ≤ CTI < 175
    * Insulation Type (optional): Required type of insulation per IEC 60664-1 §4.1. It can be one of the following:
        * `functional` — Basic operation only
        * `basic` — Single level of protection against electric shock
        * `supplementary` — Additional independent insulation
        * `double` — Basic plus supplementary insulation
        * `reinforced` — Single insulation system equivalent to double
    * Overvoltage Category (optional): Required overvoltage category per IEC 60664-1 §4.3. It can be one of the following:
        * `I` — Protected equipment, low transient overvoltage
        * `II` — Household appliances connected to fixed installation
        * `III` — Fixed installation equipment
        * `IV` — Equipment at origin of installation
    * Pollution Degree (optional): Required pollution degree per IEC 60664-1 §4.2. It can be one of the following:
        * `PD1` — No pollution or only dry non-conductive pollution
        * `PD2` — Non-conductive pollution; occasional condensation
        * `PD3` — Conductive pollution or dry pollution that becomes conductive
        * `PD4` — Persistent conductive pollution
    * Main Supply Voltage (optional): Numeric requirement representing the RMS voltage of the main supply to which this transformer is connected to.
    * Standards (optional): List of standards that will be taken into account for insulation. Each element can be one of the following:
        * `IEC 60664-1`
        * `IEC 61558-1`
        * `IEC 60335-1`
        * `IEC 62368-1`
* Market (optional): Market where the magnetic will end up being used. It can be one of the following:
    * `medical`
    * `commercial`
    * `industrial`
    * `automotive`
    * `military`
    * `space`
* Maximum Dimensions (optional): Object with `width`, `height`, and `depth` fields giving the maximum bounding-box dimensions for the designed magnetic, in m.
* Maximum Weight (optional): Maximum weight for the designed magnetic, in kg.
* Terminal Type (optional): Type of the terminal that must be used, per winding. It can be one of the following:
    * `pin`
    * `screw`
    * `smt`
    * `flyingLead`
    * `tht`
    * `pcbPad`
    * `chassis`
* Topology: Topology that will use the magnetic.


```mermaid

classDiagram

class DesignRequirements {

    InsulationRequirements insulation;
    List<IsolationSide> isolation_sides;
    List<DimensionWithTolerance> leakage_inductance;
    DimensionWithTolerance magnetizing_inductance;
    Market market;
    MaximumDimensions maximum_dimensions;
    Double maximum_weight;
    List<ImpedanceAtFrequency> minimum_impedance;
    String name;
    DimensionWithTolerance operating_temperature;
    List<DimensionWithTolerance> stray_capacitance;
    List<TerminalType> terminal_type;
    String topology;
    List<DimensionWithTolerance> turns_ratios;
    WiringTechnology wiring_technology;

    +get_*()
    +set_*()
}
DesignRequirements ..> InsulationRequirements : Dependency
DesignRequirements ..> Market : Dependency
DesignRequirements ..> TerminalType : Dependency
DesignRequirements ..> DimensionWithTolerance : Dependency

class InsulationRequirements {

    DimensionWithTolerance altitude;
    Cti cti;
    InsulationType insulation_type;
    DimensionWithTolerance main_supply_voltage;
    OvervoltageCategory overvoltage_category;
    PollutionDegree pollution_degree;
    List<InsulationStandards> standards;

    +get_*()
    +set_*()
}
InsulationRequirements ..> Cti : Dependency
InsulationRequirements ..> InsulationType : Dependency
InsulationRequirements ..> OvervoltageCategory : Dependency
InsulationRequirements ..> PollutionDegree : Dependency
InsulationRequirements ..> DimensionWithTolerance : Dependency

class DimensionWithTolerance {
    -Bool exclude_maximum;
    -Bool exclude_minimum;
    -Double maximum;
    -Double minimum;
    -Double nominal;

    +get_*()
    +set_*()
}

class Cti {
    <<enumeration>>
    GROUP_I
    GROUP_II
    GROUP_II_IA
    GROUP_II_IB
}

class InsulationType {
    <<enumeration>>
    BASIC
    DOUBLE
    FUNCTIONAL
    REINFORCED
    SUPPLEMENTARY
}

class OvervoltageCategory {
    <<enumeration>>
    OVC_I
    OVC_II
    OVC_III
    OVC_IV
}

class PollutionDegree {
    <<enumeration>>
    PD1
    PD2
    PD3
    PD4
}

class Market {
    <<enumeration>>
    AUTOMOTIVE
    COMMERCIAL
    INDUSTRIAL
    MEDICAL
    MILITARY
    SPACE
}

class TerminalType {
    <<enumeration>>
    CHASSIS
    FLYING_LEAD
    PCB_PAD
    PIN
    SCREW
    SMT
    THT
}
```

## Operating Points
The other part of a magnetic specification is the operating points that it must work under or be optimized for.
Although a magnetic is normally designed for a given topology, what really matters from the electromagnetic point of view (apart from the Design Requirement defined previously) is the excitation that it has in each of its ports, the energy that excites the magnetic component. And also is not really practical to define all variables for each topology and each of its possible configurations and controls.

Due to all these the operating points were defined from the point of view of the magnetic, as topology-agnostic waveforms, collection of points that define a signal.

And because a magnetic working on a converter must function and be efficient over a range of operating conditions, it must be designed taking into account different excitations and conditions, so it can be optimal for common cases and still work in extreme cases.

To take this into account, the operating points are designed as a list, where each element contains two main fields: the operating conditions and excitations of each winding.

```mermaid

classDiagram

class OperatingPoint {

    -OperatingConditions conditions;
    -List~OperatingPointExcitation~ excitations_per_winding;
    -String name;

    +get_*()
    +set_*()
}

OperatingPoint ..> OperatingConditions : Dependency
OperatingPoint ..> OperatingPointExcitation : Dependency

class OperatingConditions {

    -Double ambient_relative_humidity;
    -Double ambient_temperature;
    -Cooling cooling;
    -String name;

    +get_*()
    +set_*()
}

OperatingConditions ..> Cooling : Dependency

class Cooling {

    -String fluid;
    -Double temperature;
    -Double flow_diameter;
    -List<Double> velocity;
    -List<Double> dimensions;
    -Double interface_thermal_resistance;
    -Double interface_thickness;
    -Double thermal_resistance;
    -Double maximum_temperature;

    +get_*()
    +set_*()
}

class OperatingPointExcitation {

    -SignalDescriptor current;
    -Double frequency;
    -SignalDescriptor magnetic_field_strength;
    -SignalDescriptor magnetic_flux_density;
    -SignalDescriptor magnetizing_current;
    -String name;
    -SignalDescriptor voltage;

    +get_*()
    +set_*()
}

OperatingPointExcitation ..> SignalDescriptor : Dependency

class SignalDescriptor {

    -Harmonics harmonics;
    -Processed processed;
    -Waveform waveform;

    +get_*()
    +set_*()
}
```

### Name
This name references the Operating Point and can be used to refer to it from any number of magnetic components or simulations. This field can contain any valid string of characters.
### Operating Conditions
Before defining the excitations it is necessary to define the ambient conditions that will exist at that point. The reason these variables are defined here and not in the previous section of Design Requirements is to give the opportunity to design the magnetic for different excitations and different temperature and humidities and see how it behaves, instead of a global maximum value.

* Ambient temperature: Ambient temperature for this operating point.
* Relative humidity (optional): Relative humidity for this operating point.
* Cooling: Dictionary/Map that represents the cooling condition applied to the magnetic. It can be one of the following options:
    * Natural Convection Cooling: Data describing a natural convection cooling.
        * Temperature: Temperature of the fluid. To be used only if different from ambient temperature.
        * Fluid: Name of the fluid used, default: air.
    * Forced Convection Cooling: Data describing a forced convection cooling.
        * Velocity: Three-dimensional vector describing the velocity of the fluid.
        * Flow Diameter: Diameter of the fluid flow, normally defined as a fan diameter.
        * Temperature: Temperature of the fluid. To be used only if different from ambient temperature.
        * Fluid: Name of the fluid used.
    * Heatsink Cooling: Data describing a heatsink cooling.
        * Thermal Resistance: Bulk thermal resistance of the heat sink, in W/K.
        * Interface Thermal Resistance: Bulk thermal resistance of the thermal interface used to connect the device to the heatsink, in W/mK.
        * Interface Thickness: Thickness of the thermal interface used to connect the device to the heatsink, in m.
        * Dimensions: Dimensions of the cube defining the heatsink.
    * Cold Plate Cooling: Data describing a cold plate cooling.
        * Thermal Resistance: Bulk thermal resistance of the cold plate, in W/K.
        * Maximum Temperature: Maximum temperature of the cold plate.
        * Interface Thermal Resistance: Bulk thermal resistance of the thermal interface used to connect the device to the cold plate, in W/mK.
        * Interface Thickness: Thickness of the thermal interface used to connect the device to the cold plate, in m.
        * Dimensions: Dimensions of the cube defining the cold plate.

### Excitation per winding
This section describes the most important part of all the inputs, the waveforms that the magnetic will see, and be excited by, at each of its inputs and outputs. 
In order to have a structure that supports any number and combinations of individual windings, the excitations are defined in a list, with a number of elements equal to the number of elements in the Design Requirement field of Turns Ratios plus one, or what is equivalent, the number of windings.

It is possible that excitations for some or all secondaries are missing from specification, in which case they can be calculated by reflecting the waveform from the primary with the turns ratio of each secondary.

Each of these elements are composed of a frequency and one or more Electromagnetic Parameters (e.g.: current, voltage), and before looking at all the possible fields, I would like to define what an Electromagnetic Parameter is in this context.
#### Electromagnetic Parameters
This type is a template for any kind of signal existing in a magnetic, and as it happens with the important variables of the magnetic core, they are defined at three levels of definition, all of them derivable from any of them, which means that any level can completely define the signal.

The first level of definition is the direct waveform, and contains the following fields:
* Data: List of numeric values that define the signal. If the list comes without an associated time field, these values must be considered equidistant and evenly spread over the period.
* Time (optional): List of numeric values that define the time of each of the data points inside the period.

The second level of definition is the processed data about the waveform, from which the waveform itself can be built back. Additionally, they are designed to quickly provide for the values necessary in most analytical models. It contains the following fields:
* Label: Label of the waveform, if applicable. Used for common waveforms. If `custom`, the proper waveform must be defined. It can be one of the following:
    * `custom`
    * `triangular`, `triangularWithDeadtime`
    * `sinusoidal`
    * `rectangular`, `rectangularWithDeadtime`, `rectangularDCM`
    * `unipolarRectangular`, `unipolarTriangular`
    * `bipolarRectangular`, `bipolarTriangular`
    * `flybackPrimary`, `flybackSecondary`, `flybackSecondaryWithDeadtime`
    * `secondaryRectangular`, `secondaryRectangularWithDeadtime`
* Duty Cycle: The duty cycle of the waveform, if applicable.
* Peak To Peak: The peak to peak value of the waveform.
* Peak: The maximum positive value of the waveform.
* Offset: The offset value of the waveform, referred to 0.
* RMS: The Root Mean Square value of the waveform.
* Effective Frequency: The effective frequency value of the waveform, according to https://ieeexplore.ieee.org/document/750181, Appendix C
* AC Effective Frequency: The effective frequency value of the AC component of the waveform.
* THD: The Total Harmonic Distortion of the waveform, according to https://en.wikipedia.org/wiki/Total_harmonic_distortion

The third and last level of definition is the harmonics data, which is a list of the most powerful harmonics in the signal, created by applying the Discrete Fourier Transform to the signal, and which can be reversed in order to create back the original signal, although with loss of information, as the list of harmonics is not infinite. It has the following fields:
* Amplitudes: List of amplitudes of the harmonics that compose the waveform.
* Frequencies: List of frequencies of the harmonics that compose the waveform.


```mermaid
classDiagram

class SignalDescriptor {

    -Harmonics harmonics;
    -Processed processed;
    -Waveform waveform;

    +get_*()
    +set_*()
}

SignalDescriptor ..> Harmonics : Dependency
SignalDescriptor ..> Processed : Dependency
SignalDescriptor ..> Waveform : Dependency


class Harmonics {

    -std::vector<double> amplitudes;
    -std::vector<double> frequencies;

    +get_*()
    +set_*()
}

class Processed {

    -Double ac_effective_frequency;
    -Double duty_cycle;
    -Double effective_frequency;
    -WaveformLabel label;
    -Double offset;
    -Double peak;
    -Double peak_to_peak;
    -Double rms;
    -Double thd;

    +get_*()
    +set_*()
}
Processed ..> WaveformLabel : Dependency

class WaveformLabel {
    <<enumeration>>
    CUSTOM
    FLYBACK
    PHASE_SHIFTED_FULL_BRIDGE
    SINUSOIDAL
    SQUARE
    SQUARE_WITH_DEAD_TIME
    TRIANGULAR
}

class Waveform {
    -Integer number_periods;
    -String ancillary_label;
    -List~double~ data;
    -List~double~ time;

    +get_*()
    +set_*()
}
```


#### Excitation
Now that we have defined what we are calling Electromagnetic Parameter, let’s use that definition to finally describe the structure of the excitation per winding, which contains the following fields (pun intended):

Frequency: Frequency of the waveform, common for all electromagnetic parameters
Current: Electromagnetic Parameter representing the current through the wires of the winding.
Voltage: Electromagnetic Parameter representing the voltage that falls at the winding.
Magnetizing Current: Electromagnetic Parameter representing the part of the current used in magnetizing the magnetic core and generating the magnetic field. For inductors with one winding it is equal to the current field.
Magnetic Flux Density: Electromagnetic Parameter representing the magnetic flux density circulating through the magnetic core, induced by the magnetizing current.
Magnetic Field Strength: Electromagnetic Parameter representing the magnetic field strength circulating through the magnetic core, induced by the magnetizing current.

Wrapping up the inputs
As happened with the magnetic, the MAS format for the inputs can include quite a lot of information, but it is designed so all that information can be calculated from a small specification file, perfectly understandable by humans and software.

Example inputs for an inductor:
```
{
    "name": "My Inputs",
    "designRequirements": {
        "magnetizingInductance": {"nominal": 0.000465},
        "turnsRatios": []
    },
    "operatingPoints": [
        {
            "conditions": {
                "ambientTemperature": 25.0,
                "cooling": {
                    "fluid": "air",
                    "velocity": [0, 0, 0]
                }
            },
            "excitationsPerWinding": [
                {
                    "frequency": 100000.0,
                    "current": {
                        "waveform": {
                            "data": [41.0, 51.0, 41.0],
                            "time": [0.0, 2.5e-06, 1e-05]
                        }
                    },
                    "voltage": {
                        "waveform": {
                            "data": [7.5, 7.5, -2.5, -2.5, 7.5],
                            "time": [0.0, 2.5e-06, 2.5e-06, 1e-05, 1e-05]
                        }
                    }
                }
            ]
        }
    ]
}
```

