#!/usr/bin/env python3
"""
Test the compile API endpoint.
Make sure the server is running first: python serve.py
"""
import json
import requests
import sys
import time
from pathlib import Path

def test_health_check(base_url):
    """Check if backend is ready."""
    print("\n" + "="*70)
    print("HEALTH CHECK")
    print("="*70)

    try:
        response = requests.get(f"{base_url}/api/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print("✓ Backend is ready")
            print(f"  - Main QMD exists: {data['main_qmd']['exists']}")
            print(f"  - Output dir writable: {data['output_dir']['writable']}")
            print(f"  - State dir writable: {data['state_dir']['writable']}")
            return True
        else:
            print(f"✗ Health check failed: {response.status_code}")
            print(response.text)
            return False
    except requests.exceptions.ConnectionError:
        print("✗ Cannot connect to server. Is it running?")
        print(f"  Try: python serve.py")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_compile(base_url):
    """Test the compile endpoint."""
    print("\n" + "="*70)
    print("TESTING COMPILE ENDPOINT")
    print("="*70)

    # Read the main QMD file
    qmd_path = Path("analysis_report.qmd")
    if not qmd_path.exists():
        print(f"✗ File not found: {qmd_path}")
        return False

    content = qmd_path.read_text(encoding="utf-8")
    print(f"✓ Read analysis_report.qmd ({len(content)} bytes)")

    # Send to API
    payload = {
        "files": {
            "analysis_report.qmd": content
        }
    }

    print(f"✓ Sending compile request...")
    try:
        response = requests.post(
            f"{base_url}/api/compile",
            json=payload,
            timeout=300,  # 5 minute timeout for long renders
            headers={"Content-Type": "application/json"}
        )

        print(f"✓ Response received: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                html_size = len(data.get("html", ""))
                print(f"✓ COMPILATION SUCCESSFUL!")
                print(f"  - HTML size: {html_size} bytes")

                # Check if output file was written
                output_path = Path("_output/analysis_report.html")
                if output_path.exists():
                    print(f"✓ Output file exists: {output_path}")
                    print(f"  - Size: {output_path.stat().st_size} bytes")

                return True
            else:
                print(f"✗ Compilation failed")
                print(f"  - Error: {data.get('error', 'Unknown error')}")
                if "log" in data:
                    print(f"\n  Last log lines:")
                    for line in data["log"].split("\n")[-10:]:
                        if line.strip():
                            print(f"    {line}")
                return False
        else:
            print(f"✗ Compilation request failed: {response.status_code}")
            try:
                data = response.json()
                print(f"  - Error: {data.get('error', 'Unknown error')}")
                if "log" in data:
                    print(f"\n  Last log lines:")
                    for line in data["log"].split("\n")[-10:]:
                        if line.strip():
                            print(f"    {line}")
            except:
                print(f"  Response: {response.text[:500]}")
            return False

    except requests.exceptions.Timeout:
        print(f"✗ Request timed out (>5 minutes). Compilation may still be running.")
        return False
    except requests.exceptions.ConnectionError:
        print(f"✗ Cannot connect to server. Is it running?")
        print(f"  Try: python serve.py")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n" + "="*70)
    print("4DPAPER COMPILE API TEST")
    print("="*70)

    # Try to find the server
    base_url = None
    for port in [5006, 8000, 5000, 3000]:
        try:
            response = requests.get(f"http://localhost:{port}/api/health", timeout=1)
            if response.status_code == 200:
                base_url = f"http://localhost:{port}"
                print(f"✓ Found server at {base_url}")
                break
        except:
            pass

    if not base_url:
        print("✗ Server not found!")
        print("\nStart the server first:")
        print("  python serve.py")
        print("\nThen run this test again.")
        return 1

    # Run tests
    if not test_health_check(base_url):
        return 1

    if not test_compile(base_url):
        return 1

    print("\n" + "="*70)
    print("✓ ALL TESTS PASSED!")
    print("="*70)
    print("\nNow test in browser:")
    print(f"  Open: {base_url}")
    print("  Click: Compile button")
    print("  Check: Preview pane updates")

    return 0


if __name__ == "__main__":
    sys.exit(main())
