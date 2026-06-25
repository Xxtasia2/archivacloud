from pydantic import BaseModel, field_validator
import uuid
import re


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


def generate_safe_key(file_name: str, file_type: str) -> str:
    """
    Genera una ruta segura para S3 combinando un prefijo UUID4 corto
    con el nombre original del archivo sanitizado.
    - Reemplaza espacios por guiones bajos.
    - Elimina caracteres no permitidos (solo alfanuméricos, punto, guion
      y guion bajo) para mitigar Path Traversal (SEC-03).
    - Antepone los primeros 8 caracteres de un UUID4 para garantizar
      unicidad.
    Ejemplo de salida: 'uploads/a1b2c3d4-gato_1.png'
    """
    # Paso 1: Reemplazar espacios por guiones bajos
    clean_name = file_name.replace(" ", "_")

    # Paso 2: Eliminar cualquier carácter que no sea alfanumérico, punto,
    #          guion o guion bajo (mitigación SEC-03 contra Path Traversal)
    clean_name = re.sub(r"[^a-zA-Z0-9._\-]", "", clean_name)

    # Paso 3: Fallback si el nombre queda vacío tras la sanitización
    if not clean_name:
        mime_to_ext = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/gif": "gif",
        }
        ext = mime_to_ext.get(file_type, "bin")
        clean_name = f"archivo.{ext}"

    # Paso 4: Prefijo UUID4 corto (8 caracteres) para unicidad
    short_uuid = uuid.uuid4().hex[:8]

    return f"uploads/{short_uuid}-{clean_name}"

