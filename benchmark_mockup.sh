#!/bin/bash
# Benchmark script to measure mockup generation throughput on AS400
# Usage: ./benchmark_mockup.sh [LIBRARY] [TABLE]
#
# This script now calls the Python benchmark which has proper ANSI handling

LIBRARY=${1:-"GSLIBTST"}
TABLE=${2:-"THAI_TEST"}

# Run Python benchmark instead (has proper ANSI code stripping and regex parsing)
echo "🚀 Running Python benchmark script..."
echo "   Library: $LIBRARY"
echo "   Table: $TABLE"
echo ""

sudo -E python3 "$(dirname "$0")/benchmark_mockup.py" "$LIBRARY" "$TABLE"
