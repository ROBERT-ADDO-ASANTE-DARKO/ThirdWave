"""
inertial2d.py — a small 2D shallow-water solver for urban surface flooding:
the local-inertial ("acceleration") formulation of Bates, Horritt & Fewtrell
(2010, J. Hydrology 387) -- the scheme behind LISFLOOD-FP's inertial solver.

Why this and not a full Saint-Venant solver: it drops only the convective
acceleration term, keeps local inertia, so it captures the fast street-scale
flow of a pipe overflow far better than a pure diffusive wave, while
remaining ~30 lines of vectorised numpy that can be TESTED against known
solutions (see test_inertial2d.py). It is a research-grade approximation,
not a substitute for a validated commercial 2D engine, and it is not
calibrated to any observed flood.

Grid conventions
  z[j, i]   bed elevation (m); rows j run in the +y direction of the array
  h[j, i]   water depth (m)
  qx[j, i]  flux per unit width (m^2/s) across the face between (j,i) and
            (j,i+1); positive = toward +i.  qy likewise between (j,i)/(j+1,i).
  Walls     cells raised to WALL_Z: face depth -> 0, so no flux passes.
  Sinks     boolean mask: water reaching these cells is removed (canals /
            open domain edge) and accumulated in `out_volume`.

Face flux update (explicit, semi-implicit friction):
    q' = ( q - g h_f dt d(eta)/dx ) / ( 1 + g dt n^2 |q| / h_f^(7/3) )
    h_f = max(eta_i, eta_j) - max(z_i, z_j),   eta = z + h
with a cell-based positivity limiter so a cell can never give away more
water than it holds (clipped mass is counted and tested to stay ~0), and CFL dt = alpha dx / sqrt(g h_max).
"""

from __future__ import annotations

import numpy as np

G = 9.81
WALL_Z = 1.0e3
H_MIN = 1.0e-4          # m; faces shallower than this carry no flux


class InertialSolver:
    def __init__(self, z: np.ndarray, dx: float, manning_n: float = 0.03,
                 walls: np.ndarray | None = None, sinks: np.ndarray | None = None,
                 alpha: float = 0.7, dt_max: float = 2.0):
        self.z = z.astype(np.float64).copy()
        if walls is not None:
            self.z[walls] = WALL_Z
        self.walls = walls if walls is not None else np.zeros(z.shape, bool)
        self.sinks = sinks if sinks is not None else np.zeros(z.shape, bool)
        self.dx = float(dx)
        # scalar only: a spatially varying n would need per-face averaging, and
        # accepting an array here while silently ignoring it would be a wrong path
        self.n2 = float(manning_n) ** 2
        self.alpha, self.dt_max = alpha, dt_max
        ny, nx = z.shape
        self.h = np.zeros((ny, nx))
        self.qx = np.zeros((ny, nx - 1))
        self.qy = np.zeros((ny - 1, nx))
        self.t = 0.0
        self.in_volume = 0.0
        self.out_volume = 0.0
        self.max_h = np.zeros((ny, nx))
        self.clipped_volume = 0.0   # mass created by clipping negatives; must stay ~0

    # -- helpers -----------------------------------------------------------
    def stored_volume(self) -> float:
        return float(self.h[~self.walls].sum() * self.dx ** 2)

    def _face_depth(self, eta_a, eta_b, z_a, z_b):
        return np.maximum(np.maximum(eta_a, eta_b) - np.maximum(z_a, z_b), 0.0)

    def _flux(self, q, eta_a, eta_b, z_a, z_b, h_a, h_b, dt):
        hf = self._face_depth(eta_a, eta_b, z_a, z_b)
        wet = hf > H_MIN
        hf_s = np.where(wet, hf, 1.0)
        slope = (eta_b - eta_a) / self.dx
        n2 = self.n2
        qn = (q - G * hf_s * dt * slope) / (1.0 + G * dt * n2 * np.abs(q) / hf_s ** (7.0 / 3.0))
        return np.where(wet, qn, 0.0)

    # -- one step ----------------------------------------------------------
    def step(self, sources: list[tuple[int, int, float]] | None = None, dt: float | None = None) -> float:
        """Advance one CFL-limited step. sources = [(j, i, Q m^3/s), ...]."""
        h, z = self.h, self.z
        if dt is None:
            hmax = float(h[~self.walls].max()) if h.any() else 0.0
            dt = self.dt_max if hmax < 1e-6 else min(self.dt_max, self.alpha * self.dx / np.sqrt(G * hmax))
        eta = z + h
        qx = self._flux(self.qx, eta[:, :-1], eta[:, 1:], z[:, :-1], z[:, 1:], h[:, :-1], h[:, 1:], dt)
        qy = self._flux(self.qy, eta[:-1, :], eta[1:, :], z[:-1, :], z[1:, :], h[:-1, :], h[1:, :], dt)
        k = dt / self.dx

        # Cell-based positivity limiter: total water leaving a cell in this step
        # may not exceed the water it holds; scale that cell's OUTgoing fluxes
        # down if it would. (A face-level "quarter of the donor" cap was tried
        # first and failed the uniform-flow test -- it throttled channel flow
        # that legitimately sends nearly everything through one face.)
        out = np.zeros_like(h)
        out[:, :-1] += np.maximum(qx, 0.0)      # leaves (j,i) through its +x face
        out[:, 1:] += np.maximum(-qx, 0.0)      # leaves (j,i+1) through its -x face
        out[:-1, :] += np.maximum(qy, 0.0)
        out[1:, :] += np.maximum(-qy, 0.0)
        out *= k
        f = np.where(out > h, h / np.where(out > 0, out, 1.0), 1.0)
        qx = np.where(qx > 0, qx * f[:, :-1], qx * f[:, 1:])
        qy = np.where(qy > 0, qy * f[:-1, :], qy * f[1:, :])
        self.qx, self.qy = qx, qy

        dh = np.zeros_like(h)
        dh[:, :-1] -= qx * k
        dh[:, 1:] += qx * k
        dh[:-1, :] -= qy * k
        dh[1:, :] += qy * k
        h_new = h + dh
        # any negative depth here is mass the scheme would CREATE by clipping:
        # count it so a leak can never hide (tests assert this stays ~0)
        self.clipped_volume += float(-np.minimum(h_new, 0.0).sum() * self.dx ** 2)
        h = np.maximum(h_new, 0.0)
        if sources:
            for j, i, Q in sources:
                h[j, i] += Q * dt / self.dx ** 2
                self.in_volume += Q * dt
        if self.sinks.any():
            self.out_volume += float(h[self.sinks].sum() * self.dx ** 2)
            h[self.sinks] = 0.0
        h[self.walls] = 0.0
        self.h = h
        np.maximum(self.max_h, h, out=self.max_h)
        self.t += dt
        return dt
