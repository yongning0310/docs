#!/usr/bin/env python3
"""
Plot performance benchmark results.

Reads benchmarks/results/results.json and produces:
  - benchmarks/results/performance.png  (combined 3×3 grid)
  - Scaling analysis printed to stdout

Usage:
    python benchmarks/plot.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

RESULTS_DIR = Path(__file__).parent / "results"

DIMENSION_LABELS = {
    "content_kb": "Content Size (KB)",
    "num_documents": "Number of Documents",
    "num_changes": "Number of Changes",
    "num_suggestions": "Number of Suggestions",
    "num_entries": "Number of History Entries",
}


def _classify_scaling(exponent: float) -> str:
    if exponent < 0.15:
        return "~O(1)"
    if exponent < 0.6:
        return f"~O(n^{exponent:.2f})"
    if exponent < 1.15:
        return "~O(n)"
    if exponent < 1.6:
        return "~O(n log n)"
    return f"~O(n^{exponent:.1f})"


def _fit_exponent(workloads, latencies):
    """Fit power law y = a * x^k on log-log scale. Returns (exponent, r_squared)."""
    log_x = np.log10(np.array(workloads, dtype=float))
    log_y = np.log10(np.array(latencies, dtype=float))
    coeffs = np.polyfit(log_x, log_y, 1)
    slope = coeffs[0]
    # R² on log-log scale
    predicted = np.polyval(coeffs, log_x)
    ss_res = np.sum((log_y - predicted) ** 2)
    ss_tot = np.sum((log_y - np.mean(log_y)) ** 2)
    r_sq = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    return slope, r_sq, coeffs


def main():
    results_path = RESULTS_DIR / "results.json"
    if not results_path.exists():
        print(f"No results found at {results_path}. Run benchmarks first:")
        print("  python benchmarks/run.py")
        return

    with open(results_path) as f:
        data = json.load(f)

    benchmarks = data["benchmarks"]
    n = len(benchmarks)
    cols = 3
    rows = (n + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(16, rows * 4.5))
    axes = axes.flatten()

    scaling_lines = []
    scaling_lines.append(f"Performance Scaling Analysis — {data['timestamp'][:19]}")
    scaling_lines.append("=" * 60)

    for i, bench in enumerate(benchmarks):
        ax = axes[i]
        name = bench["name"]
        dim = bench["dimension"]
        results = bench["results"]

        workloads = [r["workload"] for r in results]
        medians = [r["median_ms"] for r in results]
        mins = [r["min_ms"] for r in results]
        maxs = [r["max_ms"] for r in results]

        # Plot data with error bars (min/max range)
        lower_err = [med - mn for med, mn in zip(medians, mins)]
        upper_err = [mx - med for mx, med in zip(medians, maxs)]
        ax.errorbar(
            workloads,
            medians,
            yerr=[lower_err, upper_err],
            fmt="o-",
            color="#2563eb",
            linewidth=2,
            markersize=6,
            capsize=4,
            capthick=1.5,
            label="Measured",
        )

        # Fit power law and plot trend
        exponent, r_sq, coeffs = _fit_exponent(workloads, medians)
        classification = _classify_scaling(exponent)

        # Plot fitted line
        x_fit = np.logspace(
            np.log10(min(workloads)), np.log10(max(workloads)), 50
        )
        y_fit = 10 ** np.polyval(coeffs, np.log10(x_fit))
        ax.plot(
            x_fit,
            y_fit,
            "--",
            color="#dc2626",
            linewidth=1.5,
            alpha=0.7,
            label=f"Fit: {classification} (R²={r_sq:.3f})",
        )

        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel(DIMENSION_LABELS.get(dim, dim))
        ax.set_ylabel("Latency (ms)")
        ax.set_title(f"{name}\n{bench['description']}", fontsize=11, fontweight="bold")
        ax.legend(fontsize=9, loc="upper left")
        ax.grid(True, which="both", alpha=0.3)
        ax.xaxis.set_major_formatter(ticker.ScalarFormatter())
        ax.yaxis.set_major_formatter(ticker.ScalarFormatter())

        # Scaling summary
        scaling_lines.append(f"\n{name} ({bench['description']})")
        scaling_lines.append(f"  Scaling: {classification}  (exponent={exponent:.3f}, R²={r_sq:.3f})")
        scaling_lines.append(f"  {'Workload':>12}  {'Median':>10}  {'Min':>10}  {'Max':>10}")
        for r in results:
            unit = dim.split("_")[-1] if "_" in dim else ""
            scaling_lines.append(
                f"  {r['workload']:>12}  {r['median_ms']:>9.1f}ms  "
                f"{r['min_ms']:>9.1f}ms  {r['max_ms']:>9.1f}ms"
            )

    # Hide unused subplots
    for j in range(n, len(axes)):
        axes[j].set_visible(False)

    fig.suptitle(
        "Redline Service — API Performance Scaling",
        fontsize=14,
        fontweight="bold",
        y=1.01,
    )
    fig.tight_layout()

    # Save outputs
    png_path = RESULTS_DIR / "performance.png"
    fig.savefig(png_path, dpi=150, bbox_inches="tight")
    print(f"Chart saved to {png_path}")

    print()
    for line in scaling_lines:
        print(line)


if __name__ == "__main__":
    main()
