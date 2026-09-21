import math
import io
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import streamlit as st

st.set_page_config(page_title="Optimización de Aserradero", layout="wide")

st.title("🪓 Optimización y Registro de Aserrado de Troncos")
st.markdown(
    "Sistema inteligente para optimizar el aprovechamiento de troncos con Sierra Cinta y Sierra Múltiple Circular, "
    "control de calidad de bloques (Ancho Útil $\\ge 2/3 D_e$), anclaje protegido en Cota $Z = 0$ (0 mm de holgura) "
    "y canteado/re-aserrado de piezas efectivas ($7, 9, 12\\text{ cm}$)."
)

if "historial" not in st.session_state:
    st.session_state.historial = []

# --- PARÁMETROS DE ENTRADA EN BARRA LATERAL (MÁXIMO 70 CM DE DIÁMETRO) ---
st.sidebar.header("📐 Parámetros del Tronco")
d_menor = st.sidebar.number_input("Diámetro Menor / Punta (cm)", min_value=10.0, max_value=70.0, value=32.0, step=0.5)
d_mayor = st.sidebar.number_input("Diámetro Mayor / Base (cm)", min_value=10.0, max_value=70.0, value=38.0, step=0.5)
largo = st.sidebar.number_input("Largo del Tronco (cm)", min_value=50.0, max_value=1000.0, value=250.0, step=10.0)
curvatura = st.sidebar.number_input("Flecha de Curvatura (cm)", min_value=0.0, max_value=20.0, value=2.0, step=0.5)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Espesores Solicitados y Prioridades (Sierra Cinta)")
st.sidebar.caption("Marque la casilla 'Usar' para incluir la medida en la optimización:")

default_dims = [
    {"espesor": 2.0, "prioridad": 1, "activa": True},
    {"espesor": 4.0, "prioridad": 2, "activa": True},
    {"espesor": 7.0, "prioridad": 3, "activa": True},
    {"espesor": 9.0, "prioridad": 4, "activa": True},
    {"espesor": 1.5, "prioridad": 5, "activa": False},
]

inputs_espesores = []
for i, df_val in enumerate(default_dims):
    col1, col2, col3 = st.sidebar.columns([3, 3, 2])
    with col1:
        e = st.number_input(f"Dim {i+1} (cm)", min_value=0.5, max_value=30.0, value=df_val["espesor"], key=f"e_{i}")
    with col2:
        p = st.selectbox(f"Prio {i+1}", options=[1, 2, 3, 4, 5], index=df_val["prioridad"]-1, key=f"p_{i}")
    with col3:
        act = st.checkbox("Usar", value=df_val["activa"], key=f"act_{i}")
    
    if act and e > 0.0:
        inputs_espesores.append({"espesor": float(e), "prioridad": int(p)})

st.sidebar.markdown("---")
st.sidebar.header("🪚 Sierra Múltiple Circular")
kerf_cinta_mm = st.sidebar.number_input("Kerf Sierra Cinta (mm)", min_value=1.0, max_value=10.0, value=2.5, step=0.1)
kerf_multi_mm = st.sidebar.number_input("Kerf Sierra Múltiple (mm)", min_value=1.0, max_value=10.0, value=4.5, step=0.1)
t_resaw_bloque = st.sidebar.number_input("Espesor de tablas a re-aserrar de Bloques (cm)", min_value=1.0, max_value=5.0, value=2.0, step=0.5)

if d_mayor < d_menor:
    st.sidebar.warning("⚠️ El diámetro mayor debe ser ≥ al menor. Se ajustó automáticamente.")
    d_mayor = d_menor

# --- MOTOR DE OPTIMIZACIÓN MULTI-FASE ---
def optimizar_aserrado(d_menor, d_mayor, largo, curvatura, kerf_cinta_mm, kerf_multi_mm, t_resaw_bloque, dimensiones_prio):
    d_efectivo = max(1.0, d_menor - (2.0 * curvatura))
    R_ef = d_efectivo / 2.0
    kc_cinta = kerf_cinta_mm / 10.0  # cm
    kc_multi = kerf_multi_mm / 10.0  # cm
    ancho_min_bloque = (2.0 / 3.0) * d_efectivo

    # Volumen Cónico Bruto (Smalian en m3)
    r_menor_m = (d_menor / 2.0) / 100.0
    r_mayor_m = (d_mayor / 2.0) / 100.0
    largo_m = largo / 100.0
    vol_bruto_m3 = (math.pi * largo_m / 3.0) * (r_menor_m**2 + r_mayor_m**2 + (r_menor_m * r_mayor_m))

    prio_map = {item["espesor"]: item["prioridad"] for item in dimensiones_prio}
    E_list = sorted(list(prio_map.keys()))

    tablas = [e for e in E_list if e <= 4.01]
    bloques = [e for e in E_list if e > 4.01]

    if not bloques: bloques = E_list
    if not tablas: tablas = E_list

    def calc_ancho(y):
        if y < 0 or y > d_efectivo: return 0.0
        dy = abs(R_ef - y)
        if dy > R_ef: return 0.0
        return 2.0 * math.sqrt(max(0, R_ef**2 - dy**2))

    def cumple_2tercios(y_top, y_bot):
        w1 = calc_ancho(y_top)
        w2 = calc_ancho(y_bot)
        return min(w1, w2) >= ancho_min_bloque

    # Procesamiento de Sierra Múltiple
    def process_phase3_piece(t_primary, w_usable):
        if w_usable < 7.0:
            return {"pcs": {}, "total_count": 0, "w_used": 0.0, "type": "waste", "chosen_w": 0, "h_out": 0}

        available_widths = [12.0, 9.0, 7.0]

        if t_primary <= 4.01:
            # Caso 1: Tablas (<= 4 cm) -> Repetir un único ancho uniforme (7, 9 o 12 cm)
            best_w = 0.0
            best_count = 0
            max_used_w = 0.0

            for w in available_widths:
                n = int((w_usable + kc_multi) // (w + kc_multi))
                used = n * w + max(0, n - 1) * kc_multi
                if used > max_used_w:
                    max_used_w = used
                    best_w = w
                    best_count = n

            if best_count > 0:
                key = f"{t_primary:.1f}x{best_w:.0f}"
                return {
                    "type": "board",
                    "chosen_w": best_w,
                    "count": best_count,
                    "w_used": max_used_w,
                    "pcs": {key: best_count},
                    "h_out": t_primary
                }
            else:
                return {"pcs": {}, "total_count": 0, "w_used": 0.0, "type": "waste", "chosen_w": 0, "h_out": 0}
        else:
            # Caso 2: Bloques (> 4 cm) -> Re-aserrado vertical en tablas de t_resaw_bloque
            height_out = 0.0
            for w in available_widths:
                if t_primary >= w - 1e-6:
                    height_out = w
                    break

            if height_out < 7.0:
                # Si la altura del bloque es < 7cm, no entra en el contorno -> Desperdicio
                return {"pcs": {}, "total_count": 0, "w_used": 0.0, "type": "waste", "chosen_w": 0, "h_out": 0}

            n_slabs = int((w_usable + kc_multi) // (t_resaw_bloque + kc_multi))
            w_used = n_slabs * t_resaw_bloque + max(0, n_slabs - 1) * kc_multi

            key = f"{t_resaw_bloque:.1f}x{height_out:.0f}"
            return {
                "type": "block_vertical",
                "t_out": t_resaw_bloque,
                "h_out": height_out,
                "count": n_slabs,
                "w_used": w_used,
                "pcs": {key: n_slabs},
                "chosen_w": t_resaw_bloque
            }

    z_base_ef = (d_menor - d_efectivo) / 2.0
    z_top_ef = z_base_ef + d_efectivo

    best_sol = None
    best_score = -1e9

    min_hp1 = 0.25 * d_efectivo
    max_hp1 = 0.60 * d_efectivo
    p1_candidates = []
    steps_p1 = [0]

    def search_p1(seq, current_h):
        steps_p1[0] += 1
        if steps_p1[0] > 1200 or len(p1_candidates) >= 60 or len(seq) > 8: return
        if min_hp1 <= current_h <= max_hp1: p1_candidates.append((list(seq), current_h))
        if current_h > max_hp1: return

        choices = tablas if len(seq) == 0 else E_list
        for e in choices:
            y_top = d_efectivo - current_h
            y_bot = y_top - e
            if e > 4.01 and not cumple_2tercios(y_top, y_bot):
                continue
            if current_h + e <= max_hp1 + 1.0:
                seq.append(e)
                search_p1(seq, current_h + e + kc_cinta)
                seq.pop()

    search_p1([], 0.0)

    for p1_seq, h_p1 in p1_candidates[:30]:
        h_cant = d_efectivo - h_p1
        p2_candidates = []
        steps_p2 = [0]

        def search_p2(seq, current_h):
            steps_p2[0] += 1
            if steps_p2[0] > 1200 or len(p2_candidates) >= 20 or len(seq) > 8: return
            rem = h_cant - current_h
            for b in bloques:
                if abs(rem - b) <= 0.60 and (current_h + b) <= h_cant + 0.05:
                    p2_candidates.append(list(seq) + [b])
            if rem < min(bloques) and len(seq) > 0: return

            for e in E_list:
                z_top_p = h_cant - current_h
                z_bot_p = z_top_p - e
                y_orig_1 = h_cant - z_top_p
                y_orig_2 = h_cant - z_bot_p
                if e > 4.01 and not cumple_2tercios(y_orig_1, y_orig_2):
                    continue
                if current_h + e + kc_cinta + min(bloques) <= h_cant + 0.50:
                    seq.append(e)
                    search_p2(seq, current_h + e + kc_cinta)
                    seq.pop()

        search_p2([], 0.0)

        for p2_seq in p2_candidates:
            if not p2_seq or p2_seq[-1] not in bloques: continue

            piezas_cinta = []
            cotas_fase1 = []

            # FASE 1
            y_curr_ef = d_efectivo
            z_curr_bancada = z_top_ef
            for idx, t in enumerate(p1_seq):
                y_bot_ef = y_curr_ef - t
                z_cut_bancada = z_curr_bancada - t
                w_top = calc_ancho(y_curr_ef)
                w_bot = calc_ancho(y_bot_ef)
                w_min = min(w_top, w_bot)

                res_p3 = process_phase3_piece(t, w_min)

                piezas_cinta.append({
                    "id": f"F1-P{idx+1}", "origen": "Fase 1", "espesor": t,
                    "w_min": w_min, "cota_z": round(z_cut_bancada, 2), "res_p3": res_p3
                })
                cotas_fase1.append({
                    "espesor": t, "cota_z": round(z_cut_bancada, 2),
                    "tipo": "Bloque" if t > 4.01 else "Tabla",
                    "res_p3": res_p3, "w_min": w_min
                })
                y_curr_ef = y_bot_ef - kc_cinta
                z_curr_bancada = z_cut_bancada - kc_cinta

            # FASE 2: Cota 0 protegida en la base
            cotas_fase2 = []
            z_acc = 0.0
            for idx_rev, t in enumerate(reversed(p2_seq)):
                z_bot = z_acc
                z_top = z_acc + t
                y_orig_top = h_cant - z_bot
                y_orig_bot = max(0.0, h_cant - z_top)
                w_top = calc_ancho(y_orig_top)
                w_bot = calc_ancho(y_orig_bot)
                w_min = min(w_top, w_bot)

                res_p3 = process_phase3_piece(t, w_min)
                is_base = (idx_rev == 0)

                piezas_cinta.append({
                    "id": f"F2-P{len(p2_seq)-idx_rev}", "origen": "Fase 2", "espesor": t,
                    "w_min": w_min, "cota_z": round(z_bot, 2), "res_p3": res_p3
                })

                cotas_fase2.append({
                    "espesor": t, "z_bot": round(z_bot, 2), "z_top": round(z_top, 2),
                    "cota_z_corte": round(z_bot, 2),
                    "tipo": "Bloque Base (Z=0)" if is_base else ("Bloque" if t > 4.01 else "Tabla"),
                    "res_p3": res_p3, "w_min": w_min
                })
                z_acc = z_top + kc_cinta

            cotas_fase2 = list(reversed(cotas_fase2))

            # Conteo global de piezas comerciales salientes
            all_pcs = {}
            for p in piezas_cinta:
                for k, count in p["res_p3"]["pcs"].items():
                    all_pcs[k] = all_pcs.get(k, 0) + count

            vol_saliente_m3 = 0.0
            for k, count in all_pcs.items():
                parts = k.split("x")
                t_k = float(parts[0])
                w_k = float(parts[1])
                vol_saliente_m3 += (count * (t_k * w_k * largo)) / 1e6

            vol_desperdicio_m3 = max(0.0, vol_bruto_m3 - vol_saliente_m3)
            rendimiento_pct = (vol_saliente_m3 / vol_bruto_m3) * 100.0

            prio_score = sum((6 - prio_map.get(p, 5)) * 25.0 * (p**1.5 if p > 4.01 else p) for p in (p1_seq + p2_seq))
            score = (rendimiento_pct * 100.0) + prio_score - (len(p1_seq + p2_seq) * 6.0)

            if score > best_score:
                best_score = score
                best_sol = {
                    "p1_seq": p1_seq, "p2_seq": p2_seq,
                    "cotas_fase1": cotas_fase1, "cotas_fase2": cotas_fase2,
                    "h_cant": round(z_acc - kc_cinta, 2),
                    "vol_bruto_m3": vol_bruto_m3,
                    "vol_saliente_m3": vol_saliente_m3,
                    "vol_desperdicio_m3": vol_desperdicio_m3,
                    "rendimiento_pct": rendimiento_pct,
                    "all_pcs": all_pcs,
                    "total_piezas": sum(all_pcs.values()),
                    "d_efectivo": d_efectivo,
                    "kc_cinta": kc_cinta, "kc_multi": kc_multi,
                    "z_top_ef": z_top_ef
                }

    return best_sol

# --- GRÁFICO ÚNICO INTEGRADO (SUBDIVISIÓN DE PIEZAS EFECTIVAS EN EL DIBUJO DUAL) ---
def generar_grafico_unico_integrado(sol, d_menor):
    d_efectivo = sol["d_efectivo"]
    h_cant = sol["h_cant"]
    kc_cinta = sol["kc_cinta"]
    kc_multi = sol["kc_multi"]
    R = d_menor / 2.0
    R_ef = d_efectivo / 2.0

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 7.0))
    y_base_ef = (d_menor - d_efectivo) / 2.0
    y_center_ef = y_base_ef + R_ef
    y_top_ef = sol["z_top_ef"]

    def agregar_cotas_10cm(ax):
        ax.axvline(-10, color='#333333', linestyle='--', linewidth=1.0, alpha=0.75)
        ax.axvline(10, color='#333333', linestyle='--', linewidth=1.0, alpha=0.75)
        ax.text(-10, -1.2, "-10 cm", fontsize=7.5, color='#333333', ha='center')
        ax.text(10, -1.2, "+10 cm", fontsize=7.5, color='#333333', ha='center')

    # FASE 1
    ax1.set_title("FASE 1: Sierra Cinta - Tronco Entero en Bancada\n(Subdivisión Múltiple Integrada)", fontsize=10, fontweight='bold')
    ax1.set_aspect('equal')
    ax1.plot([-R*1.5, R*1.5], [0, 0], color='black', linewidth=3)
    ax1.text(0, -1.8, "BANCADA (Z = 0.0 cm)", color='darkgreen', fontweight='bold', fontsize=8.5, ha='center')
    agregar_cotas_10cm(ax1)

    ax1.add_patch(patches.Circle((0, R), R, edgecolor='#8B4513', facecolor='#D2B48C', alpha=0.3, linestyle='--'))
    ax1.add_patch(patches.Circle((0, y_center_ef), R_ef, edgecolor='#5C4033', facecolor='#F5DEB3', alpha=0.5))

    y_curr = y_top_ef
    for idx, item in enumerate(sol["cotas_fase1"]):
        t = item["espesor"]
        y_next = item["cota_z"]
        y_mid = y_curr - (t / 2.0)
        dy = abs(y_center_ef - y_mid)
        w = 2.0 * math.sqrt(max(0, R_ef**2 - dy**2)) if dy <= R_ef else 1.0

        ax1.add_patch(patches.Rectangle((-w/2.0, y_next), w, t, edgecolor='black', facecolor='#EAEDED', alpha=0.9))

        res_p3 = item["res_p3"]
        if res_p3["type"] in ["board", "block_vertical"] and res_p3["count"] > 0:
            w_used = res_p3["w_used"]
            x_start = -w_used / 2.0
            cnt = res_p3["count"]

            if res_p3["type"] == "board":
                chosen_w = res_p3["chosen_w"]
                lbl_tag = f"{t:.0f}x{chosen_w:.0f}"
                x_c = x_start
                for _ in range(cnt):
                    ax1.add_patch(patches.Rectangle((x_c, y_next), chosen_w, t, facecolor='#2EA44E', edgecolor='black', linewidth=0.7, alpha=0.85))
                    ax1.text(x_c + chosen_w/2.0, y_next + t/2.0, lbl_tag, color='white', fontweight='bold', fontsize=7, ha='center', va='center')
                    x_c += chosen_w + kc_multi
            else:
                t_out = res_p3["t_out"]
                h_out = res_p3["h_out"]
                lbl_tag = f"{t_out:.0f}x{h_out:.0f}"
                x_c = x_start
                for _ in range(cnt):
                    ax1.add_patch(patches.Rectangle((x_c, y_next), t_out, h_out, facecolor='#1F618D', edgecolor='black', linewidth=0.7, alpha=0.85))
                    ax1.text(x_c + t_out/2.0, y_next + h_out/2.0, lbl_tag, color='white', fontweight='bold', fontsize=6.5, ha='center', va='center', rotation=90)
                    x_c += t_out + kc_multi

        ax1.axhline(y_next, color='#D32F2F', linestyle=':', linewidth=1.2)
        ax1.text(R*1.04, y_next + 0.35, f"Corte #{idx+1}: Z = {y_next:.2f} cm", fontsize=8.0, fontweight='normal', color='black', va='bottom', family='sans-serif')
        y_curr = y_next - kc_cinta

    y_cut_line = y_curr + kc_cinta
    ax1.axhline(y_cut_line, color='purple', linestyle='--', linewidth=2.0)
    ax1.text(0, y_cut_line - 1.5, f"VOLTEAR 180° (Cantón h={h_cant:.1f} cm)", color='purple', fontweight='bold', fontsize=8.5, ha='center', bbox=dict(boxstyle='round,pad=0.2', facecolor='yellow', alpha=0.9))
    ax1.set_xlim(-R*1.7, R*1.85)
    ax1.set_ylim(-3.5, d_menor + 3.5)
    ax1.set_ylabel("Altura Z sobre Bancada (cm)")
    ax1.grid(True, linestyle=':', alpha=0.4)

    # FASE 2
    ax2.set_title("FASE 2: Sierra Cinta - Cantón Volteado 180°\n(Asiento en Cota Z=0.00 cm)", fontsize=10, fontweight='bold')
    ax2.set_aspect('equal')
    ax2.plot([-R*1.5, R*1.5], [0, 0], color='black', linewidth=3)
    ax2.text(0, -1.8, "COTA 0.00 CM: Asiento Plano en Bancada", color='darkgreen', fontweight='bold', fontsize=8.5, ha='center')
    agregar_cotas_10cm(ax2)

    t_vals = np.linspace(0, 2*math.pi, 500)
    x_ef_p2 = R_ef * np.cos(t_vals)
    y_ef_p2 = y_cut_line - (y_center_ef + R_ef * np.sin(t_vals))
    valid_ef = y_ef_p2 >= -0.01
    ax2.fill(x_ef_p2[valid_ef], y_ef_p2[valid_ef], color='#F5DEB3', alpha=0.55, edgecolor='#5C4033', linewidth=1.5)

    num_fase1 = len(sol["cotas_fase1"])
    corte_count_fase2 = num_fase1

    for idx, item in enumerate(sol["cotas_fase2"]):
        t = item["espesor"]
        z_bot = item["z_bot"]
        z_top = item["z_top"]
        z_mid = (z_bot + z_top) / 2.0
        y_orig_mid = h_cant - z_mid
        dy = abs(R_ef - y_orig_mid)
        w = 2.0 * math.sqrt(max(0, R_ef**2 - dy**2)) if dy <= R_ef else 1.0

        is_last = (idx == len(sol["cotas_fase2"]) - 1)

        ax2.add_patch(patches.Rectangle((-w/2.0, z_bot), w, t, edgecolor='black', facecolor='#27AE60' if is_last else '#EAEDED', alpha=0.9))

        res_p3 = item["res_p3"]
        if res_p3["type"] in ["board", "block_vertical"] and res_p3["count"] > 0:
            w_used = res_p3["w_used"]
            x_start = -w_used / 2.0
            cnt = res_p3["count"]

            if res_p3["type"] == "board":
                chosen_w = res_p3["chosen_w"]
                lbl_tag = f"{t:.0f}x{chosen_w:.0f}"
                x_c = x_start
                for _ in range(cnt):
                    ax2.add_patch(patches.Rectangle((x_c, z_bot), chosen_w, t, facecolor='#2EA44E', edgecolor='black', linewidth=0.7, alpha=0.85))
                    ax2.text(x_c + chosen_w/2.0, z_bot + t/2.0, lbl_tag, color='white', fontweight='bold', fontsize=7, ha='center', va='center')
                    x_c += chosen_w + kc_multi
            else:
                t_out = res_p3["t_out"]
                h_out = res_p3["h_out"]
                lbl_tag = f"{t_out:.0f}x{h_out:.0f}"
                x_c = x_start
                for _ in range(cnt):
                    ax2.add_patch(patches.Rectangle((x_c, z_bot), t_out, h_out, facecolor='#1F618D', edgecolor='black', linewidth=0.7, alpha=0.85))
                    ax2.text(x_c + t_out/2.0, z_bot + h_out/2.0, lbl_tag, color='white', fontweight='bold', fontsize=6.5, ha='center', va='center', rotation=90)
                    x_c += t_out + kc_multi

        if z_bot > 0.001:
            corte_count_fase2 += 1
            ax2.axhline(z_bot, color='#D32F2F', linestyle=':', linewidth=1.2)
            ax2.text(R*1.04, z_bot + 0.35, f"Corte #{corte_count_fase2}: Z = {z_bot:.2f} cm", fontsize=8.0, fontweight='normal', color='black', va='bottom', family='sans-serif')

    ax2.set_xlim(-R*1.7, R*1.85)
    ax2.set_ylim(-3.5, d_menor + 3.5)
    ax2.set_ylabel("Altura Z sobre Bancada (cm)")
    ax2.grid(True, linestyle=':', alpha=0.4)

    plt.tight_layout()
    return fig

# --- EJECUCIÓN Y RENDERIZADO ---
if not inputs_espesores:
    st.info("👉 **Por favor marque la casilla 'Usar' en al menos un espesor de la barra lateral** para iniciar el cálculo.")
else:
    sol = optimizar_aserrado(d_menor, d_mayor, largo, curvatura, kerf_cinta_mm, kerf_multi_mm, t_resaw_bloque, inputs_espesores)

    if sol:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Volumen Cónico Entrada (Smalian)", f"{sol['vol_bruto_m3']:.3f} m³")
        m2.metric("Volumen Saliente Comercial Final", f"{sol['vol_saliente_m3']:.3f} m³")
        m3.metric("Total Piezas Efectivas", f"{sol['total_piezas']} pzs")
        m4.metric("Rendimiento Comercial Real", f"{sol['rendimiento_pct']:.1f} %")

        st.markdown("---")
        st.subheader("📐 Diagrama de Aserrado Integrado (Sierra Cinta + Subdivisión Múltiple en Dibujo Único)")
        st.pyplot(generar_grafico_unico_integrado(sol, d_menor))

        # --- PLAN DE CORTE OPERATIVO ---
        st.markdown("### 📋 Plan de Corte Paso a Paso para Operador")
        col_p1, col_p2 = st.columns(2)

        with col_p1:
            st.markdown("**FASE 1: Cortes Tronco Entero**")
            plan_f1_data = [
                {
                    "N° Corte": f"Corte #{idx+1}",
                    "Cota de Sierra (Z)": f"{item['cota_z']:.2f} cm",
                    "Pieza Primaria": f"{item['tipo']} de {item['espesor']:.1f} cm",
                    "Resultado Sierra Múltiple": f"{item['res_p3']['pcs']}" if item['res_p3']['pcs'] else "Desperdicio"
                }
                for idx, item in enumerate(sol["cotas_fase1"])
            ]
            st.table(pd.DataFrame(plan_f1_data))
            st.info(f"💡 **Acción:** Voltear cantón de **{sol['h_cant']:.1f} cm** exactamente 180°.")

        with col_p2:
            st.markdown("**FASE 2: Cortes Cantón Volteado (Asiento Z=0.00 cm)**")
            plan_f2_data = []
            c_num = len(sol["cotas_fase1"])
            for idx, item in enumerate(sol["cotas_fase2"]):
                if item["z_bot"] > 0.001:
                    c_num += 1
                    plan_f2_data.append({
                        "N° Corte": f"Corte #{c_num}",
                        "Cota de Sierra (Z)": f"{item['cota_z_corte']:.2f} cm",
                        "Pieza Primaria": f"{item['tipo']} de {item['espesor']:.1f} cm",
                        "Resultado Sierra Múltiple": f"{item['res_p3']['pcs']}" if item['res_p3']['pcs'] else "Desperdicio"
                    })
                else:
                    plan_f2_data.append({
                        "N° Corte": "Base (Sin Corte)",
                        "Cota de Sierra (Z)": "0.00 cm (Apoyo)",
                        "Pieza Primaria": f"Bloque Base de {item['espesor']:.1f} cm",
                        "Resultado Sierra Múltiple": f"{item['res_p3']['pcs']}" if item['res_p3']['pcs'] else "Desperdicio"
                    })
            st.table(pd.DataFrame(plan_f2_data))

        # --- RESUMEN DE PRODUCCIÓN (MATERIA PRIMA VS. PIEZAS EFECTIVAS SALIENTES) ---
        st.markdown("---")
        st.markdown("## 📊 Resumen de Producción del Tronco Actual")

        col_ent, col_sal = st.columns(2)

        with col_ent:
            st.markdown("#### 📥 Madera Entrante (Materia Prima)")
            df_entrante = pd.DataFrame([
                {"Parámetro": "Diámetro Menor / Punta", "Valor": f"{d_menor:.1f} cm"},
                {"Parámetro": "Diámetro Mayor / Base", "Valor": f"{d_mayor:.1f} cm"},
                {"Parámetro": "Largo del Tronco", "Valor": f"{largo:.1f} cm"},
                {"Parámetro": "Flecha de Curvatura", "Valor": f"{curvatura:.1f} cm"},
                {"Parámetro": "Diámetro Útil Efectivo", "Valor": f"{sol['d_efectivo']:.1f} cm"},
                {"Parámetro": "Volumen Cónico Bruto (Smalian)", "Valor": f"{sol['vol_bruto_m3']:.4f} m³"}
            ])
            st.table(df_entrante)

        with col_sal:
            st.markdown("#### 📤 Madera Saliente en Piezas Comerciales Efectivas")
            rows_saliente = []
            for dim_str, count in sol["all_pcs"].items():
                parts = dim_str.split("x")
                t_k = float(parts[0])
                w_k = float(parts[1])
                v_k = (count * (t_k * w_k * largo)) / 1e6
                rows_saliente.append({
                    "Medida Comercial (Espesor x Ancho x Largo)": f"{t_k:.1f} cm x {w_k:.0f} cm x {largo:.0f} cm",
                    "Piezas Resultantes": f"{count} pzs",
                    "Volumen (m³)": round(v_k, 4),
                    "% del Tronco": round((v_k / sol['vol_bruto_m3']) * 100.0, 2)
                })

            rows_saliente.append({
                "Medida Comercial (Espesor x Ancho x Largo)": "TOTAL MADERA SALIENTE ÚTIL",
                "Piezas Resultantes": f"{sol['total_piezas']} pzs",
                "Volumen (m³)": round(sol['vol_saliente_m3'], 4),
                "% del Tronco": round(sol['rendimiento_pct'], 2)
            })
            rows_saliente.append({
                "Medida Comercial (Espesor x Ancho x Largo)": "Viruta + Costeros / Desperdicio Total",
                "Piezas Resultantes": "-",
                "Volumen (m³)": round(sol['vol_desperdicio_m3'], 4),
                "% del Tronco": round(100.0 - sol['rendimiento_pct'], 2)
            })
            st.table(pd.DataFrame(rows_saliente))

        col_btn, _ = st.columns([4, 6])
        with col_btn:
            if st.button("📌 Registrar Tronco Procesado en Reporte Diario", type="primary", use_container_width=True):
                st.session_state.historial.append({
                    "ID": len(st.session_state.historial) + 1,
                    "D.Menor (cm)": d_menor,
                    "D.Mayor (cm)": d_mayor,
                    "Largo (cm)": largo,
                    "m³ Entrada": round(sol["vol_bruto_m3"], 4),
                    "Total Piezas": sol["total_piezas"],
                    "Detalle Piezas": f"{sol['all_pcs']}",
                    "m³ Saliente Útil": round(sol["vol_saliente_m3"], 4),
                    "m³ Desperdicio": round(sol["vol_desperdicio_m3"], 4),
                    "Rendimiento (%)": round(sol["rendimiento_pct"], 2)
                })
                st.success("¡Tronco agregado al registro de producción diario!")

# --- REPORTE ACUMULADO DIARIO Y DESCARGA EXCEL ---
st.markdown("---")
st.markdown("## 📊 Reporte Acumulado Diario de Producción")

if st.session_state.historial:
    df_hist = pd.DataFrame(st.session_state.historial)

    tot_bruto = df_hist["m³ Entrada"].sum()
    tot_util = df_hist["m³ Saliente Útil"].sum()
    tot_desp = df_hist["m³ Desperdicio"].sum()
    tot_pzs_gen = df_hist["Total Piezas"].sum()
    prom_rend = (tot_util / tot_bruto * 100.0) if tot_bruto > 0 else 0.0

    st1, st2, st3, st4, st5 = st.columns(5)
    st1.metric("Total m³ Entrada", f"{tot_bruto:.3f} m³")
    st2.metric("Total m³ Útil Saliente", f"{tot_util:.3f} m³")
    st3.metric("Total Piezas Producidas", f"{tot_pzs_gen} pzs")
    st4.metric("Total m³ Desperdicio", f"{tot_desp:.3f} m³")
    st5.metric("Rendimiento Global", f"{prom_rend:.1f} %")

    row_total = {
        "ID": "TOTAL",
        "D.Menor (cm)": "-", "D.Mayor (cm)": "-", "Largo (cm)": "-",
        "m³ Entrada": round(tot_bruto, 4),
        "Total Piezas": tot_pzs_gen,
        "Detalle Piezas": "-",
        "m³ Saliente Útil": round(tot_util, 4),
        "m³ Desperdicio": round(tot_desp, 4),
        "Rendimiento (%)": round(prom_rend, 2)
    }

    df_export = pd.concat([df_hist, pd.DataFrame([row_total])], ignore_index=True)
    st.dataframe(df_export, use_container_width=True)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_export.to_excel(writer, index=False, sheet_name='Reporte_Produccion_Diaria')

    st.download_button(
        label="📥 Descargar Reporte de Producción Completo (.xlsx)",
        data=output.getvalue(),
        file_name="reporte_aserradero_produccion.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary"
    )
