#!/usr/bin/env python3
"""Gera uma biblioteca demo sintética e determinística para o AssetDeck.

Estrutura gerada:
  01 - MODELOS/     -> 5 modelos OBJ (cubo, esfera, torus, cadeira, vaso) com preview .jpg ao lado
  03 - TEXTURAS/    -> 12 texturas procedurais (ruído/gradiente: concreto, madeira, mármore, etc.)
  04 - VETORES/     -> 2 arquivos vetoriais SVG
  05 - MATERIAIS/   -> 3 materiais PBR completos (_basecolor, _normal, _roughness, _height) a 1024px
  06 - HDRIs/       -> 4 panoramas procedurais (2 .hdr e 2 .exr: sol meio-dia, estúdio, pôr do sol)
  07 - IESs/        -> 1 perfil fotométrico sintético IES
  08 - LUTs/        -> 1 arquivo de color grading .cube

Uso:
  python tools/make_demo_library.py /caminho/para/pasta_destino
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys

import cv2
import numpy as np
import OpenEXR
from PIL import Image, ImageDraw, ImageFilter


def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _noise_2d(h: int, w: int, scale: float, seed: int = 42) -> np.ndarray:
    """Ruído fractal determinístico simples baseado em interpolação bicúbica."""
    rng = np.random.RandomState(seed)
    grid_h = max(2, int(h / scale))
    grid_w = max(2, int(w / scale))
    grid = rng.rand(grid_h, grid_w).astype(np.float32)

    img = Image.fromarray((grid * 255).astype(np.uint8), mode="L")
    img = img.resize((w, h), resample=Image.Resampling.BICUBIC)
    return np.asarray(img, dtype=np.float32) / 255.0


def _fbm_2d(h: int, w: int, octaves: int = 4, scale: float = 64.0, seed: int = 42) -> np.ndarray:
    out = np.zeros((h, w), dtype=np.float32)
    weight_sum = 0.0
    for i in range(octaves):
        freq = 2.0 ** i
        weight = 0.5 ** i
        cur_scale = max(2.0, scale / freq)
        out += _noise_2d(h, w, cur_scale, seed=seed + i * 17) * weight
        weight_sum += weight
    return out / weight_sum


def _normal_from_height(height: np.ndarray, strength: float = 5.0) -> np.ndarray:
    """Gera um mapa de normal padrão OpenGL (RGB 8-bit) a partir do heightmap."""
    dh_dx = np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)
    dh_dy = np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)

    nx = -dh_dx * strength
    ny = -dh_dy * strength
    nz = np.ones_like(nx)
    length = np.sqrt(nx**2 + ny**2 + nz**2)
    nx /= length
    ny /= length
    nz /= length

    r = ((nx * 0.5 + 0.5) * 255.0).clip(0, 255).astype(np.uint8)
    g = ((ny * 0.5 + 0.5) * 255.0).clip(0, 255).astype(np.uint8)
    b = ((nz * 0.5 + 0.5) * 255.0).clip(0, 255).astype(np.uint8)
    return np.stack([r, g, b], axis=-1)


# ---------------------------------------------------------------------------
# 03 - TEXTURAS (~12)
# ---------------------------------------------------------------------------


def generate_textures(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    size = 1024

    # 1. concreto_rustico_cinza.jpg
    n1 = _fbm_2d(size, size, octaves=5, scale=48.0, seed=101)
    n2 = _noise_2d(size, size, scale=4.0, seed=102)
    gray = (n1 * 0.8 + n2 * 0.2)
    c_base = np.array([145, 142, 138], dtype=np.float32)
    img_concreto = (c_base * gray[..., np.newaxis] * 1.3).clip(0, 255).astype(np.uint8)
    Image.fromarray(img_concreto).save(out_dir / "concreto_rustico_cinza.jpg", quality=92)

    # 2. madeira_carvalho_natural.jpg
    rng = np.random.RandomState(201)
    y_coords, x_coords = np.mgrid[0:size, 0:size]
    stretch_noise = _noise_2d(size, size, scale=120.0, seed=202)
    rings = np.sin((y_coords * 0.05 + stretch_noise * 12.0)) * 0.5 + 0.5
    fine_grain = _noise_2d(size, size, scale=8.0, seed=203)
    grain = rings * 0.6 + fine_grain * 0.4
    c_wood_dark = np.array([120, 72, 38], dtype=np.float32)
    c_wood_light = np.array([195, 145, 95], dtype=np.float32)
    wood = c_wood_dark + (c_wood_light - c_wood_dark) * grain[..., np.newaxis]
    Image.fromarray(wood.clip(0, 255).astype(np.uint8)).save(out_dir / "madeira_carvalho_natural.jpg", quality=92)

    # 3. marmore_carrara_veios.png
    m_base = _fbm_2d(size, size, octaves=6, scale=128.0, seed=301)
    vein_coords = np.sin((x_coords * 0.01 + y_coords * 0.005 + m_base * 6.0) * math.pi)
    veins = 1.0 - np.abs(vein_coords) ** 0.3
    veins = np.clip(veins, 0.0, 1.0)
    c_marble = np.array([238, 240, 242], dtype=np.float32)
    c_vein = np.array([90, 95, 105], dtype=np.float32)
    marble = c_marble * (1.0 - veins[..., np.newaxis] * 0.6) + c_vein * (veins[..., np.newaxis] * 0.6)
    Image.fromarray(marble.clip(0, 255).astype(np.uint8)).save(out_dir / "marmore_carrara_veios.png")

    # 4. tijolo_aparente_demolicao.jpg
    brick_h = 64
    brick_w = 128
    mortar = 6
    b_y = (y_coords % brick_h) < mortar
    row_idx = y_coords // brick_h
    offset_x = (row_idx % 2) * (brick_w // 2)
    b_x = ((x_coords + offset_x) % brick_w) < mortar
    is_mortar = b_x | b_y
    brick_noise = _fbm_2d(size, size, octaves=4, scale=32.0, seed=401)
    c_brick = np.array([175, 75, 50], dtype=np.float32) * (0.8 + brick_noise[..., np.newaxis] * 0.4)
    c_mortar = np.array([190, 185, 175], dtype=np.float32) * (0.9 + brick_noise[..., np.newaxis] * 0.2)
    bricks = np.where(is_mortar[..., np.newaxis], c_mortar, c_brick)
    Image.fromarray(bricks.clip(0, 255).astype(np.uint8)).save(out_dir / "tijolo_aparente_demolicao.jpg", quality=92)

    # 5. metal_cobre_escovado.png
    brushed = _noise_2d(size, size, scale=4.0, seed=501)
    brushed = np.repeat(np.mean(brushed, axis=0, keepdims=True), size, axis=0)
    fine_b = _noise_2d(size, size, scale=2.0, seed=502)
    b_tex = brushed * 0.7 + fine_b * 0.3
    c_copper = np.array([215, 115, 75], dtype=np.float32)
    copper = c_copper * (0.8 + b_tex[..., np.newaxis] * 0.4)
    Image.fromarray(copper.clip(0, 255).astype(np.uint8)).save(out_dir / "metal_cobre_escovado.png")

    # 6. tecido_linho_cru.jpg
    weave = (np.sin(x_coords * 0.25) * np.cos(y_coords * 0.25)) * 0.5 + 0.5
    f_noise = _noise_2d(size, size, scale=16.0, seed=601)
    linen_val = weave * 0.4 + f_noise * 0.6
    c_linen = np.array([215, 205, 185], dtype=np.float32)
    linen = c_linen * (0.85 + linen_val[..., np.newaxis] * 0.3)
    Image.fromarray(linen.clip(0, 255).astype(np.uint8)).save(out_dir / "tecido_linho_cru.jpg", quality=92)

    # 7. azulejo_ceramica_verde.png
    tile_size = 128
    tile_border = 5
    t_edge = (x_coords % tile_size < tile_border) | (y_coords % tile_size < tile_border)
    t_center_dist = np.minimum(x_coords % tile_size, tile_size - (x_coords % tile_size))
    t_center_dist = np.minimum(t_center_dist, np.minimum(y_coords % tile_size, tile_size - (y_coords % tile_size)))
    t_bevel = np.clip(t_center_dist / 16.0, 0.0, 1.0)
    c_green = np.array([22, 98, 72], dtype=np.float32) * (0.7 + t_bevel[..., np.newaxis] * 0.4)
    c_grout = np.array([210, 215, 210], dtype=np.float32)
    tile_img = np.where(t_edge[..., np.newaxis], c_grout, c_green)
    Image.fromarray(tile_img.clip(0, 255).astype(np.uint8)).save(out_dir / "azulejo_ceramica_verde.png")

    # 8. granito_preto_sao_gabriel.jpg
    speckle1 = rng.rand(size, size).astype(np.float32)
    speckle2 = _noise_2d(size, size, scale=3.0, seed=801)
    g_val = (speckle1 > 0.92).astype(np.float32) * 0.7 + (speckle2 > 0.75).astype(np.float32) * 0.3
    c_granite = np.array([32, 33, 36], dtype=np.float32) + g_val[..., np.newaxis] * 120.0
    Image.fromarray(c_granite.clip(0, 255).astype(np.uint8)).save(out_dir / "granito_preto_sao_gabriel.jpg", quality=92)

    # 9. pedra_ardosia_cinza.png
    slate_n = _fbm_2d(size, size, octaves=5, scale=64.0, seed=901)
    strata = np.sin(y_coords * 0.02 + slate_n * 8.0) * 0.5 + 0.5
    s_val = slate_n * 0.6 + strata * 0.4
    c_slate = np.array([75, 80, 85], dtype=np.float32) * (0.8 + s_val[..., np.newaxis] * 0.4)
    Image.fromarray(c_slate.clip(0, 255).astype(np.uint8)).save(out_dir / "pedra_ardosia_cinza.png")

    # 10. asfalto_urbano_fissurado.jpg
    asph_noise = _fbm_2d(size, size, octaves=6, scale=16.0, seed=1001)
    cracks = (_fbm_2d(size, size, octaves=4, scale=128.0, seed=1002) * 10.0) % 1.0
    crack_lines = (cracks < 0.03).astype(np.float32)
    c_asph = np.array([55, 55, 58], dtype=np.float32) * (0.8 + asph_noise[..., np.newaxis] * 0.3)
    c_asph = c_asph * (1.0 - crack_lines[..., np.newaxis] * 0.7)
    Image.fromarray(c_asph.clip(0, 255).astype(np.uint8)).save(out_dir / "asfalto_urbano_fissurado.jpg", quality=90)

    # 11. couro_sintetico_marrom.jpg
    c_noise = _noise_2d(size, size, scale=6.0, seed=1101)
    c_wrinkle = _fbm_2d(size, size, octaves=4, scale=32.0, seed=1102)
    leather_val = c_noise * 0.5 + c_wrinkle * 0.5
    c_leather = np.array([105, 55, 30], dtype=np.float32) * (0.8 + leather_val[..., np.newaxis] * 0.35)
    Image.fromarray(c_leather.clip(0, 255).astype(np.uint8)).save(out_dir / "couro_sintetico_marrom.jpg", quality=92)

    # 12. gesso_acabamento_branco.png
    plaster_n = _fbm_2d(size, size, octaves=5, scale=40.0, seed=1201)
    c_plaster = np.array([242, 240, 238], dtype=np.float32) * (0.94 + plaster_n[..., np.newaxis] * 0.08)
    Image.fromarray(c_plaster.clip(0, 255).astype(np.uint8)).save(out_dir / "gesso_acabamento_branco.png")


# ---------------------------------------------------------------------------
# 05 - MATERIAIS (3 sets PBR completos a 1024px)
# ---------------------------------------------------------------------------


def generate_pbr_materials(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    size = 1024
    y_coords, x_coords = np.mgrid[0:size, 0:size]

    # Material 1: concreto_industrial
    h_conc = _fbm_2d(size, size, octaves=5, scale=32.0, seed=1301)
    pockmarks = (_noise_2d(size, size, scale=8.0, seed=1302) > 0.88).astype(np.float32) * 0.4
    h_conc = np.clip(h_conc - pockmarks, 0.0, 1.0)
    norm_conc = _normal_from_height(h_conc, strength=4.0)
    rough_conc = (np.clip(0.45 + h_conc * 0.35, 0.0, 1.0) * 255).astype(np.uint8)
    base_conc = (np.array([160, 158, 155], dtype=np.float32) * (0.8 + h_conc[..., np.newaxis] * 0.3)).clip(0, 255).astype(np.uint8)
    height_conc = (h_conc * 255).astype(np.uint8)

    Image.fromarray(base_conc).save(out_dir / "concreto_industrial_basecolor.png")
    Image.fromarray(norm_conc).save(out_dir / "concreto_industrial_normal.png")
    Image.fromarray(rough_conc, mode="L").save(out_dir / "concreto_industrial_roughness.png")
    Image.fromarray(height_conc, mode="L").save(out_dir / "concreto_industrial_height.png")

    # Material 2: piso_madeira_tabuas
    plank_w = 128
    gap = 4
    is_gap = (x_coords % plank_w) < gap
    plank_idx = x_coords // plank_w
    rng = np.random.RandomState(1401)
    plank_tint = rng.uniform(0.85, 1.15, size=(size // plank_w) + 2)
    tint_map = plank_tint[plank_idx]

    wood_noise = _noise_2d(size, size, scale=96.0, seed=1402)
    grain = np.sin(y_coords * 0.04 + wood_noise * 10.0) * 0.5 + 0.5
    h_wood = np.where(is_gap, 0.1, 0.5 + grain * 0.3)
    norm_wood = _normal_from_height(h_wood, strength=6.0)
    c_w1 = np.array([135, 85, 45], dtype=np.float32)
    c_w2 = np.array([185, 130, 80], dtype=np.float32)
    base_w = (c_w1 + (c_w2 - c_w1) * grain[..., np.newaxis]) * tint_map[..., np.newaxis]
    base_w = np.where(is_gap[..., np.newaxis], np.array([40, 25, 15], dtype=np.float32), base_w)
    rough_wood = np.where(is_gap, 230, (np.clip(0.3 + grain * 0.25, 0.0, 1.0) * 255).astype(np.uint8))

    Image.fromarray(base_w.clip(0, 255).astype(np.uint8)).save(out_dir / "piso_madeira_tabuas_basecolor.png")
    Image.fromarray(norm_wood).save(out_dir / "piso_madeira_tabuas_normal.png")
    Image.fromarray(rough_wood.astype(np.uint8), mode="L").save(out_dir / "piso_madeira_tabuas_roughness.png")
    Image.fromarray((h_wood * 255).astype(np.uint8), mode="L").save(out_dir / "piso_madeira_tabuas_height.png")

    # Material 3: chapas_aco_industrial
    panel_s = 256
    p_gap = 6
    is_p_gap = (x_coords % panel_s < p_gap) | (y_coords % panel_s < p_gap)
    m_noise = _fbm_2d(size, size, octaves=4, scale=48.0, seed=1501)
    h_metal = np.where(is_p_gap, 0.05, 0.8 + m_noise * 0.15)
    norm_metal = _normal_from_height(h_metal, strength=5.0)
    c_metal = np.array([180, 185, 192], dtype=np.float32) * (0.8 + m_noise[..., np.newaxis] * 0.3)
    c_metal = np.where(is_p_gap[..., np.newaxis], np.array([50, 52, 55], dtype=np.float32), c_metal)
    rough_metal = np.where(is_p_gap, 210, (np.clip(0.2 + m_noise * 0.2, 0.0, 1.0) * 255).astype(np.uint8))

    Image.fromarray(c_metal.clip(0, 255).astype(np.uint8)).save(out_dir / "chapas_aco_industrial_basecolor.png")
    Image.fromarray(norm_metal).save(out_dir / "chapas_aco_industrial_normal.png")
    Image.fromarray(rough_metal.astype(np.uint8), mode="L").save(out_dir / "chapas_aco_industrial_roughness.png")
    Image.fromarray((h_metal * 255).astype(np.uint8), mode="L").save(out_dir / "chapas_aco_industrial_height.png")


# ---------------------------------------------------------------------------
# 06 - HDRIs (4 panoramas: 2 .hdr e 2 .exr)
# ---------------------------------------------------------------------------


def _write_exr(path: Path, array_rgb: np.ndarray) -> None:
    canais = {
        "R": array_rgb[..., 0].astype(np.float32),
        "G": array_rgb[..., 1].astype(np.float32),
        "B": array_rgb[..., 2].astype(np.float32),
    }
    part = OpenEXR.Part({}, canais)
    OpenEXR.File([part]).write(str(path))


def generate_hdris(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    w = 1024
    h = 512

    # Coordenadas equirretangulares
    # u in [0, 1] -> azimuth phi in [-pi, pi]
    # v in [0, 1] -> elevation theta in [pi/2, -pi/2]
    u, v = np.meshgrid(np.linspace(0.0, 1.0, w, endpoint=False), np.linspace(0.0, 1.0, h, endpoint=False))
    phi = (u - 0.5) * 2.0 * math.pi
    theta = (0.5 - v) * math.pi

    dx = np.cos(theta) * np.sin(phi)
    dy = np.sin(theta)
    dz = np.cos(theta) * np.cos(phi)

    # 1. ceu_ensolarado_meio_dia.hdr
    # Céu: dy > 0 gradiente azul, dy <= 0 chão quente suave
    sky_t = np.clip(dy, 0.0, 1.0)
    zenith = np.array([0.18, 0.42, 0.95], dtype=np.float32)
    horizon = np.array([0.75, 0.82, 0.95], dtype=np.float32)
    ground = np.array([0.12, 0.10, 0.08], dtype=np.float32)

    sky_rgb = horizon[np.newaxis, np.newaxis, :] * (1.0 - sky_t[..., np.newaxis]) + zenith[np.newaxis, np.newaxis, :] * sky_t[..., np.newaxis]
    ground_t = np.clip(-dy, 0.0, 1.0)
    below_rgb = horizon[np.newaxis, np.newaxis, :] * (1.0 - ground_t[..., np.newaxis]) + ground[np.newaxis, np.newaxis, :] * ground_t[..., np.newaxis]
    env1 = np.where(dy[..., np.newaxis] >= 0, sky_rgb, below_rgb)

    # Sol: direção elevation ~50 graus, azimuth ~0.4 rad
    sun_dir = np.array([math.sin(0.4) * math.cos(0.85), math.sin(0.85), math.cos(0.4) * math.cos(0.85)], dtype=np.float32)
    cos_sun = np.clip(dx * sun_dir[0] + dy * sun_dir[1] + dz * sun_dir[2], 0.0, 1.0)
    sun_disc = (cos_sun > 0.9995).astype(np.float32) * 65.0
    sun_flare = (cos_sun ** 64) * 8.0
    env1 += (sun_disc + sun_flare)[..., np.newaxis] * np.array([1.0, 0.95, 0.85], dtype=np.float32)

    cv2.imwrite(str(out_dir / "ceu_ensolarado_meio_dia.hdr"), env1[..., ::-1].astype(np.float32))

    # 2. estudio_tres_pontes.exr
    env2 = np.full((h, w, 3), 0.05, dtype=np.float32)  # fundo estúdio escuro
    # Key light: softbox à esquerda (phi ~ -1.0, dy ~ 0.3)
    k_dir = np.array([math.sin(-1.0) * math.cos(0.3), math.sin(0.3), math.cos(-1.0) * math.cos(0.3)], dtype=np.float32)
    cos_k = np.clip(dx * k_dir[0] + dy * k_dir[1] + dz * k_dir[2], 0.0, 1.0)
    env2 += ((cos_k ** 16) * 18.0)[..., np.newaxis] * np.array([1.0, 0.96, 0.90], dtype=np.float32)

    # Fill light: à direita (phi ~ 1.2, dy ~ 0.1)
    f_dir = np.array([math.sin(1.2) * math.cos(0.1), math.sin(0.1), math.cos(1.2) * math.cos(0.1)], dtype=np.float32)
    cos_f = np.clip(dx * f_dir[0] + dy * f_dir[1] + dz * f_dir[2], 0.0, 1.0)
    env2 += ((cos_f ** 24) * 6.0)[..., np.newaxis] * np.array([0.85, 0.92, 1.0], dtype=np.float32)

    # Rim light: atrás (phi ~ 2.8, dy ~ 0.5)
    r_dir = np.array([math.sin(2.8) * math.cos(0.5), math.sin(0.5), math.cos(2.8) * math.cos(0.5)], dtype=np.float32)
    cos_r = np.clip(dx * r_dir[0] + dy * r_dir[1] + dz * r_dir[2], 0.0, 1.0)
    env2 += ((cos_r ** 32) * 12.0)[..., np.newaxis] * np.array([1.0, 1.0, 1.0], dtype=np.float32)

    _write_exr(out_dir / "estudio_tres_pontes.exr", env2)

    # 3. por_do_sol_dourado.hdr
    sunset_zenith = np.array([0.06, 0.05, 0.22], dtype=np.float32)
    sunset_mid = np.array([0.65, 0.22, 0.28], dtype=np.float32)
    sunset_horizon = np.array([2.2, 0.85, 0.15], dtype=np.float32)
    sunset_ground = np.array([0.04, 0.03, 0.03], dtype=np.float32)

    t_sky = np.clip(dy * 2.0, 0.0, 1.0)
    sky_grad = np.where(
        dy[..., np.newaxis] > 0.3,
        sunset_mid[np.newaxis, np.newaxis, :] * (1.0 - t_sky[..., np.newaxis]) + sunset_zenith[np.newaxis, np.newaxis, :] * t_sky[..., np.newaxis],
        sunset_horizon[np.newaxis, np.newaxis, :] * (1.0 - t_sky[..., np.newaxis] * 3.3).clip(0, 1) + sunset_mid[np.newaxis, np.newaxis, :] * (t_sky[..., np.newaxis] * 3.3).clip(0, 1)
    )
    env3 = np.where(dy[..., np.newaxis] >= 0, sky_grad, sunset_ground[np.newaxis, np.newaxis, :])

    # Sol no horizonte
    s_dir = np.array([0.0, math.sin(0.04), math.cos(0.04)], dtype=np.float32)
    cos_s = np.clip(dx * s_dir[0] + dy * s_dir[1] + dz * s_dir[2], 0.0, 1.0)
    sun3_disc = (cos_s > 0.999) * 55.0
    sun3_glow = (cos_s ** 30) * 14.0
    env3 += (sun3_disc + sun3_glow)[..., np.newaxis] * np.array([2.5, 0.9, 0.2], dtype=np.float32)

    cv2.imwrite(str(out_dir / "por_do_sol_dourado.hdr"), env3[..., ::-1].astype(np.float32))

    # 4. estudio_fotografico_ciclorama.exr
    env4 = np.full((h, w, 3), 0.12, dtype=np.float32)
    overhead_dir = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    cos_oh = np.clip(dy, 0.0, 1.0)
    env4 += ((cos_oh ** 4) * 15.0)[..., np.newaxis] * np.array([1.0, 1.0, 1.0], dtype=np.float32)
    _write_exr(out_dir / "estudio_fotografico_ciclorama.exr", env4)


# ---------------------------------------------------------------------------
# 01 - MODELOS (5 OBJ com preview .jpg ao lado)
# ---------------------------------------------------------------------------


def _render_shaded_preview(mesh_positions: list[tuple[float, float, float]],
                           mesh_faces: list[list[int]],
                           color_rgb: tuple[int, int, int],
                           size: int = 512) -> Image.Image:
    """Renderiza um preview estilizado limpo com sombreamento difuso sobre fundo cinza suave."""
    img = Image.new("RGB", (size, size), (240, 241, 244))
    draw = ImageDraw.Draw(img)

    if not mesh_positions or not mesh_faces:
        return img

    pts = np.array(mesh_positions, dtype=np.float32)
    min_b = pts.min(axis=0)
    max_b = pts.max(axis=0)
    center = (min_b + max_b) * 0.5
    scale = (max_b - min_b).max()
    if scale <= 1e-6:
        scale = 1.0

    # Rotação isométrica: yaw ~35 deg, pitch ~25 deg
    yaw = math.radians(35)
    pitch = math.radians(25)
    r_yaw = np.array([
        [math.cos(yaw), 0, math.sin(yaw)],
        [0, 1, 0],
        [-math.sin(yaw), 0, math.cos(yaw)],
    ], dtype=np.float32)
    r_pitch = np.array([
        [1, 0, 0],
        [0, math.cos(pitch), -math.sin(pitch)],
        [0, math.sin(pitch), math.cos(pitch)],
    ], dtype=np.float32)
    rot = r_pitch @ r_yaw

    pts_norm = (pts - center) / scale
    pts_rot = pts_norm @ rot.T

    # Projeção ortográfica para o canvas
    s_view = size * 0.38
    scr_x = size * 0.5 + pts_rot[:, 0] * s_view
    scr_y = size * 0.52 - pts_rot[:, 1] * s_view
    depths = pts_rot[:, 2]

    light = np.array([0.45, 0.75, 0.48], dtype=np.float32)
    light /= np.linalg.norm(light)

    # Ordena faces por profundidade (painter's algorithm)
    sorted_faces = []
    for face in mesh_faces:
        f_idx = face[:3]
        f_depth = depths[f_idx].mean()
        # Normal no espaço de rotação
        v0 = pts_rot[f_idx[0]]
        v1 = pts_rot[f_idx[1]]
        v2 = pts_rot[f_idx[2]]
        fn = np.cross(v1 - v0, v2 - v0)
        norm = np.linalg.norm(fn)
        if norm > 1e-8:
            fn /= norm
            # Descarta faces voltadas para trás
            if fn[2] > -0.05:
                diff = max(0.15, float(np.dot(fn, light)))
                sorted_faces.append((f_depth, diff, [f - 1 for f in face] if face[0] > 0 else face))

    sorted_faces.sort(key=lambda x: x[0])

    # Sombra suave sob o objeto
    shadow_box = [int(size * 0.25), int(size * 0.76), int(size * 0.75), int(size * 0.88)]
    draw.ellipse(shadow_box, fill=(210, 212, 218))
    img = img.filter(ImageFilter.GaussianBlur(radius=6))
    draw = ImageDraw.Draw(img)

    for _, diff, f_indices in sorted_faces:
        poly = [(scr_x[idx], scr_y[idx]) for idx in f_indices]
        c = tuple(min(255, max(0, int(v * (0.4 + 0.6 * diff)))) for v in color_rgb)
        outline = tuple(max(0, int(v * 0.65)) for v in c)
        draw.polygon(poly, fill=c, outline=outline)

    return img


def _write_obj(path: Path, positions: list[tuple[float, float, float]],
               faces: list[list[int]], normals: list[tuple[float, float, float]] | None = None,
               material_name: str | None = None,
               material_color: tuple[float, float, float] | None = None) -> None:
    if material_name and material_color:
        mtl_path = path.with_suffix(".mtl")
        mtl_content = (
            f"# AssetDeck Synthetic Material: {material_name}\n"
            f"newmtl {material_name}\n"
            f"Kd {material_color[0]:.4f} {material_color[1]:.4f} {material_color[2]:.4f}\n"
        )
        mtl_path.write_text(mtl_content, encoding="utf-8")

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# AssetDeck Synthetic Model: {path.stem}\n")
        if material_name and material_color:
            f.write(f"mtllib {path.stem}.mtl\n")
            f.write(f"usemtl {material_name}\n")
        for p in positions:
            f.write(f"v {p[0]:.5f} {p[1]:.5f} {p[2]:.5f}\n")
        if normals:
            for n in normals:
                f.write(f"vn {n[0]:.5f} {n[1]:.5f} {n[2]:.5f}\n")
            for face in faces:
                indices = " ".join(f"{idx}//{idx}" for idx in face)
                f.write(f"f {indices}\n")
        else:
            for face in faces:
                indices = " ".join(str(idx) for idx in face)
                f.write(f"f {indices}\n")


def generate_models(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. cubo.obj
    cube_v: list[tuple[float, float, float]] = []
    cube_n: list[tuple[float, float, float]] = []
    cube_f: list[list[int]] = []
    faces_data = [
        ([(-1, -1,  1), ( 1, -1,  1), ( 1,  1,  1), (-1,  1,  1)], (0.0, 0.0, 1.0)),   # frente
        ([(-1,  1, -1), ( 1,  1, -1), ( 1, -1, -1), (-1, -1, -1)], (0.0, 0.0, -1.0)),  # costas
        ([(-1,  1, -1), (-1,  1,  1), ( 1,  1,  1), ( 1,  1, -1)], (0.0, 1.0, 0.0)),   # topo
        ([(-1, -1, -1), ( 1, -1, -1), ( 1, -1,  1), (-1, -1,  1)], (0.0, -1.0, 0.0)),  # base
        ([( 1, -1, -1), ( 1,  1, -1), ( 1,  1,  1), ( 1, -1,  1)], (1.0, 0.0, 0.0)),   # direita
        ([(-1, -1, -1), (-1, -1,  1), (-1,  1,  1), (-1,  1, -1)], (-1.0, 0.0, 0.0)),  # esquerda
    ]
    for face_pts, fn in faces_data:
        base = len(cube_v)
        for pt in face_pts:
            cube_v.append(pt)
            cube_n.append(fn)
        cube_f.append([base + 1, base + 2, base + 3, base + 4])

    _write_obj(out_dir / "cubo.obj", cube_v, cube_f, normals=cube_n,
               material_name="M_Cubo", material_color=(0.32, 0.52, 0.82))
    img_cube = _render_shaded_preview(cube_v, [[idx - 1 for idx in f] for f in cube_f], (80, 130, 200))
    img_cube.save(out_dir / "cubo.jpg", quality=92)

    # 2. esfera.obj
    sphere_v: list[tuple[float, float, float]] = []
    sphere_n: list[tuple[float, float, float]] = []
    sphere_f: list[list[int]] = []
    rings = 24
    sectors = 32
    for r in range(rings + 1):
        theta = r * math.pi / rings
        y = math.cos(theta)
        sin_t = math.sin(theta)
        for s in range(sectors):
            phi = s * 2 * math.pi / sectors
            x = sin_t * math.sin(phi)
            z = sin_t * math.cos(phi)
            sphere_v.append((x, y, z))
            sphere_n.append((x, y, z))

    for r in range(rings):
        for s in range(sectors):
            s_next = (s + 1) % sectors
            i1 = r * sectors + s + 1
            i2 = r * sectors + s_next + 1
            i3 = (r + 1) * sectors + s_next + 1
            i4 = (r + 1) * sectors + s + 1
            sphere_f.append([i1, i2, i3, i4])

    _write_obj(out_dir / "esfera.obj", sphere_v, sphere_f, normals=sphere_n,
               material_name="M_Esfera", material_color=(0.86, 0.38, 0.30))
    img_sphere = _render_shaded_preview(sphere_v, [[idx - 1 for idx in f] for f in sphere_f], (220, 100, 80))
    img_sphere.save(out_dir / "esfera.jpg", quality=92)

    # 3. torus.obj
    torus_v: list[tuple[float, float, float]] = []
    torus_n: list[tuple[float, float, float]] = []
    torus_f: list[list[int]] = []
    r_major = 1.0
    r_minor = 0.42
    t_rings = 48
    t_sides = 32
    for i in range(t_rings):
        u = i * 2 * math.pi / t_rings
        cos_u = math.cos(u)
        sin_u = math.sin(u)
        for j in range(t_sides):
            v = j * 2 * math.pi / t_sides
            cos_v = math.cos(v)
            sin_v = math.sin(v)
            x = (r_major + r_minor * cos_v) * cos_u
            y = r_minor * sin_v
            z = (r_major + r_minor * cos_v) * sin_u
            nx = cos_v * cos_u
            ny = sin_v
            nz = cos_v * sin_u
            torus_v.append((x, y, z))
            torus_n.append((nx, ny, nz))

    for i in range(t_rings):
        i_next = (i + 1) % t_rings
        for j in range(t_sides):
            j_next = (j + 1) % t_sides
            i1 = i * t_sides + j + 1
            i2 = i_next * t_sides + j + 1
            i3 = i_next * t_sides + j_next + 1
            i4 = i * t_sides + j_next + 1
            torus_f.append([i1, i4, i3, i2])

    _write_obj(out_dir / "torus.obj", torus_v, torus_f, normals=torus_n,
               material_name="M_Torus", material_color=(0.88, 0.48, 0.18))
    img_torus = _render_shaded_preview(torus_v, [[idx - 1 for idx in f] for f in torus_f], (225, 122, 45))
    img_torus.save(out_dir / "torus.jpg", quality=92)

    # 4. cadeira_estilizada.obj
    chair_v: list[tuple[float, float, float]] = []
    chair_n: list[tuple[float, float, float]] = []
    chair_f: list[list[int]] = []

    def _add_chair_box(cx: float, cy: float, cz: float, sx: float, sy: float, sz: float) -> None:
        dx, dy, dz = sx * 0.5, sy * 0.5, sz * 0.5
        box_faces = [
            ([(cx - dx, cy - dy, cz + dz), (cx + dx, cy - dy, cz + dz), (cx + dx, cy + dy, cz + dz), (cx - dx, cy + dy, cz + dz)], (0.0, 0.0, 1.0)),
            ([(cx - dx, cy + dy, cz - dz), (cx + dx, cy + dy, cz - dz), (cx + dx, cy - dy, cz - dz), (cx - dx, cy - dy, cz - dz)], (0.0, 0.0, -1.0)),
            ([(cx - dx, cy + dy, cz - dz), (cx - dx, cy + dy, cz + dz), (cx + dx, cy + dy, cz + dz), (cx + dx, cy + dy, cz - dz)], (0.0, 1.0, 0.0)),
            ([(cx - dx, cy - dy, cz - dz), (cx + dx, cy - dy, cz - dz), (cx + dx, cy - dy, cz + dz), (cx - dx, cy - dy, cz + dz)], (0.0, -1.0, 0.0)),
            ([(cx + dx, cy - dy, cz - dz), (cx + dx, cy + dy, cz - dz), (cx + dx, cy + dy, cz + dz), (cx + dx, cy - dy, cz + dz)], (1.0, 0.0, 0.0)),
            ([(cx - dx, cy - dy, cz - dz), (cx - dx, cy - dy, cz + dz), (cx - dx, cy + dy, cz + dz), (cx - dx, cy + dy, cz - dz)], (-1.0, 0.0, 0.0)),
        ]
        for f_pts, fn in box_faces:
            base = len(chair_v)
            for p in f_pts:
                chair_v.append(p)
                chair_n.append(fn)
            chair_f.append([base + 1, base + 2, base + 3, base + 4])

    # Assento
    _add_chair_box(0, 0.45, 0, 0.5, 0.05, 0.5)
    # Encosto
    _add_chair_box(0, 0.75, -0.22, 0.46, 0.55, 0.04)
    # 4 Pernas
    _add_chair_box(-0.2, 0.22, -0.2, 0.04, 0.45, 0.04)
    _add_chair_box(0.2, 0.22, -0.2, 0.04, 0.45, 0.04)
    _add_chair_box(-0.2, 0.22, 0.2, 0.04, 0.45, 0.04)
    _add_chair_box(0.2, 0.22, 0.2, 0.04, 0.45, 0.04)

    _write_obj(out_dir / "cadeira_estilizada.obj", chair_v, chair_f, normals=chair_n,
               material_name="M_Cadeira", material_color=(0.72, 0.48, 0.26))
    img_chair = _render_shaded_preview(chair_v, [[idx - 1 for idx in f] for f in chair_f], (180, 140, 100))
    img_chair.save(out_dir / "cadeira_estilizada.jpg", quality=92)

    # 5. vaso_decorativo.obj
    vase_v: list[tuple[float, float, float]] = []
    vase_n: list[tuple[float, float, float]] = []
    vase_f: list[list[int]] = []
    v_profile = [
        (0.2, 0.0), (0.22, 0.08), (0.42, 0.35), (0.48, 0.55),
        (0.24, 0.82), (0.18, 0.95), (0.26, 1.05),
    ]
    vase_sectors = 32
    prof_norms = []
    for k in range(len(v_profile)):
        if k == 0:
            dr = v_profile[1][0] - v_profile[0][0]
            dy = v_profile[1][1] - v_profile[0][1]
        elif k == len(v_profile) - 1:
            dr = v_profile[-1][0] - v_profile[-2][0]
            dy = v_profile[-1][1] - v_profile[-2][1]
        else:
            dr = v_profile[k + 1][0] - v_profile[k - 1][0]
            dy = v_profile[k + 1][1] - v_profile[k - 1][1]
        n_len = math.sqrt(dy * dy + dr * dr) or 1.0
        prof_norms.append((dy / n_len, -dr / n_len))

    for k, (r, y) in enumerate(v_profile):
        nr, ny = prof_norms[k]
        for s in range(vase_sectors):
            phi = s * 2 * math.pi / vase_sectors
            vase_v.append((r * math.cos(phi), y - 0.5, r * math.sin(phi)))
            vase_n.append((nr * math.cos(phi), ny, nr * math.sin(phi)))

    for i in range(len(v_profile) - 1):
        for s in range(vase_sectors):
            s_next = (s + 1) % vase_sectors
            i1 = i * vase_sectors + s + 1
            i2 = i * vase_sectors + s_next + 1
            i3 = (i + 1) * vase_sectors + s_next + 1
            i4 = (i + 1) * vase_sectors + s + 1
            vase_f.append([i1, i2, i3, i4])

    _write_obj(out_dir / "vaso_decorativo.obj", vase_v, vase_f, normals=vase_n,
               material_name="M_Vaso", material_color=(0.18, 0.65, 0.68))
    img_vase = _render_shaded_preview(vase_v, [[idx - 1 for idx in f] for f in vase_f], (70, 160, 165))
    img_vase.save(out_dir / "vaso_decorativo.jpg", quality=92)


# ---------------------------------------------------------------------------
# 07 - IESs (1 perfil sintético)
# ---------------------------------------------------------------------------


def generate_ies(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    ies_text = """IESNA:LM-63-2002
[TEST] Synthetic Spot 30D Demo
[MANUFAC] AssetDeck Procedural
[LUMCAT] SPOT-30D-SYNTH
[LUMINAIRE] Downlight LED Spot 30 Graus
TILT=NONE
1 2400 1 10 1 1 1 0.15 0.15 0.0
1.0 1.0 25.0
0 5 10 15 20 25 30 40 60 90
0
2400 2350 2100 1600 950 400 150 20 0 0
"""
    (out_dir / "spot_direcional_30graus.ies").write_text(ies_text, encoding="utf-8")


# ---------------------------------------------------------------------------
# 08 - LUTs (1 arquivo .cube)
# ---------------------------------------------------------------------------


def generate_luts(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    size = 4
    lines = [
        "# AssetDeck Synthetic Demo LUT",
        'TITLE "Filme Contraste Quente"',
        f"LUT_3D_SIZE {size}",
    ]
    for b in range(size):
        for g in range(size):
            for r in range(size):
                rf = r / (size - 1)
                gf = g / (size - 1)
                bf = b / (size - 1)
                # Contraste quente suave
                rf_out = math.pow(rf, 0.9) * 1.05
                gf_out = math.pow(gf, 0.95) * 1.02
                bf_out = math.pow(bf, 1.1) * 0.92
                lines.append(f"{min(1.0, rf_out):.6f} {min(1.0, gf_out):.6f} {min(1.0, bf_out):.6f}")

    (out_dir / "filme_contraste_quente.cube").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# 04 - VETORES (2 arquivos .svg)
# ---------------------------------------------------------------------------


def generate_vectors(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    svg1 = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500" width="500" height="500">
  <defs>
    <linearGradient id="grad1" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#3a86ff"/>
      <stop offset="100%" stop-color="#8338ec"/>
    </linearGradient>
    <linearGradient id="grad2" x1="0%" y1="100%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#ff006e"/>
      <stop offset="100%" stop-color="#fb5607"/>
    </linearGradient>
  </defs>
  <rect width="500" height="500" rx="40" fill="#1e1e24"/>
  <circle cx="250" cy="250" r="160" fill="url(#grad1)"/>
  <polygon points="250,110 370,320 130,320" fill="url(#grad2)" opacity="0.85"/>
  <circle cx="250" cy="250" r="45" fill="#ffffff"/>
</svg>
"""
    (out_dir / "icone_geometria_moderna.svg").write_text(svg1, encoding="utf-8")

    svg2 = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 400" width="600" height="400">
  <defs>
    <linearGradient id="grad3" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#06d6a0"/>
      <stop offset="100%" stop-color="#118ab2"/>
    </linearGradient>
  </defs>
  <rect width="600" height="400" rx="30" fill="#073b4c"/>
  <path d="M 120 280 L 220 120 L 320 280 L 280 280 L 220 180 L 160 280 Z" fill="url(#grad3)"/>
  <circle cx="420" cy="200" r="70" fill="none" stroke="#ffd166" stroke-width="20"/>
  <line x1="120" y1="320" x2="480" y2="320" stroke="#ffffff" stroke-width="4" stroke-dasharray="10 10"/>
</svg>
"""
    (out_dir / "logotipo_estudio_design.svg").write_text(svg2, encoding="utf-8")


def generate_library(dest: Path) -> None:
    print(f"Gerando biblioteca demo sintética em {dest}...")
    dest.mkdir(parents=True, exist_ok=True)

    generate_textures(dest / "03 - TEXTURAS")
    generate_pbr_materials(dest / "05 - MATERIAIS")
    generate_hdris(dest / "06 - HDRIs")
    generate_models(dest / "01 - MODELOS")
    generate_ies(dest / "07 - IESs")
    generate_luts(dest / "08 - LUTs")
    generate_vectors(dest / "04 - VETORES")

    print("Biblioteca demo gerada com sucesso!")


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera biblioteca sintética demo para AssetDeck.")
    parser.add_argument("dest", type=Path, help="Diretório de destino da biblioteca demo")
    args = parser.parse_args()

    generate_library(args.dest.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
