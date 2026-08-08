"""Verify that the detector runtime is installed and report GPU availability."""

from importlib import import_module
from importlib.metadata import PackageNotFoundError, version


REQUIRED_PACKAGES = {
    "numpy": "numpy",
    "opencv-python": "cv2",
    "torch": "torch",
    "ultralytics": "ultralytics",
}


def main():
    missing = []

    print("Drone pipeline environment")
    print("=" * 40)
    for package_name, import_name in REQUIRED_PACKAGES.items():
        try:
            import_module(import_name)
            try:
                installed_version = version(package_name)
            except PackageNotFoundError:
                installed_version = "installed (version metadata unavailable)"
            print(f"[OK] {package_name}: {installed_version}")
        except (ImportError, OSError) as exc:
            missing.append(package_name)
            print(f"[MISSING] {package_name}: {exc}")

    if missing:
        print("\nEnvironment is not ready.")
        print("Install PyTorch for your CPU/CUDA platform first, then run:")
        print("  python -m pip install -r requirements.txt")
        raise SystemExit(1)

    torch = import_module("torch")
    cuda_available = torch.cuda.is_available()
    print(f"\nCUDA available: {cuda_available}")
    if cuda_available:
        print(f"CUDA device: {torch.cuda.get_device_name(0)}")
    else:
        print("Use --device cpu, or install a CUDA-enabled PyTorch build.")

    print("\nEnvironment is ready.")


if __name__ == "__main__":
    main()
