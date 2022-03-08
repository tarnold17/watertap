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
"""
Tests for zero-order aeration basin model
"""
import pytest

from io import StringIO
from pyomo.environ import (
    ConcreteModel, Constraint, value, Var, assert_optimal_termination)
from pyomo.util.check_units import assert_units_consistent

from idaes.core import FlowsheetBlock
from idaes.core.util import get_solver
from idaes.core.util.model_statistics import degrees_of_freedom
from idaes.core.util.testing import initialization_tester

from watertap.unit_models.zero_order import AerationBasinZO
from watertap.core.wt_database import Database
from watertap.core.zero_order_properties import WaterParameterBlock

solver = get_solver()

class TestAerationBasinZO_no_default:
    @pytest.fixture(scope="class")
    def model(self):
        m = ConcreteModel()
        m.db = Database()

        m.fs = FlowsheetBlock(default={"dynamic": False})
        m.fs.params = WaterParameterBlock(
            default={"solute_list": ["viruses_enteric", "bod"]})

        m.fs.unit = AerationBasinZO(default={
            "property_package": m.fs.params,
            "database": m.db})

        m.fs.unit.inlet.flow_mass_comp[0, "H2O"].fix(10)
        m.fs.unit.inlet.flow_mass_comp[0, "viruses_enteric"].fix(1)
        m.fs.unit.inlet.flow_mass_comp[0, "bod"].fix(1)

        return m

    @pytest.mark.unit
    def test_build(self, model):
        assert model.fs.unit.config.database is model.db

        assert isinstance(model.fs.unit.electricity, Var)
        assert isinstance(model.fs.unit.energy_electric_flow_vol_inlet, Var)
        assert isinstance(model.fs.unit.electricity_consumption, Constraint)

    @pytest.mark.component
    def test_load_parameters(self, model):
        data = model.db.get_unit_operation_parameters("aeration_basin")

        model.fs.unit.load_parameters_from_database()

        assert model.fs.unit.recovery_frac_mass_H2O[0].fixed
        assert model.fs.unit.recovery_frac_mass_H2O[0].value == \
            data["recovery_frac_mass_H2O"]["value"]

        for (t, j), v in model.fs.unit.removal_frac_mass_solute.items():
            assert v.fixed
            assert v.value == data["removal_frac_mass_solute"][j]["value"]

        assert model.fs.unit.energy_electric_flow_vol_inlet.fixed
        assert model.fs.unit.energy_electric_flow_vol_inlet.value == data[
            "energy_electric_flow_vol_inlet"]["value"]

    @pytest.mark.component
    def test_degrees_of_freedom(self, model):
        assert degrees_of_freedom(model.fs.unit) == 0

    @pytest.mark.component
    def test_unit_consistency(self, model):
        assert_units_consistent(model.fs.unit)

    @pytest.mark.component
    def test_initialize(self, model):
        initialization_tester(model)

    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    @pytest.mark.component
    def test_solve(self, model):
        results = solver.solve(model)

        # Check for optimal solution
        assert_optimal_termination(results)

    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    @pytest.mark.component
    def test_solution(self, model):
        assert (pytest.approx(1.2e-2, rel=1e-5) ==
                value(model.fs.unit.properties_in[0].flow_vol))
        assert (pytest.approx(83.3333, rel=1e-5) ==
                value(model.fs.unit.properties_in[0].conc_mass_comp["viruses_enteric"]))
        assert (pytest.approx(83.3333, rel=1e-5) ==
                value(model.fs.unit.properties_in[0].conc_mass_comp["bod"]))
        assert (pytest.approx(0.01031, rel=1e-5) ==
                value(model.fs.unit.properties_treated[0].flow_vol))
        assert (pytest.approx(0.9699321, rel=1e-5) ==
                value(model.fs.unit.properties_treated[0].conc_mass_comp["viruses_enteric"]))
        assert (pytest.approx(29.097963, rel=1e-5) ==
                value(model.fs.unit.properties_treated[0].conc_mass_comp["bod"]))
        assert (pytest.approx(0.001690, rel=1e-5) ==
                value(model.fs.unit.properties_byproduct[0].flow_vol))
        assert (pytest.approx(585.798816, rel=1e-5) ==
                value(model.fs.unit.properties_byproduct[0].conc_mass_comp["viruses_enteric"]))
        assert (pytest.approx(414.201183, rel=1e-5) ==
                value(model.fs.unit.properties_byproduct[0].conc_mass_comp["bod"]))
        assert (pytest.approx(17.80995, abs=1e-5) ==
                value(model.fs.unit.electricity[0]))

    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    @pytest.mark.component
    def test_conservation(self, model):
        for j in model.fs.params.component_list:
            assert 1e-6 >= abs(value(
                model.fs.unit.inlet.flow_mass_comp[0, j] -
                model.fs.unit.treated.flow_mass_comp[0, j] -
                model.fs.unit.byproduct.flow_mass_comp[0, j]))

    @pytest.mark.component
    def test_report(self, model):
        stream = StringIO()

        model.fs.unit.report(ostream=stream)

        output = """
====================================================================================
Unit : fs.unit                                                             Time: 0.0
------------------------------------------------------------------------------------
    Unit Performance

    Variables: 

    Key                              : Value   : Fixed : Bounds
                  Electricity Demand :  17.810 : False : (None, None)
               Electricity Intensity : 0.41227 :  True : (None, None)
                Solute Removal [bod] : 0.70000 :  True : (0, None)
    Solute Removal [viruses_enteric] : 0.99000 :  True : (0, None)
                      Water Recovery :  1.0000 :  True : (1e-08, 1.0000001)

------------------------------------------------------------------------------------
    Stream Table
                                         Inlet   Treated  Byproduct
    Volumetric Flowrate                0.012000 0.010310  0.0016900
    Mass Concentration H2O               833.33   969.93 4.7337e-07
    Mass Concentration viruses_enteric   83.333  0.96993     585.80
    Mass Concentration bod               83.333   29.098     414.20
====================================================================================
"""

        assert output in stream.getvalue()

class TestAerationBasinZO_w_default_removal:
    @pytest.fixture(scope="class")
    def model(self):
        m = ConcreteModel()
        m.db = Database()

        m.fs = FlowsheetBlock(default={"dynamic": False})
        m.fs.params = WaterParameterBlock(
            default={"solute_list": ["viruses_enteric", "bod", "foo"]})

        m.fs.unit = AerationBasinZO(default={
            "property_package": m.fs.params,
            "database": m.db})

        m.fs.unit.inlet.flow_mass_comp[0, "H2O"].fix(10)
        m.fs.unit.inlet.flow_mass_comp[0, "viruses_enteric"].fix(1)
        m.fs.unit.inlet.flow_mass_comp[0, "bod"].fix(1)
        m.fs.unit.inlet.flow_mass_comp[0, "foo"].fix(1)

        return m

    @pytest.mark.unit
    def test_build(self, model):
        assert model.fs.unit.config.database == model.db

        assert isinstance(model.fs.unit.electricity, Var)
        assert isinstance(model.fs.unit.energy_electric_flow_vol_inlet, Var)
        assert isinstance(model.fs.unit.electricity_consumption, Constraint)

    @pytest.mark.component
    def test_load_parameters(self, model):
        data = model.db.get_unit_operation_parameters("aeration_basin")

        model.fs.unit.load_parameters_from_database(use_default_removal=True)

        assert model.fs.unit.recovery_frac_mass_H2O[0].fixed
        assert model.fs.unit.recovery_frac_mass_H2O[0].value == \
            data["recovery_frac_mass_H2O"]["value"]

        for (t, j), v in model.fs.unit.removal_frac_mass_solute.items():
            assert v.fixed
            if j == "foo":
                assert v.value == data["default_removal_frac_mass_solute"]["value"]
            else:
                assert v.value == data["removal_frac_mass_solute"][j]["value"]

        assert model.fs.unit.energy_electric_flow_vol_inlet.fixed
        assert model.fs.unit.energy_electric_flow_vol_inlet.value == data[
            "energy_electric_flow_vol_inlet"]["value"]

    @pytest.mark.component
    def test_degrees_of_freedom(self, model):
        assert degrees_of_freedom(model.fs.unit) == 0

    @pytest.mark.component
    def test_unit_consistency(self, model):
        assert_units_consistent(model.fs.unit)

    @pytest.mark.component
    def test_initialize(self, model):
        initialization_tester(model)

    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    @pytest.mark.component
    def test_solve(self, model):
        results = solver.solve(model)

        # Check for optimal solution
        assert_optimal_termination(results)

    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    @pytest.mark.component
    def test_solution(self, model):
        assert (pytest.approx(1.3e-2, rel=1e-5) ==
                value(model.fs.unit.properties_in[0].flow_vol))
        assert (pytest.approx(76.9231, rel=1e-5) ==
                value(model.fs.unit.properties_in[0].conc_mass_comp["viruses_enteric"]))
        assert (pytest.approx(76.9231, rel=1e-5) ==
                value(model.fs.unit.properties_in[0].conc_mass_comp["bod"]))
        assert (pytest.approx(76.9231, rel=1e-5) ==
                value(model.fs.unit.properties_in[0].conc_mass_comp["foo"]))
        assert (pytest.approx(0.01131, rel=1e-5) ==
                value(model.fs.unit.properties_treated[0].flow_vol))
        assert (pytest.approx(0.884173, rel=1e-5) ==
                value(model.fs.unit.properties_treated[0].conc_mass_comp["viruses_enteric"]))
        assert (pytest.approx(26.52519, rel=1e-5) ==
                value(model.fs.unit.properties_treated[0].conc_mass_comp["bod"]))
        assert (pytest.approx(88.417, rel=1e-5) ==
                value(model.fs.unit.properties_treated[0].conc_mass_comp["foo"]))
        assert (pytest.approx(0.0016900, rel=1e-5) ==
                value(model.fs.unit.properties_byproduct[0].flow_vol))
        assert (pytest.approx(585.798, rel=1e-5) ==
                value(model.fs.unit.properties_byproduct[0].conc_mass_comp["viruses_enteric"]))
        assert (pytest.approx(414.20, rel=1e-5) ==
                value(model.fs.unit.properties_byproduct[0].conc_mass_comp["bod"]))
        assert (pytest.approx(4.7337e-07, rel=1e-5) ==
                value(model.fs.unit.properties_byproduct[0].conc_mass_comp["foo"]))
        assert (pytest.approx(19.29411198, abs=1e-5) ==
                value(model.fs.unit.electricity[0]))

    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    @pytest.mark.component
    def test_conservation(self, model):
        for j in model.fs.params.component_list:
            assert 1e-6 >= abs(value(
                model.fs.unit.inlet.flow_mass_comp[0, j] -
                model.fs.unit.treated.flow_mass_comp[0, j] -
                model.fs.unit.byproduct.flow_mass_comp[0, j]))

    @pytest.mark.component
    def test_report(self, model):
        stream = StringIO()

        model.fs.unit.report(ostream=stream)

        output = """
====================================================================================
Unit : fs.unit                                                             Time: 0.0
------------------------------------------------------------------------------------
    Unit Performance

    Variables: 

    Key                              : Value   : Fixed : Bounds
                  Electricity Demand :  19.294 : False : (None, None)
               Electricity Intensity : 0.41227 :  True : (None, None)
                Solute Removal [bod] : 0.70000 :  True : (0, None)
                Solute Removal [foo] :  0.0000 :  True : (0, None)
    Solute Removal [viruses_enteric] : 0.99000 :  True : (0, None)
                      Water Recovery :  1.0000 :  True : (1e-08, 1.0000001)

------------------------------------------------------------------------------------
    Stream Table
                                         Inlet   Treated  Byproduct
    Volumetric Flowrate                0.013000 0.011310  0.0016900
    Mass Concentration H2O               769.23   884.17 4.7337e-07
    Mass Concentration viruses_enteric   76.923  0.88417     585.80
    Mass Concentration bod               76.923   26.525     414.20
    Mass Concentration foo               76.923   88.417 4.7337e-07
====================================================================================
"""

        assert output in stream.getvalue()

db = Database()
params = db._get_technology("aeration_basin")


class Test_AerationBasin_ZOsubtype:
    @pytest.fixture(scope="class")
    def model(self):
        m = ConcreteModel()

        m.fs = FlowsheetBlock(default={"dynamic": False})
        m.fs.params = WaterParameterBlock(
            default={"solute_list": ["viruses_enteric"]})

        m.fs.unit = AerationBasinZO(default={
            "property_package": m.fs.params,
            "database": db})

        return m

    @pytest.mark.parametrize("subtype", [params.keys()])
    @pytest.mark.component
    def test_load_parameters(self, model, subtype):
        model.fs.unit.config.process_subtype = subtype
        data = db.get_unit_operation_parameters("aeration_basin", subtype=subtype)

        model.fs.unit.load_parameters_from_database()

        for (t, j), v in model.fs.unit.removal_frac_mass_solute.items():
            assert v.fixed
            assert v.value == data["removal_frac_mass_solute"][j]["value"]