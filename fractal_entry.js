
(function () {
    const vertexShaderSource = `#version 300 es
        in vec2 a_position;
        void main() { gl_Position = vec4(a_position, 0.0, 1.0); }
    `;

    const fragmentShaderSource = `#version 300 es
        precision highp float;
        uniform vec2 u_resolution;
        uniform float u_time;
        uniform vec2 u_fixX_h;
        uniform vec2 u_fixY_h;
        uniform vec2 u_zoom;
        out vec4 fragColor;

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
            vec3 a = vec3(0.01, 0.05, 0.1); vec3 b = vec3(0.0, 0.8, 0.4); 
            vec3 c = vec3(1.0, 1.0, 1.0); vec3 d = vec3(0.2, 0.5, 0.8);
            return a + b * cos(6.28318 * (c * t + d));
        }
        float get_iter(vec2 screen_coord) {
            vec2 rel_uv = (screen_coord * 2.0 - u_resolution.xy) / u_resolution.y;
            vec2 dx = ds_mul(vec2(rel_uv.x, 0.0), vec2(1.0 / u_zoom.x, 0.0));
            vec2 dy = ds_mul(vec2(rel_uv.y, 0.0), vec2(1.0 / u_zoom.x, 0.0));
            float max_iter = 180.0 + 45.0 * log(u_zoom.x + 1.0);
            if (max_iter > 750.0) max_iter = 750.0;
            for (float i = 0.0; i < 750.0; i++) {
                if (i >= max_iter) break;
                float nx = 2.0 * (u_fixX_h.x * dx.x - u_fixY_h.x * dy.x) + (dx.x * dx.x - dy.x * dy.x);
                float ny = 2.0 * (u_fixX_h.x * dy.x + u_fixY_h.x * dx.x) + 2.0 * dx.x * dy.x;
                dx.x = nx; dy.x = ny;
                float r2 = (dx.x + u_fixX_h.x)*(dx.x + u_fixX_h.x) + (dy.x + u_fixY_h.x)*(dy.x + u_fixY_h.x);
                if (r2 > 1024.0) return i + 1.0 - log2(log2(r2)/2.0);
            }
            return max_iter;
        }
        void main() {
            float it = get_iter(gl_FragCoord.xy);
            float max_it = 180.0 + 45.0 * log(u_zoom.x + 1.0);
            if (max_it > 750.0) max_it = 750.0;
            vec3 col = (it < max_it) ? palette(it * 0.02 + u_time * 0.01) : vec3(0.005, 0.01, 0.02);
            fragColor = vec4(col, 1.0);
        }
    `;

    function start() {
        if (document.getElementById('fractal-canvas')) return;
        const canvas = document.createElement('canvas');
        canvas.id = 'fractal-canvas';
        canvas.style.position = 'fixed';
        canvas.style.top = '0';
        canvas.style.left = '0';
        canvas.style.width = '100vw';
        canvas.style.height = '100vh';
        canvas.style.zIndex = '-1';
        canvas.style.pointerEvents = 'none';
        document.body.appendChild(canvas);

        const gl = canvas.getContext('webgl2');
        if (!gl) return;

        const program = gl.createProgram();
        const vs = gl.createShader(gl.VERTEX_SHADER);
        gl.shaderSource(vs, vertexShaderSource); gl.compileShader(vs);
        const fs = gl.createShader(gl.FRAGMENT_SHADER);
        gl.shaderSource(fs, fragmentShaderSource); gl.compileShader(fs);
        gl.attachShader(program, vs); gl.attachShader(program, fs);
        gl.linkProgram(program); gl.useProgram(program);

        const buffer = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]), gl.STATIC_DRAW);
        const pos = gl.getAttribLocation(program, "a_position");
        gl.enableVertexAttribArray(pos); gl.vertexAttribPointer(pos, 2, gl.FLOAT, false, 0, 0);

        const locRes = gl.getUniformLocation(program, "u_resolution");
        const locTime = gl.getUniformLocation(program, "u_time");
        const locFXH = gl.getUniformLocation(program, "u_fixX_h");
        const locFYH = gl.getUniformLocation(program, "u_fixY_h");
        const locZoom = gl.getUniformLocation(program, "u_zoom");

        let currentZoomLog = 80.0;
        const startTime = Date.now();

        function render() {
            const time = (Date.now() - startTime) * 0.001;
            canvas.width = window.innerWidth; canvas.height = window.innerHeight;
            gl.viewport(0, 0, canvas.width, canvas.height);
            currentZoomLog -= 0.1 * 0.016;
            const zoom = Math.exp(currentZoomLog);
            const cx = -0.743644786; const cy = 0.131825963;
            gl.uniform2f(locRes, canvas.width, canvas.height);
            gl.uniform1f(locTime, time);
            gl.uniform2f(locFXH, cx, 0.0); gl.uniform2f(locFYH, cy, 0.0);
            gl.uniform2f(locZoom, zoom, 0.0);
            gl.drawArrays(gl.TRIANGLES, 0, 6);
            requestAnimationFrame(render);
        }
        render();
    }

    const attempt = () => {
        if (document.body) { start(); }
        else { setTimeout(attempt, 100); }
    };
    attempt();
})();
