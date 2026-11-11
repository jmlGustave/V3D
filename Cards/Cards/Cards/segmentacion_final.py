import numpy as np
import cv2
import os
import sys

# Importamos las clases definidas en tu archivo auxiliar (según el PDF)
try:
    from clases_cartas import Card, Motif
except ImportError:
    print("ERROR: No se encuentra 'clases_cartas.py'. Asegúrate de que está en la misma carpeta.")
    sys.exit(1)

# ==========================================
# 1. CONFIGURACIÓN (MODIFICAR AQUÍ)
# ==========================================

# --- IMPORTANTE: CAMBIA ESTO SEGÚN LO QUE ESTÉS GENERANDO ---

# OPCIÓN A: Para generar el ENTRENAMIENTO
# VISUALIZAR = False
# NOMBRE_ARCHIVO_SALIDA = 'trainCards.npz'
# RUTA_IMAGENES = './images/Training'  # Pon tu ruta correcta aquí

# OPCIÓN B: Para generar el TEST (Descomenta esto cuando hagas el test)
VISUALIZAR = True
NOMBRE_ARCHIVO_SALIDA = 'testCards.npz'
RUTA_IMAGENES = '/Users/javiermartinezlopez/Desktop/Python/VCO/practica7/aprendizaje/test' 

# Parámetros de imagen
low_H = 155 

# ==========================================
# 2. FUNCIONES AUXILIARES
# ==========================================

def label2rgb(label_img):
    """Colorea las etiquetas para visualización."""
    if np.max(label_img) == 0: return cv2.cvtColor(np.uint8(label_img), cv2.COLOR_GRAY2BGR)
    label_hue = np.uint8(179 * (label_img) / np.max(label_img))
    blank_ch = 255 * np.ones_like(label_hue)
    labeled_img = cv2.merge([label_hue, blank_ch, blank_ch])
    labeled_img = cv2.cvtColor(labeled_img, cv2.COLOR_HSV2BGR)
    labeled_img[label_img == 0] = 0
    return labeled_img

def ajustar_carta(img, img_gray, contorno):
    """Recorta y endereza la carta detectada."""
    rect = cv2.minAreaRect(contorno)
    box = cv2.boxPoints(rect)
    box = np.int32(box)
    
    p0, p1, p2 = box[0], box[1], box[2]
    d1 = np.linalg.norm(p0 - p1)
    d2 = np.linalg.norm(p1 - p2)
    
    if d1 > d2:
        vector_largo = p1 - p0
        ancho_final, alto_final = d2, d1
    else:
        vector_largo = p2 - p1
        ancho_final, alto_final = d1, d2
    
    angle_rad = np.arctan2(vector_largo[1], vector_largo[0])
    angle_deg = np.degrees(angle_rad)
    rotacion_necesaria = angle_deg - 90
    
    center = rect[0]
    M = cv2.getRotationMatrix2D(center, rotacion_necesaria, 1.0)
    h_img, w_img = img.shape[:2]
    
    img_rot_color = cv2.warpAffine(img, M, (w_img, h_img))
    img_rot_gray = cv2.warpAffine(img_gray, M, (w_img, h_img))
    
    w_crop = int(ancho_final)
    h_crop = int(alto_final)
    
    if w_crop > 0 and h_crop > 0:
        roi_color = cv2.getRectSubPix(img_rot_color, (w_crop, h_crop), center)
        roi_gray = cv2.getRectSubPix(img_rot_gray, (w_crop, h_crop), center)
        return roi_color, roi_gray, rotacion_necesaria
    else:
        return None, None, 0

# ==========================================
# 3. FUNCIÓN DE EXTRACCIÓN DE CARACTERÍSTICAS (CORREGIDA)
# ==========================================
def segmentar_objetos_carta(card_obj, reintento=False):
    """
    Segmenta los símbolos dentro de la carta y extrae características INVARIANTES.
    """
    # 1. Binarizar la carta (Otsu invertido porque los símbolos son oscuros sobre fondo blanco)
    _, thresh_card = cv2.threshold(card_obj.grayImage, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # 2. Limpieza morfológica para quitar ruido
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    thresh_card = cv2.morphologyEx(thresh_card, cv2.MORPH_OPEN, kernel)
    
    # 3. Componentes conectadas
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(thresh_card, 4, cv2.CV_32S)
    
    card_obj.motifs = []
    
    # Visualización
    viz_overlay = card_obj.colorImage.copy() if VISUALIZAR else None
    h_img, w_img = card_obj.grayImage.shape

    # Recorremos cada objeto encontrado (saltamos el 0 que es el fondo)
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        x = stats[i, cv2.CC_STAT_LEFT]
        y = stats[i, cv2.CC_STAT_TOP]
        w = stats[i, cv2.CC_STAT_WIDTH]
        h = stats[i, cv2.CC_STAT_HEIGHT]
        
        # Eliminamos objetos que toquen el borde (errores de corte)
        toca_borde = (x <= 1) or (y <= 1) or (x+w >= w_img-1) or (y+h >= h_img-1)
        
        # Filtro de Área: Solo nos interesan símbolos, no ruido pequeño ni la carta entera
        # Valores ajustados según el PDF [cite: 148]
        if 1000 < area < 40000 and not toca_borde:
            
            # Obtener el contorno específico de este objeto
            component_mask = (labels == i).astype(np.uint8) * 255
            contours, _ = cv2.findContours(component_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            if len(contours) > 0:
                cnt = max(contours, key=cv2.contourArea) # El contorno más grande de la máscara
                
                m = Motif()
                m.motifId = i
                m.boundingBox = (x, y, w, h)
                m.centroid = centroids[i]
                
                # --- A. CÁLCULO DE CARACTERÍSTICAS GEOMÉTRICAS ---
                
                # 1. Aspect Ratio (Relación de aspecto)
                aspect_ratio = float(w) / h
                
                # 2. Solidity (Solidez: Área / Área Convexa)
                hull = cv2.convexHull(cnt)
                hull_area = cv2.contourArea(hull)
                if hull_area == 0: 
                    solidity = 0
                else:
                    solidity = float(area) / hull_area
                
                # 3. Extent (Relación Área / BoundingBox)
                rect_area = w * h
                extent = float(area) / rect_area if rect_area > 0 else 0

                # 4. Momentos de Hu (INVARIANTES A ESCALA Y ROTACIÓN)
                moments = cv2.moments(cnt)
                huMoments = cv2.HuMoments(moments).flatten()
                
                # Log scale para los momentos de Hu (imprescindible para KNN)
                # Convierte 0.00003 en valores manejables como -4.5
                hu_log = []
                for val in huMoments:
                    if val != 0:
                        hu_log.append(-1 * np.copysign(1.0, val) * np.log10(abs(val)))
                    else:
                        hu_log.append(0)

                # --- B. RELLENO DEL VECTOR DE CARACTERÍSTICAS ---
                # ¡OJO! NO INCLUIMOS AREA NI PERÍMETRO BRUTOS AQUÍ
                # Solo características relativas (ratios) y momentos.
                
                m.features = []
                m.features.append(aspect_ratio) # Característica 0
                m.features.append(solidity)     # Característica 1
                m.features.append(extent)       # Característica 2
                m.features.extend(hu_log)       # Características 3-9 (7 momentos)
                
                # Guardamos datos extra en el objeto por si acaso, pero no en .features
                m.area = area 
                m.perimetro = cv2.arcLength(cnt, True)
                m.contorno = cnt
                
                card_obj.motifs.append(m)
                
                # Visualización
                if VISUALIZAR:
                    cv2.rectangle(viz_overlay, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    cv2.drawContours(viz_overlay, [cnt], -1, (0, 0, 255), 2)

    # Si no encuentra nada, a veces es porque la imagen está poco contrastada. 
    # Se aplica un filtro de enfoque y se reintenta una vez (recursión simple).
    if len(card_obj.motifs) == 0 and not reintento:
        kernel_sharpening = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
        card_obj.grayImage = cv2.filter2D(card_obj.grayImage, -1, kernel_sharpening)
        return segmentar_objetos_carta(card_obj, reintento=True)
    
    return viz_overlay

# ==========================================
# 4. BUCLE PRINCIPAL
# ==========================================
Cards = [] 
icard = 0

if VISUALIZAR:
    cv2.namedWindow('Proceso', cv2.WINDOW_NORMAL)

print(f"--- INICIO DEL PROCESO ---")
print(f"Leyendo imágenes de: {RUTA_IMAGENES}")
print(f"Guardando en: {NOMBRE_ARCHIVO_SALIDA}")

for root, dirs, files in os.walk(RUTA_IMAGENES):
    for name in files:
        if not name.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
            continue
        
        filename = os.path.join(root, name)
        img = cv2.imread(filename)
        if img is None: continue
        
        # 1. Detectar la carta en la mesa (Tapete verde)
        img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Umbral fijo para separar carta blanca del fondo oscuro/verde
        _, thresh1 = cv2.threshold(img_gray, low_H, 255, cv2.THRESH_BINARY)
        
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(thresh1, 4, cv2.CV_32S)
        
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            
            # Filtro para saber si es una carta (objeto grande)
            # Aproximadamente > 300,000 px según el PDF [cite: 34]
            if area > 100000: # Valor conservador, ajustado para asegurar detección
                
                componentMask = (labels == i).astype("uint8") * 255
                contours, _ = cv2.findContours(componentMask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                
                if len(contours) > 0:
                    cnt = max(contours, key=cv2.contourArea) # Contorno de la carta
                    
                    # Extraer y normalizar la imagen de la carta
                    roi_color, roi_gray, _ = ajustar_carta(img, img_gray, cnt)
                    
                    if roi_color is not None:
                        # Crear objeto Carta
                        c = Card()
                        c.cardId = icard
                        c.grayImage = roi_gray
                        c.colorImage = roi_color
                        
                        # --- EXTRACCIÓN DE MOTIVOS Y CARACTERÍSTICAS ---
                        # Aquí se llama a la función corregida
                        viz_res = segmentar_objetos_carta(c)
                        
                        # Añadir carta a la lista si tiene motivos
                        if len(c.motifs) > 0:
                            Cards.append(c)
                            print(f"Carta {icard}: Detectados {len(c.motifs)} motivos.")
                            icard += 1
                            
                            if VISUALIZAR and viz_res is not None:
                                cv2.imshow('Proceso', viz_res)
                                key = cv2.waitKey(0) # Espera tecla
                                if key == 27: # ESC para salir
                                    break
                        else:
                            print(f"Carta {icard}: No se detectaron motivos válidos.")

# ==========================================
# 5. GUARDADO FINAL
# ==========================================
print(f"--- GUARDANDO RESULTADOS ---")
np.savez(NOMBRE_ARCHIVO_SALIDA, Cartas=Cards)

if os.path.exists(NOMBRE_ARCHIVO_SALIDA):
    size = os.path.getsize(NOMBRE_ARCHIVO_SALIDA) / 1024
    print(f"Archivo '{NOMBRE_ARCHIVO_SALIDA}' generado con éxito ({size:.2f} KB).")
    print(f"Total cartas procesadas: {len(Cards)}")
    print("Recuerda: Si has cambiado las características, DEBES volver a etiquetar (etiquetar_cartas_OK.py) antes de entrenar.")
else:
    print("Error al guardar el archivo.")

cv2.destroyAllWindows()