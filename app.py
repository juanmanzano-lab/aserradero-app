import math
import io
import requests
from datetime import datetime
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import streamlit as st

st.set_page_config(page_title="Optimización de Aserradero", layout="wide")

st.title("🪓 Optimización y Registro de Aserrado de Troncos")
st.markdown("Sistema con cálculo de **canto vivo 100% rectangular**, plan de corte y almacenamiento.")

# --- INICIALIZACIÓN DE HISTORIAL EN MEMORIA LOCAL ---
if "historial" not in st.session_state:
    st.session_state.historial = []

# Obtención de la URL de Google Apps Script desde Secrets
WEBAPP_URL = st.secrets.get("GOOGLE_SHEET_WEBAPP_URL", "")


# =========================================================
# 1. PARÁMETROS DE ENTRADA (EN LA PARTE SUPERIOR)
# =========================================================
st.header("📐 Dimensiones del Tronco")
col1, col2, col3, col4 = st.columns(4)

with col1:
    d_menor = st.number_input("Diámetro Menor (cm)", min_value=10.0, max_value=100.0, value=32.0, step=0.5)
with col2:
    d_mayor = st.number_input("Diámetro Mayor (cm)", min_value=10.0, max_value=120.0, value=38.0, step=0.5)
with col3:
    largo = st.number_input("Largo del Tronco (cm)", min_value=50.0, max_value=1000.0, value=250.0, step=10.0)
with col4:
    kerf_mm = st.number_input("Kerf de Sierra (mm)", min_value=1.0, max_value=10.0, value=2.5, step=0.1)

if d_mayor < d_menor:
    st.warning("⚠️ El diámetro mayor debe ser mayor o igual al menor. Se ajustará al valor menor.")
    d_mayor = d_menor


# =========================================================
# 2. ALGORITMO DE CÁLCULO RECTANGULAR ESTRICTO (CANTO VIVO)
# =========================================================
def calcular_ancho_rectangular_recto(y_top, y_bot, R_ef):
    """Calcula el ancho máximo de un rectángulo con 4 esquinas dentro de la circunferencia."""
    dy_top = abs(y_top - R_ef)
    dy_bot = abs(y_bot - R_ef)
    dy_max = max(dy_top, dy_bot)
    if dy_max >= R_ef:
        return 0.0
    return 2.0 * math.sqrt(R_ef**2 - dy_max**2)

def optimizar_aserrado(d_menor, d_mayor, largo, kerf_mm, dimensiones_prio):
    # Ya no hay curvatura, el D_efectivo es el D_menor
    d_efectivo = d_menor
    R_ef = d_efectivo / 2.0
    kc = kerf_mm / 10.0  # Pasar a cm

    # Volumen Bruto Cónico Real (Smalian)
    r_menor_m = (d_menor / 2.0) / 100.0
    r_mayor_m = (d_mayor / 2.0) / 100.0
    largo_m = largo / 100.0
    vol_bruto_m3 = (math.pi * largo_m / 3.0) * (r_menor_m**2 + r_mayor_m**2 + (r_menor_m * r_mayor_m))

    prio_map = {item["espesor"]: item["prioridad"] for item in dimensiones_prio if item["espesor"] > 0}
    if not prio_map:
        return None # Si no hay medidas, no calcula

    E_list = sorted(list(prio_map.keys()))
    tablas = [e for e in E_list if e <= 2.01]
    bloques = [e for e in E_list if e > 2.01]

    if not bloques: bloques = [max(E_list)]
    if not tablas: tablas = [min(E_list)]

    best_sol = None
    best_score = -1e9

    for h_destape in [0.5, 1.0, 1.5, 2.0, 2.5]:
        z_top_ef = d_efectivo - h_destape

        min_hp1 = 0.20 * d_efectivo
        max_hp1 = 0.55 * d_efectivo
        p1_candidates = []
        steps_p1 = [0]

        def search_p1(seq, current_h):
            steps_p1[0] += 1
            if steps_p1[0] > 1000 or len(p1_candidates) >= 40: return
            if min_hp1 <= current_h <= max_hp1: p1_candidates.append((list(seq), current_h))
            if current_h > max_hp1: return

            choices = tablas if len(seq) == 0 else (tablas + bloques)
            for e in choices:
                if current_h + e <= max_hp1 + 1.0:
                    seq.append(e)
                    search_p1(seq, current_h + e + kc)
                    seq.pop()

        search_p1([], 0.0)

        for p1_seq, h_p1 in p1_candidates[:25]:
            h_cant = (d_efectivo - h_destape) - h_p1
            if h_cant < min(bloques): continue

            p2_candidates = []
            steps_p2 = [0]

            def search_p2(seq, current_h):
                steps_p2[0] += 1
                if steps_p2[0] > 1000 or len(p2_candidates) >= 20: return
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

                vol_bloques, vol_tablas = 0.0, 0.0
                vol_rect_total = 0.0
                y_curr_ef = d_efectivo - h_destape
                z_curr_bancada = z_top_ef
                cotas_fase1 = []

                for t in p1_seq:
                    y_bot_ef = y_curr_ef - t
                    z_cut_bancada = z_curr_bancada - t
                    
                    w_rect = calcular_ancho_rectangular_recto(y_curr_ef, y_bot_ef, R_ef)
                    area_rect = w_rect * t
                    v_p = (area_rect * largo) / 1e6

                    vol_rect_total += v_p
                    if t > 2.01: vol_bloques += v_p
                    else: vol_tablas += v_p

                    cotas_fase1.append({
                        "espesor": t,
                        "ancho_rect": round(w_rect, 2),
                        "cota_z": round(z_cut_bancada, 2),
                        "tipo": "Bloque" if t > 2.01 else "Tabla"
                    })

                    y_curr_ef = y_bot_ef - kc
                    z_curr_bancada = z_cut_bancada - kc

                fase2_items = []
                z_acc = 0.0

                for idx_rev, t in enumerate(reversed(p2_seq)):
                    z_bot = z_acc
                    z_top = z_acc + t
                    is_base = (idx_rev == 0)

                    y_orig_top = h_cant - z_bot
                    y_orig_bot = max(0.0, h_cant - z_top)

                    w_rect = calcular_ancho_rectangular_recto(y_orig_top, y_orig_bot, R_ef)
                    area_rect = w_rect * t
                    v_p = (area_rect * largo) / 1e6

                    vol_rect_total += v_p
                    if t > 2.01: vol_bloques += v_p
                    else: vol_tablas += v_p

                    fase2_items.append({
                        "espesor": t,
                        "ancho_rect": round(w_rect, 2),
                        "z_bot": round(z_bot, 2),
                        "z_top": round(z_top, 2),
                        "cota_z_corte": round(z_bot, 2),
                        "tipo": "Bloque Base (Z=0)" if is_base else ("Bloque" if t > 2.01 else "Tabla")
                    })
                    z_acc = z_top + kc

                cotas_fase2 = list(reversed(fase2_items))
                h_cant_real = round(z_acc - kc, 2)

                n_cortes = len(p1_seq) + len(p2_seq) - 1
                vol_kerf_m3 = (n_cortes * (kc / 100.0) * (R_ef / 100.0 * 2) * largo_m)
                vol_desperdicio_m3 = max(0.0, vol_bruto_m3 - vol_rect_total - vol_kerf_m3)
                rendimiento_pct = (vol_rect_total / vol_bruto_m3) * 100.0

                prio_score = sum((6 - prio_map.get(p, 5)) * 25.0 * (p**1.3) for p in (p1_seq + p2_seq))
                score = (rendimiento_pct * 60.0) + prio_score

                if score > best_score:
                    best_score = score
                    best_sol = {
                        "p1_seq": p1_seq, "p2_seq": p2_seq,
                        "cotas_fase1": cotas_fase1, "cotas_fase2": cotas_fase2,
                        "h_cant": h_cant_real, "vol_m3": vol_rect_total,
                        "vol_bruto_m3": vol_bruto_m3, "vol_bloques_m3": vol_bloques,
                        "vol_tablas_m3": vol_tablas, "vol_kerf_m3": vol_kerf_m3,
                        "vol_desperdicio_m3": vol_desperdicio_m3,
                        "aprovechamiento_pct": rendimiento_pct,
                        "d_efectivo": d_efectivo, "kc": kc, "z_top_ef": z_top_ef
                    }

    return best_sol

# =========================================================
# 3. GRAFICADOR
# =========================================================
def generar_grafico_cortes(sol, d_menor):
    d_efectivo = sol["d_efectivo"]
    h_cant = sol["h_cant"]
    kc = sol["kc"]
    R = d_menor / 2.0
    R_ef = d_efectivo / 2.0

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6.5))
    y_top_ef = sol["z_top_ef"]

    def agregar_referencia_ancho(ax):
        ax.axvline(-10, color='#666666', linestyle='--', linewidth=0.8, alpha=0.6)
        ax.axvline(10, color='#666666', linestyle='--', linewidth=0.8, alpha=0.6)
        ax.text(-10, -1.2, "-10 cm", fontsize=7.5, color='#555555', ha='center')
        ax.text(10, -1.2, "+10 cm", fontsize=7.5, color='#555555', ha='center')

    # FASE 1
    ax1.set_title("FASE 1: Tronco Entero y Piezas Útiles de Canto Vivo", fontsize=10, fontweight='bold')
    ax1.set_aspect('equal')
    ax1.plot([-R*1.5, R*1.5], [0, 0], color='black', linewidth=3)
    ax1.text(0, -1.8, "BANCADA (Z = 0.0 cm)", color='darkgreen', fontweight='bold', fontsize=8.5, ha='center')
    agregar_referencia_ancho(ax1)

    # Circunferencia del tronco (Al no haber curvatura, D_menor = D_efectivo)
    ax1.add_patch(patches.Circle((0, R), R, edgecolor='#2E7D32', facecolor='#D2B48C', alpha=0.25, linestyle='-', linewidth=1.5, label=f'D_menor ({d_menor} cm)'))

    for idx, item in enumerate(sol["cotas_fase1"]):
        t = item["espesor"]
        w = item["ancho_rect"]
        z_cut = item["cota_z"]
        color = '#1E88E5' if t > 2.01 else '#FFB300'

        if w > 0:
            ax1.add_patch(patches.Rectangle((-w/2.0, z_cut), w, t, edgecolor='black', facecolor=color, alpha=0.85))
            ax1.text(0, z_cut + t/2.0, f"{item['tipo']} {t:.1f} x {w:.1f} cm", color='white' if t > 2.01 else 'black', fontweight='bold', fontsize=8.0, ha='center', va='center')
        
        ax1.axhline(z_cut, color='#D32F2F', linestyle=':', linewidth=1.2)
        ax1.text(R*1.04, z_cut + 0.2, f"Corte #{idx+1}: Z={z_cut:.2f} cm", fontsize=8.0, fontweight='bold', color='#D32F2F', va='bottom')

    ax1.set_xlim(-R*1.7, R*1.85)
    ax1.set_ylim(-3.0, d_menor + 3.0)
    ax1.set_ylabel("Altura Z sobre Bancada (cm)")
    ax1.grid(True, linestyle=':', alpha=0.4)
    ax1.legend(loc='upper right', fontsize=8)

    # FASE 2
    ax2.set_title("FASE 2: Cantón Volteado 180°", fontsize=10, fontweight='bold')
    ax2.set_aspect('equal')
    ax2.plot([-R*1.5, R*1.5], [0, 0], color='black', linewidth=3)
    ax2.text(0, -1.8, "COTA 0.00 CM: Asiento Plano", color='darkgreen', fontweight='bold', fontsize=8.5, ha='center')
    agregar_referencia_ancho(ax2)

    # Restauración del círculo en la Fase 2, ajustado visualmente al cantón
    centro_y_fase2 = h_cant - R_ef
    ax2.add_patch(patches.Circle((0, centro_y_fase2), R_ef, edgecolor='#2E7D32', facecolor='none', linewidth=1.5, linestyle='--', label=f'Circunferencia'))

    corte_count = len(sol["cotas_fase1"])
    for idx, item in enumerate(sol["cotas_fase2"]):
        t = item["espesor"]
        w = item["ancho_rect"]
        z_bot = item["z_bot"]
        is_last = (idx == len(sol["cotas_fase2"]) - 1)
        color = '#2E7D32' if is_last else ('#0D47A1' if t > 2.01 else '#FB8C00')

        if w > 0:
            ax2.add_patch(patches.Rectangle((-w/2.0, z_bot), w, t, edgecolor='black', facecolor=color, alpha=0.85))
            tag = f"BASE {t:.1f} x {w:.1f} cm" if is_last else f"{item['tipo']} {t:.1f} x {w:.1f} cm"
            ax2.text(0, z_bot + t/2.0, tag, color='white', fontweight='bold', fontsize=8.0, ha='center', va='center')

        if z_bot > 0.001:
            corte_count += 1
            ax2.axhline(z_bot, color='#D32F2F', linestyle=':', linewidth=1.2)
            ax2.text(R*1.04, z_bot + 0.2, f"Corte #{corte_count}: Z={z_bot:.2f} cm", fontsize=8.0, fontweight='bold', color='#D32F2F', va='bottom')

    ax2.set_xlim(-R*1.7, R*1.85)
    ax2.set_ylim(-3.0, d_menor + 3.0)
    ax2.set_ylabel("Altura Z sobre Bancada (cm)")
    ax2.grid(True, linestyle=':', alpha=0.4)

    plt.tight_layout()
    return fig

st.markdown("---")


# =========================================================
# 4. MEDIDAS Y PRIORIDADES (EN LA PARTE INFERIOR)
# =========================================================
st.header("⚙️ Medidas Solicitadas y Prioridades")
st.markdown("💡 **Instrucción:** Debes ingresar al menos una medida mayor a 0 para que se generen los gráficos de corte.")

default_dims = [
    {"espesor": 0.0, "prio": 1},
    {"espesor": 0.0, "prio": 2},
    {"espesor": 0.0, "prio": 3},
    {"espesor": 0.0, "prio": 4},
    {"espesor": 0.0, "prio": 5},
]

inputs_espesores = []
cols = st.columns(5)

for i, df_val in enumerate(default_dims):
    with cols[i]:
        e = st.number_input(f"Medida {i+1} (cm)", min_value=0.0, max_value=30.0, value=df_val["espesor"], step=0.5, key=f"e_{i}")
        p = st.selectbox(f"Prioridad {i+1}", options=[1, 2, 3, 4, 5], index=df_val["prio"]-1, key=f"p_{i}")
        
        # Solo se toman en cuenta si son mayores a 0
        if e > 0:
            inputs_espesores.append({"espesor": float(e), "prioridad": int(p)})


# =========================================================
# 5. RENDERIZADO CONDICIONAL DE RESULTADOS Y TABLAS
# =========================================================
if len(inputs_espesores) > 0:
    sol = optimizar_aserrado(d_menor, d_mayor, largo, kerf_mm, inputs_espesores)

    if sol:
        st.markdown("---")
        st.pyplot(generar_grafico_cortes(sol, d_menor))
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Volumen Entrada (Smalian)", f"{sol['vol_bruto_m3']:.3f} m³")
        m2.metric("Maderable Canto Vivo", f"{sol['vol_m3']:.3f} m³")
        m3.metric("Rendimiento (Aprovechamiento)", f"{sol['aprovechamiento_pct']:.1f} %")
        m4.metric("Diámetro Base Usado", f"{sol['d_efectivo']:.1f} cm")

        # PLAN DE CORTE Y MEDIDAS RECTANGULARES
        st.markdown("### 📋 Plan de Corte con Anchos Rectangulares Útiles")
        col_p1, col_p2 = st.columns(2)

        with col_p1:
            st.markdown("**FASE 1: Cortes Tronco Entero**")
            plan_f1 = []
            for idx, item in enumerate(sol["cotas_fase1"]):
                plan_f1.append({
                    "N° Corte": f"Corte #{idx+1}",
                    "Cota Z (Sierra)": f"{item['cota_z']:.2f} cm",
                    "Pieza Extraída": f"{item['tipo']} {item['espesor']:.1f} cm",
                    "Ancho Útil": f"{item['ancho_rect']:.1f} cm"
                })
            st.table(pd.DataFrame(plan_f1))

        with col_p2:
            st.markdown("**FASE 2: Cortes Cantón Volteado (Z=0.00 cm)**")
            plan_f2 = []
            c_num = len(sol["cotas_fase1"])
            for idx, item in enumerate(sol["cotas_fase2"]):
                if item["z_bot"] > 0.001:
                    c_num += 1
                    plan_f2.append({
                        "N° Corte": f"Corte #{c_num}",
                        "Cota Z (Sierra)": f"{item['cota_z_corte']:.2f} cm",
                        "Pieza Extraída": f"{item['tipo']} {item['espesor']:.1f} cm",
                        "Ancho Útil": f"{item['ancho_rect']:.1f} cm"
                    })
                else:
                    plan_f2.append({
                        "N° Corte": "Base (Apoyo)",
                        "Cota Z (Sierra)": "0.00 cm",
                        "Pieza Extraída": f"Bloque Base {item['espesor']:.1f} cm",
                        "Ancho Útil": f"{item['ancho_rect']:.1f} cm"
                    })
            st.table(pd.DataFrame(plan_f2))

        # BOTÓN DE REGISTRO DUAL
        st.markdown("---")
        col_btn, _ = st.columns([4, 6])
        with col_btn:
            if st.button("📌 Registrar Tronco Procesado en Reporte Diario", type="primary", use_container_width=True):
                nuevo_registro = {
                    "ID": len(st.session_state.historial) + 1,
                    "Fecha_Hora": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "D.Menor (cm)": d_menor,
                    "D.Mayor (cm)": d_mayor,
                    "Largo (cm)": largo,
                    "m³ Entrada": round(sol["vol_bruto_m3"], 4),
                    "m³ Útil (Rectangular)": round(sol["vol_m3"], 4),
                    "m³ Bloques": round(sol["vol_bloques_m3"], 4),
                    "m³ Tablas": round(sol["vol_tablas_m3"], 4),
                    "m³ Kerf": round(sol["vol_kerf_m3"], 4),
                    "Rendimiento (%)": round(sol["aprovechamiento_pct"], 2),
                    "Bloque Base Z=0 (cm)": sol["p2_seq"][-1]
                }

                # 1. Registro en memoria local
                st.session_state.historial.append(nuevo_registro)
                st.success("✅ Tronco guardado en el reporte acumulado diario local.")

                # 2. Envío a Google Sheets (Si está configurado WEBAPP_URL)
                if WEBAPP_URL:
                    try:
                        res = requests.post(WEBAPP_URL, json=nuevo_registro, timeout=8)
                        if res.status_code == 200:
                            st.info("☁️ Registro respaldado con éxito en Google Sheets.")
                        elif res.status_code == 404:
                            st.error("⚠️ Error 404: La URL en Secrets no es correcta o le falta terminar en '/exec'.")
                        else:
                            st.warning(f"Guardado localmente. Código de error de Google: {res.status_code}")
                    except Exception as ex:
                        st.warning(f"Guardado localmente. No se pudo conectar a la web: {ex}")
                else:
                    st.caption("ℹ️ Nota: Configura GOOGLE_SHEET_WEBAPP_URL en Secrets para activar la subida a la nube.")
else:
    st.info("⚠️ Ingresa al menos una medida mayor a 0.0 cm en la sección de abajo para empezar.")


# =========================================================
# 6. REPORTE ACUMULADO Y DESCARGA
# =========================================================
if st.session_state.historial:
    st.markdown("---")
    st.markdown("## 📊 Reporte de Producción Acumulado Diario")
    
    df_hist = pd.DataFrame(st.session_state.historial)

    tot_bruto = df_hist["m³ Entrada"].sum()
    tot_util = df_hist["m³ Útil (Rectangular)"].sum()
    tot_bloques = df_hist["m³ Bloques"].sum()
    tot_tablas = df_hist["m³ Tablas"].sum()
    prom_rend = (tot_util / tot_bruto * 100.0) if tot_bruto > 0 else 0.0

    st1, st2, st3, st4, st5 = st.columns(5)
    st1.metric("Total m³ Entrada", f"{tot_bruto:.3f} m³")
    st2.metric("Total m³ Útil", f"{tot_util:.3f} m³")
    st3.metric("Total m³ Bloques", f"{tot_bloques:.3f} m³")
    st4.metric("Total m³ Tablas", f"{tot_tablas:.3f} m³")
    st5.metric("Rendimiento Global", f"{prom_rend:.1f} %")

    st.dataframe(df_hist, use_container_width=True)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_hist.to_excel(writer, index=False, sheet_name='Reporte_Produccion')

    st.download_button(
        label="📥 Descargar Reporte de Producción (.xlsx)",
        data=output.getvalue(),
        file_name="reporte_produccion_aserradero.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary"
    )
