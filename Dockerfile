FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies (curl for healthchecks, etc.)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc curl \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml first to cache pip installation
COPY pyproject.toml /app/

# Install dependencies (ignoring the 'core' package missing error by using pip install with specific packages, or just copying the source code)
# Since pip install . requires the source files listed in pyproject.toml to exist, we'll copy everything here.
# Thanks to .dockerignore, .venv and other heavy files won't be copied.
COPY . /app/

# Install the application and its dependencies
RUN pip install --no-cache-dir .

# Start the application using uvicorn
# Render injects the PORT environment variable. We default to 8000 if it's not set.
CMD ["sh", "-c", "uvicorn core.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
