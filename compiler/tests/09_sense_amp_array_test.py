#!/usr/bin/env python3
# See LICENSE for licensing information.
#
# Copyright (c) 2016-2019 Regents of the University of California and The Board
# of Regents for the Oklahoma Agricultural and Mechanical College
# (acting for and on behalf of Oklahoma State University)
# All rights reserved.
#
"""
Run a regression test on a sense amp array
"""

import unittest
from testutils import *
import sys,os
sys.path.append(os.getenv("OPENRAM_HOME"))
import globals
from globals import OPTS
from sram_factory import factory
import debug

class sense_amp_test(openram_test):

    def runTest(self):
        globals.init_openram("config_{0}".format(OPTS.tech_name))

        # check sense amp array for single port
        debug.info(2, "Testing sense_amp_array for word_size=4, words_per_row=2")
        a = factory.create(module_type="sense_amp_array", word_size=4, words_per_row=2)
        self.local_check(a)

        debug.info(2, "Testing sense_amp_array for word_size=4, words_per_row=4")
        a = factory.create(module_type="sense_amp_array", word_size=4, words_per_row=4)
        self.local_check(a)
        
        # check sense amp array for multi-port
        OPTS.bitcell = "pbitcell"
        OPTS.num_rw_ports = 1
        OPTS.num_w_ports = 0
        OPTS.num_r_ports = 0

        factory.reset()
        debug.info(2, "Testing sense_amp_array for word_size=4, words_per_row=2 (multi-port case)")
        a = factory.create(module_type="sense_amp_array", word_size=4, words_per_row=2)
        self.local_check(a)

        debug.info(2, "Testing sense_amp_array for word_size=4, words_per_row=4 (multi-port case)")
        a = factory.create(module_type="sense_amp_array", word_size=4, words_per_row=4)
        self.local_check(a)
        
        globals.end_openram()
        
# run the test from the command line
if __name__ == "__main__":
    (OPTS, args) = globals.parse_args()
    del sys.argv[1:]
    header(__file__, OPTS.tech_name)
    unittest.main(testRunner=debugTestRunner())
