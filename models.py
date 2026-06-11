from pydantic import BaseModel, field_validator
import uuid
import pathlib

class UploadRequest(BaseModel):
    fileName: str
    fileType: str
    fileSize: int

    @field_validator('fileType')
    @classmethod
    def validate_file_type(cls, value: str) -> str:
        allowed_types = {"image/jpeg", "image/png", "image/gif"}
        if value not in allowed_types:
            raise ValueError(f"Tipo de archivo no válido. Se permiten: {', '.join(allowed_types)}")
        return value

    @field_validator('fileSize')
    @classmethod
    def validate_file_size(cls, value: int) -> int:
        if value <= 0 or value > 15728640:
            raise ValueError("El tamaño del archivo debe ser mayor a 0 y máximo de 15 MB (15728640 bytes)")
        return value

def generate_safe_key(original_filename: str) -> str:
    """
    Genera una ruta segura para S3 basada en un UUID4 y la 
    extensión del archivo original (forzada a ser alfanumérica).
    Evita riesgos de Path Traversal al no usar el nombre original.
    """
    # Extraer la extensión sin el punto inicial
    ext = pathlib.Path(original_filename).suffix.lstrip('.')
    
    # Filtrar solo caracteres alfanuméricos en la extensión
    safe_ext = "".join(c for c in ext if c.isalnum())
    
    # Fallback si no tiene extensión o si tenía caracteres no válidos
    if not safe_ext:
        safe_ext = "bin"
        
    safe_uuid = uuid.uuid4()
    
    return f"uploads/{safe_uuid}.{safe_ext}"
