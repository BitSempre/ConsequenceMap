# Prototype README

## Running the Prototype
To execute the prototype demonstrating the human authorization architecture, navigate to the `ConsequenceMap` directory and run:

````
python prototype/demo.py
````

## Structure of the Prototype
- **`protocol.py`**: Contains all the necessary functions for handling the authorization protocols.
- **`demo.py`**: Tests various aspects of secure authorization, including:
  - Proposal creation and hashing
  - Validation against tampered data
  - Handling expired authorization
  - Verifying non-ASCII inputs.

Ensure that the implemented checks capture edge cases effectively and report results clearly.