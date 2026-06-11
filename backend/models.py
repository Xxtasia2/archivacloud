from pydantic import BaseModel, field_validator
import uuid

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

def generate_safe_key(file_type: str) -> str:
    """
    Genera una ruta segura para S3 basada en un UUID4 y derivando la 
    extensión a partir del MIME type validado.
    Evita riesgos de Path Traversal al ignorar el nombre original (SEC-03).
    """
    mime_to_ext = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/gif": "gif"
    }
    ext = mime_to_ext.get(file_type, "bin")
        
    safe_uuid = uuid.uuid4()
    
    return f"uploads/{safe_uuid}.{ext}"
