###############################################################################
# ProteusLib Copyright (c) 2021, The Regents of the University of California,
# through Lawrence Berkeley National Laboratory, Oak Ridge National
# Laboratory, National Renewable Energy Laboratory, and National Energy
# Technology Laboratory (subject to receipt of any required approvals from
# the U.S. Dept. of Energy). All rights reserved.
#
# Please see the files COPYRIGHT.md and LICENSE.md for full copyright and license
# information, respectively. These files are also available online at the URL
# "https://github.com/nawi-hub/proteuslib/"
#
###############################################################################

"""0D reverse osmosis examples"""

from pyomo.environ import ConcreteModel
from idaes.core import FlowsheetBlock
from idaes.core.util.scaling import calculate_scaling_factors
import proteuslib.property_models.seawater_prop_pack as props
from proteuslib.unit_models.reverse_osmosis_0D import (ReverseOsmosis0D,
                                                       ConcentrationPolarizationType,
                                                       MassTransferCoefficient,
                                                       PressureChangeType)
from proteuslib.flowsheets.full_treatment_train.util import solve_with_user_scaling, check_dof


def build_simple_RO_example(m):
    # build unit
    m.fs.RO_properties = props.SeawaterParameterBlock()
    m.fs.RO = ReverseOsmosis0D(default={"property_package": m.fs.RO_properties})

    # specify unit
    # feed
    feed_flow_mass = 1
    feed_mass_frac_TDS = 0.035
    m.fs.RO.inlet.flow_mass_phase_comp[0, 'Liq', 'TDS'].fix(feed_flow_mass * feed_mass_frac_TDS)
    m.fs.RO.inlet.flow_mass_phase_comp[0, 'Liq', 'H2O'].fix(feed_flow_mass * (1 - feed_mass_frac_TDS))
    m.fs.RO.inlet.pressure[0].fix(50e5)
    m.fs.RO.inlet.temperature[0].fix(298.15)
    # RO
    m.fs.RO.area.fix(50 * feed_flow_mass)
    m.fs.RO.A_comp.fix(4.2e-12)
    m.fs.RO.B_comp.fix(3.5e-8)
    m.fs.RO.permeate.pressure[0].fix(101325)
    check_dof(m)

    # scale unit
    m.fs.RO_properties.set_default_scaling('flow_mass_phase_comp', 1 / feed_flow_mass, index=('Liq', 'H2O'))
    m.fs.RO_properties.set_default_scaling('flow_mass_phase_comp', 1 / feed_flow_mass * 1e2, index=('Liq', 'TDS'))
    calculate_scaling_factors(m.fs.RO)

    # initialize
    m.fs.RO.initialize(optarg={'nlp_scaling_method': 'user-scaling'})


def build_detailed_RO_example(m):
    # build unit
    m.fs.RO_properties = props.SeawaterParameterBlock()
    m.fs.RO = ReverseOsmosis0D(default={
        "property_package": m.fs.RO_properties,
        "has_pressure_change": True,
        "pressure_change_type": PressureChangeType.calculated,
        "mass_transfer_coefficient": MassTransferCoefficient.calculated,
        "concentration_polarization_type": ConcentrationPolarizationType.calculated})

    # specify unit
    # feed
    feed_flow_mass = 1
    feed_mass_frac_TDS = 0.035
    m.fs.RO.inlet.flow_mass_phase_comp[0, 'Liq', 'TDS'].fix(feed_flow_mass * feed_mass_frac_TDS)
    m.fs.RO.inlet.flow_mass_phase_comp[0, 'Liq', 'H2O'].fix(feed_flow_mass * (1 - feed_mass_frac_TDS))
    m.fs.RO.inlet.pressure[0].fix(50e5)
    m.fs.RO.inlet.temperature[0].fix(298.15)
    # RO
    m.fs.RO.area.fix(50 * feed_flow_mass)
    m.fs.RO.A_comp.fix(4.2e-12)
    m.fs.RO.B_comp.fix(3.5e-8)
    m.fs.RO.permeate.pressure[0].fix(101325)
    m.fs.RO.channel_height.fix(1e-3)
    m.fs.RO.spacer_porosity.fix(0.97)
    m.fs.RO.N_Re_io[0, 'in'].fix(500)
    check_dof(m)

    # scaling
    m.fs.RO_properties.set_default_scaling('flow_mass_phase_comp', 1 / feed_flow_mass, index=('Liq', 'H2O'))
    m.fs.RO_properties.set_default_scaling('flow_mass_phase_comp', 1 / feed_flow_mass * 1e2, index=('Liq', 'TDS'))
    calculate_scaling_factors(m.fs.RO)

    # initialize
    m.fs.RO.initialize(optarg={'nlp_scaling_method': 'user-scaling'})


def run_simple_RO_example():
    m = ConcreteModel()
    m.fs = FlowsheetBlock(default={"dynamic": False})

    build_simple_RO_example(m)
    solve_with_user_scaling(m)

    m.fs.RO.report()


def run_detailed_RO_example():
    m = ConcreteModel()
    m.fs = FlowsheetBlock(default={"dynamic": False})

    build_detailed_RO_example(m)
    solve_with_user_scaling(m)

    m.fs.RO.report()


if __name__ == "__main__":
    run_simple_RO_example()
    run_detailed_RO_example()
