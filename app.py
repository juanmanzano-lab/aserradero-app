import math
import io
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import streamlit as st

st.set_page_config(page_title="Optimización de Aserradero", layout="wide")

st.title("🪓 Optimización y Registro de Aserrado de Troncos")
st.markdown("Sistema inteligente con cálculo cónico de tronco ($D_{menor}$, $D_{mayor}$, $Largo$, $Curvatura$) y control de asiento en Cota 0.")

if "historial" not in st.session_state:
    st.session_state.historial = []

# --- PARÁMETROS DE ENTRADA ---
st.sidebar.header("📐 Parámetros del Tronco")
d_menor = st.sidebar.number_input("Diámetro Menor / Punta (cm)", min_value=10.0, max_value=100.0, value=32.0, step=0.5)
d_mayor = st.sidebar.number_input("Diámetro Mayor / Base (cm)", min_value=10.0, max_value=120.0, value=38.0, step=0.5)
largo = st.sidebar.number_input("Largo del Tronco (cm)", min_value=50.0, max_value=1000.0, value=250.0, step=10.0)
curvatura = st.sidebar.number_input("Flecha de Curvatura (cm)", min_value=0.0, max_value=20.0, value=2.0, step=0.5)
kerf_mm = st.sidebar.number_input("Espesor de Corte / Kerf (mm)", min_value=1.0, max_value=10.0, value=2.5, step=0.1)

# Validación de geometría
if d_mayor < d_menor:
    st.sidebar.warning("⚠️ El diámetro mayor debe ser mayor o igual al menor. Se igualarán automáticamenete.")
    d_mayor = d_menor

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Medidas Solicitadas y Prioridades")

default_dims = [
    {"espesor": 2.0, "prio": 3, "activa": True},
    {"espesor": 6.0, "prio": 1, "activa": True},
    {"espesor": 9.0, "prio": 2, "activa": True},
    {"espesor": 4.0, "prio": 4, "activa": True},
    {"espesor": 1.5, "prio": 5, "activa": False},
]

inputs_espesores = []
for i, df_val in enumerate(default_dims):
    col1, col2, col3 = st.sidebar.columns([3, 3, 2])
    with col1:
        e = st.number_input(f"Dim {i+1} (cm)", min_value=0.5, max_value=30.0, value=df_val["espesor"], key=f"e_{i}")
    with col2:
        p = st.selectbox(f"Prioridad {i+1}", options=[1, 2, 3, 4, 5], index=df_val["prio"]-1, key=f"p_{i}")
    with col3:
        act = st.checkbox("Usar", value=df_val["activa"], key=f"act_{i}")
    
    if act:
        inputs_espesores.append({"espesor": float(e), "prioridad": int(p)})

# --- MOTOR DE OPTIMIZACIÓN CÓNICA Y CORTES ---
def optimizar_aserrado(d_menor, d_mayor, largo, curvatura, kerf_mm, dimensiones_prio):
    # Cálculo del Diámetro Útil Mínimo considerando Curvatura
    d_efectivo = max(1.0, d_menor - (2.0 * curvatura))
    R_ef = d_efectivo / 2.0
    kc = kerf_mm / 10.0  # cm
    ancho_min_bloque = (2.0 / 3.0) * d_efectivo

    # Volumen Bruto Cónico Real (Fórmula Frustrum / Smalian)
    r_menor_m = (d_menor / 2.0) / 100.0
    r_mayor_m = (d_mayor / 2.0) / 100.0
    largo_m = largo / 100.0
    vol_bruto_m3 = (math.pi * largo_m / 3.0) * (r_menor_m**2 + r_mayor_m**2 + (r_menor_m * r_mayor_m))

    prio_map = {item["espesor"]: item["prioridad"] for item in dimensiones_prio if item["espesor"] > 0}
    E_list = sorted(list(prio_map.keys()))
    
    tablas = [e for e in E_list if e <= 2.01]
    bloques = [e for e in E_list if e > 2.01]

    if not bloques: bloques = [6.0]
    if not tablas: tablas = [2.0]

    def calc_ancho(y):
        if y < 0 or y > d_efectivo: return 0.0
        dy = abs(R_ef - y)
        if dy > R_ef: return 0.0
        return 2.0 * math.sqrt(max(0, R_ef**2 - dy**2))

    def cumple_2tercios(y_top, y_bot):
        w1 = calc_ancho(y_top)
        w2 = calc_ancho(y_bot)
        return min(w1, w2) >= ancho_min_bloque

    def area_pieza(y_top, y_bot):
        return ((calc_ancho(y_top) + calc_ancho(y_bot)) / 2.0) * abs(y_top - y_bot)

    z_base_ef = (d_menor - d_efectivo) / 2.0
    z_top_ef = z_base_ef + d_efectivo

    best_sol = None
    best_score = -1e9

    min_hp1 = 0.25 * d_efectivo
    max_hp1 = 0.60 * d_efectivo
    p1_candidates = []
    steps_p1 = [0]
    MAX_STEPS = 1200

    def search_p1(seq, current_h):
        steps_p1[0] += 1
        if steps_p1[0] > MAX_STEPS or len(p1_candidates) >= 60 or len(seq) > 8: return
        if min_hp1 <= current_h <= max_hp1: p1_candidates.append((list(seq), current_h))
        if current_h > max_hp1: return

        choices = tablas if len(seq) == 0 else (tablas + bloques)
        for e in choices:
            y_top = d_efectivo - current_h
            y_bot = y_top - e
            if current_h + e <= max_hp1 + 1.0:
                seq.append(e)
                search_p1(seq, current_h + e + kc)
                seq.pop()

    search_p1([], 0.0)

    for p1_seq, h_p1 in p1_candidates[:30]:
        h_cant = d_efectivo - h_p1
        p2_candidates = []
        steps_p2 = [0]

        def search_p2(seq, current_h):
            steps_p2[0] += 1
            if steps_p2[0] > MAX_STEPS or len(p2_candidates) >= 20 or len(seq) > 8: return
            rem = h_cant - current_h
            for b in bloques:
                if abs(rem - b) <= 0.60 and (current_h + b) <= h_cant + 0.05:
                    p2_candidates.append(list(seq) + [b])
            if rem < min(bloques) and len(seq) > 0: return

            choices = tablas + bloques
            for e in choices:
                if current_h + e + kc + min(bloques) <= h_cant + 0.50:
                    seq.append(e)
                    search_p2(seq, current_h + e + kc)
                    seq.pop()

        search_p2([], 0.0)

        for p2_seq in p2_candidates:
            if not p2_seq or p2_seq[-1] not in bloques: continue

            vol1, vol_bloques, vol_tablas = 0.0, 0.0, 0.0
            y_curr_ef = d_efectivo
            z_curr_bancada = z_top_ef
            cotas_fase1 = []

            for t in p1_seq:
                y_bot_ef = y_curr_ef - t
                z_cut_bancada = z_curr_bancada - t
                v_p = area_pieza(y_curr_ef, y_bot_ef) * largo
                vol1 += area_pieza(y_curr_ef, y_bot_ef)
                cotas_fase1.append({"espesor": t, "cota_z": round(z_cut_bancada, 2), "tipo": "Bloque" if t > 2.01 else "Tabla"})
                if t > 2.01: vol_bloques += v_p
                else: vol_tablas += v_p
                y_curr_ef = y_bot_ef - kc
                z_curr_bancada = z_cut_bancada - kc

            vol2 = 0.0
            fase2_items = []
            z_acc = 0.0  # Anclaje directo en Z=0 (Sin holgura)

            for idx_rev, t in enumerate(reversed(p2_seq)):
                z_bot = z_acc
                z_top = z_acc + t
                is_base = (idx_rev == 0)
                y_orig_top = h_cant - z_bot
                y_orig_bot = max(0.0, h_cant - z_top)
                v_p = area_pieza(y_orig_top, y_orig_bot) * largo
                vol2 += area_pieza(y_orig_top, y_orig_bot)

                fase2_items.append({
                    "espesor": t,
                    "z_bot": round(z_bot, 2),
                    "z_top": round(z_top, 2),
                    "cota_z_corte": round(z_bot, 2),
                    "tipo": "Bloque Base (Z=0)" if is_base else ("Bloque" if t > 2.01 else "Tabla")
                })
                if t > 2.01: vol_bloques += v_p
                else: vol_tablas += v_p
                z_acc = z_top + kc

            cotas_fase2 = list(reversed(fase2_items))
            h_cant_real = round(z_acc - kc, 2)

            total_vol_m3 = ((vol1 + vol2) * largo) / 1e6
            vol_bloques_m3 = vol_bloques / 1e6
            vol_tablas_m3 = vol_tablas / 1e6

            n_cortes = len(p1_seq) + len(p2_seq) - 1
            area_prom = (vol1 + vol2) / n_cortes if n_cortes > 0 else 0
            vol_kerf_m3 = (n_cortes * kc * area_prom * largo) / 1e6
            vol_desperdicio_m3 = max(0.0, vol_bruto_m3 - total_vol_m3 - vol_kerf_m3)
            rendimiento_pct = (total_vol_m3 / vol_bruto_m3) * 100.0

            prio_score = sum((6 - prio_map.get(p, 5)) * 20.0 * (p**1.5 if p > 2.01 else p) for p in (p1_seq + p2_seq))
            score = (rendimiento_pct * 50.0) + prio_score - (len(p1_seq + p2_seq) * 8.0)

            if score > best_score:
                best_score = score
                best_sol = {
                    "p1_seq": p1_seq, "p2_seq": p2_seq,
                    "cotas_fase1": cotas_fase1, "cotas_fase2": cotas_fase2,
                    "h_cant": h_cant_real, "vol_m3": total_vol_m3,
                    "vol_bruto_m3": vol_bruto_m3, "vol_bloques_m3": vol_bloques_m3,
                    "vol_tablas_m3": vol_tablas_m3, "vol_kerf_m3": vol_kerf_m3,
                    "vol_desperdicio_m3": vol_desperdicio_m3,
                    "aprovechamiento_pct": rendimiento_pct,
                    "n_bloques": sum(1 for x in (p1_seq + p2_seq) if x > 2.01),
                    "n_tablas": sum(1 for x in (p1_seq + p2_seq) if x <= 2.01),
                    "d_efectivo": d_efectivo, "kc": kc, "z_top_ef": z_top_ef
                }

    return best_sol

# --- GRÁFICO ---
def generar_grafico_cortes(sol, d_menor):
    d_efectivo = sol["d_efectivo"]
    h_cant = sol["h_cant"]
    kc = sol["kc"]
    R = d_menor / 2.0
    R_ef = d_efectivo / 2.0
    diff_d = d_menor - d_efectivo

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6.5))
    y_base_ef = diff_d / 2.0
    y_center_ef = y_base_ef + R_ef
    y_top_ef = sol["z_top_ef"]

    def agregar_cotas_10cm(ax):
        ax.axvline(-10, color='#333333', linestyle='--', linewidth=1.0, alpha=0.7)
        ax.axvline(10, color='#333333', linestyle='--', linewidth=1.0, alpha=0.7)
        ax.text(-10, -1.2, "-10 cm", fontsize=7.5, color='#333333', ha='center')
        ax.text(10, -1.2, "+10 cm", fontsize=7.5, color='#333333', ha='center')

    # FASE 1
    ax1.set_title("FASE 1: Tronco Entero\n(Posicionamiento de Sierra desde Arriba)", fontsize=11, fontweight='bold')
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
        color = '#1E88E5' if t > 2.01 else '#FFB300'

        ax1.add_patch(patches.Rectangle((-w/2.0, y_next), w, t, edgecolor='black', facecolor=color, alpha=0.85))
        ax1.text(0, y_mid, f"{item['tipo']} {t:.1f} cm", color='white' if t > 2.01 else 'black', fontweight='bold', fontsize=8.5, ha='center', va='center')
        ax1.axhline(y_next, color='#D32F2F', linestyle=':', linewidth=1.0)
        ax1.text(R*1.04, y_next + 0.35, f"Corte #{idx+1}: Z = {y_next:.2f} cm", fontsize=7.5, color='black', family='sans-serif')
        y_curr = y_next - kc

    y_cut_line = y_curr + kc
    ax1.axhline(y_cut_line, color='purple', linestyle='--', linewidth=2.0)
    ax1.text(0, y_cut_line - 1.5, f"VOLTEAR 180° (Cantón h={h_cant:.1f} cm)", color='purple', fontweight='bold', fontsize=8.5, ha='center', bbox=dict(boxstyle='round,pad=0.2', facecolor='yellow', alpha=0.9))
    ax1.set_xlim(-R*1.7, R*1.85)
    ax1.set_ylim(-3.5, d_menor + 3.5)
    ax1.set_ylabel("Altura Z sobre Bancada (cm)")
    ax1.grid(True, linestyle=':', alpha=0.4)

    # FASE 2
    ax2.set_title("FASE 2: Cantón Volteado 180°\n(Asiento Perfecto en Cota 0 | 0 mm Holgura)", fontsize=11, fontweight='bold')
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
    for idx, item in enumerate(sol["cotas_fase2"]):
        t = item["espesor"]
        z_bot = item["z_bot"]
        z_top = item["z_top"]
        z_mid = (z_bot + z_top) / 2.0
        y_orig_mid = h_cant - z_mid
        dy = abs(R_ef - y_orig_mid)
        w = 2.0 * math.sqrt(max(0, R_ef**2 - dy**2)) if dy <= R_ef else 1.0

        is_last = (idx == len(sol["cotas_fase2"]) - 1)
        color = '#2E7D32' if is_last else ('#0D47A1' if t > 2.01 else '#FB8C00')

        ax2.add_patch(patches.Rectangle((-w/2.0, z_bot), w, t, edgecolor='black', facecolor=color, alpha=0.9))
        tag = f"BLOQUE BASE {t:.1f} cm (Z=0.00)" if is_last else f"{'Bloque' if t > 2.01 else 'Tabla'} {t:.1f} cm"
        ax2.text(0, z_mid, tag, color='white', fontweight='bold', fontsize=8.5, ha='center', va='center')

        if z_bot > 0.001:
            ax2.axhline(z_bot, color='#D32F2F', linestyle=':', linewidth=1.0)
            ax2.text(R*1.04, z_bot + 0.35, f"Corte #{num_fase1 + idx + 1}: Z = {z_bot:.2f} cm", fontsize=7.5, color='black', family='sans-serif')

    ax2.set_xlim(-R*1.7, R*1.85)
    ax2.set_ylim(-3.5, d_menor + 3.5)
    ax2.set_ylabel("Altura Z sobre Bancada (cm)")
    ax2.grid(True, linestyle=':', alpha=0.4)

    plt.tight_layout()
    return fig

# --- RESULTADOS ---
sol = optimizar_aserrado(d_menor, d_mayor, largo, curvatura, kerf_mm, inputs_espesores)

if sol:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Volumen Cónico Entrada (Smalian)", f"{sol['vol_bruto_m3']:.3f} m³")
    m2.metric("Volumen Útil Comercial", f"{sol['vol_m3']:.3f} m³")
    m3.metric("Rendimiento / Aprovechamiento", f"{sol['aprovechamiento_pct']:.1f} %")
    m4.metric("Diámetro Útil Efectivo", f"{sol['d_efectivo']:.1f} cm")

    st.markdown("---")
    st.pyplot(generar_grafico_cortes(sol, d_menor))

    st.markdown("### 📈 Reporte de Proyección de Aprovechamiento del Tronco")
    df_desglose = pd.DataFrame([
        {"Categoría": "Bloques Comerciales (Ancho útil ≥ 2/3 D_e)", "Volumen (m³)": round(sol["vol_bloques_m3"], 4), "% del Total": round((sol["vol_bloques_m3"]/sol["vol_bruto_m3"])*100, 2)},
        {"Categoría": "Tablas Auxiliares / Laterales", "Volumen (m³)": round(sol["vol_tablas_m3"], 4), "% del Total": round((sol["vol_tablas_m3"]/sol["vol_bruto_m3"])*100, 2)},
        {"Categoría": "Pérdida por Sangría (Kerf de Sierra)", "Volumen (m³)": round(sol["vol_kerf_m3"], 4), "% del Total": round((sol["vol_kerf_m3"]/sol["vol_bruto_m3"])*100, 2)},
        {"Categoría": "Costeros / Desperdicio por Curvatura y Conicidad", "Volumen (m³)": round(sol["vol_desperdicio_m3"], 4), "% del Total": round((sol["vol_desperdicio_m3"]/sol["vol_bruto_m3"])*100, 2)}
    ])
    st.table(df_desglose)