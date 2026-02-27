FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY backend/    ./backend/
COPY blockchain/ ./blockchain/
COPY frontend/   ./frontend/

# Create data directories
RUN mkdir -p /app/data

# The voter registry DB and chain file live in /app/data (volume-mounted)
ENV PYTHONUNBUFFERED=1
ENV PORT=5000

EXPOSE 5000

# Override DB and chain paths to use /app/data at runtime via env
# (api.py reads these via the module defaults which resolve relative to __file__)
# We symlink the data directory into the expected locations
CMD ["sh", "-c", "\
  ln -sf /app/data/voter_registry.db /app/backend/voter_registry.db 2>/dev/null || true && \
  ln -sf /app/data/chain.json /app/blockchain/chain.json 2>/dev/null || true && \
  python /app/backend/api.py \
"]
