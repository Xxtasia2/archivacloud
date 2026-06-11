import os
import boto3
from dotenv import load_dotenv
from fastapi import FastAPI

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
