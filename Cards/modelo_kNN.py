import cv2
import os
import numpy as np
import matplotlib.pyplot as plt
from sklearn import metrics
from sklearn.metrics import confusion_matrix, classification_report, matthews_corrcoef
from clases_cartas import Card, Motif

# ==========================================
# CONFIGURACIÓN
# ==========================================
FIGURES = ('0','A','2','3','4','5','6','7','8','9','J','Q','K') 
SUITS = ('Rombos','Picas','Corazones','Treboles')
MOTIF_LABELS = ('Rombos','Picas','Corazones','Treboles','0','2','3','4','5','6','7','8','9','A','J','Q','K','Others')   

# ==========================================
# 1. TRAINING (Entrenamiento)
# ==========================================
filecard = 'cartas.npz'
if not os.path.exists(filecard):
    print(f"Error: No existe {filecard}")
    exit()

npzfile = np.load(filecard, allow_pickle=True) 
cards = npzfile['Cartas']
llen = cards.size

samples = []     
responses = []   

print("--- Procesando ENTRENAMIENTO ---")
j=0
for i in range(0, llen):
    motifs = cards[i].motifs
    for mot in motifs:
        # Validación de seguridad
        if not hasattr(mot, 'features') or mot.features is None: continue
        
        lbl = getattr(mot, 'motifLabel', 'i')
        if lbl == 'i' or lbl == '?' or lbl == '': continue
        
        if lbl in MOTIF_LABELS:
            idx = MOTIF_LABELS.index(lbl)
            responses.append(idx)
            j += 1
            
            # --- CORRECCIÓN CLAVE ---
            # Usamos el vector de características que ya calculamos en el paso 1.
            # Esto contiene [Area, Perimetro, Compacidad, Color, HuMoments...]
            samples.append(mot.features) 

# Convertir a numpy array float32 (Requerido por OpenCV)
# CORREGIDO: Usamos 'samples', no 'samples_vect'
sampl = np.asarray(samples).astype(np.float32)
resp = np.asarray(responses).astype(np.int32)

print(f"Entrenando con {len(samples)} muestras...")

# Creación y entrenamiento del modelo kNN
knn = cv2.ml.KNearest_create()
knn.train(sampl, cv2.ml.ROW_SAMPLE, resp)      

print("Modelo entrenado.")

# ==========================================
# 2. TEST (Validación)
# ==========================================
filecardTest = 'trainingCards.npz'
if not os.path.exists(filecardTest):
    print(f"Error: No existe {filecardTest}")
    exit()

npzfileT = np.load(filecardTest, allow_pickle=True) 
cardsTest = npzfileT['Cartas']

samplesTest = []
responsesTest = []

# CORREGIDO: Recalculamos la longitud para el test
le_test = len(cardsTest)

print("--- Procesando TEST ---")
j=0
for i in range(0, le_test):   
    motifs = cardsTest[i].motifs
    for mot in motifs:
        if not hasattr(mot, 'features') or mot.features is None: continue

        lbl = getattr(mot, 'motifLabel', 'i')
        
        # Gestión de etiquetas desconocidas en test
        if lbl == 'i' or lbl == '?' or lbl == '': lbl = 'Others'
        if lbl not in MOTIF_LABELS: lbl = 'Others'

        idx = MOTIF_LABELS.index(lbl)
        responsesTest.append(idx)
        j +=1
        
        # Añadimos features (DEBE SER IGUAL QUE EN TRAINING)
        samplesTest.append(mot.features)
      
# Convertir a arrays
samplTest = np.asarray(samplesTest).astype(np.float32)
respTest = np.asarray(responsesTest).astype(np.int32)

# Predicción k=3
print("Ejecutando predicción...")
ret, results, neighbours, dist = knn.findNearest(samplTest, k=3)

# ==========================================
# 3. VISUALIZACIÓN
# ==========================================
le = len(results)
aciertos = 0
pred = np.zeros(le)
real = np.zeros(le)

for i in range(0, le):
    pred[i] = int(results[i][0])
    real[i] = respTest[i]
    
    if pred[i] == real[i]:
        aciertos += 1

print(f'>>> Tasa aciertos: {aciertos/le:.2%}')

# Métricas
# Usamos try/except para evitar errores si faltan clases en el test
try:
    print(classification_report(real, pred, target_names=MOTIF_LABELS, zero_division=0))
except:
    print(classification_report(real, pred, zero_division=0))

CONF_MAT = confusion_matrix(real, pred)
MCC = matthews_corrcoef(real, pred)
print('MCC: ', MCC)

# Gráfica corregida
plt.figure(figsize=(10, 8))
# CORREGIDO: Llamada correcta a display
cm_display = metrics.ConfusionMatrixDisplay(confusion_matrix=CONF_MAT, display_labels=MOTIF_LABELS)
# CORREGIDO: Argumento correcto es xticks_rotation
cm_display.plot(xticks_rotation='vertical') 
plt.title('Matriz de Confusión')
plt.show()