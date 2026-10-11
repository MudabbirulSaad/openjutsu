import { useEffect, useRef } from "react";
export function DepthContour({ frozen }: { frozen: boolean }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const el = canvas.current!;
    const gl = el.getContext("webgl2", {
      antialias: false,
      powerPreference: "low-power",
    });
    if (!gl) return;
    const shader = (type: number, source: string) => {
      const s = gl.createShader(type)!;
      gl.shaderSource(s, source);
      gl.compileShader(s);
      return s;
    };
    const program = gl.createProgram()!;
    const v = shader(
      gl.VERTEX_SHADER,
      "#version 300 es\nvoid main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);gl_Position=vec4(p*2.-1.,0.,1.);}",
    );
    const f = shader(
      gl.FRAGMENT_SHADER,
      "#version 300 es\nprecision mediump float;uniform float t;out vec4 c;void main(){vec2 p=gl_FragCoord.xy/vec2(220.,44.);float d=sin(p.x*6.+t*.08)*.18+sin(p.x*13.+p.y*2.)*.08+p.y;float line=1.-smoothstep(.02,.075,abs(fract(d*9.)-.5));c=vec4(.45,.55,.65,line*.3);}",
    );
    gl.attachShader(program, v);
    gl.attachShader(program, f);
    gl.linkProgram(program);
    gl.useProgram(program);
    const uniform = gl.getUniformLocation(program, "t");
    let frame = 0;
    const draw = (t: number) => {
      gl.viewport(0, 0, 220, 44);
      gl.uniform1f(uniform, t / 1000);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    const tick = (t: number) => {
      draw(t);
      if (!frozen && !document.hidden && !reduced.matches)
        frame = requestAnimationFrame(tick);
    };
    const resume = () => {
      cancelAnimationFrame(frame);
      tick(performance.now());
    };
    document.addEventListener("visibilitychange", resume);
    reduced.addEventListener("change", resume);
    resume();
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("visibilitychange", resume);
      reduced.removeEventListener("change", resume);
      gl.deleteProgram(program);
      gl.deleteShader(v);
      gl.deleteShader(f);
    };
  }, [frozen]);
  return (
    <canvas
      ref={canvas}
      width={220}
      height={44}
      aria-hidden="true"
      className="contour"
    />
  );
}
