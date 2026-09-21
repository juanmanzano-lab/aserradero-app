import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np

def graficar_plan_de_corte(tablero_w, tablero_h, piezas, kerf=2.0, titulo="Plan de Corte y Piezas Efectivas"):
    """
    Dibuja el tablero base y la disposición espacial de las piezas efectivas cortadas.

    Parámetros:
    - tablero_w: Ancho del tablero base (mm o cm)
    - tablero_h: Alto del tablero base (mm o cm)
    - piezas: Lista de diccionarios con las piezas colocadas:
              [{'x': float, 'y': float, 'w': float, 'h': float, 'nombre': str, 'id': str}, ...]
    - kerf: Ancho del corte de sierra / disco (mm o cm)
    - titulo: Título principal del gráfico
    """
    fig, ax = plt.subplots(figsize=(12, 8))
    
    # 1. Dibujar el Tablero Base (Fondo / Desperdicio)
    tablero_patch = patches.Rectangle(
        (0, 0), tablero_w, tablero_h,
        linewidth=2, edgecolor='#1C2833', facecolor='#EAECEE',
        hatch='//', alpha=0.7, label='Retal / Desperdicio'
    )
    ax.add_patch(tablero_patch)

    # Palette de colores vistosos para piezas efectivas
    colores = [
        '#2EA44E', '#2874A6', '#D4AC0D', '#884EA0',
        '#CA6F1E', '#17A589', '#D98880', '#2F4F4F'
    ]

    area_piezas_total = 0.0

    # 2. Dibujar cada Pieza Efectiva
    for i, p in enumerate(piezas):
        x, y, w, h = p['x'], p['y'], p['w'], p['h']
        nombre = p.get('nombre', f"P{i+1}")
        id_p = p.get('id', f"#{i+1}")
        color = colores[i % len(colores)]

        # Rectángulo de la pieza
        pieza_rect = patches.Rectangle(
            (x, y), w, h,
            linewidth=1.5, edgecolor='#1B2631', facecolor=color, alpha=0.85
        )
        ax.add_patch(pieza_rect)

        # Representación visual del Kerf (línea exterior de corte)
        if kerf > 0:
            kerf_rect = patches.Rectangle(
                (x - kerf/2, y - kerf/2), w + kerf, h + kerf,
                linewidth=1, edgecolor='#E74C3C', facecolor='none', linestyle='--'
            )
            ax.add_patch(kerf_rect)

        # Texto / Etiqueta central de la pieza
        area_pieza = w * h
        area_piezas_total += area_pieza
        
        texto_label = f"{id_p}\n{nombre}\n{w:.1f} x {h:.1f}"
        ax.text(
            x + w / 2.0, y + h / 2.0, texto_label,
            color='white', fontweight='bold', fontsize=9,
            ha='center', va='center',
            bbox=dict(boxstyle='round,pad=0.2', facecolor='black', alpha=0.4, edgecolor='none')
        )

    # 3. Métricas de Rendimiento
    area_tablero = tablero_w * tablero_h
    area_desperdicio = area_tablero - area_piezas_total
    rendimiento_pct = (area_piezas_total / area_tablero) * 100.0 if area_tablero > 0 else 0.0

    # 4. Cotas y Flechas de Dimensiones del Tablero
    # Cota Horizontal (Ancho)
    ax.annotate(
        '', xy=(0, tablero_h + 30), xytext=(tablero_w, tablero_h + 30),
        arrowprops=dict(arrowstyle='<->', color='#2C3E50', lw=1.5)
    )
    ax.text(
        tablero_w / 2.0, tablero_h + 45, f"Ancho Tablero: {tablero_w:.1f}",
        fontsize=10, fontweight='bold', ha='center', color='#2C3E50'
    )

    # Cota Vertical (Alto)
    ax.annotate(
        '', xy=(-30, 0), xytext=(-30, tablero_h),
        arrowprops=dict(arrowstyle='<->', color='#2C3E50', lw=1.5)
    )
    ax.text(
        -50, tablero_h / 2.0, f"Alto Tablero:\n{tablero_h:.1f}",
        fontsize=10, fontweight='bold', va='center', ha='center', rotation=90, color='#2C3E50'
    )

    # 5. Panel Lateral con Métricas y Resumen de Piezas
    info_box = (
        f"📊 RENDIMIENTO DE CORTE\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• Área Tablero Total: {area_tablero:,.1f}\n"
        f"• Área Piezas Útiles: {area_piezas_total:,.1f}\n"
        f"• Área Desperdicio:   {area_desperdicio:,.1f}\n"
        f"• Rendimiento Útil:   {rendimiento_pct:.2f} %\n"
        f"• Cantidad de Piezas: {len(piezas)} unid.\n"
        f"• Espesor Corte/Kerf: {kerf:.1f}"
    )

    ax.text(
        1.02, 0.65, info_box, transform=ax.transAxes,
        fontsize=10, verticalalignment='top', family='monospace',
        bbox=dict(boxstyle='round,pad=0.6', facecolor='#F8F9F9', edgecolor='#BDC3C7', alpha=0.95)
    )

    # Configuración de ejes y bordes del gráfico
    margin_x = tablero_w * 0.1
    margin_y = tablero_h * 0.15
    ax.set_xlim(-margin_x, tablero_w + margin_x)
    ax.set_ylim(-margin_y, tablero_h + margin_y)
    
    ax.set_aspect('equal')
    ax.set_title(titulo, fontsize=14, fontweight='bold', pad=25, color='#1A5276')
    ax.set_xlabel("Coordenada X (mm/cm)", fontsize=10)
    ax.set_ylabel("Coordenada Y (mm/cm)", fontsize=10)
    ax.grid(True, linestyle=':', alpha=0.4, color='#95A5A6')

    plt.tight_layout()
    return fig


# ==============================================================================
# EJEMPLO DE USO / PRUEBA DEL GRÁFICO
# ==============================================================================
if __name__ == "__main__":
    # Dimensiones del tablero principal
    ANCHO_TABLERO = 2440.0  # mm (ej. 2.44 m)
    ALTO_TABLERO = 1220.0   # mm (ej. 1.22 m)
    KERF = 3.0              # mm (espesor de sierra)

    # Lista de Piezas Efectivas colocadas en el mapa X, Y
    piezas_efectivas = [
        # Fila inferior
        {'x': 0, 'y': 0, 'w': 800, 'h': 600, 'nombre': 'Puerta Inf. A', 'id': 'P-01'},
        {'x': 803, 'y': 0, 'w': 800, 'h': 600, 'nombre': 'Puerta Inf. B', 'id': 'P-02'},
        {'x': 1606, 'y': 0, 'w': 800, 'h': 400, 'nombre': 'Base Cajón 1', 'id': 'P-03'},
        {'x': 1606, 'y': 403, 'w': 800, 'h': 200, 'nombre': 'Frontal Cajón', 'id': 'P-04'},

        # Fila intermedia
        {'x': 0, 'y': 603, 'w': 1200, 'h': 350, 'nombre': 'Estante Sup. 1', 'id': 'P-05'},
        {'x': 1203, 'y': 603, 'w': 1200, 'h': 350, 'nombre': 'Estante Sup. 2', 'id': 'P-06'},

        # Fila superior
        {'x': 0, 'y': 956, 'w': 900, 'h': 250, 'nombre': 'Lateral Der.', 'id': 'P-07'},
        {'x': 903, 'y': 956, 'w': 900, 'h': 250, 'nombre': 'Lateral Izq.', 'id': 'P-08'},
        {'x': 1806, 'y': 956, 'w': 600, 'h': 250, 'nombre': 'Tapa Registro', 'id': 'P-09'},
    ]

    # Generar y mostrar el diagrama
    figura = graficar_plan_de_corte(
        tablero_w=ANCHO_TABLERO,
        tablero_h=ALTO_TABLERO,
        piezas=piezas_efectivas,
        kerf=KERF,
        titulo="Plan de Corte Optimizando Piezas Efectivas (Tablero 2440x1220 mm)"
    )
    
    plt.show()
