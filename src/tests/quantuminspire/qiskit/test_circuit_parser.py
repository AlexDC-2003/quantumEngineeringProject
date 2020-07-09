""" Quantum Inspire SDK

Copyright 2018 QuTech Delft

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import unittest
from unittest.mock import Mock

import numpy as np
import qiskit
from qiskit import QuantumRegister, ClassicalRegister, QuantumCircuit
from qiskit.compiler import assemble, transpile
from qiskit.circuit import Instruction
from qiskit.assembler.run_config import RunConfig
from qiskit.qobj import QobjHeader
from quantuminspire.qiskit.circuit_parser import CircuitToString
from quantuminspire.qiskit.backend_qx import QuantumInspireBackend
from quantuminspire.exceptions import ApiError


class TestQiCircuitToString(unittest.TestCase):

    def test_generate_cqasm_with_entangle_algorithm(self):
        q = QuantumRegister(2)
        b = ClassicalRegister(2)
        circuit = QuantumCircuit(q, b)

        circuit.h(q[0])
        circuit.cx(q[0], q[1])
        circuit.measure(q[0], b[0])
        circuit.measure(q[1], b[1])

        backend = QuantumInspireBackend(Mock(), Mock())
        # transpiling the circuits using the transpiler_config
        new_circuits = transpile(circuit, backend)
        run_config = RunConfig(shots=1024, max_credits=10, memory=False)
        # assembling the circuits into a qobj to be run on the backend
        qiskit_job = assemble(new_circuits, backend, run_config=run_config.to_dict())

        experiment = qiskit_job.experiments[0]
        result = backend._generate_cqasm(experiment)
        expected = "version 1.0\n" \
                   "# cQASM generated by QI backend for Qiskit\n" \
                   "qubits 2\n" \
                   "H q[0]\n" \
                   "CNOT q[0], q[1]\n"
        self.assertEqual(result, expected)

    @staticmethod
    def _generate_cqasm_from_instructions(instructions, number_of_qubits=2, full_state_projection=True):
        experiment_dict = {'instructions': instructions,
                           'header': {'n_qubits': number_of_qubits,
                                      'number_of_clbits': number_of_qubits,
                                      'compiled_circuit_qasm': ''},
                           'config': {'coupling_map': 'all-to-all',
                                      'basis_gates': 'x,y,z,h,rx,ry,rz,s,cx,ccx,u1,u2,u3,id,snapshot',
                                      'n_qubits': number_of_qubits}}
        experiment = qiskit.qobj.QasmQobjExperiment.from_dict(experiment_dict)
        for instruction in experiment.instructions:
            if hasattr(instruction, 'params'):
                # convert params to params used in qiskit instructions
                qiskit_instruction = Instruction('dummy', 0, 0, instruction.params)
                instruction.params = qiskit_instruction.params

        simulator = QuantumInspireBackend(Mock(), Mock())
        result = simulator._generate_cqasm(experiment, full_state_projection)
        return result

    def test_generate_cqasm_correct_output_controlled_z(self):
        instructions = [{'name': 'cz', 'qubits': [0, 1]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('CZ q[0], q[1]\n' in result)

    def test_generate_cqasm_correct_output_conditional_controlled_z(self):
        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 1, 'relation': '==', 'val': '0xE'},
                        {'conditional': 1, 'name': 'cz', 'qubits': [0, 1]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[0]\nC-CZ b[0:3], q[0], q[1]\nnot b[0]\n' in result)

    def test_generate_cqasm_correct_output_controlled_not(self):
        instructions = [{'name': 'cx', 'qubits': [0, 1]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('CNOT q[0], q[1]\n' in result)

    def test_generate_cqasm_correct_output_conditional_controlled_not(self):
        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 1, 'relation': '==', 'val': '0xE'},
                        {'conditional': 1, 'name': 'cx', 'qubits': [0, 1]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[0]\nC-CNOT b[0:3], q[0], q[1]\nnot b[0]\n' in result)

    def test_generate_cqasm_correct_output_toffoli(self):
        instructions = [{'name': 'ccx', 'qubits': [0, 1, 2]}]
        result = self._generate_cqasm_from_instructions(instructions, number_of_qubits=3)
        self.assertTrue('Toffoli q[0], q[1], q[2]\n' in result)

    def test_generate_cqasm_correct_output_conditional_toffoli(self):
        instructions = [{'mask': '0xFF', 'name': 'bfunc', 'register': 2, 'relation': '==', 'val': '0xE'},
                        {'conditional': 2, 'name': 'ccx', 'qubits': [0, 1, 2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[0,4,5,6,7]\nC-Toffoli b[0:7], q[0], q[1], q[2]\nnot b[0,4,5,6,7]\n' in result)

    def test_generate_cqasm_correct_output_measure(self):
        instructions = [{'memory': [0], 'name': 'measure', 'qubits': [0]}]
        result = self._generate_cqasm_from_instructions(instructions, 3)
        measure_line = 'measure q[0]\n'
        self.assertTrue(measure_line not in result)

    def test_generate_cqasm_correct_output_measure_q0_non_fsp(self):
        instructions = [{'memory': [0], 'name': 'measure', 'qubits': [0]}]
        result = self._generate_cqasm_from_instructions(instructions, 3, False)
        measure_line = 'measure q[0]\n'
        self.assertTrue(measure_line in result)

    def test_generate_cqasm_correct_output_measure_q1_non_fsp(self):
        instructions = [{'memory': [0], 'name': 'measure', 'qubits': [1]}]
        result = self._generate_cqasm_from_instructions(instructions, 3, False)
        measure_line = 'measure q[1]\n'
        self.assertTrue(measure_line in result)

    def test_generate_cqasm_correct_output_hadamard(self):
        instructions = [{'name': 'h', 'qubits': [0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('H q[0]\n' in result)

    def test_generate_cqasm_correct_output_conditional_hadamard(self):
        instructions = [{'mask': '0xFF', 'name': 'bfunc', 'register': 3, 'relation': '==', 'val': '0xE'},
                        {'conditional': 3, 'name': 'h', 'qubits': [0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[0,4,5,6,7]\nC-H b[0:7], q[0]\nnot b[0,4,5,6,7]\n' in result)

    def test_generate_cqasm_correct_output_barrier(self):
        instructions = [{'name': 'barrier', 'qubits': [0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertFalse('barrier' in result)

    def test_generate_cqasm_correct_output_conditional_barrier(self):
        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 4, 'relation': '==', 'val': '0xE'},
                        {'conditional': 4, 'name': 'barrier', 'qubits': [0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertFalse('barrier' in result)

    def test_generate_cqasm_correct_output_identity(self):
        instructions = [{'name': 'id', 'qubits': [0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('I q[0]\n' in result)

    def test_generate_cqasm_correct_output_conditional_identity(self):
        instructions = [{'mask': '0xFF', 'name': 'bfunc', 'register': 5, 'relation': '==', 'val': '0xE'},
                        {'conditional': 5, 'name': 'id', 'qubits': [0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[0,4,5,6,7]\nC-I b[0:7], q[0]\nnot b[0,4,5,6,7]\n' in result)

    def test_generate_cqasm_correct_output_gate_s(self):
        instructions = [{'name': 's', 'qubits': [1]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('S q[1]\n' in result)

    def test_generate_cqasm_correct_output_conditional_gate_s(self):
        instructions = [{'mask': '0x1FF', 'name': 'bfunc', 'register': 5, 'relation': '==', 'val': '0xB'},
                        {'conditional': 5, 'name': 's', 'qubits': [2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[2,4,5,6,7,8]\nC-S b[0:8], q[2]\nnot b[2,4,5,6,7,8]\n' in result)

    def test_generate_cqasm_correct_output_gate_sdag(self):
        instructions = [{'name': 'sdg', 'qubits': [2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Sdag q[2]\n' in result)

    def test_generate_cqasm_correct_output_conditional_gate_sdag(self):
        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 6, 'relation': '==', 'val': '0xE'},
                        {'conditional': 6, 'name': 'sdg', 'qubits': [0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[0]\nC-Sdag b[0:3], q[0]\nnot b[0]\n' in result)

    def test_generate_cqasm_correct_output_gate_swap(self):
        instructions = [{'name': 'swap', 'qubits': [2, 3]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('SWAP q[2], q[3]\n' in result)

    def test_generate_cqasm_correct_output_conditional_gate_swap(self):
        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 7, 'relation': '==', 'val': '0xE'},
                        {'conditional': 7, 'name': 'swap', 'qubits': [0, 1]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[0]\nC-SWAP b[0:3], q[0], q[1]\nnot b[0]\n' in result)

    def test_generate_cqasm_correct_output_gate_t(self):
        instructions = [{'name': 't', 'qubits': [2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('T q[2]\n' in result)

    def test_generate_cqasm_correct_output_conditional_gate_t(self):
        instructions = [{'mask': '0x1FF', 'name': 'bfunc', 'register': 8, 'relation': '==', 'val': '0xB'},
                        {'conditional': 8, 'name': 't', 'qubits': [1]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[2,4,5,6,7,8]\nC-T b[0:8], q[1]\nnot b[2,4,5,6,7,8]\n' in result)

    def test_generate_cqasm_correct_output_gate_tdag(self):
        instructions = [{'name': 'tdg', 'qubits': [2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Tdag q[2]\n' in result)

    def test_generate_cqasm_correct_output_conditional_gate_tdag(self):
        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 9, 'relation': '==', 'val': '0xE'},
                        {'conditional': 9, 'name': 'tdg', 'qubits': [0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[0]\nC-Tdag b[0:3], q[0]\nnot b[0]\n' in result)

    def test_generate_cqasm_correct_output_gate_x(self):
        instructions = [{'name': 'x', 'qubits': [0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('X q[0]\n' in result)

    def test_generate_cqasm_correct_output_conditional_gate_x(self):
        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 9, 'relation': '==', 'val': '0xE'},
                        {'conditional': 9, 'name': 'x', 'qubits': [0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[0]\nC-X b[0:3], q[0]\nnot b[0]\n' in result)

    def test_generate_cqasm_correct_output_gate_y(self):
        instructions = [{'name': 'y', 'qubits': [0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Y q[0]\n' in result)

    def test_generate_cqasm_correct_output_conditional_gate_y(self):
        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 9, 'relation': '==', 'val': '0x1'},
                        {'conditional': 9, 'name': 'y', 'qubits': [0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[1,2,3]\nC-Y b[0:3], q[0]\nnot b[1,2,3]\n' in result)

    def test_generate_cqasm_correct_output_gate_z(self):
        instructions = [{'name': 'z', 'qubits': [0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Z q[0]\n' in result)

    def test_generate_cqasm_correct_output_conditional_gate_z(self):
        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 9, 'relation': '==', 'val': '0x3'},
                        {'conditional': 9, 'name': 'z', 'qubits': [0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[2,3]\nC-Z b[0:3], q[0]\nnot b[2,3]\n' in result)

    def test_generate_cqasm_correct_output_gate_u(self):
        instructions = [{'name': 'u', 'qubits': [0], 'params': [0, 0, np.pi / 2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Rz q[0], 1.570796\n' in result)

        instructions = [{'name': 'u', 'qubits': [0], 'params': [-np.pi / 2, 0, 0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Ry q[0], -1.570796\n' in result)

        instructions = [{'name': 'u', 'qubits': [0], 'params': [np.pi / 4, np.pi / 2, -np.pi / 2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Rz q[0], -1.570796\nRy q[0], 0.785398\nRz q[0], 1.570796\n' in result)

        instructions = [{'name': 'u', 'qubits': [1], 'params': [0.123456, 0.654321, -0.333333]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Rz q[1], -0.333333\nRy q[1], 0.123456\nRz q[1], 0.654321\n' in result)

    def test_generate_cqasm_correct_output_conditional_gate_u(self):
        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 10, 'relation': '==', 'val': '0x3'},
                        {'conditional': 10, 'name': 'u', 'qubits': [0], 'params': [0, 0, np.pi / 2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[2,3]\nC-Rz b[0:3], q[0], 1.570796\nnot b[2,3]\n' in result)

        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 10, 'relation': '==', 'val': '0x3'},
                        {'conditional': 10, 'name': 'u', 'qubits': [0], 'params': [-np.pi / 2, 0, 0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[2,3]\nC-Ry b[0:3], q[0], -1.570796\nnot b[2,3]' in result)

        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 10, 'relation': '==', 'val': '0x3'},
                        {'conditional': 10, 'name': 'u', 'qubits': [0], 'params': [np.pi / 4, np.pi / 2, -np.pi / 2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[2,3]\nC-Rz b[0:3], q[0], -1.570796\nC-Ry b[0:3], q[0], 0.785398\nC-Rz b[0:3],'
                        ' q[0], 1.570796\nnot b[2,3]\n' in result)

        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 10, 'relation': '==', 'val': '0x3'},
                        {'conditional': 10, 'name': 'u', 'qubits': [1], 'params': [0.123456, 0.654321, -0.333333]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[2,3]\nC-Rz b[0:3], q[1], -0.333333\nC-Ry b[0:3], q[1], 0.123456\nC-Rz b[0:3],'
                        ' q[1], 0.654321\nnot b[2,3]\n' in result)

    def test_generate_cqasm_correct_output_gate_u1(self):
        instructions = [{'name': 'u1', 'qubits': [0], 'params': [np.pi / 2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Rz q[0], 1.570796\n' in result)

        instructions = [{'name': 'u1', 'qubits': [1], 'params': [np.pi / 4]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Rz q[1], 0.785398\n' in result)

        instructions = [{'name': 'u1', 'qubits': [2], 'params': [-np.pi / 4]}]
        result = self._generate_cqasm_from_instructions(instructions, 3)
        self.assertTrue('Rz q[2], -0.785398\n' in result)

        instructions = [{'name': 'u1', 'qubits': [2], 'params': [0.123456]}]
        result = self._generate_cqasm_from_instructions(instructions, 3)
        self.assertTrue('Rz q[2], 0.123456\n' in result)

        instructions = [{'name': 'u1', 'qubits': [0], 'params': [0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertFalse('q[0]' in result)

    def test_generate_cqasm_correct_output_conditional_gate_u1(self):
        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 11, 'relation': '==', 'val': '0x3'},
                        {'conditional': 11, 'name': 'u1', 'qubits': [0], 'params': [np.pi / 2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[2,3]\nC-Rz b[0:3], q[0], 1.570796\nnot b[2,3]\n' in result)

        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 11, 'relation': '==', 'val': '0x3'},
                        {'conditional': 11, 'name': 'u1', 'qubits': [1], 'params': [np.pi / 4]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[2,3]\nC-Rz b[0:3], q[1], 0.785398\nnot b[2,3]\n' in result)

        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 11, 'relation': '==', 'val': '0x3'},
                        {'conditional': 11, 'name': 'u1', 'qubits': [2], 'params': [-np.pi / 4]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[2,3]\nC-Rz b[0:3], q[2], -0.785398\nnot b[2,3]\n' in result)

        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 11, 'relation': '==', 'val': '0x3'},
                        {'conditional': 11, 'name': 'u1', 'qubits': [2], 'params': [0.123456]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[2,3]\nC-Rz b[0:3], q[2], 0.123456\nnot b[2,3]\n' in result)

        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 11, 'relation': '==', 'val': '0x3'},
                        {'conditional': 11, 'name': 'u1', 'qubits': [0], 'params': [0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertFalse('q[0]' in result)

    def test_generate_cqasm_correct_output_gate_u2(self):
        instructions = [{'name': 'u2', 'qubits': [0], 'params': [np.pi, np.pi / 2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Rz q[0], 1.570796\nRy q[0], 1.570796\nRz q[0], 3.141593\n' in result)

        instructions = [{'name': 'u2', 'qubits': [1], 'params': [0, np.pi]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Rz q[1], 3.141593\nRy q[1], 1.570796\n' in result)

        instructions = [{'name': 'u2', 'qubits': [2], 'params': [0.123456, -0.654321]}]
        result = self._generate_cqasm_from_instructions(instructions, 3)
        self.assertTrue('Rz q[2], -0.654321\nRy q[2], 1.570796\nRz q[2], 0.123456\n' in result)

        instructions = [{'name': 'u2', 'qubits': [0], 'params': [0, 0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Ry q[0], 1.570796\n' in result)

    def test_generate_cqasm_correct_output_conditional_gate_u2(self):
        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 12, 'relation': '==', 'val': '0x3'},
                        {'conditional': 12, 'name': 'u2', 'qubits': [0], 'params': [np.pi, np.pi / 2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[2,3]\nC-Rz b[0:3], q[0], 1.570796\nC-Ry b[0:3], q[0], 1.570796\nC-Rz b[0:3], q[0],'
                        ' 3.141593\nnot b[2,3]\n' in result)

        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 12, 'relation': '==', 'val': '0x3'},
                        {'conditional': 12, 'name': 'u2', 'qubits': [1], 'params': [0, np.pi]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[2,3]\nC-Rz b[0:3], q[1], 3.141593\nC-Ry b[0:3], q[1], 1.570796\nnot b[2,3]\n' in result)

        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 12, 'relation': '==', 'val': '0x3'},
                        {'conditional': 12, 'name': 'u2', 'qubits': [2], 'params': [0.123456, -0.654321]}]
        result = self._generate_cqasm_from_instructions(instructions, 3)
        self.assertTrue('not b[2,3]\nC-Rz b[0:3], q[2], -0.654321\nC-Ry b[0:3], q[2], 1.570796\nC-Rz b[0:3], q[2],'
                        ' 0.123456\nnot b[2,3]\n' in result)

        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 12, 'relation': '==', 'val': '0x3'},
                        {'conditional': 12, 'name': 'u2', 'qubits': [0], 'params': [0, 0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[2,3]\nC-Ry b[0:3], q[0], 1.570796\nnot b[2,3]\n' in result)

    def test_generate_cqasm_correct_output_gate_u3(self):
        instructions = [{'name': 'u3', 'qubits': [0], 'params': [1, 2, 3]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Rz q[0], 3.000000\nRy q[0], 1.000000\nRz q[0], 2.000000\n' in result)

        instructions = [{'name': 'u3', 'qubits': [1], 'params': [0.123456, 0.654321, -0.333333]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Rz q[1], -0.333333\nRy q[1], 0.123456\nRz q[1], 0.654321\n' in result)

        instructions = [{'name': 'u3', 'qubits': [1], 'params': [0, 0.654321, 0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Rz q[1], 0.654321\n' in result)

        instructions = [{'name': 'u3', 'qubits': [2], 'params': [0.654321, 0, 0]}]
        result = self._generate_cqasm_from_instructions(instructions, 3)
        self.assertTrue('Ry q[2], 0.654321\n' in result)

        instructions = [{'name': 'u3', 'qubits': [0], 'params': [0, 0, 0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertFalse('q[0]' in result)

    def test_generate_cqasm_correct_output_conditional_gate_u3(self):
        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 13, 'relation': '==', 'val': '0x3'},
                        {'conditional': 13, 'name': 'u3', 'qubits': [0], 'params': [1, 2, 3]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[2,3]\nC-Rz b[0:3], q[0], 3.000000\nC-Ry b[0:3], q[0], 1.000000\nC-Rz b[0:3], q[0],'
                        ' 2.000000\nnot b[2,3]\n' in result)

        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 13, 'relation': '==', 'val': '0x3'},
                        {'conditional': 13, 'name': 'u3', 'qubits': [1], 'params': [0.123456, 0.654321, -0.333333]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[2,3]\nC-Rz b[0:3], q[1], -0.333333\nC-Ry b[0:3], q[1], 0.123456\nC-Rz b[0:3], q[1],'
                        ' 0.654321\nnot b[2,3]\n' in result)

        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 13, 'relation': '==', 'val': '0x3'},
                        {'conditional': 13, 'name': 'u3', 'qubits': [1], 'params': [0, 0.654321, 0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[2,3]\nC-Rz b[0:3], q[1], 0.654321\nnot b[2,3]\n' in result)

        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 13, 'relation': '==', 'val': '0x3'},
                        {'conditional': 13, 'name': 'u3', 'qubits': [2], 'params': [0.654321, 0, 0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[2,3]\nC-Ry b[0:3], q[2], 0.654321\nnot b[2,3]\n' in result)

        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 13, 'relation': '==', 'val': '0x1'},
                        {'conditional': 13, 'name': 'u3', 'qubits': [0], 'params': [0, 0, 0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertFalse('q[0]' in result)

    def test_generate_cqasm_correct_output_sympy_special_cases(self):
        # Zero
        instructions = [{'name': 'rx', 'qubits': [1], 'params': [0]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Rx q[1], 0.000000\n' in result)

        # One
        instructions = [{'name': 'rx', 'qubits': [1], 'params': [1]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Rx q[1], 1.000000\n' in result)

        # Integer
        instructions = [{'name': 'rx', 'qubits': [1], 'params': [2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Rx q[1], 2.000000\n' in result)

        # NegativeOne
        instructions = [{'name': 'rx', 'qubits': [1], 'params': [-1]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Rx q[1], -1.000000\n' in result)

        # Float
        instructions = [{'name': 'rx', 'qubits': [0], 'params': [np.pi / 2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Rx q[0], 1.570796\n' in result)

    def test_generate_cqasm_correct_output_rotation_x(self):
        instructions = [{'name': 'rx', 'qubits': [0], 'params': [np.pi / 2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Rx q[0], 1.570796\n' in result)

        instructions = [{'name': 'rx', 'qubits': [1], 'params': [0.123456]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Rx q[1], 0.123456\n' in result)

    def test_generate_cqasm_correct_output_conditional_rotation_x(self):
        instructions = [{'mask': '0xFF', 'name': 'bfunc', 'register': 14, 'relation': '==', 'val': '0xE'},
                        {'conditional': 14, 'name': 'rx', 'qubits': [0], 'params': [np.pi / 2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[0,4,5,6,7]\nC-Rx b[0:7], q[0], 1.570796\nnot b[0,4,5,6,7]\n' in result)

        instructions = [{'mask': '0xFF', 'name': 'bfunc', 'register': 14, 'relation': '==', 'val': '0xE'},
                        {'conditional': 14, 'name': 'rx', 'qubits': [1], 'params': [0.123456]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[0,4,5,6,7]\nC-Rx b[0:7], q[1], 0.123456\nnot b[0,4,5,6,7]\n' in result)

    def test_generate_cqasm_correct_output_rotation_y(self):
        instructions = [{'name': 'ry', 'qubits': [0], 'params': [np.pi / 2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Ry q[0], 1.570796\n' in result)

        instructions = [{'name': 'ry', 'qubits': [1], 'params': [0.654321]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Ry q[1], 0.654321\n' in result)

    def test_generate_cqasm_correct_output_conditional_rotation_y(self):
        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 15, 'relation': '==', 'val': '0x3'},
                        {'conditional': 15, 'name': 'ry', 'qubits': [0], 'params': [np.pi / 2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[2,3]\nC-Ry b[0:3], q[0], 1.570796\nnot b[2,3]\n' in result)

        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 15, 'relation': '==', 'val': '0x3'},
                        {'conditional': 15, 'name': 'ry', 'qubits': [1], 'params': [0.654321]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[2,3]\nC-Ry b[0:3], q[1], 0.654321\nnot b[2,3]\n' in result)

    def test_generate_cqasm_correct_output_rotation_z(self):
        instructions = [{'name': 'rz', 'qubits': [0], 'params': [np.pi / 2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Rz q[0], 1.570796\n' in result)

        instructions = [{'name': 'rz', 'qubits': [1], 'params': [-np.pi / 2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('Rz q[1], -1.570796\n' in result)

    def test_generate_cqasm_correct_output_conditional_rotation_z(self):
        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 16, 'relation': '==', 'val': '0x1'},
                        {'conditional': 16, 'name': 'rz', 'qubits': [0], 'params': [np.pi / 2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[1,2,3]\nC-Rz b[0:3], q[0], 1.570796\nnot b[1,2,3]\n' in result)

        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 16, 'relation': '==', 'val': '0x1'},
                        {'conditional': 16, 'name': 'rz', 'qubits': [1], 'params': [-np.pi / 2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[1,2,3]\nC-Rz b[0:3], q[1], -1.570796\nnot b[1,2,3]\n' in result)

    def test_generate_cqasm_correct_output_unknown_gate(self):
        instructions = [{'name': 'bla', 'qubits': [1], 'params': [-np.pi / 2]}]
        self.assertRaisesRegex(ApiError, 'Gate bla not supported', self._generate_cqasm_from_instructions,
                               instructions, 2)

    def test_generate_cqasm_correct_output_unknown_controlled_gate(self):
        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 17, 'relation': '==', 'val': '0x1'},
                        {'conditional': 17, 'name': 'bla', 'qubits': [1], 'params': [-np.pi / 2]}]
        self.assertRaisesRegex(ApiError, 'Conditional gate c-bla not supported',
                               self._generate_cqasm_from_instructions, instructions, 2)

    def test_generate_cqasm_correct_output_no_bit_negation(self):
        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 18, 'relation': '==', 'val': '0xF'},
                        {'conditional': 18, 'name': 'rx', 'qubits': [1], 'params': [-np.pi / 2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('C-Rx b[0:3], q[1], -1.570796\n' in result)
        self.assertFalse('not\n' in result)

    def test_generate_cqasm_correct_output_one_bit_condition(self):
        instructions = [{'mask': '0x1', 'name': 'bfunc', 'register': 19, 'relation': '==', 'val': '0x1'},
                        {'conditional': 19, 'name': 'rx', 'qubits': [1], 'params': [-np.pi / 2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('C-Rx b[0], q[1], -1.570796\n' in result)
        self.assertFalse('not\n' in result)

        instructions = [{'mask': '0x2', 'name': 'bfunc', 'register': 19, 'relation': '==', 'val': '0x2'},
                        {'conditional': 19, 'name': 'rx', 'qubits': [1], 'params': [-np.pi / 2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('C-Rx b[1], q[1], -1.570796\n' in result)
        self.assertFalse('not\n' in result)

        instructions = [{'mask': '0x40', 'name': 'bfunc', 'register': 19, 'relation': '==', 'val': '0x40'},
                        {'conditional': 19, 'name': 'rx', 'qubits': [1], 'params': [-np.pi / 2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('C-Rx b[6], q[1], -1.570796\n' in result)
        self.assertFalse('not\n' in result)

        instructions = [{'mask': '0x40', 'name': 'bfunc', 'register': 19, 'relation': '==', 'val': '0x0'},
                        {'conditional': 19, 'name': 'rx', 'qubits': [1], 'params': [-np.pi / 2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[6]\nC-Rx b[6], q[1], -1.570796\nnot b[6]\n' in result)

    def test_generate_cqasm_correct_output_more_bit_condition(self):
        instructions = [{'mask': '0x38', 'name': 'bfunc', 'register': 20, 'relation': '==', 'val': '0x18'},
                        {'conditional': 20, 'name': 'y', 'qubits': [2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[5]\nC-Y b[3:5], q[2]\nnot b[5]\n' in result)

        instructions = [{'mask': '0xFE', 'name': 'bfunc', 'register': 20, 'relation': '==', 'val': '0x18'},
                        {'conditional': 20, 'name': 'y', 'qubits': [2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[1,2,5,6,7]\nC-Y b[1:7], q[2]\nnot b[1,2,5,6,7]\n' in result)

        instructions = [{'mask': '0xFE', 'name': 'bfunc', 'register': 20, 'relation': '==', 'val': '0x36'},
                        {'conditional': 20, 'name': 'y', 'qubits': [2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[3,6,7]\nC-Y b[1:7], q[2]\nnot b[3,6,7]\n' in result)

        instructions = [{'mask': '0x60', 'name': 'bfunc', 'register': 20, 'relation': '==', 'val': '0x40'},
                        {'conditional': 20, 'name': 'y', 'qubits': [2]}]
        result = self._generate_cqasm_from_instructions(instructions, 2)
        self.assertTrue('not b[5]\nC-Y b[5:6], q[2]\nnot b[5]\n' in result)

    def test_generate_cqasm_correct_output_unknown_type(self):
        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 18, 'relation': '!=', 'val': '0x1'},
                        {'conditional': 18, 'name': 'rx', 'qubits': [1], 'params': [-np.pi / 2]}]
        self.assertRaisesRegex(ApiError, 'Conditional statement with relation != not supported',
                               self._generate_cqasm_from_instructions, instructions, 2)

    def test_generate_cqasm_correct_output_no_mask(self):
        instructions = [{'mask': '0x0', 'name': 'bfunc', 'register': 18, 'relation': '==', 'val': '0x1'},
                        {'conditional': 18, 'name': 'rx', 'qubits': [1], 'params': [-np.pi / 2]}]
        self.assertRaisesRegex(ApiError, 'Conditional statement rx without a mask',
                               self._generate_cqasm_from_instructions, instructions, 2)

    def test_generate_cqasm_register_no_match(self):
        instructions = [{'mask': '0xF', 'name': 'bfunc', 'register': 1, 'relation': '==', 'val': '0x3'},
                        {'conditional': 2, 'name': 'rx', 'qubits': [1], 'params': [-np.pi / 2]}]
        self.assertRaisesRegex(ApiError, 'Conditional not found: reg_idx = 2',
                               self._generate_cqasm_from_instructions, instructions, 2)

    def test_get_mask_data(self):
        mask = 0
        lowest_mask_bit, mask_length = CircuitToString.get_mask_data(mask)
        self.assertEqual(lowest_mask_bit, -1)
        self.assertEqual(mask_length, 0)

        mask = 56
        lowest_mask_bit, mask_length = CircuitToString.get_mask_data(mask)
        self.assertEqual(lowest_mask_bit, 3)
        self.assertEqual(mask_length, 3)

        mask = 1
        lowest_mask_bit, mask_length = CircuitToString.get_mask_data(mask)
        self.assertEqual(lowest_mask_bit, 0)
        self.assertEqual(mask_length, 1)

        mask = 255
        lowest_mask_bit, mask_length = CircuitToString.get_mask_data(mask)
        self.assertEqual(lowest_mask_bit, 0)
        self.assertEqual(mask_length, 8)

        mask = 510
        lowest_mask_bit, mask_length = CircuitToString.get_mask_data(mask)
        self.assertEqual(lowest_mask_bit, 1)
        self.assertEqual(mask_length, 8)

        mask = 128
        lowest_mask_bit, mask_length = CircuitToString.get_mask_data(mask)
        self.assertEqual(lowest_mask_bit, 7)
        self.assertEqual(mask_length, 1)

        mask = 192
        lowest_mask_bit, mask_length = CircuitToString.get_mask_data(mask)
        self.assertEqual(lowest_mask_bit, 6)
        self.assertEqual(mask_length, 2)
