import os
import boto3
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from botocore.exceptions import ClientError
from backend.models import UploadRequest, generate_safe_key

# 1. Cargar variables de entorno
load_dotenv()

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

if USE_MOCK_S3:
    s3_client = MockS3Client()
else:
    # Se asume que las credenciales están configuradas en el entorno
    s3_client = boto3.client("s3", region_name=AWS_REGION)

app = FastAPI(
    title="ArchivaCloud API",
    description="API con configuración S3 segura y sistema Mock"
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
    # 2. Obtener ruta segura a partir del fileType (SEC-03)
    safe_key = generate_safe_key(body.fileType)

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
