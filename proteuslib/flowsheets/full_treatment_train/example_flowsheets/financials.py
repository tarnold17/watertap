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
from pyomo.environ import (
    Block, Constraint, Expression, Var, Param, Reals, NonNegativeReals, units as pyunits)
from idaes.core.util.exceptions import ConfigurationError


# TODO: choose year --> 2018 probably (use CEPCI)
# TODO: in example flowsheets --> build_costing and use **kwargs to build flowsheet
# TODO: make kwargs dict
# Todo: have options for PX types/pump types (for example) or use more generic approach with conditionals
# mixers, splitters, pumps, erds, RO, NF, stoich reactor (lime softening), equilibrium reactor (chlorination)

def add_costing_param_block(self):
    self.costing_param = Block()
    b = self.costing_param

    b.load_factor = Var(
        initialize=0.9,
        doc='Load factor [fraction of uptime]')
    b.factor_total_investment = Var(
        initialize=2,
        doc='Total investment factor [investment cost/equipment cost]')
    b.factor_MLC = Var(
        initialize=0.03,
        doc='Maintenance-labor-chemical factor [fraction of investment cost/year]')
    b.factor_capital_annualization = Var(
        initialize=0.1,
        doc='Capital annualization factor [fraction of investment cost/year]')
    b.factor_membrane_replacement = Var(
        initialize=0.2,
        doc='Membrane replacement factor [fraction of membrane replaced/year]')
    b.electricity_cost = Var(
        initialize=0.07,
        doc='Electricity cost [$/kWh]')
    b.RO_mem_cost = Var(
        initialize=30,
        doc='Membrane cost [$/m2]')
    b.NF_mem_cost = Var(
        initialize=15,
        doc='Membrane cost [$/m2]')
    b.hp_pump_cost = Var(
        initialize=53 / 1e5 * 3600,
        doc='High pressure pump cost [$/W]')
    b.pxr_cost = Var(
        initialize=535,
        doc='Pressure exchanger cost [$/(m3/h)]')
    b.chemical_lime_cost = Var(
        #TODO: add "real" value instead of dummy val for lime cost per kg
        initialize=1,
        doc='Lime cost [$/kg]')

    # traditional parameters are the only Vars on the block and should be fixed
    for v in b.component_objects(Var, descend_into=True):
        for i in v:
            if v[i].value is None:
                raise ConfigurationError(
                    "{} parameter {} was not assigned"
                    " a value. Please check your configuration "
                    "arguments.".format(b.name, v.local_name))
            v[i].fix()


def get_system_costing(self):
    if not hasattr(self, 'costing'):
        self.costing = Block()
    b = self.costing

    b.capital_cost_total = Var(
        initialize=1e3,
        domain=NonNegativeReals,
        doc='Total capital cost [$]')
    b.investment_cost_total = Var(
        initialize=1e3,
        domain=NonNegativeReals,
        doc='Total investment cost [$]')
    b.operating_cost_MLC = Var(
        initialize=1e3,
        domain=NonNegativeReals,
        doc='Maintenance-labor-chemical operating cost [$/year]')
    b.operating_cost_total = Var(
        initialize=1e3,
        domain=NonNegativeReals,
        doc='Total operating cost [$/year]')
    b.LCOW = Var(
        initialize=1,
        domain=NonNegativeReals,
        doc='Levelized cost of water [$/m3]')

    capital_cost_var_lst = []
    operating_cost_var_lst = []
    for b_unit in self.component_objects(Block, descend_into=True):
        if hasattr(b_unit, 'costing'):
            capital_cost_var_lst.append(b_unit.costing.capital_cost)
            operating_cost_var_lst.append(b_unit.costing.operating_cost)
    operating_cost_var_lst.append(b.operating_cost_MLC)

    b.eq_capital_cost_total = Constraint(
        expr=b.capital_cost_total == sum(capital_cost_var_lst))
    b.eq_investment_cost_total = Constraint(
        expr=(b.investment_cost_total ==
              b.capital_cost_total * self.costing_param.factor_total_investment))
    b.eq_operating_cost_MLC = Constraint(
        expr=(b.operating_cost_MLC ==
              b.investment_cost_total * self.costing_param.factor_MLC))
    b.eq_operating_cost_total = Constraint(
        expr=b.operating_cost_total == sum(operating_cost_var_lst))
    b.eq_LCOW = Constraint(
        expr=b.LCOW == (b.investment_cost_total * self.costing_param.factor_capital_annualization
                        + b.operating_cost_total) / (self.annual_water_production / (pyunits.m ** 3 / pyunits.year)))


def _make_vars(self):
    # build generic costing variables (all costing models need these vars)
    self.capital_cost = Var(initialize=1e5,
                            domain=NonNegativeReals,
                            doc='Unit capital cost [$]')
    self.operating_cost = Var(initialize=1e5,
                              domain=Reals,
                              bounds=(0, 1e6),
                              doc='Unit operating cost [$/year]')


def ReverseOsmosis_costing(self):
    _make_vars(self)

    b_RO = self.parent_block()
    b_fs = b_RO.parent_block()

    # capital cost
    self.eq_capital_cost = Constraint(
        expr=self.capital_cost == b_fs.costing_param.RO_mem_cost * b_RO.area / pyunits.m ** 2)

    # operating cost
    self.eq_operating_cost = Constraint(
        expr=self.operating_cost == b_fs.costing_param.factor_membrane_replacement
             * b_fs.costing_param.RO_mem_cost * b_RO.area / pyunits.m ** 2)


def Nanofiltration_costing(self):
    ''' This method is being added for the nanofiltration step in the pre-treatment section of the full treatment train'''

    _make_vars(self)

    b_NF = self.parent_block()
    b_fs = b_NF.parent_block()

    # capital cost
    self.eq_capital_cost = Constraint(
        expr=self.capital_cost == b_fs.costing_param.NF_mem_cost * b_NF.area / pyunits.m ** 2)

    # operating cost
    self.eq_operating_cost = Constraint(
        expr=self.operating_cost == b_fs.costing_param.factor_membrane_replacement
             * b_fs.costing_param.NF_mem_cost * b_NF.area / pyunits.m ** 2)

#TODO: could attach to equilibrium reactor in chlorination step, but eq reactor currently has no get_costing method
def Chlorination_costing(self):
    ''' This method is being added for the chlorination step in the post-treatment section of the full treatment train'''
    _make_vars(self)

    b_chlorination = self.parent_block()
    b_fs = b_chlorination.parent_block()

    # capital cost
    #TODO: WaterTAP cites a table from Texas Water Development Board for determining capex of a hypochlorite feed system;
    # implement capex relationship here

    # self.eq_capital_cost = Constraint(
    #     expr=self.capital_cost == )

    # self.eq_operating_cost = Constraint(
    #     expr=self.operating_cost == )


#TODO: fill in capex and opex for lime softening in stoichiometric reactor costing
def rstoic_costing(self):
    ''' This method is being added for the softening step in the pre-treatment section of the full treatment train
    (two cost equations still undergoing verification by AAA; "Lime Addition" seems like the better choice):

    (1) "Lime Softening" capex
    https://industrialwatersoftener.com/water-treatment-equipment/industrial-water-softeners/analysis-ion-exchange-vs-lime-softening/

    C_lime=0.0704 * Qin ** 0.7306
    Qin= volumetric flowrate (m3/hr)
    C_lime= $MM

    (2) "Lime Addition" capex
    Capital cost based on McGivney & Kawamura, 2008, and adopted from the WaterTAP conversion
    C_lime = 16972 * S ** 0.5435
    S= volumetric flow rate (m3/hr)
    Clime = $

    '''

    _make_vars(self)

    b_lime = self.parent_block()
    b_fs = b_lime.parent_block()

    # capital cost
    #TODO: may need to touch flow_vol in softener sub-flowsheet; fill in the capex constraint as well once eqn verified

    # self.eq_capital_cost = Constraint(
    #     expr=self.capital_cost == b_lime.control_volume.properties_in[0.0].flow_vol)

    # TODO: add cost of chemical; touch flow_mass_phase_comp['Liq', "Ca(OH)2"] in softener flowsheet
    # self.eq_operating_cost = Constraint(
    #     expr=self.operating_cost == b_lime.control_volume.properties_in[0.0].flow_mass_phase_comp['Liq', 'Ca(OH)2']
    #          * b_fs.costing_param.chemical_lime_cost * 3600 * 8760)

def Separator_costing(self):
    pass

def Mixer_costing(self):
    pass

def PressureExchanger_costing(self):
    _make_vars(self)

    b_PXR = self.parent_block()
    b_fs = b_PXR.parent_block()

    # capital cost
    self.eq_capital_cost = Constraint(
        expr=self.capital_cost == b_fs.costing_param.pxr_cost
             * b_PXR.low_pressure_side.properties_in[0].flow_vol * 3600 / (pyunits.m ** 3 / pyunits.s))

    # operating cost
    self.operating_cost.fix(0)


def pressure_changer_costing(self, pump_type="centrifugal"):
    _make_vars(self)

    b_PC = self.parent_block()
    b_fs = b_PC.parent_block()

    self.purchase_cost = Var()
    self.cp_cost_eq = Constraint(expr=self.purchase_cost == 0)

    if pump_type == 'High pressure':
        # capital cost
        self.eq_capital_cost = Constraint(
            expr=self.capital_cost == b_fs.costing_param.hp_pump_cost * b_PC.work_mechanical[0] / pyunits.W)

        # operating cost
        self.eq_operating_cost = Constraint(
            expr=self.operating_cost == (b_PC.work_mechanical[0] / pyunits.W
                                         * 3600 * 24 * 365 * b_fs.costing_param.load_factor)
                 * b_fs.costing_param.electricity_cost / 3600 / 1000)

    elif pump_type == 'Pressure exchanger':
        # capital cost
        b_cv_in = b_PC.control_volume.properties_in[0]
        self.eq_capital_cost = Constraint(
            expr=(self.capital_cost == b_fs.costing_param.erd_cost['A']
                  * (sum(b_cv_in.flow_mass_comp[j] / (pyunits.kg / pyunits.s)
                         for j in b_PC.config.property_package.component_list)
                     / (b_cv_in.dens_mass / (pyunits.kg / pyunits.m ** 3)) * 3600) ** 0.58))

        # operating cost
        self.operating_cost.setlb(-1e6)
        self.eq_operating_cost = Constraint(
            expr=self.operating_cost == (b_PC.work_mechanical[0] / pyunits.W
                                         * 3600 * 24 * 365 * b_fs.costing_param.load_factor)
                 * b_fs.costing_param.electricity_cost / 3600 / 1000)