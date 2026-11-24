#!/bin/bash -e
# Run the Docker-free Jinja2/Twig/FreeMarker variant tests.
# The harness spawns the local ranges itself; run ranges/setup_runtimes.sh
# once to provision the optional PHP/Java runtimes.

cd "$( dirname "${BASH_SOURCE[0]}" )"/../

python3 -m unittest tests.test_engine_variants -v
