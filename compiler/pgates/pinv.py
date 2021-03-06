# See LICENSE for licensing information.
#
# Copyright (c) 2016-2019 Regents of the University of California and The Board
# of Regents for the Oklahoma Agricultural and Mechanical College
# (acting for and on behalf of Oklahoma State University)
# All rights reserved.
#
import contact
import pgate
import debug
from tech import drc, parameter, spice
from vector import vector
from math import ceil
from globals import OPTS
from utils import round_to_grid
import logical_effort
from sram_factory import factory


class pinv(pgate.pgate):
    """
    Pinv generates gds of a parametrically sized inverter. The
    size is specified as the drive size (relative to minimum NMOS) and
    a beta value for choosing the pmos size.  The inverter's cell
    height is usually the same as the 6t library cell and is measured
    from center of rail to rail..  The route_output will route the
    output to the right side of the cell for easier access.
    """

    def __init__(self, name, size=1, beta=parameter["beta"], height=None, route_output=True):

        debug.info(2,
                   "creating pinv structure {0} with size of {1}".format(name,
                                                                         size))
        self.add_comment("size: {}".format(size))

        self.size = size
        self.nmos_size = size
        self.pmos_size = beta * size
        self.beta = beta
        self.route_output = False
        
        pgate.pgate.__init__(self, name, height)

    def create_netlist(self):
        """ Calls all functions related to the generation of the netlist """
        self.add_pins()
        self.determine_tx_mults()
        self.add_ptx()
        self.create_ptx()
        
    def create_layout(self):
        """ Calls all functions related to the generation of the layout """
        self.setup_layout_constants()
        self.place_ptx()
        self.add_well_contacts()
        self.extend_wells()
        self.route_supply_rails()
        self.connect_rails()
        self.route_input_gate(self.pmos_inst,
                              self.nmos_inst,
                              self.output_pos.y,
                              "A",
                              position="farleft")
        self.route_outputs()
        
    def add_pins(self):
        """ Adds pins for spice netlist """
        pin_list = ["A", "Z", "vdd", "gnd"]
        dir_list = ["INPUT", "OUTPUT", "POWER", "GROUND"]
        self.add_pin_list(pin_list, dir_list)

    def determine_tx_mults(self):
        """
        Determines the number of fingers needed to achieve the size within
        the height constraint. This may fail if the user has a tight height.
        """

        # This may make the result differ when the layout is created...
        if OPTS.netlist_only:
            self.tx_mults = 1
            self.nmos_width = self.nmos_size * drc("minwidth_tx")
            self.pmos_width = self.pmos_size * drc("minwidth_tx")
            return
        
        # Do a quick sanity check and bail if unlikely feasible height
        # Sanity check. can we make an inverter in the height
        # with minimum tx sizes?
        # Assume we need 3 metal 1 pitches (2 power rails, one
        # between the tx for the drain)
        # plus the tx height
        nmos = factory.create(module_type="ptx",
                              tx_type="nmos")
        pmos = factory.create(module_type="ptx",
                              width=drc("minwidth_tx"),
                              tx_type="pmos")
        tx_height = nmos.poly_height + pmos.poly_height
        # rotated m1 pitch or poly to active spacing
        min_channel = max(contact.poly_contact.width + self.m1_space,
                          contact.poly_contact.width + 2 * self.poly_to_active)
        
        # This is the extra space needed to ensure DRC rules
        # to the active contacts
        extra_contact_space = max(-nmos.get_pin("D").by(), 0)
        # This is a poly-to-poly of a flipped cell
        self.top_bottom_space = max(0.5*self.m1_width + self.m1_space + extra_contact_space, 
                                    self.poly_extend_active + self.poly_space)
        total_height = tx_height + min_channel + 2 * self.top_bottom_space

        debug.check(self.height > total_height,
                    "Cell height {0} too small for simple min height {1}.".format(self.height,
                                                                                  total_height))

        # Determine the height left to the transistors to determine
        # the number of fingers
        tx_height_available = self.height - min_channel - 2 * self.top_bottom_space
        # Divide the height in half. Could divide proportional to beta,
        # but this makes connecting wells of multiple cells easier.
        # Subtract the poly space under the rail of the tx
        nmos_height_available = 0.5 * tx_height_available - 0.5 * self.poly_space
        pmos_height_available = 0.5 * tx_height_available - 0.5 * self.poly_space

        debug.info(2,
                   "Height avail {0:.4f} PMOS {1:.4f} NMOS {2:.4f}".format(tx_height_available,
                                                                           nmos_height_available,
                                                                           pmos_height_available))

        # Determine the number of mults for each to fit width
        # into available space
        self.nmos_width = self.nmos_size * drc("minwidth_tx")
        self.pmos_width = self.pmos_size * drc("minwidth_tx")
        nmos_required_mults = max(int(ceil(self.nmos_width / nmos_height_available)), 1)
        pmos_required_mults = max(int(ceil(self.pmos_width / pmos_height_available)), 1)
        # The mults must be the same for easy connection of poly
        self.tx_mults = max(nmos_required_mults, pmos_required_mults)

        # Recompute each mult width and check it isn't too small
        # This could happen if the height is narrow and the size is small
        # User should pick a bigger size to fix it...
        # We also need to round the width to the grid or we will end up
        # with LVS property mismatch errors when fingers are not a grid
        # length and get rounded in the offset geometry.
        self.nmos_width = round_to_grid(self.nmos_width / self.tx_mults)
        debug.check(self.nmos_width >= drc("minwidth_tx"),
                    "Cannot finger NMOS transistors to fit cell height.")
        self.pmos_width = round_to_grid(self.pmos_width / self.tx_mults)
        debug.check(self.pmos_width >= drc("minwidth_tx"),
                    "Cannot finger PMOS transistors to fit cell height.")

    def setup_layout_constants(self):
        """
        Compute the width and height
        """

        # the width is determined the multi-finger PMOS device width plus
        # the well contact width, spacing between them
        # space is for power supply contact to nwell m1 spacing
        self.width = self.pmos.active_offset.x + self.pmos.active_width \
                     + self.active_space + contact.nwell_contact.width \
                     + 0.5 * self.nwell_enclose_active \
                     + self.m1_space
        # This includes full enclosures on each end
        self.well_width = self.width + 2*self.nwell_enclose_active
        # Height is an input parameter, so it is not recomputed.
        
    def add_ptx(self):
        """ Create the PMOS and NMOS transistors. """
        self.nmos = factory.create(module_type="ptx",
                                   width=self.nmos_width,
                                   mults=self.tx_mults,
                                   tx_type="nmos",
                                   connect_poly=True,
                                   connect_active=True)
        self.add_mod(self.nmos)
        
        self.pmos = factory.create(module_type="ptx",
                                   width=self.pmos_width,
                                   mults=self.tx_mults,
                                   tx_type="pmos",
                                   connect_poly=True,
                                   connect_active=True)
        self.add_mod(self.pmos)
        
    def route_supply_rails(self):
        """ Add vdd/gnd rails to the top and bottom. """
        self.add_layout_pin_rect_center(text="gnd",
                                        layer="m1",
                                        offset=vector(0.5 * self.width, 0),
                                        width=self.width)

        self.add_layout_pin_rect_center(text="vdd",
                                        layer="m1",
                                        offset=vector(0.5 * self.width, self.height),
                                        width=self.width)

    def create_ptx(self):
        """
        Create the PMOS and NMOS netlist.
        """
        
        self.pmos_inst = self.add_inst(name="pinv_pmos",
                                       mod=self.pmos)
        self.connect_inst(["Z", "A", "vdd", "vdd"])

        self.nmos_inst = self.add_inst(name="pinv_nmos",
                                      mod=self.nmos)
        self.connect_inst(["Z", "A", "gnd", "gnd"])

    def place_ptx(self):
        """
        Place PMOS and NMOS to the layout at the upper-most and lowest position
        to provide maximum routing in channel
        """
        
        # place PMOS so it is half a poly spacing down from the top
        self.pmos_pos = self.pmos.active_offset.scale(1, 0) \
                        + vector(0,
                                 self.height - self.pmos.active_height - self.top_bottom_space)
        self.pmos_inst.place(self.pmos_pos)

        # place NMOS so that it is half a poly spacing up from the bottom
        self.nmos_pos = self.nmos.active_offset.scale(1, 0) \
                        + vector(0, self.top_bottom_space)
        self.nmos_inst.place(self.nmos_pos)

        # Output position will be in between the PMOS and NMOS drains
        pmos_drain_pos = self.pmos_inst.get_pin("D").ll()
        nmos_drain_pos = self.nmos_inst.get_pin("D").ul()
        self.output_pos = vector(0, 0.5 * (pmos_drain_pos.y + nmos_drain_pos.y))

    def route_outputs(self):
        """
        Route the output (drains) together.
        Optionally, routes output to edge.
        """

        # Get the drain pins
        nmos_drain_pin = self.nmos_inst.get_pin("D")
        pmos_drain_pin = self.pmos_inst.get_pin("D")

        # Pick point at right most of NMOS and connect down to PMOS
        nmos_drain_pos = nmos_drain_pin.bc()
        pmos_drain_pos = vector(nmos_drain_pos.x, pmos_drain_pin.uc().y)
        self.add_path("m1", [nmos_drain_pos, pmos_drain_pos])

        # Remember the mid for the output
        mid_drain_offset = vector(nmos_drain_pos.x, self.output_pos.y)

        if self.route_output:
            # This extends the output to the edge of the cell
            output_offset = mid_drain_offset.scale(0, 1) + vector(self.width, 0)
            self.add_layout_pin_segment_center(text="Z",
                                               layer="m1",
                                               start=mid_drain_offset,
                                               end=output_offset)
        else:
            # This leaves the output as an internal pin (min sized)
            self.add_layout_pin_rect_center(text="Z",
                                            layer="m1",
                                            offset=mid_drain_offset \
                                            + vector(0.5 * self.m1_width, 0))

    def add_well_contacts(self):
        """ Add n/p well taps to the layout and connect to supplies """

        self.add_nwell_contact(self.pmos, self.pmos_pos)

        self.add_pwell_contact(self.nmos, self.nmos_pos)

    def connect_rails(self):
        """ Connect the nmos and pmos to its respective power rails """

        self.connect_pin_to_rail(self.nmos_inst, "S", "gnd")

        self.connect_pin_to_rail(self.pmos_inst, "S", "vdd")
        
    def analytical_power(self, corner, load):
        """Returns dynamic and leakage power. Results in nW"""
        c_eff = self.calculate_effective_capacitance(load)
        freq = spice["default_event_frequency"]
        power_dyn = self.calc_dynamic_power(corner, c_eff, freq)
        power_leak = spice["inv_leakage"]
        
        total_power = self.return_power(power_dyn, power_leak)
        return total_power
        
    def calculate_effective_capacitance(self, load):
        """Computes effective capacitance. Results in fF"""
        c_load = load
        # In fF
        c_para = spice["min_tx_drain_c"] * (self.nmos_size / parameter["min_tx_size"])
        transition_prob = 0.5
        return transition_prob * (c_load + c_para)

    def input_load(self):
        """
        Return the capacitance of the gate connection in generic capacitive
        units relative to the minimum width of a transistor
        """
        return self.nmos_size + self.pmos_size
      
    def get_stage_effort(self, cout, inp_is_rise=True):
        """
        Returns an object representing the parameters for delay in tau units.
        Optional is_rise refers to the input direction rise/fall.
        Input inverted by this stage.
        """
        parasitic_delay = 1
        return logical_effort.logical_effort(self.name,
                                             self.size,
                                             self.input_load(),
                                             cout,
                                             parasitic_delay,
                                             not inp_is_rise)

    def build_graph(self, graph, inst_name, port_nets):
        """
        Adds edges based on inputs/outputs.
        Overrides base class function.
        """
        self.add_graph_edges(graph, port_nets)
