# qkd-strap

## Team QuackAttack!

### DEALBREAKERS (FIX)
- Implement classical link authentication

### Protocol background
[This paper covers security concerns](https://www.researchgate.net/publication/252481123_Security_and_implementation_of_differential_phase_shift_quantum_key_distribution_systems)

### QKD Strap
The Team QuackAttack QKD-strap includes a QNE harness for demonstrating the implementation of BBM'92 using NetQASM

### Instructions
Contained is alice and bob implementing BBM'92 QKD protocol, within parameters for testing.

As configured, 50 Qubits are exchanged, QBER is computed, first 16 valid Qubits comprise the key (as required).

To run:
[Install QNE, NetQASM](https://github.com/QuTech-Delft/qne-qchack-2022#pre-requisites)
- Requires Linux, Mac OSX, Windows Subsystem for Linux
- Supports Python3 <=3.9 

- Establish `conda` environment using `conda create qkd-env python=3.9`
- Test that QNE and NetQASM are availble

`git clone https://github.com/meltyness/qkd-strap`

`cd qkd-strap`

use `./env_setup.py` to faciliate

`cd qkd`

`qne experiment run exp --timeout=30`

`qne experiment results exp --show`

... or in your favorite editor:

`vim exp/raw_output/LAST/results.yaml`

Targeted results are returned in the dict as `secret_key`

Detailed comments in `app_alice.py` describe the full procedure, and variable involved.

See also `application.json` and `exp/` .json files for details about how the application is being run, and the network it's being simulated on. Details for how to modify this configuration are: [in the QNE-ADK docs](https://www.quantum-network.com/knowledge-base/qne-adk/)

### Debugging
In order to facilitate a more in-depth understanding of the proceedings, ensure that you have NetQASM installed based on aforementioned instructions, and use:
`cd qkd-strap/src`
`netqasm simulate --log-level=INFO`

and your screen will be flooded with details about the proceedings between alice and bob.

### Road ahead
- Implement an Eavesdropper, possibly in-line with eavesdropping strategies which may be possible following the security-implications paper above.
- Differentiate between an eavesdropper and a noisy-channel. See [this part of wikipedia](https://en.wikipedia.org/wiki/Quantum_key_distribution#Information_reconciliation_and_privacy_amplification)


