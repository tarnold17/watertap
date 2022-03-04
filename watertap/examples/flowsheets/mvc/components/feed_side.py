###############################################################################
# WaterTAP Copyright (c) 2021, The Regents of the University of California,
# through Lawrence Berkeley National Laboratory, Oak Ridge National
# Laboratory, National Renewable Energy Laboratory, and National Energy
# Technology Laboratory (subject to receipt of any required approvals from
# the U.S. Dept. of Energy). All rights reserved.
#
# Please see the files COPYRIGHT.md and LICENSE.md for full copyright and license
# information, respectively. These files are also available online at the URL
# "https://github.com/watertap-org/watertap/"
#
###############################################################################

# Import Pyomo libraries
from pyomo.environ import (Block,
                           Set,
                           Var,
                           Param,
                           Suffix,
                           NonNegativeReals,
                           Reference,
                           units as pyunits)
from pyomo.common.config import ConfigBlock, ConfigValue, In

# Import IDAES cores
from idaes.core import (ControlVolume0DBlock,
                        declare_process_block_class,
                        MaterialBalanceType,
                        EnergyBalanceType,
                        MomentumBalanceType,
                        UnitModelBlockData,
                        useDefault,
                        MaterialFlowBasis)
from idaes.core.util import get_solver
from idaes.core.util.tables import create_stream_table_dataframe
from idaes.core.util.config import is_physical_parameter_block
from idaes.core.util.exceptions import ConfigurationError
import idaes.core.util.scaling as iscale
import idaes.logger as idaeslog


_log = idaeslog.getLogger(__name__)

@declare_process_block_class("Feed_side")
class EvaporatorData(UnitModelBlockData):
    """
    Evaporator model for MVC
    """
    # CONFIG are options for the unit model, this simple model only has the mandatory config options
    CONFIG = ConfigBlock()

    CONFIG.declare("dynamic", ConfigValue(
        domain=In([False]),
        default=False,
        description="Dynamic model flag - must be False",
        doc="""Indicates whether this model will be dynamic or not,
    **default** = False. The filtration unit does not support dynamic
    behavior, thus this must be False."""))
    CONFIG.declare("has_holdup", ConfigValue(
        default=False,
        domain=In([False]),
        description="Holdup construction flag - must be False",
        doc="""Indicates whether holdup terms should be constructed or not.
    **default** - False. The filtration unit does not have defined volume, thus
    this must be False."""))
    CONFIG.declare("property_package_feed", ConfigValue(
        domain=is_physical_parameter_block,
        description="Property package to use for control volume",
        doc="""Property parameter object used to define property calculations,
    **default** - useDefault.
    **Valid values:** {
    **useDefault** - use default package from parent model or flowsheet,
    **PhysicalParameterObject** - a PhysicalParameterBlock object.}"""))
    CONFIG.declare("property_package_args_feed", ConfigBlock(
        implicit=True,
        description="Arguments to use for constructing property packages",
        doc="""A ConfigBlock with arguments to be passed to a property block(s)
    and used when constructing these,
    **default** - None.
    **Valid values:** {
    see property package for documentation.}"""))
    CONFIG.declare("property_package_vapor", ConfigValue(
        domain=is_physical_parameter_block,
        description="Property package to use for control volume",
        doc="""Property parameter object used to define property calculations,
        **default** - useDefault.
        **Valid values:** {
        **useDefault** - use default package from parent model or flowsheet,
        **PhysicalParameterObject** - a PhysicalParameterBlock object.}"""))
    CONFIG.declare("property_package_args_vapor", ConfigBlock(
        implicit=True,
        description="Arguments to use for constructing property packages",
        doc="""A ConfigBlock with arguments to be passed to a property block(s)
        and used when constructing these,
        **default** - None.
        **Valid values:** {
        see property package for documentation.}"""))
    CONFIG.declare("material_balance_type", ConfigValue(
        default=MaterialBalanceType.useDefault,
        domain=In(MaterialBalanceType),
        description="Material balance construction flag",
        doc="""Indicates what type of mass balance should be constructed,
        **default** - MaterialBalanceType.useDefault.
        **Valid values:** {
        **MaterialBalanceType.useDefault - refer to property package for default
        balance type
        **MaterialBalanceType.none** - exclude material balances,
        **MaterialBalanceType.componentPhase** - use phase component balances,
        **MaterialBalanceType.componentTotal** - use total component balances,
        **MaterialBalanceType.elementTotal** - use total element balances,
        **MaterialBalanceType.total** - use total material balance.}"""))
    CONFIG.declare("energy_balance_type", ConfigValue(
        default=EnergyBalanceType.useDefault,
        domain=In(EnergyBalanceType),
        description="Energy balance construction flag",
        doc="""Indicates what type of energy balance should be constructed,
        **default** - EnergyBalanceType.useDefault.
        **Valid values:** {
        **EnergyBalanceType.useDefault - refer to property package for default
        balance type
        **EnergyBalanceType.none** - exclude energy balances,
        **EnergyBalanceType.enthalpyTotal** - single enthalpy balance for material,
        **EnergyBalanceType.enthalpyPhase** - enthalpy balances for each phase,
        **EnergyBalanceType.energyTotal** - single energy balance for material,
        **EnergyBalanceType.energyPhase** - energy balances for each phase.}"""))
    CONFIG.declare("momentum_balance_type", ConfigValue(
        default=MomentumBalanceType.pressureTotal,
        domain=In(MomentumBalanceType),
        description="Momentum balance construction flag",
        doc="""Indicates what type of momentum balance should be constructed,
        **default** - MomentumBalanceType.pressureTotal.
        **Valid values:** {
        **MomentumBalanceType.none** - exclude momentum balances,
        **MomentumBalanceType.pressureTotal** - single pressure balance for material,
        **MomentumBalanceType.pressurePhase** - pressure balances for each phase,
        **MomentumBalanceType.momentumTotal** - single momentum balance for material,
        **MomentumBalanceType.momentumPhase** - momentum balances for each phase.}"""))


    def build(self):
        super().build()

        if self.config.property_package_feed is None:
            raise ConfigurationError("Users must provide a feed property package to the evaporator unit model")
        if self.config.property_package_vapor is None:
            raise ConfigurationError("Users must provide a vapor property package to the evaporator unit model")

        # this creates blank scaling factors, which are populated later
        self.scaling_factor = Suffix(direction=Suffix.EXPORT)

        # Next, get the base units of measurement from the property definition
        units_meta_feed = self.config.property_package_feed.get_metadata().get_derived_units # TODO: Should be same as vapor package - need error message if not?

        # Add unit model variables
        self.heat_transfer = Var(
            initialize = 1e4,
            bounds=(1,1e10),
            units=pyunits.J * pyunits.s**-1
        )

        # Add state blocks
        # Feed state block
        tmp_dict = dict(**self.config.property_package_args_feed)
        tmp_dict["has_phase_equilibrium"] = False
        tmp_dict["parameters"] = self.config.property_package_feed
        tmp_dict["defined_state"] = True  # feed inlet defined
        self.properties_feed = self.config.property_package_feed.state_block_class(
            self.flowsheet().config.time,
            doc="Material properties of feed inlet",
            default=tmp_dict)

        # Brine state block
        tmp_dict["defined_state"] = False  # brine outlet not yet defined
        self.properties_brine = self.config.property_package_feed.state_block_class(
            self.flowsheet().config.time,
            doc="Material properties of brine outlet",
            default=tmp_dict)

        # Vapor state block
        tmp_dict = dict(**self.config.property_package_args_vapor)
        tmp_dict["has_phase_equilibrium"] = False
        tmp_dict["parameters"] = self.config.property_package_vapor
        tmp_dict["defined_state"] = False  # vapor outlet not yet defined
        self.properties_vapor = self.config.property_package_vapor.state_block_class(
            self.flowsheet().config.time,
            doc="Material properties of vapor outlet",
            default=tmp_dict)

        # Add ports - oftentimes users interact with these rather than the state blocks
        self.add_port(name='inlet_feed', block=self.properties_feed)
        self.add_port(name='outlet_brine', block=self.properties_brine)
        self.add_port(name='outlet_vapor', block=self.properties_vapor)

        # Add constraints

        ### EVAPORATOR CONSTRAINTS ###
        # Mass balance
        @self.Constraint(self.flowsheet().time, self.config.property_package_feed.component_list, doc="Mass balance")
        def eq_mass_balance(b,t,j):
            lb = b.properties_vapor[t].flow_mass_phase_comp['Liq', 'H2O'].lb
            b.properties_vapor[t].flow_mass_phase_comp['Liq', 'H2O'].fix(lb)
            if j == 'H2O':
                return b.properties_feed[t].flow_mass_phase_comp['Liq','H2O']  == \
                   b.properties_brine[t].flow_mass_phase_comp['Liq','H2O'] + b.properties_vapor[t].flow_mass_phase_comp['Vap','H2O']

            else:
                return b.properties_feed[t].flow_mass_phase_comp['Liq',j] == b.properties_brine[t].flow_mass_phase_comp['Liq',j]

        # Energy balance
        @self.Constraint(self.flowsheet().time,doc="Energy balance")
        def eq_energy_balance(b,t):
            return b.heat_transfer + b.properties_feed[t].enth_flow == b.properties_brine[t].enth_flow + b.properties_vapor[t].enth_flow_phase['Vap']

        # Brine pressure
        @self.Constraint(self.flowsheet().time, doc="Brine temperature") #TODO: changet to saturation pressure
        def eq_brine_temperature(b, t):
             return b.properties_brine[t].pressure == b.properties_brine[t].pressure_sat

        # Vapor pressure
        @self.Constraint(self.flowsheet().time,doc="Vapor pressure")
        def eq_vapor_pressure(b,t):
            return b.properties_vapor[t].pressure == b.properties_brine[t].pressure

        # Vapor temperature
        @self.Constraint(self.flowsheet().time, doc="Vapor temperature")
        def eq_vapor_temperature(b, t):
            return b.properties_vapor[t].temperature == b.properties_brine[t].temperature
            # return b.properties_vapor[t].temperature == 0.5*(b.properties_out[t].temperature + b.properties_in[t].temperature)

        # @self.Constraint(self.flowsheet().time, doc="Temperature difference in")
        # def eq_delta_temperature_in(b, t):
        #     return b.delta_temperature_in[t] == b.condenser_out.temperature - b.properties_out[t].temperature

        # @self.Constraint(self.flowsheet().time, doc="Temperature difference out")
        # def eq_delta_temperature_out(b, t):
        #     return b.delta_temperature_out[t] == b.condenser_in.temperature - b.properties_out[t].temperature

        # log mean temperature
        # @self.Constraint(self.flowsheet().time, doc="Log mean temperature difference")
        # def eq_lmtd(b, t):
        #     dT_in= b.delta_temperature_in[t]
        #     dT_out = b.delta_temperature_out[t]
        #     temp_units = pyunits.get_units(dT_in)
        #     dT_avg = (dT_in + dT_out) / 2
        #     return b.delta_temperature == (dT_in * dT_out * dT_avg) ** (1 / 3) * temp_units

    def initialize(
            blk,
            state_args=None,
            outlvl=idaeslog.NOTSET,
            solver=None,
            optarg=None):
        """
        General wrapper for pressure changer initialization routines

        Keyword Arguments:
            state_args : a dict of arguments to be passed to the property
                         package(s) to provide an initial state for
                         initialization (see documentation of the specific
                         property package) (default = {}).
            outlvl : sets output level of initialization routine
            optarg : solver options dictionary object (default=None)
            solver : str indicating which solver to use during
                     initialization (default = None)

        Returns: None
        """
        init_log = idaeslog.getInitLogger(blk.name, outlvl, tag="unit")
        solve_log = idaeslog.getSolveLogger(blk.name, outlvl, tag="unit")
        # Set solver options
        opt = get_solver(solver, optarg)

        # ---------------------------------------------------------------------
        # Initialize state blocks
        flags = blk.properties_feed.initialize(
            outlvl=outlvl,
            optarg=optarg,
            solver=solver,
            state_args=state_args,
            hold_state=True,
        )
        print('flags:', flags)
        init_log.info_high("Initialization Step 1 Complete.")
        # # ---------------------------------------------------------------------
        # # Initialize permeate
        # Set state_args from inlet state
        if state_args is None:
            state_args = {}
            state_dict = blk.properties_feed[
                blk.flowsheet().config.time.first()].define_port_members()

            for k in state_dict.keys():
                if state_dict[k].is_indexed():
                    state_args[k] = {}
                    for m in state_dict[k].keys():
                        state_args[k][m] = state_dict[k][m].value
                else:
                    state_args[k] = state_dict[k].value

        blk.properties_brine.initialize(
            outlvl=outlvl,
            optarg=optarg,
            solver=solver,
            state_args=state_args,
        )

        state_args_vapor = {}
        state_args_vapor['pressure'] = state_args['pressure']
        state_args_vapor['temperature'] = state_args['temperature']
        state_args_vapor['flow_mass_phase_comp'] = {
            ('Liq','H2O'): blk.properties_vapor[0].flow_mass_phase_comp['Liq','H2O'].lb,
            ('Vap','H2O'): state_args['flow_mass_phase_comp'][('Liq','H2O')]}
        blk.properties_vapor.initialize(
            outlvl=outlvl,
            optarg=optarg,
            solver=solver,
            state_args=state_args_vapor,
        )
        init_log.info_high("Initialization Step 2 Complete.")
        # ---------------------------------------------------------------------
        # Solve unit
        with idaeslog.solver_log(solve_log, idaeslog.DEBUG) as slc:
            res = opt.solve(blk, tee=slc.tee)
        init_log.info_high(
            "Initialization Step 3 {}.".format(idaeslog.condition(res)))

        # ---------------------------------------------------------------------
        # Release Inlet state
        print('flags:', flags)
        blk.properties_feed.release_state(flags, outlvl=outlvl)
        init_log.info(
            "Initialization Complete: {}".format(idaeslog.condition(res))
        )

    def _get_performance_contents(self, time_point=0):
        var_dict = {}

        return {"vars": var_dict}

    def calculate_scaling_factors(self):
        super().calculate_scaling_factors()

        if iscale.get_scaling_factor(self.heat_transfer) is None:
            sf = iscale.get_scaling_factor(self.properties_vapor[0].enth_flow_phase['Vap'])
            iscale.set_scaling_factor(self.heat_transfer, sf)

        # for (t,j), c in self.eq_mass_balance.items():
        #     sf = iscale.get_scaling_factor(self.properties_feed[t].flow_mass_phase_comp['Liq', j])
        #     iscale.constraint_scaling_transform(c, sf)
        #
        # # Pressure constraints
        # sf = iscale.get_scaling_factor(self.properties_feed[0].pressure)
        # iscale.constraint_scaling_transform(self.eq_vapor_pressure, sf)
        #
        # # Temperature constraint
        # sf = iscale.get_scaling_factor(self.properties_feed[0].temperature)
        # iscale.constraint_scaling_transform(self.eq_brine_temperature, sf)
        # iscale.constraint_scaling_transform(self.eq_vapor_temperature, sf)
        #
        # # Efficiency, work constraints
        # sf = iscale.get_scaling_factor(self.heat_transfer)
        # iscale.constraint_scaling_transform(self.eq_energy_balance, sf)
