"""
test_inertial2d.py — checks the 2D solver against solutions that are KNOWN,
before it is allowed near any Amsterdam result.

  T1  lake at rest     bumpy bed, flat water surface -> must stay at rest
                       (a solver that invents flow over a still lake is wrong)
  T2  mass balance     sources into a closed basin -> inflow == stored volume
  T3  flat basin       a filled flat basin equilibrates to uniform depth V/A
  T4  uniform flow     steady flow down an inclined channel reaches Manning's
                       normal depth  h = (q n / sqrt(S))^(3/5)   (tests friction)
  T5  drains           a sink at the low end removes water; overall mass closes

Run:  python3 test_inertial2d.py
"""
import numpy as np
from inertial2d import InertialSolver


def walls_ring(shape):
    w = np.zeros(shape, bool)
    w[0, :] = w[-1, :] = w[:, 0] = w[:, -1] = True
    return w


def t1_lake_at_rest():
    rng = np.random.default_rng(1)
    z = rng.uniform(0.0, 0.3, (60, 60)); w = walls_ring(z.shape)
    s = InertialSolver(z, 1.0, 0.03, walls=w)
    s.h = np.where(w, 0.0, 0.5 - z)
    v0 = s.stored_volume()
    for _ in range(400):
        s.step(dt=0.2)
    q = max(np.abs(s.qx).max(), np.abs(s.qy).max())
    dv = abs(s.stored_volume() - v0) / v0
    ok = q < 1e-9 and dv < 1e-9
    print(f"T1 lake at rest        max|q|={q:.2e} m2/s, volume drift={dv:.1e}   {'PASS' if ok else 'FAIL'}")
    return ok


def t2_mass_balance():
    rng = np.random.default_rng(2)
    z = rng.uniform(0.0, 0.5, (80, 80)); w = walls_ring(z.shape)
    s = InertialSolver(z, 1.0, 0.03, walls=w)
    for k in range(3000):
        s.step(sources=[(20, 20, 0.5), (60, 45, 0.3)] if k < 1500 else None)
    err = abs(s.in_volume - s.stored_volume()) / s.in_volume
    ok = err < 1e-9 and s.clipped_volume < 1e-9
    print(f"T2 mass balance        in={s.in_volume:.1f} m3, stored={s.stored_volume():.1f} m3, rel.err={err:.1e}, clipped={s.clipped_volume:.1e}   {'PASS' if ok else 'FAIL'}")
    return ok


def t3_flat_basin():
    z = np.zeros((50, 50)); w = walls_ring(z.shape)
    s = InertialSolver(z, 1.0, 0.03, walls=w)
    for k in range(2500):
        s.step(sources=[(10, 10, 1.0)] if k < 1000 else None)
    h = s.h[~w]
    V, A = s.in_volume, h.size
    mean_expected = V / A
    spread = h.std() / h.mean()
    ok = abs(h.mean() - mean_expected) / mean_expected < 1e-6 and spread < 0.03
    print(f"T3 flat basin          mean depth={h.mean()*100:.2f} cm (expected {mean_expected*100:.2f}), std/mean={spread:.3f}   {'PASS' if ok else 'FAIL'}")
    return ok


def t4_uniform_flow():
    # channel 300 m long, 6 m wide (walls on lateral sides), bed slope S along +x,
    # inflow q per unit width at the upstream end, free sink at the downstream end
    S, n, q = 0.01, 0.03, 0.05
    nx, ny, dx = 300, 8, 1.0
    x = np.arange(nx) * dx
    z = np.tile(-S * x, (ny, 1))
    w = np.zeros((ny, nx), bool); w[0, :] = w[-1, :] = True
    sinks = np.zeros((ny, nx), bool); sinks[:, -1] = True
    s = InertialSolver(z, dx, n, walls=w, sinks=sinks)
    width = ny - 2
    for _ in range(9000):
        s.step(sources=[(j, 1, q * dx / 1.0) for j in range(1, ny - 1)])  # q [m2/s] * dx -> Q [m3/s] per cell
    h_mid = s.h[1:-1, 140:160].mean()
    h_expected = (q * n / np.sqrt(S)) ** 0.6
    err = abs(h_mid - h_expected) / h_expected
    ok = err < 0.08
    print(f"T4 uniform flow        depth={h_mid*100:.2f} cm vs Manning {h_expected*100:.2f} cm (err {err*100:.1f}%)   {'PASS' if ok else 'FAIL'}")
    return ok


def t5_drains():
    z = np.zeros((40, 40)); z += np.linspace(0.5, 0.0, 40)[None, :]
    w = walls_ring(z.shape); sinks = np.zeros(z.shape, bool); sinks[:, -2] = True; w[:, -1] = True
    s = InertialSolver(z, 1.0, 0.03, walls=w, sinks=sinks)
    for k in range(6000):
        s.step(sources=[(20, 3, 0.4)] if k < 500 else None)
    closure = abs(s.in_volume - s.stored_volume() - s.out_volume) / s.in_volume
    drained = s.out_volume / s.in_volume
    ok = closure < 1e-9 and drained > 0.9 and s.clipped_volume < 1e-9
    print(f"T5 drains              in={s.in_volume:.1f}, out={s.out_volume:.1f}, stored={s.stored_volume():.2f} m3; closure err={closure:.1e}, drained {drained*100:.0f}%   {'PASS' if ok else 'FAIL'}")
    return ok


if __name__ == "__main__":
    results = [t1_lake_at_rest(), t2_mass_balance(), t3_flat_basin(), t4_uniform_flow(), t5_drains()]
    print("\nALL PASS" if all(results) else "\nFAILURES -- do not use the solver")
    raise SystemExit(0 if all(results) else 1)
