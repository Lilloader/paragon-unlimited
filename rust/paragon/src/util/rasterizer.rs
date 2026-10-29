//! Paragon Unlimited: small software rasterizer for model previews (no GPU needed).
//!
//! Orthographic triangles with a depth buffer, nearest-neighbour texturing (wrap),
//! alpha cut-out and simple Lambert lighting. Vertices arrive already projected:
//! x, y in pixels, z = depth (larger is closer to the viewer).

pub struct MeshData<'a> {
    pub positions: &'a [f32], // x, y, z per vertex
    pub normals: &'a [f32],   // x, y, z per vertex (view space), may be empty
    pub uvs: &'a [f32],       // u, v per vertex, may be empty
    pub indices: &'a [u32],   // 3 per triangle
    pub texture: &'a [u8],    // RGBA8, may be empty
    pub tex_width: usize,
    pub tex_height: usize,
}

/// Bilinear texture lookup with wrapping; v = 0 is the bottom row (3DS convention).
fn sample_bilinear(tex: &[u8], w: usize, h: usize, u: f32, v: f32) -> [f32; 4] {
    let fu = (u - u.floor()) * w as f32 - 0.5;
    let fv = (1.0 - (v - v.floor())) * h as f32 - 0.5;
    let x0 = fu.floor();
    let y0 = fv.floor();
    let tx = fu - x0;
    let ty = fv - y0;
    let wrap = |i: f32, n: usize| -> usize { (i as isize).rem_euclid(n as isize) as usize };
    let (xa, xb) = (wrap(x0, w), wrap(x0 + 1.0, w));
    let (ya, yb) = (wrap(y0, h), wrap(y0 + 1.0, h));
    let px = |x: usize, y: usize, k: usize| tex[(y * w + x) * 4 + k] as f32;
    let mut out = [0.0f32; 4];
    for k in 0..4 {
        let top = px(xa, ya, k) * (1.0 - tx) + px(xb, ya, k) * tx;
        let bot = px(xa, yb, k) * (1.0 - tx) + px(xb, yb, k) * tx;
        out[k] = top * (1.0 - ty) + bot * ty;
    }
    out
}

pub fn render(
    width: usize,
    height: usize,
    meshes: &[MeshData],
    light: [f32; 3],
    background: [u8; 4],
) -> Result<Vec<u8>, String> {
    if width == 0 || height == 0 || width > 8192 || height > 8192 {
        return Err("Bad image size".to_string());
    }
    let mut color = vec![0u8; width * height * 4];
    for px in color.chunks_mut(4) {
        px.copy_from_slice(&background);
    }
    let mut depth = vec![f32::NEG_INFINITY; width * height];
    let ll = (light[0] * light[0] + light[1] * light[1] + light[2] * light[2]).sqrt().max(1e-6);
    let light = [light[0] / ll, light[1] / ll, light[2] / ll];

    for m in meshes {
        let vcount = m.positions.len() / 3;
        let has_uv = m.uvs.len() >= vcount * 2 && vcount > 0;
        let has_n = m.normals.len() >= vcount * 3 && vcount > 0;
        let has_tex = m.tex_width > 0 && m.tex_height > 0 && m.texture.len() >= m.tex_width * m.tex_height * 4;
        for tri in m.indices.chunks(3) {
            if tri.len() < 3 {
                break;
            }
            let (a, b, c) = (tri[0] as usize, tri[1] as usize, tri[2] as usize);
            if a >= vcount || b >= vcount || c >= vcount {
                continue;
            }
            let p = |i: usize| (m.positions[i * 3], m.positions[i * 3 + 1], m.positions[i * 3 + 2]);
            let (x0, y0, z0) = p(a);
            let (x1, y1, z1) = p(b);
            let (x2, y2, z2) = p(c);
            let area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0);
            if area.abs() < 1e-12 || !area.is_finite() {
                continue;
            }
            let minx = x0.min(x1).min(x2).floor().max(0.0) as isize;
            let maxx = x0.max(x1).max(x2).ceil().min(width as f32 - 1.0) as isize;
            let miny = y0.min(y1).min(y2).floor().max(0.0) as isize;
            let maxy = y0.max(y1).max(y2).ceil().min(height as f32 - 1.0) as isize;
            if maxx < minx || maxy < miny {
                continue;
            }
            for py in miny..=maxy {
                let fy = py as f32 + 0.5;
                for px in minx..=maxx {
                    let fx = px as f32 + 0.5;
                    let w0 = ((x1 - fx) * (y2 - fy) - (x2 - fx) * (y1 - fy)) / area;
                    let w1 = ((x2 - fx) * (y0 - fy) - (x0 - fx) * (y2 - fy)) / area;
                    let w2 = 1.0 - w0 - w1;
                    if w0 < -1e-5 || w1 < -1e-5 || w2 < -1e-5 {
                        continue;
                    }
                    let z = w0 * z0 + w1 * z1 + w2 * z2;
                    let di = py as usize * width + px as usize;
                    if z <= depth[di] {
                        continue;
                    }
                    let mut col = [190.0f32, 190.0, 190.0, 255.0];
                    if has_tex && has_uv {
                        let u = w0 * m.uvs[a * 2] + w1 * m.uvs[b * 2] + w2 * m.uvs[c * 2];
                        let v = w0 * m.uvs[a * 2 + 1] + w1 * m.uvs[b * 2 + 1] + w2 * m.uvs[c * 2 + 1];
                        col = sample_bilinear(m.texture, m.tex_width, m.tex_height, u, v);
                        if col[3] < 24.0 {
                            continue; // cut-out (hair tips, eyelashes)
                        }
                    }
                    let mut shade = 1.0f32;
                    if has_n {
                        let n = |i: usize, k: usize| m.normals[i * 3 + k];
                        let nx = w0 * n(a, 0) + w1 * n(b, 0) + w2 * n(c, 0);
                        let ny = w0 * n(a, 1) + w1 * n(b, 1) + w2 * n(c, 1);
                        let nz = w0 * n(a, 2) + w1 * n(b, 2) + w2 * n(c, 2);
                        let len = (nx * nx + ny * ny + nz * nz).sqrt();
                        if len > 1e-6 {
                            let d = (nx * light[0] + ny * light[1] + nz * light[2]) / len;
                            shade = 0.5 + 0.5 * d.max(0.0);
                        }
                    }
                    depth[di] = z;
                    let o = di * 4;
                    color[o] = (col[0] * shade).min(255.0) as u8;
                    color[o + 1] = (col[1] * shade).min(255.0) as u8;
                    color[o + 2] = (col[2] * shade).min(255.0) as u8;
                    color[o + 3] = 255;
                }
            }
        }
    }
    Ok(color)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn draws_a_triangle_with_depth() {
        let pos = [1.0f32, 1.0, 0.0, 9.0, 1.0, 0.0, 1.0, 9.0, 0.0];
        let near = [1.0f32, 1.0, 1.0, 9.0, 1.0, 1.0, 9.0, 9.0, 1.0];
        let idx = [0u32, 1, 2];
        let a = MeshData { positions: &pos, normals: &[], uvs: &[], indices: &idx, texture: &[], tex_width: 0, tex_height: 0 };
        let tex = [255u8, 0, 0, 255];
        let uv = [0.5f32, 0.5, 0.5, 0.5, 0.5, 0.5];
        let b = MeshData { positions: &near, normals: &[], uvs: &uv, indices: &idx, texture: &tex, tex_width: 1, tex_height: 1 };
        let img = render(10, 10, &[a, b], [0.0, 0.0, 1.0], [0, 0, 0, 255]).unwrap();
        assert_eq!(&img[(6 * 10 + 2) * 4..(6 * 10 + 2) * 4 + 4], &[190, 190, 190, 255]);
        assert_eq!(&img[(2 * 10 + 7) * 4..(2 * 10 + 7) * 4 + 4], &[255, 0, 0, 255]);
        assert_eq!(&img[(9 * 10 + 0) * 4..(9 * 10 + 0) * 4 + 4], &[0, 0, 0, 255]);
    }
}
