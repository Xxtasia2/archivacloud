const API_BASE = "https://archivacloud.onrender.com";

// Umbral de compresión: 1 MB
const COMPRESS_THRESHOLD = 1048576;

// ─────────────────────────────────────────────
// 0. Compresión de imagen vía backend (Pillow)
// ─────────────────────────────────────────────

/**
 * Envía una imagen al endpoint de compresión y devuelve un nuevo File.
 * Solo se invoca para JPEG/PNG que superen 1 MB.
 *
 * @param {File} file - Archivo original del usuario.
 * @returns {Promise<File>} Archivo comprimido como objeto File.
 */
async function compressImage(file) {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/api/compress`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => null);
    throw new Error(
      errorData?.detail ||
        `Error al comprimir imagen (HTTP ${res.status})`
    );
  }

  const blob = await res.blob();
  // Crear un nuevo File con el mismo nombre y tipo para mantener compatibilidad
  return new File([blob], file.name, { type: file.type });
}

// ─────────────────────────────────────────────
// 1. Subida en tres pasos (Compresión + Presigned URL + S3)
// ─────────────────────────────────────────────

/**
 * Paso A: Si es JPG/PNG y pesa > 1 MB, comprime vía /api/compress.
 * Paso B: Solicita una presigned URL al backend con los datos del archivo final.
 * Paso C: Sube el archivo directamente a S3 usando FormData.
 *
 * @param {File} file - Objeto File del input del usuario.
 * @returns {Promise<{key: string, publicUrl: string}>} Datos del archivo subido.
 */
export async function uploadFile(file) {
  try {
    // ── Paso A: Compresión condicional ──
    let finalFile = file;
    const compressibleTypes = ["image/jpeg", "image/png"];

    if (compressibleTypes.includes(file.type) && file.size > COMPRESS_THRESHOLD) {
      console.info(
        `🗜️ Comprimiendo imagen (${(file.size / 1024 / 1024).toFixed(2)} MB)...`
      );
      finalFile = await compressImage(file);
      console.info(
        `✅ Imagen comprimida: ${(finalFile.size / 1024 / 1024).toFixed(2)} MB`
      );
    }

    // ── Paso B: Obtener presigned POST desde el backend ──
    const presignedRes = await fetch(`${API_BASE}/api/upload/presigned-url`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        fileName: finalFile.name,
        fileType: finalFile.type,
        fileSize: finalFile.size,
      }),
    });

    if (!presignedRes.ok) {
      const errorData = await presignedRes.json().catch(() => null);
      throw new Error(
        errorData?.detail ||
          `Error al obtener presigned URL (HTTP ${presignedRes.status})`
      );
    }

    const { presignedUrl, key, publicUrl } = await presignedRes.json();

    // ── Paso C: Subir archivo directo a S3 con FormData ──
    const formData = new FormData();

    // Adjuntar todos los campos de autorización que devolvió S3
    Object.entries(presignedUrl.fields).forEach(([field, value]) => {
      formData.append(field, value);
    });

    // El archivo SIEMPRE va al final del FormData (requisito de S3)
    formData.append("file", finalFile);

    const s3Res = await fetch(presignedUrl.url, {
      method: "POST",
      body: formData,
      // No establecer Content-Type manualmente; el navegador
      // agrega el boundary correcto para multipart/form-data
    });

    if (!s3Res.ok) {
      throw new Error(
        `Error al subir archivo a S3 (HTTP ${s3Res.status}). ` +
          "Verifica que el bucket tenga la configuración CORS correcta."
      );
    }

    console.info(`✅ Archivo subido exitosamente: ${key}`);
    return { key, publicUrl };
  } catch (error) {
    // Detección específica de errores comunes
    if (error instanceof TypeError && error.message === "Failed to fetch") {
      console.error(
        "❌ Error de red o CORS: No se pudo conectar con el servidor. " +
          "Verifica que el backend esté corriendo en " +
          API_BASE +
          " y que la configuración CORS permita el origen del frontend."
      );
    } else if (error.message?.includes("413")) {
      console.error(
        "❌ Archivo demasiado grande: El servidor rechazó la solicitud " +
          "por exceder el tamaño máximo permitido (15 MB)."
      );
    } else {
      console.error(`❌ Error durante la subida: ${error.message}`);
    }
    throw error;
  }
}

// ─────────────────────────────────────────────
// 2. Listado de archivos
// ─────────────────────────────────────────────

/**
 * Obtiene la lista de archivos subidos con sus URLs firmadas.
 *
 * @returns {Promise<Array<{key: string, size: number, lastModified: string, url: string}>>}
 */
export async function listFiles() {
  try {
    const res = await fetch(`${API_BASE}/api/files`);

    if (!res.ok) {
      const errorData = await res.json().catch(() => null);
      throw new Error(
        errorData?.detail ||
          `Error al obtener archivos (HTTP ${res.status})`
      );
    }

    const data = await res.json();
    return data.files;
  } catch (error) {
    if (error instanceof TypeError && error.message === "Failed to fetch") {
      console.error(
        "❌ Error de red o CORS: No se pudo conectar con el servidor. " +
          "Verifica que el backend esté corriendo en " +
          API_BASE +
          " y que CORS esté configurado correctamente."
      );
    } else {
      console.error(`❌ Error al listar archivos: ${error.message}`);
    }
    throw error;
  }
}

// ─────────────────────────────────────────────
// 3. Borrado de archivo
// ─────────────────────────────────────────────

/**
 * Elimina un archivo de S3 a través del backend.
 * Envía solo el nombre del archivo (UUID + extensión), sin el prefijo "uploads/".
 *
 * @param {string} fileKey - Llave completa del archivo (ej: "uploads/uuid.jpg").
 * @returns {Promise<{message: string}>} Mensaje de confirmación.
 */
export async function deleteFile(fileKey) {
  try {
    // Extraer solo el identificador del archivo (sin "uploads/")
    const fileId = fileKey.startsWith("uploads/")
      ? fileKey.slice("uploads/".length)
      : fileKey;

    const res = await fetch(`${API_BASE}/api/files/${fileId}`, {
      method: "DELETE",
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => null);
      throw new Error(
        errorData?.detail ||
          `Error al eliminar archivo (HTTP ${res.status})`
      );
    }

    const data = await res.json();
    console.info(`✅ ${data.message}`);
    return data;
  } catch (error) {
    if (error instanceof TypeError && error.message === "Failed to fetch") {
      console.error(
        "❌ Error de red o CORS: No se pudo conectar con el servidor. " +
          "Verifica que el backend esté corriendo en " +
          API_BASE +
          " y que CORS esté configurado correctamente."
      );
    } else {
      console.error(`❌ Error al eliminar archivo: ${error.message}`);
    }
    throw error;
  }
}
