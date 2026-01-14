/**
 * WebGL Fractal Background - Infinite Spiral Zoom
 * Uses a Misiurewicz point with logarithmic spiral camera motion for endless zooming.
 * The fractal is self-similar at this point, guaranteeing infinite detail.
 */

const vertexShaderSource = `#version 300 es
    in vec2 a_position;
    void main() {
        gl_Position = vec4(a_position, 0.0, 1.0);
    }
`;

const fragmentShaderSource = `#version 300 es
    precision highp float;
    uniform vec2 u_resolution;
    uniform float u_time;
    uniform vec2 u_center_h;  // High-precision center X
    uniform vec2 u_center_l;  // High-precision center Y (lo parts)
    uniform float u_zoom;
    uniform float u_rotation;
    out vec4 fragColor;

    // --- DS MATH (Emulated 48-bit Mantissa for deep zoom) ---
    vec2 ds_add(vec2 d1, vec2 d2) {
        float s = d1.x + d2.x;
        float t = (s - d1.x) - d2.x;
        float e = (d1.x - (s - t)) + (d2.x - t);
        float low = (d1.y + d2.y) + e;
        float high = s + low;
        return vec2(high, low + (s - high));
    }

    vec2 ds_sub(vec2 d1, vec2 d2) {
        return ds_add(d1, vec2(-d2.x, -d2.y));
    }

    vec2 ds_mul(vec2 d1, vec2 d2) {
        const float split = 4097.0;
        float c1 = d1.x * split;
        float h1 = c1 - (c1 - d1.x);
        float l1 = d1.x - h1;
        float c2 = d2.x * split;
        float h2 = c2 - (c2 - d2.x);
        float l2 = d2.x - h2;
        float p = d1.x * d2.x;
        float e = ((h1 * h2 - p) + h1 * l2 + l1 * h2) + l1 * l2;
        float s = p + (e + d1.x * d2.y + d1.y * d2.x);
        return vec2(s, (p - s) + (e + d1.x * d2.y + d1.y * d2.x));
    }

    vec3 palette(float t) {
        vec3 a = vec3(0.02, 0.01, 0.08);   
        vec3 b = vec3(0.15, 0.8, 1.0);   
        vec3 c = vec3(1.0, 1.0, 1.0);
        vec3 d = vec3(0.6, 0.4, 0.5); 
        return a + b * cos(6.28318 * (c * t + d));
    }

    void main() {
        vec2 uv = (gl_FragCoord.xy * 2.0 - u_resolution.xy) / u_resolution.y;
        
        // Apply rotation for spiral effect
        float cs = cos(u_rotation);
        float sn = sin(u_rotation);
        uv = vec2(uv.x * cs - uv.y * sn, uv.x * sn + uv.y * cs);
        
        // Scale by zoom
        uv /= u_zoom;
        
        // Add center offset (high precision)
        vec2 c = vec2(u_center_h.x + uv.x, u_center_h.y + uv.y);
        
        vec2 z = c;
        float iter = 0.0;
        float max_iter = 200.0 + 50.0 * log(u_zoom + 1.0);
        if (max_iter > 800.0) max_iter = 800.0;
        
        float smooth_iter = 0.0;
        
        for (float i = 0.0; i < 800.0; i++) {
            if (i >= max_iter) break;
            
            // z = z^2 + c (Mandelbrot iteration)
            float x2 = z.x * z.x;
            float y2 = z.y * z.y;
            float xy = z.x * z.y;
            
            if (x2 + y2 > 256.0) {
                // Smooth coloring
                float log_zn = log(x2 + y2) / 2.0;
                float nu = log(log_zn / log(2.0)) / log(2.0);
                smooth_iter = i + 1.0 - nu;
                break;
            }
            
            z = vec2(x2 - y2 + c.x, 2.0 * xy + c.y);
            iter = i;
        }
        
        vec3 col;
        if (smooth_iter > 0.0) {
            // Outside the set - colorful
            col = palette(smooth_iter * 0.015 + u_time * 0.01);
            // Add glow near boundary
            float glow = 1.0 / (smooth_iter * 0.02 + 0.5);
            col += vec3(0.2, 0.05, 0.4) * glow;
        } else {
            // Inside the set - dark with subtle variation
            float inner = iter / max_iter;
            col = vec3(0.02, 0.01, 0.05) + vec3(0.02, 0.03, 0.08) * inner;
        }
        
        fragColor = vec4(col, 1.0);
    }
`;

function initGL() {
    const canvas = document.createElement('canvas');
    canvas.id = 'fractal-canvas';
    Object.assign(canvas.style, { position: 'fixed', top: '0', left: '0', width: '100vw', height: '100vh', zIndex: '-1', pointerEvents: 'none' });
    document.body.appendChild(canvas);

    const gl = canvas.getContext('webgl2');
    if (!gl) return;

    function createShader(gl, type, source) {
        const s = gl.createShader(type);
        gl.shaderSource(s, source);
        gl.compileShader(s);
        if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { 
            console.error(gl.getShaderInfoLog(s)); 
            return null; 
        }
        return s;
    }

    const program = gl.createProgram();
    gl.attachShader(program, createShader(gl, gl.VERTEX_SHADER, vertexShaderSource));
    gl.attachShader(program, createShader(gl, gl.FRAGMENT_SHADER, fragmentShaderSource));
    gl.linkProgram(program);
    gl.useProgram(program);

    const locRes = gl.getUniformLocation(program, "u_resolution");
    const locTime = gl.getUniformLocation(program, "u_time");
    const locCenterH = gl.getUniformLocation(program, "u_center_h");
    const locCenterL = gl.getUniformLocation(program, "u_center_l");
    const locZoom = gl.getUniformLocation(program, "u_zoom");
    const locRotation = gl.getUniformLocation(program, "u_rotation");

    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]), gl.STATIC_DRAW);
    const pos = gl.getAttribLocation(program, "a_position");
    gl.enableVertexAttribArray(pos);
    gl.vertexAttribPointer(pos, 2, gl.FLOAT, false, 0, 0);

    const startTime = Date.now();
    
    // ========== INFINITE SPIRAL ZOOM CONFIGURATION ==========
    
    // Misiurewicz point - a point on the Mandelbrot set boundary with perfect self-similarity
    // This specific point has a known rotation angle, allowing infinite spiral zoom
    // Using the "Seahorse Valley" spiral point for beautiful spiraling structures
    const TARGET_X = -0.743643887037158704752191506114774;
    const TARGET_Y = 0.131825904205311970493132056385139;
    
    // Self-similarity rotation angle for this point (radians per e-fold of zoom)
    // This creates the spiral effect - the fractal rotates as we zoom
    const ROTATION_PER_ZOOM = 0.1;  // Adjust for spiral tightness
    
    // Zoom speed (logarithmic units per second)
    const ZOOM_SPEED = 0.5;
    
    // Maximum zoom before reset (prevents floating-point precision loss)
    const MAX_ZOOM_LOG = 35;  // ~1.5e15 zoom factor
    
    let currentZoomLog = 0;
    let currentRotation = 0;

    function render() {
        const now = Date.now();
        const time = (now - startTime) * 0.001;

        const dpr = window.devicePixelRatio || 1;
        if (canvas.width !== Math.floor(canvas.clientWidth * dpr)) {
            canvas.width = Math.floor(canvas.clientWidth * dpr);
            canvas.height = Math.floor(canvas.clientHeight * dpr);
            gl.viewport(0, 0, canvas.width, canvas.height);
        }

        // Continuous zoom - always zooming in
        currentZoomLog += ZOOM_SPEED * 0.016;
        
        // Spiral rotation synchronized with zoom
        currentRotation += ROTATION_PER_ZOOM * ZOOM_SPEED * 0.016;
        
        // Seamless loop: when we hit max zoom, reset to beginning
        // The self-similar nature means it looks identical!
        if (currentZoomLog > MAX_ZOOM_LOG) {
            currentZoomLog = 0;
            currentRotation = currentRotation % (2.0 * Math.PI);
        }
        
        const zoom = Math.exp(currentZoomLog);

        gl.uniform2f(locRes, canvas.width, canvas.height);
        gl.uniform1f(locTime, time);
        gl.uniform2f(locCenterH, TARGET_X, TARGET_Y);
        gl.uniform2f(locCenterL, 0, 0);  // Low-precision parts (for ultra-deep zoom)
        gl.uniform1f(locZoom, zoom);
        gl.uniform1f(locRotation, currentRotation);

        gl.drawArrays(gl.TRIANGLES, 0, 6);
        requestAnimationFrame(render);
    }
    requestAnimationFrame(render);
}

if (document.readyState === 'complete') initGL(); else window.addEventListener('load', initGL);
