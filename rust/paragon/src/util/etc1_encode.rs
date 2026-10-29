//! Paragon Unlimited: ETC1 / ETC1A4 encoder (3DS tile order), the inverse of mila::etc1::decode.
//!
//! Std only, so it can be unit-tested with plain rustc. Quality-oriented but simple:
//! both flip orientations, differential and individual modes, all 8 modifier tables,
//! and a small luminance search around each sub-block's average color.

const MODIFIERS: [[i32; 2]; 8] = [
    [2, 8],
    [5, 17],
    [9, 29],
    [13, 42],
    [18, 60],
    [24, 80],
    [33, 106],
    [47, 183],
];

#[derive(Clone, Copy)]
struct Px {
    rgb: [i32; 3],
    w: i32, // 0 = fully transparent (color does not matter)
}

fn expand5(c: i32) -> i32 {
    (c << 3) | ((c >> 2) & 7)
}

fn expand4(c: i32) -> i32 {
    c * 0x11
}

fn clamp255(v: i32) -> i32 {
    v.clamp(0, 255)
}

/// Best table + per-pixel indices for one half with a fixed (expanded) base color.
/// Returns (error, table, [index per pixel] where index = (sign << 1) | amount_bit).
fn fit_half(base: [i32; 3], pixels: &[Px; 8]) -> (i64, u8, [u8; 8]) {
    let mut best = (i64::MAX, 0u8, [0u8; 8]);
    for (t, table) in MODIFIERS.iter().enumerate() {
        let cand = [table[0], table[1], -table[0], -table[1]];
        let idx_of = [0u8, 1, 2, 3]; // sign=0 amt=0, sign=0 amt=1, sign=1 amt=0, sign=1 amt=1
        let mut err: i64 = 0;
        let mut idx = [0u8; 8];
        for (i, p) in pixels.iter().enumerate() {
            if p.w == 0 {
                continue;
            }
            let mut be = i64::MAX;
            let mut bi = 0u8;
            for (k, m) in cand.iter().enumerate() {
                let mut e: i64 = 0;
                for c in 0..3 {
                    let d = (clamp255(base[c] + m) - p.rgb[c]) as i64;
                    e += d * d;
                }
                if e < be {
                    be = e;
                    bi = idx_of[k];
                }
            }
            err += be * p.w as i64;
            idx[i] = bi;
            if err >= best.0 {
                break;
            }
        }
        if err < best.0 {
            best = (err, t as u8, idx);
        }
    }
    best
}

fn average(pixels: &[Px; 8]) -> Option<[f32; 3]> {
    let mut s = [0f32; 3];
    let mut n = 0f32;
    for p in pixels {
        if p.w > 0 {
            for c in 0..3 {
                s[c] += p.rgb[c] as f32;
            }
            n += 1.0;
        }
    }
    if n == 0.0 {
        None
    } else {
        Some([s[0] / n, s[1] / n, s[2] / n])
    }
}

struct Candidate {
    err: i64,
    bits: u64,
}

fn pack(
    diff: bool,
    flip: bool,
    c1: [i32; 3],
    c2: [i32; 3], // individual: 4-bit color; differential: 5-bit base and 3-bit signed delta
    t1: u8,
    t2: u8,
    idx: &[u8; 16], // by block offset (px * 4 + py)
) -> u64 {
    let mut v: u64 = 0;
    if diff {
        v |= (c1[0] as u64 & 0x1F) << 59;
        v |= (c1[1] as u64 & 0x1F) << 51;
        v |= (c1[2] as u64 & 0x1F) << 43;
        v |= (c2[0] as u64 & 7) << 56;
        v |= (c2[1] as u64 & 7) << 48;
        v |= (c2[2] as u64 & 7) << 40;
        v |= 1 << 33;
    } else {
        v |= (c1[0] as u64 & 0xF) << 60;
        v |= (c1[1] as u64 & 0xF) << 52;
        v |= (c1[2] as u64 & 0xF) << 44;
        v |= (c2[0] as u64 & 0xF) << 56;
        v |= (c2[1] as u64 & 0xF) << 48;
        v |= (c2[2] as u64 & 0xF) << 40;
    }
    v |= (t1 as u64 & 7) << 37;
    v |= (t2 as u64 & 7) << 34;
    if flip {
        v |= 1 << 32;
    }
    for (off, &i) in idx.iter().enumerate() {
        let amount = (i & 1) as u64;
        let sign = ((i >> 1) & 1) as u64;
        v |= amount << off;
        v |= sign << (16 + off);
    }
    v
}

/// Encodes one 4x4 block. `block[px][py]` = RGBA.
fn encode_block(block: &[[[u8; 4]; 4]; 4]) -> u64 {
    let mut any = false;
    let mut px_at = [[Px { rgb: [0; 3], w: 0 }; 4]; 4];
    for x in 0..4 {
        for y in 0..4 {
            let p = block[x][y];
            let w = if (p[3] as i32 * 15 + 127) / 255 == 0 { 0 } else { 1 };
            if w > 0 {
                any = true;
            }
            px_at[x][y] = Px {
                rgb: [p[0] as i32, p[1] as i32, p[2] as i32],
                w,
            };
        }
    }
    if !any {
        return 0;
    }

    let mut best: Option<Candidate> = None;
    for &flip in &[false, true] {
        // Collect halves with their block offsets.
        let mut halves = [[Px { rgb: [0; 3], w: 0 }; 8]; 2];
        let mut offs = [[0usize; 8]; 2];
        let mut n = [0usize; 2];
        for x in 0..4 {
            for y in 0..4 {
                let h = if flip { (y >= 2) as usize } else { (x >= 2) as usize };
                halves[h][n[h]] = px_at[x][y];
                offs[h][n[h]] = x * 4 + y;
                n[h] += 1;
            }
        }
        let a0 = average(&halves[0]);
        let a1 = average(&halves[1]);
        let avg0 = a0.or(a1).unwrap();
        let avg1 = a1.or(a0).unwrap();

        let mut consider = |err: i64, bits: u64| {
            if best.as_ref().map_or(true, |b| err < b.err) {
                best = Some(Candidate { err, bits });
            }
        };

        // ---- Individual mode (4 bits per channel per half)
        {
            let mut res = Vec::new();
            for (h, avg) in [avg0, avg1].iter().enumerate() {
                let mut hb: (i64, [i32; 3], u8, [u8; 8]) = (i64::MAX, [0; 3], 0, [0; 8]);
                for combo in 0..27 {
                    let sh = [combo % 3 - 1, (combo / 3) % 3 - 1, combo / 9 - 1];
                    let q: [i32; 3] = [0, 1, 2].map(|c| {
                        ((avg[c] * 15.0 / 255.0).round() as i32 + sh[c]).clamp(0, 15)
                    });
                    let base = q.map(expand4);
                    let (e, t, idx) = fit_half(base, &halves[h]);
                    if e < hb.0 {
                        hb = (e, q, t, idx);
                    }
                }
                res.push(hb);
            }
            let mut idx16 = [0u8; 16];
            for h in 0..2 {
                for i in 0..8 {
                    idx16[offs[h][i]] = res[h].3[i];
                }
            }
            let bits = pack(false, flip, res[0].1, res[1].1, res[0].2, res[1].2, &idx16);
            consider(res[0].0.saturating_add(res[1].0), bits);
        }

        // ---- Differential mode (5-bit base + 3-bit delta)
        {
            let q0: [i32; 3] = [0, 1, 2].map(|c| (avg0[c] * 31.0 / 255.0).round() as i32);
            let q1: [i32; 3] = [0, 1, 2].map(|c| (avg1[c] * 31.0 / 255.0).round() as i32);
            let mut hb0: (i64, [i32; 3], u8, [u8; 8]) = (i64::MAX, [0; 3], 0, [0; 8]);
            for combo in 0..27 {
                let sh = [combo % 3 - 1, (combo / 3) % 3 - 1, combo / 9 - 1];
                let q: [i32; 3] = [0, 1, 2].map(|c| (q0[c] + sh[c]).clamp(0, 31));
                let (e, t, idx) = fit_half(q.map(expand5), &halves[0]);
                if e < hb0.0 {
                    hb0 = (e, q, t, idx);
                }
            }
            let base0 = hb0.1;
            let mut hb1: (i64, [i32; 3], u8, [u8; 8]) = (i64::MAX, [0; 3], 0, [0; 8]);
            for combo in 0..27 {
                let sh = [combo % 3 - 1, (combo / 3) % 3 - 1, combo / 9 - 1];
                let q: [i32; 3] = [0, 1, 2].map(|c| {
                    let want = (q1[c] + sh[c]).clamp(0, 31);
                    let d = (want - base0[c]).clamp(-4, 3);
                    base0[c] + d
                });
                if q.iter().any(|&v| !(0..=31).contains(&v)) {
                    continue;
                }
                let (e, t, idx) = fit_half(q.map(expand5), &halves[1]);
                if e < hb1.0 {
                    hb1 = (e, q, t, idx);
                }
            }
            if hb1.0 != i64::MAX {
                let delta = [0, 1, 2].map(|c| (hb1.1[c] - base0[c]) & 7);
                let mut idx16 = [0u8; 16];
                for i in 0..8 {
                    idx16[offs[0][i]] = hb0.3[i];
                    idx16[offs[1][i]] = hb1.3[i];
                }
                let bits = pack(true, flip, base0, delta, hb0.2, hb1.2, &idx16);
                consider(hb0.0.saturating_add(hb1.0), bits);
            }
        }
    }
    best.unwrap().bits
}

fn alpha_bits(block: &[[[u8; 4]; 4]; 4]) -> u64 {
    let mut v: u64 = 0;
    for x in 0..4 {
        for y in 0..4 {
            let a = ((block[x][y][3] as u32 * 15 + 127) / 255) as u64;
            v |= a << ((x * 4 + y) * 4);
        }
    }
    v
}

/// Encode RGBA8 (row-major, width*height*4) to ETC1A4 (`with_alpha`) or ETC1.
/// Width and height must be multiples of 8.
pub fn encode(rgba: &[u8], width: usize, height: usize, with_alpha: bool) -> Result<Vec<u8>, String> {
    if width % 8 != 0 || height % 8 != 0 {
        return Err(format!("ETC1 size must be a multiple of 8, got {}x{}", width, height));
    }
    if rgba.len() != width * height * 4 {
        return Err("RGBA buffer size does not match width/height".to_string());
    }
    let mut out = Vec::with_capacity(if with_alpha { width * height } else { width * height / 2 });
    for tile_y in 0..height / 8 {
        for tile_x in 0..width / 8 {
            for block_y in 0..2 {
                for block_x in 0..2 {
                    let mut block = [[[0u8; 4]; 4]; 4];
                    for px in 0..4 {
                        for py in 0..4 {
                            let x = tile_x * 8 + block_x * 4 + px;
                            let y = tile_y * 8 + block_y * 4 + py;
                            let o = (y * width + x) * 4;
                            block[px][py] = [rgba[o], rgba[o + 1], rgba[o + 2], rgba[o + 3]];
                        }
                    }
                    if with_alpha {
                        out.extend_from_slice(&alpha_bits(&block).to_le_bytes());
                    } else {
                        for px in 0..4 {
                            for py in 0..4 {
                                block[px][py][3] = 255;
                            }
                        }
                    }
                    out.extend_from_slice(&encode_block(&block).to_le_bytes());
                }
            }
        }
    }
    Ok(out)
}
