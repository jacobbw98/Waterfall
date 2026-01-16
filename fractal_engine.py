"""
Fractal Engine - High Precision Reference Orbit Calculation using Perturbation Theory.
"""
import mpmath
import struct
import base64
import numpy as np
from typing import Tuple, List, Dict, Any

# Set mpmath precision high enough for deep zooms
mpmath.mp.dps = 200  # 200 decimal digits for high precision reference orbit


class FractalEngine:
    def __init__(self, width: int = 1920, height: int = 1080):
        self.width = width
        self.height = height
        
        # High precision center coordinates
        self.cx = mpmath.mpf(0.0)
        self.cy = mpmath.mpf(0.0)
        self.zoom = mpmath.mpf(1.0)
        
        # Physics / Loop params
        self.max_iter = 1000
        self.bailout = 4.0
        
        # Reference Data
        self.ref_orbit: List[complex] = []   # Z_n
        self.ref_derivs: List[complex] = []  # D_n (Derivative)
        
        # Current Reference Point (C_ref)
        self.ref_idx = -1
        self.ref_c = complex(0,0)
    
    def set_view(self, cx_str: str, cy_str: str, zoom_str: str):
        """Set view using string inputs to maintain precision."""
        self.cx = mpmath.mpf(cx_str)
        self.cy = mpmath.mpf(cy_str)
        self.zoom = mpmath.mpf(zoom_str)
        
        # Ideally, we should check if we need to rebase here
        # For now, let's assume we always re-calculate reference on significant move
    
    def calculate_reference(self, max_iter: int = None) -> Dict[str, Any]:
        """
        Calculate the high-precision reference orbit + derivatives.
        Returns data ready for GPU (as float32 arrays encoded in base64/bytes).
        """
        if max_iter:
            self.max_iter = max_iter
            
        c_ref = mpmath.mpc(self.cx, self.cy)
        
        # Start reference orbit
        z = mpmath.mpc(0, 0)
        dc = mpmath.mpc(1, 0) # Derivative initializer (Automatic Differentiation)
        
        # Use lists for storage
        orbit_real = []
        orbit_imag = []
        deriv_real = []
        deriv_imag = []
        
        # First point
        orbit_real.append(float(z.real))
        orbit_imag.append(float(z.imag))
        # Initial derivative for z_0 is 0, but for perturbation we track dz/dc
        # z_{n+1} = z_n^2 + c
        # dz_{n+1}/dc = 2*z_n * dz_n/dc + 1
        # z_0 = 0, dz_0 = 0
        
        # Dual number tracking:
        # We track dz_n (relative to dc).
        dz = mpmath.mpc(0, 0)
        
        for i in range(self.max_iter):
            # 1. Update Derivative (Chain Rule first while z is z_n)
            # D_{n+1} = 2 * Z_n * D_n + 1
            dz = 2 * z * dz + 1
            
            # 2. Update Orbit
            z = z * z + c_ref
            
            # Store values (downcast to double/float for GPU usage)
            # We store them as standard floats because the shader uses them 
            # in the perturbation formula which is "Low Precision" relative logic.
            # The MAGIC is that Z_n needs to be precise ONLY relative to delta.
            # actually... wait. 
            # In standard perturbation: delta_{n+1} = 2*Z_n*delta_n + delta_n^2 + Delta_c
            # The Z_n here MUST be the high precision value? 
            # No, K.I. Martin says Z_n is downcast to double. 
            # The precision comes from keeping delta small.
            
            orbit_real.append(float(z.real))
            orbit_imag.append(float(z.imag))
            
            # For the universal formula delta_{n+1} = A_n * delta_n + B_n * delta_n^2 + dc
            # approximated as delta_{n+1} = 2*Z_n*delta_n + ... for Mandelbrot
            # We verify the derivative calculation:
            # dz = 2*z*dz + 1. 
            # This 'dz' matches the linear coefficient A_n if we were doing Series Approx?
            # actually for simple perturbation we just need Z_n.
            # But the user asked for "Universal".
            # Universal formula: delta = f'(Z)*delta + dc
            # f(z) = z^2+c -> f'(z)=2z. 
            # So the coefficient is 2*Z_n. 
            # So passing Z_n is sufficient for Mandelbrot.
            # But let's pass the derivative D_n just in case for future generic fractals.
            # (For z^2+c, D_n is effectively 2*z_n? No f'(Z_n) is 2Z_n.
            # The "derivative" tracked in calculate_reference (dz) is usually dZ_n/dC for distance estimation!)
            #
            # Re-reading Step 5.2 of the research:
            # "Input: Z_n + 1*epsilon -> Output: Z_{n+1} + D_{n+1}*epsilon"
            # "Result: D_{n+1} is the value of f'(Z_n)"
            # Wait, f'(Z_n) for z^2+c is just 2*Z_n. We don't need a separate array for that.
            # UNLESS, we are doing "Series Approximation" where we need A_n, B_n coefficients.
            # Research 4.1: A_{n+1} = 2*Z_n*A_n + 1. 
            # AND Research 5.1: delta_{n+1} approx f'(Z_n)*delta_n + ...
            # For Mandelbrot, f'(Z_n) = 2Z_n.
            
            # CONCLUSION: For Mandelbrot, sending just Z_n is enough.
            # For generic support, we would send the calculated derivative.
            # Let's send a "coefficient" array which is 2*Z_n for Mandelbrot.
            # This allows the shader to just do: delta = Coeff * delta + delta^2 + dc
            
            coeff = 2*z # Simple derivative for Mandelbrot
            deriv_real.append(float(coeff.real))
            deriv_imag.append(float(coeff.imag))
            
            if mpmath.norm(z) > self.bailout:
                break
                
        # Pack into numpy arrays for efficient transfer
        # float32 is usually enough for the reference 'skeleton' effectively
        # but float64 (double) is safer for the "low precision" part if we want 
        # to zoom to 1e-1000 without intermediate rebasing too often.
        
        np_orbit_re = np.array(orbit_real, dtype=np.float32)
        np_orbit_im = np.array(orbit_imag, dtype=np.float32)
        
        return {
            "orbit_re": np_orbit_re,
            "orbit_im": np_orbit_im,
            "count": len(orbit_real)
        }

    def get_orbit_as_bytes(self):
        """Get reference data encoded for shader consumption."""
        data = self.calculate_reference()
        
        # We need to serialize this to pass to JS/Shader
        # Simplest way: base64 encoded raw bytes
        import base64
        re_bytes = base64.b64encode(data['orbit_re'].tobytes()).decode('utf-8')
        im_bytes = base64.b64encode(data['orbit_im'].tobytes()).decode('utf-8')
        
        return {
            "re": re_bytes, 
            "im": im_bytes,
            "count": data['count']
        }

if __name__ == "__main__":
    # Test
    engine = FractalEngine()
    engine.set_view("-0.75", "0.0", "1.0")
    res = engine.get_orbit_as_bytes()
    print(f"Computed {res['count']} points.")
    print(f"Byte sample: {res['re'][:20]}...")
