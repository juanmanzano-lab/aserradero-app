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

# --- INICIALIZACIÓN DE ESTADOS EN SESSION STATE ---
if "historial" not in st.session_state:
    st.session_state.historial = []
if "jornada_iniciada" not in st.session_state:
    st.session_state.jornada_iniciada = False
if "jornada_finalizada" not in st.session_state:
    st.session_state.jornada_finalizada = False
if "datos_jornada" not in st.session_state:
    st.session_state.datos_jornada = {}

# Lectura segura de Secrets
url_secret = ""
try:
    url_secret = st.secrets.get("GOOGLE_SHEET_WEBAPP_URL", "")
except Exception:
    url_secret = ""


# =========================================================
# MENÚ LATERAL: CONTROL DE JORNADA
# =========================================================
st.sidebar.title("📋 Control de Jornada")

if not st.session_state.jornada_iniciada and not st.session_state.jornada_finalizada:
    st.sidebar.subheader("Parámetros Generales")
    fecha_jornada = st.sidebar.date_input("Fecha", datetime.now())
    turno = st.sidebar.selectbox("Turno de Trabajo", ["Diurno", "Nocturno"])
    kerf_mm = st.sidebar.number_input("Kerf de Sierra (mm)", min_value=1.0, max_value=10.0, value=2.5, step=0.1)

    st.sidebar.markdown("---")
    st.sidebar.subheader("☁️ Conexión a Google Drive")
    webapp_url_input = st.sidebar.text_input(
        "URL de Google Apps Script",
        value=url_secret,
        placeholder="https://script.google.com/macros/s/.../exec",
        help="Pega aquí la URL WebApp de Google Apps Script."
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("🪓 Equipo Aserradero Manual")
    op_m1 = st.sidebar.text_input("Operador 1 (Manual)", value="", key="op_m1")
    op_m2 = st.sidebar.text_input("Operador 2 (Manual)", value="", key="op_m2")
    op_m3 = st.sidebar.text_input("Operador 3 (Manual)", value="", key="op_m3")

    st.sidebar.markdown("---")
    st.sidebar.subheader("⚙️ Equipo Aserradero Hidráulico")
    op_h1 = st.sidebar.text_input("Operador 1 (Hidráulico)", value="", key="op_h1")
    op_h2 = st.sidebar.text_input("Operador 2 (Hidráulico)", value="", key="op_h2")
    op_h3 = st.sidebar.text_input("Operador 3 (Hidráulico)", value="", key="op_h3")

    st.sidebar.markdown("---")
    if st.sidebar.button("🚀 Iniciar Jornada", type="primary", use_container_width=True):
        if not (op_m1.strip() and op_m2.strip() and op_m3.strip() and op_h1.strip() and op_h2.strip() and op_h3.strip()):
            st.sidebar.error("⚠️ Debes registrar los 3 operadores de AMBOS equipos para iniciar la jornada.")
        else:
            st.session_state.datos_jornada = {
                "fecha": fecha_jornada.strftime("%Y-%m-%d"),
                "turno": turno,
                "kerf_mm": float(kerf_mm),
                "webapp_url": webapp_url_input.strip(),
                "equipo_manual": f"{op_m1.strip()}, {op_m2.strip()}, {op_m3.strip()}",
                "equipo_hidraulico": f"{op_h1.strip()}, {op_h2.strip()}, {op_h3.strip()}"
            }
            st.session_state.jornada_iniciada = True
            st.rerun()

elif st.session_state.jornada_iniciada and not st.session_state.jornada_finalizada:
    st.sidebar.success("🟢 **JORNADA EN CURSO**")
    dj = st.session_state.datos_jornada
    st.sidebar.markdown(f"**Fecha:** {dj['fecha']}")
    st.sidebar.markdown(f"**Turno:** {dj['turno']}")
    st.sidebar.markdown(f"**Kerf Configurado:** {dj['kerf_mm']} mm")
    if dj.get("webapp_url"):
        st.sidebar.markdown("☁️ **Google Drive:** Conectado")
    else:
        st.sidebar.markdown("⚠️ **Google Drive:** Sin URL")
    st.sidebar.markdown(f"**Equipo Manual:**\n{dj['equipo_manual']}")
    st.sidebar.markdown(f"**Equipo Hidráulico:**\n{dj['equipo_hidraulico']}")
    
    st.sidebar.markdown("---")
    if st.sidebar.button("🛑 Finalizar Jornada", type="secondary", use_container_width=True):
        st.session_state.jornada_finalizada = True
        st.session_state.jornada_iniciada = False
        st.rerun()

elif st.session_state.jornada_finalizada:
    st.sidebar.error("🔒 **JORNADA FINALIZADA**")
    dj = st.session_state.datos_jornada
    st.sidebar.markdown(f"**Fecha:** {dj['fecha']}")
    st.sidebar.markdown(f"**Turno:** {dj['turno']}")
    st.sidebar.markdown(f"**Kerf Configurado:** {dj['kerf_mm']} mm")
    st.sidebar.markdown(f"**Equipo Manual:**\n{dj['equipo_manual']}")
    st.sidebar.markdown(f"**Equipo Hidráulico:**\n{dj['equipo_hidraulico']}")
    
    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 Iniciar Nueva Jornada", type="primary", use_container_width=True):
        st.session_state.jornada_iniciada = False
        st.session_state.jornada_finalizada = False
        st.session_state.historial = []
        st.session_state.datos_jornada = {}
        st.rerun()


# =========================================================
# TÍTULO Y ESTADO DE APLICACIÓN
# =========================================================
st.title("🪓 Optimización y Registro de Aserrado de Troncos")

WEBAPP_URL = ""
if st.session_state.jornada_iniciada or st.session_state.jornada_finalizada:
    WEBAPP_URL = st.session_state.datos_jornada.get("webapp_url", "")
else:
    WEBAPP_URL = url_secret

if WEBAPP_URL:
    st.success("✅ Conexión con Google Drive lista.")
else:
    st.warning("⚠️ No se ha detectado la URL en Secrets. Puedes pegarla manualmente en el menú lateral.")

st.markdown("Sistema inteligente con cálculo de **canto vivo 100% rectangular**, plan de corte y almacenamiento en la nube.")

if st.session_state.jornada_finalizada:
    st.warning("🔒 **La jornada de trabajo ha sido finalizada.** El sistema se encuentra bloqueado para nuevos registros.")
elif not st.session_state.jornada_iniciada:
    st.info("👈 **Por favor, completa la información de los equipos en el menú lateral y presiona 'Iniciar Jornada' para comenzar.**")


# =========================================================
# FUNCIONES ALGORÍTMICAS Y GRÁFICAS
# =========================================================
def calcular_ancho_rectangular_recto(y_top, y_bot, R_ef):
    dy_top = abs(y_top - R_ef)
    dy_bot = abs(y_bot - R_ef)
    dy_max = max(dy_top, dy_bot)
    if dy_max >= R_ef:
        return 0.0
    return 2.0 * math.sqrt(R_ef**2 - dy_max**2)

def optimizar_aserrado(d_menor, d_mayor, largo, kerf_mm, dimensiones_prio):
    d_efectivo = d_menor
    R_ef = d_efectivo / 2.0
    kc = kerf_mm / 10.0

    r_menor_m = (d_menor / 2.0) / 100.0
    r_mayor_m = (d_mayor / 2.0) / 100.0
    largo_m = largo / 100.0
    vol_bruto_m3 = (math.pi * largo_m / 3.0) * (r_menor_m**2 + r_mayor_m**2 + (r_menor_m * r_mayor_m))

    prio_map = {item["espesor"]: item["prioridad"] for item in dimensiones_prio if item["espesor"] > 0}
    if not prio_map:
        return None

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
                rendimiento_pct = (vol_rect_total / vol_bruto_m3) * 100.0 if vol_bruto_m3 > 0 else 0.0

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

def generar_grafico_cortes(sol, d_menor):
    d_efectivo = sol["d_efectivo"]
    h_cant = sol["h_cant"]
    kc = sol["kc"]
    R = d_menor / 2.0
    R_ef = d_efectivo / 2.0

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6.5))

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

    centro_y_fase2 = h_cant - R_ef
    ax2.add_patch(patches.Circle((0, centro_y_fase2), R_ef, edgecolor='#2E7D32', facecolor='none', linewidth=1.5, linestyle='--', label='Circunferencia'))

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


# =========================================================
# FORMULARIO DE INGRESO (HABILITADO SI LA JORNADA ESTÁ ACTIVA)
# =========================================================
if st.session_state.jornada_iniciada and not st.session_state.jornada_finalizada:
    st.header("📐 Dimensiones del Tronco y Selección de Aserradero")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        aserradero_sel = st.selectbox("Aserradero en Proceso", ["Aserradero Manual", "Aserradero Hidráulico"])
    with col2:
        d_menor = st.number_input("Diámetro Menor (cm)", min_value=0.0, max_value=100.0, value=0.0, step=0.5)
    with col3:
        d_mayor = st.number_input("Diámetro Mayor (cm)", min_value=0.0, max_value=120.0, value=0.0, step=0.5)
    with col4:
        largo = st.number_input("Largo del Tronco (cm)", min_value=0.0, max_value=1000.0, value=250.0, step=10.0)

    kerf_mm = st.session_state.datos_jornada["kerf_mm"]

    if d_mayor < d_menor and d_menor > 0:
        st.warning("⚠️ El diámetro mayor debe ser mayor o igual al menor. Se ajustará al valor menor.")
        d_mayor = d_menor

    st.markdown("---")
    st.header("⚙️ Medidas Solicitadas y Prioridades")
    st.markdown("💡 **Instrucción:** Marca la casilla **Usar** e ingresa un valor mayor a 0 para incluir la medida en el plan de corte.")

    default_dims = [
        {"espesor": 0.0, "prio": 1, "usar": True},
        {"espesor": 0.0, "prio": 2, "usar": True},
        {"espesor": 0.0, "prio": 3, "usar": True},
        {"espesor": 0.0, "prio": 4, "usar": False},
        {"espesor": 0.0, "prio": 5, "usar": False},
    ]

    inputs_espesores = []
    cols = st.columns(5)

    for i, df_val in enumerate(default_dims):
        with cols[i]:
            usar = st.checkbox(f"Usar Medida {i+1}", value=df_val["usar"], key=f"usar_{i}")
            e = st.number_input(f"Medida {i+1} (cm)", min_value=0.0, max_value=30.0, value=df_val["espesor"], step=0.5, key=f"e_{i}")
            p = st.selectbox(f"Prioridad {i+1}", options=[1, 2, 3, 4, 5], index=df_val["prio"]-1, key=f"p_{i}")
            
            if usar and e > 0:
                inputs_espesores.append({"espesor": float(e), "prioridad": int(p)})

    # RENDERIZADO DE RESULTADOS
    if d_menor > 0 and d_mayor > 0 and len(inputs_espesores) > 0:
        sol = optimizar_aserrado(d_menor, d_mayor, largo, kerf_mm, inputs_espesores)

        if sol:
            st.markdown("---")
            st.pyplot(generar_grafico_cortes(sol, d_menor))
            
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Volumen Entrada (Smalian)", f"{sol['vol_bruto_m3']:.3f} m³")
            m2.metric("Maderable Canto Vivo", f"{sol['vol_m3']:.3f} m³")
            m3.metric("Rendimiento (Aprovechamiento)", f"{sol['aprovechamiento_pct']:.1f} %")
            m4.metric("Diámetro Menor Usado", f"{sol['d_efectivo']:.1f} cm")

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

            # REGISTRO
            st.markdown("---")
            col_btn, _ = st.columns([4, 6])
            with col_btn:
                if st.button("📌 Registrar Tronco Procesado en Reporte Diario", type="primary", use_container_width=True):
                    dj = st.session_state.datos_jornada
                    operadores_activos = dj["equipo_manual"] if aserradero_sel == "Aserradero Manual" else dj["equipo_hidraulico"]

                    nuevo_registro = {
                        "ID": int(len(st.session_state.historial) + 1),
                        "Fecha_Hora": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "Aserradero": str(aserradero_sel),
                        "Turno": str(dj["turno"]),
                        "Operadores": str(operadores_activos),
                        "D.Menor (cm)": round(float(d_menor), 2),
                        "D.Mayor (cm)": round(float(d_mayor), 2),
                        "Largo (cm)": round(float(largo), 2),
                        "m³ Entrada": round(float(sol["vol_bruto_m3"]), 4),
                        "m³ Útil (Rectangular)": round(float(sol["vol_m3"]), 4),
                        "m³ Bloques": round(float(sol["vol_bloques_m3"]), 4),
                        "m³ Tablas": round(float(sol["vol_tablas_m3"]), 4),
                        "m³ Kerf": round(float(sol["vol_kerf_m3"]), 4),
                        "Rendimiento (%)": round(float(sol["aprovechamiento_pct"]), 2),
                        "Bloque Base Z=0 (cm)": round(float(sol["p2_seq"][-1]), 2)
                    }

                    st.session_state.historial.append(nuevo_registro)
                    st.success("✅ Tronco guardado en el reporte acumulado diario local.")

                    if WEBAPP_URL:
                        try:
                            url_limpia = WEBAPP_URL.strip()
                            
                            # Envío explicito de números decimales formateados como punto
                            params = {
                                "id": nuevo_registro["ID"],
                                "fecha_hora": nuevo_registro["Fecha_Hora"],
                                "aserradero": nuevo_registro["Aserradero"],
                                "turno": nuevo_registro["Turno"],
                                "operadores": nuevo_registro["Operadores"],
                                "d_menor": f"{nuevo_registro['D.Menor (cm)']:.2f}",
                                "d_mayor": f"{nuevo_registro['D.Mayor (cm)']:.2f}",
                                "largo": f"{nuevo_registro['Largo (cm)']:.2f}",
                                "m3_entrada": f"{nuevo_registro['m³ Entrada']:.4f}",
                                "m3_util": f"{nuevo_registro['m³ Útil (Rectangular)']:.4f}",
                                "m3_bloques": f"{nuevo_registro['m³ Bloques']:.4f}",
                                "m3_tablas": f"{nuevo_registro['m³ Tablas']:.4f}",
                                "m3_kerf": f"{nuevo_registro['m³ Kerf']:.4f}",
                                "rendimiento": f"{nuevo_registro['Rendimiento (%)']:.2f}",
                                "bloque_base": f"{nuevo_registro['Bloque Base Z=0 (cm)']:.2f}"
                            }
                            
                            res = requests.get(url_limpia, params=params, timeout=10)
                            if res.status_code == 200:
                                st.info("☁️ Registro respaldado con éxito en Google Sheets con decimales precisos.")
                            else:
                                st.warning(f"Guardado localmente. Código de respuesta de Google: {res.status_code}")
                        except Exception as ex:
                            st.warning(f"Guardado localmente. No se pudo conectar a la web: {ex}")
                    else:
                        st.caption("ℹ️️ Nota: No ingresaste una URL de Google Apps Script. El registro queda guardado en la tabla de abajo.")
    else:
        st.info("⚠️ Ingresa diámetros mayores a 0 cm y marca al menos una medida activa mayor a 0 cm.")


# =========================================================
# REPORTE ACUMULADO Y TOTALIZACIÓN DE PRODUCCIÓN
# =========================================================
if st.session_state.historial:
    st.markdown("---")
    st.markdown("## 📊 Reporte de Producción Acumulado de la Jornada")
    
    df_hist = pd.DataFrame(st.session_state.historial)

    tot_bruto = float(df_hist["m³ Entrada"].sum())
    tot_util = float(df_hist["m³ Útil (Rectangular)"].sum())
    tot_bloques = float(df_hist["m³ Bloques"].sum())
    tot_tablas = float(df_hist["m³ Tablas"].sum())
    tot_kerf = float(df_hist["m³ Kerf"].sum())
    prom_rend = float((tot_util / tot_bruto * 100.0)) if tot_bruto > 0 else 0.0

    st1, st2, st3, st4, st5 = st.columns(5)
    st1.metric("Total m³ Entrada", f"{tot_bruto:.4f} m³")
    st2.metric("Total m³ Útil", f"{tot_util:.4f} m³")
    st3.metric("Total m³ Bloques", f"{tot_bloques:.4f} m³")
    st4.metric("Total m³ Tablas", f"{tot_tablas:.4f} m³")
    st5.metric("Rendimiento Global", f"{prom_rend:.2f} %")

    row_total = {
        "ID": "TOTAL",
        "Fecha_Hora": "-",
        "Aserradero": "-",
        "Turno": "-",
        "Operadores": "-",
        "D.Menor (cm)": "-",
        "D.Mayor (cm)": "-",
        "Largo (cm)": "-",
        "m³ Entrada": round(tot_bruto, 4),
        "m³ Útil (Rectangular)": round(tot_util, 4),
        "m³ Bloques": round(tot_bloques, 4),
        "m³ Tablas": round(tot_tablas, 4),
        "m³ Kerf": round(tot_kerf, 4),
        "Rendimiento (%)": round(prom_rend, 2),
        "Bloque Base Z=0 (cm)": "-"
    }

    df_export = pd.concat([df_hist, pd.DataFrame([row_total])], ignore_index=True)
    st.dataframe(df_export, use_container_width=True)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_export.to_excel(writer, index=False, sheet_name='Reporte_Produccion')

    st.download_button(
        label="📥 Descargar Reporte de Producción de Jornada (.xlsx)",
        data=output.getvalue(),
        file_name=f"reporte_produccion_aserradero_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary"
    )
