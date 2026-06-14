#!/usr/bin/env python3
"""Benchmark mockup generation throughput on AS400."""

import subprocess
import time
import re
import sys
from datetime import datetime

def run_mockup_benchmark(library="GSLIBTST", table="THAI_TEST"):
    """Run mockup generation benchmark."""
    
    print("=" * 50)
    print("Mockup Generation Throughput Benchmark")
    print("=" * 50)
    print(f"Target: {library}.{table}")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Auto-detect running agent
    import os
    import urllib.request
    try:
        req = urllib.request.Request("http://127.0.0.1:8765/health")
        with urllib.request.urlopen(req, timeout=1) as response:
            if response.status == 200:
                os.environ["QADMCLI_AGENT_URL"] = "http://127.0.0.1:8765"
                print("🔗 Connected to Agent at http://127.0.0.1:8765 (Bypassing startup overhead!)")
    except Exception:
        print("⚠️ No running Agent detected on http://127.0.0.1:8765. Running direct (slower).")
    print()
    
    # Test configurations
    batch_sizes = [50, 100, 200, 500]
    tx_counts = [100, 500, 1000]
    
    results = []
    
    for tx_count in tx_counts:
        for batch_size in batch_sizes:
            print()
            print("━" * 50)
            print(f"📊 Test: {tx_count} transactions, batch size {batch_size}")
            print("━" * 50)
            
            # Record start time
            start_time = time.time()
            
            # Run mockup generate
            cmd = [
                "bash", "qadmcli.sh", "mockup", "generate",
                "-t", table,
                "-l", library,
                "-r", str(tx_count),
                "--batch-size", str(batch_size),
                "--insert-ratio", "60",
                "--update-ratio", "20",
                "--delete-ratio", "20"
            ]
            
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                
                # Record end time
                end_time = time.time()
                duration = end_time - start_time
                
                # Combine stdout and stderr
                output = result.stdout + result.stderr
                
                # Remove ANSI color codes
                import re as re_ansi
                output = re_ansi.sub(r'\x1b\[[0-9;]*m', '', output)
                
                # Extract stats using regex (handle extra whitespace)
                inserted = re.search(r'Inserted:\s+(\d+)', output)
                updated = re.search(r'Updated:\s+(\d+)', output)
                deleted = re.search(r'Deleted:\s+(\d+)', output)
                
                inserted_count = int(inserted.group(1)) if inserted else 0
                updated_count = int(updated.group(1)) if updated else 0
                deleted_count = int(deleted.group(1)) if deleted else 0
                
                total_rows = inserted_count + updated_count + deleted_count
                rows_per_sec = total_rows / duration if duration > 0 else 0
                
                print(f"✅ Results:")
                print(f"   Duration: {duration:.2f}s")
                print(f"   Inserted: {inserted_count} rows")
                print(f"   Updated:  {updated_count} rows")
                print(f"   Deleted:  {deleted_count} rows")
                print(f"   Throughput: {rows_per_sec:.2f} rows/sec")
                
                results.append({
                    'tx_count': tx_count,
                    'batch_size': batch_size,
                    'inserted': inserted_count,
                    'updated': updated_count,
                    'deleted': deleted_count,
                    'duration': duration,
                    'rows_per_sec': rows_per_sec
                })
                
            except subprocess.TimeoutExpired:
                print("❌ Timeout after 300 seconds")
                results.append({
                    'tx_count': tx_count,
                    'batch_size': batch_size,
                    'inserted': 0,
                    'updated': 0,
                    'deleted': 0,
                    'duration': 300,
                    'rows_per_sec': 0
                })
            except Exception as e:
                print(f"❌ Error: {e}")
                results.append({
                    'tx_count': tx_count,
                    'batch_size': batch_size,
                    'inserted': 0,
                    'updated': 0,
                    'deleted': 0,
                    'duration': 0,
                    'rows_per_sec': 0
                })
            
            # Small delay between tests
            time.sleep(2)
    
    # Print summary
    print()
    print("=" * 50)
    print("✅ Benchmark Complete!")
    print("=" * 50)
    print()
    print("Summary:")
    print(f"{'TX Count':<12} {'Batch':<8} {'Inserted':<10} {'Updated':<10} {'Deleted':<10} {'Duration':<10} {'Rows/sec':<10}")
    print("-" * 70)
    
    for r in results:
        print(f"{r['tx_count']:<12} {r['batch_size']:<8} {r['inserted']:<10} {r['updated']:<10} {r['deleted']:<10} {r['duration']:<10.2f} {r['rows_per_sec']:<10.2f}")
    
    # Find best configuration
    if results:
        best = max(results, key=lambda x: x['rows_per_sec'])
        print()
        print("=" * 50)
        print("💡 Best Configuration:")
        print("=" * 50)
        print(f"   Transactions: {best['tx_count']}")
        print(f"   Batch Size: {best['batch_size']}")
        print(f"   Throughput: {best['rows_per_sec']:.2f} rows/sec")
        print()

if __name__ == "__main__":
    library = sys.argv[1] if len(sys.argv) > 1 else "GSLIBTST"
    table = sys.argv[2] if len(sys.argv) > 2 else "THAI_TEST"
    
    run_mockup_benchmark(library, table)

