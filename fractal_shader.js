/**
 * WebGL Fractal Background with Dead-Space Detection & Auto-Reverse.
 * Automatically zoom-out if the screen goes black, then resume once structures return.
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
    uniform vec2 u_fixX_h;
    uniform vec2 u_fixY_h;
    uniform vec2 u_zoom;
    out vec4 fragColor;

    // --- DS MATH (Emulated 48-bit Mantissa) ---
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
        vec3 a = vec3(0.015, 0.0, 0.05);   
        vec3 b = vec3(0.1, 0.7, 0.95);   
        vec3 c = vec3(1.0, 1.0, 1.0);
        vec3 d = vec3(0.65, 0.35, 0.45); 
        return a + b * cos(6.28318 * (c * t + d));
    }

    float get_iter(vec2 screen_coord) {
        vec2 rel_uv = (screen_coord * 2.0 - u_resolution.xy) / u_resolution.y;
        vec2 dx = ds_mul(vec2(rel_uv.x, 0.0), vec2(1.0 / u_zoom.x, 0.0));
        vec2 dy = ds_mul(vec2(rel_uv.y, 0.0), vec2(1.0 / u_zoom.x, 0.0));
        
        float iter = 0.0;
        float max_iter = 180.0 + 45.0 * log(u_zoom.x + 1.0);
        if (max_iter > 750.0) max_iter = 750.0;

        for (float i = 0.0; i < 750.0; i++) {
            if (i >= max_iter) break;
            vec2 fixX_dx = ds_mul(u_fixX_h, dx);
            vec2 fixY_dy = ds_mul(u_fixY_h, dy);
            vec2 fixX_dy = ds_mul(u_fixX_h, dy);
            vec2 fixY_dx = ds_mul(u_fixY_h, dx);
            vec2 dx2 = ds_mul(dx, dx);
            vec2 dy2 = ds_mul(dy, dy);
            vec2 dxdy = ds_mul(dx, dy);
            vec2 term1_x = ds_sub(fixX_dx, fixY_dy);
            term1_x = ds_add(term1_x, term1_x);
            dx = ds_add(term1_x, ds_sub(dx2, dy2));
            vec2 term1_y = ds_add(fixX_dy, fixY_dx);
            term1_y = ds_add(term1_y, term1_y);
            dy = ds_add(term1_y, ds_add(dxdy, dxdy));
            float cur_x = dx.x + u_fixX_h.x;
            float cur_y = dy.x + u_fixY_h.x;
            if (cur_x*cur_x + cur_y*cur_y > 1024.0) {
                float r2 = cur_x*cur_x + cur_y*cur_y;
                float nu = log2(log2(r2 + 0.00001) / 2.0);
                return i + 1.0 - nu;
            }
            iter++;
        }
        return max_iter;
    }

    void main() {
        float iter = get_iter(gl_FragCoord.xy);
        vec3 col = vec3(0.0);
        float max_iter = 180.0 + 45.0 * log(u_zoom.x + 1.0);
        if (max_iter > 750.0) max_iter = 750.0;

        if (iter < max_iter) {
            col = palette(iter * 0.02 + u_time * 0.008);
            col += vec3(0.15, 0.0, 0.35) * (2.0 / (iter * 0.04 + 0.1));
        } else {
            col = vec3(0.015, 0.0, 0.05); // Interior Color (Dead Space)
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
        if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { console.error(gl.getShaderInfoLog(s)); return null; }
        return s;
    }

    const program = gl.createProgram();
    gl.attachShader(program, createShader(gl, gl.VERTEX_SHADER, vertexShaderSource));
    gl.attachShader(program, createShader(gl, gl.FRAGMENT_SHADER, fragmentShaderSource));
    gl.linkProgram(program);
    gl.useProgram(program);

    const locRes = gl.getUniformLocation(program, "u_resolution");
    const locTime = gl.getUniformLocation(program, "u_time");
    const locFXH = gl.getUniformLocation(program, "u_fixX_h");
    const locFYH = gl.getUniformLocation(program, "u_fixY_h");
    const locZoom = gl.getUniformLocation(program, "u_zoom");

    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]), gl.STATIC_DRAW);
    const pos = gl.getAttribLocation(program, "a_position");
    gl.enableVertexAttribArray(pos);
    gl.vertexAttribPointer(pos, 2, gl.FLOAT, false, 0, 0);

    const startTime = Date.now();
    let currentZoomLog = 0;
    let zoomDirection = 1.0;
    let targetZoomRate = 0.075;
    let actualZoomRate = 0.075;
    let deadSpaceTime = 0;
    let recoversSince = 0;

    function splitDouble(d) {
        const hi = Math.fround(d);
        const lo = d - hi;
        return [hi, lo];
    }

    // --- CPU SIDE COMPLEXITY PROBE ---
    function cpuIter(cx, cy, fx, fy, ux, uy) {
        let dx = ux, dy = uy;
        let max_iter = 180 + 45 * Math.log(Math.exp(currentZoomLog) + 1);
        if (max_iter > 750) max_iter = 750;
        for (let i = 0; i < max_iter; i++) {
            let n_dx = 2 * (fx * dx - fy * dy) + (dx * dx - dy * dy);
            let n_dy = 2 * (fx * dy + fy * dx) + 2 * dx * dy;
            dx = n_dx; dy = n_dy;
            if ((dx + fx) * (dx + fx) + (dy + fy) * (dy + fy) > 1024) return i;
        }
        return max_iter;
    }

    function render() {
        const now = Date.now();
        const time = (now - startTime) * 0.001;

        const dpr = window.devicePixelRatio || 1;
        if (canvas.width !== Math.floor(canvas.clientWidth * dpr)) {
            canvas.width = Math.floor(canvas.clientWidth * dpr);
            canvas.height = Math.floor(canvas.clientHeight * dpr);
            gl.viewport(0, 0, canvas.width, canvas.height);
        }

        const morphRate = 0.035;
        const phi = time * morphRate;
        const cx = 0.35 * Math.cos(phi) - 0.1 * Math.cos(2.0 * phi);
        const cy = 0.35 * Math.sin(phi) - 0.1 * Math.sin(2.0 * phi);
        const wx = 1.0 - 4.0 * cx;
        const wy = -4.0 * cy;
        const r_w = Math.sqrt(wx * wx + wy * wy);
        let sx = Math.sqrt((r_w + wx) * 0.5);
        let sy = Math.sqrt((r_w - wx) * 0.5);
        if (wy < 0.0) sy = -sy;
        let fixX = (1.0 + sx) * 0.5;
        let fixY = sy * 0.5;

        // COMPLEXITY PROBE
        const zoom = Math.exp(currentZoomLog);
        const prX = (0.5 * 2.0 - 1.0) / (canvas.height / canvas.width); // Center point normalized
        const samples = [[0, 0], [0.1, 0.1], [-0.1, -0.1], [0.1, -0.1], [-0.1, 0.1]];
        let max_hits = 0;
        samples.forEach(s => {
            let it = cpuIter(cx, cy, fixX, fixY, s[0] / zoom, s[1] / zoom);
            if (it >= 745) max_hits++;
        });

        // BOUNCE LOGIC (Persistent Zoom-Out)
        if (max_hits >= 5) {
            deadSpaceTime += 0.016;
            if (deadSpaceTime > 1.5) zoomDirection = -1.0; // Reverse!
        } else {
            deadSpaceTime = 0;
        }

        // Smoothly adjust actual rate
        actualZoomRate = actualZoomRate * 0.98 + (targetZoomRate * zoomDirection) * 0.02;
        currentZoomLog += actualZoomRate * 0.016;

        const panRadius = 0.01 / zoom;
        fixX += panRadius * Math.cos(time * 0.15);
        fixY += panRadius * Math.sin(time * 0.15);

        gl.uniform2f(locRes, canvas.width, canvas.height);
        gl.uniform1f(locTime, time);
        gl.uniform2fv(locFXH, splitDouble(fixX));
        gl.uniform2fv(locFYH, splitDouble(fixY));
        gl.uniform2fv(locZoom, splitDouble(zoom));

        gl.drawArrays(gl.TRIANGLES, 0, 6);
        requestAnimationFrame(render);
    }
    requestAnimationFrame(render);
}

if (document.readyState === 'complete') initGL(); else window.addEventListener('load', initGL);
