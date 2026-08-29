"""Quick diagnostic: can Python + pikepdf open a small PDF at all?"""

import io
import sys
print("python:", sys.executable)
print("version:", sys.version)

import pikepdf
print("pikepdf:", pikepdf.__version__)

# Tiny in-memory PDF — one blank page, no text.
tiny = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n191\n%%EOF\n"

print("opening tiny PDF...")
pdf = pikepdf.open(io.BytesIO(tiny))
print("pages:", len(pdf.pages))
pdf.close()
print("OK")
