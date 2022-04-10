import json
import math
import random
from dataclasses import dataclass
from typing import Optional

from netqasm.logging.glob import get_netqasm_logger
from netqasm.sdk import EPRSocket
from netqasm.sdk.classical_communication.message import StructuredMessage
from netqasm.sdk.external import NetQASMConnection, Socket

logger = get_netqasm_logger()

buf_msgs = []  # type: ignore
EOF = "EOF"
ALL_MEASURED = "All qubits measured"


def recv_single_msg(socket):
    """Used to not get multiple messages at a time"""
    if len(buf_msgs) > 0:
        msg = buf_msgs.pop(0)
    else:
        msgs = socket.recv().split(EOF)[:-1]
        buf_msgs.extend(msgs[1:])
        msg = msgs[0]
    logger.debug(f"Alice received msg {msg}")
    return msg


def send_single_msg(socket, msg):
    """Used to not get multiple messages at a time"""
    socket.send(msg + EOF)


def sendClassicalAssured(socket, data):
    data = json.dumps(data)
    send_single_msg(socket, data)
    while recv_single_msg(socket) != "ACK":
        pass


def recvClassicalAssured(socket):
    data = recv_single_msg(socket)
    data = json.loads(data)
    send_single_msg(socket, "ACK")
    return data


def distribute_bb92_states(conn, epr_socket, socket, target, n):
    # Empty list of length n
    bit_flips = [None for _ in range(n)]

    # List of zeros/ones of length n
    basis_flips = [random.randint(0, 1) for _ in range(n)]

    # Share EPR pairs
    for i in range(n):
        # (Alice blocks here, until Socket established with Bob)
        q = epr_socket.create_keep(1)[0]

        # Based on pre-determine bases, Alice performs basis change
        if basis_flips[i]:
            q.H()

        # Ensure that bob has access to the pair, before we measure
        # IMPORTANT: this is the key distinction between BB84, BB92
        # The quantum processor must actually have shared the pair
        # prior to Alice's measurement, otherwise she will have implicitly
        # prepared a specific state by measuring it prior to Bob's access.
        conn.flush()

        # Records the measurement
        m = q.measure()

        # Execute measurement
        conn.flush()

        # I guess this is always zero or one.
        bit_flips[i] = int(m)

    # Return this implicit tuple thing.
    return bit_flips, basis_flips


def filter_bases(socket, pairs_info):
    # An array of tuples indexing pairs_info (established sequentially)
    bases = [(i, pairs_info[i].basis) for (i, pair) in enumerate(pairs_info)]
    
    # Push over the channel
    msg = StructuredMessage(header="Bases", payload=bases)
    socket.send_structured(msg)

    # Receive remote bases
    remote_bases = socket.recv_structured().payload

    # zip bases and remote bases, zipped into 
    for (i, basis), (remote_i, remote_basis) in zip(bases, remote_bases):
        assert i == remote_i
        pairs_info[i].same_basis = basis == remote_basis

    return pairs_info


def estimate_error_rate(socket, pairs_info, num_test_bits):
    # might shuffle the order around
    same_basis_indices = [pair.index for pair in pairs_info if pair.same_basis]

    # Choose a quarter of the indices
    test_indices = random.sample(
        same_basis_indices, min(num_test_bits, len(same_basis_indices))
    )

    # For each pair -- generated
    for pair in pairs_info:
        # Set test_outcome to true or false if 
        # our "randomly-selected" indices, indicate we should do so.
        pair.test_outcome = pair.index in test_indices

    # The outcomes from the test set
    test_outcomes = [(i, pairs_info[i].outcome) for i in test_indices]

    # These are the randomly selected test bits
    logger.info(f"alice finding {num_test_bits} test bits")
    logger.info(f"alice test indices: {test_indices}")
    logger.info(f"alice test outcomes: {test_outcomes}")

    # Alice directs bob on the selected test bits 
    socket.send_structured(StructuredMessage("Test indices", test_indices))

    # Target test outcomes received from bob
    target_test_outcomes = socket.recv_structured().payload

    # Allow bob to computer error rate separately
    socket.send_structured(StructuredMessage("Test outcomes", test_outcomes))
    logger.info(f"alice target_test_outcomes: {target_test_outcomes}")

    # Inside of the pairs of (index, test outcome --- remote index, remote test outcome)
    num_error = 0
    for (i1, t1), (i2, t2) in zip(test_outcomes, target_test_outcomes):
        assert i1 == i2
        if t1 != t2:
            num_error += 1
            pairs_info[i1].same_outcome = False
        else:
            pairs_info[i1].same_outcome = True

    return pairs_info, (num_error / num_test_bits)


def extract_key(x, r):
    return sum([xj * rj for xj, rj in zip(x, r)]) % 2


def h(p):
    if p == 0 or p == 1:
        return 0
    else:
        return -p * math.log2(p) - (1 - p) * math.log2(1 - p)


@dataclass
class PairInfo:
    """Information that Alice has about one generated pair.
    The information is filled progressively during the protocol."""

    # Index in list of all generated pairs.
    index: int

    # Basis Alice measured in. 0 = Z, 1 = X.
    basis: int

    # Measurement outcome (0 or 1).
    outcome: int

    # Whether Bob measured his qubit in the same basis or not.
    same_basis: Optional[bool] = None

    # Whether to use this pair to estimate errors by comparing the outcomes.
    test_outcome: Optional[bool] = None

    # Whether measurement outcome is the same as Bob's. (Only for pairs used for error estimation.)
    same_outcome: Optional[bool] = None


def main(app_config=None, num_bits=144, key_length=16):
    # num_bits configured by alice.yaml
    num_test_bits = max(int(num_bits / 4), 1)

    # Socket for classical communication
    socket = Socket("alice", "bob", log_config=app_config.log_config)
    
    # Socket for EPR generation
    epr_socket = EPRSocket("bob")

    alice = NetQASMConnection(
        app_name=app_config.app_name,
        log_config=app_config.log_config,
        epr_sockets=[epr_socket],
    )
    with alice:
        # Exchanges tuple of 
        # basis_flips - The set of bases that Alice chose transmitting
        # bit_flips - The set of bits that Alice actually measured
        #                 of her side of the EPR Pairs exchanged.
        bit_flips, basis_flips = distribute_bb92_states(
            alice, epr_socket, socket, "bob", num_bits
        )
    
    # Arrays of zeroes and ones
    outcomes = [int(b) for b in bit_flips]
    theta = [int(b) for b in basis_flips]

    logger.info(f"alice outcomes: {outcomes}")
    logger.info(f"alice theta: {theta}")

    # Boil down results to single array of dicts
    pairs_info = []
    for i in range(num_bits):
        pairs_info.append(
            PairInfo(
                index=i,
                basis=int(basis_flips[i]),
                outcome=int(bit_flips[i]),
            )
        )
    
    # Establish socket for filtering
    m = socket.recv()
    if m != ALL_MEASURED:
        logger.info(m)
        raise RuntimeError("Failed to distribute BB84 states")

    # Classical channel used to exchange basis, and 
    # storing "true" into same_basis for each matching exchange
    pairs_info = filter_bases(socket, pairs_info)


    logger.info(f"alice HAS DECIDED TO USE {num_test_bits} OF THOSE QUBITS")
    # Use the portion of the shared qubit measurements to perform
    pairs_info, error_rate = estimate_error_rate(socket, pairs_info, num_test_bits)
    logger.info(f"alice error rate: {error_rate}")

    # Select the key from the untested qubit measurements sharing a basis
    raw_key = [pair.outcome for pair in pairs_info if (not pair.test_outcome and pair.same_basis)]
    logger.info(f"alice raw key: {raw_key}")
    
    # Select the same basis using the raw key?

    # Return data.

    # Establish a blank table
    table = []
    # For each pair
    for pair in pairs_info:
        # Transform basis into a name
        basis = "X" if pair.basis == 1 else "Z"
        # Identify pairs used in testing, and result
        check = pair.same_outcome if pair.test_outcome else "-"
        # Add to table
        table.append([pair.index, basis, pair.same_basis, pair.outcome, check])
    
    # Count selection rate
    x_basis_count = sum(pair.basis for pair in pairs_info)
    z_basis_count = num_bits - x_basis_count
    
    # Number viable for testing or raw_key
    same_basis_count = sum(pair.same_basis for pair in pairs_info)

    # Number of qubits used for error testing (i.e., same basis, and marked)
    outcome_comparison_count = sum(
        pair.test_outcome for pair in pairs_info if pair.same_basis
    )

    # pairs which constitute errors
    diff_outcome_count = outcome_comparison_count - sum(
        pair.same_outcome for pair in pairs_info if pair.test_outcome
    )
    if outcome_comparison_count == 0:
        qber = 1
    else:
        qber = (diff_outcome_count) / outcome_comparison_count

    # Compute a "key-rate potential"
    # Using the Binary entropy
    key_rate_potential = 1 - 2 * h(qber)

    return {
        # Table with one row per generated pair.
        # Columns:
        #   - Pair number
        #   - Measurement basis ("X" or "Z")
        #   - Same basis as Bob ("True" or "False")
        #   - Measurement outcome ("0" or "1")
        #   - Outcome same as Bob ("True", "False" or "-")
        #       ("-" is when outcomes are not compared)
        "secret_key": raw_key[0:key_length],
        "table": table,
        # Number of times measured in the X basis.
        "x_basis_count": x_basis_count,
        # Number of times measured in the Z basis.
        "z_basis_count": z_basis_count,
        # Number of times measured in the same basis as Bob.
        "same_basis_count": same_basis_count,
        # Number of pairs chosen to compare measurement outcomes for.
        "outcome_comparison_count": outcome_comparison_count,
        # Number of compared outcomes with equal values.
        "diff_outcome_count": diff_outcome_count,
        # Estimated Quantum Bit Error Rate (QBER).
        "qber": qber,
        # Rate of secure key that can in theory be extracted from the raw key.
        "key_rate_potential": key_rate_potential,
        # Raw key.
        # ('Result' of this application. In practice, there'll be post-processing to produce secure shared key.)
        "raw_key": raw_key,
    }


if __name__ == "__main__":
    main()
