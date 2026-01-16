import mpmath

# Test Misiurewicz point with VERY high precision
mpmath.mp.dps = 200  # 200 decimal digits

# Seahorse Valley Misiurewicz point
c = mpmath.mpf("-0.743643887037158704752191506114774") + mpmath.mpf("0.131825904205311970493132056385139") * 1j

z = mpmath.mpc(0, 0)
escaped = False
max_mag = 0

for i in range(20000):
    z = z * z + c
    mag = float(mpmath.fabs(z))
    if mag > max_mag:
        max_mag = mag
    if mag > 1e10:  # Very high bailout
        escaped = True
        print(f"ESCAPED at iteration {i}, |z| = {mag}")
        break
    if i < 20 or i % 1000 == 0:
        print(f"Iter {i}: |z| = {mag:.6f}")

if not escaped:
    print(f"Did NOT escape after 20000 iterations! Max |z| = {max_mag:.6f}")
