"""Independent native reproducer: NumPy only, no OpenJutsu imports or media.

Default workload matches the child in test_numpy_palette_path_in_fresh_processes.
Run in a disposable diagnostic environment, not as an application workaround.
"""

import argparse
import faulthandler

import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--mode", choices=("gather", "stack", "boolean"), default="boolean")
    args = parser.parse_args()
    faulthandler.enable()
    colors = np.array([[0, 0, 0], [230, 190, 40], [40, 150, 250], [185, 100, 230]], dtype=np.uint8)
    labels = np.random.default_rng(5).integers(0, 4, size=(261, 96, 54), dtype=np.uint8)
    print(
        f"NumPy {np.__version__}; mode={args.mode}; seed=5; iterations={args.iterations}",
        flush=True,
    )
    for i in range(args.iterations):
        if args.mode == "gather":
            for plane in labels:
                result = colors[plane]
                assert result.shape == (96, 54, 3)
        else:
            result = np.stack([colors[plane] for plane in labels])
            assert result.shape == (261, 96, 54, 3)
            if args.mode == "boolean":
                assert np.array_equal(
                    result[labels == 3], np.broadcast_to(colors[3], result[labels == 3].shape)
                )
        if i % 10 == 0:
            print(f"completed iteration {i + 1}", flush=True)
    print(f"PASS: {args.iterations} exact palette passes", flush=True)


if __name__ == "__main__":
    main()
