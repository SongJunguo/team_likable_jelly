#!/usr/bin/env python3
"""
Analyze tracking boundary conditions for dual-aircraft companion flight.

Companion flight (formation) definition used here:
  - Relative distance <= d_thresh,
  - Relative speed <= v_thresh,
  - Heading difference <= psi_thresh,
  - Sustained over a time window.

Key factors that influence companion tracking performance and boundaries:
  1) Relative geometry: separation, relative speed, and heading offset.
  2) Maneuver intensity: turn-rate and acceleration changes (model mismatch).
  3) Noise levels: process/measurement covariance (Q/R).
  4) Sampling rate: update interval (dt) and latency.
  5) IMM mode probabilities: transition matrix and model set.
  6) Initialization/association errors for multi-target tracking.
  7) Formation rigidity: how tightly relative states are maintained.

This script compares a baseline IMM (for non-companion flight) against a
virtual-structure model (VSMM) for companion flight. It uses Kalman filters
with Gaussian process/measurement noise, then estimates a boundary in the
relative distance/speed plane where VSMM outperforms IMM.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Dict, Iterable, Tuple

import numpy as np


@dataclasses.dataclass
class ModelConfig:
    dt: float = 1.0
    steps: int = 60
    omega: float = math.radians(3.0)  # turn rate for CT model
    q_cv: float = 0.5
    q_ct: float = 0.8
    q_vsmm: float = 0.2
    r_pos: float = 30.0
    imm_transition: np.ndarray = dataclasses.field(
        default_factory=lambda: np.array([[0.95, 0.05], [0.05, 0.95]])
    )


def cv_matrices(dt: float, q: float) -> Tuple[np.ndarray, np.ndarray]:
    f = np.array(
        [
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ],
        dtype=float,
    )
    q_block = q * np.array(
        [[dt**4 / 4, dt**3 / 2], [dt**3 / 2, dt**2]], dtype=float
    )
    q_mat = np.block(
        [
            [q_block, np.zeros((2, 2))],
            [np.zeros((2, 2)), q_block],
        ]
    )
    return f, q_mat


def ct_matrices(dt: float, omega: float, q: float) -> Tuple[np.ndarray, np.ndarray]:
    if abs(omega) < 1e-6:
        return cv_matrices(dt, q)
    s = math.sin(omega * dt)
    c = math.cos(omega * dt)
    f = np.array(
        [
            [1, 0, s / omega, -(1 - c) / omega],
            [0, 1, (1 - c) / omega, s / omega],
            [0, 0, c, -s],
            [0, 0, s, c],
        ],
        dtype=float,
    )
    q_mat = q * np.eye(4)
    return f, q_mat


def kf_predict(x: np.ndarray, p: np.ndarray, f: np.ndarray, q: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    x_pred = f @ x
    p_pred = f @ p @ f.T + q
    return x_pred, p_pred


def kf_update(
    x: np.ndarray,
    p: np.ndarray,
    z: np.ndarray,
    h: np.ndarray,
    r: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, float]:
    y = z - h @ x
    s = h @ p @ h.T + r
    k = p @ h.T @ np.linalg.inv(s)
    x_upd = x + k @ y
    p_upd = (np.eye(len(x)) - k @ h) @ p
    nis = float(y.T @ np.linalg.inv(s) @ y)
    return x_upd, p_upd, nis


def imm_filter(
    measurements: np.ndarray,
    config: ModelConfig,
    init_state: np.ndarray,
    init_cov: np.ndarray,
) -> Dict[str, np.ndarray]:
    dt = config.dt
    h = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=float)
    r = (config.r_pos**2) * np.eye(2)

    f_cv, q_cv = cv_matrices(dt, config.q_cv)
    f_ct, q_ct = ct_matrices(dt, config.omega, config.q_ct)
    models = [(f_cv, q_cv), (f_ct, q_ct)]

    mu = np.array([0.5, 0.5], dtype=float)
    p_ij = config.imm_transition

    x_models = [init_state.copy(), init_state.copy()]
    p_models = [init_cov.copy(), init_cov.copy()]
    nis_hist = []
    fused_states = []
    fused_covs = []

    for z in measurements:
        c_j = p_ij.T @ mu
        mix_probs = (p_ij * mu[:, None]) / c_j[None, :]

        mixed_x = []
        mixed_p = []
        for j in range(2):
            x_mix = sum(mix_probs[i, j] * x_models[i] for i in range(2))
            p_mix = np.zeros_like(init_cov)
            for i in range(2):
                dx = x_models[i] - x_mix
                p_mix += mix_probs[i, j] * (p_models[i] + np.outer(dx, dx))
            mixed_x.append(x_mix)
            mixed_p.append(p_mix)

        likelihoods = []
        for j, (f, q) in enumerate(models):
            x_pred, p_pred = kf_predict(mixed_x[j], mixed_p[j], f, q)
            x_upd, p_upd, nis = kf_update(x_pred, p_pred, z, h, r)
            x_models[j] = x_upd
            p_models[j] = p_upd
            likelihoods.append(math.exp(-0.5 * nis))
            nis_hist.append(nis)

        mu = c_j * np.array(likelihoods)
        mu = mu / mu.sum()

        x_fused = sum(mu[i] * x_models[i] for i in range(2))
        p_fused = sum(mu[i] * p_models[i] for i in range(2))
        fused_states.append(x_fused)
        fused_covs.append(p_fused)

    return {
        "state": fused_states[-1],
        "cov": fused_covs[-1],
        "state_hist": np.array(fused_states),
        "cov_hist": np.array(fused_covs),
        "nis": np.array(nis_hist),
    }


def vsmm_filter(
    rel_measurements: np.ndarray,
    config: ModelConfig,
    init_state: np.ndarray,
    init_cov: np.ndarray,
) -> Dict[str, np.ndarray]:
    f, q = cv_matrices(config.dt, config.q_vsmm)
    h = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=float)
    r = (config.r_pos**2) * np.eye(2)

    x = init_state.copy()
    p = init_cov.copy()
    nis_hist = []

    for z in rel_measurements:
        x_pred, p_pred = kf_predict(x, p, f, q)
        x, p, nis = kf_update(x_pred, p_pred, z, h, r)
        nis_hist.append(nis)

    return {"state": x, "cov": p, "nis": np.array(nis_hist)}


def simulate_pair(
    config: ModelConfig,
    d0: float,
    v_rel: float,
    formation: bool,
    rng: np.random.Generator,
) -> Tuple[np.ndarray, np.ndarray]:
    dt = config.dt
    steps = config.steps
    leader_state = np.array([0.0, 0.0, 250.0, 0.0])

    rel_angle = rng.uniform(0, 2 * math.pi)
    rel_pos = np.array([d0 * math.cos(rel_angle), d0 * math.sin(rel_angle)])
    rel_vel = np.array([v_rel * math.cos(rel_angle), v_rel * math.sin(rel_angle)])

    if formation:
        rel_vel *= 0.1
        rel_pos += rng.normal(scale=10.0, size=2)

    follower_state = np.array(
        [
            leader_state[0] + rel_pos[0],
            leader_state[1] + rel_pos[1],
            leader_state[2] + rel_vel[0],
            leader_state[3] + rel_vel[1],
        ]
    )

    leader_hist = []
    follower_hist = []

    for k in range(steps):
        omega = config.omega if k > steps // 2 else 0.0
        f_leader, q_leader = ct_matrices(dt, omega, config.q_cv)
        leader_state, _ = kf_predict(
            leader_state, np.zeros((4, 4)), f_leader, q_leader
        )
        leader_state += rng.normal(scale=0.5, size=4)

        if formation:
            follower_state[:2] = leader_state[:2] + rel_pos
            follower_state[2:] = leader_state[2:] + rng.normal(scale=0.2, size=2)
        else:
            follower_state[:2] += follower_state[2:] * dt
            follower_state[2:] += rng.normal(scale=0.5, size=2)

        leader_hist.append(leader_state.copy())
        follower_hist.append(follower_state.copy())

    leader_hist = np.array(leader_hist)
    follower_hist = np.array(follower_hist)
    noise = rng.normal(scale=config.r_pos, size=(steps, 2))
    z_leader = leader_hist[:, :2] + noise
    z_follower = follower_hist[:, :2] + rng.normal(scale=config.r_pos, size=(steps, 2))
    return z_leader, z_follower


def evaluate_boundary(
    config: ModelConfig,
    d_grid: Iterable[float],
    v_grid: Iterable[float],
    seed: int = 42,
) -> Dict[float, float]:
    rng = np.random.default_rng(seed)
    results: Dict[float, float] = {}
    init_state = np.zeros(4)
    init_cov = np.eye(4) * 1e3

    for d0 in d_grid:
        best_v = None
        for v_rel in v_grid:
            z1, z2 = simulate_pair(config, d0, v_rel, formation=True, rng=rng)
            rel_meas = z2 - z1

            imm1 = imm_filter(z1, config, init_state, init_cov)
            imm2 = imm_filter(z2, config, init_state, init_cov)

            r = (config.r_pos**2) * np.eye(2)
            nis_imm = []
            for step, z in enumerate(rel_meas):
                rel_pred = imm2["state_hist"][step][:2] - imm1["state_hist"][step][:2]
                rel_cov = (
                    imm1["cov_hist"][step][:2, :2]
                    + imm2["cov_hist"][step][:2, :2]
                )
                y = z - rel_pred
                s = rel_cov + r
                nis_imm.append(float(y.T @ np.linalg.inv(s) @ y))

            vsmm = vsmm_filter(rel_meas, config, init_state, init_cov)
            delta = np.mean(nis_imm) - np.mean(vsmm["nis"])
            if delta >= 0:
                best_v = v_rel

        results[d0] = best_v if best_v is not None else 0.0
    return results


def print_boundary(boundary: Dict[float, float]) -> None:
    print("Estimated boundary (max relative speed where VSMM wins):")
    for d0, v_rel in boundary.items():
        print(f"  distance={d0:6.1f} m -> v_rel_max={v_rel:6.1f} m/s")


def main() -> None:
    config = ModelConfig()
    d_grid = np.linspace(500, 3000, 6)
    v_grid = np.linspace(0, 60, 7)
    boundary = evaluate_boundary(config, d_grid, v_grid)
    print_boundary(boundary)


if __name__ == "__main__":
    main()
