import os
import io
import boto3
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from botocore.exceptions import ClientError
from PIL import Image
from backend.models import UploadRequest, generate_safe_key

# 1. Cargar variables de entorno explícitamente desde la raíz
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(dotenv_path=env_path, override=True)

# Fail-Fast: Crash inmediato si faltan variables obligatorias
BUCKET_NAME: str = os.environ["BUCKET_NAME"]
AWS_REGION: str = os.environ["AWS_REGION"]

# Mock dinámico controlado por .env
USE_MOCK_S3: bool = os.getenv("USE_MOCK_S3", "false").lower() == "true"

class MockS3Client:
    def generate_presigned_post(self, Bucket, Key, Conditions=None, ExpiresIn=300):
        """Simula la respuesta de boto3 para la generación de presigned POST"""
        return {
            "url": "http://mock-s3-url.local",
            "fields": {"key": Key}
        }

    def list_objects_v2(self, Bucket, Prefix=""):
        """Simula la respuesta de boto3 para listar objetos en S3"""
        return {
            "Contents": [
                {
                    "Key": "uploads/mock-test-image.jpg",
                    "Size": 204800,
                    "LastModified": "2026-01-15T10:30:00Z"
                }
            ]
        }

    def generate_presigned_url(self, ClientMethod, Params=None, ExpiresIn=3600):
        """Simula la respuesta de boto3 para generar presigned GET URL"""
        key = Params.get("Key", "unknown") if Params else "unknown"
        return f"http://mock-s3-url.local/{key}?signature=mock"

    def delete_object(self, Bucket, Key):
        """Simula la respuesta de boto3 para eliminar un objeto en S3"""
        return {"ResponseMetadata": {"HTTPStatusCode": 204}}

if USE_MOCK_S3:
    s3_client = MockS3Client()
else:
    # Se asume que las credenciales están configuradas en el entorno
    s3_client = boto3.client("s3", region_name=AWS_REGION)

app = FastAPI(
    title="ArchivaCloud API",
    description="API con configuración S3 segura y sistema Mock"
)

# CORS: Permitir peticiones desde el frontend de desarrollo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# Exception handler global para ValidationError de Pydantic (SEC-07)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "Error de validación: tipo o tamaño incorrecto"}
    )

@app.get("/healthz", summary="Health check del sistema")
def health_check():
    return {"status": "ok"}

logger = logging.getLogger(__name__)

@app.post("/api/upload/presigned-url", summary="Generar presigned URL para subida a S3")
async def get_presigned_url(body: UploadRequest):
    # 2. Obtener ruta segura a partir del fileName y fileType (SEC-03)
    safe_key = generate_safe_key(body.fileName, body.fileType)

    # 3. Retornar Mock simulado si está activo
    if USE_MOCK_S3:
        return {
            "presignedUrl": {
                "url": "http://mock-s3-url.local",
                "fields": {"key": safe_key}
            },
            "key": safe_key,
            "publicUrl": f"https://mock/{safe_key}"
        }

    # 4. Generar URL real usando boto3 si no está en mock
    try:
        presigned_post = s3_client.generate_presigned_post(
            Bucket=BUCKET_NAME,
            Key=safe_key,
            Conditions=[
                ["content-length-range", 1, 15728640]
            ],
            ExpiresIn=300
        )
        
        public_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{safe_key}"
        
        return {
            "presignedUrl": presigned_post,
            "key": safe_key,
            "publicUrl": public_url
        }

    except ClientError as e:
        # 5. Ocultar el traceback al cliente (SEC-07)
        logger.error(f"ClientError de AWS: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor."
        )
    except Exception as e:
        logger.error(f"Error inesperado al generar presigned URL: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor."
        )


@app.get("/api/files", summary="Listar archivos subidos a S3 con URLs firmadas")
async def list_files():
    # Retornar datos simulados si el mock está activo
    if USE_MOCK_S3:
        return {
            "files": [
                {
                    "key": "uploads/mock-test-image.jpg",
                    "size": 204800,
                    "lastModified": "2026-01-15T10:30:00Z",
                    "url": "http://mock-s3-url.local/uploads/mock-test-image.jpg?signature=mock"
                }
            ]
        }

    # Lógica real con boto3
    try:
        response = s3_client.list_objects_v2(
            Bucket=BUCKET_NAME,
            Prefix="uploads/"
        )

        contents = response.get("Contents", [])
        files = []

        for obj in contents:
            key = obj["Key"]

            # Omitir la ruta raíz "uploads/" si S3 la devuelve como objeto
            if key == "uploads/":
                continue

            # Generar URL firmada temporal para lectura segura (bucket con bloqueo público)
            presigned_url = s3_client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": BUCKET_NAME, "Key": key},
                ExpiresIn=3600
            )

            files.append({
                "key": key,
                "size": obj.get("Size", 0),
                "lastModified": obj["LastModified"].isoformat()
                    if hasattr(obj["LastModified"], "isoformat")
                    else str(obj["LastModified"]),
                "url": presigned_url
            })

        return {"files": files}

    except ClientError as e:
        # SEC-07: Ocultar el traceback al cliente
        logger.error(f"ClientError de AWS al listar archivos: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al obtener archivos."
        )
    except Exception as e:
        logger.error(f"Error inesperado al listar archivos: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al obtener archivos."
        )


@app.delete("/api/files/{file_id}", summary="Eliminar un archivo de S3 de forma segura")
async def delete_file(file_id: str):
    # SEC-03: Mitigación de Path Traversal — rechazar identificadores con caracteres peligrosos
    if "/" in file_id or "\\" in file_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Identificador de archivo inválido."
        )

    # Construcción segura de la llave completa
    safe_key = f"uploads/{file_id}"

    # Retornar respuesta simulada si el mock está activo
    if USE_MOCK_S3:
        return {
            "message": f"Archivo '{file_id}' eliminado exitosamente (modo mock).",
            "key": safe_key
        }

    # Lógica real con boto3
    try:
        s3_client.delete_object(
            Bucket=BUCKET_NAME,
            Key=safe_key
        )

        return {
            "message": f"Archivo '{file_id}' eliminado exitosamente.",
            "key": safe_key
        }

    except ClientError as e:
        # SEC-07: Ocultar el traceback al cliente
        logger.error(f"ClientError de AWS al eliminar archivo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al eliminar el archivo."
        )
    except Exception as e:
        logger.error(f"Error inesperado al eliminar archivo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al eliminar el archivo."
        )


@app.post("/api/compress", summary="Comprimir una imagen usando Pillow")
async def compress_image(file: UploadFile):
    """
    Recibe un archivo de imagen (JPEG o PNG), lo comprime en memoria
    usando Pillow y retorna la imagen comprimida como respuesta binaria.
    """
    # Validar que el Content-Type sea una imagen soportada
    allowed_types = {
        "image/jpeg": ("JPEG", "image/jpeg"),
        "image/png": ("PNG", "image/png"),
    }

    content_type = file.content_type or ""
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato no soportado para compresión. Se permiten: {', '.join(allowed_types.keys())}",
        )

    pil_format, media_type = allowed_types[content_type]

    try:
        # Leer bytes del archivo subido en memoria
        file_bytes = await file.read()
        image = Image.open(io.BytesIO(file_bytes))

        # Preparar buffer de salida
        output_buffer = io.BytesIO()

        # Comprimir según el formato
        save_kwargs = {"format": pil_format, "optimize": True}
        if pil_format == "JPEG":
            save_kwargs["quality"] = 60
        elif pil_format == "PNG":
            # Para PNG, compress_level va de 0 (sin compresión) a 9 (máxima)
            save_kwargs["compress_level"] = 6

        image.save(output_buffer, **save_kwargs)
        output_buffer.seek(0)

        return Response(
            content=output_buffer.getvalue(),
            media_type=media_type,
            headers={
                "Content-Disposition": f'inline; filename="compressed_{file.filename}"'
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al comprimir imagen con Pillow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al comprimir la imagen.",
        )
