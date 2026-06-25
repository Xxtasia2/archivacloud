import { useState, useEffect, useCallback } from 'react';
import { uploadFile, listFiles, deleteFile } from './services/api';
import './App.css';

const MAX_FILE_SIZE = 15 * 1024 * 1024; // 15 MB
const ACCEPTED_TYPES = '.jpg,.jpeg,.png,.gif';

function formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function formatDate(dateStr) {
  try {
    return new Date(dateStr).toLocaleDateString('es-ES', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return dateStr;
  }
}

/**
 * Extrae el nombre limpio de archivo desde la key de S3.
 * Formato esperado: 'uploads/a1b2c3d4-nombre_real.png'
 * Retorna: 'nombre_real.png'
 */
function extractFileName(key) {
  // Quitar el prefijo 'uploads/'
  const withoutPrefix = key.replace(/^uploads\//, '');
  // Quitar el UUID corto de 8 caracteres + guion (ej: 'a1b2c3d4-')
  const withoutUuid = withoutPrefix.replace(/^[a-f0-9]{8}-/, '');
  return withoutUuid || key;
}

export default function App() {
  // ── State ──
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isLoadingFiles, setIsLoadingFiles] = useState(true);
  const [deletingKey, setDeletingKey] = useState(null);
  const [statusMsg, setStatusMsg] = useState(null); // { type: 'success' | 'error', text }
  const [isDragging, setIsDragging] = useState(false);

  // ── Fetch files ──
  const fetchFiles = useCallback(async () => {
    try {
      setIsLoadingFiles(true);
      const data = await listFiles();
      setFiles(data || []);
    } catch {
      setStatusMsg({ type: 'error', text: 'No se pudieron cargar los archivos.' });
    } finally {
      setIsLoadingFiles(false);
    }
  }, []);

  useEffect(() => {
    fetchFiles();
  }, [fetchFiles]);

  // ── Auto-clear status messages ──
  useEffect(() => {
    if (!statusMsg) return;
    const timer = setTimeout(() => setStatusMsg(null), 4000);
    return () => clearTimeout(timer);
  }, [statusMsg]);

  // ── File selection ──
  function handleFileSelect(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > MAX_FILE_SIZE) {
      setStatusMsg({ type: 'error', text: `El archivo supera los 15 MB (${formatBytes(file.size)}).` });
      setSelectedFile(null);
      e.target.value = '';
      return;
    }

    setSelectedFile(file);
    setStatusMsg(null);
  }

  // ── Upload ──
  async function handleUpload() {
    if (!selectedFile) return;

    try {
      setIsUploading(true);
      setStatusMsg(null);
      await uploadFile(selectedFile);
      setStatusMsg({ type: 'success', text: '¡Archivo subido exitosamente!' });
      setSelectedFile(null);

      // Reset the file input
      const input = document.getElementById('file-input');
      if (input) input.value = '';

      // Refresh gallery
      await fetchFiles();
    } catch (err) {
      setStatusMsg({ type: 'error', text: err.message || 'Error al subir el archivo.' });
    } finally {
      setIsUploading(false);
    }
  }

  // ── Delete ──
  async function handleDelete(fileKey) {
    try {
      setDeletingKey(fileKey);
      await deleteFile(fileKey);
      setFiles((prev) => prev.filter((f) => f.key !== fileKey));
      setStatusMsg({ type: 'success', text: 'Archivo eliminado correctamente.' });
    } catch (err) {
      setStatusMsg({ type: 'error', text: err.message || 'Error al eliminar el archivo.' });
    } finally {
      setDeletingKey(null);
    }
  }

  // ── Drag & Drop ──
  function handleDragOver(e) {
    e.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave(e) {
    e.preventDefault();
    setIsDragging(false);
  }

  function handleDrop(e) {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (!file) return;

    const validTypes = ['image/jpeg', 'image/png', 'image/gif'];
    if (!validTypes.includes(file.type)) {
      setStatusMsg({ type: 'error', text: 'Tipo de archivo no permitido. Solo JPG, PNG o GIF.' });
      return;
    }

    if (file.size > MAX_FILE_SIZE) {
      setStatusMsg({ type: 'error', text: `El archivo supera los 15 MB (${formatBytes(file.size)}).` });
      return;
    }

    setSelectedFile(file);
    setStatusMsg(null);
  }

  // ── Render ──
  return (
    <div className="app-wrapper">
      <div className="container">

        {/* ── Header ── */}
        <header className="app-header">
          <div className="app-logo">
            <span className="logo-dot"></span>
            ArchivaCloud
          </div>
          <h1 className="app-title">Gestor de Archivos</h1>
          <p className="app-subtitle">
            Sube, visualiza y administra tus imágenes de forma segura en la nube.
          </p>
        </header>

        {/* ── Upload Zone ── */}
        <section
          className={`upload-zone ${isDragging ? 'dragging' : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          id="upload-zone"
        >
          <span className="upload-icon">☁️</span>
          <p className="upload-label">
            Arrastra tu imagen aquí o <strong>selecciónala</strong>
          </p>

          <div className="file-input-wrapper">
            <input
              id="file-input"
              className="file-input"
              type="file"
              accept={ACCEPTED_TYPES}
              onChange={handleFileSelect}
              disabled={isUploading}
            />
            <span className="file-input-btn">📁 Seleccionar archivo</span>
          </div>

          {/* Selected file preview */}
          {selectedFile && !isUploading && (
            <div className="selected-file">
              <span className="file-name">{selectedFile.name}</span>
              <span className="file-size">{formatBytes(selectedFile.size)}</span>
            </div>
          )}

          {/* Upload button */}
          {selectedFile && !isUploading && (
            <button
              className="btn btn-primary"
              onClick={handleUpload}
              id="upload-btn"
            >
              ⬆ Subir Archivo
            </button>
          )}

          {/* Loading state */}
          {isUploading && (
            <>
              <div className="loader-bar">
                <div className="loader-bar-inner"></div>
              </div>
              <p className="loader-text">Comprimiendo y subiendo archivo...</p>
            </>
          )}

          {/* Status message */}
          {statusMsg && (
            <div className={`status-message status-${statusMsg.type}`}>
              {statusMsg.type === 'success' ? '✓' : '✕'} {statusMsg.text}
            </div>
          )}
        </section>

        {/* ── Gallery Section ── */}
        <div className="section-header">
          <h2 className="section-title">Galería</h2>
          {!isLoadingFiles && files.length > 0 && (
            <span className="file-count">
              {files.length} {files.length === 1 ? 'archivo' : 'archivos'}
            </span>
          )}
        </div>

        {/* Loading skeletons */}
        {isLoadingFiles && (
          <div className="skeleton-grid">
            {[1, 2, 3].map((i) => (
              <div className="skeleton-card" key={i}>
                <div className="skeleton-image"></div>
                <div className="skeleton-body">
                  <div className="skeleton-line skeleton-line-long"></div>
                  <div className="skeleton-line skeleton-line-short"></div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Empty state */}
        {!isLoadingFiles && files.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-icon">📂</div>
            <p className="empty-state-text">No hay archivos aún</p>
            <p className="empty-state-sub">Sube tu primera imagen para comenzar.</p>
          </div>
        )}

        {/* Gallery grid */}
        {!isLoadingFiles && files.length > 0 && (
          <div className="gallery-grid">
            {files.map((file, idx) => (
              <article
                className="gallery-card"
                key={file.key}
                style={{ animationDelay: `${idx * 60}ms` }}
              >
                <div className="gallery-card-image-wrapper">
                  <img
                    className="gallery-card-image"
                    src={file.url}
                    alt={extractFileName(file.key)}
                    loading="lazy"
                  />
                </div>
                <div className="gallery-card-body">
                  <div className="gallery-card-info">
                    <p className="gallery-card-name" title={extractFileName(file.key)}>
                      {extractFileName(file.key)}
                    </p>
                    <p className="gallery-card-meta">
                      {formatBytes(file.size)} · {formatDate(file.lastModified)}
                    </p>
                  </div>
                  <button
                    className="btn btn-danger"
                    onClick={() => handleDelete(file.key)}
                    disabled={deletingKey === file.key}
                    id={`delete-btn-${idx}`}
                  >
                    {deletingKey === file.key ? '...' : '✕ Eliminar'}
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
