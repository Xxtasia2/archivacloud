import os
import boto3
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status, Body
from pydantic import ValidationError
from botocore.exceptions import ClientError
from models import UploadRequest, generate_safe_key

# 1. Cargar variables de entorno (con valores default hardcodeados por problemas de permisos)
load_dotenv()

BUCKET_NAME: str = os.getenv("BUCKET_NAME", "archivacloud-p02-temp")
AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")

# 3. Variable booleana para controlar el uso del mock
USE_MOCK_S3: bool = True

# Sistema de fallback (mock) para desarrollo local
class MockS3Client:
    def generate_presigned_post(self, Bucket, Key, Conditions=None, ExpiresIn=300):
        """Simula la respuesta de boto3 para la generación de presigned POST"""
        return {
            "url": "http://mock-s3-url.local",
            "fields": {"key": Key}
        }

# 2. Inicializar el cliente (Mock o Real)
if USE_MOCK_S3:
    s3_client = MockS3Client()
else:
    # Se asume que AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY y AWS_SESSION_TOKEN están en el entorno
    s3_client = boto3.client("s3", region_name=AWS_REGION)

# Inicialización básica de la app FastAPI
app = FastAPI(
    title="ArchivaCloud API",
    description="API con configuración S3 y sistema Mock"
)

@app.get("/healthz", summary="Health check del sistema")
def health_check():
    return {"status": "ok"}

logger = logging.getLogger(__name__)

@app.post("/api/upload/presigned-url", summary="Generar presigned URL para subida a S3")
async def get_presigned_url(body: dict = Body(...)):
    # 1. Validar el body usando UploadRequest y capturar ValidationError
    try:
        req_data = UploadRequest(**body)
    except ValidationError as e:
        logger.warning(f"Error de validación Pydantic: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Error de validación en los datos proporcionados."
        )

    # 2. Obtener ruta segura
    safe_key = generate_safe_key(req_data.fileName)

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

