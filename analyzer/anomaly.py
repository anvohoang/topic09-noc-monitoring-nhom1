from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass
class AnomalyResult:
    metric_name: str
    current_value: float
    mean: float
    std: float
    z_score: float
    is_anomaly: bool
    severity: str  # "normal", "warning", or "critical"
    reason: str


class RollingZScoreDetector:
    def __init__(
        self,
        window_size: int = 30,
        min_samples: int = 10,
        warning_threshold: float = 2.0,
        critical_threshold: float = 3.0,
    ) -> None:
        if window_size < 2:
            raise ValueError("window_size must be >= 2")
        if min_samples < 2 or min_samples > window_size:
            raise ValueError("min_samples must be between 2 and window_size")
        if warning_threshold <= 0 or critical_threshold <= warning_threshold:
            raise ValueError("Thresholds must satisfy 0 < warning < critical")

        self.window_size = window_size
        self.min_samples = min_samples
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold

    def evaluate(
        self,
        metric_name: str,
        values: list[float],
        only_spikes: bool = True,
    ) -> AnomalyResult:
        if not values:
            raise ValueError("values list cannot be empty")

        current_value = float(values[-1])
        history = values[:-1]

        if len(history) < self.min_samples:
            return AnomalyResult(
                metric_name=metric_name,
                current_value=current_value,
                mean=current_value,
                std=0.0,
                z_score=0.0,
                is_anomaly=False,
                severity="normal",
                reason=f"Insufficient baseline samples ({len(history)}/{self.min_samples})",
            )

        baseline = np.asarray(history[-self.window_size :], dtype=float)
        mean = float(np.mean(baseline))
        std = float(np.std(baseline))

        effective_std = max(std, 1.0)
        z_score = (current_value - mean) / effective_std
        score_to_check = z_score if only_spikes else abs(z_score)

        if score_to_check >= self.critical_threshold:
            severity = "critical"
            is_anomaly = True
            reason = (
                f"Critical Z-Score spike on {metric_name}: "
                f"current={current_value:.2f}, mean={mean:.2f}, std={std:.2f}, z={z_score:.2f}"
            )
        elif score_to_check >= self.warning_threshold:
            severity = "warning"
            is_anomaly = True
            reason = (
                f"Warning Z-Score spike on {metric_name}: "
                f"current={current_value:.2f}, mean={mean:.2f}, std={std:.2f}, z={z_score:.2f}"
            )
        else:
            severity = "normal"
            is_anomaly = False
            reason = f"Normal (z={z_score:.2f})"

        return AnomalyResult(
            metric_name=metric_name,
            current_value=current_value,
            mean=round(mean, 4),
            std=round(std, 4),
            z_score=round(z_score, 4),
            is_anomaly=is_anomaly,
            severity=severity,
            reason=reason,
        )