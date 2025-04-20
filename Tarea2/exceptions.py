class VueloException(Exception):
    """Excepción base para errores en la gestión de vuelos"""
    pass

class OwnEmpty(VueloException):
    """Excepción para cuando la lista está vacía"""
    pass