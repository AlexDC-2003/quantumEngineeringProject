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
import io
import json
import uuid
import numpy as np
from collections import defaultdict, OrderedDict, Counter

from coreapi.exceptions import ErrorMessage
from qiskit.providers import BaseBackend
from qiskit.providers.models import BackendConfiguration
from qiskit.providers.models.backendconfiguration import GateConfig
from qiskit.qobj import Qobj, QobjExperiment
from qiskit.result.models import ExperimentResult, ExperimentResultData
from qiskit.validation.base import Obj

from quantuminspire.exceptions import QisKitBackendError
from quantuminspire.qiskit.circuit_parser import CircuitToString
from quantuminspire.qiskit.qi_job import QIJob
from quantuminspire.version import __version__ as quantum_inspire_version


class QuantumInspireBackend(BaseBackend):
    DEFAULT_CONFIGURATION = BackendConfiguration(
        backend_name='qi_simulator',
        backend_version=quantum_inspire_version,
        n_qubits=26,
        basis_gates=['x', 'y', 'z', 'h', 'rx', 'ry', 'rz', 's', 'cx', 'ccx', 'u1', 'u2', 'u3', 'id', 'snapshot'],
        gates=[GateConfig(name='NotUsed', parameters=['NaN'], qasm_def='NaN')],
        conditional=False,
        simulator=True,
        local=False,
        memory=True,
        open_pulse=False,
        max_shots=1024
    )

    def __init__(self, api, provider, configuration=None):
        """ Python implementation of a quantum simulator using Quantum Inspire API.

        Args:
            api (QuantumInspireApi): The interface instance to the Quantum Inspire API.
            provider (QuantumInspireProvider): Provider for this backend.
            configuration (BackendConfiguration, optional): The configuration of the quantum inspire backend. The
                configuration must implement the fields given by the QiSimulatorPy.DEFAULT_CONFIGURATION. All
                configuration fields are listed in the table below. The table rows with an asterisk specify fields which
                can have a custom value and are allowed to be changed according to the description column.

                | key                    | description
                |------------------------|----------------------------------------------------------------------------
                | name (str)*            | The name of the quantum inspire backend. The API can list the name of each
                                            available backend using the function api.list_backend_types(). One of the
                                            listed names must be used.
                | basis_gates (str)      | A comma-separated set of basis gates to compile to.
                | gates (GateConfig):    | List of basis gates on the backend. Not used.
                | conditional (bool)     | Backend supports conditional operations.
                | memory (bool):         | Backend supports memory. True.
                | simulator (bool)       | Specifies whether the backend is a simulator or a quantum system. Not used.
                | local (bool)           | Indicates whether the system is running locally or remotely. Not used.
                | open_pulse (bool)      | Backend supports open pulse. False.
                | max_shots (int)        | Maximum number of shots supported.
        """
        super().__init__(configuration=(configuration or
                                        QuantumInspireBackend.DEFAULT_CONFIGURATION),
                         provider=provider)
        self.__backend = api.get_backend_type_by_name(self.name())
        self.__api = api

    @property
    def backend_name(self):
        return self.name()

    def run(self, qobj):
        """ Submits a quantum job to the Quantum Inspire platform.

        Args:
            qobj (Qobj): The quantum job with the Qiskit algorithm and quantum inspire backend.

        Returns:
            QIJob: A job that has been submitted.
        """
        QuantumInspireBackend.__validate(qobj)
        number_of_shots = qobj.config.shots

        identifier = uuid.uuid1()
        project_name = 'qi-sdk-project-{}'.format(identifier)
        project = self.__api.create_project(project_name, number_of_shots, self.__backend)
        experiments = qobj.experiments
        job = QIJob(self, str(project['id']), self.__api)
        [self._submit_experiment(experiment, number_of_shots, project=project) for experiment in experiments]
        job.experiments = experiments
        return job

    def retrieve_job(self, job_id):
        """ Retrieve a specified job by its job_id.

        Args:
            job_id (str): The job id.

        Returns:
            QIJob: The job that has been retrieved.

        Raises:
            QisKitBackendError: If job not found or error occurs during retrieval of the job.
        """
        try:
            self.__api.get_project(job_id)
        except ErrorMessage:
            raise QisKitBackendError("Could not retrieve job with job_id '{}' ".format(job_id))
        return QIJob(self, job_id, self.__api)

    def _generate_cqasm(self, experiment):
        """ Generates the cQASM from the Qiskit experiment.

        Args:
            experiment (QobjExperiment): The experiment that contains instructions to be converted to cQASM.

        Returns:
            str: The cQASM code that can be sent to the Quantum Inspire API.
        """
        parser = CircuitToString()
        number_of_qubits = experiment.header.n_qubits
        instructions = experiment.instructions
        with io.StringIO() as stream:
            stream.write('version 1.0\n')
            stream.write('# cQASM generated by QI backend for Qiskit\n')
            stream.write('qubits %d\n' % number_of_qubits)
            for instruction in instructions:
                gate_name = '_%s' % instruction.name.lower()
                gate_function = getattr(parser, gate_name)
                line = gate_function(instruction.as_dict())
                if isinstance(line, str):
                    stream.write(line)

            return stream.getvalue()

    def _submit_experiment(self, experiment, number_of_shots, project=None):
        compiled_qasm = self._generate_cqasm(experiment)
        measurements = self._collect_measurements(experiment)
        user_data = {'name': experiment.header.name, 'memory_slots': experiment.header.memory_slots,
                     'creg_sizes': experiment.header.creg_sizes, 'measurements': measurements}
        job_id = self.__api.execute_qasm_async(compiled_qasm, backend_type=self.__backend,
                                               number_of_shots=number_of_shots, project=project,
                                               job_name=experiment.header.name, user_data=json.dumps(user_data))
        return job_id

    def get_experiment_results(self, qi_job):
        """ Get results from experiments from the Quantum-inspire platform.

        Args:
            qi_job (QIJob): A job that has already been submitted and which execution is completed.

        Raises:
            QisKitBackendError: If an error occurred during execution by the backend.

        Returns:
            list: A list of experiment results; containing the data, execution time, status, etc.
        """
        jobs = self.__api.get_jobs_from_project(qi_job.job_id())
        results = [self.__api.get(job['results']) for job in jobs]
        experiment_results = []
        for result, job in zip(results, jobs):
            if not result.get('histogram', {}):
                raise QisKitBackendError(
                    'Result from backend contains no histogram data!\n{}'.format(result.get('raw_text')))

            user_data = json.loads(job.get('user_data'))
            measurements = user_data.pop('measurements')
            histogram_obj, memory_data = self.__convert_result_data(result, measurements)
            full_state_histogram_obj = self.__convert_histogram(result, measurements)
            experiment_result_data = ExperimentResultData(counts=histogram_obj,
                                                          probabilities=full_state_histogram_obj,
                                                          memory=memory_data)
            header = Obj.from_dict(user_data)
            experiment_result_dictionary = {'name': job.get('name'), 'seed': 42, 'shots': job.get('number_of_shots'),
                                            'data': experiment_result_data, 'status': 'DONE', 'success': True,
                                            'time_taken': result.get('execution_time_in_seconds'), 'header': header}
            experiment_results.append(ExperimentResult(**experiment_result_dictionary))
        return experiment_results

    @staticmethod
    def __validate(job):
        """ Validates the number of shots, classical bits and compiled Qiskit circuits.

        Args:
            job (QObj): The quantum job with the Qiskit algorithm and quantum inspire backend.
        """
        QuantumInspireBackend.__validate_number_of_shots(job)

        for experiment in job.experiments:
            QuantumInspireBackend.__validate_number_of_clbits(experiment)
            QuantumInspireBackend.__validate_no_gates_after_measure(experiment)

    @staticmethod
    def __validate_number_of_shots(job):
        """ Checks whether the number of shots has a valid value.

        Args:
            job (QObj): The quantum job with the Qiskit algorithm and quantum inspire backend.

        Raises:
            QisKitBackendError: When the value is not correct.
        """
        number_of_shots = job.config.shots
        if number_of_shots < 1:
            raise QisKitBackendError('Invalid shots (number_of_shots={})'.format(number_of_shots))

    @staticmethod
    def __validate_number_of_clbits(experiment):
        """ Checks whether the number of classical bits has a valid value.

        Args:
            experiment (QobjExperiment): The experiment with gate operations and header.

        Raises:
            QisKitBackendError: When the value is not correct.
        """
        number_of_clbits = experiment.header.memory_slots
        if number_of_clbits < 1:
            raise QisKitBackendError("Invalid amount of classical bits ({})!".format(number_of_clbits))

    @staticmethod
    def __validate_no_gates_after_measure(experiment):
        """ Checks whether the number of classical bits has a valid value.

        Args:
            experiment (QobjExperiment): The experiment with gate operations and header.

        Raises:
            QisKitBackendError: When the value is not correct.
        """
        measured_qubits = []
        for instruction in experiment.instructions:
            for qubit in instruction.qubits:
                if instruction.name == 'measure':
                    measured_qubits.append(qubit)
                elif qubit in measured_qubits:
                    raise QisKitBackendError('Operation after measurement!')

    @staticmethod
    def _collect_measurements(experiment):
        """ Determines the measured qubits and classical bits. The full-state measured
            qubits is returned when no measurements are present in the compiled circuit.

        Args:
            experiment (QobjExperiment): The experiment with gate operations and header.

        Returns:
            list: A list of lists, for each measurement the returned list contains a list of
                  [qubit_index, classical_bit_index], which represents the measurement of a qubit to a classical bit.
        """
        header = experiment.header
        number_of_qubits = header.n_qubits
        number_of_clbits = header.memory_slots

        operations = experiment.instructions
        measurements = [[number_of_qubits - 1 - m.qubits[0],
                         number_of_clbits - 1 - m.memory[0]]
                        for m in operations if m.name == 'measure']
        if not measurements:
            measurements = [[index, index] for index in range(number_of_qubits)]
        return {'measurements': measurements, 'number_of_clbits': number_of_clbits}

    @staticmethod
    def __qubit_to_classical_hex(qubit_register, measurements, number_of_qubits):
        """ This function converts the qubit register data to the hexadecimal representation of the classical state.

        Args:
            qubit_register (int): The measured value of the qubits represented as int.
            measurements (dict): The dictionary contains a measured qubits/classical bits map (list) and the
                                 number of classical bits (int).
            number_of_qubits (int): Number of qubits used in the algorithm.

        Returns:
            str: The hexadecimal value of the classical state.

        """
        qubit_state = ('{0:0{1}b}'.format(int(qubit_register), number_of_qubits))
        classical_state = ['0'] * measurements['number_of_clbits']
        for q, c in measurements['measurements']:
            classical_state[c] = qubit_state[q]
        classical_state = ''.join(classical_state)
        classical_state_hex = hex(int(classical_state, 2))
        return classical_state_hex

    @staticmethod
    def __convert_histogram(result, measurements):
        """ The quantum inspire backend always uses full state projection. The SDK user
            can measure not all qubits and change the combined classical bits. This function
            converts the result to a histogram output that represents the probabilities
            measured with the classical bits.

        Args:
            result (dict): The result output from the quantum inspire backend with full-
                           state projection histogram output.
            measurements (dict): The dictionary contains a measured qubits/classical bits map (list) and the
                                 number of classical bits (int).

        Returns:
            (Obj): The resulting full state histogram with probabilities.
        """
        output_histogram_probabilities = defaultdict(lambda: 0)
        number_of_qubits = result['number_of_qubits']
        state_probability = result['histogram']
        for qubit_register, probability in state_probability.items():
            classical_state_hex = QuantumInspireBackend.__qubit_to_classical_hex(qubit_register, measurements,
                                                                                 number_of_qubits)
            output_histogram_probabilities[classical_state_hex] += probability

        full_state_histogram_obj = OrderedDict(sorted(output_histogram_probabilities.items(),
                                                      key=lambda kv: int(kv[0], 16)))
        return Obj.from_dict(full_state_histogram_obj)

    def __convert_result_data(self, result, measurements):
        """ The quantum inspire backend returns the single shot values as raw data. This function
            converts this list of single shot values to hexadecimal memory data according the Qiskit spec.
            From this memory data the counts histogram is constructed by counting the single shot values.

        Note:
            When shots = 1, the backend returns an empty list as raw_data. This is a special case. In this case the
            resulting memory data consists of 1 value and the count histogram consists of 1 instance of this value.
            To determine this value a random float is generated in the range [0, 1). With this random number the
            value from this probabilities histogram is taken where the added probabilities is greater this random
            number.
            Example: probability histogram is {[0x0, 0.2], [0x3, 0.4], [0x5, 0.1], [0x6, 0.3]}.
            When random is in the range [0, 0.2) the first value of the probability histogram is taken (0x0).
            When random is in the range [0.2, 0.6) the second value of the probability histogram is taken (0x3).
            When random is in the range [0.6, 0.7) the third value of the probability histogram is taken (0x5).
            When random is in the range [0.7, 1) the last value of the probability histogram is taken (0x6).

        Args:
            result (dict): The result output from the quantum inspire backend with full-
                           state projection histogram output.
            measurements (dict): The dictionary contains a measured qubits/classical bits map (list) and the
                                 number of classical bits (int).

        Returns:
            (Obj, list): The result consists of two formats for the result. The first result is the histogram with
                         count data, the second result is a list with converted hexadecimal memory values for
                         each shot.
        """
        memory_data = []
        histogram_data = defaultdict(lambda: 0)
        number_of_qubits = result['number_of_qubits']
        raw_data = self.__api.get_raw_data(str(result['id']))
        if raw_data:
            for qubit_register in raw_data:
                classical_state_hex = QuantumInspireBackend.__qubit_to_classical_hex(qubit_register, measurements,
                                                                                     number_of_qubits)
                memory_data.append(classical_state_hex)
            for elem, count in Counter(memory_data).items():
                histogram_data[elem] = count
        else:
            state_probabilities = result['histogram']
            prob = np.random.rand()
            sum_probability = 0.0
            for qubit_register, probability in state_probabilities.items():
                sum_probability += probability
                if prob < sum_probability:
                    classical_state_hex = QuantumInspireBackend.__qubit_to_classical_hex(qubit_register, measurements,
                                                                                         number_of_qubits)
                    memory_data.append(classical_state_hex)
                    histogram_data[classical_state_hex] = 1
                    break

        histogram_obj = OrderedDict(sorted(histogram_data.items(), key=lambda kv: int(kv[0], 16)))
        return Obj.from_dict(histogram_obj), memory_data
