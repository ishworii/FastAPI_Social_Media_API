FROM python:3.12

# Install poetry
RUN pip install poetry

# Configure poetry to not create a virtual environment inside container
RUN poetry config virtualenvs.create false

WORKDIR /fastapi_server

# Copy poetry files
COPY pyproject.toml poetry.lock ./

# Install dependencies (only production dependencies)
RUN poetry install --only main --no-root

# Copy application code
COPY /app ./app
COPY /tests ./tests
COPY /.env.docker .env

EXPOSE 8000

# Use poetry to run the FastAPI application
CMD ["poetry", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]