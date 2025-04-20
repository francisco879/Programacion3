from enum import Enum
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime
from typing import Optional, List, Any
from exceptions import OwnEmpty

Base = declarative_base()

class EstadoVuelo(str, Enum):
    PROGRAMADO = "programado"
    EMERGENCIA = "emergencia"
    RETRASADO = "retrasado"

class Vuelo(Base):
    __tablename__ = "vuelos"
    
    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String, unique=True, index=True)
    estado = Column(String)
    hora = Column(DateTime)
    origen = Column(String)
    destino = Column(String)
    posicion = Column(Integer, nullable=True)
    
    # Para mantener la estructura de lista enlazada en la BD
    anterior_id = Column(Integer, ForeignKey('vuelos.id'), nullable=True)
    siguiente_id = Column(Integer, ForeignKey('vuelos.id'), nullable=True)

class Nodo:
    """Nodo para la lista doblemente enlazada."""
    
    def __init__(self, vuelo: Vuelo):
        self.vuelo = vuelo
        self.anterior = None
        self.siguiente = None

class ListaVuelos:
    """Implementación de una lista doblemente enlazada para la gestión de vuelos."""
    
    def __init__(self, session):
        self.cabeza = None
        self.cola = None
        self.size = 0
        self.session = session
        self._cargar_desde_bd()
    
    def _cargar_desde_bd(self):
        """Inicializa la lista cargando datos desde la base de datos."""
        try:
            # Obtener todos los vuelos ordenados por posición
            vuelos = self.session.query(Vuelo).all()
            
            if not vuelos:
                return  # Base de datos vacía
            
            # Construir diccionario id → vuelo
            vuelos_dict = {v.id: v for v in vuelos}
            
            # Encontrar la cabeza (sin anterior_id)
            cabeza = next((v for v in vuelos if v.anterior_id is None), None)
            
            if not cabeza:
                # Si no hay una cabeza clara, usar el primer vuelo
                cabeza = vuelos[0]
                
            # Reconstruir la lista
            self.cabeza = Nodo(cabeza)
            nodo_actual = self.cabeza
            self.size = 1
            
            # Seguir los siguientes
            siguiente_id = cabeza.siguiente_id
            while siguiente_id and siguiente_id in vuelos_dict:
                siguiente_vuelo = vuelos_dict[siguiente_id]
                nuevo_nodo = Nodo(siguiente_vuelo)
                
                nuevo_nodo.anterior = nodo_actual
                nodo_actual.siguiente = nuevo_nodo
                
                nodo_actual = nuevo_nodo
                self.size += 1
                
                siguiente_id = siguiente_vuelo.siguiente_id
            
            self.cola = nodo_actual
        except Exception as e:
            print(f"Error al cargar vuelos desde BD: {e}")
            # Empezar con lista vacía en caso de error
            self.cabeza = None
            self.cola = None
            self.size = 0
    
    def _actualizar_bd(self, vuelo: Vuelo, anterior_id: Optional[int] = None, siguiente_id: Optional[int] = None):
        """Actualiza las referencias de un vuelo en la base de datos."""
        try:
            if anterior_id is not None:
                vuelo.anterior_id = anterior_id
            if siguiente_id is not None:
                vuelo.siguiente_id = siguiente_id
                
            self.session.add(vuelo)
            self.session.commit()
            return True
        except Exception as e:
            print(f"Error al actualizar vuelo en BD: {e}")
            self.session.rollback()
            return False
    
    def insertar_al_frente(self, vuelo: Vuelo):
        """Añade un vuelo al inicio de la lista (para emergencias)."""
        nuevo_nodo = Nodo(vuelo)
        
        if self.cabeza is None:  # Lista vacía
            self.cabeza = nuevo_nodo
            self.cola = nuevo_nodo
            self._actualizar_bd(vuelo, anterior_id=None, siguiente_id=None)
        else:
            nuevo_nodo.siguiente = self.cabeza
            self.cabeza.anterior = nuevo_nodo
            
            # Actualizar referencias en BD
            self._actualizar_bd(vuelo, anterior_id=None, siguiente_id=self.cabeza.vuelo.id)
            self._actualizar_bd(self.cabeza.vuelo, anterior_id=vuelo.id)
            
            self.cabeza = nuevo_nodo
        
        self.size += 1
        return vuelo
    
    def insertar_al_final(self, vuelo: Vuelo):
        """Añade un vuelo al final de la lista (vuelos regulares)."""
        nuevo_nodo = Nodo(vuelo)
        
        if self.cola is None:  # Lista vacía
            self.cabeza = nuevo_nodo
            self.cola = nuevo_nodo
            self._actualizar_bd(vuelo, anterior_id=None, siguiente_id=None)
        else:
            nuevo_nodo.anterior = self.cola
            self.cola.siguiente = nuevo_nodo
            
            # Actualizar referencias en BD
            self._actualizar_bd(vuelo, anterior_id=self.cola.vuelo.id, siguiente_id=None)
            self._actualizar_bd(self.cola.vuelo, siguiente_id=vuelo.id)
            
            self.cola = nuevo_nodo
        
        self.size += 1
        return vuelo
    
    def obtener_primero(self):
        """Retorna (sin remover) el primer vuelo de la lista."""
        if self.cabeza is None:
            return None
        return self.cabeza.vuelo
    
    def obtener_ultimo(self):
        """Retorna (sin remover) el último vuelo de la lista."""
        if self.cola is None:
            return None
        return self.cola.vuelo
    
    def longitud(self):
        """Retorna el número total de vuelos en la lista."""
        return self.size
    
    def insertar_en_posicion(self, vuelo: Vuelo, posicion: int):
        """Inserta un vuelo en una posición específica (ej: índice 2)."""
        if posicion < 0 or posicion > self.size:
            raise ValueError(f"Posición {posicion} fuera de rango (0-{self.size})")
        
        if posicion == 0:
            return self.insertar_al_frente(vuelo)
        elif posicion == self.size:
            return self.insertar_al_final(vuelo)
        
        nuevo_nodo = Nodo(vuelo)
        actual = self.cabeza
        
        # Avanzar hasta la posición deseada
        for _ in range(posicion):
            actual = actual.siguiente
        
        # Insertar entre actual.anterior y actual
        nuevo_nodo.anterior = actual.anterior
        nuevo_nodo.siguiente = actual
        
        # Actualizar referencias en BD
        self._actualizar_bd(vuelo, 
                          anterior_id=actual.anterior.vuelo.id,
                          siguiente_id=actual.vuelo.id)
        self._actualizar_bd(actual.anterior.vuelo, siguiente_id=vuelo.id)
        self._actualizar_bd(actual.vuelo, anterior_id=vuelo.id)
        
        # Actualizar enlaces de los nodos
        actual.anterior.siguiente = nuevo_nodo
        actual.anterior = nuevo_nodo
        
        self.size += 1
        return vuelo
    
    def extraer_de_posicion(self, posicion: int):
        """Remueve y retorna el vuelo en la posición dada (ej: cancelación)."""
        if posicion < 0 or posicion >= self.size:
            raise ValueError(f"Posición {posicion} fuera de rango (0-{self.size-1})")
        
        vuelo_extraido = None
        
        if posicion == 0:
            # Extracción al inicio
            nodo_extraido = self.cabeza
            vuelo_extraido = nodo_extraido.vuelo
            
            self.cabeza = nodo_extraido.siguiente
            
            if self.cabeza:
                self.cabeza.anterior = None
                self._actualizar_bd(self.cabeza.vuelo, anterior_id=None)
            else:
                self.cola = None
                
            self._actualizar_bd(vuelo_extraido, anterior_id=None, siguiente_id=None)
        
        elif posicion == self.size - 1:
            # Extracción al final
            nodo_extraido = self.cola
            vuelo_extraido = nodo_extraido.vuelo
            
            self.cola = nodo_extraido.anterior
            
            if self.cola:
                self.cola.siguiente = None
                self._actualizar_bd(self.cola.vuelo, siguiente_id=None)
            else:
                self.cabeza = None
                
            self._actualizar_bd(vuelo_extraido, anterior_id=None, siguiente_id=None)
        
        else:
            # Extracción en medio
            actual = self.cabeza
            for _ in range(posicion):
                actual = actual.siguiente
            
            nodo_extraido = actual
            vuelo_extraido = nodo_extraido.vuelo
            
            actual.anterior.siguiente = actual.siguiente
            actual.siguiente.anterior = actual.anterior
            
            # Actualizar referencias en BD
            self._actualizar_bd(actual.anterior.vuelo, siguiente_id=actual.siguiente.vuelo.id)
            self._actualizar_bd(actual.siguiente.vuelo, anterior_id=actual.anterior.vuelo.id)
            self._actualizar_bd(vuelo_extraido, anterior_id=None, siguiente_id=None)
        
        self.size -= 1
        return vuelo_extraido
    
    def listar_todos(self):
        """Retorna una lista ordenada de todos los vuelos."""
        vuelos = []
        nodo_actual = self.cabeza
        
        while nodo_actual:
            vuelos.append(nodo_actual.vuelo)
            nodo_actual = nodo_actual.siguiente
            
        return vuelos
    
    def reordenar(self, orden_ids: List[int]):
        """Reordena la lista según un nuevo orden de IDs."""
        if len(orden_ids) != self.size:
            raise ValueError("La cantidad de IDs no coincide con el tamaño de la lista")
        
        # Crear una lista nueva basada en el orden proporcionado
        vuelos = {}
        nodo_actual = self.cabeza
        
        # Construir un diccionario con todos los vuelos
        while nodo_actual:
            vuelos[nodo_actual.vuelo.id] = nodo_actual.vuelo
            nodo_actual = nodo_actual.siguiente
        
        # Verificar que todos los IDs existan
        if not all(id in vuelos for id in orden_ids):
            raise ValueError("Uno o más IDs proporcionados no existen en la lista")
        
        # Vaciar la lista actual
        self.cabeza = None
        self.cola = None
        self.size = 0
        
        # Reconstruir la lista con el nuevo orden
        for id in orden_ids:
            self.insertar_al_final(vuelos[id])
            
        return self.listar_todos()