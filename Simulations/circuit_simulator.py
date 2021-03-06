# Copyright (C) 2008  Matthew Neeley
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
### BEGIN NODE INFO
[info]
name = Circuit Simulator
version = 1.0
description = Simple time-domain simulations of superconducting circuits.

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 5
### END NODE INFO
"""

from __future__ import with_statement

import time

from numpy import arange, array, sin, cos, hstack, pi, sqrt, zeros
from scipy.optimize import leastsq, fsolve

from labrad.server import LabradServer, setting

from circuitsim import (h, hbar, phi0bar, Circuit, Capacitor, Inductor,
                        Mutual, Junction, Resistor, CurrentBias)
from processtools import new_priority

class CircuitSimulator(LabradServer):
    name = 'Circuit Simulator'
    
    @setting(0, 'New Circuit', nodes='w')
    def new_circuit(self, c, nodes):
        """Create a new circuit with the specified number of nodes."""
        c['circuit'] = Circuit(nodes)

    @setting(10, 'Add Capacitor', label='s', C='v[F]', node1='w', node2='w')
    def add_capacitor(self, c, label, C, node1, node2=None):
        """Add a capacitor to the current circuit.
        
        If node2 is not specified, GND will be used.
        """
        c['circuit'][label] = Capacitor(float(C), node1, node2)
        
    @setting(11, 'Add Junction', label='s', I0='v[A]', node1='w', node2='w')
    def add_junction(self, c, label, I0, node1, node2=None):
        """Add a junction to the current circuit.
        
        If node2 is not specified, GND will be used.
        """
        c['circuit'][label] = Junction(float(I0), node1, node2)
        
    @setting(12, 'Add Inductor', label='s', L='v[H]', bias='v[]', node1='w', node2='w')
    def add_inductor(self, c, label, L, bias, node1, node2=None):
        """Add an inductor to the current circuit.
        
        If node2 is not specified, GND will be used.
        Bias is specified in units of phase, so that
        one flux quantum corresponds to bias = 2*pi.
        """
        c['circuit'][label] = Inductor(float(L), node1, node2, bias)
    
    @setting(13, 'Add Mutual', label='s', M='v[H]', L1='s', L2='s')
    def add_mutual(self, c, label, M, L1, L2):
        """Add a mutual inductance to the current circuit.
        
        The mutual inductance M is added between two
        existing inductors with labels L1 and L2.
        """
        L1 = c['circuit'][L1]
        L2 = c['circuit'][L2]
        c['circuit'][label] = Mutual(float(M), L1.L, L2.L, i=L1.i, j=L1.j, k=L2.i, l=L2.j)
    
    @setting(14, 'Add Resistor', label='s', R='v[Ohm]', node1='w', node2='w')
    def add_resistor(self, c, label, R, node1, node2=None):
        """Add a resistor to the current circuit.
        
        If node2 is not specified, GND will be used.
        """
        c['circuit'][label] = Resistor(float(R), node1, node2)
        
    @setting(15, 'Add Current Bias', label='s', I='v[A]', node='w')
    def add_current_bias(self, c, label, I, node):
        """Add a current bias to the current circuit."""
        c['circuit'][label] = CurrentBias(I, node)
    
    @setting(100, 'Time', T=['*v[s]', 'v[s]v[s]v[s]'], returns=['', '*v[s]'])
    def time(self, c, T=None):
        """Set or get the time for the circuit simulation.
        
        The time can be specified as an explicit list, or
        as a tuple of start, stop, and step.  If nothing
        is passed in, the current time setting will be returned
        as an explicit list of values.
        """
        if T is None:
            return c['T']
        else:
            if isinstance(T, tuple):
                c['T'] = arange(float(T[0]), float(T[1]), float(T[2]))
            else:
                c['T'] = T.asarray
    
    @setting(101, 'Delta', d0='*v[]', returns=['', '*v[]'])
    def delta(self, c, d0=None):
        """Set or get the initial node phases for the circuit simulation."""
        if d0 is None:
            return c['d0']
        else:
            c['d0'] = d0.asarray
    
    @setting(102, 'Delta Dot', dd0='*v[s^-1]', returns=['', '*v[s^-1]'])
    def delta_dot(self, c, dd0=None):
        """Set or get the initial node phase derivs for the circuit simulation.
        
        This parameter does not need to be specified to run a simulation.
        If it is not specified, the initial phase derivs will be set to 0.
        """
        if dd0 is None:
            return c['dd0']
        else:
            c['dd0'] = dd0.asarray
    
    @setting(103, 'Solve Initial Condition', returns='*v[]')
    def solve_initial_condition(self, c):
        """Solve for the initial condition to make d(d0)/dt = 0.
        
        This uses the current value of d0 as a guess to find an
        initial condition with derivs = 0 (a fixed point).
        The solution found will be set as the new initial condition
        and also returned.
        """
        c['d0'] = leastsq(c['circuit'].deriv, c['d0'])[0]
        return c['d0']
    
    @setting(104, 'Perturb Initial Condition', d0_offset='*v[]', returns='*v[]')
    def perturb_initial_condition(self, c, d0_offset):
        """Adds the specified perturbation to the current initial condition."""
        c['d0'] += d0_offset.asarray
        return c['d0']
    
    @setting(200, 'Simulate', returns='v[s]')
    def simulate(self, c):
        """Run the circuit simulation.
        
        Returns the time it took to run the simulation.
        """
        start = time.time()
        c['circuit'].simulate(c['T'], c['d0'], c.get('dd0', None))
        end = time.time()
        return end - start
        
    
    @setting(300, 'Get', component='s', parameter='s')
    def get_sim_result(self, c, component, parameter):
        """Get parameters and simulation results.
        
        Retrieve the value of a parameter for a particular circuit component,
        as a function of time.  For all components, you can get 'energy', for
        most the 'phase' is also available, as is 'current'.

        In addition, you can get circuit parameters which are not functions
        of time, such as inductance ('L'), capacitance ('C'), etc. 
        """
        circuit = c['circuit']
        p = getattr(circuit[component], parameter)
        if callable(p):
            p = p(circuit)
        return p
    
    @setting(301, 'Energy', returns='*v[J]')
    def energy(self, c):
        """Get the total energy as a function of time.

        Returns the energy as a function of time for the
        last simulation run.
        """
        return c['circuit'].energy()
    


    # functions to calculate things about the qubit potential shape

    def qubit_energies(self, c, I0, L, bias, C):
        EJ = phi0bar * I0
        EL = phi0bar**2 / L / 2
        EC = phi0bar**2 * C / 2
        return EJ, EL, EC
    
    def qubit_U(self, c, I0, L, bias, C):
        EJ, EL, EC = self.qubit_energies(c, I0, L, bias, C)
        return lambda delta: EL*(delta - bias)**2 - EJ*cos(delta)
    
    def qubit_dU(self, c, I0, L, bias, C):
        EJ, EL, EC = self.qubit_energies(c, I0, L, bias, C)
        return lambda delta: 2*EL*(delta - bias) + EJ*sin(delta)
    
    def qubit_d2U(self, c, I0, L, bias, C):
        EJ, EL, EC = self.qubit_energies(c, I0, L, bias, C)
        return lambda delta: 2*EL + EJ*cos(delta)
    
    @setting(500, 'Qubit Extrema', I0='v[A]', L='v[H]', bias='v[]', C='v[F]')
    def qubit_extrema(self, c, I0, L, bias, C):
        """Calculates the extrema in a qubit potential.

        Returns the phases found by solving for dU/dphi = 0, starting
        with initial guesses phi = 0, phi = pi and phi = 2*pi.
        """
        I0, L, bias, C = float(I0), float(L), float(bias), float(C)
        dU = self.qubit_dU(c, I0, L, bias, C)
        return array([fsolve(dU, 0), fsolve(dU, pi), fsolve(dU, 2*pi)])
    
    @setting(501, 'Plasma Frequency', I0='v[A]', L='v[H]', bias='v[]', C='v[F]')
    def plasma_frequency(self, c, I0, L, bias, C):
        """Calculates the plasma frequencies in the two qubit wells.

        First solves for qubit extrema, interpreting these as left well,
        barrier, and right well.  Then evaluates the plasma frequency
        in the left and right wells.
        """
        I0, L, bias, C = float(I0), float(L), float(bias), float(C)
        EC = phi0bar**2 * C / 2
        d2U = self.qubit_d2U(c, I0, L, bias, C)
        left, barrier, right = self.qubit_extrema(c, I0, L, bias, C)
        return array([sqrt(d2U(left)/EC/2), sqrt(d2U(right)/EC/2)])
    
    @setting(502, 'Barrier Height', I0='v[A]', L='v[H]', bias='v[]', C='v[F]')
    def barrier_height(self, c, I0, L, bias, C):
        """Calculates the barrier height in a qubit potential.

        First solves for qubit extrema, interpreting these as left well,
        barrier, and right well.  Then calculates U(barrier) - U(left) and
        U(barrier) - U(right).
        """
        I0, L, bias, C = float(I0), float(L), float(bias), float(C)
        U = self.qubit_U(c, I0, L, bias, C)
        left, barrier, right = self.qubit_extrema(c, I0, L, bias, C)
        return array([U(barrier) - U(left), U(barrier) - U(right)])
    
    @setting(503, 'One Photon Offset', I0='v[A]', L='v[H]', bias='v[]', C='v[F]')
    def one_photon_offset(self, c, I0, L, bias, C):
        """Calculates the phase displacement for one photon of energy.

        This displacement can be used with perturb_initial_condition to
        put one photon of energy into a qubit.
        """
        I0, L, bias, C = float(I0), float(L), float(bias), float(C)
        d2U = self.qubit_d2U(c, I0, L, bias, C)
        left, barrier, right = self.qubit_extrema(c, I0, L, bias, C)
        d = array([left, right])
        wp = self.plasma_frequency(c, I0, L, bias, C)
        return sqrt(2*hbar*wp/d2U(d))


__server__ = CircuitSimulator()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
