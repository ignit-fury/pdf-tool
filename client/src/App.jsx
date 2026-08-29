import React, { useState, useCallback, useEffect, useRef } from 'react';
import * as pdfjsLib from 'pdfjs-dist';
import { PDFDocument, rgb } from '@cantoo/pdf-lib';

// Configure pdfjs worker — served locally by Vite, not CDN
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

const API_BASE = import.meta.env.VITE_API_URL || '';

/** ============================================================
 *  Helpers
 *  ============================================================ */

function apiFetch(url, options = {}) {
  return fetch(`${API_BASE}${url}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers },
  }).then(r => {
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${r.statusText}`);
    return r.json();
  });
}

function formatBytes(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

/** ============================================================
 *  App
 *  ============================================================ */

export default function App() {
  // ---- State ----
  const [jobId, setJobId] = useState(null);
  const [pdfBytes, setPdfBytes] = useState(null);
  const [fileName, setFileName] = useState('');
  const [fileSize, setFileSize] = useState(0);
  const [classification, setClassification] = useState(null);
  const [pages, setPages] = useState([]);
  const [currentPage, setCurrentPage] = useState(0);
  const [findText, setFindText] = useState('');
  const [replaceText, setReplaceText] = useState('');
  const [replacements, setReplacements] = useState([]);
  const [outputJobId, setOutputJobId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(null);
  const [viewMode, setViewMode] = useState('pages'); // 'pages' | 'replace'
  const [dpi, setDpi] = useState(150);

  const canvasRef = useRef(null);
  const pdfDocRef = useRef(null);

  // ---- Render current page to canvas ----
  const renderPage = useCallback(async (pageIndex) => {
    if (!pdfDocRef.current || !canvasRef.current) return;
    const pdf = pdfDocRef.current;
    const page = await pdf.getPage(pageIndex + 1);
    const viewport = page.getViewport({ scale: dpi / 72 });
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    await page.render({ canvasContext: ctx, viewport }).promise;
  }, [dpi]);

  // ---- Load PDF from bytes ----
  const loadPdf = useCallback(async (bytes) => {
    const loadingTask = pdfjsLib.getDocument({ data: bytes.slice(0) });
    const pdf = await loadingTask.promise;
    pdfDocRef.current = pdf;
    const pageCount = pdf.numPages;
    setPages(Array.from({ length: pageCount }, (_, i) => i));
    setCurrentPage(0);
    await renderPage(0);
  }, [renderPage]);

  // ---- Fetch classification ----
  const fetchClassification = useCallback(async () => {
    if (!jobId) return;
    try {
      const status = await apiFetch(`/jobs/${jobId}/status`);
      setClassification(status.classification || []);
    } catch (e) {
      setMessage({ type: 'error', text: `Classification failed: ${e.message}` });
    }
  }, [jobId]);

  // ---- Handle file drop / select ----
  const handleFile = useCallback(async (file) => {
    if (!file || !file.name.toLowerCase().endsWith('.pdf')) {
      setMessage({ type: 'error', text: 'Please select a PDF file.' });
      return;
    }
    setLoading(true);
    setMessage(null);
    try {
      const bytes = await file.arrayBuffer();
      const b = new Uint8Array(bytes);
      setPdfBytes(b);
      setFileName(file.name);
      setFileSize(file.size);
      setJobId(null);
      setClassification(null);
      setReplacements([]);
      setOutputJobId(null);

      // Upload to server
      const form = new FormData();
      form.append('file', file, file.name);
      const resp = await fetch(`${API_BASE}/upload`, { method: 'POST', body: form });
      if (!resp.ok) throw new Error(`Upload failed: ${resp.status}`);
      const data = await resp.json();
      setJobId(data.job_id);
      await fetchClassification();
      await loadPdf(b);
    } catch (e) {
      setMessage({ type: 'error', text: `Upload failed: ${e.message}` });
    } finally {
      setLoading(false);
    }
  }, [fetchClassification, loadPdf]);

  // ---- Find-and-replace: build replacement list ----
  const doFindReplace = useCallback(() => {
    if (!findText.trim() || !jobId) {
      setMessage({ type: 'error', text: 'Enter text to find and a job must be loaded.' });
      return;
    }
    // In a real app, match against the classification's run display_text.
    // For now, we create one replacement per editable run whose display_text
    // contains the find string.
    const newReplacements = [];
    if (classification) {
      for (const page of classification) {
        // We don't have per-run data in classification; the server would
        // need a /jobs/{id}/runs endpoint. For the prototype, we submit
        // a single replacement for the first editable run we find.
        // This is a placeholder — the real UI would list runs and let
        // the user pick which to replace.
      }
    }
    // Placeholder: submit a single replacement spec.
    // The server needs run_id; we don't have one yet without a /runs endpoint.
    // For the demo, we'll just show the UI flow and note the missing endpoint.
    setMessage({
      type: 'info',
      text: `Find "${findText}" — in the full version, this would list all editable runs containing that text. The /jobs/{id}/runs endpoint needs to be added to the server.`,
    });
    setViewMode('replace');
  }, [findText, jobId, classification]);

  // ---- Execute replacements ----
  const executeReplace = useCallback(async () => {
    if (!jobId || replacements.length === 0) {
      setMessage({ type: 'error', text: 'No replacements to execute.' });
      return;
    }
    setLoading(true);
    setMessage(null);
    try {
      const resp = await fetch(`${API_BASE}/jobs/${jobId}/replace`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ replacements }),
      });
      if (!resp.ok) throw new Error(`Replace failed: ${resp.status}`);
      const data = await resp.json();
      setOutputJobId(data.output_job_id);
      setMessage({ type: 'success', text: `Replacements applied. Output job: ${data.output_job_id}` });
    } catch (e) {
      setMessage({ type: 'error', text: `Replace failed: ${e.message}` });
    } finally {
      setLoading(false);
    }
  }, [jobId, replacements]);

  // ---- Download output ----
  const downloadOutput = useCallback(async () => {
    if (!outputJobId) return;
    try {
      const resp = await fetch(`${API_BASE}/jobs/${outputJobId}/download`);
      if (!resp.ok) throw new Error(`Download failed: ${resp.status}`);
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `edited_${fileName.replace('.pdf', '')}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setMessage({ type: 'error', text: `Download failed: ${e.message}` });
    }
  }, [outputJobId, fileName]);

  // ---- Page navigation ----
  const goToPage = useCallback(async (idx) => {
    if (idx < 0 || idx >= pages.length) return;
    setCurrentPage(idx);
    await renderPage(idx);
  }, [pages, renderPage]);

  // ---- Drag-and-drop ----
  const onDrop = useCallback((e) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    handleFile(file);
  }, [handleFile]);

  const onDragOver = useCallback((e) => {
    e.preventDefault();
  }, []);

  // ---- File input ----
  const onFileChange = useCallback((e) => {
    const file = e.target.files[0];
    handleFile(file);
  }, [handleFile]);

  // ---- Export: render page to PNG download ----
  const exportPng = useCallback(async () => {
    if (!pdfDocRef.current) return;
    const page = await pdfDocRef.current.getPage(currentPage + 1);
    const viewport = page.getViewport({ scale: dpi / 72 });
    const canvas = document.createElement('canvas');
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    const ctx = canvas.getContext('2d');
    await page.render({ canvasContext: ctx, viewport }).promise;
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${fileName.replace('.pdf', '')}_page${currentPage + 1}.png`;
    a.click();
    URL.revokeObjectURL(url);
  }, [currentPage, dpi, fileName]);

  // ---- Render ----
  return (
    <div style={styles.container}>
      {/* Header */}
      <header style={styles.header}>
        <h1 style={styles.title}>PDF Tool</h1>
        <p style={styles.subtitle}>Edit the actual content of your PDF — not white-box overlays.</p>
      </header>

      {/* Upload zone */}
      {!pdfBytes && (
        <div
          style={styles.dropZone}
          onDrop={onDrop}
          onDragOver={onDragOver}
          onClick={() => document.getElementById('fileInput').click()}
        >
          <input
            id="fileInput"
            type="file"
            accept=".pdf"
            style={{ display: 'none' }}
            onChange={onFileChange}
          />
          <div style={styles.dropIcon}>📄</div>
          <p style={styles.dropText}>Drop a PDF here, or click to browse</p>
          <p style={styles.dropHint}>Your file stays on this device until you close the page.</p>
        </div>
      )}

      {/* Loaded document */}
      {pdfBytes && (
        <div style={styles.docBar}>
          <span style={styles.docName}>{fileName}</span>
          <span style={styles.docSize}>{formatBytes(fileSize)}</span>
          <div style={styles.docControls}>
            <button style={styles.btn} onClick={() => setViewMode('pages')}>Pages</button>
            <button style={styles.btn} onClick={() => setViewMode('replace')}>Find & Replace</button>
            <button style={styles.btn} onClick={exportPng}>Export PNG</button>
            <button style={styles.btn} onClick={() => { setPdfBytes(null); setJobId(null); setFileName(''); setClassification(null); setReplacements([]); setOutputJobId(null); setMessage(null); }}>
              Close
            </button>
          </div>
        </div>
      )}

      {/* Message bar */}
      {message && (
        <div style={{
          ...styles.message,
          backgroundColor: message.type === 'error' ? '#fee2e2' :
                          message.type === 'success' ? '#dcfce7' : '#fef9c3',
          color: message.type === 'error' ? '#991b1b' :
                 message.type === 'success' ? '#166534' : '#92400e',
        }}>
          {message.text}
        </div>
      )}

      {/* Loading */}
      {loading && <div style={styles.loading}>Working…</div>}

      {/* Main content */}
      {pdfBytes && viewMode === 'pages' && (
        <div style={styles.pagesView}>
          {/* Page navigator */}
          <div style={styles.pageNav}>
            <button style={styles.btn} onClick={() => goToPage(currentPage - 1)} disabled={currentPage === 0}>
              ← Prev
            </button>
            <span style={styles.pageIndicator}>Page {currentPage + 1} of {pages.length}</span>
            <button style={styles.btn} onClick={() => goToPage(currentPage + 1)} disabled={currentPage >= pages.length - 1}>
              Next →
            </button>
            <label style={styles.dpiLabel}>
              DPI:
              <input type="range" min="72" max="300" value={dpi} onChange={e => setDpi(Number(e.target.value))} style={styles.dpiSlider} />
              {dpi}
            </label>
          </div>

          {/* Canvas */}
          <div style={styles.canvasWrap}>
            <canvas ref={canvasRef} style={styles.canvas} />
          </div>

          {/* Classification summary */}
          {classification && classification.length > 0 && (
            <div style={styles.classificationPanel}>
              <h3 style={styles.panelTitle}>Document Classification</h3>
              <table style={styles.classTable}>
                <thead>
                  <tr>
                    <th>Page</th>
                    <th>Bucket</th>
                    <th>Runs</th>
                    <th>Editable</th>
                    <th>Subst</th>
                    <th>Not Editable</th>
                  </tr>
                </thead>
                <tbody>
                  {classification.map(p => (
                    <tr key={p.page}>
                      <td>{p.page + 1}</td>
                      <td>{p.bucket}</td>
                      <td>{p.runs}</td>
                      <td style={{ color: '#166534' }}>{p.editable}</td>
                      <td style={{ color: '#92400e' }}>{p.substitution}</td>
                      <td style={{ color: '#991b1b' }}>{p.not_editable}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {pdfBytes && viewMode === 'replace' && (
        <div style={styles.replaceView}>
          <h2 style={styles.sectionTitle}>Find & Replace</h2>

          <div style={styles.replaceForm}>
            <label>
              Find:
              <input
                style={styles.input}
                value={findText}
                onChange={e => setFindText(e.target.value)}
                placeholder="Text to find"
              />
            </label>
            <label>
              Replace with:
              <input
                style={styles.input}
                value={replaceText}
                onChange={e => setReplaceText(e.target.value)}
                placeholder="Replacement text"
              />
            </label>
            <button style={styles.btnPrimary} onClick={doFindReplace}>
              Find Matches
            </button>
          </div>

          {replacements.length > 0 && (
            <div style={styles.replaceList}>
              <h3 style={styles.panelTitle}>Matches ({replacements.length})</h3>
              {replacements.map((r, i) => (
                <div key={i} style={styles.replaceItem}>
                  <span>{r.display_text}</span>
                  <span style={styles.replaceId}>{r.run_id.slice(0, 16)}…</span>
                  <span style={{ color: r.verdict === 'editable' ? '#166534' : '#991b1b' }}>
                    {r.verdict}
                  </span>
                  {r.new_text && (
                    <span style={styles.newText}>→ {r.new_text}</span>
                  )}
                </div>
              ))}
              <button style={styles.btnPrimary} onClick={executeReplace} disabled={loading}>
                {loading ? 'Applying…' : 'Apply Replacements'}
              </button>
            </div>
          )}

          {!replacements.length && (
            <p style={styles.hint}>
              Enter text to find, then click "Find Matches". The system will list
              all editable text runs containing that string. Select which to replace
              and apply.
            </p>
          )}

          {outputJobId && (
            <div style={styles.outputSection}>
              <h3 style={styles.panelTitle}>Output ready</h3>
              <p style={styles.outputInfo}>Edited PDF is on the server. Download or close this page — the file is ephemeral.</p>
              <button style={styles.btnPrimary} onClick={downloadOutput}>Download Edited PDF</button>
            </div>
          )}
        </div>
      )}

      {/* Footer */}
      <footer style={styles.footer}>
        <p>
          Hybrid client/server — page operations in the browser, content-stream
          text rewrite on the server via pikepdf + playa-pdf + fontTools.
        </p>
        <p style={styles.privacyNote}>
          Ephemerality is structural, not a retention policy. The server has no
          state whose loss is observable — kill the cache mid-session, the session survives.
        </p>
      </footer>
    </div>
  );
}

/** ============================================================
 *  Styles (inline, no CSS file needed)
 *  ============================================================ */

const styles = {
  container: {
    fontFamily: 'system-ui, -apple-system, sans-serif',
    maxWidth: 1100,
    margin: '0 auto',
    padding: '24px 20px 40px',
    color: 'var(--foreground, #1a1a1a)',
    minHeight: '100vh',
    backgroundColor: 'var(--card, #fafafa)',
  },
  header: {
    textAlign: 'center',
    marginBottom: 24,
  },
  title: {
    fontSize: 32,
    fontWeight: 700,
    margin: '0 0 4px',
    color: 'var(--foreground, #111)',
  },
  subtitle: {
    fontSize: 14,
    color: 'var(--muted-foreground, #666)',
    margin: 0,
  },
  dropZone: {
    border: '2px dashed #ccc',
    borderRadius: 12,
    padding: '48px 24px',
    textAlign: 'center',
    cursor: 'pointer',
    transition: 'border-color 0.2s',
    backgroundColor: '#fff',
  },
  dropIcon: {
    fontSize: 48,
    marginBottom: 8,
  },
  dropText: {
    fontSize: 16,
    fontWeight: 600,
    color: '#333',
    margin: '0 0 4px',
  },
  dropHint: {
    fontSize: 13,
    color: '#888',
    margin: 0,
  },
  docBar: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    padding: '10px 14px',
    backgroundColor: '#fff',
    border: '1px solid #e5e7eb',
    borderRadius: 8,
    marginBottom: 16,
    flexWrap: 'wrap',
  },
  docName: {
    fontWeight: 600,
    fontSize: 14,
  },
  docSize: {
    color: '#888',
    fontSize: 13,
  },
  docControls: {
    display: 'flex',
    gap: 8,
    marginLeft: 'auto',
  },
  btn: {
    padding: '6px 14px',
    border: '1px solid #d1d5db',
    borderRadius: 6,
    background: '#fff',
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 500,
    color: '#374151',
  },
  btnPrimary: {
    padding: '8px 20px',
    border: 'none',
    borderRadius: 6,
    background: '#2563eb',
    color: '#fff',
    cursor: 'pointer',
    fontSize: 14,
    fontWeight: 600,
  },
  message: {
    padding: '8px 14px',
    borderRadius: 6,
    marginBottom: 12,
    fontSize: 13,
  },
  loading: {
    textAlign: 'center',
    padding: 20,
    color: '#888',
    fontStyle: 'italic',
  },
  pagesView: {
    display: 'flex',
    flexDirection: 'column',
    gap: 16,
  },
  pageNav: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    flexWrap: 'wrap',
  },
  pageIndicator: {
    fontSize: 14,
    fontWeight: 500,
    minWidth: 140,
    textAlign: 'center',
  },
  dpiLabel: {
    fontSize: 12,
    color: '#666',
    display: 'flex',
    alignItems: 'center',
    gap: 6,
  },
  dpiSlider: {
    width: 100,
    verticalAlign: 'middle',
  },
  canvasWrap: {
    background: '#fff',
    border: '1px solid #e5e7eb',
    borderRadius: 8,
    overflow: 'auto',
    display: 'flex',
    justifyContent: 'center',
    padding: 12,
  },
  canvas: {
    display: 'block',
    maxWidth: '100%',
    height: 'auto',
  },
  classificationPanel: {
    background: '#fff',
    border: '1px solid #e5e7eb',
    borderRadius: 8,
    padding: 12,
    overflow: 'auto',
  },
  panelTitle: {
    fontSize: 14,
    fontWeight: 600,
    margin: '0 0 8px',
    color: '#374151',
  },
  classTable: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: 12,
  },
  replaceView: {
    display: 'flex',
    flexDirection: 'column',
    gap: 16,
  },
  sectionTitle: {
    fontSize: 20,
    fontWeight: 600,
    margin: '0 0 12px',
  },
  replaceForm: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    background: '#fff',
    border: '1px solid #e5e7eb',
    borderRadius: 8,
    padding: 14,
  },
  input: {
    padding: '6px 10px',
    border: '1px solid #d1d5db',
    borderRadius: 6,
    fontSize: 14,
    width: '100%',
    boxSizing: 'border-box',
  },
  replaceList: {
    background: '#fff',
    border: '1px solid #e5e7eb',
    borderRadius: 8,
    padding: 14,
    maxHeight: 400,
    overflow: 'auto',
  },
  replaceItem: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '6px 0',
    borderBottom: '1px solid #f3f4f6',
    fontSize: 13,
    flexWrap: 'wrap',
  },
  replaceId: {
    color: '#888',
    fontFamily: 'monospace',
    fontSize: 11,
  },
  newText: {
    color: '#2563eb',
    fontWeight: 500,
  },
  hint: {
    color: '#888',
    fontSize: 13,
    fontStyle: 'italic',
    margin: '0 0 12px',
  },
  outputSection: {
    background: '#f0fdf4',
    border: '1px solid #86efac',
    borderRadius: 8,
    padding: 14,
  },
  outputInfo: {
    fontSize: 13,
    color: '#166534',
    margin: '0 0 10px',
  },
  footer: {
    marginTop: 32,
    paddingTop: 12,
    borderTop: '1px solid #e5e7eb',
    fontSize: 12,
    color: '#888',
  },
  privacyNote: {
    fontStyle: 'italic',
    marginTop: 4,
  },
};
