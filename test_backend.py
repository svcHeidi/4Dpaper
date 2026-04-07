#!/usr/bin/env python3
"""
Test script to verify the backend can process the real OpenFOAM case.
Tests the 4dpaper pre-render hook with the Niederer benchmark case.
"""
import sys
import json
import importlib.util
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scripts.data_loader import SimulationData

# Import 4dpaper.py using importlib (can't use normal import due to dots in path)
spec = importlib.util.spec_from_file_location(
    "dpaper_module",
    project_root / "_extensions" / "4dpaper" / "4dpaper.py"
)
dpaper_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dpaper_module)
parse_shortcodes = dpaper_module.parse_shortcodes


def test_data_loading():
    """Test that the SimulationData loader can read the OpenFOAM case."""
    print("\n" + "="*70)
    print("TEST 1: Loading OpenFOAM Decomposed Case")
    print("="*70)

    # Use .foam file as entry point
    foam_path = Path("/Users/simaocastro/cardiacFoamEP/cardiacFoam+GPUv1+frontendv1/NiedererEtAl2012/Niederer.foam")

    if not foam_path.exists():
        print(f"❌ Foam file not found: {foam_path}")
        return False

    print(f"✓ Foam file found: {foam_path}")
    case_dir = foam_path.parent
    print(f"  - processor0: {(case_dir / 'processor0').exists()}")
    print(f"  - processor1: {(case_dir / 'processor1').exists()}")

    try:
        sim = SimulationData(str(foam_path)).load()
        print(f"✓ SimulationData loaded successfully")
        print(f"  - Time steps: {sim.n_steps}")
        if hasattr(sim, 'time_values'):
            print(f"  - Time values: {sim.time_values[:5] if len(sim.time_values) > 5 else sim.time_values}")
        else:
            print(f"  - Time values: (not available)")

        if sim.n_steps == 0:
            print("❌ No time steps found!")
            return False

        # Try to load a mesh
        mesh = sim.get_mesh(0)
        if mesh is None:
            print("❌ Could not load mesh at step 0")
            return False

        print(f"✓ Mesh loaded successfully")
        print(f"  - Points: {mesh.n_points}")
        print(f"  - Cells: {mesh.n_cells}")
        print(f"  - Available fields: {list(mesh.point_data.keys()) + list(mesh.cell_data.keys())}")

        # Check for required fields
        required_fields = ["Vm", "activationTime", "activationVelocity"]
        available = set(mesh.point_data.keys()) | set(mesh.cell_data.keys())
        for field in required_fields:
            if field in available:
                print(f"  ✓ {field} available")
            else:
                print(f"  ⚠ {field} NOT found")

        return True

    except Exception as e:
        print(f"❌ Error loading SimulationData: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_shortcode_parsing():
    """Test that the shortcode parser can extract 4d-image directives."""
    print("\n" + "="*70)
    print("TEST 2: Parsing 4d-image Shortcodes")
    print("="*70)

    qmd_path = Path("/Users/simaocastro/4Dpapers/analysis_report.qmd")

    if not qmd_path.exists():
        print(f"❌ QMD file not found: {qmd_path}")
        return False

    print(f"✓ QMD file found: {qmd_path}")

    try:
        text = qmd_path.read_text()
        print(f"✓ QMD file read ({len(text)} chars)")

        shortcodes = parse_shortcodes(text)
        print(f"✓ Found {len(shortcodes)} shortcodes")

        if len(shortcodes) == 0:
            print("❌ No shortcodes found!")
            return False

        for i, sc in enumerate(shortcodes, 1):
            print(f"\nShortcode {i}:")
            print(f"  - id: {sc.get('id')}")
            print(f"  - src: {sc.get('src')}")
            print(f"  - field: {sc.get('field')}")
            print(f"  - fields: {sc.get('fields')}")
            print(f"  - style: {sc.get('style')}")

        return True

    except Exception as e:
        print(f"❌ Error parsing shortcodes: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_api_payload():
    """Test that the API payload would be valid."""
    print("\n" + "="*70)
    print("TEST 3: API Payload Structure")
    print("="*70)

    try:
        payload = {
            "files": {
                "analysis_report.qmd": (Path("/Users/simaocastro/4Dpapers/analysis_report.qmd").read_text()
                                       if Path("/Users/simaocastro/4Dpapers/analysis_report.qmd").exists()
                                       else "# Test")
            }
        }

        json_str = json.dumps(payload)
        print(f"✓ Valid JSON payload ({len(json_str)} bytes)")
        print(f"  - Files in payload: {len(payload['files'])}")

        for fname in payload['files'].keys():
            print(f"    - {fname}")

        return True

    except Exception as e:
        print(f"❌ Error creating payload: {e}")
        return False


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("4DPAPER BACKEND VERIFICATION TESTS")
    print("="*70)

    results = {
        "Data Loading": test_data_loading(),
        "Shortcode Parsing": test_shortcode_parsing(),
        "API Payload": test_api_payload(),
    }

    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "❌ FAIL"
        print(f"{status} — {test_name}")

    all_passed = all(results.values())

    if all_passed:
        print("\n✓ All tests passed! Backend should work correctly.")
        print("\nNext steps:")
        print("  1. Start server: python serve.py")
        print("  2. Visit: http://localhost:5006")
        print("  3. Click 'Compile' button to render the full document")
        print("  4. Check _output/analysis_report.html for results")
    else:
        print("\n❌ Some tests failed. Check errors above.")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
