import math
import io
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import streamlit as st

st.set_page_config(page_title="Optimización de Aserradero", layout="wide")

st.title("🪓 Optimización y Pronóstico de Aserrado (Sierra Cinta + Sierra Múltiple)")
st.markdown(
    "Sistema de planificación en 3 Fases: **Fase 1 y 2 (Sierra Cinta)** para cortes longitudinales y "
    "**Fase 3 (Sierra Múltiple Circular)** para canteado y re-aserrado de piezas finales ($2\\times7$, $2\\times9$, $4\\times7$, $4\\times9$)."
)

if "historial" not in st.session_state:
    st.session_state.historial = []

# --- PARÁMETROS DE ENTRADA ---
st.sidebar.header("📐 Parámetros del Tronco")
d_menor = st.sidebar.number_input("Diámetro Menor / Punta (cm)", min_value=10.0, max_value=100.0, value=32.0, step=0.5)
d_mayor = st.sidebar.number_input("Diámetro Mayor / Base (cm)", min_value=10.0, max_value=120.0, value=38.0, step=0.5)
largo = st.sidebar.number_input("Largo del Tronco (cm)", min_value=50.0, max_value=1000.0, value=250.0, step=10.0)
curvatura = st.sidebar.number_input("Flecha de Curvatura (cm)", min_value=0.0, max_value=20.0, value=2.0, step=0.5)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Especificaciones de Sierras")
kerf_cinta_mm = st.sidebar.number_input("Kerf Sierra Cinta (mm)", min_value=1.0, max_value=10.0, value=2.5, step=0.1)
kerf_multi_mm = st.sidebar.number_input("Kerf Sierra Múltiple Circular (mm)", min_value=1.0, max_value=10.0, value=4.5, step=0.1)

if d_mayor < d_menor:
    st.sidebar.warning("⚠️ El diámetro mayor debe ser mayor o igual al menor. Se ajustó automáticamente.")
    d_mayor = d_menor

# --- ALGORITMO DE OPTIMIZACIÓN MULTI-FASE ---
def optimizar_aserrado_completo(d_menor, d_mayor, largo, curvatura, kerf_cinta_mm, kerf_multi_mm):
    d_efectivo = max(1.0, d_menor - (2.0 * curvatura))
    R_ef = d_efectivo / 2.0
    kc_cinta = kerf_cinta_mm / 10.0  # cm
    kc_multi = kerf_multi_mm / 10.0  # cm

    # Volumen Bruto Cónico Real (Fórmula de Smalian en m3)
    r_menor_m = (d_menor / 2.0) / 100.0
    r_mayor_m = (d_mayor / 2.0) / 100.0
    largo_m = largo / 100.0
    vol_bruto_m3 = (math.pi * largo_m / 3.0) * (r_menor_m**2 + r_mayor_m**2 + (r_menor_m * r_mayor_m))

    # Opciones de corte primario en Sierra Cinta
    tablas_cinta = [2.0]
    bloques_cinta = [4.0, 7.0, 8.0, 9.0]

    def calc_ancho(y):
        if y < 0 or y > d_efectivo: return 0.0
        dy = abs(R_ef - y)
        if dy > R_ef: return 0.0
        return 2.0 * math.sqrt(max(0, R_ef**2 - dy**2))

    def min_ancho_pieza(y_top, y_bot):
        # Garantiza producto completo (Non-wane width a lo largo del plano útil)
        return min(calc_ancho(y_top), calc_ancho(y_bot))

    z_base_ef = (d_menor - d_efectivo) / 2.0
    z_top_ef = z_base_ef + d_efectivo

    # Búsqueda de la mejor combinación en Sierra Cinta
    min_hp1 = 0.25 * d_efectivo
    max_hp1 = 0.60 * d_efectivo
    p1_candidates = []
    steps_p1 = [0]

    def search_p1(seq, current_h):
        steps_p1[0] += 1
        if steps_p1[0] > 1200 or len(p1_candidates) >= 60 or len(seq) > 8: return
        if min_hp1 <= current_h <= max_hp1: p1_candidates.append((list(seq), current_h))
        if current_h > max_hp1: return

        choices = tablas_cinta if len(seq) == 0 else (tablas_cinta + bloques_cinta)
        for e in choices:
            if current_h + e <= max_hp1 + 1.0:
                seq.append(e)
                search_p1(seq, current_h + e + kc_cinta)
                seq.pop()

    search_p1([], 0.0)

    # Función para optimizar canteado a anchos de 7cm y 9cm
    def calc_edging(w_usable):
        if w_usable < 7.0: return 0, 0, 0.0
        best_n7, best_n9 = 0, 0
        max_used = 0.0
        max_7 = int((w_usable + kc_multi) // (7.0 + kc_multi)) + 1
        max_9 = int((w_usable + kc_multi) // (9.0 + kc_multi)) + 1
        
        for n7 in range(max_7 + 1):
            for n9 in range(max_9 + 1):
                if n7 == 0 and n9 == 0: continue
                total_w = n7 * 7.0 + n9 * 9.0 + (n7 + n9 - 1) * kc_multi
                if total_w <= w_usable + 1e-6:
                    if total_w > max_used:
                        max_used = total_w
                        best_n7, best_n9 = n7, n9
        return best_n7, best_n9, max_used

    best_sol = None
    best_score = -1e9

    for p1_seq, h_p1 in p1_candidates[:30]:
        h_cant = d_efectivo - h_p1
        p2_candidates = []
        steps_p2 = [0]

        def search_p2(seq, current_h):
            steps_p2[0] += 1
            if steps_p2[0] > 1200 or len(p2_candidates) >= 20 or len(seq) > 8: return
            rem = h_cant - current_h
            for b in bloques_cinta:
                if abs(rem - b) <= 0.60 and (current_h + b) <= h_cant + 0.05:
                    p2_candidates.append(list(seq) + [b])
            if rem < min(bloques_cinta) and len(seq) > 0: return

            choices = tablas_cinta + bloques_cinta
            for e in choices:
                if current_h + e + kc_cinta + min(bloques_cinta) <= h_cant + 0.50:
                    seq.append(e)
                    search_p2(seq, current_h + e + kc_cinta)
                    seq.pop()

        search_p2([], 0.0)

        for p2_seq in p2_candidates:
            if not p2_seq or p2_seq[-1] not in bloques_cinta: continue

            piezas_cinta = []
            cotas_fase1 = []

            # FASE 1: Sierra Cinta
            y_curr_ef = d_efectivo
            z_curr_bancada = z_top_ef
            for t in p1_seq:
                y_bot_ef = y_curr_ef - t
                z_cut_bancada = z_curr_bancada - t
                w_min = min_ancho_pieza(y_curr_ef, y_bot_ef)
                piezas_cinta.append({"origen": "Fase 1", "espesor": t, "w_min": w_min, "cota_z": round(z_cut_bancada, 2)})
                cotas_fase1.append({"espesor": t, "cota_z": round(z_cut_bancada, 2), "tipo": "Bloque" if t > 2.01 else "Tabla"})
                y_curr_ef = y_bot_ef - kc_cinta
                z_curr_bancada = z_cut_bancada - kc_cinta

            # FASE 2: Cantón Volteado
            cotas_fase2 = []
            z_acc = 0.0
            for idx_rev, t in enumerate(reversed(p2_seq)):
                z_bot = z_acc
                z_top = z_acc + t
                y_orig_top = h_cant - z_bot
                y_orig_bot = max(0.0, h_cant - z_top)
                w_min = min_ancho_pieza(y_orig_top, y_orig_bot)
                piezas_cinta.append({"origen": "Fase 2", "espesor": t, "w_min": w_min, "cota_z": round(z_bot, 2)})

                is_base = (idx_rev == 0)
                cotas_fase2.append({
                    "espesor": t, "z_bot": round(z_bot, 2), "z_top": round(z_top, 2),
                    "cota_z_corte": round(z_bot, 2),
                    "tipo": "Bloque Base (Z=0)" if is_base else ("Bloque" if t > 2.01 else "Tabla")
                })
                z_acc = z_top + kc_cinta

            cotas_fase2 = list(reversed(cotas_fase2))

            # FASE 3: SIERRA MÚLTIPLE (Canteado y Re-aserrado)
            cnt_2x7, cnt_2x9 = 0, 0
            cnt_4x7, cnt_4x9 = 0, 0
            detalles_fase3 = []

            for p in piezas_cinta:
                t = p["espesor"]
                w_min = p["w_min"]

                if abs(t - 2.0) < 0.1:
                    n7, n9, w_used = calc_edging(w_min)
                    cnt_2x7 += n7
                    cnt_2x9 += n9
                    detalles_fase3.append({
                        "Origen": p["origen"], "Espesor Primario": f"{t:.1f} cm", "Ancho Útil Garantizado": f"{w_min:.1f} cm",
                        "Procesamiento Múltiple": "Canteado a 7 y 9 cm",
                        "Piezas Finales Resultantes": f"{n7} pzs (2x7) + {n9} pzs (2x9)"
                    })
                elif abs(t - 4.0) < 0.1:
                    n7, n9, w_used = calc_edging(w_min)
                    cnt_4x7 += n7
                    cnt_4x9 += n9
                    detalles_fase3.append({
                        "Origen": p["origen"], "Espesor Primario": f"{t:.1f} cm", "Ancho Útil Garantizado": f"{w_min:.1f} cm",
                        "Procesamiento Múltiple": "Canteado a 7 y 9 cm",
                        "Piezas Finales Resultantes": f"{n7} pzs (4x7) + {n9} pzs (4x9)"
                    })
                elif t >= 6.0:
                    # Bloque >= 7 cm (o >= 6cm): Dividir en capas de 2 cm
                    n_capas = int((t + kc_multi) // (2.0 + kc_multi))
                    n7, n9, w_used = calc_edging(w_min)
                    cnt_2x7 += n_capas * n7
                    cnt_2x9 += n_capas * n9
                    detalles_fase3.append({
                        "Origen": p["origen"], "Espesor Primario": f"Bloque {t:.1f} cm", "Ancho Útil Garantizado": f"{w_min:.1f} cm",
                        "Procesamiento Múltiple": f"Re-aserrado a {n_capas} capas de 2cm + Canteado",
                        "Piezas Finales Resultantes": f"{n_capas*n7} pzs (2x7) + {n_capas*n9} pzs (2x9)"
                    })

            # Volúmenes en m3 por tipo de pieza
            vol_2x7_m3 = (cnt_2x7 * (2.0 * 7.0 * largo)) / 1e6
            vol_2x9_m3 = (cnt_2x9 * (2.0 * 9.0 * largo)) / 1e6
            vol_4x7_m3 = (cnt_4x7 * (4.0 * 7.0 * largo)) / 1e6
            vol_4x9_m3 = (cnt_4x9 * (4.0 * 9.0 * largo)) / 1e6

            total_piezas_comerciales = cnt_2x7 + cnt_2x9 + cnt_4x7 + cnt_4x9
            vol_saliente_m3 = vol_2x7_m3 + vol_2x9_m3 + vol_4x7_m3 + vol_4x9_m3
            vol_desperdicio_m3 = max(0.0, vol_bruto_m3 - vol_saliente_m3)
            rendimiento_pct = (vol_saliente_m3 / vol_bruto_m3) * 100.0

            score = (rendimiento_pct * 100.0) + (total_piezas_comerciales * 5.0)

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
                    "cnt_2x7": cnt_2x7, "cnt_2x9": cnt_2x9,
                    "cnt_4x7": cnt_4x7, "cnt_4x9": cnt_4x9,
                    "vol_2x7_m3": vol_2x7_m3, "vol_2x9_m3": vol_2x9_m3,
                    "vol_4x7_m3": vol_4x7_m3, "vol_4x9_m3": vol_4x9_m3,
                    "total_piezas": total_piezas_comerciales,
                    "detalles_fase3": detalles_fase3,
                    "d_efectivo": d_efectivo,
                    "kc_cinta": kc_cinta, "kc_multi": kc_multi,
                    "z_top_ef": z_top_ef
                }

    return best_sol

# --- GENERADOR DE GRÁFICOS SIERRA CINTA (FASES 1 Y 2) ---
def generar_grafico_cortes(sol, d_menor):
    d_efectivo = sol["d_efectivo"]
    h_cant = sol["h_cant"]
    kc = sol["kc_cinta"]
    R = d_menor / 2.0
    R_ef = d_efectivo / 2.0

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6.0))
    y_base_ef = (d_menor - d_efectivo) / 2.0
    y_center_ef = y_base_ef + R_ef
    y_top_ef = sol["z_top_ef"]

    def agregar_cotas_10cm(ax):
        ax.axvline(-10, color='#333333', linestyle='--', linewidth=1.0, alpha=0.7)
        ax.axvline(10, color='#333333', linestyle='--', linewidth=1.0, alpha=0.7)
        ax.text(-10, -1.2, "-10 cm", fontsize=7.5, color='#333333', ha='center')
        ax.text(10, -1.2, "+10 cm", fontsize=7.5, color='#333333', ha='center')

    # FASE 1
    ax1.set_title("FASE 1: Sierra Cinta - Tronco Entero en Bancada", fontsize=11, fontweight='bold')
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
        ax1.axhline(y_next, color='#D32F2F', linestyle=':', linewidth=1.2)
        ax1.text(R*1.04, y_next + 0.35, f"Corte #{idx+1}: Z = {y_next:.2f} cm", fontsize=8.0, fontweight='bold', color='#D32F2F', va='bottom')
        y_curr = y_next - kc

    y_cut_line = y_curr + kc
    ax1.axhline(y_cut_line, color='purple', linestyle='--', linewidth=2.0)
    ax1.text(0, y_cut_line - 1.5, f"VOLTEAR 180° (Cantón h={h_cant:.1f} cm)", color='purple', fontweight='bold', fontsize=8.5, ha='center', bbox=dict(boxstyle='round,pad=0.2', facecolor='yellow', alpha=0.9))
    ax1.set_xlim(-R*1.7, R*1.85)
    ax1.set_ylim(-3.5, d_menor + 3.5)
    ax1.set_ylabel("Altura Z sobre Bancada (cm)")
    ax1.grid(True, linestyle=':', alpha=0.4)

    # FASE 2
    ax2.set_title("FASE 2: Sierra Cinta - Cantón Volteado 180°", fontsize=11, fontweight='bold')
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
        color = '#2E7D32' if is_last else ('#0D47A1' if t > 2.01 else '#FB8C00')

        ax2.add_patch(patches.Rectangle((-w/2.0, z_bot), w, t, edgecolor='black', facecolor=color, alpha=0.9))
        tag = f"BLOQUE BASE {t:.1f} cm (Z=0.00)" if is_last else f"{'Bloque' if t > 2.01 else 'Tabla'} {t:.1f} cm"
        ax2.text(0, z_mid, tag, color='white', fontweight='bold', fontsize=8.5, ha='center', va='center')

        if z_bot > 0.001:
            corte_count_fase2 += 1
            ax2.axhline(z_bot, color='#D32F2F', linestyle=':', linewidth=1.2)
            ax2.text(R*1.04, z_bot + 0.35, f"Corte #{corte_count_fase2}: Z = {z_bot:.2f} cm", fontsize=8.0, fontweight='bold', color='#D32F2F', va='bottom')

    ax2.set_xlim(-R*1.7, R*1.85)
    ax2.set_ylim(-3.5, d_menor + 3.5)
    ax2.set_ylabel("Altura Z sobre Bancada (cm)")
    ax2.grid(True, linestyle=':', alpha=0.4)

    plt.tight_layout()
    return fig

# --- EJECUCIÓN PRINCIPAL ---
sol = optimizar_aserrado_completo(d_menor, d_mayor, largo, curvatura, kerf_cinta_mm, kerf_multi_mm)

if sol:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Volumen Cónico Entrada (Smalian)", f"{sol['vol_bruto_m3']:.3f} m³")
    m2.metric("Volumen Saliente Comercial Final", f"{sol['vol_saliente_m3']:.3f} m³")
    m3.metric("Total Piezas Comerciales", f"{sol['total_piezas']} pzs")
    m4.metric("Rendimiento Comercial Real", f"{sol['rendimiento_pct']:.1f} %")

    st.markdown("---")
    st.subheader("📐 Diagrama de Aserrado en Sierra Cinta (Fases 1 y 2)")
    st.pyplot(generar_grafico_cortes(sol, d_menor))

    # --- PLAN DE CORTE EN SIERRA CINTA ---
    st.markdown("### 📋 Plan de Corte 1 y 2: Sierra Cinta")
    col_p1, col_p2 = st.columns(2)

    with col_p1:
        st.markdown("**FASE 1: Cortes Tronco Entero**")
        plan_f1_data = [
            {"N° Corte": f"Corte #{idx+1}", "Cota de Sierra (Z)": f"{item['cota_z']:.2f} cm", "Pieza Extraída": f"{item['tipo']} de {item['espesor']:.1f} cm"}
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
                plan_f2_data.append({"N° Corte": f"Corte #{c_num}", "Cota de Sierra (Z)": f"{item['cota_z_corte']:.2f} cm", "Pieza Extraída": f"{item['tipo']} de {item['espesor']:.1f} cm"})
            else:
                plan_f2_data.append({"N° Corte": "Base (Sin Corte)", "Cota de Sierra (Z)": "0.00 cm", "Pieza Extraída": f"Bloque Base de {item['espesor']:.1f} cm"})
        st.table(pd.DataFrame(plan_f2_data))

    # --- FASE 3: SIERRA MÚLTIPLE ---
    st.markdown("---")
    st.markdown("### ⚡ FASE 3: Programación de Sierra Múltiple / Canteadora")
    st.markdown(
        f"Procesamiento de piezas primarias con sierra circular (Kerf = {kerf_multi_mm:.1f} mm). "
        "Las piezas de 2cm y 4cm se cantean a anchos de 7cm o 9cm. Los bloques $\\ge 7\\text{ cm}$ se re-asierran en tablas de 2cm."
    )
    st.table(pd.DataFrame(sol["detalles_fase3"]))

    # --- RESUMEN DE PRODUCCIÓN (ENTRANTE VS SALIENTE EN PIEZAS) ---
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
        st.markdown("#### 📤 Madera Saliente en Piezas Comerciales Completas")
        df_saliente = pd.DataFrame([
            {"Dimensiones (Espesor x Ancho x Largo)": f"2 cm x 7 cm x {largo:.0f} cm", "Piezas Resultantes": f"{sol['cnt_2x7']} pzs", "Volumen (m³)": round(sol['vol_2x7_m3'], 4), "% del Tronco": round((sol['vol_2x7_m3']/sol['vol_bruto_m3'])*100, 2)},
            {"Dimensiones (Espesor x Ancho x Largo)": f"2 cm x 9 cm x {largo:.0f} cm", "Piezas Resultantes": f"{sol['cnt_2x9']} pzs", "Volumen (m³)": round(sol['vol_2x9_m3'], 4), "% del Tronco": round((sol['vol_2x9_m3']/sol['vol_bruto_m3'])*100, 2)},
            {"Dimensiones (Espesor x Ancho x Largo)": f"4 cm x 7 cm x {largo:.0f} cm", "Piezas Resultantes": f"{sol['cnt_4x7']} pzs", "Volumen (m³)": round(sol['vol_4x7_m3'], 4), "% del Tronco": round((sol['vol_4x7_m3']/sol['vol_bruto_m3'])*100, 2)},
            {"Dimensiones (Espesor x Ancho x Largo)": f"4 cm x 9 cm x {largo:.0f} cm", "Piezas Resultantes": f"{sol['cnt_4x9']} pzs", "Volumen (m³)": round(sol['vol_4x9_m3'], 4), "% del Tronco": round((sol['vol_4x9_m3']/sol['vol_bruto_m3'])*100, 2)},
            {"Dimensiones (Espesor x Ancho x Largo)": "TOTAL MADERA SALIENTE ÚTIL", "Piezas Resultantes": f"{sol['total_piezas']} pzs", "Volumen (m³)": round(sol['vol_saliente_m3'], 4), "% del Tronco": round(sol['rendimiento_pct'], 2)},
            {"Dimensiones (Espesor x Ancho x Largo)": "Viruta + Costeros / Desperdicio Total", "Piezas Resultantes": "-", "Volumen (m³)": round(sol['vol_desperdicio_m3'], 4), "% del Tronco": round(100.0 - sol['rendimiento_pct'], 2)}
        ])
        st.table(df_saliente)

    col_btn, _ = st.columns([4, 6])
    with col_btn:
        if st.button("📌 Registrar Tronco Procesado en Reporte Diario", type="primary", use_container_width=True):
            st.session_state.historial.append({
                "ID": len(st.session_state.historial) + 1,
                "D.Menor (cm)": d_menor,
                "D.Mayor (cm)": d_mayor,
                "Largo (cm)": largo,
                "m³ Entrada": round(sol["vol_bruto_m3"], 4),
                "Pzs 2x7": sol["cnt_2x7"],
                "Pzs 2x9": sol["cnt_2x9"],
                "Pzs 4x7": sol["cnt_4x7"],
                "Pzs 4x9": sol["cnt_4x9"],
                "Total Pzs": sol["total_piezas"],
                "m³ Saliente Útil": round(sol["vol_saliente_m3"], 4),
                "m³ Desperdicio": round(sol["vol_desperdicio_m3"], 4),
                "Rendimiento (%)": round(sol["rendimiento_pct"], 2)
            })
            st.success("¡Tronco agregado al registro acumulado de producción!")

# --- REPORTE DE PRODUCCIÓN ACUMULADO CON EXCEL ---
st.markdown("---")
st.markdown("## 📊 Reporte Acumulado Diario de Producción")

if st.session_state.historial:
    df_hist = pd.DataFrame(st.session_state.historial)

    tot_bruto = df_hist["m³ Entrada"].sum()
    tot_util = df_hist["m³ Saliente Útil"].sum()
    tot_desp = df_hist["m³ Desperdicio"].sum()
    tot_pzs_2x7 = df_hist["Pzs 2x7"].sum()
    tot_pzs_2x9 = df_hist["Pzs 2x9"].sum()
    tot_pzs_4x7 = df_hist["Pzs 4x7"].sum()
    tot_pzs_4x9 = df_hist["Pzs 4x9"].sum()
    tot_pzs_gen = df_hist["Total Pzs"].sum()
    prom_rend = (tot_util / tot_bruto * 100.0) if tot_bruto > 0 else 0.0

    st1, st2, st3, st4, st5 = st.columns(5)
    st1.metric("Total m³ Entrada", f"{tot_bruto:.3f} m³")
    st2.metric("Total m³ Útil Saliente", f"{tot_util:.3f} m³")
    st3.metric("Total Piezas Producidas", f"{tot_pzs_gen} pzs")
    st4.metric("Total m³ Desperdicio", f"{tot_desp:.3f} m³")
    st5.metric("Rendimiento Global", f"{prom_rend:.1f} %")

    # Fila de TOTAL para exportación
    row_total = {
        "ID": "TOTAL",
        "D.Menor (cm)": "-", "D.Mayor (cm)": "-", "Largo (cm)": "-",
        "m³ Entrada": round(tot_bruto, 4),
        "Pzs 2x7": tot_pzs_2x7, "Pzs 2x9": tot_pzs_2x9,
        "Pzs 4x7": tot_pzs_4x7, "Pzs 4x9": tot_pzs_4x9,
        "Total Pzs": tot_pzs_gen,
        "m³ Saliente Útil": round(tot_util, 4),
        "m³ Desperdicio": round(tot_desp, 4),
        "Rendimiento (%)": round(prom_rend, 2)
    }

    df_export = pd.concat([df_hist, pd.DataFrame([row_total])], ignore_index=True)
    st.dataframe(df_export, use_container_width=True)

    # Generación de Excel en memoria
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_export.to_excel(writer, index=False, sheet_name='Reporte_Produccion_Multiples')

    st.download_button(
        label="📥 Descargar Reporte de Producción Completo (.xlsx)",
        data=output.getvalue(),
        file_name="reporte_aserradero_sierra_multiple.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary"
    )
else:
    st.info("Haz clic en '📌 Registrar Tronco Procesado en Reporte Diario' para acumular la producción de troncos del día.")
