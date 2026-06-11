"""Analyze graded results: bootstrap CIs, significance tests, and graphs.

Usage:
    python -m harness.analyze [--experiment NAME]

Outputs per experiment into graphs/:
- <exp>_acus.png            mean ACUs per arm with 95% bootstrap CI
- <exp>_accuracy.png        mean accuracy per arm with 95% bootstrap CI
- <exp>_scatter.png         ACU vs accuracy scatter colored by arm
- <exp>_cost_per_success.png  ACUs per successful task with bootstrap CI
- summary.md                table of stats + significance
"""

from __future__ import annotations

import sys
import json
import random
import pathlib
import argparse
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    from scipy.stats import mannwhitneyu
except ImportError:  # pragma: no cover
    mannwhitneyu = None

ROOT = pathlib.Path(__file__).resolve().parent.parent
GRADED = ROOT / "results" / "graded.jsonl"
GRAPHS = ROOT / "graphs"

COLORS = {"control": "#9aa0a6", "default": "#4285f4"}
ARM_COLORS = ["#9aa0a6", "#4285f4", "#34a853", "#fbbc04", "#ea4335"]


def bootstrap_ci(values, stat=lambda v: sum(v) / len(v), n=10000, alpha=0.05, seed=7):
    if not values:
        return (float("nan"), float("nan"), float("nan"))
    rng = random.Random(seed)
    point = stat(values)
    stats = []
    for _ in range(n):
        sample = [values[rng.randrange(len(values))] for _ in values]
        s = stat(sample)
        if s is not None:
            stats.append(s)
    if not stats:
        return (point, float("nan"), float("nan"))
    stats.sort()
    n = len(stats)
    lo = stats[int(alpha / 2 * n)]
    hi = stats[int((1 - alpha / 2) * n) - 1]
    return point, lo, hi


def cost_per_success(rows):
    succ = [r for r in rows if r.get("success")]
    if not succ:
        return None
    total_acus = sum(r["acus"] or 0 for r in rows)
    return total_acus / len(succ)


def bar_with_ci(ax, arms, points, los, his, ylabel, title):
    xs = range(len(arms))
    colors = ARM_COLORS[: len(arms)]
    ax.bar(xs, points, color=colors, width=0.6)
    ax.errorbar(
        xs, points,
        yerr=[[p - l for p, l in zip(points, los)], [h - p for p, h in zip(points, his)]],
        fmt="none", ecolor="black", capsize=6, lw=1.5,
    )
    ax.set_xticks(list(xs))
    ax.set_xticklabels(arms)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    if len(points) >= 2 and points[0]:
        for i in range(1, len(points)):
            delta = (points[i] - points[0]) / points[0] * 100
            ax.annotate(f"{delta:+.0f}%", (i, points[i]), ha="center", va="bottom",
                        xytext=(0, 8), textcoords="offset points", fontweight="bold")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment")
    args = ap.parse_args()
    GRAPHS.mkdir(exist_ok=True)

    rows = [json.loads(l) for l in GRADED.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if r.get("acus") is not None]
    by_exp = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if args.experiment and r["experiment"] != args.experiment:
            continue
        by_exp[r["experiment"]][r["arm"]].append(r)

    summary_lines = ["# Eval summary\n"]
    for exp, arms_dict in by_exp.items():
        arms = list(arms_dict)
        summary_lines.append(f"\n## {exp}\n")
        summary_lines.append("| arm | n | mean ACUs [95% CI] | median ACUs | accuracy [95% CI] | success rate | ACUs/success |")
        summary_lines.append("|---|---|---|---|---|---|---|")

        acu_stats, acc_stats, cps_stats = [], [], []
        for arm in arms:
            rs = arms_dict[arm]
            acus = [r["acus"] for r in rs]
            accs = [r["score"] for r in rs if r.get("score") is not None]
            a_p, a_l, a_h = bootstrap_ci(acus)
            s_p, s_l, s_h = bootstrap_ci(accs) if accs else (float("nan"),) * 3
            cps = cost_per_success(rs)
            cps_ci = bootstrap_ci(rs, stat=cost_per_success) if cps else (None, None, None)
            acu_stats.append((a_p, a_l, a_h))
            acc_stats.append((s_p, s_l, s_h))
            cps_stats.append(cps_ci)
            med = sorted(acus)[len(acus) // 2]
            sr = sum(1 for r in rs if r.get("success")) / len(rs)
            summary_lines.append(
                f"| {arm} | {len(rs)} | {a_p:.2f} [{a_l:.2f},{a_h:.2f}] | {med:.2f} "
                f"| {s_p:.2f} [{s_l:.2f},{s_h:.2f}] | {sr:.0%} | {f'{cps:.2f}' if cps else 'n/a'} |"
            )

        if mannwhitneyu and len(arms) >= 2:
            base = [r["acus"] for r in arms_dict[arms[0]]]
            for arm in arms[1:]:
                u = mannwhitneyu([r["acus"] for r in arms_dict[arm]], base, alternative="two-sided")
                summary_lines.append(f"\nMann-Whitney U ({arm} vs {arms[0]}, ACUs): p={u.pvalue:.4f}")

        for metric, stats, ylabel in [
            ("acus", acu_stats, "ACUs per session"),
            ("accuracy", acc_stats, "Accuracy"),
            ("cost_per_success", cps_stats, "ACUs per successful task"),
        ]:
            if any(s[0] is None or s[0] != s[0] for s in stats):
                continue
            fig, ax = plt.subplots(figsize=(7, 5))
            bar_with_ci(ax, arms, [s[0] for s in stats], [s[1] for s in stats],
                        [s[2] for s in stats], ylabel, f"{exp}: {ylabel} (95% bootstrap CI)")
            fig.tight_layout()
            fig.savefig(GRAPHS / f"{exp}_{metric}.png", dpi=160)
            plt.close(fig)

        fig, ax = plt.subplots(figsize=(7, 5))
        for i, arm in enumerate(arms):
            rs = [r for r in arms_dict[arm] if r.get("score") is not None]
            ax.scatter([r["acus"] for r in rs], [r["score"] for r in rs],
                       label=arm, color=ARM_COLORS[i % len(ARM_COLORS)], alpha=0.75, s=60)
        ax.set_xlabel("ACUs per session")
        ax.set_ylabel("Accuracy")
        ax.set_title(f"{exp}: cost vs accuracy by arm")
        ax.legend()
        fig.tight_layout()
        fig.savefig(GRAPHS / f"{exp}_scatter.png", dpi=160)
        plt.close(fig)

    (GRAPHS / "summary.md").write_text("\n".join(summary_lines) + "\n")
    print("\n".join(summary_lines))


if __name__ == "__main__":
    sys.exit(main())
