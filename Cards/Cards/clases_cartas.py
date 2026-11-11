import matplotlib.pyplot as plt
import numpy as np
import cv2
import os

# --- 1. CLASE MOTIF (NUEVO) ---
class Motif:
    def __init__(self):
        self.motifId = 0
        self.image = np.empty([0,0], dtype=np.uint8) 
        self.area = 0
        self.boundingBox = None 
        self.centroid = None
        self.perimetro = 0
        self.HuMoments = np.empty([0,0], dtype=np.float64)
        self.contorno = None


# --- 2. CLASE CARD (ACTUALIZADA) ---
class Card:
    DIAMONDS = 'Diamonds' 
    SPADES = 'Spades'     
    HEARDS = 'Hearts'     
    CLUBS ='Clubs'        
    FIGURES = ('0','A','2','3','4','5','6','7','8','9','J','Q','K') 
    
    def __init__(self): 
        self.cardId = 0
        self.realSuit = ''
        self.realFigure = ''
        
        bboxType = [('x', np.intc),('y',np.intc),('width',np.intc),('height',np.intc)]
        self.boundingBox = np.zeros(1, dtype=bboxType).view(np.recarray)
        
        self.angle = 0.0
        self.grayImage = np.empty([0,0], dtype=np.uint8)
        self.colorImage = np.empty([0,0,0], dtype=np.uint8)
        
        # ### NUEVO EJERCICIO 7: Lista para guardar los motivos internos
        self.motifs = [] 

    def __repr__(self): 
        return f"Card ID: {self.cardId} | Motifs count: {len(self.motifs)}"
        
        